#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两个搜索源的 adapter，统一归一化成 Doc。

源：
- doubao    POST /search_api/web_search（Custom 版：如意卡片、行业/站点/时间过滤、RankScore、正文）
- parallel  parallel-cli 子进程，或 POST https://api.parallel.ai/v1/search

只用豆包 Custom 版，不接 Global 版：Global 仅支持按量后付费、吃不到订阅套餐额度，
而它相对 Custom 的独占项（全球站点覆盖、可控长摘要）由 Parallel 覆盖得更好
——Custom 的 Content 本来就给全文，比 Global 的 3000 token 片段更完整。
代价是失去 Global 的图搜图（SearchType=visual），本 skill 未使用该能力。

重要：豆包请求体一律 PascalCase。服务端按字段名精确匹配，
传 doc_count / max_snippet_length 会被静默丢弃而不报错（huashu 的 MCP 就栽在这里）。
字段定义见 references/doubao-api.md，改动前先核对文档，不要凭记忆写。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import config as cfgmod

DOUBAO_TIMEOUT = 20
PARALLEL_TIMEOUT = 40
EXTRACT_TIMEOUT = 60

AUTHORITY_LABEL = {1: "非常权威", 2: "正常权威", 3: "一般权威", 4: "一般不权威"}

_TIME_RANGE_ENUM = {"OneDay", "OneWeek", "OneMonth", "OneYear"}
# 用 fullmatch 而不是 match + ^$：`$` 也匹配串尾换行之前的位置，
# 于是 "2026-01-01..2026-09-04\n" 会被判为合法并原样发给上游。
_TIME_RANGE_SPAN = re.compile(r"(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})")

TIME_RANGE_HINT = "应为 OneDay/OneWeek/OneMonth/OneYear 或 YYYY-MM-DD..YYYY-MM-DD（起始日期不得晚于结束日期）"


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Parallel 官方建议每条 3~6 个词、给 2~3 条，上限 5 条
MAX_KEYWORDS = 5
# 缓存命名空间与 transport 无关：同一份请求无论走 CLI 还是 HTTP 都命中同一条缓存
PARALLEL_CACHE_NS = "parallel"


def normalize_keywords(queries: list[str] | None) -> list[str]:
    """关键词的**唯一**规范化入口：去空白、丢空串、截到上游上限。

    CLI 通路、HTTP 通路和缓存指纹必须共用这一份结果，三处各写各的会让指纹
    和真正发出去的请求对不上：["", "a".."e"] 与 ["a".."e"] 曾算出相同指纹，
    而 CLI 实际发的是「空串 + a..d」和「a..e」——两个不同的请求共用了同一份缓存。
    """
    return [q.strip() for q in (queries or []) if q and q.strip()][:MAX_KEYWORDS]


def resolve_search_queries(objective: str, queries: list[str] | None) -> list[str]:
    """两条通路最终发出的 search_queries——**唯一**的决定处。

    /v1/search 的 search_queries 是必填项，没给 --pq 时只能用 objective 兜一条。
    CLI 过去在这种情况下不传任何 -q，于是同一个逻辑查询在装了 parallel-cli 的机器上
    和没装的机器上发的是**不同的请求**、可能拿到不同的结果——而 transport 走 auto 时
    用户根本不知道自己走的是哪条。统一成一份之后两条通路发的东西一致，
    缓存也就能共用一个命名空间，装卸 CLI 不再让缓存整个作废。
    """
    return normalize_keywords(queries) or [(objective or "").strip()[:120]]


def valid_date(value: str) -> bool:
    """严格 YYYY-MM-DD，再做真日历校验。两道都不能省：

    - 只做正则：2026-13-45 格式对但不是存在的日期；
    - 只做 fromisoformat：Python 3.11 起它还接受 20260904 和 2026-W01-1，
      而报错文案和上游契约都只认 YYYY-MM-DD——放过去等于把格式问题推给服务端，
      换来的是一个语焉不详的远端报错。
    """
    if not _ISO_DATE.fullmatch(value or ""):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def valid_time_range(value: str) -> bool:
    """校验 --time-range，见 references/doubao-api.md。

    只对格式做正则匹配是不够的：2026-13-45 能通过正则但不是合法日期，
    2026-09-03..2026-01-01 顺序颠倒，两者都会被上游按未定义行为处理。
    """
    if value in _TIME_RANGE_ENUM:
        return True
    match = _TIME_RANGE_SPAN.fullmatch(value)
    if not match:
        return False
    start, end = match.group(1), match.group(2)
    if not (valid_date(start) and valid_date(end)):
        return False
    return date.fromisoformat(start) <= date.fromisoformat(end)

