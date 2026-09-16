#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gr-content-ai-avoid 机械自检脚本。

只定位表达模式：高频词、结构句式、密度指标，不鉴定作者或事实真伪。
C/R 层只有部分表面模式能机械提示，语义是否成立仍要靠人按 references/rules.md 判断。

用法：
    python3 check.py 稿子.md
    python3 check.py 稿子.md --genre xhs-short
    python3 check.py 稿子.md --json
    echo "文本" | python3 check.py -
    python3 check.py 稿子.md --fail-on high     # 有 🔴 命中时退出码 1

体裁：default wechat xhs-short xhs-long weibo zhihu video persona copy quant academic
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from bisect import bisect_left
from pathlib import Path

SEV_ICON = {"high": "🔴", "mid": "⚠️", "low": "💡"}
SEV_ORDER = {"high": 0, "mid": 1, "low": 2}

EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U0001F000-\U0001F2FF"
    "\U00002600-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\U0000FE0F"
    "\U00002190-\U000021FF"
    "]"
)


# --------------------------------------------------------------------------- #
# 文本预处理
# --------------------------------------------------------------------------- #

def blank_out(text: str, pattern: re.Pattern) -> str:
    """把匹配区域替换成等长空格，保持字符偏移不变。"""
    out = list(text)
    for m in pattern.finditer(text):
        for i in range(m.start(), m.end()):
            if out[i] not in "\r\n":
                out[i] = " "
    return "".join(out)


def preserve_link_labels(text: str) -> str:
    """屏蔽普通 Markdown 链接的标记和目标，保留读者可见的标签文本。"""
    pattern = re.compile(r"(?<!!)\[([^\]\n]*)\]\([^)\n]*\)")
    out = list(text)
    for m in pattern.finditer(text):
        label_start, label_end = m.span(1)
        for i in range(m.start(), m.end()):
            if not label_start <= i < label_end and out[i] not in "\r\n":
                out[i] = " "
    return "".join(out)


def mask_ranges(text: str, ranges: list[tuple[int, int]]) -> str:
    """等长屏蔽；保留 LF/CRLF，所有定位均指向原文字符偏移。"""
    out = list(text)
    for start, end in ranges:
        for i in range(start, end):
            if out[i] not in "\r\n":
                out[i] = " "
    return "".join(out)


def mask_fences(text: str) -> str:
    """支持常见 Markdown 围栏；闭合符同类且不短于开符，未闭合延续至 EOF。"""
    ranges, offset = [], 0
    opener = None
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if opener is not None:
            start, char, width = opener
            if re.fullmatch(r" {0,3}" + re.escape(char) + "{" + str(width) + r",}[ \t]*", body):
                ranges.append((start, offset + len(line)))
                opener = None
        else:
            match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", body)
            if match:
                fence, info = match.groups()
                if fence[0] != "`" or "`" not in info:
                    opener = (offset, fence[0], len(fence))
        offset += len(line)
    if opener is not None:
        ranges.append((opener[0], len(text)))
    return mask_ranges(text, ranges)


def mask_blockquotes(text: str) -> str:
    """保护显式块引用及首段懒续行；复杂嵌套和行内引语仍须人工复核。"""
    ranges, offset, in_quote = [], 0, False
    block_start = re.compile(r"^ {0,3}(?:#{1,6}(?:\s|$)|[-+*]\s|\d+[.)]\s|`{3,}|~{3,}|\|)")
    for line in text.splitlines(keepends=True):
        explicit = re.match(r"^ {0,3}>", line)
        if explicit:
            in_quote = True
        elif not line.strip() or block_start.match(line) or re.fullmatch(r" {0,3}(?:[-*_] *){3,}\s*", line):
            in_quote = False
        if in_quote:
            ranges.append((offset, offset + len(line)))
        offset += len(line)
    return mask_ranges(text, ranges)


