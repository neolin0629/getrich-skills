#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch 子命令。

`--max-chars` 是**整个 stdout** 的预算而不只是正文预算——它存在的理由就是护住
上下文窗口。历史上标题和 URL 不计入也不限长，`--max-chars 1` 能输出两万字符。

同时守住反方向：页数多、预算紧时不能退化成一串只有标题和链接的空壳，
正文才是 fetch 唯一的产出。
"""

from __future__ import annotations

import argparse

import pytest

import gr_search
import render
from conftest import HUGE, INJECT, INJECT_SENTENCE, fence_counts, outside_fence


def run_fetch(capsys, max_chars=12000, session_id=None):
    args = argparse.Namespace(urls=["https://e.com"], objective=None,
                              max_chars=max_chars, session_id=session_id)
    code = gr_search.run_fetch(args, {})
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------- 总预算


@pytest.mark.parametrize("pages_n", [1, 20])
def test_huge_title_and_url_cannot_blow_max_chars(fake_extract, page, capsys, pages_n):
    """回归：1 页 → 20080 字符、20 页 → 400547 字符。"""
    fake_extract([page(i, title=HUGE, url=f"https://e.com/{HUGE}") for i in range(pages_n)])
    _, out, _ = run_fetch(capsys, max_chars=1)
    assert len(out.rstrip()) < 1000, f"输出 {len(out)} 字符"


@pytest.mark.parametrize("max_chars", [500, 3000, 12000])
@pytest.mark.parametrize("pages_n", [1, 5, 20])
def test_output_fits_max_chars(fake_extract, page, capsys, max_chars, pages_n):
    fake_extract([page(i) for i in range(pages_n)])
    _, out, _ = run_fetch(capsys, max_chars=max_chars)
    assert len(out.rstrip()) <= max_chars, f"超支 {len(out.rstrip()) - max_chars} 字符"


@pytest.mark.parametrize("max_chars", [500, 3000, 12000])
@pytest.mark.parametrize("pages_n", [1, 5, 20])
def test_body_is_never_entirely_dropped(fake_extract, page, capsys, max_chars, pages_n):
    """回归：20 页 / --max-chars 500 曾输出 20 个只有标题和链接的空壳。"""
    fake_extract([page(i) for i in range(pages_n)])
    _, out, _ = run_fetch(capsys, max_chars=max_chars)
    assert "正文内容" in out, "正文被完全挤掉"


def test_dropped_pages_are_announced(fake_extract, page, capsys):
    fake_extract([page(i) for i in range(20)])
    _, out, _ = run_fetch(capsys, max_chars=1000)
    assert "未展开" in out


def test_first_page_always_rendered(fake_extract, page, capsys):
    """预算再小也不能输出一对空围栏。"""
    fake_extract([page(1)])
    _, out, _ = run_fetch(capsys, max_chars=1)
    assert "页面标题 1" in out


# ---------------------------------------------------------------- 围栏


@pytest.mark.parametrize("field", ["title", "content", "url", "publish"])
def test_page_fields_cannot_forge_fence(fake_extract, page, capsys, field):
    """抓来的整页正文是不可信内容里最"厚"的一种。"""
    fake_extract([page(1, **{field: INJECT})])
    _, out, _ = run_fetch(capsys, max_chars=8000)
    assert fence_counts(out) == (1, 1)
    assert INJECT_SENTENCE not in outside_fence(out)


def test_fatal_error_is_fenced(fake_extract, capsys):
    """错误串里嵌着上游响应片段，不能裸奔输出。"""
    fake_extract([], error=f"HTTP 500: {INJECT}")
    code, _, err = run_fetch(capsys)
    assert code == 1
    assert fence_counts(err) == (1, 1)
    assert INJECT_SENTENCE not in outside_fence(err)


# ---------------------------------------------------------------- 参数与告警


@pytest.mark.parametrize("max_chars", [0, -1])
def test_invalid_max_chars_exits_2(fake_extract, page, capsys, max_chars):
    fake_extract([page(1)])
    code, _, _ = run_fetch(capsys, max_chars=max_chars)
    assert code == 2


def test_warnings_print_before_fatal_error(fake_extract, capsys):
    """整体失败时也可能已经有话要说（比如 URL 被截到 20 个），
    告警必须先打，否则用户只看到失败、不知道输入已被裁剪。"""
    fake_extract([], error="boom", warnings=["URL 超过 20 个，只抓前 20 个"])
    code, _, err = run_fetch(capsys)
    assert code == 1
    assert err.index("只抓前 20 个") < err.index("抓取失败")


def test_empty_result_is_not_an_empty_fence(fake_extract, capsys):
    fake_extract([])
    code, out, err = run_fetch(capsys)
    assert code == 1
    assert "没有抓到任何内容" in err
    assert render.BOUNDARY_OPEN not in out


# ---------------------------------------------------------------- 部分失败告警


def test_partial_failure_warnings_are_fenced(fake_extract, page, capsys):
    """回归：/v1/extract 的 errors[] 会把上游 URL 和 error_type 拼进 warning，
    过去直接写 stderr——既没 defang 也不在围栏内。抓取成功但部分 URL 失败时同样如此。"""
    fake_extract([page(1)], warnings=[f"2 个 URL 抓取失败: {INJECT}"])
    _, out, err = run_fetch(capsys, max_chars=8000)
    assert INJECT_SENTENCE not in outside_fence(out)
    assert INJECT_SENTENCE not in err, "告警绕过 stdout 的围栏跑到 stderr 去了"
    assert fence_counts(out) == (1, 1)


def test_partial_failure_warnings_are_visible(fake_extract, page, capsys):
    """围栏化不能把告警弄丢——用户仍然要知道有 URL 没抓到。"""
    fake_extract([page(1)], warnings=["2 个 URL 抓取失败: https://x.com: timeout"])
    _, out, _ = run_fetch(capsys, max_chars=8000)
    assert "抓取失败" in out and "timeout" in out


def test_fatal_path_keeps_warnings_in_one_fence(fake_extract, capsys):
    """整体失败时告警和错误详情必须在**同一道**围栏里，不能有半句落在外面。"""
    fake_extract([], error=f"HTTP 500 {INJECT}", warnings=[f"URL 被截断 {INJECT}"])
    code, _, err = run_fetch(capsys)
    assert code == 1
    assert fence_counts(err) == (1, 1)
    assert INJECT_SENTENCE not in outside_fence(err)


def test_warnings_count_against_budget(fake_extract, page, capsys):
    fake_extract([page(1)], warnings=["告警" * 200])
    _, out, _ = run_fetch(capsys, max_chars=1500)
    assert len(out.rstrip()) <= 1500


# ---------------------------------------------------------------- 紧预算 + 长元数据


@pytest.mark.parametrize("max_chars", [200, 500, 1000, 3000])
def test_long_metadata_under_tight_budget(fake_extract, page, capsys, max_chars):
    """回归：标题/URL/正文各 10000 字符、--max-chars 500 → 输出 566 且正文为空。

    症结是 200/300 的字段上限不随预算收缩：光元数据就吃光预算，
    而 shown=1 又强制保留首页，于是既超支又没有正文。
    """
    fake_extract([page(1, title=HUGE, url=f"https://e.com/{HUGE}", content="正文内容。" * 2000)])
    _, out, _ = run_fetch(capsys, max_chars=max_chars)
    assert len(out.rstrip()) <= max_chars, f"超支 {len(out.rstrip()) - max_chars}"
    assert "正文内容" in out, "元数据吃光预算，正文为空"


# ---------------------------------------------------------------- 告警 × 紧预算 组合

# fetch 也有围栏造成的固定下限（围栏 53 + 最小标题/URL 上限），实测约 189 字符。
_FETCH_FLOOR = 200
_LONG_WARNING = "URL 超过 20 个，只抓前 20 个（其余请分批 fetch）" + "，" * 80


@pytest.mark.parametrize("pages_n", [1, 3, 20])
@pytest.mark.parametrize("warn_n", [0, 1, 2, 5, 10])
def test_warnings_and_tight_budget_combined(fake_extract, page, capsys, pages_n, warn_n):
    """回归：告警和长元数据**分开测都通过，组合起来就崩**。

    单条告警有限长，但条数没有上限，整段无条件加入。两条真实可达的告警
    （URL 超 20 条、部分 URL 抓取失败）在 --max-chars 300 下就能把正文挤光。
    组合场景必须显式扫，不能指望两个单独用例的交集。
    """
    fake_extract([page(i, title=HUGE, url=f"https://e.com/{HUGE}",
                       content="正文内容。" * 2000) for i in range(pages_n)],
                 warnings=[_LONG_WARNING] * warn_n)
    overruns, bodyless = [], []
    for max_chars in range(_FETCH_FLOOR, 3100, 100):
        _, out, _ = run_fetch(capsys, max_chars=max_chars)
        text = out.rstrip()
        if len(text) > max_chars:
            overruns.append((max_chars, len(text)))
        elif max_chars >= 400 and "正文内容" not in text:
            bodyless.append(max_chars)
    assert not overruns, f"超支 {overruns[:5]}"
    assert not bodyless, f"预算充足却没有正文 {bodyless[:5]}"


def test_below_fetch_floor_output_is_bounded(fake_extract, page, capsys):
    """低于下限时允许超支，但超出量必须有界、不随页数或告警条数增长。"""
    fake_extract([page(i, title=HUGE, url=f"https://e.com/{HUGE}") for i in range(20)],
                 warnings=[_LONG_WARNING] * 30)
    worst = max(len(run_fetch(capsys, max_chars=mc)[1].rstrip())
                for mc in range(1, _FETCH_FLOOR, 10))
    assert worst < 400, f"下限区输出 {worst} 字符"


def test_dropped_warnings_are_announced(fake_extract, page, capsys):
    fake_extract([page(1)], warnings=[_LONG_WARNING] * 10)
    _, out, _ = run_fetch(capsys, max_chars=600)
    assert "条抓取告警从略" in out


def test_no_pages_without_error_keeps_warnings(fake_extract, capsys):
    """一页都没抓到时，告警往往正是原因所在（全部 URL 都失败），不能丢。"""
    fake_extract([], warnings=["3 个 URL 抓取失败: https://a.com: timeout"])
    code, _, err = run_fetch(capsys)
    assert code == 1
    assert "timeout" in err, "告警被「没有抓到任何内容」顶掉了"
    assert fence_counts(err) == (1, 1)


def test_no_pages_warnings_are_fenced(fake_extract, capsys):
    fake_extract([], warnings=[f"抓取失败 {INJECT}"])
    _, _, err = run_fetch(capsys)
    assert fence_counts(err) == (1, 1)
    assert INJECT_SENTENCE not in outside_fence(err)


# ---------------------------------------------------------------- Extract 的上游告警与通路等价


def _extract_via(monkeypatch, tmp_path, transport, body):
    import copy

    import config as cfgmod
    import sources

    cfg = copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"])
    cfg["parallel"]["transport"] = transport
    cfg["parallel"]["api_key"] = "k"
    if transport == "http":
        monkeypatch.setattr(sources, "_post_parallel", lambda *a, **k: dict(body))
    else:
        class _Proc:
            returncode = 0
            stdout = stderr = ""

        def fake_run(cmd, **kwargs):
            import copy as _copy
            import json as jsonlib
            from pathlib import Path as P
            written = _copy.deepcopy(body)
            # 模拟 CLI 的真实行为：--no-excerpts 会在写输出文件时把 excerpts 删掉。
            # 桩不照着做的话，"CLI 把兜底数据删了"这个缺陷根本复现不出来。
            if "--no-excerpts" in cmd:
                for item in written.get("results", []):
                    item.pop("excerpts", None)
            P(cmd[cmd.index("-o") + 1]).write_text(jsonlib.dumps(written), encoding="utf-8")
            fake_run.cmd = cmd
            return _Proc()

        monkeypatch.setattr(sources.shutil, "which", lambda _: "/usr/bin/parallel-cli")
        monkeypatch.setattr(sources.subprocess, "run", fake_run)
        _extract_via.last_cmd = fake_run
    return sources.parallel_extract(cfg, ["https://e.com"], None, 5000)


_SUCCESS_WITH_WARNING = {
    "results": [{"url": "https://e.com", "title": "t", "excerpts": ["正文"]}],
    "warnings": [{"type": "field_downgraded", "message": "full_content 降级为 excerpts"}],
}


@pytest.mark.parametrize("transport", ["http", "cli"])
def test_extract_surfaces_upstream_warnings(monkeypatch, tmp_path, transport):
    """回归：Search 路径补了顶层 warnings，Extract 一度还漏着——
    字段降级、提取不完整都会被当成"完全成功"。"""
    pages, error, warnings = _extract_via(monkeypatch, tmp_path, transport, _SUCCESS_WITH_WARNING)
    assert pages and error is None
    assert any("field_downgraded" in w for w in warnings), f"{transport} 通路丢了告警"


def test_extract_cli_sends_client_model(monkeypatch, tmp_path):
    """HTTP 一直在发 client_model，CLI 漏了。
    `parallel-cli extract --help` 明确支持 --client-model——跑过 --help 确认，不是猜的。"""
    _extract_via(monkeypatch, tmp_path, "cli", _SUCCESS_WITH_WARNING)
    cmd = _extract_via.last_cmd.cmd
    assert "--client-model" in cmd
    assert cmd[cmd.index("--client-model") + 1] == "claude-opus-5"


def test_extract_warnings_reach_stdout(fake_extract, page, capsys):
    """告警要真的走到输出里，并且在围栏内。"""
    fake_extract([page(1)], warnings=["field_downgraded: full_content 降级为 excerpts"])
    _, out, _ = run_fetch(capsys, max_chars=8000)
    assert "field_downgraded" in out
    assert INJECT_SENTENCE not in outside_fence(out)


# ---------------------------------------------------------------- excerpt 兜底


_FULL_CONTENT_NULL = {
    "results": [{"url": "https://e.com", "title": "t",
                 "full_content": None, "excerpts": ["这是兜底摘录"]}],
}


@pytest.mark.parametrize("transport", ["http", "cli"])
def test_null_full_content_falls_back_to_excerpts(monkeypatch, tmp_path, transport):
    """回归：无 --objective 时 CLI 传了 --no-excerpts，而 CLI 会在写输出文件时
    把 excerpts 删掉。上游 full_content 为 null 时，HTTP 能回退到 excerpt，
    CLI 却只剩空正文还报成功——`_extract_pages` 的兜底得留着东西可兜。"""
    pages, error, _ = _extract_via(monkeypatch, tmp_path, transport, _FULL_CONTENT_NULL)
    assert error is None and pages
    assert "这是兜底摘录" in pages[0]["content"], f"{transport} 通路正文为空"


def test_cli_does_not_strip_excerpts(monkeypatch, tmp_path):
    """直接盯住根因：命令里不该再出现 --no-excerpts。"""
    _extract_via(monkeypatch, tmp_path, "cli", _FULL_CONTENT_NULL)
    assert "--no-excerpts" not in _extract_via.last_cmd.cmd


def test_full_content_still_preferred_over_excerpts(monkeypatch, tmp_path):
    """有 full_content 时仍以它为准，excerpt 只是兜底。"""
    body = {"results": [{"url": "https://e.com", "title": "t",
                         "full_content": "完整正文在此", "excerpts": ["摘录"]}]}
    pages, _, _ = _extract_via(monkeypatch, tmp_path, "cli", body)
    assert "完整正文在此" in pages[0]["content"]


def test_cli_error_detail_is_redacted(monkeypatch, tmp_path):
    """纵深防御要打在**真实的错误路径**上：只测 redact() 本身的话，
    "调用点忘了调用它"这个缺陷根本不会被执行到。"""
    import copy

    import config as cfgmod
    import sources

    secret = "sk-SENTINEL-secret-value-9876543210"
    cfg = copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"])
    cfg["parallel"]["transport"] = "cli"
    cfg["parallel"]["api_key"] = secret
    cfg["cache"]["dir"] = str(tmp_path)

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = f"boom: env PARALLEL_API_KEY={secret} rejected"

    monkeypatch.setattr(sources.shutil, "which", lambda _: "/usr/bin/parallel-cli")
    monkeypatch.setattr(sources.subprocess, "run", lambda *a, **k: _Proc())
    _, error, _ = sources.parallel_extract(cfg, ["https://e.com"], None, 5000)
    assert error and secret not in error
    assert "[已脱敏的密钥]" in error


def test_search_cli_error_detail_is_redacted(monkeypatch, tmp_path):
    import copy

    import config as cfgmod
    import sources

    secret = "sk-SENTINEL-secret-value-9876543210"
    cfg = copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"])
    cfg["parallel"]["transport"] = "cli"
    cfg["parallel"]["api_key"] = secret
    cfg["cache"]["dir"] = str(tmp_path)

    class _Proc:
        returncode = 1
        stdout = ""
        stderr = f"auth failed for {secret}"

    monkeypatch.setattr(sources.shutil, "which", lambda _: "/usr/bin/parallel-cli")
    monkeypatch.setattr(sources.subprocess, "run", lambda *a, **k: _Proc())
    result = sources.parallel_search(cfg, "目标", ["甲"], {"mode": "basic"})
    assert result.error and secret not in result.error


# ---------------------------------------------------------------- clean_text 只去导航


def test_repeated_body_lines_are_kept():
    """回归：40 行窗口去重对任何长度 >2 的重复行生效，会静默删掉正文。
    两段结构相同的代码示例，第二段的 `return None` 直接消失——
    而 SKILL.md 正是把 fetch 定位到文档站。"""
    import sources

    code = (
        "def a():\n    x = compute()\n    if not x:\n        return None\n    return x\n\n"
        "def b():\n    y = compute()\n    if not y:\n        return None\n    return y"
    )
    assert sources.clean_text(code).count("return None") == 2


@pytest.mark.parametrize("repeated", [
    "| 字段 | 类型 | 说明 |",
    "2026-09-05 INFO 请求完成",
    "    return None",
    "以上内容仅供参考。",
])
def test_repeated_plain_lines_are_kept(repeated):
    """表格行、重复日志、重复提示语都是正文，不能当导航删掉。"""
    import sources

    text = f"{repeated}\n中间内容\n{repeated}"
    assert sources.clean_text(text).count(repeated.strip()) == 2


@pytest.mark.parametrize("line", [
    "[产品文档](https://a/1)",
    "请访问 [控制台](https://a/1) 创建项目。",
    "[Linux 下载](https://a/linux) [Windows 下载](https://a/windows)",
])
def test_repeated_link_content_is_kept(line):
    """链接和重复句子本身不能证明是导航。"""
    import sources

    text = f"{line}\n第一步\n{line}\n第二步"
    assert sources.clean_text(text) == text



def _extract_cmd(monkeypatch, urls, objective=None):
    """跑一次 CLI 通路的 parallel_extract，把真正拼出来的 argv 抓回来。"""
    import copy
    import json as jsonlib
    from pathlib import Path as P

    import config as cfgmod
    import sources

    cfg = copy.deepcopy(cfgmod.load_config.__globals__["DEFAULTS"])
    cfg["parallel"]["transport"] = "cli"
    cfg["parallel"]["api_key"] = "k"
    captured = {}

    class _Proc:
        returncode = 0
        stdout = stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        P(cmd[cmd.index("-o") + 1]).write_text(jsonlib.dumps({"results": []}), encoding="utf-8")
        return _Proc()

    monkeypatch.setattr(sources.shutil, "which", lambda _: "/usr/bin/parallel-cli")
    monkeypatch.setattr(sources.subprocess, "run", fake_run)
    sources.parallel_extract(cfg, urls, objective, 5000)
    return captured["cmd"]


@pytest.mark.parametrize("url", ["--help", "--json", "-", "-o"])
def test_dash_leading_url_is_not_parsed_as_option(monkeypatch, url):
    """回归：URL 曾排在所有选项之前且没有 `--`，以 `-` 开头时被 click 当成选项——
    `--help` 让 CLI 打印帮助后**正常退出**却不写结果文件，我们随后崩在
    JSONDecodeError 上；`--json` 被吞成 flag，那个 URL 静默从请求里消失，
    而我们照常报成功、只是少了一页。

    URL 多半来自上一次 search 落盘 JSON 的 docs[].url，是上游可控字段。
    HTTP 通路把 URL 放在 JSON body 里没这问题，不修则 auto 模式下行为
    取决于本机装没装 parallel-cli——与 objective 那条是同一个缺陷。
    """
    cmd = _extract_cmd(monkeypatch, [url])
    assert cmd[-2:] == ["--", url]
    assert cmd.index("--") == len(cmd) - 2, "`--` 之后只能剩 URL"


def test_all_urls_sit_after_the_terminator(monkeypatch):
    """多 URL 时全部都要在 `--` 之后，且保序——漏掉任何一个就等于没修。"""
    urls = ["https://a.com", "--json", "https://b.com"]
    cmd = _extract_cmd(monkeypatch, urls)
    assert cmd[cmd.index("--") + 1:] == urls, "`--` 之后必须正好是全部 URL、保序"


def test_dash_urls_survive_click_parsing(monkeypatch):
    """不止断言我们拼了 `--`，还要断言 click 真的按位置参数解析它。
    用 parallel-cli 自带的那份 click 复刻 `extract` 的参数签名。"""
    import click
    from click.testing import CliRunner

    @click.command()
    @click.argument("urls", nargs=-1)
    @click.option("--json", "as_json", is_flag=True)
    @click.option("-o", "out")
    @click.option("--full-content", is_flag=True)
    @click.option("--full-content-max-chars", type=int)
    @click.option("--client-model")
    def fake_extract(urls, **_):
        click.echo("\n".join(urls))

    urls = ["--help", "https://e.com", "--json"]
    cmd = _extract_cmd(monkeypatch, urls)
    result = CliRunner().invoke(fake_extract, cmd[2:])
    assert result.exit_code == 0
    assert result.output.split() == urls, "URL 仍被当成选项解析"


@pytest.mark.parametrize("bad_urls", [[], [""], ["   "], ["", "   "]])
def test_run_fetch_rejects_empty_or_whitespace_urls(capsys, bad_urls):
    """fetch 收到空 URL 或纯空白 URL 时应当直接返回错误码 2，而不是向下打崩上游。"""
    args = argparse.Namespace(urls=bad_urls, objective=None, max_chars=12000, session_id=None)
    code = gr_search.run_fetch(args, {})
    assert code == 2
    err = capsys.readouterr().err
    assert "URL 列表不能为空" in err


def test_run_fetch_strips_valid_urls(monkeypatch):
    """fetch 应当清洗 URL 两端的空白字符再发给上游。"""
    passed_urls = []

    def stub_extract(cfg, urls, *a, **k):
        passed_urls.extend(urls)
        return [], None, []

    monkeypatch.setattr(gr_search.sources, "parallel_extract", stub_extract)
    args = argparse.Namespace(urls=["  https://a.com  ", "https://b.com/ "],
                              objective=None, max_chars=12000, session_id=None)
    gr_search.run_fetch(args, {})
    assert passed_urls == ["https://a.com", "https://b.com/"]


def test_extract_http_error_redacts_secrets(monkeypatch):
    """HTTP 403/401 报错如果包含密钥，必须在出口被脱敏。"""
    import io
    import urllib.error
    import sources

    secret = "sk-SENTINEL-secret-value-9876543210"
    cfg = {"parallel": {"api_key": secret, "client_model": "test"}}

    class _ErrResponse(io.BytesIO):
        def __init__(self):
            super().__init__(f"Invalid key: {secret}".encode("utf-8"))

    def fake_post(*a, **k):
        raise urllib.error.HTTPError("https://api.parallel.ai/v1/extract", 401, "Unauthorized", {}, _ErrResponse())

    monkeypatch.setattr(sources, "_post_parallel", fake_post)
    pages, error, warnings = sources._parallel_extract_http(cfg, ["https://example.com"], None, 12000)
    assert secret not in error
    assert "[已脱敏的密钥]" in error


def test_doubao_http_error_redacts_secrets(monkeypatch):
    """豆包 HTTP 错误若回显密钥，也必须在出口被脱敏。"""
    import io
    import urllib.error
    import sources

    secret = "sk-SENTINEL-doubao-secret-value-123"
    cfg = {"doubao": {"api_key": secret, "count": 10}}

    class _ErrResponse(io.BytesIO):
        def __init__(self):
            super().__init__(f"Invalid bearer {secret}".encode("utf-8"))

    def fake_post(*a, **k):
        raise urllib.error.HTTPError("https://open.feedcoopapi.com", 401, "Unauthorized", {}, _ErrResponse())

    monkeypatch.setattr(sources, "_post_json", fake_post)
    result = sources.doubao_search(cfg, "测试", {"no_cache": True})
    assert result.error and secret not in result.error
    assert "[已脱敏的密钥]" in result.error


def test_parallel_search_http_error_redacts_secrets(monkeypatch):
    """Parallel Search HTTP 错误若回显密钥，也必须在出口被脱敏。"""
    import io
    import urllib.error
    import sources

    secret = "sk-SENTINEL-parallel-secret-value-456"
    cfg = {"parallel": {"api_key": secret, "mode": "basic", "excerpt_max_chars_total": 1000, "max_results": 10}}

    class _ErrResponse(io.BytesIO):
        def __init__(self):
            super().__init__(f"Invalid parallel-key: {secret}".encode("utf-8"))

    def fake_post(*a, **k):
        raise urllib.error.HTTPError("https://api.parallel.ai/v1/search", 403, "Forbidden", {}, _ErrResponse())

    monkeypatch.setattr(sources, "_post_parallel", fake_post)
    result = sources._parallel_search_http(cfg, "测试", ["关键词"], {"no_cache": True})
    assert result.error and secret not in result.error
    assert "[已脱敏的密钥]" in result.error
