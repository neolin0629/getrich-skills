import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "skills" / "gr-content-ai-avoid" / "scripts" / "check.py"


def run_check(text: str, *, genre: str = "default", fail_on: str = "never"):
    proc = subprocess.run(
        [sys.executable, str(CHECK), "-", "--genre", genre, "--fail-on", fail_on, "--json"],
        input=text,
        text=True,
        capture_output=True,
        check=False,
    )
    return proc, json.loads(proc.stdout)


def metric(result: dict, key: str) -> dict:
    return next(row for row in result["metrics"] if row["key"] == key)


def test_w1_below_density_threshold_does_not_fail_or_emit_hits():
    proc, result = run_check("甲" * 997 + "彰显。", genre="copy", fail_on="high")

    assert proc.returncode == 0
    assert metric(result, "W1")["flagged"] is False
    assert not [hit for hit in result["hits"] if hit["rule"] == "W1"]
    assert result["severity_totals"]["high"] == 0


def test_w1_above_threshold_fails_once_but_keeps_all_locations():
    proc, result = run_check("甲" * 990 + "彰显。彰显。彰显。", genre="copy", fail_on="high")

    assert proc.returncode == 1
    assert metric(result, "W1")["flagged"] is True
    assert len([hit for hit in result["hits"] if hit["rule"] == "W1"]) == 3
    assert result["severity_totals"]["high"] == 1


def test_w3_does_not_treat_quarter_ordinals_as_connectors():
    _, result = run_check("这是第一季度数据。第二季度会更新。", genre="quant")

    assert metric(result, "W3")["value"] == "0.00 (0/2)"
    assert not [hit for hit in result["hits"] if hit["rule"] == "W3"]


def test_w3_counts_nested_connector_once_and_respects_boundary():
    _, result = run_check("甲。乙。丙。尽管如此，丁。")

    assert metric(result, "W3")["value"] == "0.25 (1/4)"
    assert metric(result, "W3")["flagged"] is False
    assert not [hit for hit in result["hits"] if hit["rule"] in {"W3", "P3"}]


def test_w3_allows_one_connector_in_a_short_text():
    proc, result = run_check("然而，这次结果不同。", fail_on="any")

    assert proc.returncode == 0
    assert metric(result, "W3")["flagged"] is False
    assert not [hit for hit in result["hits"] if hit["rule"] == "W3"]


def test_strict_genres_preserve_normal_exemptions():
    cases = [
        ("然而，这次结果不同。", "video", "W3"),
        ("甲" * 997 + "彰显。", "academic", "W1"),
    ]

    for text, genre, rule in cases:
        proc, result = run_check(text, genre=genre, fail_on="high")

        assert proc.returncode == 0
        assert metric(result, rule)["flagged"] is False
        assert not any(hit["rule"] == rule for hit in result["hits"])


def test_overlapping_aggregate_rules_keep_locations_for_the_flagged_rule():
    proc, result = run_check("值得注意的是甲。值得注意的是乙。", fail_on="any")

    assert proc.returncode == 1
    assert metric(result, "W1")["flagged"] is False
    assert metric(result, "W3")["flagged"] is True
    assert len([hit for hit in result["hits"] if hit["rule"] == "W3"]) == 2
    assert result["counts"] == {"W3": 2}


def test_numbered_connector_hits_report_their_own_lines():
    _, result = run_check("甲。\n第一，先看。\n第二，再看。")

    hits = [hit for hit in result["hits"] if hit["rule"] == "W3"]
    assert [(hit["matched"], hit["line"]) for hit in hits] == [("第一", 2), ("第二", 3)]


def test_markdown_link_keeps_visible_label_for_scanning():
    _, result = run_check("[这是一个非常好的问题](https://example.com)。")

    assert result["stats"]["chars"] > 4
    assert any(hit["rule"] == "F6" for hit in result["hits"])


def test_crlf_frontmatter_is_excluded_from_scanning():
    _, result = run_check("---\r\ntitle: 彰显\r\n---\r\n普通正文。")

    assert metric(result, "W1")["value"] == "0.0 (0)"
    assert not [hit for hit in result["hits"] if hit["rule"] == "W1"]


