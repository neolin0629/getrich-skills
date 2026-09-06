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
import math
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
        # 只是"从哪个环境变量读密钥"的输入别名。注入 parallel-cli 时**永远**用官方的
        # PARALLEL_API_KEY——把它同时当输出变量名会让自定义名字下鉴权静默失效，
        # 配成 PYTHONWARNINGS 之类还会让解释器把密钥打进 stderr。
        "api_key_env": PARALLEL_ENV_DEFAULT,
        "transport": "auto",  # auto | cli | http
        "mode": "basic",
        "max_results": 10,
        "excerpt_max_chars_total": 24000,
        # 声明"谁在消费这批结果"，供 Parallel 侧统计。默认值假设本 skill 跑在
        # Claude Code 里；换到别的 harness（Codex 等）请改成实际的模型名，
        # 它只影响上游的归因统计，不影响检索结果。
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
        # 带日级时效诉求的 query（今天/现在/实时/刚刚…）走这个短得多的 TTL。
        # 30 分钟的缓存对「北京今日最高气温」这类查询就是在发旧货，而工具本来
        # 就已经识别出这类 query 并给它加排序权重了，缓存这边不能装作不知道。
        # 仍保留一小段缓存而不是完全跳过：agent 同一轮里重复调用是常态，不该重复付费。
        "fresh_ttl_seconds": 120,
        "dir": str(CACHE_ROOT / "http"),
        "keep_entries": 500,
    },
    "card_shortcircuit": True,
}

PROFILE_BUDGETS = {"compact": 8000, "standard": 15000, "full": 30000}

# 规范化清单。判据是"这个字段会不会在调用点被强制转换"——会，就必须在这里，
# 否则一个笔误会变成远端调用之后的崩溃。下界的含义各不相同，逐项标注：
_INT_FIELDS = (
    ("cache", "ttl_seconds", 1),          # 0 会绕过 ttl > 0 的判断，变成永不过期
    ("cache", "fresh_ttl_seconds", 1),
    ("cache", "keep_entries", 0),         # 0 = 不清理，是文档写明的合法值
    ("output", "keep_runs", 0),
    ("doubao", "count", 1),
    ("doubao", "auth_info_level", 0),
    ("parallel", "max_results", 1),
    ("parallel", "excerpt_max_chars_total", 1),
)
_FLOAT_FIELDS = (
    ("fusion", "weight_doubao", 0.0, None),
    ("fusion", "weight_parallel", 0.0, None),
    ("fusion", "rrf_k", 1.0, None),       # RRF 的分母是 k + 名次，k ≤ 0 会除零
    ("fusion", "dedup_jaccard", 0.0, 1.0),  # Jaccard 相似度天然落在 [0, 1]
)
_CHOICE_FIELDS = (
    ("parallel", "transport", {"auto", "cli", "http"}),
    ("parallel", "mode", {"turbo", "fast", "basic", "advanced"}),
    # 官方只认 text / markdown，写错会原样发给上游换回一个语焉不详的远端报错
    ("doubao", "content_formats", {"text", "markdown"}),
    ("output", "profile", set(PROFILE_BUDGETS)),
)
_STR_FIELDS = (
    ("output", "dump_dir"),
    ("cache", "dir"),
)
# 单独一类：这个名字指向的**值会被当作密钥读取**，校验规则比普通字符串严
_ENV_NAME_FIELDS = (("parallel", "api_key_env"),)
# 布尔开关全部走真值判断（if cfg[...]），而字符串 "false" 在 Python 里是**真**。
# 后果不是崩溃而是静默反转：need_url: "false" 会真的发出 NeedUrl: true，
# 把如意卡片整个过滤掉——用户写下的配置起了与字面相反的作用，最难排查的一类 bug。
_BOOL_FIELDS = (
    ("parallel", "enabled"),
    ("cache", "enabled"),
    ("doubao", "need_url"),
    ("doubao", "need_content"),
    ("doubao", "query_rewrite"),
)
_TOP_BOOL_FIELDS = ("card_shortcircuit",)


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