# 网页样板噪声：导航、页脚、文档站控件等，对回答无贡献但吃 token。
# 允许外面套一层 markdown 链接——抓取结果里这些词通常是 [登录](https://...) 的形式。
_NOISE_WORDS = (
    r"登录|注册|复制全文|下载\s*pdf|我的收藏|文档中心|文档首页|文档指南|在线咨询|"
    r"这个页面对您有帮助吗[？?]?|有用|无用|上一篇|下一篇|返回顶部|展开|收起|我知道了|不再提醒|"
    r"Skip to (?:main )?content|Cookie(?:s)? (?:settings|policy)|Sign in|Sign up|Log ?in|Menu"
)
_NOISE_LINE = re.compile(
    rf"^\s*(?:\[\s*)?(?:{_NOISE_WORDS})(?:\s*\]\([^)]*\))?\s*$", re.IGNORECASE
)
# 整行只有两个以上 markdown 链接、没有其他文字 —— 基本可以断定是导航条
_LINK_ONLY_LINE = re.compile(r"^\s*(?:\[[^\]]*\]\([^)]*\)[\s|·,、]*){2,}$")
_NOISE_WINDOW = 40  # 同一行在这个窗口内重复出现即视为导航重复
# 只有**带 markdown 链接**的行才参与重复去除。
# 无差别去重会静默删掉正文：两段结构相同的代码示例里，第二段的 `return None`
# 直接消失；表格行、重复日志同理。而 SKILL.md 恰恰把 fetch 定位到文档站。
# 导航条在抓取结果里本来就是链接行，限定到链接行既保住了原本的收益，
# 又不会碰到正文——宁可漏删几行菜单，也不能删用户要读的内容。
_HAS_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
# 零宽与方向控制字符：抓取内容里很常见，白占 token 还会干扰去重比对
_ZERO_WIDTH = re.compile("[­​-‏‪-‮⁠﻿]")
_BLANK_RUN = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """清掉零宽字符、样板噪声行和重复的导航行，折叠多余空行。

    导航条在抓取结果里常常整段重复出现两三次（响应式站点的移动版 + 桌面版菜单），
    不去重的话能吃掉整页预算 —— 实测火山引擎文档站的前 3000 字符几乎全是菜单。
    """
    if not text:
        return ""
    text = _ZERO_WIDTH.sub("", text)
    kept: list[str] = []
    recent: dict[str, int] = {}
    for index, raw in enumerate(text.splitlines()):
        line = raw.rstrip()
        if _NOISE_LINE.match(line) or _LINK_ONLY_LINE.match(line):
            continue
        stripped = line.strip()
        if len(stripped) > 2 and _HAS_LINK.search(stripped):
            seen_at = recent.get(stripped)
            if seen_at is not None and index - seen_at <= _NOISE_WINDOW:
                recent[stripped] = index
                continue
            recent[stripped] = index
        kept.append(line)
    return _BLANK_RUN.sub("\n\n", "\n".join(kept)).strip()


@dataclass
class Doc:
    """跨源归一化后的单篇文档。"""

    url: str
    title: str
    body: str
    site: str
    source: str
    rank: int
    publish: str | None = None
    authority: int | None = None
    rank_score: float | None = None
    images: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)


@dataclass
class SourceResult:
    """单个源的调用结果。失败不抛异常，让编排层继续用其他源。"""

    source: str
    docs: list[Doc] = field(default_factory=list)
    cards: list[dict] = field(default_factory=list)
    error: str | None = None
    elapsed: float = 0.0
    cached: bool = False
    raw: Any = None
    request: Any = None
    # 上游"成功但有保留"的信号（spec/input 校验告警、降级提示）。
    # 它不是 error——请求成功了——但可能意味着请求没被完整执行，
    # 只塞进 raw 等于让它消失：--no-dump 时连翻都没处翻。
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 豆包


def build_doubao_payload(query: str, opts: dict, cfg: dict) -> dict:
    """构造豆包 Custom 版请求体。字段名必须与官方文档逐字一致（PascalCase）。"""
    query = (query or "").strip()[:100]  # 官方限制 1~100 字符，过长会被截断
    search_type = opts.get("search_type", "web")

    conf = cfg["doubao"]
    max_count = 5 if search_type == "image" else 50
    count = int(opts.get("count") or conf["count"])
    payload: dict[str, Any] = {
        "Query": query,
        "SearchType": search_type,
        "Count": max(1, min(count, max_count)),
        "EnableWaiting": True,
        "MaxWaitTime": 5000,
    }
    if search_type == "image":
        image_filter = {
            k: v
            for k, v in {
                "ImageWidthMin": opts.get("image_width_min"),
                "ImageHeightMin": opts.get("image_height_min"),
                "ImageWidthMax": opts.get("image_width_max"),
                "ImageHeightMax": opts.get("image_height_max"),
            }.items()
            if v is not None
        }
        if image_filter:
            payload["Filter"] = image_filter
        if conf.get("query_rewrite"):
            payload["QueryControl"] = {"QueryRewrite": True}
        return payload

    # 只发与服务端默认值不同的过滤条件。NeedUrl / AuthInfoLevel / Industry
    # 都会滤掉如意结果，默认一个都不发，免得无意中关掉结构化卡片。
    filters: dict[str, Any] = {}
    if opts.get("need_url") or conf.get("need_url", False):
        filters["NeedUrl"] = True
    if opts.get("need_content") or conf.get("need_content", False):
        filters["NeedContent"] = True
    if opts.get("sites"):
        filters["Sites"] = "|".join(opts["sites"][:20])
    if opts.get("block_hosts"):
        filters["BlockHosts"] = "|".join(opts["block_hosts"][:5])
    if opts.get("authoritative") or conf.get("auth_info_level"):
        filters["AuthInfoLevel"] = 1
    if filters:
        payload["Filter"] = filters

    if opts.get("time_range"):
        payload["TimeRange"] = opts["time_range"]
    if opts.get("query_rewrite", conf.get("query_rewrite")):
        payload["QueryControl"] = {"QueryRewrite": True}
    if conf.get("content_formats"):
        payload["ContentFormats"] = conf["content_formats"]
    if opts.get("industry"):
        payload["Industry"] = opts["industry"]
    return payload


