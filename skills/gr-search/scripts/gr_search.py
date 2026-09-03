#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gr-search：豆包搜索 + Parallel 双路融合检索。

用法:
    python3 gr_search.py search "查询词" [选项]
    python3 gr_search.py fetch <url> [<url> ...] [--max-chars N]
    python3 gr_search.py config set-key doubao|parallel | show | path | doctor

设计要点:
- 豆包为主、Parallel 为补充，结果去重融合后按 token 预算压缩输出
- 全量结果落盘 JSON，agent 追问时直接读文件，不必重新搜索
- 任一源失败不影响另一源，输出里显式标注失败原因
- --dry-run 打印请求体但不发请求，用于核对豆包的 PascalCase 字段名
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import config as cfgmod
import fusion
import render
import sources

_SLUG = re.compile(r"[^\w一-鿿-]+")


# ---------------------------------------------------------------- 工具


def slugify(text: str, limit: int = 40) -> str:
    return _SLUG.sub("-", text.strip()).strip("-")[:limit] or "query"


# ---------------------------------------------------------------- search


def run_search(args: argparse.Namespace, cfg: dict) -> int:
    query = args.query.strip()
    if not query:
        print("查询词不能为空", file=sys.stderr)
        return 2

    doubao_query = (args.q or query)[:100]
    objective = args.objective or query
    keywords = args.pq or []
    image_mode = args.type == "image"

    # 秒级时间戳会在同一秒内的并发/连续调用间碰撞（session 混用、落盘互相覆盖），
    # 加个随机后缀保证同一进程内每次调用都是唯一的。
    run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"

    opts = {
        "count": args.count,
        "search_type": "image" if image_mode else "web",
        "time_range": args.time_range,
        "sites": [s.strip() for s in (args.sites or "").split(",") if s.strip()],
        "block_hosts": [s.strip() for s in (args.block_hosts or "").split(",") if s.strip()],
        "industry": args.industry,
        "authoritative": args.authoritative,
        "need_content": args.need_content,
        "need_url": args.need_url,
        "no_cache": args.no_cache,
        "session_id": f"gr-search-{run_id}",
        "after_date": args.after_date,
        "mode": args.mode,
    }

    use_doubao = args.source in ("both", "doubao")
    use_parallel = args.source in ("both", "parallel") and not image_mode

    # ---------------- dry-run：只打印请求体，不发请求、不花额度
    if args.dry_run:
        print(f'gr-search --dry-run | query="{query}"')
        if use_doubao:
            result = sources.doubao_search(cfg, doubao_query, opts, dry_run=True)
            print(f"\n--- doubao ---\n{result.request['url']}")
            print(json.dumps(result.request["payload"], ensure_ascii=False, indent=2))
        if use_parallel:
            result = sources.parallel_search(cfg, objective, keywords, opts, dry_run=True)
            print("\n--- parallel ---")
            if "cmd" in result.request:
                print(" ".join(repr(c) if " " in c else c for c in result.request["cmd"]))
            else:
                print(result.request["url"])
                print(json.dumps(result.request["payload"], ensure_ascii=False, indent=2))
        return 0

    started = time.monotonic()
    results: list[sources.SourceResult] = []

    # 两个源都必须兜住意外异常再返回 SourceResult，而不是向上抛——
    # 否则卡片短路分支（下面直接同步调用，不经过线程池）会被单个源的崩溃拖垮整个命令，
    # 违背"任一源失败不影响另一源"的设计承诺。
    def call_doubao() -> sources.SourceResult:
        try:
            return sources.doubao_search(cfg, doubao_query, opts)
        except Exception as exc:
            return sources.SourceResult("doubao", error=f"{type(exc).__name__}: {exc}")

    def call_parallel() -> sources.SourceResult:
        try:
            return sources.parallel_search(cfg, objective, keywords, opts)
        except Exception as exc:
            return sources.SourceResult("parallel", error=f"{type(exc).__name__}: {exc}")

    # 卡片短路：如意卡片本身就是权威直答，命中时没必要再花钱调 Parallel。
    # 代价是先跑豆包再决定，非命中场景会多等豆包那一跳（约 0.7s）。
    shortcircuit = (
        cfg.get("card_shortcircuit", True)
        and not args.force_all
        and use_doubao
        and use_parallel
    )

    if shortcircuit:
        first = call_doubao()
        results.append(first)
        if not first.cards:
            results.append(call_parallel())
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = []
            if use_doubao:
                futures.append(pool.submit(call_doubao))
            if use_parallel:
                futures.append(pool.submit(call_parallel))
            for future in futures:
                results.append(future.result())

    # ---------------- 汇总
    docs, cards, stats, errors = [], [], [], []
    for result in results:
        if result.error:
            errors.append(f"{result.source} 失败: {result.error}")
            continue
        docs.extend(result.docs)
        cards.extend(result.cards)
        stats.append(f"{result.source} {len(result.docs)}{'(缓存)' if result.cached else ''}")

    merged = fusion.merge(docs, threshold=float(cfg["fusion"]["dedup_jaccard"]))
    strong_fresh = fusion.is_strong_fresh_query(query)
    fresh = args.fresh or strong_fresh or fusion.is_fresh_query(query)
    ranked = fusion.rank(merged, cfg, fresh=fresh, strong_fresh=strong_fresh)
    elapsed = time.monotonic() - started

    budget, profile = cfgmod.resolve_budget(cfg, args.profile, args.budget)

    # ---------------- 全量落盘：压缩输出之外的信息不丢，追问时直接读文件
    dump_path = None
    if not args.no_dump:
        payload = {
            "query": query,
            "doubao_query": doubao_query,
            "objective": objective,
            "keywords": keywords,
            # Parallel 官方最佳实践：同一任务的 search→extract 应复用 session_id 串联上下文，
            # 落盘这个值供后续 fetch 调用手动传 --session-id 复用。
            "session_id": opts["session_id"],
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "stats": stats,
            "errors": errors,
            "cards": cards,
            "docs": [asdict(d) for d in ranked],
            "raw": {r.source: r.raw for r in results if r.raw is not None},
        }
        try:
            directory = cfgmod.dump_dir(cfg)
            target = directory / f"{cfgmod.FILE_PREFIX}{slugify(query)}-{run_id}.json"
            cfgmod.secure_write(target, json.dumps(payload, ensure_ascii=False, indent=2))
            dump_path = str(target)
            cfgmod.prune_dir(directory, int(cfg["output"].get("keep_runs", 200)))
        except OSError as exc:
            errors.append(f"结果落盘失败: {exc}")

    if args.json:
        print(json.dumps(
            {
                "query": query, "elapsed": round(elapsed, 2),
                "stats": stats, "errors": errors, "cards": cards,
                "dump": dump_path,
                "docs": [asdict(d) for d in ranked],
            },
            ensure_ascii=False, indent=2,
        ))
        return 0 if (ranked or cards) else 1

    print(render.render(
        query=query, items=ranked, cards=cards, budget=budget, profile=profile,
        stats=stats, errors=errors, elapsed=elapsed, dump_path=dump_path,
        image_mode=image_mode,
    ))
    return 0 if (ranked or cards) else 1