def _strict_int(value: Any) -> int | None:
    """严格整数解析，无法确定语义时返回 None 而不是猜。

    裸 int() 会放过三类东西：`true` 变成 TTL 1（JSON 里这明显是笔误而不是意图）、
    `1.9` 被静默截成 1、`Infinity` 抛 OverflowError——OverflowError 既不是
    TypeError 也不是 ValueError，会直接漏出去崩掉整条命令，连 `config doctor` 都起不来。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or value != int(value):
            return None
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def bounded_int(value: Any, default: int, label: str, minimum: int) -> int:
    """把配置项读成整数并夹在下界之上；非法值告警后回退默认，绝不让它传播出去。

    两个具体后果：`ttl_seconds: "invalid"` 会在调用任何 source 之前抛 ValueError 崩掉整条命令；
    而 TTL 取 0 或负数会绕过 `ttl > 0` 的过期判断，把磁盘缓存变成永不过期。
    minimum=0 用于 keep_runs / keep_entries——它们的 0 是"不清理"的合法取值。
    """
    parsed = _strict_int(value)
    if parsed is None:
        print(f"⚠ 配置项 {label} 不是整数（{value!r}），改用默认值 {default}", file=sys.stderr)
        return default
    if parsed < minimum:
        print(f"⚠ 配置项 {label} 不得小于 {minimum}（{value!r}），改用默认值 {default}", file=sys.stderr)
        return default
    return parsed


def bounded_float(value: Any, default: float, label: str,
                  minimum: float, maximum: float | None = None) -> float:
    """浮点配置项同理。`dedup_jaccard: "oops"` 尤其恶劣——它在**两个源都返回之后**
    才被 float()，钱已经花掉了，命令却崩在最后一步，用户什么也拿不到。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        parsed = None
    else:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = None
    if parsed is None or not math.isfinite(parsed):
        print(f"⚠ 配置项 {label} 不是有效数字（{value!r}），改用默认值 {default}", file=sys.stderr)
        return default
    if parsed < minimum or (maximum is not None and parsed > maximum):
        span = f"[{minimum}, {maximum}]" if maximum is not None else f"≥ {minimum}"
        print(f"⚠ 配置项 {label} 超出范围 {span}（{value!r}），改用默认值 {default}", file=sys.stderr)
        return default
    return parsed


def one_of(value: Any, default: str, label: str, allowed: set[str]) -> str:
    """枚举配置项。`transport: 1` 会让 resolve_transport 在 .lower() 上抛 AttributeError。"""
    if isinstance(value, str) and value.strip().lower() in allowed:
        return value.strip().lower()
    print(f"⚠ 配置项 {label} 只能是 {'/'.join(sorted(allowed))}（{value!r}），"
          f"改用默认值 {default}", file=sys.stderr)
    return default


def strict_bool(value: Any, default: bool, label: str) -> bool:
    """只接受 JSON 的 true/false。

    刻意不认 "true"/"false"/0/1：认了就等于鼓励在配置里写字符串，
    而写错一个字母（"flase"）又会静默变成真。宁可告警让用户改成真布尔值。
    """
    if isinstance(value, bool):
        return value
    print(f"⚠ 配置项 {label} 只能是 true 或 false（{value!r}，注意 \"false\" 是字符串、"
          f"在判断时为真），改用默认值 {default}", file=sys.stderr)
    return default


# api_key_env 指向的变量会被**当成密钥读取**，所以名字本身要挑。
# 指到 PATH 就会把 PATH 的值当密钥发给上游；指到 PYTHONWARNINGS 这类解释器控制变量，
# 即使我们不再往里注入，用户自己 export 之后一样会被读成密钥。
_UNSAFE_ENV_NAMES = {
    "PATH", "HOME", "USER", "SHELL", "PWD", "TMPDIR", "LANG", "TERM",
    "PYTHONWARNINGS", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME", "PYTHONINSPECT",
    "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "IFS", "BASH_ENV",
}
_ENV_NAME = __import__("re").compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _describe(value: Any) -> str:
    """描述一个不便回显的值：只给类型和长度，不给内容。"""
    if isinstance(value, str):
        return f"{type(value).__name__}，长度 {len(value)}，值已隐藏"
    return f"{type(value).__name__}，值已隐藏"


