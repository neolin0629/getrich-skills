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
from typing import Any

import config as cfgmod

DOUBAO_TIMEOUT = 20
PARALLEL_TIMEOUT = 40
EXTRACT_TIMEOUT = 60

AUTHORITY_LABEL = {1: "非常权威", 2: "正常权威", 3: "一般权威", 4: "一般不权威"}

_TIME_RANGE_ENUM = {"OneDay", "OneWeek", "OneMonth", "OneYear"}
_TIME_RANGE_SPAN = re.compile(r"^\d{4}-\d{2}-\d{2}\.\.\d{4}-\d{2}-\d{2}$")


def _valid_time_range(value: str) -> bool:
    """校验 --time-range 是否符合官方枚举/日期区间格式，见 references/doubao-api.md。"""
    return value in _TIME_RANGE_ENUM or bool(_TIME_RANGE_SPAN.match(value))

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
        if len(stripped) > 2:
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
    time_range = opts.get("time_range")
    if time_range and not _valid_time_range(time_range):
        return SourceResult(
            source=name,
            error=f"--time-range 格式不对：{time_range}（应为 OneDay/OneWeek/OneMonth/OneYear 或 YYYY-MM-DD..YYYY-MM-DD）",
        )
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
        hit = cfgmod.cache_get(cfg, key)
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
    """
    env = dict(os.environ)
    secret, origin = cfgmod.parallel_key(cfg)
    if secret and origin != "env":
        env[cfg["parallel"].get("api_key_env") or cfgmod.PARALLEL_ENV_DEFAULT] = secret
    return env


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
    cmd = ["parallel-cli", "search", objective]
    for keyword in (queries or [])[:5]:
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
    if opts.get("sites"):
        cmd += ["--include-domains", ",".join(opts["sites"])]
    if opts.get("block_hosts"):
        cmd += ["--exclude-domains", ",".join(opts["block_hosts"])]
    return cmd


def build_parallel_http_payload(cfg: dict, objective: str, queries: list[str], opts: dict) -> dict:
    """构造 POST /v1/search 的请求体。

    契约来自官方 OpenAPI（V1SearchRequest）：search_queries 必填，
    max_results 在 advanced_settings 里而不是顶层。该 schema 是
    additionalProperties: false，字段名写错会返回 422 而不是被静默忽略。
    """
    conf = cfg["parallel"]
    # search_queries 是必填项；没给 --pq 时用 objective 兜一个，
    # 官方建议每条 3~6 个词、给 2~3 条效果最好
    search_queries = [q for q in (queries or []) if q.strip()] or [objective.strip()[:120]]
    payload: dict[str, Any] = {
        "search_queries": search_queries[:5],
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

    session_id 只是串联上下文用的关联 ID，不影响返回内容；把它纳入缓存键
    会导致相同的搜索参数每次都算作不同请求，30 分钟缓存实际永远不命中。
    """
    return {
        "objective": objective,
        "queries": sorted(q.strip() for q in (queries or []) if q.strip()),
        "mode": str(opts.get("mode") or conf["mode"]),
        "max_results": int(opts.get("count") or conf["max_results"]),
        "excerpt_max_chars_total": int(conf["excerpt_max_chars_total"]),
        "sites": sorted(opts.get("sites") or []),
        "block_hosts": sorted(opts.get("block_hosts") or []),
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


def _parallel_search_http(cfg: dict, objective: str, queries: list[str], opts: dict) -> SourceResult:
    """不依赖 parallel-cli 的直连通路，只需要一个 API Key。"""
    payload = build_parallel_http_payload(cfg, objective, queries, opts)
    request_info = {"url": "https://api.parallel.ai/v1/search", "payload": payload}
    api_key, _ = cfgmod.parallel_key(cfg)

    key = cfgmod.cache_key(
        "parallel-http", _parallel_cache_fingerprint(objective, queries, opts, cfg["parallel"])
    )
    if not opts.get("no_cache"):
        hit = cfgmod.cache_get(cfg, key)
        if hit is not None:
            return SourceResult("parallel", _map_parallel(hit), cached=True, raw=hit, request=request_info)

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
                        raw=body, request=request_info)


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
        "parallel-cli", _parallel_cache_fingerprint(objective, queries, opts, cfg["parallel"])
    )
    if not opts.get("no_cache"):
        hit = cfgmod.cache_get(cfg, key)
        if hit is not None:
            os.unlink(out_path)
            return SourceResult("parallel", _map_parallel(hit), cached=True, raw=hit, request={"cmd": cmd})

    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=PARALLEL_TIMEOUT, env=parallel_env(cfg)
        )
        elapsed = time.monotonic() - started
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[:300]
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
    return SourceResult("parallel", _map_parallel(body), elapsed=elapsed, raw=body, request={"cmd": cmd})


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

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        out_path = tmp.name
    cmd = ["parallel-cli", "extract", *urls, "--json", "-o", out_path]
    if objective:
        # 有目标就取相关性摘录，而不是从页首截断的整页正文
        cmd += ["--objective", objective, "--excerpt-max-chars-total", str(max_chars)]
    else:
        # per-result 预算按 URL 数均分，让 max_chars 始终表示整次调用的输出预算
        per_result = max(max_chars // max(len(urls), 1), 500)
        cmd += ["--full-content", "--full-content-max-chars", str(per_result), "--no-excerpts"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=EXTRACT_TIMEOUT, env=parallel_env(cfg)
        )
        if proc.returncode != 0:
            return [], f"退出码 {proc.returncode}: {(proc.stderr or proc.stdout or '').strip()[:300]}", []
        with open(out_path, encoding="utf-8") as fh:
            body = json.load(fh)
    except subprocess.TimeoutExpired:
        return [], f"抓取超时（{EXTRACT_TIMEOUT}s）", []
    except (OSError, json.JSONDecodeError) as exc:
        return [], f"{type(exc).__name__}: {exc}", []
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass

    pages = _extract_pages(body)
    # 与 HTTP 通路共享同一份响应契约（见 references/parallel-api.md），errors[] 同样不能当成"没有结果"
    failures = [f"{e.get('url')}: {e.get('error_type')}" for e in (body.get("errors") or [])]
    if not pages and failures:
        return [], "; ".join(failures[:3]), []
    warnings = []
    if failures:
        tail = " 等" if len(failures) > 3 else ""
        warnings.append(f"{len(failures)} 个 URL 抓取失败: " + "; ".join(failures[:3]) + tail)
    return pages, None, warnings