# ---------------------------------------------------------------- fetch


def run_fetch(args: argparse.Namespace, cfg: dict) -> int:
    pages, error, warnings = sources.parallel_extract(
        cfg, args.urls, args.objective, args.max_chars, session_id=args.session_id
    )
    if error:
        print(f"⚠ 抓取失败: {error}", file=sys.stderr)
        return 1
    if not pages:
        print("⚠ 没有抓到任何内容", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"⚠ {warning}", file=sys.stderr)

    per_page = max(args.max_chars // max(len(pages), 1), 500)
    blocks = [render.BOUNDARY_OPEN, ""]
    for index, page in enumerate(pages, start=1):
        header = f"[{index}] {page['title'] or '(无标题)'}"
        if page.get("publish"):
            header += f" · {page['publish'][:10]}"
        blocks += [header, page["url"], "", render.truncate(page["content"], per_page), ""]
    blocks.append(render.BOUNDARY_CLOSE)
    print("\n".join(blocks))
    return 0


# ---------------------------------------------------------------- config


def run_config(args: argparse.Namespace, cfg: dict) -> int:
    if args.op == "path":
        print(cfgmod.CONFIG_PATH)
        return 0

    if args.op == "set-key":
        if not args.target:
            print("请指定目标：config set-key doubao 或 config set-key parallel", file=sys.stderr)
            return 2
        return cfgmod.prompt_and_store_key(args.target)

    if args.op == "show":
        doubao_secret, doubao_origin = cfgmod.doubao_key(cfg)
        parallel_secret, parallel_origin = cfgmod.parallel_key(cfg)
        if args.raw_parallel_key:
            # 仅供自检 Parallel 环境变量名是否正确，避免密钥流入日志或管道
            if not sys.stdout.isatty():
                print("--raw-parallel-key 只能在交互式终端中使用", file=sys.stderr)
                return 2
            print(parallel_secret)
            return 0
        redacted = json.loads(json.dumps(cfg))
        redacted["doubao"]["api_key"] = cfgmod.mask(str(cfg["doubao"].get("api_key") or ""))
        redacted["parallel"]["api_key"] = cfgmod.mask(str(cfg["parallel"].get("api_key") or ""))
        print(f"配置文件: {cfgmod.CONFIG_PATH}")
        print(f"豆包密钥: {cfgmod.mask(doubao_secret)}（来源 {doubao_origin}）")
        print(f"Parallel 密钥: {cfgmod.mask(parallel_secret)}（来源 {parallel_origin}）")
        print(json.dumps(redacted, ensure_ascii=False, indent=2))
        return 0

    # doctor：换机器后的第一步，逐项确认两个源真的可用
    print(f"配置文件: {cfgmod.CONFIG_PATH}（存在: {cfgmod.CONFIG_PATH.exists()}）")
    if cfgmod.CONFIG_PATH.exists():
        mode = cfgmod.CONFIG_PATH.stat().st_mode & 0o777
        flag = "✓" if mode == 0o600 else "⚠ 建议 chmod 600"
        print(f"  权限: {oct(mode)} {flag}")

    doubao_secret, doubao_origin = cfgmod.doubao_key(cfg)
    print(f"\n[豆包] 密钥: {cfgmod.mask(doubao_secret)}（来源 {doubao_origin}）")
    if not doubao_secret:
        print(f"  未配置。请你本人在终端运行：python3 {Path(__file__).resolve()} config set-key doubao")
        print(f"  或设置环境变量 {cfgmod.DOUBAO_ENV}")
    print(f"  接口: {cfgmod.DOUBAO_URL}（Custom 版）")

    parallel_secret, parallel_origin = cfgmod.parallel_key(cfg)
    env_name = cfg["parallel"].get("api_key_env") or cfgmod.PARALLEL_ENV_DEFAULT
    print(f"\n[Parallel] 密钥: {cfgmod.mask(parallel_secret)}（来源 {parallel_origin}，环境变量名 {env_name}）")
    binary = shutil.which("parallel-cli")
    print(f"  parallel-cli: {binary or '未安装'}")
    if not binary:
        print('  安装: uv tool install "parallel-web-tools[cli]"')
        return 0
    try:
        proc = subprocess.run(
            ["parallel-cli", "auth", "--json"], capture_output=True, text=True,
            timeout=20, env=sources.parallel_env(cfg),
        )
        auth = json.loads(proc.stdout or "{}")
        print(f"  已鉴权: {auth.get('authenticated')} | 方式: {auth.get('method')}")
        print(f"  env_var_set: {auth.get('env_var_set')} | stored_overridden_by_env: {auth.get('stored_overridden_by_env')}")
        if parallel_secret and not auth.get("env_var_set"):
            print(f"  ⚠ 配了密钥但 parallel-cli 没读到，说明它读的环境变量名不是 {env_name}。")
            print("    请查 parallel-cli 文档确定真名，改配置项 parallel.api_key_env，不要猜。")
        if not auth.get("authenticated"):
            print("  未鉴权：运行 /parallel-cli-setup 走 OAuth，或用 config set-key parallel 配密钥")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        print(f"  ⚠ 无法读取鉴权状态: {exc}")
    return 0


# ---------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gr_search.py", description="豆包 + Parallel 双路融合搜索")
    sub = parser.add_subparsers(dest="cmd", required=True)

    search = sub.add_parser("search", help="搜索")
    search.add_argument("query")
    search.add_argument("--q", help="豆包用的单个短语（≤100 字符，豆包不支持多词搜索）")
    search.add_argument("--objective", help="Parallel 用的自然语言目标")
    search.add_argument("--pq", action="append", help="Parallel 关键词，可重复")
    search.add_argument("--source", default="both", choices=["both", "doubao", "parallel"])
    search.add_argument("--type", default="web", choices=["web", "image"])
    search.add_argument("--profile", choices=["compact", "standard", "full"])
    search.add_argument("--budget", type=int, help="输出字符预算，优先于 --profile")
    search.add_argument("--count", type=int)
    search.add_argument("--fresh", action="store_true", help="给新内容加权、压低陈旧内容")
    search.add_argument("--time-range", help="OneDay|OneWeek|OneMonth|OneYear|YYYY-MM-DD..YYYY-MM-DD")
    search.add_argument("--after-date", help="Parallel 的日期下限 YYYY-MM-DD")
    search.add_argument("--sites", help="限定站点，逗号分隔")
    search.add_argument("--block-hosts", help="屏蔽站点，逗号分隔")
    search.add_argument("--industry", choices=["finance", "game", "health", "gov"])
    search.add_argument("--authoritative", action="store_true", help="仅非常权威来源（会过滤掉如意结果）")
    search.add_argument("--need-content", action="store_true", help="仅返回有正文的结果")
    search.add_argument("--need-url", action="store_true",
                        help="仅返回有原文链接的结果（注意：会过滤掉如意卡片）")
    search.add_argument("--mode", choices=["turbo", "fast", "basic", "advanced"], help="Parallel 检索档位")
    search.add_argument("--no-cache", action="store_true")
    search.add_argument("--no-dump", action="store_true")
    search.add_argument("--force-all", action="store_true", help="关闭卡片短路，强制两个源都调")
    search.add_argument("--dry-run", action="store_true")
    search.add_argument("--json", action="store_true")

    fetch = sub.add_parser("fetch", help="抓取网页正文（对 SPA 文档站有效）")
    fetch.add_argument("urls", nargs="+")
    fetch.add_argument("--objective")
    fetch.add_argument("--max-chars", type=int, default=12000)
    fetch.add_argument("--session-id", help="复用某次 search 落盘 JSON 里的 session_id 以串联上下文")

    conf = sub.add_parser("config", help="配置与诊断")
    conf.add_argument("op", choices=["set-key", "show", "path", "doctor"])
    conf.add_argument("target", nargs="?", choices=["doubao", "parallel"])
    conf.add_argument("--raw-parallel-key", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = cfgmod.load_config()
    if args.cmd == "search":
        return run_search(args, cfg)
    if args.cmd == "fetch":
        return run_fetch(args, cfg)
    return run_config(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