def _doubao_error(body: dict) -> str | None:
    """从两种错误位置里提取可读的错误信息。"""
    meta_error = (body.get("ResponseMetadata") or {}).get("Error")
    if meta_error:
        code = meta_error.get("Code") or meta_error.get("CodeN")
        return f"{code} {meta_error.get('Message', '')}".strip()
    result = body.get("Result")
    if isinstance(result, dict) and result.get("ErrorCode"):
        return f"{result['ErrorCode']} {result.get('ErrorMsg', '')}".strip()
    if result is None:
        return "服务端返回 Result 为 null"
    return None


def _post_json(url: str, payload: dict, api_key: str, timeout: int) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _map_custom(body: dict) -> tuple[list[Doc], list[dict]]:
    """映射 Custom 版响应。web 搜索读 WebResults，图片搜索读 ImageResults。"""
    result = body.get("Result") or {}
    docs: list[Doc] = []

    for index, item in enumerate(result.get("WebResults") or []):
        # 官方文档：Summary(500~1000字) 推荐用于大模型场景；
        # Snippet(约200字) 明确标注「强烈不建议用于大模型场景」，只作兜底。
        body_text = item.get("Summary") or item.get("Content") or item.get("Snippet") or ""
        docs.append(
            Doc(
                url=item.get("Url") or "",
                title=item.get("Title") or "",
                body=clean_text(body_text),
                site=item.get("SiteName") or "",
                source="doubao",
                rank=item.get("SortId", index) if isinstance(item.get("SortId"), int) else index,
                publish=item.get("PublishTime") or None,
                authority=item.get("AuthInfoLevel"),
                rank_score=item.get("RankScore"),
                images=[
                    {
                        "url": img.get("ImageUrl"),
                        "width": img.get("Width"),
                        "height": img.get("Height"),
                        "alt": img.get("Alt"),
                    }
                    for img in (item.get("InlineImages") or [])
                ],
                extra={
                    "ruyi": (item.get("RuyiInfo") or {}).get("Type"),
                    "content_formats": item.get("ContentFormats"),
                    "auth_desc": item.get("AuthInfoDes"),
                },
            )
        )

    for index, item in enumerate(result.get("ImageResults") or []):
        image = item.get("Image") or {}
        features = image.get("Features") or {}
        docs.append(
            Doc(
                url=item.get("Url") or "",
                title=item.get("Title") or "",
                body=features.get("Description") or "",
                site=item.get("SiteName") or "",
                source="doubao",
                rank=item.get("SortId", index) if isinstance(item.get("SortId"), int) else index,
                publish=item.get("PublishTime") or None,
                rank_score=item.get("RankScore"),
                images=[
                    {
                        "url": image.get("Url"),
                        "width": image.get("Width"),
                        "height": image.get("Height"),
                        "alt": features.get("Description") or item.get("Title"),
                        "shape": image.get("Shape"),
                        "blur": image.get("BlurDes"),
                        "watermark": "有水印" if str(image.get("Watermark")) == "1" else None,
                        "style": features.get("StyleType"),
                    }
                ],
                extra={"category": image.get("Category"), "entity": features.get("EntityType")},
            )
        )

    return docs, list(result.get("CardResults") or [])


