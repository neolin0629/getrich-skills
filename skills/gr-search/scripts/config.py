#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gr-search 的配置、密钥与磁盘缓存。

配置文件位于 ~/.config/gr-search/config.json，权限 0600。
读取优先级：CLI 参数 > 环境变量 > 配置文件 > 内置默认。

密钥永远不进 argv、不进 shell 历史、不进进程列表：
- 交互写入走 getpass
- 传给 parallel-cli 时走子进程环境变量
"""

from __future__ import annotations

import copy
import getpass
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- 路径

CONFIG_DIR = Path.home() / ".config" / "gr-search"
CONFIG_PATH = CONFIG_DIR / "config.json"
CACHE_ROOT = Path.home() / ".cache" / "gr-search"

# 豆包 Custom 版接口地址（PascalCase 请求体，见 references/doubao-api.md）。
# 只用 Custom 不用 Global：Global 仅支持按量后付费、吃不到订阅套餐额度，
# 而它相对 Custom 的独占能力（全球站点覆盖、长摘要）由 Parallel 覆盖得更好。
DOUBAO_URL = "https://open.feedcoopapi.com/search_api/web_search"

DOUBAO_ENV = "DOUBAO_SEARCH_API_KEY"
# 官方 SDK 用的就是这个名字：new Parallel({ apiKey: process.env.PARALLEL_API_KEY })。
# 若上游改名，改这里即可，`config doctor` 会通过 `parallel-cli auth --json`
# 的 env_var_set 字段实测校验密钥是否真的被读到。
PARALLEL_ENV_DEFAULT = "PARALLEL_API_KEY"

DEFAULTS: dict[str, Any] = {
    "doubao": {
        "api_key": "",
        "count": 10,
        "content_formats": "markdown",
        "query_rewrite": False,
        # 必须保持 false：官方文档明确 NeedUrl=true 会滤掉如意结果，
        # 打开它等于永久关闭火山如意卡片（连带卡片短路也失效）。
        # 需要"每条结果都可引用"时用 --need-url 单次开启。
        "need_url": False,
        "need_content": False,
        "auth_info_level": 0,
    },
    "parallel": {
        "enabled": True,
        "api_key": "",
        "api_key_env": PARALLEL_ENV_DEFAULT,
        "transport": "auto",  # auto | cli | http
        "mode": "basic",
        "max_results": 10,
        "excerpt_max_chars_total": 24000,
        "client_model": "claude-opus-5",
    },
    "fusion": {
        "weight_doubao": 1.0,
        "weight_parallel": 0.7,
        "rrf_k": 60,
        "dedup_jaccard": 0.75,
    },
    "output": {
        "profile": "standard",
        "budget_chars": None,
        "dump_dir": str(CACHE_ROOT / "runs"),
        "keep_runs": 200,  # 保留最近多少份全量结果，0 表示不清理
    },
    "cache": {
        "enabled": True,
        "ttl_seconds": 1800,
        "dir": str(CACHE_ROOT / "http"),
        "keep_entries": 500,
    },
    "card_shortcircuit": True,
}

PROFILE_BUDGETS = {"compact": 8000, "standard": 15000, "full": 30000}


# ---------------------------------------------------------------- 配置读写


def _deep_merge(base: dict, override: dict) -> dict:
    """把 override 递归叠加到 base 上，返回新字典。"""
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict[str, Any]:
    """读取配置，缺失项用内置默认补齐。配置文件损坏时退回默认并告警。"""
    if not CONFIG_PATH.exists():
        return copy.deepcopy(DEFAULTS)
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"⚠ 配置文件无法解析，本次使用默认配置：{CONFIG_PATH}（{exc}）", file=sys.stderr)
        return copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        print(f"⚠ 配置文件顶层不是对象，本次使用默认配置：{CONFIG_PATH}", file=sys.stderr)
        return copy.deepcopy(DEFAULTS)
    return _deep_merge(DEFAULTS, raw)


def save_config(cfg: dict[str, Any]) -> None:
    """原子写入配置并强制 0600 权限（含密钥，不能给同机其他用户读到）。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, stat.S_IRWXU)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    # 先建 0600 的空文件，再写内容，避免明文密钥有一瞬间是默认权限
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, CONFIG_PATH)
    os.chmod(CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)


# ---------------------------------------------------------------- 密钥


def doubao_key(cfg: dict[str, Any]) -> tuple[str, str]:
    """返回 (密钥, 来源)。来源用于 doctor 输出，取值 env / config / none。"""
    env_value = os.environ.get(DOUBAO_ENV, "").strip()
    if env_value:
        return env_value, "env"
    stored = str(cfg["doubao"].get("api_key") or "").strip()
    if stored:
        return stored, "config"
    return "", "none"


