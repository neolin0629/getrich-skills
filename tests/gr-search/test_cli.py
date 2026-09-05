#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编排层：输入校验、session 语义、缓存指纹、dry-run。

输入校验必须跑在**任何 source 调用之前**——非法参数是用户错误，
不该先把一个源打崩、再拿另一个源的钱去搜。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pytest

import config as cfgmod
import gr_search
import sources

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "skills" / "gr-search" / "scripts"


def _args(**overrides):
    base = dict(query="查询词", count=None, time_range=None, after_date=None,
                budget=None, source="both", type="web")
    base.update(overrides)
    return argparse.Namespace(**base)


# ---------------------------------------------------------------- 输入校验


@pytest.mark.parametrize("kwargs,hint", [
    pytest.param({"query": "   "}, "查询词", id="空查询"),
    pytest.param({"count": 0}, "count", id="count=0"),
    pytest.param({"count": -3}, "count", id="count负数"),
    pytest.param({"time_range": "OneCentury"}, "time-range", id="未知区间"),
    pytest.param({"time_range": "2026-01-01"}, "time-range", id="区间缺右端"),
    pytest.param({"time_range": "2026-09-01..2026-01-01"}, "time-range", id="起止倒序"),
    pytest.param({"time_range": "2026-13-40..2026-14-40"}, "time-range", id="非法日期"),
    pytest.param({"after_date": "2026-13-40"}, "after-date", id="非法after-date"),
    pytest.param({"after_date": "昨天"}, "after-date", id="非日期after-date"),
])
def test_invalid_args_are_rejected(kwargs, hint):
    message = gr_search.validate_search_args(_args(**kwargs))
    assert message and hint in message


@pytest.mark.parametrize("kwargs", [
    {}, {"count": 5}, {"time_range": "OneWeek"},
    {"time_range": "2026-01-01..2026-09-03"}, {"after_date": "2026-01-01"},
])
def test_valid_args_pass(kwargs):
    assert gr_search.validate_search_args(_args(**kwargs)) is None


@pytest.mark.parametrize("value,ok", [
    ("OneDay", True), ("OneWeek", True), ("OneMonth", True), ("OneYear", True),
    ("oneday", False), ("", False), ("2026-01-01..2026-01-01", True),
])
def test_time_range_vocabulary(value, ok):
    assert sources.valid_time_range(value) is ok


# ---------------------------------------------------------------- session 语义


def test_session_id_reused_when_request_actually_sent():
    """session_id 是客户端指定、由请求本身创建的关联 ID：
    真发了请求，我们生成的那个 ID 才在上游存在。"""
    results = [sources.SourceResult("parallel", docs=[])]
    assert gr_search.parallel_session_id(results, "生成的ID") == "生成的ID"


def test_session_id_comes_from_cache_on_hit():
    """缓存命中说明本次没发请求，得用缓存里记录的那次的 ID。"""
    results = [sources.SourceResult("parallel", docs=[], cached=True,
                                    raw={"session_id": "上一次的ID"})]
    assert gr_search.parallel_session_id(results, "生成的ID") == "上一次的ID"


@pytest.mark.parametrize("results,reason", [
    pytest.param([sources.SourceResult("doubao", docs=[])], "只调了豆包", id="未调用"),
    pytest.param([sources.SourceResult("parallel", error="boom")], "调用失败", id="失败"),
    pytest.param([], "一个源都没调", id="空"),
])
def test_session_id_is_none_when_no_upstream_session(results, reason):
    """写一个从未创建过的 session 进落盘 JSON，后续 fetch 会拿它去串上下文——
    串的是一个不存在的东西。"""
    assert gr_search.parallel_session_id(results, "生成的ID") is None, reason


def test_cached_result_without_session_id_yields_none():
    results = [sources.SourceResult("parallel", docs=[], cached=True, raw={})]
    assert gr_search.parallel_session_id(results, "生成的ID") is None


# ---------------------------------------------------------------- 缓存指纹


def _fingerprint(**overrides):
    opts = {"mode": "basic"}
    opts.update(overrides.pop("opts", {}))
    return sources._parallel_cache_fingerprint(
        overrides.get("objective", "目标"),
        overrides.get("queries", ["甲", "乙"]),
        opts,
        cfgmod.DEFAULTS["parallel"],
    )


def test_session_id_excluded_from_cache_key():
    """session_id 每次调用都不同，纳入指纹会让 30 分钟缓存永远不命中。"""
    assert _fingerprint(opts={"session_id": "run-1"}) == _fingerprint(opts={"session_id": "run-2"})


def test_keyword_order_included_in_cache_key():
    """关键词顺序会影响 Parallel 的检索结果，排序后不同的请求会错误地共用缓存。"""
    assert _fingerprint(queries=["甲", "乙"]) != _fingerprint(queries=["乙", "甲"])