def doubao_search(cfg: dict, query: str, opts: dict, dry_run: bool = False) -> SourceResult:
    """调用豆包 Custom 版。异常一律收敛成 SourceResult.error，不向上抛。"""
    name = "doubao"
    # 入参合法性由调用层在任何 source 调用之前统一校验（gr_search.validate_search_args），
    # 这里不再重复检查：那样会产出一个没有 request 的 SourceResult，dry-run 读它就崩。
    payload = build_doubao_payload(query, opts, cfg)
    url = cfgmod.DOUBAO_URL
    request_info = {"url": url, "payload": payload}
    if dry_run:
        return SourceResult(source=name, request=request_info)

    api_key, _ = cfgmod.doubao_key(cfg)
    if not api_key:
        return SourceResult(source=name, error="缺少豆包 API Key（运行 config doctor 查看）", request=request_info)

    key = cfgmod.cache_key(name, payload)
    if not opts.get("no_cache"):
        hit = cfgmod.cache_get(cfg, key, ttl=opts.get("cache_ttl"))
        if hit is not None:
            docs, cards = _map_custom(hit)
            return SourceResult(name, docs, cards, cached=True, raw=hit, request=request_info)

    started = time.monotonic()
    body: dict | None = None
    error: str | None = None
    # 10500/10501 是官方标注可重试的内部错误；限流靠 EnableWaiting 队列模式兜底
    for attempt in range(2):
        try:
            body = _post_json(url, payload, api_key, DOUBAO_TIMEOUT)
            error = _doubao_error(body)
            if error and error.split()[0] in ("10500", "10501") and attempt == 0:
                time.sleep(0.8)
                continue
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            error, body = f"HTTP {exc.code} {detail}", None
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            error, body = f"{type(exc).__name__}: {exc}", None
            if attempt == 0:
                time.sleep(0.8)
                continue
            break

    elapsed = time.monotonic() - started
    if error or body is None:
        return SourceResult(name, error=error or "未知错误", elapsed=elapsed, request=request_info)

    docs, cards = _map_custom(body)
    if not opts.get("no_cache"):
        cfgmod.cache_put(cfg, key, body)
    return SourceResult(name, docs, cards, elapsed=elapsed, raw=body, request=request_info)


# ---------------------------------------------------------------- Parallel


def parallel_env(cfg: dict) -> dict[str, str]:
    """把 Parallel 密钥注入子进程环境；没有密钥就沿用本机 OAuth 凭据。

    走环境变量而不是命令行参数，密钥就不会出现在 ps 输出或 shell 历史里。

    **注入的变量名永远是官方的 PARALLEL_API_KEY，不看 api_key_env。**
    api_key_env 只是"从哪个变量读密钥"的输入别名，把它同时当成输出变量名有两个后果，
    都实测过：
    - 配成自定义名字 → CLI 读的仍是 PARALLEL_API_KEY，密钥根本没送到，鉴权静默失效；
    - 配成 PYTHONWARNINGS 这类解释器控制变量 → 子进程把**完整密钥**打进 stderr，
      而那段 stderr 又会被我们当作错误详情显示出来。
    """
    env = dict(os.environ)
    # **先清掉继承来的那把**。只"有密钥就覆盖"是不够的：配了自定义 api_key_env
    # 而该变量恰好没设时，我们解析不出密钥、doctor 如实报告"回落 OAuth"，
    # 可父环境里残留的旧 PARALLEL_API_KEY 却仍会被子进程读到——
    # 于是拿**另一个账号**的密钥去查询、计费、发送数据，而诊断信息还说没在用密钥。
    # 子进程能用的密钥，必须与 parallel_key() 这一次解析出来的完全一致。
    env.pop(cfgmod.PARALLEL_ENV_DEFAULT, None)
    secret, _origin = cfgmod.parallel_key(cfg)
    if secret:
        # 判据是"CLI 读的那个变量里是不是这把密钥"，不是"密钥从哪来"。
        # 曾经按 origin != "env" 跳过注入：配了自定义 api_key_env 并 export 之后，
        # origin 是 env、于是不注入，而 CLI 读的仍是 PARALLEL_API_KEY——
        # 环境里若残留一把旧的，子进程就拿旧密钥去鉴权，
        # `config show` 显示的却是新的那把，两边对不上还查不出来。
        env[cfgmod.PARALLEL_ENV_DEFAULT] = secret
    return env


def redact(text: str, cfg: dict) -> str:
    """把子进程输出里可能出现的密钥换成脱敏占位符。

    纵深防御：即便注入的变量名已经收敛到官方名字，子进程仍可能因为别的原因
    把环境变量回显出来（崩溃转储、调试开关、上游自己打日志）。
    错误详情是要显示给用户的，出口这里再兜一道。
    """
    if not text:
        return text
    for secret, _ in (cfgmod.parallel_key(cfg), cfgmod.doubao_key(cfg)):
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[已脱敏的密钥]")
    return text


def parallel_available(cfg: dict) -> bool:
    """CLI 或 HTTP 任一条通路可用即可。"""
    return resolve_transport(cfg) is not None