def prose_view(text: str) -> str:
    """句段指标的散文正文视图；不改变词表/格式规则使用的可见文本视图。"""
    lines = text.splitlines(keepends=True)
    excluded: set[int] = set()
    heading = re.compile(r"^ {0,3}#{1,6}(?:\s|$)")
    list_item = re.compile(r"^([ \t]*)(?:[-+*]|\d+[.)、])[ \t]+")
    setext = re.compile(r" {0,3}(?:=+|-+)[ \t]*[\r\n]*")
    thematic = re.compile(r" {0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})[\r\n]*")
    delimiter = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
    list_indent = None
    after_blank = False
    for i, line in enumerate(lines):
        if not line.strip():
            after_blank = True
            continue
        # 分隔线优先于列表标记；它会结束列表，不能吞掉后面的正文。
        # setext 下划线修饰整个前置段落，标题可能含多行软换行。
        if setext.fullmatch(line) or thematic.fullmatch(line):
            if setext.fullmatch(line):
                j = i - 1
                while j >= 0 and lines[j].strip() and j not in excluded:
                    excluded.add(j)
                    j -= 1
            excluded.add(i)
            list_indent = None
            after_blank = False
            continue
        item = list_item.match(line)
        if item:
            list_indent = len(item.group(0).expandtabs(4))
            excluded.add(i)
            after_blank = False
            continue
        if list_indent is not None:
            indent = len(line[:len(line) - len(line.lstrip())].expandtabs(4))
            if indent >= list_indent or (not after_blank and not heading.match(line) and not line.lstrip().startswith("|")):
                excluded.add(i)
                continue
            list_indent = None
        after_blank = False
        if heading.match(line) or line.lstrip().startswith("|"):
            excluded.add(i)
        if delimiter.match(line):
            excluded.add(i)
            if i:
                excluded.add(i - 1)
            j = i + 1
            while j < len(lines) and lines[j].strip() and "|" in lines[j]:
                excluded.add(j)
                j += 1
    ranges, offset = [], 0
    for i, line in enumerate(lines):
        if i in excluded:
            ranges.append((offset, offset + len(line)))
        offset += len(line)
    return mask_ranges(text, ranges)


def preprocess(raw: str) -> str:
    """屏蔽非正文区域，并保留普通链接的可见标签文本。偏移保持不变。"""
    text = raw
    text = blank_out(text, re.compile(r"\A---\r?\n.*?\r?\n---(?:\r?\n|\Z)", re.S))
    text = mask_fences(text)
    text = mask_blockquotes(text)
    text = blank_out(text, re.compile(r"`[^`\n]+`"))
    text = blank_out(text, re.compile(r"!\[[^\]\n]*\]\([^)\n]*\)"))
    text = preserve_link_labels(text)
    # 裸 URL 遇中文标点结束，避免吞掉紧接着的中文正文。
    text = blank_out(text, re.compile(r"https?://[^\s<>\"'。，、！？；：“”‘’]+"))
    text = blank_out(text, re.compile(r"<[^>\n]{1,80}>"))
    return text


def line_index(text: str) -> list[int]:
    starts, pos = [0], 0
    for line in text.split("\n"):
        pos += len(line) + 1
        starts.append(pos)
    return starts


def line_of(starts: list[int], offset: int) -> int:
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def snippet(text: str, start: int, end: int, pad: int = 14) -> str:
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    s = text[a:b].replace("\n", " ").strip()
    return ("…" if a > 0 else "") + s + ("…" if b < len(text) else "")


def split_sentences(text: str) -> list[tuple[int, str]]:
    """按句末标点和空行切分；普通 Markdown 软换行不单独成为一句。"""
    out, start = [], 0
    boundaries = list(re.finditer(r"[。！？!?；;]+|\r?\n[ \t\r]*\n", text))
    ends = [m.end() for m in boundaries] + [len(text)]
    for end in ends:
        chunk = text[start:end]
        sentence = chunk.strip()
        if re.search(r"[一-鿿A-Za-z0-9]", sentence):
            out.append((start + len(chunk) - len(chunk.lstrip()), sentence))
        start = end
    return out


