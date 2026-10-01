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
    assert checker.check('v123456、0.123456、123456e3、1.23456E10', profile='finance') == []
    assert any(f['rule'] == 'thousands' for f in checker.check('共 123456 行。', profile='finance'))


@pytest.mark.parametrize('text', ['我想想...', '然后...好吧', '我想想。。。', '我想想。。。。'])
def test_ellipsis_reports_the_right_rule_and_fix(text):
    findings = checker.check(text)
    assert [f['rule'] for f in findings] == ['bad-ellipsis']
    assert '……' in findings[0]['fix']


@pytest.mark.parametrize('text, line, col', [
    ('- 父项\n    - 子项中文!错误', 2, 11),
    ('1. 第一步\n\n    这里是续段,有错误。', 3, 10),
    ('- 父项\n    - 子项\n\n      续段!\n', 4, 9),
    ('- 父项\n\t- 子项!', 2, 6),
])
def test_list_prose_is_checked(text, line, col):
    assert [(f['rule'], f['line'], f['col']) for f in checker.check(text)] == [
        ('ascii-comma', line, col)
    ]


@pytest.mark.parametrize('text', [
    '- 父项\n\n      代码!\n',
    '1. 父项\n\n       代码!\n',
    '- 父项\n\n    ```txt\n    代码!\n    ```',
])
def test_code_inside_lists_is_protected(text):
    assert checker.check(text) == []


def test_nested_list_fence_closes_before_following_prose():
    text = '- 父项\n    - ```txt\n      代码!\n      ```\n      正文!'
    assert [(f['rule'], f['line'], f['col']) for f in checker.check(text)] == [
        ('ascii-comma', 5, 9)
    ]


@pytest.mark.parametrize('text, expected', [
    ('- 项\n  ```\n  代码!\n```\n正文!', [('ascii-comma', 5, 3)]),
    ('1. 步骤\n   ```bash\n   ls!\n```\n\n后文!\n\n## 标题。',
     [('ascii-comma', 6, 3), ('heading-trailing-punct', 8, 1)]),
    ('- 项\n  ~~~txt\n  代码!\n~~~\n正文!', [('ascii-comma', 5, 3)]),
    ('- 项\n  ```\n  代码!\n    ```\n正文!', [('ascii-comma', 5, 3)]),
    ('- 父项\n    - ```txt\n      代码!\n  ````\n正文!', [('ascii-comma', 5, 3)]),
])
def test_dedented_list_fence_closer_preserves_following_prose(text, expected):
    masked = checker.preprocess(text)
    assert len(masked) == len(text)
    assert [i for i, c in enumerate(masked) if c == '\n'] == [
        i for i, c in enumerate(text) if c == '\n'
    ]
    assert [(f['rule'], f['line'], f['col']) for f in checker.check(text)] == expected


@pytest.mark.parametrize('closer', ['``', '~~~', '``` trailing text', '      ```', 'xx```'])
def test_invalid_dedented_closer_keeps_code_protected(closer):
    text = '- 项\n  ```\n  代码!\n' + closer + '\n正文!'
    assert checker.check(text) == []


def test_dedented_list_fence_inside_callout_preserves_prose_positions():
    text = '> [!note]\n> - 项\n>   ```\n>   代码!\n> ```\n> 正文!'
    assert [(f['rule'], f['line'], f['col']) for f in checker.check(text)] == [
        ('ascii-comma', 6, 5)
    ]


def test_fullwidth_range_connector_is_a_valid_style():
    assert checker.check('区间 3～5 天，收益 15%～20%。') == []
    assert [f['rule'] for f in checker.check('区间 3~5 天。')] == ['range-hyphen']


@pytest.mark.parametrize('text', [
    '贵州茅台（600519）上涨。', '联系 13800138000。',
    '电话 010-12345678', 'ISBN 978-7-111-12345-6',
])
def test_identifiers_do_not_raise_numeric_style_warnings(text):
    assert checker.check(text) == []
    assert checker.check(text, profile='finance') == []


def test_identifier_masking_preserves_adjacent_prose():
    findings = checker.check('电话 010-12345678，正文! ISBN 978-7-111-12345-6，后文!', profile='finance')
    assert [(f['rule'], f['col']) for f in findings] == [('ascii-comma', 19), ('ascii-comma', 46)]


@pytest.mark.parametrize('profile', ['general', 'finance'])
def test_isbn_adjacent_to_chinese_preserves_label_and_prose(profile):
    text = '见ISBN 978-7-111-12345-6,好。后文!'
    findings = checker.check(text, profile=profile)
    assert [(f['rule'], f['line'], f['col']) for f in findings] == [
        ('ascii-comma', 1, text.index('!') + 1), ('cjk-latin-glue', 1, 2)
    ]


def test_finance_rules_are_opt_in():
    text = '共 123456 行，夏普>1.5。'
    assert checker.check(text) == []
    assert {f['rule'] for f in checker.check(text, profile='finance')} == {'thousands', 'math-space'}


@pytest.mark.parametrize('english', ['She said “hello” to me.', 'She said ‘hello’ to me.', "It’s the users’ choice."])
def test_english_quotes_do_not_mix_chinese_styles(english):
    assert checker.check('他说「你好」。\n\n' + english) == []