def resolve_transport(cfg: dict) -> str | None:
    """确定 Parallel 走哪条通路：cli 需要可执行文件，http 需要密钥。

    返回 None 表示该源不可用（被禁用，或两条通路都不满足）。
    """
    if not cfg["parallel"].get("enabled", True):
        return None
    mode = (cfg["parallel"].get("transport") or "auto").lower()
    has_cli = shutil.which("parallel-cli") is not None
    has_key = bool(cfgmod.parallel_key(cfg)[0])
    if mode == "cli":
        return "cli" if has_cli else None
    if mode == "http":
        return "http" if has_key else None
    if has_cli:
        return "cli"
    return "http" if has_key else None


def build_parallel_cmd(cfg: dict, objective: str, queries: list[str], opts: dict, out_path: str) -> list[str]:
    conf = cfg["parallel"]
    cmd = ["parallel-cli", "search"]
    # 显式传 -q，与 HTTP 通路发出的 search_queries 逐字一致
    for keyword in resolve_search_queries(objective, queries):
        cmd += ["-q", keyword]
    cmd += [
        "--json",
        "--mode", str(opts.get("mode") or conf["mode"]),
        "--max-results", str(int(opts.get("count") or conf["max_results"])),
        "--excerpt-max-chars-total", str(int(conf["excerpt_max_chars_total"])),
        "-o", out_path,
    ]
    if conf.get("client_model"):
        cmd += ["--client-model", str(conf["client_model"])]
    if opts.get("session_id"):
        cmd += ["--session-id", str(opts["session_id"])]
    if opts.get("after_date"):
        cmd += ["--after-date", str(opts["after_date"])]
    # 与 HTTP 通路保持同一套取舍：官方语义是 include 非空时 exclude 被忽略，
    # 两边都只发其中一个，请求才真正等价
    if opts.get("sites"):
        cmd += ["--include-domains", ",".join(opts["sites"])]
    elif opts.get("block_hosts"):
        cmd += ["--exclude-domains", ",".join(opts["block_hosts"])]
    # objective 放在最后，并用 `--` 终止选项解析——它是用户/上层给的自由文本，
    # 以 `-` 开头时会被 click 当成选项：`--help` 让 CLI 打印帮助后正常退出、
    # 却不写结果文件（我们随后崩在 JSONDecodeError 上），`-` 被当成读 stdin 的哨兵。
    # HTTP 通路没这个问题，于是 auto 模式下行为取决于本机装没装 CLI。
    # （已用 CLI 自带的 click 8.5 验证 `--` 的行为，不是照惯例假设。）
    cmd += ["--", objective]
    return cmd


def build_parallel_http_payload(cfg: dict, objective: str, queries: list[str], opts: dict) -> dict:
    """构造 POST /v1/search 的请求体。

    契约来自官方 OpenAPI（V1SearchRequest）：search_queries 必填，
    max_results 在 advanced_settings 里而不是顶层。该 schema 是
    additionalProperties: false，字段名写错会返回 422 而不是被静默忽略。
    """
    conf = cfg["parallel"]
    # 官方建议每条 3~6 个词、给 2~3 条效果最好
    search_queries = resolve_search_queries(objective, queries)
    payload: dict[str, Any] = {
        "search_queries": search_queries,
        "objective": objective,
        "mode": str(opts.get("mode") or conf["mode"]),
        "max_chars_total": int(conf["excerpt_max_chars_total"]),
    }
    if conf.get("client_model"):
        payload["client_model"] = str(conf["client_model"])
    if opts.get("session_id"):
        payload["session_id"] = str(opts["session_id"])

    advanced: dict[str, Any] = {"max_results": int(opts.get("count") or conf["max_results"])}
    source_policy: dict[str, Any] = {}
    if opts.get("sites"):
        source_policy["include_domains"] = opts["sites"]
    elif opts.get("block_hosts"):
        # 官方语义：include_domains 非空时 exclude_domains 会被忽略
        source_policy["exclude_domains"] = opts["block_hosts"]
    if opts.get("after_date"):
        source_policy["after_date"] = str(opts["after_date"])
    if source_policy:
        advanced["source_policy"] = source_policy
    payload["advanced_settings"] = advanced
    return payload


def _parallel_cache_fingerprint(objective: str, queries: list[str], opts: dict, conf: dict) -> dict:
    """构造与 transport 细节（临时 -o 路径、每次都变的 session_id）无关的缓存指纹。

    指纹相同就必须共用缓存，所以命名空间也必须与 transport 无关（都叫 parallel）——
    否则装一下 parallel-cli、或把 transport 从 auto 改成 http，整个缓存就作废重付一遍。
    前提是两条通路真的发同样的请求，这由 resolve_search_queries 保证。

    session_id 只是串联上下文用的关联 ID，不影响返回内容；把它纳入缓存键
    会导致相同的搜索参数每次都算作不同请求，30 分钟缓存实际永远不命中。

    反过来，凡是会进入 wire request 的字段都必须**原样保序**纳入指纹：
    关键词顺序会影响 Parallel 的检索结果，排序后不同的请求会错误地共用同一份缓存。
    """
    return {
        "objective": objective,
        # 记录最终发出去的那份，而不是原始入参：两条通路都经过 resolve_search_queries
        "queries": resolve_search_queries(objective, queries),
        "mode": str(opts.get("mode") or conf["mode"]),
        "max_results": int(opts.get("count") or conf["max_results"]),
        "excerpt_max_chars_total": int(conf["excerpt_max_chars_total"]),
        # 与实际请求一致：include 非空时 exclude 被上游忽略，
        # 把它纳入指纹只会制造发出去其实一模一样的两个请求各占一份缓存
        "sites": list(opts.get("sites") or []),
        "block_hosts": [] if opts.get("sites") else list(opts.get("block_hosts") or []),
        "after_date": opts.get("after_date"),
        "client_model": conf.get("client_model"),
    }