def content_len(s: str) -> int:
    """有效字符数：去掉空白和 markdown 标记符。"""
    return len(re.sub(r"[\s#>*`\-_|\[\]()。，、！？；：\"'“”‘’]", "", s))


def paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text) if content_len(p) > 0]


# --------------------------------------------------------------------------- #
# 检测
# --------------------------------------------------------------------------- #

class Hit:
    __slots__ = ("rule", "name", "sev", "start", "end", "matched", "desc", "hint")

    def __init__(self, rule, name, sev, start, end, matched, desc="", hint=""):
        self.rule, self.name, self.sev = rule, name, sev
        self.start, self.end, self.matched = start, end, matched
        self.desc, self.hint = desc, hint

    def as_dict(self, text, starts):
        return {
            "rule": self.rule,
            "name": self.name,
            "severity": self.sev,
            "line": line_of(starts, self.start),
            "offset": self.start,
            "matched": self.matched,
            "desc": self.desc,
            "snippet": snippet(text, self.start, self.end),
            "hint": self.hint,
        }


def scan_lexicon(text: str, lexicon: dict, active: set[str]) -> list[Hit]:
    """词表扫描。全局掩码去重：同一段字符只归给一条规则（按严重度优先）。"""
    mask = bytearray(len(text))
    hits: list[Hit] = []

    order = sorted(
        (k for k in lexicon if k in active),
        key=lambda k: (SEV_ORDER.get(lexicon[k].get("severity", "mid"), 1), k),
    )

    for rule in order:
        cfg = lexicon[rule]
        if cfg.get("is_positive_signal"):
            continue
        sev = cfg.get("severity", "mid")
        hint = cfg.get("hint", "")
        for w in sorted(cfg.get("words", []), key=len, reverse=True):
            if "…" in w or not w.strip():
                continue
            pos = 0
            while True:
                i = text.find(w, pos)
                if i < 0:
                    break
                pos = i + 1
                if any(mask[i:i + len(w)]):
                    continue
                for k in range(i, i + len(w)):
                    mask[k] = 1
                hits.append(Hit(rule, cfg["name"], sev, i, i + len(w), w, "", hint))
        for rx in cfg.get("regex", []):
            try:
                cre = re.compile(rx["pattern"])
            except re.error:
                continue
            for m in cre.finditer(text):
                group = rx.get("match_group", 0)
                start, end = m.span(group)
                if any(mask[start:end]):
                    continue
                for k in range(start, end):
                    mask[k] = 1
                hits.append(Hit(rule, cfg["name"], sev, start, end,
                                m.group(group), rx.get("desc", ""), hint))
    return hits


def count_non_overlapping_matches(text: str, cfg: dict) -> int:
    """按最长优先统计单条规则的词和正则，避免嵌套表达重复计数。"""
    spans: list[tuple[int, int]] = []
    for word in sorted(cfg.get("words", []), key=len, reverse=True):
        if "…" in word or not word.strip():
            continue
        spans.extend((m.start(), m.end()) for m in re.finditer(re.escape(word), text))
    for rx in cfg.get("regex", []):
        try:
            cre = re.compile(rx["pattern"])
        except re.error:
            continue
        group = rx.get("match_group", 0)
        spans.extend(m.span(group) for m in cre.finditer(text))

    mask = bytearray(len(text))
    count = 0
    for start, end in sorted(spans, key=lambda span: (-(span[1] - span[0]), span[0])):
        if any(mask[start:end]):
            continue
        for i in range(start, end):
            mask[i] = 1
        count += 1
    return count