@pytest.mark.parametrize('text', ['他说「你好」，又说“再见”。', '他说「你好」，又说 “hello”。', '他说「你好」，又说 “再见，hello”。'])
def test_chinese_curly_quotes_still_trigger_style_mix(text):
    assert any(f['rule'] == 'quote-style-mix' for f in checker.check(text))


@pytest.mark.parametrize('text', ['他说「你好」。她回答：“OK”。', '他说「你好」。她回答：‘OK’。'])
def test_curly_quotes_adjacent_to_chinese_punctuation_trigger_style_mix(text):
    assert [f['rule'] for f in checker.check(text)] == ['quote-style-mix']


def test_callout_prose_is_checked_with_original_positions():
    text = '> [!note] 提示\n> 这是作者自己的说明,有错误。\n>\n> 后文!'
    masked = checker.preprocess(text)
    assert len(masked) == len(text)
    assert [i for i, c in enumerate(masked) if c == '\n'] == [
        i for i, c in enumerate(text) if c == '\n'
    ]
    assert [(f['rule'], f['line'], f['col']) for f in checker.check(text)] == [
        ('ascii-comma', 2, 12), ('ascii-comma', 4, 5)
    ]


def test_callout_code_and_nested_quotes_are_protected():
    text = '> [!note]\n> ```txt\n> 代码!\n> ```\n> > 原话!\n>\n> 正文!\n\n正文!'
    assert [(f['rule'], f['line']) for f in checker.check(text)] == [
        ('ascii-comma', 7), ('ascii-comma', 9)
    ]


def test_callout_does_not_make_a_following_quote_editable():
    assert checker.check('> [!note]\n> 正文。\n\n> 原话!') == []


def test_callout_container_marker_is_not_a_comparison_symbol():
    assert checker.check('>[!note]\n>1.5 倍', profile='finance') == []


@pytest.mark.parametrize('text, line', [
    ('```md\n> [!note]\n> 示例!\n```\n正文!', 5),
    ('- 父项\n    ```md\n> [!note]\n> 示例!\n    ```\n正文!', 6),
    ('---\n> [!note]\n> 示例!\n---\n正文!', 5),
    ('> 原话。\n> [!note]\n> 示例!\n\n正文!', 5),
])
def test_callout_syntax_inside_protected_blocks_does_not_hide_following_prose(text, line):
    assert [(f['rule'], f['line']) for f in checker.check(text)] == [('ascii-comma', line)]


def test_wikilink_target_is_protected_but_alias_is_checked():
    assert checker.check('见[[笔记A]]、![[图像A.png]]。') == []
    findings = checker.check('见[[笔记A#标题|别名!]]。')
    assert [f['rule'] for f in findings] == ['ascii-comma']


def test_punctuation_stack_takes_priority_over_ascii_punctuation():
    assert [f['rule'] for f in checker.check('太好了!!!')] == ['dup-punct']


def test_heading_with_closing_hashes_is_checked():
    assert [f['rule'] for f in checker.check('## 标题。 ##')] == ['heading-trailing-punct']


def test_dash_next_to_english_is_checked_but_double_dash_flag_is_a_candidate():
    assert [f['rule'] for f in checker.check('答案—OK')] == ['bad-dash']
    assert [f['level'] for f in checker.check('加上--force参数') if f['rule'] == 'bad-dash'] == ['warn']
    assert checker.check('答案——OK。') == []


def test_year_month_is_not_a_range():
    assert checker.check('2024-03 月报') == []


@pytest.mark.parametrize('text', [
    '时间戳 2024-03-31T09:30:00 记录。',
    '更新于 2024-03-31T09:30:00Z',
    '文件 2024-03-31_report 生成。',
    '文件 report_2024-03-31 生成。',
    '更新于 2024-03-31T09:30:00+08:00',
])
def test_iso_date_with_time_or_filename_affix_is_not_a_range(text):
    assert checker.check(text) == []


@pytest.mark.parametrize('text', ['12024-03', '2024-033', '3-2024-03', '2024-03-31-5'])
def test_partial_date_inside_other_numeric_sequences_does_not_hide_ranges(text):
    assert any(f['rule'] == 'range-hyphen' for f in checker.check(text))


@pytest.mark.parametrize('text', ['日期2024-03-31', '2024-03月报'])
def test_date_adjacent_to_chinese_only_reports_spacing(text):
    assert [f['rule'] for f in checker.check(text)] == ['cjk-latin-glue']


def test_supplementary_cjk_is_recognized():
    assert [f['rule'] for f in checker.check('𠀀!')] == ['ascii-comma']


def test_currency_does_not_hide_prose_between_dollar_signs():
    findings = checker.check('价格 $5，中文! 另一件 $10。')
    assert [f['rule'] for f in findings] == ['ascii-comma']


def run_cli(text, *args):
    proc = subprocess.run([sys.executable, str(SCRIPT), '-', '--json', *args],
                          input=text, text=True, capture_output=True, check=False)
    return proc.returncode, json.loads(proc.stdout)


def test_cli_finance_profile_and_exit_status():
    code, payload = run_cli('共 123456 行。', '--fail-on', 'warn')
    assert code == 0
    assert payload['findings'] == []
    code, payload = run_cli('共 123456 行。', '--profile', 'finance', '--fail-on', 'warn')
    assert code == 1
    assert [f['rule'] for f in payload['findings']] == ['thousands']


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
