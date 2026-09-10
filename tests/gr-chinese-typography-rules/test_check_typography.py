"""保护内容、误报与 CLI 合约的回归测试。"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "skills/gr-chinese-typography-rules/scripts/check_typography.py"
SPEC = importlib.util.spec_from_file_location("check_typography", SCRIPT)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


@pytest.mark.parametrize("protected", [
    '```txt\n中文!\n```',
    '```txt\n中文!\n````',
    '  ~~~txt\n中文!\n ~~~~',
    '````txt\n```\n中文!\n```\n````',
    '```txt\n中文!\n',
    '``中文`代码!``',
    '``中文!\n代码!``',
    '---\ntitle: 中文!\n---',
    '\ufeff---\ntitle: 中文!\n...\n',
    '---\ntitle: 中文!\n',
    '> 原话:中文!\n续行!\n',
    '  > > 原话:中文!\n',
    '    中文!\n\t 中文!\n',
    '<!-- 中文!\n中文! -->',
    '<div title="中文!">',
    '$中文!$、$$中文!\n内容!$$',
    r'\(中文!\) 与 \[中文!\]',
    '[id]: https://example.com "标题!"\n',
    '[id]: https://example.com\n  "标题!"\n',
    '[链接](https://example.com/a(b(c)) "标题!")',
    r'[链接](folder/a\(b\).md "标题!")',
    '[链接](file.md "带 ) 的标题!")',
    '[链接](<file(a.md> "标题!")',
    '$x$、$a + b$、$x_1$、$$a$$',
])
def test_protected_content_is_ignored_without_losing_offsets(protected):
    masked = checker.preprocess(protected)
    assert len(masked) == len(protected)
    assert [i for i, c in enumerate(masked) if c == "\n"] == [
        i for i, c in enumerate(protected) if c == "\n"
    ]
    assert checker.check(protected) == []


def test_code_closer_does_not_swallow_following_prose():
    findings = checker.check('```\n中文!\n````\n正文!')
    assert [(f["rule"], f["line"], f["col"]) for f in findings] == [
        ("ascii-comma", 4, 3)
    ]


def test_inline_code_requires_equal_delimiter_length():
    findings = checker.check('``代码`中文!`更多``正文!')
    assert len(findings) == 1
    assert findings[0]["col"] == 16


def test_visible_link_label_is_checked():
    findings = checker.check('[正文!](https://example.com/a(b(c)) "标题!") 后文!')
    assert len(findings) == 2
    assert all(f["rule"] == "ascii-comma" for f in findings)


def test_blank_line_ends_quote_protection():
    findings = checker.check('> 原话!\n续行!\n\n正文!')
    assert [(f["rule"], f["line"]) for f in findings] == [("ascii-comma", 4)]


def test_temperature_is_not_angle_spacing_error():
    assert checker.check('温度 25 °C、77 °F。') == []
    findings = checker.check('角度 25 °。')
    assert [(f["rule"], f["level"]) for f in findings] == [("pct-space", "warn")]


def test_numeric_colon_needs_context():
    findings = checker.check('比例 3：5，时间 15：00。')
    assert len(findings) == 2
    assert all(f["level"] == "warn" for f in findings)


def test_bold_latin_spacing_is_preserved():
    assert checker.check('使用 **GitHub** 登录。') == []
    assert {f["rule"] for f in checker.check('这是 **重点** 内容。')} == {"cjk-md-space"}


def test_unit_consistency_handles_multiple_spaces():
    findings = checker.check('容量 10  GB 与 20GB。')
    assert any(f["rule"] == "unit-space-mix" for f in findings)


def test_iso_date_is_not_a_range():
    assert checker.check('日期 2024-03-31。') == []
    assert any(f["rule"] == "range-hyphen" for f in checker.check('区间 3-5。'))


def test_shared_units_and_unary_sign_do_not_raise_warnings():
    assert checker.check('区间 3–5 kg，偏差 ±2%。') == []
    findings = checker.check('区间 15–20.5%。')
    assert [f['rule'] for f in findings] == ['range-unit']


def test_thousands_does_not_split_identifiers_decimals_or_exponents():
    assert checker.check('v123456、0.123456、123456e3、1.23456E10') == []
    assert any(f['rule'] == 'thousands' for f in checker.check('共 123456 行。'))


def test_currency_does_not_hide_prose_between_dollar_signs():
    findings = checker.check('价格 $5，中文! 另一件 $10。')
    assert [f['rule'] for f in findings] == ['ascii-comma']


def run_cli(text, *args):
    proc = subprocess.run([sys.executable, str(SCRIPT), '-', '--json', *args],
                          input=text, text=True, capture_output=True, check=False)
    return proc.returncode, json.loads(proc.stdout)


@pytest.mark.parametrize('args, status, note, count', [
    ([], 0, False, 1),
    (['--fail-on', 'error'], 1, False, 1),
    (['--fail-on', 'warn', '--level', 'error'], 1, False, 1),
    (['--fail-on', 'error', '--level', 'warn'], 1, True, 0),
    (['--fail-on', 'warn', '--level', 'warn'], 1, True, 0),
])
def test_cli_exit_status_is_independent_of_display(args, status, note, count):
    code, payload = run_cli('正文!', *args)
    assert code == status
    assert ('note' in payload) == note
    assert len(payload['findings']) == count


def test_cli_warn_threshold_includes_warnings_and_crlf_positions():
    code, payload = run_cli('正常。\r\n中文AI。', '--fail-on', 'warn')
    assert code == 1
    assert [(f['line'], f['col']) for f in payload['findings']] == [(2, 3)]
    code, _ = run_cli('中文AI。', '--fail-on', 'error')
    assert code == 0


def test_cli_never_modifies_input_file(tmp_path):
    path = tmp_path / '稿子.md'
    original = '正文!\r\n'.encode()
    path.write_bytes(original)
    proc = subprocess.run([sys.executable, str(SCRIPT), str(path), '--fail-on', 'error'],
                          capture_output=True, check=False)
    assert proc.returncode == 1
    assert path.read_bytes() == original