def test_short_text_allows_one_dash():
    _, result = run_check("今天亏了点钱——先睡觉。")

    assert metric(result, "F1")["flagged"] is False


def test_r1_requires_manual_review_without_keyword_verdicts():
    _, generic = run_check("这是一段事实说明。" * 60)
    _, quant = run_check("这是量化分析。" * 70, genre="quant")

    assert not [row for row in generic["metrics"] if row["key"] == "R1"]
    assert not [row for row in quant["metrics"] if row["key"] == "R1"]
    assert "R1" in quant["manual_review"]


def test_directory_input_returns_usage_error_without_traceback():
    proc = subprocess.run(
        [sys.executable, str(CHECK), str(ROOT / "skills" / "gr-content-ai-avoid")],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2
    assert "不是普通文件" in proc.stderr
    assert "Traceback" not in proc.stderr


@pytest.mark.parametrize("text, expected", [
    ("逻辑清晰、执行简单、风险可控。", False),
    ("苹果、香蕉、葡萄、橘子。", False),
    ("苹果、香蕉、葡萄、橘子、草莓。", False),
    ("苹果、香蕉、葡萄、橘。", False),
    ("苹果、香蕉、葡萄\n普通正文。", False),
])
def test_s1_defers_enumerations_to_manual_review(text, expected):
    proc, result = run_check(text, fail_on="high")
    assert bool([h for h in result["hits"] if h["rule"] == "S1"]) is expected
    assert proc.returncode == 0  # 项目数量不能证明刻意凑项。
    assert "S1" in result["manual_review"]
    assert all(h["severity"] == "low" for h in result["hits"] if h["rule"] == "S1")


def test_literal_correction_does_not_fail_as_an_aphorism():
    proc, result = run_check("这次不是系统故障，是插头松了。", fail_on="high")
    assert proc.returncode == 0
    assert not [h for h in result["hits"] if h["rule"] in {"S3", "S8"}]


def test_s8_still_reports_metaphorical_candidates():
    _, result = run_check("仓位管理不是技术，是认知的镜子。")
    assert any(h["rule"] == "S8" for h in result["hits"])


@pytest.mark.parametrize("prefix", [
    "---\ndescription: " + "甲" * 200 + "\n---\n",
    "```text\n" + "甲" * 200 + "\n```\n",
    "# 日常记录\n\n![配图](https://example.com/" + "a" * 200 + ")\n",
])
def test_head_window_ignores_masked_content_and_keeps_source_location(prefix):
    raw = prefix + "你是不是经常忘记带伞？"
    _, result = run_check(raw)
    hit = next(h for h in result["hits"] if h["rule"] == "P1")
    assert hit["offset"] == len(prefix)
    assert hit["line"] == prefix.count("\n") + 1
    assert raw[hit["offset"]:].startswith(hit["matched"])


def test_tail_window_ignores_code_appendix_and_keeps_source_location():
    prefix = "记录已经写完。\n"
    raw = prefix + "三条建议：今晚早点睡觉。\n\n```text\n" + "甲" * 500 + "\n```\n"
    _, result = run_check(raw)
    hit = next(h for h in result["hits"] if h["rule"] == "P5")
    assert hit["offset"] == len(prefix)
    assert hit["line"] == 2


def test_scoped_rules_still_exclude_body_outside_their_windows():
    _, head = run_check("甲" * 160 + "。你是不是经常忘记带伞？")
    _, tail = run_check("三条建议：今晚早点睡觉。" + "甲" * 500)
    assert not [h for h in head["hits"] if h["rule"] == "P1"]
    assert not [h for h in tail["hits"] if h["rule"] == "P5"]


def test_weibo_exempts_short_sentences_but_default_still_checks_them():
    raw = "到家了。洗个澡。睡觉了。"
    proc, weibo = run_check(raw, genre="weibo", fail_on="any")
    _, default = run_check(raw)
    assert proc.returncode == 0
    assert not [m for m in weibo["metrics"] if m["key"] in {"S7", "S7b"}]
    assert metric(default, "S7b")["flagged"] is True


def test_persona_relaxes_connectors_but_still_reports_excess():
    raw = "但是今天下雨。不过我带了伞。雨到下午才停。回家的路上看到了晚霞。"
    _, persona = run_check(raw, genre="persona")
    _, default = run_check(raw)
    _, excess = run_check("但是今天下雨。不过我带了伞。", genre="persona")
    assert metric(persona, "W3")["flagged"] is False
    assert metric(default, "W3")["flagged"] is True
    assert metric(excess, "W3")["flagged"] is True


def test_s3_reports_local_cluster_without_flagging_a_distant_occurrence():
    sentence = "与其说天气变好不如说风小了。"
    raw = sentence * 3 + "甲" * 1600 + "。" + sentence
    proc, result = run_check(raw, fail_on="high")
    hits = [h for h in result["hits"] if h["rule"] == "S3"]
    assert proc.returncode == 1
    assert [h["offset"] for h in hits] == [0, len(sentence), len(sentence) * 2]


@pytest.mark.parametrize("span, expected", [(799, 3), (800, 3), (801, 0)])
def test_s3_window_boundary_counts_effective_characters(span, expected):
    prefix = "与其说天气变好不如说风小了。" * 2
    last_match = "与其说天气变好不如说"
    used = len(prefix.replace("。", "")) + len(last_match)
    raw = prefix + "甲" * (span - used) + "。" + last_match + "风小了。"
    _, result = run_check(raw)
    assert len([h for h in result["hits"] if h["rule"] == "S3"]) == expected


def test_s3_ignores_masked_content_between_occurrences():
    sentence = "与其说天气变好不如说风小了。\n"
    raw = sentence * 2 + "```text\n" + "甲" * 1000 + "\n```\n" + sentence
    _, result = run_check(raw)
    hits = [h for h in result["hits"] if h["rule"] == "S3"]
    assert len(hits) == 3
    assert hits[-1]["line"] == 6
    assert hits[-1]["offset"] == raw.rindex("与其说")


def test_s3_deduplicates_overlapping_sentence_patterns():
    raw = "不仅仅是速度快而且是成本低。与其说天气变好不如说风小了。"
    _, below = run_check(raw)
    _, above = run_check(raw + "与其说路面干了不如说雨停了。")
    assert not [h for h in below["hits"] if h["rule"] == "S3"]
    assert len([h for h in above["hits"] if h["rule"] == "S3"]) == 3


@pytest.mark.parametrize('raw', [
    '本次结论仅覆盖沪深市场日频数据，区间为 2019 年至 2024 年，未覆盖其他市场，也未扣除滑点。',
    '该策略在任何市场都不会失效。',
    '我们已完成样本外验证，因此任何情况下都有收益。',
    '我不确定。',
])
def test_r1_never_uses_word_presence_as_evidence(raw):
    _, result = run_check(raw, genre='quant')
    assert 'R1' in result['manual_review']
    assert not any(m['key'] == 'R1' for m in result['metrics'])
    assert not any(h['rule'] == 'R1' for h in result['hits'])


@pytest.mark.parametrize('genre, expected', [('quant', True), ('academic', False), ('copy', False)])
def test_manual_review_respects_genre(genre, expected):
    _, result = run_check('本次数据已整理完毕。', genre=genre)
    assert ('R1' in result['manual_review']) is expected


@pytest.mark.parametrize('raw, rule', [
    ('这次实测延迟是 1.7 秒。', 'R2'),
    ('监控日志记录停顿了 3.5 秒。', 'R2'),  # 时间候选可复核，但不能认定数据虚假。
    ('我有个朋友，昨天帮我修了水管。', 'R4'),
    ('本次问卷共回收 100 份，原始数据见附表。数据显示，60 人选择公交。', 'C5'),
    ('原文写道：“愿你平安。”', 'P4'),
    ('苹果、香蕉、葡萄。', 'S1'),
])
def test_semantic_candidates_do_not_fail_high(raw, rule):
    proc, result = run_check(raw, genre='quant', fail_on='high')
    assert proc.returncode == 0
    assert all(h['severity'] == 'low' for h in result['hits'] if h['rule'] == rule)


@pytest.mark.parametrize('raw, rule', [
    ('这次实测延迟是 1.7 秒。', 'R2'),
    ('屋里的天花板漏水了。', 'C9'),
    ('我们修好了水泵，为村里提供了饮用水。', 'S5'),
    ('我们修好了水泵，为村里提供了饮用水。', 'P2'),
    ('我们买了发电机，让停电的教室能够继续上课。', 'S5'),
    ('## 发货时间\n\n发货时间为周一。', 'P2'),
    ('## 流动性\n\n流动性下降了两成。', 'P2'),
    ('祝你生日快乐！', 'P4'),
])
def test_concrete_statements_are_not_reported_as_empty_or_fake(raw, rule):
    _, result = run_check(raw)
    assert not any(h['rule'] == rule for h in result['hits'])


@pytest.mark.parametrize('raw, rule', [
    ('那一刻，1.7 秒后，我心头一紧。', 'R2'),
    ('这个产品堪称行业天花板。', 'C9'),
    ('项目顺利完成，为未来发展奠定了坚实基础。', 'S5'),
    ('## 关于流动性\n\n流动性很重要。', 'P2'),
    ('## 发货时间\n\n发货时间。', 'P2'),
    ('好了，接着往下讲。', 'P2'),
    ('有研究表明，这个方法有效。', 'C5'),
])
def test_problematic_counterparts_remain_visible(raw, rule):
    _, result = run_check(raw)
    assert any(h['rule'] == rule for h in result['hits'])


def test_p4_only_scans_tail_and_does_not_double_count():
    raw = '愿你平安。' + '甲' * 220 + '。记录结束。'
    _, middle = run_check(raw)
    assert not any(h['rule'].startswith('P4') for h in middle['hits'])
    _, tail = run_check('记录结束。愿你平安。')
    hits = [h for h in tail['hits'] if h['rule'].startswith('P4')]
    assert [(h['rule'], h['matched']) for h in hits] == [('P4', '愿你')]
    assert tail['severity_totals']['low'] == 1


@pytest.mark.parametrize('prefix', [
    '参考 https://example.com。',
    '参考 https://example.com，',
    '参考 https://example.com?q=报告。',
    '参考 https://example.com/a?x=1&y=2；\n',
])
def test_url_mask_preserves_following_chinese_text_and_locations(prefix):
    raw = prefix + '这是一个非常好的问题。'
    _, result = run_check(raw)
    hit = next(h for h in result['hits'] if h['rule'] == 'F6')
    assert hit['offset'] == len(prefix)
    assert hit['line'] == prefix.count('\n') + 1
    assert raw[hit['offset']:].startswith(hit['matched'])


def test_strict_still_escalates_excess_connectors():
    proc, result = run_check('然而今天下雨。不过我带了伞。', genre='video', fail_on='high')
    assert proc.returncode == 1
    assert metric(result, 'W3')['flagged'] is True
    assert metric(result, 'W3')['severity'] == 'high'


def test_uniform_sentences_are_advisory_even_in_strict_genre():
    proc, result = run_check('记录已经整理完毕。' * 10, genre='wechat', fail_on='high')
    assert proc.returncode == 0
    assert metric(result, 'S2')['flagged'] is False
    assert metric(result, 'S2')['informational'] is True
    assert metric(result, 'S2')['severity'] == 'low'


@pytest.mark.parametrize('genre', ['persona', 'copy', 'video', 'weibo', 'academic'])
def test_genres_allow_short_sentence_sequences(genre):
    _, result = run_check('到家了。洗个澡。睡觉了。', genre=genre)
    assert not any(m['key'] in {'S7', 'S7b'} for m in result['metrics'])


def test_any_includes_low_candidates_but_default_does_not_fail():
    default, result = run_check('愿你平安。')
    high, _ = run_check('愿你平安。', fail_on='high')
    any_hit, _ = run_check('愿你平安。', fail_on='any')
    assert (default.returncode, high.returncode, any_hit.returncode) == (0, 0, 1)
    assert result['severity_totals'] == {'high': 0, 'mid': 0, 'low': 1}


def test_render_discloses_manual_review_and_does_not_offer_r1_pass():
    proc = subprocess.run(
        [sys.executable, str(CHECK), '-', '--genre', 'quant'],
        input='本次研究只覆盖一个市场。', text=True, capture_output=True,
    )
    assert proc.returncode == 0
    assert 'R1：' in proc.stdout
    assert '未自动判定通过或失败' in proc.stdout
    assert '不确定表达处数' not in proc.stdout
