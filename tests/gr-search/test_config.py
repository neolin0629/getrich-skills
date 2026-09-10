#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置加载、密钥落盘权限、缓存清理。

配置里的坏值有一类特别恶劣：它让**用来诊断这个问题的 `config doctor` 自己也起不来**。
`ttl_seconds: Infinity` 抛的是 OverflowError，既不是 TypeError 也不是 ValueError，
裸 int() 的 except 接不住；`{"cache": null}` 则让后续每一处 cfg["cache"].get() 抛
AttributeError。所以规范化必须在 load_config 里一次做完，且永远不抛。
"""

from __future__ import annotations

import argparse
import os
import re
import stat

import pytest

import config as cfgmod


# ---------------------------------------------------------------- 非法值


@pytest.mark.parametrize("raw,section,key,expect", [
    pytest.param('{"cache": null}', "cache", "ttl_seconds", 1800, id="section=null"),
    pytest.param('{"cache": []}', "cache", "ttl_seconds", 1800, id="section=list"),
    pytest.param('{"output": "x"}', "output", "keep_runs", 200, id="section=str"),
    pytest.param('{"cache": {"ttl_seconds": Infinity}}', "cache", "ttl_seconds", 1800, id="Infinity"),
    pytest.param('{"cache": {"ttl_seconds": -Infinity}}', "cache", "ttl_seconds", 1800, id="-Infinity"),
    pytest.param('{"cache": {"ttl_seconds": NaN}}', "cache", "ttl_seconds", 1800, id="NaN"),
    pytest.param('{"cache": {"ttl_seconds": true}}', "cache", "ttl_seconds", 1800, id="bool"),
    pytest.param('{"cache": {"ttl_seconds": 1.9}}', "cache", "ttl_seconds", 1800, id="非整值浮点"),
    pytest.param('{"cache": {"ttl_seconds": "invalid"}}', "cache", "ttl_seconds", 1800, id="字符串"),
    pytest.param('{"cache": {"ttl_seconds": 0}}', "cache", "ttl_seconds", 1800, id="0=永不过期"),
    pytest.param('{"cache": {"ttl_seconds": -5}}', "cache", "ttl_seconds", 1800, id="负数"),
    pytest.param('{"cache": {"fresh_ttl_seconds": 0}}', "cache", "fresh_ttl_seconds", 120, id="短TTL=0"),
    pytest.param('{"output": {"keep_runs": -1}}', "output", "keep_runs", 200, id="keep_runs负数"),
])
def test_invalid_values_fall_back_with_warning(load_config_from, raw, section, key, expect):
    cfg, err = load_config_from(raw)
    assert cfg[section][key] == expect
    assert "⚠" in err, "静默回退——用户永远不会知道配置写错了"


@pytest.mark.parametrize("raw,section,key,expect", [
    pytest.param('{"cache": {"ttl_seconds": 60}}', "cache", "ttl_seconds", 60, id="int"),
    pytest.param('{"cache": {"ttl_seconds": "900"}}', "cache", "ttl_seconds", 900, id="数字字符串"),
    pytest.param('{"cache": {"ttl_seconds": 900.0}}', "cache", "ttl_seconds", 900, id="整值浮点"),
    pytest.param('{"output": {"keep_runs": 0}}', "output", "keep_runs", 0, id="keep_runs=0"),
    pytest.param('{"cache": {"keep_entries": 0}}', "cache", "keep_entries", 0, id="keep_entries=0"),
])
def test_valid_values_pass_through_silently(load_config_from, raw, section, key, expect):
    """`keep_* = 0` 是文档写明的"不清理"，不是非法值——
    用统一的"必须为正"规则会把一个正常功能改坏。"""
    cfg, err = load_config_from(raw)
    assert cfg[section][key] == expect
    assert "⚠" not in err, "对合法配置误报告警"


def test_broken_json_falls_back_to_defaults(load_config_from):
    cfg, err = load_config_from("{ 这不是 JSON")
    assert cfg["cache"]["ttl_seconds"] == 1800
    assert "⚠" in err


def test_non_object_toplevel_falls_back(load_config_from):
    cfg, err = load_config_from('["a"]')
    assert cfg["cache"]["ttl_seconds"] == 1800
    assert "⚠" in err


def test_doctor_survives_every_section_being_wrong(load_config_from, capsys):
    """坏配置的最低要求：诊断命令本身还能跑起来告诉用户哪里坏了。"""
    import gr_search

    cfg, _ = load_config_from(
        '{"cache": null, "output": [], "fusion": "x", "doubao": 3, "parallel": null}')
    args = argparse.Namespace(op="show", target=None, raw_parallel_key=False)
    assert gr_search.run_config(args, cfg) == 0
    assert cfgmod.resolve_budget(cfg, None, None) == (15000, "standard")


def test_unknown_keys_are_preserved(load_config_from):
    """不认识的键原样保留，不要替用户删配置。"""
    cfg, _ = load_config_from('{"cache": {"未来的选项": 1}}')
    assert cfg["cache"]["未来的选项"] == 1


# ---------------------------------------------------------------- 权限


def test_secure_write_is_0600(tmp_path):
    target = tmp_path / "x.json"
    cfgmod.secure_write(target, "{}")
    assert target.stat().st_mode & 0o777 == 0o600


def test_secure_write_tightens_existing_file(tmp_path):
    """os.open 的 mode 只在创建时生效——覆写既有文件必须再 fchmod 一次，
    否则历史上以 0644 落盘的文件会一直保持可读。"""
    target = tmp_path / "x.json"
    target.write_text("{}")
    os.chmod(target, 0o644)
    cfgmod.secure_write(target, "{}")
    assert target.stat().st_mode & 0o777 == 0o600


# ---------------------------------------------------------------- 清理


def test_prune_only_touches_own_files(tmp_path):
    """dump_dir / cache dir 可能是用户自己也在用的目录，
    按 FILE_PREFIX 精确识别，绝不按 *.json 通配去删。"""
    foreign = tmp_path / "用户自己的.json"
    foreign.write_text("{}")
    for i in range(5):
        cfgmod.secure_write(tmp_path / f"{cfgmod.FILE_PREFIX}{i}.json", "{}")
    cfgmod.prune_dir(tmp_path, keep=2)
    assert foreign.exists()
    assert len(list(tmp_path.glob(f"{cfgmod.FILE_PREFIX}*.json"))) == 2


def test_prune_keep_zero_means_no_cleanup(tmp_path):
    for i in range(3):
        cfgmod.secure_write(tmp_path / f"{cfgmod.FILE_PREFIX}{i}.json", "{}")
    cfgmod.prune_dir(tmp_path, keep=0)
    assert len(list(tmp_path.glob(f"{cfgmod.FILE_PREFIX}*.json"))) == 3


def test_prune_survives_missing_dir(tmp_path):
    cfgmod.prune_dir(tmp_path / "不存在", keep=2)  # 不得抛异常


# ---------------------------------------------------------------- 缓存键与 TTL


def test_cache_key_changes_with_payload():
    assert cfgmod.cache_key("doubao", {"q": "a"}) != cfgmod.cache_key("doubao", {"q": "b"})


def test_cache_key_is_source_scoped():
    assert cfgmod.cache_key("doubao", {"q": "a"}) != cfgmod.cache_key("parallel", {"q": "a"})


def test_cache_miss_on_expired_entry(tmp_path):
    cfg = {"cache": {"enabled": True, "dir": str(tmp_path), "ttl_seconds": 1800}}
    key = "k" * 32
    cfgmod.secure_write(tmp_path / f"{cfgmod.FILE_PREFIX}{key}.json", '{"v": 1}')
    assert cfgmod.cache_get(cfg, key, ttl=3600) == {"v": 1}
    os.utime(tmp_path / f"{cfgmod.FILE_PREFIX}{key}.json", (0, 0))
    assert cfgmod.cache_get(cfg, key, ttl=3600) is None


def test_bad_ttl_at_call_site_does_not_crash(tmp_path):
    """cfg 也可能由库调用方自己拼出来，没走过 load_config 的规范化。"""
    cfg = {"cache": {"enabled": True, "dir": str(tmp_path), "ttl_seconds": "坏值"}}
    assert cfgmod.cache_get(cfg, "k" * 32) is None


def test_resolve_budget_precedence():
    cfg = cfgmod.load_config.__globals__["DEFAULTS"]
    import copy
    base = copy.deepcopy(cfg)
    assert cfgmod.resolve_budget(base, None, 999) == (999, "custom")   # --budget 最高
    assert cfgmod.resolve_budget(base, "compact", None) == (8000, "compact")
    base["output"]["budget_chars"] = 4321
    assert cfgmod.resolve_budget(base, None, None) == (4321, "custom")
    assert cfgmod.resolve_budget(base, "full", None) == (30000, "full")  # 显式 profile 压过配置


# ---------------------------------------------------------------- 全字段规范化

@pytest.mark.parametrize("raw,section,key,expect", [
    # 这些字段过去只在调用点被强制转换，笔误要等到那一刻才炸
    pytest.param('{"parallel": {"transport": 1}}', "parallel", "transport", "auto", id="transport非字符串"),
    pytest.param('{"parallel": {"transport": "ftp"}}', "parallel", "transport", "auto", id="transport未知值"),
    pytest.param('{"parallel": {"mode": "hyper"}}', "parallel", "mode", "basic", id="mode未知值"),
    pytest.param('{"doubao": {"count": "bad"}}', "doubao", "count", 10, id="count非数字"),
    pytest.param('{"doubao": {"count": 0}}', "doubao", "count", 10, id="count=0"),
    pytest.param('{"parallel": {"max_results": "bad"}}', "parallel", "max_results", 10, id="max_results非数字"),
    pytest.param('{"parallel": {"excerpt_max_chars_total": "x"}}', "parallel",
                 "excerpt_max_chars_total", 24000, id="excerpt非数字"),
    pytest.param('{"fusion": {"dedup_jaccard": "oops"}}', "fusion", "dedup_jaccard", 0.9, id="阈值非数字"),
    pytest.param('{"fusion": {"dedup_jaccard": 1.5}}', "fusion", "dedup_jaccard", 0.9, id="阈值越界"),
    pytest.param('{"fusion": {"rrf_k": -1}}', "fusion", "rrf_k", 60, id="rrf_k负数除零"),
    pytest.param('{"fusion": {"rrf_k": 0}}', "fusion", "rrf_k", 60, id="rrf_k=0除零"),
    pytest.param('{"fusion": {"weight_doubao": "x"}}', "fusion", "weight_doubao", 1.0, id="权重非数字"),
    pytest.param('{"fusion": {"weight_parallel": Infinity}}', "fusion", "weight_parallel", 1.0, id="权重无穷"),
    pytest.param('{"output": {"profile": "huge"}}', "output", "profile", "standard", id="profile未知"),
    pytest.param('{"cache": {"dir": 5}}', "cache", "dir", None, id="缓存目录非字符串"),
    # 回退目标是**真正的默认值 None**，不是 15000——回退成具体数字等于凭空造出
    # 一个 custom 预算，把用户合法的 output.profile 覆盖掉
    pytest.param('{"output": {"budget_chars": 0}}', "output", "budget_chars", None, id="budget_chars=0"),
])
def test_all_coerced_fields_are_normalized(load_config_from, raw, section, key, expect):
    cfg, err = load_config_from(raw)
    assert "⚠" in err
    if expect is not None:
        assert cfg[section][key] == expect


def test_budget_chars_null_is_valid(load_config_from):
    """null 表示"用 profile 的值"，是合法配置，不该告警。"""
    cfg, err = load_config_from('{"output": {"budget_chars": null}}')
    assert cfg["output"]["budget_chars"] is None
    assert "⚠" not in err


def test_transport_is_case_normalized(load_config_from):
    cfg, err = load_config_from('{"parallel": {"transport": "HTTP"}}')
    assert cfg["parallel"]["transport"] == "http"
    assert "⚠" not in err


@pytest.mark.parametrize("raw", [
    '{"parallel": {"transport": 1}}',
    '{"doubao": {"count": "bad"}}',
    '{"parallel": {"max_results": "bad"}}',
    '{"fusion": {"dedup_jaccard": "oops"}}',
    '{"fusion": {"rrf_k": -1}}',
    '{"fusion": {"weight_doubao": "x"}}',
    '{"cache": {"dir": 5}}',
])
def test_bad_config_never_reaches_call_sites(load_config_from, raw):
    """规范化的意义在于调用点拿到的一定是能用的值。

    fusion.* 尤其要紧：它在**两个源都返回之后**才被读到，
    崩在那里意味着钱已经花了、结果却拿不到。
    """
    import copy

    import fusion
    import sources
    from fusion import Merged

    cfg, _ = load_config_from(raw)
    sources.resolve_transport(cfg)
    sources.build_doubao_payload("q", {}, cfg)
    sources.build_parallel_http_payload(cfg, "o", ["a"], {})
    sources.build_parallel_cmd(cfg, "o", ["a"], {}, "/tmp/x")
    item = Merged(url="u", title="t", body="b", site="s", sources={"doubao": 1})
    fusion.merge([], threshold=float(cfg["fusion"]["dedup_jaccard"]))
    fusion.rank([item], cfg)
    cfgmod.resolve_budget(cfg, None, None)
    os.path.expanduser(cfg["cache"]["dir"])


# ---------------------------------------------------------------- 布尔开关


@pytest.mark.parametrize("raw,section,key", [
    pytest.param('{"parallel": {"enabled": "false"}}', "parallel", "enabled", id="parallel.enabled"),
    pytest.param('{"cache": {"enabled": "false"}}', "cache", "enabled", id="cache.enabled"),
    pytest.param('{"doubao": {"need_url": "false"}}', "doubao", "need_url", id="need_url"),
    pytest.param('{"doubao": {"need_content": "false"}}', "doubao", "need_content", id="need_content"),
    pytest.param('{"doubao": {"query_rewrite": "false"}}', "doubao", "query_rewrite", id="query_rewrite"),
])
def test_string_false_does_not_become_true(load_config_from, raw, section, key):
    """字符串 "false" 在 Python 里是**真**。这类缺陷不是崩溃而是静默反转：
    用户写下的配置起了与字面完全相反的作用。"""
    cfg, err = load_config_from(raw)
    assert cfg[section][key] is DEFAULTS_BOOL[(section, key)]
    assert "⚠" in err


DEFAULTS_BOOL = {
    ("parallel", "enabled"): True, ("cache", "enabled"): True,
    ("doubao", "need_url"): False, ("doubao", "need_content"): False,
    ("doubao", "query_rewrite"): False,
}


def test_top_level_bool_normalized(load_config_from):
    cfg, err = load_config_from('{"card_shortcircuit": "false"}')
    assert cfg["card_shortcircuit"] is False
    assert "⚠" in err


def test_string_false_need_url_does_not_filter_ruyi(load_config_from):
    """need_url: "false" 过去会真的发出 NeedUrl: true，把如意卡片整个过滤掉——
    官方文档明确 NeedUrl=true 会滤掉如意结果。"""
    import sources

    cfg, _ = load_config_from('{"doubao": {"need_url": "false"}}')
    assert "NeedUrl" not in (sources.build_doubao_payload("q", {}, cfg).get("Filter") or {})


def test_real_true_still_sends_need_url(load_config_from):
    import sources

    cfg, _ = load_config_from('{"doubao": {"need_url": true}}')
    assert sources.build_doubao_payload("q", {}, cfg)["Filter"]["NeedUrl"] is True


@pytest.mark.parametrize("raw,section,key,expect", [
    ('{"cache": {"enabled": false}}', "cache", "enabled", False),
    ('{"cache": {"enabled": true}}', "cache", "enabled", True),
    ('{"doubao": {"need_url": true}}', "doubao", "need_url", True),
])
def test_real_booleans_pass_silently(load_config_from, raw, section, key, expect):
    cfg, err = load_config_from(raw)
    assert cfg[section][key] is expect
    assert "⚠" not in err


@pytest.mark.parametrize("bad", ["0", "1", '"true"', '"yes"', "null", "[]"])
def test_non_boolean_forms_rejected(load_config_from, bad):
    """刻意不认 0/1/"true"：认了就等于鼓励在配置里写字符串，
    而写错一个字母（"flase"）又会静默变成真。"""
    cfg, err = load_config_from('{"cache": {"enabled": %s}}' % bad)
    assert cfg["cache"]["enabled"] is True
    assert "⚠" in err


@pytest.mark.parametrize("raw,expect", [
    ('{"doubao": {"content_formats": "html"}}', "markdown"),
    ('{"doubao": {"content_formats": 1}}', "markdown"),
    ('{"doubao": {"content_formats": "MARKDOWN"}}', "markdown"),
])
def test_content_formats_normalized(load_config_from, raw, expect):
    """官方只认 text / markdown，写错会原样发给上游换回一个语焉不详的远端报错。"""
    cfg, _ = load_config_from(raw)
    assert cfg["doubao"]["content_formats"] == expect


def test_content_formats_text_is_valid(load_config_from):
    cfg, err = load_config_from('{"doubao": {"content_formats": "text"}}')
    assert cfg["doubao"]["content_formats"] == "text"
    assert "⚠" not in err


def test_bad_content_formats_never_reaches_payload(load_config_from):
    import sources

    cfg, _ = load_config_from('{"doubao": {"content_formats": "html"}}')
    assert sources.build_doubao_payload("q", {}, cfg)["ContentFormats"] in ("text", "markdown")


# ---------------------------------------------------------------- 密钥不得明文回显


def test_no_plaintext_key_flag_exists():
    """回归：--raw-parallel-key 用 stdout.isatty() 当护栏打印明文密钥。
    那道护栏是假的——伪终端下父进程、agent、CI 日志照样能完整捕获输出。
    这个入口已彻底移除，不是加固，是删除。"""
    import gr_search
    from pathlib import Path

    conf = gr_search.build_parser()._subparsers._group_actions[0].choices["config"]
    flags = [flag for action in conf._actions for flag in action.option_strings]
    assert "--raw-parallel-key" not in flags
    # 也不许换个名字复活：源码里不该再有任何直接 print 密钥的路径。
    # 注意用词边界——`fingerprint(parallel_secret)` 里就含有子串
    # `print(parallel_secret)`，裸 `in` 判断会误报（正是 now/snowflake 那个坑）。
    source = Path(gr_search.__file__).read_text(encoding="utf-8")
    bare_print = re.compile(r"(?<![A-Za-z_])print\(\s*(?:parallel|doubao)_secret\s*\)")
    assert not bare_print.search(source), "又出现了直接 print 密钥的路径"


def test_config_show_never_prints_the_key(tmp_path, monkeypatch, capsys):
    """config show 的任何输出里都不能出现完整密钥。"""
    import copy

    import gr_search

    sentinel = "sk-SENTINEL-0123456789abcdefXYZ"
    cfg = copy.deepcopy(cfgmod.DEFAULTS)
    cfg["parallel"]["api_key"] = sentinel
    cfg["doubao"]["api_key"] = sentinel
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    monkeypatch.delenv(cfgmod.DOUBAO_ENV, raising=False)
    args = argparse.Namespace(op="show", target=None)
    assert gr_search.run_config(args, cfg) == 0
    out = capsys.readouterr()
    assert sentinel not in out.out and sentinel not in out.err


def test_fingerprint_identifies_without_revealing():
    """指纹要能回答"配的是不是同一个密钥"，但反推不出密钥。"""
    secret = "sk-SENTINEL-0123456789abcdefXYZ"
    fp = cfgmod.fingerprint(secret)
    assert fp == cfgmod.fingerprint(secret)
    assert fp != cfgmod.fingerprint(secret + "x")
    assert secret[:8] not in fp and len(fp) <= 16
    assert cfgmod.fingerprint("") == "(未配置)"


def test_mask_never_leaks_short_keys():
    assert cfgmod.mask("abc123") .count("*") >= 4
    assert "0123456789abcdef" not in cfgmod.mask("sk-0123456789abcdef-tail")


# ---------------------------------------------------------------- api_key_env 的双重用途


@pytest.mark.parametrize("env_name", ["PYTHONWARNINGS", "MY_CUSTOM_KEY", "LD_PRELOAD"])
def test_api_key_env_never_becomes_the_injected_name(env_name):
    """回归：api_key_env 被同时当作"从哪读"和"注入哪个变量"，两个后果都实测过——
    自定义名字下 CLI 读的仍是 PARALLEL_API_KEY，密钥根本没送到、鉴权静默失效；
    配成 PYTHONWARNINGS 这类解释器控制变量，子进程会把**完整密钥**打进 stderr。

    它只能是输入别名；注入子进程时永远用官方的 PARALLEL_API_KEY。
    """
    import copy

    import sources

    secret = "sk-SENTINEL-secret-value-9876543210"
    cfg = copy.deepcopy(cfgmod.DEFAULTS)
    cfg["parallel"]["api_key"] = secret
    cfg["parallel"]["api_key_env"] = env_name
    env = sources.parallel_env(cfg)
    assert env[cfgmod.PARALLEL_ENV_DEFAULT] == secret, "密钥没注入到 CLI 实际读的变量"
    if env_name != cfgmod.PARALLEL_ENV_DEFAULT:
        assert env.get(env_name) != secret, f"{env_name} 被密钥污染"


def test_python_control_var_no_longer_leaks_to_stderr():
    """按审核的复现方式实测：子进程 stderr 里不得出现明文密钥。"""
    import copy
    import subprocess
    import sys

    import sources

    secret = "sk-SENTINEL-secret-value-9876543210"
    cfg = copy.deepcopy(cfgmod.DEFAULTS)
    cfg["parallel"]["api_key"] = secret
    cfg["parallel"]["api_key_env"] = "PYTHONWARNINGS"
    proc = subprocess.run([sys.executable, "-c", "print('ok')"],
                          env=sources.parallel_env(cfg), capture_output=True, text=True)
    assert secret not in proc.stderr and secret not in proc.stdout


@pytest.mark.parametrize("origin_env", [True, False])
def test_env_sourced_key_is_not_reinjected(origin_env, monkeypatch):
    """密钥本来就来自环境变量时不必重复注入（子进程本就继承得到）。"""
    import copy

    import sources

    secret = "sk-SENTINEL-secret-value-9876543210"
    cfg = copy.deepcopy(cfgmod.DEFAULTS)
    if origin_env:
        monkeypatch.setenv(cfgmod.PARALLEL_ENV_DEFAULT, secret)
    else:
        monkeypatch.delenv(cfgmod.PARALLEL_ENV_DEFAULT, raising=False)
        cfg["parallel"]["api_key"] = secret
    assert sources.parallel_env(cfg)[cfgmod.PARALLEL_ENV_DEFAULT] == secret


def test_subprocess_output_is_redacted():
    """纵深防御：子进程仍可能因别的原因回显环境变量，
    而错误详情是要显示给用户的，出口再兜一道。"""
    import copy

    import sources

    secret = "sk-SENTINEL-secret-value-9876543210"
    cfg = copy.deepcopy(cfgmod.DEFAULTS)
    cfg["parallel"]["api_key"] = secret
    assert secret not in sources.redact(f"boom {secret} end", cfg)
    assert "[已脱敏的密钥]" in sources.redact(f"boom {secret} end", cfg)
    assert sources.redact("", cfg) == ""
    assert sources.redact("正常错误", cfg) == "正常错误"


@pytest.mark.parametrize("secret", ["a", "ab", "abc", "abcd"])
def test_mask_hides_very_short_keys_entirely(secret):
    """回归：1~2 位的"密钥"里 secret[:2] 就是全部内容，等于没脱敏。"""
    assert secret not in cfgmod.mask(secret)


def test_doctor_shows_fingerprint(capsys, monkeypatch):
    """SKILL.md 声称 doctor 也显示指纹——实际一度只有 show 显示。
    文档和实现必须一致，而 doctor 才是诊断命令。"""
    import copy

    import gr_search

    secret = "sk-SENTINEL-0123456789abcdefXYZ"
    cfg = copy.deepcopy(cfgmod.DEFAULTS)
    cfg["parallel"]["api_key"] = secret
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    monkeypatch.setattr(cfgmod, "CONFIG_PATH", cfgmod.CONFIG_PATH.with_name("does-not-exist.json"))
    gr_search.run_config(argparse.Namespace(op="doctor", target=None), cfg)
    out = capsys.readouterr().out
    assert cfgmod.fingerprint(secret) in out
    assert secret not in out


@pytest.mark.parametrize("bad", ["PATH", "HOME", "PYTHONWARNINGS", "LD_PRELOAD",
                                 "DYLD_INSERT_LIBRARIES", "my key", "", "1BAD"])
def test_dangerous_api_key_env_names_rejected(load_config_from, bad):
    """api_key_env 指向的变量的**值会被当成密钥读取**。指到 PATH 就会把 PATH
    的内容发给上游；指到解释器控制变量，用户自己 export 之后一样会被读成密钥。
    这不是普通字符串项，校验要更严。"""
    import json as jsonlib

    cfg, err = load_config_from(jsonlib.dumps({"parallel": {"api_key_env": bad}}))
    assert cfg["parallel"]["api_key_env"] == cfgmod.PARALLEL_ENV_DEFAULT
    assert "⚠" in err


@pytest.mark.parametrize("good", ["PARALLEL_API_KEY", "MY_PARALLEL_KEY", "_private_key"])
def test_reasonable_api_key_env_names_accepted(load_config_from, good):
    import json as jsonlib

    cfg, err = load_config_from(jsonlib.dumps({"parallel": {"api_key_env": good}}))
    assert cfg["parallel"]["api_key_env"] == good
    assert "⚠" not in err


@pytest.mark.parametrize("bad", ['"oops"', "0", "-5", "true", "1.9", "Infinity"])
def test_bad_budget_chars_does_not_override_profile(load_config_from, bad):
    """回归：budget_chars 校验失败时回退到 15000，于是一个笔误把合法的
    `profile: compact` 覆盖成 (15000, custom)。回退目标必须是 None。"""
    cfg, err = load_config_from(
        '{"output": {"profile": "compact", "budget_chars": %s}}' % bad)
    assert cfg["output"]["budget_chars"] is None
    assert cfgmod.resolve_budget(cfg, None, None) == (8000, "compact")
    assert "⚠" in err


def test_valid_budget_chars_still_wins_over_profile(load_config_from):
    cfg, err = load_config_from('{"output": {"profile": "compact", "budget_chars": 4321}}')
    assert cfgmod.resolve_budget(cfg, None, None) == (4321, "custom")
    assert "⚠" not in err


def test_stale_key_is_cleared_when_none_resolves(monkeypatch):
    """回归：配了自定义 api_key_env 而该变量没设时，我们解析不出密钥、
    doctor 如实报告"回落 OAuth"，可父环境残留的旧 PARALLEL_API_KEY 仍被子进程读到——
    于是拿**另一个账号**的密钥去查询、计费、发送数据，诊断信息还说没在用密钥。"""
    import copy

    import sources

    monkeypatch.delenv("MY_PARALLEL_KEY", raising=False)
    monkeypatch.setenv("PARALLEL_API_KEY", "sk-STALE-OTHER-ACCOUNT")
    cfg = copy.deepcopy(cfgmod.DEFAULTS)
    cfg["parallel"]["api_key_env"] = "MY_PARALLEL_KEY"

    assert cfgmod.parallel_key(cfg) == ("", "none")
    assert cfgmod.PARALLEL_ENV_DEFAULT not in sources.parallel_env(cfg), \
        "解析不出密钥时，继承来的旧密钥必须被清掉"


def test_subprocess_key_always_matches_resolved_key(monkeypatch):
    """更强的不变量：子进程能用的密钥必须与 parallel_key() 这次解析出来的完全一致。"""
    import copy

    import sources

    monkeypatch.setenv("PARALLEL_API_KEY", "sk-STALE")
    for env_name, env_value, config_value, expect in [
        ("MY_KEY", "sk-CUSTOM", "", "sk-CUSTOM"),
        ("MY_KEY", None, "sk-FROM-CONFIG", "sk-FROM-CONFIG"),
        ("MY_KEY", None, "", None),
    ]:
        if env_value is None:
            monkeypatch.delenv(env_name, raising=False)
        else:
            monkeypatch.setenv(env_name, env_value)
        cfg = copy.deepcopy(cfgmod.DEFAULTS)
        cfg["parallel"]["api_key_env"] = env_name
        cfg["parallel"]["api_key"] = config_value
        resolved = cfgmod.parallel_key(cfg)[0] or None
        assert sources.parallel_env(cfg).get(cfgmod.PARALLEL_ENV_DEFAULT) == resolved == expect


@pytest.mark.parametrize("bad", [
    "sk-SENTINEL-user-pasted-the-key-here-123456",
    "sk-proj-AAAABBBBCCCCDDDD",
])
def test_bad_api_key_env_value_is_not_echoed(load_config_from, bad):
    """回归：非法 api_key_env 用 {value!r} 回显原值。
    而这个字段最可能被填错的内容**就是密钥本身**——"变量名"和"变量的值"
    是最容易混的一对。一旦回显，搜索、config show、doctor 每次都会把它
    写进终端、agent 上下文和 CI 日志。"""
    import json as jsonlib

    cfg, err = load_config_from(jsonlib.dumps({"parallel": {"api_key_env": bad}}))
    assert cfg["parallel"]["api_key_env"] == cfgmod.PARALLEL_ENV_DEFAULT
    assert bad not in err, "非法值被原样回显"
    assert "值已隐藏" in err and "长度" in err, "要给出足以定位问题的描述"


def test_dangerous_env_name_may_be_echoed(load_config_from):
    """指向 PATH/PYTHONWARNINGS 这类**已知系统变量名**时可以回显——
    那是个变量名不是密钥，说出来才好排查。"""
    cfg, err = load_config_from('{"parallel": {"api_key_env": "PATH"}}')
    assert "PATH" in err


def test_prompt_and_store_key_non_tty_points_to_gr_search(capsys, monkeypatch):
    """在非交互式终端下运行 set-key 时，提示的终端命令必须指向主入口 gr_search.py，
    而不是没有 CLI 行为的 config.py。"""
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    code = cfgmod.prompt_and_store_key("doubao")
    assert code == 2
    err = capsys.readouterr().err
    assert "gr_search.py config set-key doubao" in err
    assert "config.py config set-key" not in err