def _post_parallel(path: str, payload: dict, api_key: str, timeout: int) -> dict:
    request = urllib.request.Request(
        f"https://api.parallel.ai{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _map_parallel(body: dict) -> list[Doc]:
    docs: list[Doc] = []
    for index, item in enumerate(body.get("results") or []):
        docs.append(
            Doc(
                url=item.get("url") or "",
                title=item.get("title") or "",
                body=clean_text("\n".join(item.get("excerpts") or [])),
                site="",  # Parallel 不返回站点名，交给 fusion 从 URL 推导
                source="parallel",
                rank=index,
                publish=item.get("publish_date") or None,
            )
        )
    return docs


_WARNING_KEYS = ("warnings", "spec_validation_warnings", "input_validation_warnings")


def parallel_warnings(body: Any) -> list[str]:
    """从 Parallel 响应里捞出"成功但有保留"的告警。

    上游的告警形态不止一种（顶层 warnings、嵌在 meta 里、字符串或 {type,message} 对象），
    所以这里按结构宽松地取，取不到就当没有——告警本身不该成为新的故障点。
    """
    out: list[str] = []
    if not isinstance(body, dict):
        return out
    buckets: list[Any] = [body.get(k) for k in _WARNING_KEYS]
    meta = body.get("meta")
    if isinstance(meta, dict):
        buckets += [meta.get(k) for k in _WARNING_KEYS]
    for bucket in buckets:
        if not isinstance(bucket, list):
            continue
        for entry in bucket:
            if isinstance(entry, str):
                out.append(entry)
            elif isinstance(entry, dict):
                kind = entry.get("type") or entry.get("code") or "warning"
                message = entry.get("message") or entry.get("detail") or ""
                out.append(f"{kind}: {message}".strip(": "))
    return out


def _parallel_search_http(cfg: dict, objective: str, queries: list[str], opts: dict) -> SourceResult:
    """不依赖 parallel-cli 的直连通路，只需要一个 API Key。"""
    payload = build_parallel_http_payload(cfg, objective, queries, opts)
    request_info = {"url": "https://api.parallel.ai/v1/search", "payload": payload}
    api_key, _ = cfgmod.parallel_key(cfg)

    key = cfgmod.cache_key(
        PARALLEL_CACHE_NS, _parallel_cache_fingerprint(objective, queries, opts, cfg["parallel"])
    )
    if not opts.get("no_cache"):
        hit = cfgmod.cache_get(cfg, key, ttl=opts.get("cache_ttl"))
        if hit is not None:
            return SourceResult("parallel", _map_parallel(hit), cached=True, raw=hit,
                                request=request_info, warnings=parallel_warnings(hit))

    started = time.monotonic()
    try:
        body = _post_parallel("/v1/search", payload, api_key, PARALLEL_TIMEOUT)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        hint = "（402/403 通常是余额不足，可运行 parallel-cli balance get）" if exc.code in (402, 403) else ""
        return SourceResult("parallel", error=f"HTTP {exc.code} {detail}{hint}",
                            elapsed=time.monotonic() - started, request=request_info)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return SourceResult("parallel", error=f"{type(exc).__name__}: {exc}",
                            elapsed=time.monotonic() - started, request=request_info)

    if not opts.get("no_cache"):
        cfgmod.cache_put(cfg, key, body)
    return SourceResult("parallel", _map_parallel(body), elapsed=time.monotonic() - started,
                        raw=body, request=request_info, warnings=parallel_warnings(body))


def parallel_search(cfg: dict, objective: str, queries: list[str], opts: dict, dry_run: bool = False) -> SourceResult:
    """优先走 parallel-cli；没装 CLI 但有密钥时走 HTTP 直连。"""
    transport = resolve_transport(cfg)

    if dry_run:
        if transport == "http":
            return SourceResult(
                source="parallel",
                request={"url": "https://api.parallel.ai/v1/search",
                         "payload": build_parallel_http_payload(cfg, objective, queries, opts)},
            )
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            probe = tmp.name
        cmd = build_parallel_cmd(cfg, objective, queries, opts, probe)
        os.unlink(probe)
        return SourceResult(source="parallel", request={"cmd": cmd})

    if transport is None:
        reason = (
            "已在配置中禁用"
            if not cfg["parallel"].get("enabled", True)
            else '无可用通路：未找到 parallel-cli（uv tool install "parallel-web-tools[cli]"），'
                 "也没有配置 API Key（config set-key parallel）"
        )
        return SourceResult(source="parallel", error=reason)
    if transport == "http":
        return _parallel_search_http(cfg, objective, queries, opts)

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        out_path = tmp.name
    cmd = build_parallel_cmd(cfg, objective, queries, opts, out_path)

    key = cfgmod.cache_key(
        PARALLEL_CACHE_NS, _parallel_cache_fingerprint(objective, queries, opts, cfg["parallel"])
    )
    if not opts.get("no_cache"):
        hit = cfgmod.cache_get(cfg, key, ttl=opts.get("cache_ttl"))
        if hit is not None:
            os.unlink(out_path)
            return SourceResult("parallel", _map_parallel(hit), cached=True, raw=hit,
                                request={"cmd": cmd}, warnings=parallel_warnings(hit))

    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=PARALLEL_TIMEOUT, env=parallel_env(cfg)
        )
        elapsed = time.monotonic() - started
        if proc.returncode != 0:
            detail = redact((proc.stderr or proc.stdout or "").strip(), cfg)[:300]
            hint = "（403 通常是余额不足，可运行 parallel-cli balance get）" if "403" in detail else ""
            return SourceResult(
                "parallel", error=f"退出码 {proc.returncode}: {detail}{hint}",
                elapsed=elapsed, request={"cmd": cmd},
            )
        with open(out_path, encoding="utf-8") as fh:
            body = json.load(fh)
    except subprocess.TimeoutExpired:
        return SourceResult(
            "parallel", error=f"超时（{PARALLEL_TIMEOUT}s）",
            elapsed=time.monotonic() - started, request={"cmd": cmd},
        )
    except (OSError, json.JSONDecodeError) as exc:
        return SourceResult(
            "parallel", error=f"{type(exc).__name__}: {exc}",
            elapsed=time.monotonic() - started, request={"cmd": cmd},
        )
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass

    if not opts.get("no_cache"):
        cfgmod.cache_put(cfg, key, body)
    # CLI 与 HTTP 打的是同一个接口，告警也必须同样传出去
    return SourceResult("parallel", _map_parallel(body), elapsed=elapsed, raw=body,
                        request={"cmd": cmd}, warnings=parallel_warnings(body))