def env_var_name(value: Any, default: str, label: str) -> str:
    """校验"从哪个环境变量读密钥"这个名字。

    它不是普通字符串项：这个名字指向的值会被直接当作 API Key 用。
    形态不合法（含空格、空串）或指向众所周知的系统/解释器变量，一律拒绝——
    否则一次笔误就会把 PATH 的内容当密钥发给上游。
    """
    if isinstance(value, str) and _ENV_NAME.fullmatch(value.strip()):
        name = value.strip()
        if name.upper() not in _UNSAFE_ENV_NAMES:
            return name
        print(f"⚠ 配置项 {label} 不能指向系统/解释器变量 {name}（它的值会被当成密钥读取），"
              f"改用默认值 {default}", file=sys.stderr)
        return default
    # **不回显原值**：把这里填错的人，最可能填进去的就是密钥本身
    # （"环境变量名"和"环境变量的值"是最容易混的一对）。一旦回显，
    # 搜索、config show、doctor 每次都会把它写进终端、agent 上下文和 CI 日志。
    print(f"⚠ 配置项 {label} 不是合法的环境变量名（{_describe(value)}），"
          f"改用默认值 {default}。注意这里要填**变量名**而不是密钥本身。",
          file=sys.stderr)
    return default


def plain_str(value: Any, default: str, label: str) -> str:
    """路径/环境变量名之类的字符串项。非字符串会在 expanduser / os.environ 上崩。"""
    if isinstance(value, str) and value.strip():
        return value
    print(f"⚠ 配置项 {label} 不是非空字符串（{value!r}），改用默认值 {default}", file=sys.stderr)
    return default


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
    cfg = _deep_merge(DEFAULTS, raw)
    # section 必须是对象。`{"cache": null}` / `{"cache": []}` / `{"output": "x"}` 会被
    # _deep_merge 原样保留（非 dict 直接覆盖），随后每一处 cfg["cache"].get(...) 都抛
    # AttributeError——连用来诊断这个问题的 `config doctor` 自己都跑不起来。
    for section, default in DEFAULTS.items():
        if isinstance(default, dict) and not isinstance(cfg.get(section), dict):
            print(f"⚠ 配置项 {section} 不是对象（{cfg.get(section)!r}），本节改用默认值", file=sys.stderr)
            cfg[section] = copy.deepcopy(default)
    # 所有会被调用点 int() / float() / .lower() / expanduser() 的公开字段都在这里
    # 一次性规范化。只normalize TTL 是不够的——调用点散落在各处，每一处都可能崩，
    # 而崩的时机往往在付费请求之后（fusion.* 在两个源都返回后才被读到）。
    for section, key, minimum in _INT_FIELDS:
        cfg[section][key] = bounded_int(
            cfg[section].get(key), DEFAULTS[section][key], f"{section}.{key}", minimum
        )
    for section, key, minimum, maximum in _FLOAT_FIELDS:
        cfg[section][key] = bounded_float(
            cfg[section].get(key), DEFAULTS[section][key], f"{section}.{key}", minimum, maximum
        )
    for section, key, allowed in _CHOICE_FIELDS:
        cfg[section][key] = one_of(
            cfg[section].get(key), DEFAULTS[section][key], f"{section}.{key}", allowed
        )
    for section, key in _STR_FIELDS:
        cfg[section][key] = plain_str(
            cfg[section].get(key), DEFAULTS[section][key], f"{section}.{key}"
        )
    for section, key in _ENV_NAME_FIELDS:
        cfg[section][key] = env_var_name(
            cfg[section].get(key), DEFAULTS[section][key], f"{section}.{key}"
        )
    for section, key in _BOOL_FIELDS:
        cfg[section][key] = strict_bool(
            cfg[section].get(key), DEFAULTS[section][key], f"{section}.{key}"
        )
    for key in _TOP_BOOL_FIELDS:
        cfg[key] = strict_bool(cfg.get(key), DEFAULTS[key], key)
    # budget_chars 允许为 null（表示"用 profile 的值"），非 null 时必须是正整数。
    # 校验失败要回到**真正的默认值 None**，而不是 15000——回退成一个具体数字
    # 等于凭空造出一个 custom 预算，把用户合法的 output.profile 覆盖掉：
    # {"profile": "compact", "budget_chars": "oops"} 会得到 (15000, custom) 而不是 (8000, compact)。
    if cfg["output"].get("budget_chars") is not None:
        parsed = _strict_int(cfg["output"]["budget_chars"])
        if parsed is None or parsed < 1:
            print(f"⚠ 配置项 output.budget_chars 不是正整数"
                  f"（{cfg['output']['budget_chars']!r}），改用默认值 null（按 profile 取）",
                  file=sys.stderr)
            parsed = DEFAULTS["output"]["budget_chars"]
        cfg["output"]["budget_chars"] = parsed
    return cfg


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
    stored = str((cfg.get("doubao") or {}).get("api_key") or "").strip()
    if stored:
        return stored, "config"
    return "", "none"