def scan_regex_rules(text: str, rules: dict, active: set[str], chars: int) -> list[Hit]:
    hits: list[Hit] = []
    # 有效正文的位置用于窗口计数；匹配仍在原文本上进行，以保留行号和偏移。
    body_offsets = [i for i, ch in enumerate(text) if content_len(ch)]
    for rule, cfg in rules.items():
        base = rule.split("_")[0]
        if rule not in active and base not in active:
            continue
        sev = cfg.get("severity", "mid")
        hint = cfg.get("hint", "")

        if "line_patterns" in cfg:
            hits.extend(_scan_lines(text, rule, cfg, sev, hint))
            continue

        scope = cfg.get("scope")
        if scope == "head":
            n = cfg.get("head_chars", 150)
            end = body_offsets[n] if len(body_offsets) > n else len(text)
            region, base_off = text[:end], 0
        elif scope == "tail":
            n = cfg.get("tail_chars", 200)
            base_off = body_offsets[-n] if len(body_offsets) > n else 0
            region = text[base_off:]
        elif scope == "prose":
            region, base_off = prose_view(text), 0
        else:
            region, base_off = text, 0

        raw: list[Hit] = []
        for rx in cfg.get("patterns", []):
            try:
                cre = re.compile(rx["pattern"], re.M)
            except re.error:
                continue
            for m in cre.finditer(region):
                if rx.get("check") == "similar_length" and not _similar_len(m):
                    continue
                if rx.get("check") == "three_similar_items" and not _three_similar_items(m):
                    continue
                raw.append(Hit(rule, cfg["name"], sev, base_off + m.start(),
                               base_off + m.end(), m.group(0), rx.get("desc", ""), hint))

        thr = cfg.get("density_per_800")
        if thr and chars > 0:
            raw = _dense_window_hits(raw, body_offsets, thr, 800)
        hits.extend(raw)
    return hits


def _similar_len(m: re.Match) -> bool:
    gs = [g for g in m.groups() if g]
    if len(gs) < 3:
        return False
    lens = [len(g) for g in gs[:3]]
    return max(lens) - min(lens) <= 2


def _three_similar_items(m: re.Match) -> bool:
    items = m.group(0).split("、")
    if len(items) != 3:
        return False
    lens = [content_len(item) for item in items]
    return min(lens) >= 2 and max(lens) <= 8 and max(lens) - min(lens) <= 2


def _dense_window_hits(hits: list[Hit], body_offsets: list[int],
                       minimum: int, window: int) -> list[Hit]:
    """只保留参与局部高密度窗口的命中；重叠句式不重复计数。"""
    distinct: list[Hit] = []
    for hit in sorted(hits, key=lambda h: (h.start, -h.end)):
        if not distinct or hit.start >= distinct[-1].end:
            distinct.append(hit)

    starts = [bisect_left(body_offsets, h.start) for h in distinct]
    ends = [bisect_left(body_offsets, h.end) for h in distinct]
    # 差分标记所有合格窗口，避免同一命中重复输出。
    coverage = [0] * (len(distinct) + 1)
    left = 0
    for right, end in enumerate(ends):
        while left <= right and end - starts[left] > window:
            left += 1
        if right - left + 1 >= minimum:
            coverage[left] += 1
            coverage[right + 1] -= 1
    selected, depth = [], 0
    for i, hit in enumerate(distinct):
        depth += coverage[i]
        if depth:
            selected.append(hit)
    return selected


def _scan_lines(text: str, rule: str, cfg: dict, sev: str, hint: str) -> list[Hit]:
    cres = []
    for rx in cfg.get("line_patterns", []):
        try:
            cres.append((re.compile(rx["pattern"]), rx.get("desc", "")))
        except re.error:
            pass
    min_run = cfg.get("min_consecutive", 1)
    hits, run, offset = [], [], 0
    for line in text.split("\n"):
        matched = next(((offset, line, d) for cre, d in cres if cre.search(line)), None)
        if matched:
            run.append(matched)
        else:
            if len(run) >= min_run:
                o, ln, d = run[0]
                hits.append(Hit(rule, cfg["name"], sev, o, o + len(ln),
                                ln.strip()[:40], f"{d}（连续 {len(run)} 项）", hint))
            run = []
        offset += len(line) + 1
    if len(run) >= min_run:
        o, ln, d = run[0]
        hits.append(Hit(rule, cfg["name"], sev, o, o + len(ln),
                        ln.strip()[:40], f"{d}（连续 {len(run)} 项）", hint))
    return hits