@pytest.mark.parametrize("opts", [
    {"mode": "advanced"}, {"count": 25}, {"sites": ["a.com"]},
    {"block_hosts": ["b.com"]}, {"after_date": "2026-01-01"},
])
def test_wire_affecting_options_included_in_cache_key(opts):
    assert _fingerprint(opts=opts) != _fingerprint()


def test_blank_keywords_normalized_out():
    assert _fingerprint(queries=["甲", "  ", "乙"]) == _fingerprint(queries=["甲", "乙"])


# ---------------------------------------------------------------- dry-run 子进程


def _run(*argv, tmp_home):
    """在干净的 HOME 下跑真实 CLI：CONFIG_DIR 在导入时由 Path.home() 决定，
    换 HOME 就能保证用例读不到、也写不脏用户的真实配置。"""
    env = dict(os.environ, HOME=str(tmp_home))
    env.pop("DOUBAO_SEARCH_API_KEY", None)
    env.pop("PARALLEL_API_KEY", None)
    return subprocess.run([sys.executable, str(SCRIPTS / "gr_search.py"), *argv],
                          capture_output=True, text=True, env=env, timeout=60)


@pytest.mark.parametrize("source", ["doubao", "parallel", "both"])
def test_dry_run_prints_request_without_calling(tmp_path, source):
    """--dry-run 用来核对豆包的 PascalCase 字段名，必须零网络、零额度。
    历史上 HTTP 通路因为直接下标取 request["cmd"] 抛过 KeyError。"""
    proc = _run("search", "测试查询", "--dry-run", "--source", source, tmp_home=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()


def test_dry_run_does_not_write_config(tmp_path):
    _run("search", "测试", "--dry-run", tmp_home=tmp_path)
    assert not (tmp_path / ".config" / "gr-search" / "config.json").exists()


@pytest.mark.parametrize("argv,code", [
    (["search", "  ", "--dry-run"], 2),
    (["search", "测试", "--count", "0", "--dry-run"], 2),
    (["search", "测试", "--time-range", "OneCentury", "--dry-run"], 2),
    (["fetch", "https://e.com", "--max-chars", "0"], 2),
    (["fetch", "https://e.com", "--max-chars", "-1"], 2),
])
def test_invalid_cli_input_exits_2(tmp_path, argv, code):
    assert _run(*argv, tmp_home=tmp_path).returncode == code


def test_config_path_and_show_work_on_fresh_machine(tmp_path):
    """换机器后的第一步不能崩在"配置文件还不存在"上。"""
    assert _run("config", "path", tmp_home=tmp_path).returncode == 0
    assert _run("config", "show", tmp_home=tmp_path).returncode == 0


# ---------------------------------------------------------------- 关键词规范化


@pytest.mark.parametrize("raw,expect", [
    (["a", "b"], ["a", "b"]),
    (["", "a", "b"], ["a", "b"]),
    (["  a  ", "b"], ["a", "b"]),
    ([None, "a"], ["a"]),
    (["a", "b", "c", "d", "e", "f"], ["a", "b", "c", "d", "e"]),   # 上游上限 5
    ([], []),
    (None, []),
])
def test_normalize_keywords(raw, expect):
    assert sources.normalize_keywords(raw) == expect


def test_cli_http_and_fingerprint_agree_on_keywords():
    """回归：["", "a".."e"] 与 ["a".."e"] 指纹相同，但 CLI 实际发的是
    「空串 + a..d」和「a..e」——两个不同的请求错误地共用了同一份缓存。

    根因是三处各写各的规范化。现在必须共用同一个函数。
    """
    cfg = cfgmod.DEFAULTS
    noisy, clean = ["", "a", "b", "c", "d", "e"], ["a", "b", "c", "d", "e"]

    def cli_keywords(queries):
        cmd = sources.build_parallel_cmd(cfg, "o", queries, {}, "/tmp/x")
        return [cmd[i + 1] for i, token in enumerate(cmd) if token == "-q"]

    def http_keywords(queries):
        return sources.build_parallel_http_payload(cfg, "o", queries, {})["search_queries"]

    def fingerprint_keywords(queries):
        return sources._parallel_cache_fingerprint("o", queries, {}, cfg["parallel"])["queries"]

    for queries in (noisy, clean):
        assert cli_keywords(queries) == http_keywords(queries) == fingerprint_keywords(queries)


def test_blank_padded_keywords_do_not_share_cache_with_full_set():
    """指纹相同就必须是同一个请求；请求不同，指纹就得不同。"""
    cfg = cfgmod.DEFAULTS["parallel"]
    six = ["a", "b", "c", "d", "e", "f"]
    five = ["a", "b", "c", "d", "e"]
    assert (sources._parallel_cache_fingerprint("o", six, {}, cfg)
            == sources._parallel_cache_fingerprint("o", five, {}, cfg)), "第 6 个词根本没发出去"


# ---------------------------------------------------------------- 日期严格性


@pytest.mark.parametrize("value", ["20260904", "2026-W01-1", "2026-9-4", "2026/09/04",
                                   "2026-13-45", "", "今天"])
def test_after_date_rejects_non_iso_forms(value):
    """date.fromisoformat 从 3.11 起还接受 20260904 和 2026-W01-1，
    而报错文案和上游契约都只认 YYYY-MM-DD。"""
    assert not sources.valid_date(value)


@pytest.mark.parametrize("value", ["2026-09-04", "2026-01-01", "2024-02-29"])
def test_after_date_accepts_iso(value):
    assert sources.valid_date(value)


def test_time_range_span_still_works():
    assert sources.valid_time_range("2026-01-01..2026-09-03")
    assert not sources.valid_time_range("20260101..20260903")


# ---------------------------------------------------------------- 时效判定覆盖全部查询


@pytest.mark.parametrize("kwargs", [
    pytest.param({"q": "北京今日最高温"}, id="--q"),
    pytest.param({"objective": "current Beijing weather"}, id="--objective"),
    pytest.param({"pq": ["latest weather"]}, id="--pq"),
])
def test_freshness_covers_every_query_actually_sent(kwargs, monkeypatch, tmp_path):
    """回归：只看位置参数。SKILL.md 明确建议复杂问题拆成 --q/--objective/--pq，
    位置参数写「北京天气」、--q 写「北京今日最高温」正是推荐用法。"""
    import fusion
    import render

    captured = {}

    def fake_doubao(cfg, query, opts, dry_run=False):
        captured["cache_ttl"] = opts.get("cache_ttl")
        return sources.SourceResult("doubao", docs=[])

    monkeypatch.setattr(sources, "doubao_search", fake_doubao)
    monkeypatch.setattr(sources, "parallel_search",
                        lambda *a, **k: sources.SourceResult("parallel", docs=[]))
    monkeypatch.setattr(render, "render", lambda **kw: "")

    base = dict(query="北京天气", q=None, objective=None, pq=None, source="both", type="web",
                profile=None, budget=None, count=None, fresh=False, time_range=None,
                after_date=None, sites=None, block_hosts=None, industry=None,
                authoritative=False, need_content=False, need_url=False, mode=None,
                no_cache=False, no_dump=True, force_all=False, dry_run=False, json=False)
    base.update(kwargs)
    cfg = cfgmod.load_config.__globals__["DEFAULTS"]
    import copy
    gr_search.run_search(argparse.Namespace(**base), copy.deepcopy(cfg))
    assert captured["cache_ttl"] == 120, "时效诉求写在 --q/--objective/--pq 里就被忽略了"


def test_plain_query_keeps_long_ttl(monkeypatch):
    import copy

    import render

    captured = {}
    monkeypatch.setattr(sources, "doubao_search",
                        lambda cfg, q, opts, dry_run=False: (
                            captured.update(cache_ttl=opts.get("cache_ttl")),
                            sources.SourceResult("doubao", docs=[]))[1])
    monkeypatch.setattr(render, "render", lambda **kw: "")
    args = argparse.Namespace(query="Python 装饰器原理", q=None, objective=None, pq=None,
                              source="doubao", type="web", profile=None, budget=None, count=None,
                              fresh=False, time_range=None, after_date=None, sites=None,
                              block_hosts=None, industry=None, authoritative=False,
                              need_content=False, need_url=False, mode=None, no_cache=False,
                              no_dump=True, force_all=False, dry_run=False, json=False)
    gr_search.run_search(args, copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"]))
    assert captured["cache_ttl"] is None


# ---------------------------------------------------------------- 参数组合


@pytest.mark.parametrize("kwargs,hint", [
    pytest.param({"budget": 0}, "budget", id="budget=0"),
    pytest.param({"budget": -5}, "budget", id="budget负数"),
    pytest.param({"source": "parallel", "type": "image"}, "image", id="parallel+图片"),
])
def test_silently_useless_combinations_are_rejected(kwargs, hint):
    """这两个组合过去都是静默降级：--budget 0 回退到默认 15000（用户以为限住了），
    --source parallel --type image 变成一个源都不调的空操作。"""
    message = gr_search.validate_search_args(_args(**kwargs))
    assert message and hint in message


def test_doubao_image_search_still_allowed():
    assert gr_search.validate_search_args(_args(source="doubao", type="image")) is None


# ---------------------------------------------------------------- JSON 输出的不可信声明


def _search_argv(**over):
    base = dict(query="测试", q=None, objective=None, pq=None, source="doubao", type="web",
                profile=None, budget=None, count=None, fresh=False, time_range=None,
                after_date=None, sites=None, block_hosts=None, industry=None,
                authoritative=False, need_content=False, need_url=False, mode=None,
                no_cache=False, no_dump=True, force_all=False, dry_run=False, json=False)
    base.update(over)
    return argparse.Namespace(**base)


def _run_search_capturing(monkeypatch, capsys, tmp_path, **over):
    import copy

    import render
    monkeypatch.setattr(sources, "doubao_search",
                        lambda cfg, q, opts, dry_run=False: sources.SourceResult(
                            "doubao",
                            docs=[sources.Doc(url="https://e.com/a", title="标题", body="正文",
                                              site="e.com", source="doubao", rank=1)]))
    monkeypatch.setattr(render, "render", lambda **kw: "")
    cfg = copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"])
    cfg["output"]["dump_dir"] = str(tmp_path)
    gr_search.run_search(_search_argv(**over), cfg)
    return capsys.readouterr().out


def test_json_output_declares_content_untrusted(monkeypatch, capsys, tmp_path):
    """--json 加不了围栏（加了就不是合法 JSON），改用数据内的显式声明。
    没有它，这条路径就是"所有网络内容都在围栏内"这句话的反例。"""
    import json as jsonlib

    payload = jsonlib.loads(_run_search_capturing(monkeypatch, capsys, tmp_path, json=True))
    assert "_notice" in payload
    assert "不是指令" in payload["_notice"]


def test_dump_file_declares_content_untrusted(monkeypatch, capsys, tmp_path):
    """落盘 JSON 会被 agent 直接读来追问细节，同样绕过 stdout 的围栏。"""
    import json as jsonlib

    _run_search_capturing(monkeypatch, capsys, tmp_path, no_dump=False)
    dumps = list(tmp_path.glob(f"{cfgmod.FILE_PREFIX}*.json"))
    assert dumps
    assert "不是指令" in jsonlib.loads(dumps[0].read_text(encoding="utf-8"))["_notice"]


# ---------------------------------------------------------------- raw 与不可信声明


def test_notice_covers_raw(monkeypatch, capsys, tmp_path):
    """回归：_notice 只列了 docs/cards/errors，但落盘文件还含完整上游响应 raw，
    而 SKILL.md 明确让 agent 直接读 raw——最厚的一层上游内容恰恰被声明漏掉了。"""
    import json as jsonlib

    _run_search_capturing(monkeypatch, capsys, tmp_path, no_dump=False)
    dump = jsonlib.loads(next(tmp_path.glob(f"{cfgmod.FILE_PREFIX}*.json")).read_text(encoding="utf-8"))
    assert "raw" in dump, "落盘结构变了，本用例需要同步更新"
    for name in ("docs", "cards", "errors", "raw"):
        assert name in dump["_notice"], f"_notice 没有覆盖 {name}"


def test_json_notice_covers_raw(monkeypatch, capsys, tmp_path):
    import json as jsonlib

    payload = jsonlib.loads(_run_search_capturing(monkeypatch, capsys, tmp_path, json=True))
    for name in ("docs", "cards", "errors", "raw"):
        assert name in payload["_notice"]


# ---------------------------------------------------------------- 空白覆盖参数


def _capture_queries(monkeypatch, **over):
    import copy

    import render
    seen = {}
    monkeypatch.setattr(sources, "doubao_search",
                        lambda cfg, q, opts, dry_run=False: (
                            seen.update(doubao=q), sources.SourceResult("doubao", docs=[]))[1])
    monkeypatch.setattr(sources, "parallel_search",
                        lambda cfg, o, kw, opts, dry_run=False: (
                            seen.update(objective=o, keywords=kw),
                            sources.SourceResult("parallel", docs=[]))[1])
    monkeypatch.setattr(render, "render", lambda **kw: "")
    gr_search.run_search(_search_argv(source="both", force_all=True, **over),
                         copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"]))
    return seen


@pytest.mark.parametrize("blank", ["   ", "\t", "\n", ""])
def test_blank_override_falls_back_to_positional(monkeypatch, blank):
    """回归：`--q "   "` 让豆包收到 Query=""，位置参数里那个有效查询被白白丢掉。
    空白是空白，不是内容。"""
    seen = _capture_queries(monkeypatch, query="有效查询", q=blank, objective=blank)
    assert seen["doubao"] == "有效查询"
    assert seen["objective"] == "有效查询"


def test_real_override_still_wins(monkeypatch):
    seen = _capture_queries(monkeypatch, query="位置参数", q="豆包短语", objective="Parallel 目标")
    assert seen["doubao"] == "豆包短语"
    assert seen["objective"] == "Parallel 目标"


def test_override_is_stripped(monkeypatch):
    seen = _capture_queries(monkeypatch, query="位置参数", q="  豆包短语  ")
    assert seen["doubao"] == "豆包短语"


# ---------------------------------------------------------------- 时效判定的精确范围


def _cache_ttl(monkeypatch, **over):
    import copy

    import render
    seen = {}
    monkeypatch.setattr(sources, "doubao_search",
                        lambda cfg, q, opts, dry_run=False: (
                            seen.setdefault("ttl", opts.get("cache_ttl")),
                            sources.SourceResult("doubao", docs=[]))[1])
    monkeypatch.setattr(sources, "parallel_search",
                        lambda cfg, o, kw, opts, dry_run=False: (
                            seen.setdefault("ttl", opts.get("cache_ttl")),
                            sources.SourceResult("parallel", docs=[]))[1])
    monkeypatch.setattr(render, "render", lambda **kw: "")
    gr_search.run_search(_search_argv(force_all=True, **over),
                         copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"]))
    return seen["ttl"]


def test_sixth_keyword_is_not_scanned(monkeypatch):
    """只发前 5 个 --pq，第 6 个不该触发短 TTL——它根本没发出去，
    白白 miss 一次缓存就是白白多花一次钱。"""
    assert _cache_ttl(monkeypatch, source="parallel",
                      pq=["a", "b", "c", "d", "e", "今天最新行情"]) is None


def test_truncated_doubao_query_tail_is_not_scanned(monkeypatch):
    """--q 超过 100 字符的部分会被豆包截掉，截掉的尾巴同样不该触发短 TTL。"""
    assert _cache_ttl(monkeypatch, source="doubao", q="填充" * 60 + "今天") is None


def test_disabled_source_params_are_not_scanned(monkeypatch):
    """--source doubao 时 --objective/--pq 根本不发，不该影响 TTL。"""
    assert _cache_ttl(monkeypatch, source="doubao", objective="latest news today") is None


@pytest.mark.parametrize("over", [
    pytest.param({"source": "doubao", "q": "北京今日最高温"}, id="--q"),
    pytest.param({"source": "parallel", "objective": "current Beijing weather"}, id="--objective"),
    pytest.param({"source": "parallel", "pq": ["latest weather"]}, id="--pq"),
    pytest.param({"source": "both", "query": "北京今日天气"}, id="位置参数"),
])
def test_sent_queries_do_trigger_short_ttl(monkeypatch, over):
    assert _cache_ttl(monkeypatch, **over) == 120


# ---------------------------------------------------------------- 尾随换行


@pytest.mark.parametrize("value", ["2026-09-04\n", "2026-09-04\r\n", " 2026-09-04"])
def test_date_rejects_trailing_whitespace(value):
    """`$` 也匹配串尾换行之前的位置，所以 `^...$` + match() 会放过
    "2026-01-01..2026-09-04\\n" 并原样发给上游。改用 fullmatch。"""
    assert not sources.valid_date(value)


@pytest.mark.parametrize("value", ["2026-01-01..2026-09-04\n", "OneWeek\n", "OneWeek "])
def test_time_range_rejects_trailing_whitespace(value):
    assert not sources.valid_time_range(value)


# ---------------------------------------------------------------- 两条通路的请求等价性


def _cli_keywords(cfg, objective, queries, opts=None):
    cmd = sources.build_parallel_cmd(cfg, objective, queries, opts or {}, "/tmp/x")
    return [cmd[i + 1] for i, token in enumerate(cmd) if token == "-q"]


@pytest.mark.parametrize("queries", [[], None, ["甲"], ["甲", "乙"], ["", "甲"], ["a"] * 8])
def test_both_transports_send_same_search_queries(queries):
    """回归：无 --pq 时 HTTP 用 objective 补 search_queries、CLI 不传 -q，
    于是同一个逻辑查询在装了 parallel-cli 的机器上和没装的机器上发的是不同请求。
    transport 走 auto 时用户根本不知道自己走的是哪条。"""
    cfg = cfgmod.DEFAULTS
    http = sources.build_parallel_http_payload(cfg, "北京天气怎么样", queries, {})["search_queries"]
    assert _cli_keywords(cfg, "北京天气怎么样", queries) == http


def test_cache_key_is_transport_independent():
    """指纹相同就必须共用缓存。命名空间带 transport 的话，装一下 parallel-cli
    或把 transport 从 auto 改成 http，整个缓存就作废重付一遍。"""
    cfg = cfgmod.DEFAULTS
    fingerprint = sources._parallel_cache_fingerprint("目标", ["甲"], {"mode": "basic"},
                                                     cfg["parallel"])
    key = cfgmod.cache_key(sources.PARALLEL_CACHE_NS, fingerprint)
    assert "cli" not in sources.PARALLEL_CACHE_NS and "http" not in sources.PARALLEL_CACHE_NS
    assert key == cfgmod.cache_key(sources.PARALLEL_CACHE_NS, fingerprint)


def test_fingerprint_records_resolved_queries():
    """指纹要记最终发出去的那份，而不是原始入参——否则"无 --pq" 和
    "--pq 恰好等于 objective" 会被算成两个请求。"""
    cfg = cfgmod.DEFAULTS["parallel"]
    assert (sources._parallel_cache_fingerprint("北京天气", [], {}, cfg)["queries"]
            == ["北京天气"])


def test_both_transports_agree_on_domain_policy():
    """官方语义：include_domains 非空时 exclude_domains 被忽略。
    两条通路要用同一套取舍，请求才真正等价。"""
    cfg = cfgmod.DEFAULTS
    opts = {"sites": ["a.com"], "block_hosts": ["b.com"]}
    cmd = sources.build_parallel_cmd(cfg, "o", ["甲"], opts, "/tmp/x")
    policy = sources.build_parallel_http_payload(
        cfg, "o", ["甲"], opts)["advanced_settings"]["source_policy"]
    assert "--exclude-domains" not in cmd
    assert "exclude_domains" not in policy
    assert "--include-domains" in cmd and "include_domains" in policy


def test_resolve_search_queries_caps_objective_fallback():
    assert len(sources.resolve_search_queries("很长的目标" * 100, [])[0]) <= 120


# ---------------------------------------------------------------- 上游告警传递


@pytest.mark.parametrize("body,expect", [
    pytest.param({"warnings": ["降级到 basic"]}, "降级到 basic", id="顶层字符串"),
    pytest.param({"warnings": [{"type": "spec_validation_warning", "message": "字段被忽略"}]},
                 "spec_validation_warning", id="顶层对象"),
    pytest.param({"meta": {"input_validation_warnings": [{"code": "x", "detail": "d"}]}},
                 "x", id="嵌在 meta 里"),
    pytest.param({"results": []}, None, id="没有告警"),
    pytest.param({"warnings": "不是列表"}, None, id="类型异常不得抛"),
    pytest.param(None, None, id="body 不是 dict"),
])
def test_parallel_warnings_extraction(body, expect):
    got = sources.parallel_warnings(body)
    if expect is None:
        assert got == []
    else:
        assert any(expect in w for w in got)


def test_source_result_carries_warnings():
    """warnings 不是 error——请求成功了——但可能意味着请求没被完整执行。"""
    assert sources.SourceResult("parallel").warnings == []
    assert sources.SourceResult("parallel", warnings=["w"]).warnings == ["w"]


def test_upstream_warnings_reach_stdout(monkeypatch, capsys, tmp_path):
    """回归：告警只存在 raw 里，正常输出和 --json 都看不到；
    加了 --no-dump 更是连翻都没处翻。"""
    import copy

    import render
    monkeypatch.setattr(sources, "doubao_search",
                        lambda cfg, q, opts, dry_run=False: sources.SourceResult("doubao", docs=[]))
    monkeypatch.setattr(sources, "parallel_search",
                        lambda cfg, o, kw, opts, dry_run=False: sources.SourceResult(
                            "parallel", docs=[], warnings=["spec_validation_warning: 字段被忽略"]))
    captured = {}
    monkeypatch.setattr(render, "render", lambda **kw: captured.update(errors=kw["errors"]) or "")
    gr_search.run_search(_search_argv(source="both", force_all=True, no_dump=True),
                         copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"]))
    assert any("告警" in e and "spec_validation_warning" in e for e in captured["errors"])


def test_upstream_warnings_reach_json(monkeypatch, capsys, tmp_path):
    import copy
    import json as jsonlib

    import render
    monkeypatch.setattr(sources, "doubao_search",
                        lambda cfg, q, opts, dry_run=False: sources.SourceResult(
                            "doubao", docs=[], warnings=["降级提示"]))
    monkeypatch.setattr(render, "render", lambda **kw: "")
    gr_search.run_search(_search_argv(source="doubao", json=True, no_dump=True),
                         copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"]))
    payload = jsonlib.loads(capsys.readouterr().out)
    assert any("降级提示" in e for e in payload["errors"])


# ---------------------------------------------------------------- --time-range 与短 TTL


@pytest.mark.parametrize("time_range,expect", [
    pytest.param("OneDay", 120, id="OneDay=日级"),
    pytest.param("OneWeek", 120, id="OneWeek"),
    pytest.param("OneMonth", 120, id="OneMonth"),
    pytest.param("OneYear", None, id="OneYear跨度太大"),
    pytest.param("2026-01-01..2026-09-03", None, id="显式日期区间多为历史查询"),
    pytest.param(None, None, id="未指定"),
])
def test_time_range_drives_cache_ttl(monkeypatch, time_range, expect):
    """回归：`天气 --time-range OneDay` 仍可命中 30 分钟前的缓存。
    显式的相对时间范围是比任何关键词都明确的时效诉求。"""
    assert _cache_ttl(monkeypatch, query="天气", source="doubao",
                      time_range=time_range) == expect


def test_one_day_is_strong_fresh():
    """OneDay 对应「今天」，陈旧内容要被压低而不只是不加分。"""
    import fusion

    assert fusion.time_range_is_strong_fresh("OneDay")
    assert not fusion.time_range_is_strong_fresh("OneWeek")
    assert fusion.time_range_is_fresh("OneWeek")


# ---------------------------------------------------------------- 指纹不记被忽略的字段


def test_ignored_block_hosts_excluded_from_fingerprint():
    """include 非空时上游忽略 exclude，两个请求发出去一模一样，
    却因为指纹不同各占一份缓存——白白多付一次钱。"""
    cfg = cfgmod.DEFAULTS["parallel"]
    with_block = sources._parallel_cache_fingerprint(
        "o", ["a"], {"sites": ["x.com"], "block_hosts": ["y.com"]}, cfg)
    without = sources._parallel_cache_fingerprint("o", ["a"], {"sites": ["x.com"]}, cfg)
    assert with_block == without


def test_block_hosts_still_counted_without_sites():
    cfg = cfgmod.DEFAULTS["parallel"]
    assert (sources._parallel_cache_fingerprint("o", ["a"], {"block_hosts": ["y.com"]}, cfg)
            != sources._parallel_cache_fingerprint("o", ["a"], {}, cfg))


@pytest.mark.parametrize("cached", [False, True])
def test_http_transport_attaches_warnings_to_result(monkeypatch, tmp_path, cached):
    """打在真实的 _parallel_search_http 上，而不是把 parallel_search 整个替掉——
    否则"SourceResult 忘了带 warnings"这类缺陷根本不会被执行到。"""
    import copy

    body = {"results": [], "warnings": [{"type": "spec_validation_warning", "message": "忽略了字段"}]}
    monkeypatch.setattr(sources, "_post_parallel", lambda *a, **k: dict(body))
    cfg = copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"])
    cfg["cache"]["dir"] = str(tmp_path)
    opts = {"mode": "basic"}
    if cached:
        sources._parallel_search_http(cfg, "目标", ["甲"], opts)      # 先写入缓存
        monkeypatch.setattr(sources, "_post_parallel",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("不该再发请求")))
    result = sources._parallel_search_http(cfg, "目标", ["甲"], opts)
    assert result.cached is cached
    assert any("spec_validation_warning" in w for w in result.warnings), \
        "缓存命中时也要带上告警——告警是那次响应的一部分"


def test_cli_transport_attaches_warnings_to_result(monkeypatch, tmp_path):
    """CLI 与 HTTP 打的是同一个接口，告警也必须同样传出去。"""
    import copy
    import json as jsonlib

    body = {"results": [], "warnings": ["检索降级"]}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        # CLI 把结果写进 -o 指定的文件，不是 stdout——照着真实行为造，
        # 否则测的只是"我以为它怎么工作"
        out_path = cmd[cmd.index("-o") + 1]
        Path(out_path).write_text(jsonlib.dumps(body), encoding="utf-8")
        return _Proc()

    monkeypatch.setattr(sources.shutil, "which", lambda _: "/usr/bin/parallel-cli")
    monkeypatch.setattr(sources.subprocess, "run", fake_run)
    cfg = copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"])
    cfg["cache"]["dir"] = str(tmp_path)
    cfg["parallel"]["transport"] = "cli"
    result = sources.parallel_search(cfg, "目标", ["甲"], {"mode": "basic"})
    assert not result.error, result.error
    assert any("检索降级" in w for w in result.warnings)


def test_custom_env_name_still_reaches_the_cli(monkeypatch):
    """回归：`parallel_env` 用"来源是不是 env"而不是"注入的变量名对不对"做判断。
    配了自定义 api_key_env 并 export 之后 origin 是 env、于是跳过注入，
    而 CLI 读的仍是 PARALLEL_API_KEY——环境里残留一把旧的，子进程就拿旧密钥鉴权，
    `config show` 显示的却是新的那把，两边对不上还查不出来。
    """
    import copy

    monkeypatch.setenv("MY_PARALLEL_KEY", "sk-CURRENT")
    monkeypatch.setenv("PARALLEL_API_KEY", "sk-STALE")
    cfg = copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"])
    cfg["parallel"]["api_key_env"] = "MY_PARALLEL_KEY"

    shown, _origin = cfgmod.parallel_key(cfg)
    injected = sources.parallel_env(cfg)[cfgmod.PARALLEL_ENV_DEFAULT]
    assert shown == "sk-CURRENT"
    assert injected == shown, "config show 显示的和子进程实际用的不是同一把密钥"


def test_env_sourced_default_name_is_passed_through(monkeypatch):
    """密钥本来就在官方变量里时，注入后仍然是它，不能被覆盖成别的。"""
    import copy

    monkeypatch.setenv("PARALLEL_API_KEY", "sk-FROM-ENV")
    cfg = copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"])
    assert sources.parallel_env(cfg)[cfgmod.PARALLEL_ENV_DEFAULT] == "sk-FROM-ENV"


def test_fresh_flag_help_matches_behaviour():
    """回归：--fresh 的 help 写"压低陈旧内容"，但单独用 --fresh 时 strong_fresh 为假，
    _recency_bonus(strong=False) 永远不返回负值。文案必须与行为一致。"""
    import fusion

    assert fusion._recency_bonus("2015-01-01", strong=False) >= 0
    assert fusion._recency_bonus("2015-01-01", strong=True) < 0

    conf = gr_search.build_parser()._subparsers._group_actions[0].choices["search"]
    fresh_help = next(a.help for a in conf._actions if "--fresh" in a.option_strings)
    assert "压低陈旧内容需" in fresh_help, "help 仍在承诺 --fresh 单独就能降权"


def test_fresh_flag_alone_does_not_demote(monkeypatch):
    """行为侧也钉一下：--fresh 只加权，不降权。"""
    import copy

    import fusion

    old = fusion.Merged(url="https://a.com", title="a", body="", site="a",
                        sources={"doubao": 1}, publish="2015-01-01")
    cfg = copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"])
    ranked = fusion.rank([old], cfg, fresh=True, strong_fresh=False)
    assert ranked[0].score >= 0


# ---------------------------------------------------------------- 以 - 开头的 objective


@pytest.mark.parametrize("objective", ["--help", "--starts-with-dash", "-", "-q", "--json"])
def test_dash_leading_objective_is_not_parsed_as_option(objective):
    """回归：objective 直接跟在 `parallel-cli search` 后面，以 `-` 开头时被 click
    当成选项——`--help` 让 CLI 打印帮助后**正常退出**却不写结果文件，我们随后崩在
    JSONDecodeError 上；`-` 被当成读 stdin 的哨兵。HTTP 通路没这问题，
    于是 auto 模式下行为取决于本机装没装 CLI。

    修法是把 objective 放最后并用 `--` 终止选项解析
    （已用 CLI 自带的 click 8.5 验证过这个行为，不是照惯例假设）。
    """
    cmd = sources.build_parallel_cmd(cfgmod.DEFAULTS, objective, ["甲"], {}, "/tmp/x")
    assert cmd[-2:] == ["--", objective]
    assert cmd.index("--") == len(cmd) - 2, "`--` 之后只能剩 objective"


def test_dash_objective_survives_click_parsing():
    """不止断言我们拼了 `--`，还要断言 click 真的按位置参数解析它。
    用 parallel-cli 自带的那份 click 复刻同样的参数签名。"""
    import click
    from click.testing import CliRunner

    @click.command()
    @click.argument("objective", required=False)
    @click.option("-q", "queries", multiple=True)
    @click.option("--json", "as_json", is_flag=True)
    @click.option("-o", "out")
    def fake_search(objective, queries, as_json, out):
        click.echo(objective or "")

    cmd = sources.build_parallel_cmd(cfgmod.DEFAULTS, "--help", ["甲"], {}, "/tmp/x")
    # 去掉可执行名与子命令，只留参数；再剔除本地 fake 不认识的选项
    known = {"-q", "--json", "-o"}
    argv, skip = [], False
    for i, token in enumerate(cmd[2:]):
        if skip:
            argv.append(token); skip = False; continue
        if token == "--":
            argv.extend(cmd[2:][i:]); break
        if token in known:
            argv.append(token); skip = token != "--json"
    result = CliRunner().invoke(fake_search, argv)
    assert result.exit_code == 0
    assert result.output.strip() == "--help", "objective 仍被当成选项解析"


def test_normal_objective_still_works():
    cmd = sources.build_parallel_cmd(cfgmod.DEFAULTS, "北京天气怎么样", ["甲"], {}, "/tmp/x")
    assert cmd[-1] == "北京天气怎么样"
    assert cmd[0:2] == ["parallel-cli", "search"]


def test_dash_objective_does_not_change_http_payload():
    """HTTP 通路本来就没问题，修 CLI 不能把它带歪。"""
    payload = sources.build_parallel_http_payload(cfgmod.DEFAULTS, "--help", ["甲"], {})
    assert payload["objective"] == "--help"