def parallel_key(cfg: dict[str, Any]) -> tuple[str, str]:
    """返回 (密钥, 来源)。没有密钥时回落到 parallel-cli 本机 OAuth 凭据。"""
    env_name = (cfg.get("parallel") or {}).get("api_key_env") or PARALLEL_ENV_DEFAULT
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return env_value, "env"
    stored = str((cfg.get("parallel") or {}).get("api_key") or "").strip()
    if stored:
        return stored, "config"
    return "", "none"


def mask(secret: str) -> str:
    """密钥脱敏，只留首尾各 4 位，短密钥整体打码。"""
    if not secret:
        return "(未配置)"
    if len(secret) <= 4:
        # 1~2 位时 secret[:2] 就是全部内容，等于没脱敏
        return "*" * len(secret)
    if len(secret) <= 12:
        return secret[:2] + "*" * (len(secret) - 2)
    return f"{secret[:4]}…{secret[-4:]}（共 {len(secret)} 位）"


def fingerprint(secret: str) -> str:
    """密钥指纹：够用来回答"配的是不是同一个密钥"，又不泄露密钥本身。

    这是明文回显的替代品。原来有个 --raw-parallel-key 直接 print 密钥，
    靠 stdout.isatty() 当护栏——伪终端下父进程、agent、CI 日志照样全都拿得到。
    要比对密钥用指纹：同一个密钥指纹相同，而指纹反推不出密钥。
    """
    if not secret:
        return "(未配置)"
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:12]


def prompt_and_store_key(target: str) -> int:
    """交互写入密钥。必须由用户本人在终端执行，agent 不得代劳。"""
    if target not in ("doubao", "parallel"):
        print(f"未知的密钥目标：{target}（可选 doubao / parallel）", file=sys.stderr)
        return 2
    if not sys.stdin.isatty():
        print(
            "set-key 需要在交互式终端中运行，以免密钥进入命令行历史或日志。\n"
            "请你本人在终端执行：\n"
            f"  python3 {Path(__file__).resolve().parent / 'gr_search.py'} config set-key {target}",
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


def cache_get(cfg: dict[str, Any], key: str, ttl: int | None = None) -> Any | None:
    """命中且未过期时返回缓存内容，否则返回 None。缓存问题一律降级为不命中。

    ttl 用于按查询覆盖默认存活时间（时效敏感的 query 只接受很新的缓存）。
    """
    if not cfg["cache"].get("enabled", True):
        return None
    path = _cache_dir(cfg) / f"{FILE_PREFIX}{key}.json"
    try:
        if not path.exists():
            return None
        # 防御性兜底：load_config 已规范化过，但 cfg 也可能由库调用方自己拼出来
        if ttl is None:
            ttl = bounded_int(cfg["cache"].get("ttl_seconds"), 1800, "cache.ttl_seconds", 1)
        else:
            ttl = bounded_int(ttl, 1800, "cache_ttl", 1)
        if time.time() - path.stat().st_mtime > ttl:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def secure_write(path: Path, content: str) -> None:
    """以 0600 权限写文件，避免全量结果/缓存以默认 umask（通常 0644）落盘。

    os.open 的 mode 只在「创建」时生效，覆写既有文件不会收紧它的权限，
    所以必须再 fchmod 一次——否则历史上以 0644 落盘的文件会一直保持可读。
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        os.fchmod(fh.fileno(), stat.S_IRUSR | stat.S_IWUSR)
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