def scan_empty_headers(text: str, active: set[str]) -> list[Hit]:
    """P2 结构式检测：标题下面先来一句把标题重说一遍的短句。"""
    if "P2" not in active:
        return []
    hits, lines, offset = [], text.split("\n"), 0
    offsets = []
    for ln in lines:
        offsets.append(offset)
        offset += len(ln) + 1
    for i, ln in enumerate(lines):
        m = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", ln)
        if not m:
            continue
        title = re.sub(r"[^\w一-鿿]", "", m.group(1))
        for j in range(i + 1, min(i + 4, len(lines))):
            nxt = lines[j].strip()
            if not nxt:
                continue
            if re.match(r"^([-*+>#|]|\d+[.、])", nxt):
                break
            body = re.sub(r"[^\w一-鿿]", "", nxt)
            subject = re.sub(r"^(关于|有关)", "", title)
            # 只提示原样复述或明确的空泛评价；共享字符不能证明没有新信息。
            empty = re.fullmatch(re.escape(subject) + r"(?:(?:是)?(?:很重要|非常重要|至关重要|不可忽视|值得关注))?", body)
            if len(subject) >= 2 and empty:
                hits.append(Hit("P2", "空转与预告", "mid", offsets[j],
                                offsets[j] + len(lines[j]), nxt[:30],
                                "标题下可能重复标题", "确认是否提供了新信息；有事实就保留。"))
            break
    return hits


