"""机械回归：保护范围、统计分母、弱信号与定位；不测作者身份或改写自然度。"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "gr-content-ai-avoid"
SPEC = importlib.util.spec_from_file_location("gr_ai_check_views", SKILL / "scripts" / "check.py")
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)
CONFIG = json.loads((SKILL / "scripts" / "patterns.json").read_text(encoding="utf-8"))


def analyze(raw: str, genre: str = "default") -> dict:
    return CHECK.analyze(raw, CONFIG, genre)


def metric(result: dict, key: str) -> dict:
    return next(row for row in result["metrics"] if row["key"] == key)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("claimed_prefix", [0, 2])
def test_r3_lexicon_count_and_locations_share_overlap_priority(reverse, claimed_prefix):
    raw = "虽然而且"
    words = ["然而", "虽然", "而且"]
    if reverse:
        words.reverse()
    cfg = {"name": "连接词", "words": words, "severity": "mid"}
    claimed = bytearray([1] * claimed_prefix + [0] * (len(raw) - claimed_prefix))
    hits = CHECK.scan_lexicon(raw, {"W3": cfg}, {"W3"}, claimed)
    expected = [(0, "虽然"), (2, "而且")] if not claimed_prefix else [(1, "然而")]
    assert [(h.start, h.matched) for h in hits] == expected
    assert CHECK.count_non_overlapping_matches(raw, cfg, claimed) == len(hits)


@pytest.mark.parametrize("words, regex, expected", [
    (["然而"], [{"pattern": "虽然|而且"}], [(0, "虽然"), (2, "而且")]),
    (["虽然", "而且"], [{"pattern": "然而且"}], [(1, "然而且")]),
])
def test_r3_words_and_regex_share_longest_then_position_priority(words, regex, expected):
    raw = "虽然而且"
    cfg = {"name": "连接词", "words": words, "regex": regex, "severity": "mid"}
    hits = CHECK.scan_lexicon(raw, {"W3": cfg}, {"W3"})
    assert [(h.start, h.matched) for h in hits] == expected
    assert CHECK.count_non_overlapping_matches(raw, cfg) == len(hits)


@pytest.mark.parametrize("block", [
    "```text\n这是一个非常好的问题。\n```",
    "~~~text\n这是一个非常好的问题。\n~~~",
    "````md\n```text\n这是一个非常好的问题。\n```\n````",
    "```text\n~~~\n这是一个非常好的问题。\n~~~\n```",
    "```text\n```not-a-close\n这是一个非常好的问题。\n````",
    "   ````text\n这是一个非常好的问题。\n   `````  ",
    "> 这是一个非常好的问题。",
    "> 引用开始。\n这是一个非常好的问题。",
    "> 引用开始。\n>\n>> 这是一个非常好的问题。",
])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_protected_blocks_do_not_emit_hits_and_keep_following_locations(block, newline):
    prefix = (block + "\n\n").replace("\n", newline)
    raw = prefix + "这是一个非常好的问题。"
    result = analyze(raw)
    hits = [h for h in result["hits"] if h["rule"] == "F6"]
    assert len(hits) == 1
    assert hits[0]["offset"] == len(prefix)
    assert hits[0]["line"] == prefix.count("\n") + 1
    masked = CHECK.preprocess(raw)
    assert len(masked) == len(raw)
    assert [(i, c) for i, c in enumerate(masked) if c in "\r\n"] == [
        (i, c) for i, c in enumerate(raw) if c in "\r\n"]


@pytest.mark.parametrize("raw", [
    "```text\n这是一个非常好的问题。",
    "````text\n```\n这是一个非常好的问题。",
    "~~~text\n```\n这是一个非常好的问题。",
])
def test_unclosed_fence_is_protected_to_eof(raw):
    result = analyze(raw)
    assert result["hits"] == []
    assert result["stats"]["chars"] == 0


@pytest.mark.parametrize("block", [
    "# 然而\n## 此外",
    "然而\n===\n\n此外\n---",
    "- 然而，步骤甲。\n- 此外，步骤乙。",
    "+ 然而，步骤甲。\n+ 此外，步骤乙。",
    "1. 然而，步骤甲。\n2. 此外，步骤乙。",
    "1) 然而，步骤甲。\n2) 此外，步骤乙。",
    "1、 然而，步骤甲。\n2、 此外，步骤乙。",
    "- 步骤甲。\n  然而，继续步骤。\n\n  此外，还有说明。",
    "- 步骤甲。\n然而，这行是列表段落的懒续行。\n此外，继续说明。",
    "| 标题 | 解释 |\n| --- | --- |\n| 然而 | 此外 |",
    "名称 | 解释\n--- | ---\n然而 | 此外",
])
def test_sentence_metrics_and_connector_hits_ignore_layout_blocks(block):
    prose = "今天已经完成数据整理。明天将核对原始记录。"
    result = analyze(block + "\n\n" + prose)
    assert result["stats"]["sentences"] == 2
    assert result["stats"]["paragraphs"] == 1
    assert result["stats"]["prose_chars"] == CHECK.content_len(prose)
    assert metric(result, "W3")["value"] == "0.00 (0/2)"
    assert not any(h["rule"] == "W3" for h in result["hits"])


def test_connector_numerator_denominator_and_locations_share_view():
    prefix = "# 然而\n\n- 此外\n\n| 项目 | 值 |\n| --- | --- |\n| 因此 | 1 |\n\n"
    prose = "然而今天下雨。不过我带了伞。"
    result = analyze(prefix + prose)
    assert metric(result, "W3")["value"] == "1.00 (2/2)"
    hits = [h for h in result["hits"] if h["rule"] == "W3"]
    assert [h["matched"] for h in hits] == ["然而", "不过"]
    assert all(h["offset"] >= len(prefix) for h in hits)


def test_prose_mask_does_not_silence_lexical_or_format_rules():
    raw = "# 这是一个非常好的问题\n\n- **甲：** 内容一。\n- **乙：** 内容二。\n- **丙：** 内容三。"
    result = analyze(raw)
    assert any(h["rule"] == "F6" for h in result["hits"])
    assert any(h["rule"] == "P6" for h in result["hits"])
    assert result["stats"]["sentences"] == 0


def test_soft_line_wrap_does_not_create_sentence_or_paragraph():
    prose = "今天已经完成\n原始数据的整理。明天再核对来源。"
    result = analyze(prose)
    assert result["stats"]["sentences"] == 2
    assert result["stats"]["paragraphs"] == 1
    assert metric(result, "W3")["value"] == "0.00 (0/2)"
    wrapped = "  今天\n完成。\n\n  明天继续。"
    assert CHECK.split_sentences(wrapped)[1][0] == wrapped.index("明天")


@pytest.mark.parametrize("divider", ["***", "* * *", "---", "- - -", "___", "_ _ _"])
@pytest.mark.parametrize("prefix", ["", "- 条目。\n"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_thematic_break_ends_list_without_hiding_following_prose(divider, prefix, newline):
    prose = "然而今天下雨。不过我带了伞。"
    raw = (prefix + divider + "\n" + prose).replace("\n", newline)
    result = analyze(raw, "video")
    assert result["stats"]["prose_chars"] == CHECK.content_len(prose)
    assert result["stats"]["sentences"] == 2
    assert metric(result, "W3")["value"] == "1.00 (2/2)"
    assert metric(result, "W3")["flagged"] is True
    hits = [h for h in result["hits"] if h["rule"] == "W3"]
    assert [h["offset"] for h in hits] == [raw.index("然而"), raw.index("不过")]
    assert result["severity_totals"]["high"] > 0


@pytest.mark.parametrize("underline", ["===", "---"])
@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_multiline_setext_heading_is_fully_excluded(underline, newline):
    raw = ("然而\n此外\n检查说明\n" + underline + "\n\n普通正文。").replace("\n", newline)
    result = analyze(raw, "video")
    assert result["stats"]["prose_chars"] == CHECK.content_len("普通正文。")
    assert result["stats"]["sentences"] == 1
    assert metric(result, "W3")["value"] == "0.00 (0/1)"
    assert result["severity_totals"]["high"] == 0
    assert not any(h["rule"] == "W3" for h in result["hits"])


@pytest.mark.parametrize("separator", ["\n\n", "\n# 新章节\n", "\n> 引文内容\n\n", "\n```\n例子\n```\n"])
def test_staccato_does_not_cross_paragraph_or_excluded_block(separator):
    result = analyze(separator.join(["到家了。", "洗个澡。", "睡觉了。"]))
    assert metric(result, "S7b")["value"] == 1
    assert metric(result, "S7b")["flagged"] is False


def test_staccato_within_one_paragraph_remains_visible():
    assert metric(analyze("到家了。洗个澡。睡觉了。"), "S7b")["flagged"] is True


def test_punchline_sample_size_counts_only_eligible_paragraphs():
    long_para = "这一段先完整交代已经核实的过程和具体的变化。结束。"
    result = analyze("记录甲。\n\n记录乙。\n\n记录丙。\n\n" + long_para)
    assert not any(m["key"] == "S7" for m in result["metrics"])
    valid = analyze("\n\n".join([long_para] * 4))
    assert metric(valid, "S7")["value"] == "100% (4/4)"
    assert metric(valid, "S7")["flagged"] is True


@pytest.mark.parametrize("genre", list(CONFIG["genres"]))
def test_s1_is_manual_in_every_genre_without_shape_hits(genre):
    result = analyze("苹果、香蕉、葡萄。", genre)
    assert "S1" in result["manual_review"]
    assert not any(h["rule"] == "S1" for h in result["hits"])


def test_cv_is_descriptive_and_never_contributes_to_severity():
    result = analyze("这一批原始记录已经整理完毕。" * 10, "academic")
    cv = metric(result, "S2")
    assert cv["value"] == 0
    assert cv["informational"] is True
    assert cv["sample_size"] == 10
    assert cv["flagged"] is False
    assert result["severity_totals"] == {"high": 0, "mid": 0, "low": 0}
    report = CHECK.render(result, "fixture", CONFIG)
    row = next(line for line in report.splitlines() if line.startswith("| S2 "))
    assert "仅描述" in row and "✅" not in row and "超标" not in row


@pytest.mark.parametrize("prefix", ["一句话总结：", "核心是：", "结论是:", "重点是：", "关键是："])
def test_prompt_colon_is_a_low_priority_prose_candidate(prefix):
    result = analyze(prefix + "今天不加仓。")
    hits = [h for h in result["hits"] if h["rule"] == "P2_prompt_colon"]
    assert len(hits) == 1 and hits[0]["severity"] == "low"
    assert hits[0]["offset"] == 0


@pytest.mark.parametrize("raw", [
    "会议时间：09:30。", "回撤：净值从高点下降的幅度。",
    "他说：今天不加仓。", "这段话中的关键是：不要丢信息。",
    "# 核心是：今天不加仓", "- 核心是：今天不加仓。",
    "1. 核心是：今天不加仓。", "| 核心是：今天不加仓 |",
    "`核心是：今天不加仓`", "> 核心是：今天不加仓。",
    "```\n核心是：今天不加仓。\n```",
])
def test_prompt_colon_preserves_non_prompt_and_protected_cases(raw):
    assert not any(h["rule"] == "P2_prompt_colon" for h in analyze(raw)["hits"])


def test_prompt_colon_inherits_p2_genre_exemption():
    assert not any(h["rule"].startswith("P2") for h in analyze("核心是：今天不加仓。", "video")["hits"])


def test_s3_does_not_build_one_match_across_lines():
    raw = ("与其说天气变好\n不如说风小了。\n") * 3
    assert not any(h["rule"] == "S3" for h in analyze(raw)["hits"])


@pytest.mark.parametrize("word", ["在某些情况下", "在大多数情况下", "在这种情况下"])
def test_scope_qualifiers_are_not_standalone_w2_triggers(word):
    assert not any(h["rule"] == "W2" for h in analyze(word + "可能略有改善。")["hits"])


def test_config_patterns_compile_and_rule_inventory_stays_consistent():
    for section in ("lexicon", "regex_rules"):
        for rule in CONFIG[section].values():
            for field in ("regex", "patterns", "line_patterns"):
                for item in rule.get(field, []):
                    re.compile(item["pattern"])
    mechanical = {key.split("_")[0] for section in ("lexicon", "regex_rules", "metrics") for key in CONFIG[section]}
    manual = set(CONFIG["manual_rules"])
    assert len(mechanical) == 31 and len(manual) == 8
    assert not mechanical & manual
    assert len(mechanical | manual) == 39
    rules_text = (SKILL / "references" / "rules.md").read_text(encoding="utf-8")
    assert set(re.findall(r"^## ([WSPCRF]\d+) ·", rules_text, re.M)) == mechanical | manual


def test_custom_s1_regex_configuration_still_works():
    config = copy.deepcopy(CONFIG)
    config["regex_rules"]["S1"] = {
        "name": "custom", "severity": "low",
        "patterns": [{"pattern": "(甲甲)、(乙乙)、(丙丙)", "check": "similar_length"}],
    }
    result = CHECK.analyze("甲甲、乙乙、丙丙。", config, "default")
    assert any(h["rule"] == "S1" for h in result["hits"])


def test_unreadable_patterns_path_returns_input_error(tmp_path):
    proc = subprocess.run([sys.executable, str(SKILL / "scripts" / "check.py"), "-", "--patterns", str(tmp_path)],
                          input="正文。", text=True, capture_output=True, timeout=10)
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr


def test_crlf_file_preserves_original_character_offsets(tmp_path):
    raw = "```text\r\n这是一个非常好的问题。\r\n```\r\n\r\n这是一个非常好的问题。"
    path = tmp_path / "draft.md"
    path.write_bytes(raw.encode("utf-8"))
    proc = subprocess.run([sys.executable, str(SKILL / "scripts" / "check.py"), str(path), "--json"],
                          text=True, capture_output=True, timeout=10)
    result = json.loads(proc.stdout)
    hit = next(h for h in result["hits"] if h["rule"] == "F6")
    assert hit["offset"] == raw.rindex("这是一个非常好的问题")
    assert hit["line"] == 5


def test_prompt_colon_does_not_duplicate_an_existing_p2_location():
    config = copy.deepcopy(CONFIG)
    config["lexicon"]["P2"]["words"].append("核心是")
    result = CHECK.analyze("核心是：今天不加仓。", config, "default")
    hits = [h for h in result["hits"] if h["rule"].startswith("P2")]
    assert len(hits) == 1 and hits[0]["rule"] == "P2"


def test_crlf_stdin_preserves_original_character_offsets():
    raw = "> 原话。\r\n\r\n这是一个非常好的问题。"
    proc = subprocess.run([sys.executable, str(SKILL / "scripts" / "check.py"), "-", "--json"],
                          input=raw.encode("utf-8"), capture_output=True, timeout=10)
    result = json.loads(proc.stdout)
    hit = next(h for h in result["hits"] if h["rule"] == "F6")
    assert hit["offset"] == raw.index("这是一个非常好的问题")
    assert hit["line"] == 3