def _extract_pages(body: dict) -> list[dict]:
    pages = []
    for item in body.get("results") or []:
        content = item.get("full_content") or "\n".join(item.get("excerpts") or [])
        pages.append(
            {
                "url": item.get("url") or "",
                "title": item.get("title") or "",
                "publish": item.get("publish_date"),
                "content": clean_text(content),
            }
        )
    return pages


def _parallel_extract_http(
    cfg: dict, urls: list[str], objective: str | None, max_chars: int, session_id: str | None = None
) -> tuple[list[dict], str | None, list[str]]:
    """POST /v1/extract。契约来自官方 OpenAPI 的 V1ExtractRequest。"""
    warnings: list[str] = []
    targets = urls[:20]  # 官方上限 20 个 URL
    if len(urls) > 20:
        warnings.append(f"仅抓取前 20 个 URL（Extract 单次上限 20），已丢弃 {len(urls) - 20} 个")
    payload: dict[str, Any] = {"urls": targets}
    if objective:
        # 给了目标就取相关性摘录：整页正文是从页首截断的，
        # 导航条厚的站点（如火山引擎文档）几千字符都还没到正文。
        payload["objective"] = objective
        payload["max_chars_total"] = max_chars
    else:
        # max_chars 统一表示"整次调用的输出预算"。这里的字段是 per_result，
        # 所以要按 URL 数均分——否则多 URL 时会请求远超预算的内容再被丢掉。
        payload["advanced_settings"] = {
            "full_content": {"max_chars_per_result": max(max_chars // max(len(targets), 1), 500)}
        }
    if cfg["parallel"].get("client_model"):
        payload["client_model"] = str(cfg["parallel"]["client_model"])
    if session_id:
        payload["session_id"] = session_id

    api_key, _ = cfgmod.parallel_key(cfg)
    try:
        body = _post_parallel("/v1/extract", payload, api_key, EXTRACT_TIMEOUT)
    except urllib.error.HTTPError as exc:
        return [], f"HTTP {exc.code} {exc.read().decode('utf-8', 'replace')[:300]}", warnings
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return [], f"{type(exc).__name__}: {exc}", warnings

    pages = _extract_pages(body)
    # Search 那边补了顶层 warnings，Extract 这边一度还漏着：字段降级、
    # 提取不完整都会被当成"完全成功"。两条路径的语义必须一致。
    warnings += parallel_warnings(body)
    # /v1/extract 会把抓取失败的 URL 单独放在 errors 里，别当成"没有结果"
    failures = [f"{e.get('url')}: {e.get('error_type')}" for e in (body.get("errors") or [])]
    if not pages and failures:
        return [], "; ".join(failures[:3]), warnings
    if failures:
        tail = " 等" if len(failures) > 3 else ""
        warnings.append(f"{len(failures)} 个 URL 抓取失败: " + "; ".join(failures[:3]) + tail)
    return pages, None, warnings


def parallel_extract(
    cfg: dict, urls: list[str], objective: str | None, max_chars: int, session_id: str | None = None
) -> tuple[list[dict], str | None, list[str]]:
    """抓取整页正文。存在的理由：普通 HTTP 抓取对 SPA 文档站（如火山引擎文档）拿到的是空壳。"""
    transport = resolve_transport(cfg)
    if transport is None:
        return [], ('无可用通路：未找到 parallel-cli（uv tool install "parallel-web-tools[cli]"），'
                    "也没有配置 API Key（config set-key parallel）"), []
    if transport == "http":
        return _parallel_extract_http(cfg, urls, objective, max_chars, session_id=session_id)

    # CLI 与 HTTP 打的是同一个 /v1/extract，20 个 URL 的上限和 session 语义都一样，
    # 两条通路必须表现一致——auto 模式下装了 parallel-cli 走的正是这条。
    warnings: list[str] = []
    targets = urls[:20]
    if len(urls) > 20:
        warnings.append(f"仅抓取前 20 个 URL（Extract 单次上限 20），已丢弃 {len(urls) - 20} 个")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        out_path = tmp.name
    cmd = ["parallel-cli", "extract", "--json", "-o", out_path]
    if objective:
        # 有目标就取相关性摘录，而不是从页首截断的整页正文
        cmd += ["--objective", objective, "--excerpt-max-chars-total", str(max_chars)]
    else:
        # per-result 预算按 URL 数均分，让 max_chars 始终表示整次调用的输出预算
        per_result = max(max_chars // max(len(targets), 1), 500)
        # 不加 --no-excerpts：CLI 会在写输出文件时把 excerpts 删掉，
        # 而上游 full_content 可能是 null——那时 HTTP 通路能回退到 excerpt，
        # CLI 通路却只剩空正文还报成功。_extract_pages 的兜底得留着东西可兜。
        cmd += ["--full-content", "--full-content-max-chars", str(per_result)]
    if session_id:
        cmd += ["--session-id", session_id]
    # HTTP 通路一直在发 client_model，CLI 这边漏了——`parallel-cli extract --help`
    # 明确支持 --client-model，两条路径必须发同样的请求
    if cfg["parallel"].get("client_model"):
        cmd += ["--client-model", str(cfg["parallel"]["client_model"])]
    # URL 放最后并用 `--` 终止选项解析，和 build_parallel_cmd 里的 objective 同一处理。
    # URL 多半来自上一次 search 落盘 JSON 的 docs[].url，是上游可控字段，以 `-` 开头时
    # 会被 click 当成选项：`--help` 让 CLI 打印帮助后正常退出、却不写结果文件
    # （我们随后崩在 JSONDecodeError 上），`--json` 这类干脆被吞成 flag、那个 URL
    # 静默从请求里消失而我们照常报成功。HTTP 通路把 URL 放在 JSON body 里没这问题，
    # 不修的话 auto 模式下行为取决于本机装没装 parallel-cli。
    cmd += ["--", *targets]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=EXTRACT_TIMEOUT, env=parallel_env(cfg)
        )
        if proc.returncode != 0:
            detail = redact((proc.stderr or proc.stdout or "").strip(), cfg)[:300]
            return [], f"退出码 {proc.returncode}: {detail}", warnings
        with open(out_path, encoding="utf-8") as fh:
            body = json.load(fh)
    except subprocess.TimeoutExpired:
        return [], f"抓取超时（{EXTRACT_TIMEOUT}s）", warnings
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"{type(exc).__name__}: {exc}", warnings
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass

    pages = _extract_pages(body)
    # 与 HTTP 通路共享同一份响应契约（见 references/parallel-api.md）：
    # 顶层 warnings 和 errors[] 的处理都必须一致，errors[] 同样不能当成"没有结果"
    warnings += parallel_warnings(body)
    failures = [f"{e.get('url')}: {e.get('error_type')}" for e in (body.get("errors") or [])]
    if not pages and failures:
        return [], "; ".join(failures[:3]), warnings
    if failures:
        tail = " 等" if len(failures) > 3 else ""
        warnings.append(f"{len(failures)} 个 URL 抓取失败: " + "; ".join(failures[:3]) + tail)
    return pages, None, warnings