def compute_metrics(text: str, cfg_all: dict, genre: str, active: set[str],
                    lexicon: dict) -> list[dict]:
    prose = prose_view(text)
    sents = split_sentences(prose)
    lens = [content_len(s) for _, s in sents]
    lens = [n for n in lens if n > 0]
    paras = paragraphs(prose)
    chars = content_len(text)
    k = max(chars, 1) / 1000.0
    rows = []

    def add(key, label, value, thr_txt, bad, sev, hint=""):
        rows.append({"key": key, "name": label, "value": value,
                     "threshold": thr_txt, "flagged": bad, "severity": sev, "hint": hint})

    # S2 句长变异系数
    c = cfg_all.get("S2_sentence_cv", {})
    if "S2_sentence_cv" in active and len(lens) >= c.get("min_sentences", 8):
        mean = sum(lens) / len(lens)
        sd = math.sqrt(sum((x - mean) ** 2 for x in lens) / len(lens))
        cv = sd / mean if mean else 0.0
        add("S2", "句长变异系数", round(cv, 3), "仅描述，不设优劣阈值",
            False, c.get("severity", "low"), c.get("hint", ""))
        rows[-1].update(informational=True, sample_size=len(lens))

    # S7 段末金句率
    c = cfg_all.get("S7_punchline_rate", {})
    if "S7_punchline_rate" in active and len(paras) >= c.get("min_paragraphs", 4):
        hitn = tot = 0
        for p in paras:
            ss = [content_len(s) for _, s in split_sentences(p)]
            ss = [x for x in ss if x > 0]
            if len(ss) < 2:
                continue
            tot += 1
            if ss[-1] < 0.6 * (sum(ss) / len(ss)):
                hitn += 1
        if tot >= c.get("min_paragraphs", 4):
            rate = hitn / tot
            add("S7", "段末短句比例", f"{rate:.0%} ({hitn}/{tot})",
                f"≤ {c.get('warn_above', 0.6):.0%}", rate > c.get("warn_above", 0.6),
                c.get("severity", "low"), c.get("hint", ""))

    # S7 连续短句
    c = cfg_all.get("S7_staccato_run", {})
    if "S7_staccato_run" in active and lens:
        mx = 0
        for para in paras:
            run = 0  # 不把不相邻的段落拼成短句连打。
            for _, sentence in split_sentences(para):
                n = content_len(sentence)
                run = run + 1 if 0 < n <= c.get("max_len", 8) else 0
                mx = max(mx, run)
        add("S7b", "最长连续短句", mx, f"< {c.get('min_run', 3)}",
            mx >= c.get("min_run", 3), "mid", c.get("hint", ""))

    # 密度类
    for key, label, cnt in (
        ("F1_dash_per_1k", "破折号/千字", text.count("——") + len(re.findall(r"(?<!-)--(?!-)", text))),
        ("F2_bold_per_1k", "粗体/千字", len(re.findall(r"\*\*[^*\n]+\*\*", text))),
        ("F3_emoji_per_1k", "emoji/千字", len(EMOJI_RE.findall(text))),
    ):
        c = cfg_all.get(key, {})
        if key not in active:
            continue
        thr = c.get("warn_above", 99)
        thr = c.get("genre_override", {}).get(genre, thr)
        d = cnt / k
        min_allowed = c.get("min_allowed_count", 0)
        bad = d > thr and cnt > min_allowed
        threshold = f"≤ {thr}" + (f"；总数 ≤ {min_allowed} 豁免" if min_allowed else "")
        add(key.split("_")[0], label, f"{d:.1f} ({cnt})", threshold, bad,
            c.get("severity", "mid"), c.get("hint", ""))

    # W1 密度
    c = cfg_all.get("W1_per_1k", {})
    if "W1_per_1k" in active and "W1" in lexicon:
        cnt = count_non_overlapping_matches(text, lexicon["W1"])
        d = cnt / k
        min_allowed = c.get("min_allowed_count", 0)
        bad = d > c.get("warn_above", 2.0) and cnt > min_allowed
        threshold = f"≤ {c.get('warn_above', 2.0)}" + (f"；总数 ≤ {min_allowed} 豁免" if min_allowed else "")
        add("W1", "空泛词候选/千字", f"{d:.1f} ({cnt})", threshold,
            bad, "high", "")

    # W3 连接词密度
    if "W3" in lexicon and "W3" in active and sents:
        dens = lexicon["W3"].get("density_per_sentence", {})
        thr = dens.get(genre, dens.get("default", 0.25))
        cnt = count_non_overlapping_matches(prose, lexicon["W3"])
        d = cnt / len(sents)
        min_allowed = lexicon["W3"].get("min_allowed_count", 0)
        bad = d > thr and cnt > min_allowed
        threshold = f"≤ {thr}" + (f"；总数 ≤ {min_allowed} 豁免" if min_allowed else "")
        add("W3", "连接词/句", f"{d:.2f} ({cnt}/{len(sents)})", threshold, bad,
            "mid", lexicon["W3"].get("hint", ""))

    return rows


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

def build_active(cfg: dict, genre: str) -> set[str]:
    all_keys = set(cfg["lexicon"]) | set(cfg["regex_rules"]) | set(cfg["metrics"]) | set(cfg.get("manual_rules", {}))
    skip = set(cfg["genres"].get(genre, {}).get("skip", []))
    active = {k for k in all_keys if k not in skip}
    for s in skip:  # 支持用基础 ID 屏蔽（如 skip: ["P6"]）
        active = {k for k in active if not k.startswith(s + "_") and k != s}
    return active