def parallel_key(cfg: dict[str, Any]) -> tuple[str, str]:
    """返回 (密钥, 来源)。没有密钥时回落到 parallel-cli 本机 OAuth 凭据。"""
    env_name = cfg["parallel"].get("api_key_env") or PARALLEL_ENV_DEFAULT
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return env_value, "env"
    stored = str(cfg["parallel"].get("api_key") or "").strip()
    if stored:
        return stored, "config"
    return "", "none"


def mask(secret: str) -> str:
    """密钥脱敏，只留首尾各 4 位，短密钥整体打码。"""
    if not secret:
        return "(未配置)"
    if len(secret) <= 12:
        return secret[:2] + "*" * max(len(secret) - 2, 0)
    return f"{secret[:4]}…{secret[-4:]}（共 {len(secret)} 位）"


def prompt_and_store_key(target: str) -> int:
    """交互写入密钥。必须由用户本人在终端执行，agent 不得代劳。"""
    if target not in ("doubao", "parallel"):
        print(f"未知的密钥目标：{target}（可选 doubao / parallel）", file=sys.stderr)
        return 2
    if not sys.stdin.isatty():
        print(
            "set-key 需要在交互式终端中运行，以免密钥进入命令行历史或日志。\n"
            "请你本人在终端执行：\n"
            f"  python3 {Path(__file__).resolve()} config set-key {target}",
            file=sys.stderr,
        )
        return 2

    label = "豆包搜索 API Key" if target == "doubao" else "Parallel API Key"
    secret = getpass.getpass(f"请粘贴{label}（输入不回显，回车确认）: ").strip()
    if not secret:
        print("未输入内容，已取消。", file=sys.stderr)
        return 2

    cfg = load_config()
    cfg[target]["api_key"] = secret
    save_config(cfg)
    print(f"已写入 {CONFIG_PATH}（权限 600）：{label} = {mask(secret)}")
    return 0


# ---------------------------------------------------------------- 预算


def resolve_budget(cfg: dict[str, Any], profile: str | None, budget: int | None) -> tuple[int, str]:
    """确定输出字符预算，返回 (预算, 档位名)。--budget 优先于 --profile。"""
    if budget and budget > 0:
        return budget, "custom"
    name = profile or cfg["output"].get("profile") or "standard"
    if name not in PROFILE_BUDGETS:
        name = "standard"
    configured = cfg["output"].get("budget_chars")
    if not profile and isinstance(configured, int) and configured > 0:
        return configured, "custom"
    return PROFILE_BUDGETS[name], name


# ---------------------------------------------------------------- 缓存

FILE_PREFIX = "grs-"  # 本工具写入的所有 json 文件都带这个前缀，供 prune_dir 精确识别
_PRUNE_GLOB = f"{FILE_PREFIX}*.json"


def _cache_dir(cfg: dict[str, Any]) -> Path:
    return Path(os.path.expanduser(cfg["cache"]["dir"]))


def cache_key(source: str, payload: Any) -> str:
    """按源与完整请求参数生成缓存键，参数变了就必须重新请求。"""
    blob = json.dumps({"source": source, "payload": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def cache_get(cfg: dict[str, Any], key: str) -> Any | None:
    """命中且未过期时返回缓存内容，否则返回 None。缓存问题一律降级为不命中。"""
    if not cfg["cache"].get("enabled", True):
        return None
    path = _cache_dir(cfg) / f"{FILE_PREFIX}{key}.json"
    try:
        if not path.exists():
            return None
        ttl = int(cfg["cache"].get("ttl_seconds", 1800))
        if ttl > 0 and time.time() - path.stat().st_mtime > ttl:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def secure_write(path: Path, content: str) -> None:
    """以 0600 权限写文件，避免全量结果/缓存以默认 umask（通常 0644）落盘。"""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)


def prune_dir(directory: Path, keep: int) -> None:
    """只保留最近 keep 个本工具写入的 json 文件（按 FILE_PREFIX 识别，不动目录里其他文件）。"""
    if keep <= 0:
        return
    try:
        files = sorted(directory.glob(_PRUNE_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in files[keep:]:
            stale.unlink(missing_ok=True)
    except OSError:
        pass


def cache_put(cfg: dict[str, Any], key: str, value: Any) -> None:
    """写缓存，失败静默忽略（缓存不是关键路径）。"""
    if not cfg["cache"].get("enabled", True):
        return
    try:
        directory = _cache_dir(cfg)
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, stat.S_IRWXU)
        secure_write(directory / f"{FILE_PREFIX}{key}.json", json.dumps(value, ensure_ascii=False))
    except OSError:
        return
    prune_dir(directory, int(cfg["cache"].get("keep_entries", 500)))


def dump_dir(cfg: dict[str, Any]) -> Path:
    """全量结果落盘目录，供 agent 追问时直接读取，避免重复搜索。"""
    directory = Path(os.path.expanduser(cfg["output"]["dump_dir"]))
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, stat.S_IRWXU)
    return directory