def analyze(raw: str, cfg: dict, genre: str) -> dict:
    text = preprocess(raw)
    active = build_active(cfg, genre)
    chars = content_len(text)
    aggregate_rules = {"W1", "W3"}

    # 聚合规则独立扫描，避免跨规则掩码吞掉超标规则的定位。
    hits = scan_lexicon(text, cfg["lexicon"], active - aggregate_rules)
    regex_hits = scan_regex_rules(text, cfg["regex_rules"], active, chars)
    # P2 的新提示冒号子规则与已有词表重叠时只保留原定位。
    p2_hits = [h for h in hits if h.rule == "P2"]
    hits += [h for h in regex_hits if h.rule != "P2_prompt_colon" or not any(
        h.start < existing.end and existing.start < h.end for existing in p2_hits)]
    hits += scan_empty_headers(text, active)

    metrics = compute_metrics(text, cfg["metrics"], genre, active, cfg["lexicon"])

    # 加严只提升已超阈值的 mid 项；依赖语义的 low 候选仍由人工判断。
    strict = set(cfg["genres"].get(genre, {}).get("strict", []))
    strict_bases = {s.split("_")[0] for s in strict}

    def is_strict(rid: str) -> bool:
        return rid in strict or rid.split("_")[0] in strict_bases

    metrics_by_key = {m["key"]: m for m in metrics}
    for rule in aggregate_rules:
        if rule not in active or rule not in cfg["lexicon"]:
            continue
        scan_text = prose_view(text) if rule == "W3" else text
        rule_hits = scan_lexicon(scan_text, {rule: cfg["lexicon"][rule]}, {rule})
        metric = metrics_by_key.get(rule)
        if metric and metric["flagged"]:
            hits.extend(rule_hits)

    if strict:
        for h in hits:
            if h.sev == "mid" and is_strict(h.rule):
                h.sev = "high"
        for m in metrics:
            if m["flagged"] and m["severity"] == "mid" and is_strict(m["key"]):
                m["severity"] = "high"

    hits.sort(key=lambda h: h.start)
    starts = line_index(text)
    prose = prose_view(text)
    sents = split_sentences(prose)

    counts: dict[str, int] = {}
    for h in hits:
        counts[h.rule] = counts.get(h.rule, 0) + 1

    return {
        "genre": genre,
        "stats": {"chars": chars, "prose_chars": content_len(prose),
                  "sentences": len(sents), "paragraphs": len(paragraphs(prose))},
        "analysis_scope": {
            "chars": "可见文本；排除代码、块引用及其他已屏蔽内容",
            "sentence_metrics": "散文正文；另排除标题、表格和列表；软换行不分句",
            "limitations": "有限 Markdown 支持；行内引语和复杂嵌套需人工复核",
        },
        "metrics": metrics,
        "manual_review": {k: v for k, v in cfg.get("manual_rules", {}).items() if k in active},
        "hits": [h.as_dict(text, starts) for h in hits],
        "counts": counts,
        "severity_totals": {
            "high": sum(1 for h in hits if h.sev == "high" and h.rule not in aggregate_rules) +
                    sum(1 for m in metrics if m["flagged"] and m["severity"] == "high"),
            "mid": sum(1 for h in hits if h.sev == "mid" and h.rule not in aggregate_rules) +
                   sum(1 for m in metrics if m["flagged"] and m["severity"] == "mid"),
            "low": sum(1 for h in hits if h.sev == "low" and h.rule not in aggregate_rules) +
                   sum(1 for m in metrics if m["flagged"] and m["severity"] == "low"),
        },
        "strict": cfg["genres"].get(genre, {}).get("strict", []),
    }


def render(res: dict, source: str, cfg: dict) -> str:
    st, out = res["stats"], []
    out.append("# gr-content-ai-avoid 自检报告\n")
    out.append(f"来源：{source}　体裁：{res['genre']}　"
               f"可见文本 {st['chars']} 字；散文正文 {st['prose_chars']} 字 / "
               f"{st['sentences']} 句 / {st['paragraphs']} 段\n")

    out.append("\n## 量化指标\n")
    if res["metrics"]:
        out.append("| 指标 | 当前值 | 阈值 | 判定 |")
        out.append("| --- | --- | --- | --- |")
        for m in res["metrics"]:
            mark = f"{SEV_ICON.get(m['severity'], '⚠️')} 超标" if m["flagged"] else "✅"
            if m.get("informational"):
                mark = "仅描述"
            out.append(f"| {m['key']} {m['name']} | {m['value']} | {m['threshold']} | {mark} |")
    else:
        out.append("（文本过短，跳过量化指标）")

    out.append("\n## 命中明细\n")
    if not res["hits"]:
        out.append("没有命中词表和句式规则。")
    else:
        for h in res["hits"]:
            d = f"（{h['desc']}）" if h["desc"] else ""
            out.append(f"- L{h['line']} {SEV_ICON.get(h['severity'],'⚠️')} `{h['rule']}` "
                       f"**{h['matched']}**{d}　> {h['snippet']}")

    out.append("\n## 汇总\n")
    tot = res["severity_totals"]
    out.append(f"🔴 {tot['high']} 项　⚠️ {tot['mid']} 项　💡 {tot['low']} 项（聚合指标按项计数）")
    if res["counts"]:
        top = sorted(res["counts"].items(), key=lambda kv: -kv[1])[:6]
        names = {**{k: v["name"] for k, v in cfg["lexicon"].items()},
                 **{k: v["name"] for k, v in cfg["regex_rules"].items()}}
        out.append("候选定位：" + "　".join(f"{k} {names.get(k,'')}({v})" for k, v in top))
    if res["strict"]:
        out.append(f"本体裁加严：{', '.join(res['strict'])}")

    out.append("\n---\n")
    if res["manual_review"]:
        out.append("人工检查（未自动判定通过或失败）：")
        out.extend(f"- {k}：{v}" for k, v in res["manual_review"].items())
    out.append("脚本只查机械指标，**每一处都要人工复核再改**，会有误伤。")
    out.append(res["analysis_scope"]["limitations"] + "；S2 不参与命中与退出码。")
    out.append("C/R 层只有部分表面模式能机械提示，语义是否成立仍要按 `references/rules.md` 人工判断。")
    out.append("观点、经验和分析类内容尤其要确认是否如实写明判断边界；没有真实不确定性时不要硬加。")
    out.append("引文、字面用法和作者习惯需结合上下文保留。合理命中不必清零；无命中也不证明事实正确或出自人类。")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="gr-content-ai-avoid 机械自检")
    ap.add_argument("path", help="待检文件路径，或 - 表示从 stdin 读")
    ap.add_argument("--genre", default="default", help="体裁，见 references/genre-profiles.md")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--patterns", default=None, help="自定义 patterns.json 路径")
    ap.add_argument("--fail-on", choices=["never", "high", "any"], default="never",
                    help="never 不因命中失败；high 仅高优先项；any 包括 low 候选。输入错误均返回 2")
    args = ap.parse_args()

    pfile = Path(args.patterns) if args.patterns else Path(__file__).with_name("patterns.json")
    if not pfile.exists():
        print(f"找不到词表文件：{pfile}", file=sys.stderr)
        return 2
    try:
        cfg = json.loads(pfile.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError) as e:
        print(f"patterns.json 解析失败：{e}", file=sys.stderr)
        return 2

    if args.genre not in cfg["genres"]:
        print(f"未知体裁 {args.genre}，可选：{', '.join(cfg['genres'])}", file=sys.stderr)
        return 2

    if args.path == "-":
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(newline="")
        raw, source = sys.stdin.read(), "stdin"
    else:
        p = Path(args.path)
        if not p.exists():
            print(f"找不到文件：{p}", file=sys.stderr)
            return 2
        if not p.is_file():
            print(f"不是普通文件：{p}", file=sys.stderr)
            return 2
        try:
            with p.open("r", encoding="utf-8", errors="replace", newline="") as stream:
                raw = stream.read()
        except OSError as e:
            print(f"读取文件失败：{p}：{e}", file=sys.stderr)
            return 2
        source = p.name

    if not raw.strip():
        print("文件为空。", file=sys.stderr)
        return 2

    res = analyze(raw, cfg, args.genre)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json
          else render(res, source, cfg))

    tot = res["severity_totals"]
    if args.fail_on == "high" and tot["high"] > 0:
        return 1
    if args.fail_on == "any" and any(tot.values()):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
