#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gr-content-ai-avoid 机械自检脚本。

只检查可量化的 AI 写作指纹：高频词、结构句式、密度指标。
语义层规则（C 层的判断、R 层的真实感）脚本测不了，靠人按 references/rules.md 过。

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

SENT_END = "。！？!?；;\n"


# --------------------------------------------------------------------------- #
# 文本预处理
# --------------------------------------------------------------------------- #

def blank_out(text: str, pattern: re.Pattern) -> str:
    """把匹配区域替换成等长空格，保持字符偏移不变。"""
    out = list(text)
    for m in pattern.finditer(text):
        for i in range(m.start(), m.end()):
            if out[i] != "\n":
                out[i] = " "
    return "".join(out)


def preprocess(raw: str) -> str:
    """屏蔽 frontmatter、代码块、行内代码、URL、HTML 标签、图片。偏移保持不变。"""
    text = raw
    text = blank_out(text, re.compile(r"\A---\n.*?\n---\n", re.S))
    text = blank_out(text, re.compile(r"```.*?```", re.S))
    text = blank_out(text, re.compile(r"~~~.*?~~~", re.S))
    text = blank_out(text, re.compile(r"`[^`\n]+`"))
    text = blank_out(text, re.compile(r"!?\[[^\]\n]*\]\([^)\n]*\)"))
    text = blank_out(text, re.compile(r"https?://\S+"))
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
    """返回 [(起始偏移, 句子文本)]，只保留含中文/字母数字的句子。"""
    out, buf, start = [], [], 0
    for i, ch in enumerate(text):
        if not buf:
            start = i
        buf.append(ch)
        if ch in SENT_END:
            s = "".join(buf).strip()
            if re.search(r"[一-鿿A-Za-z0-9]", s):
                out.append((start, s))
            buf = []
    if buf:
        s = "".join(buf).strip()
        if re.search(r"[一-鿿A-Za-z0-9]", s):
            out.append((start, s))
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
                if any(mask[m.start():m.end()]):
                    continue
                for k in range(m.start(), m.end()):
                    mask[k] = 1
                hits.append(Hit(rule, cfg["name"], sev, m.start(), m.end(),
                                m.group(0), rx.get("desc", ""), hint))
    return hits


def count_positive(text: str, cfg: dict) -> int:
    return sum(text.count(w) for w in cfg.get("words", []))


def scan_regex_rules(text: str, rules: dict, active: set[str], chars: int) -> list[Hit]:
    hits: list[Hit] = []
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
            region, base_off = text[: cfg.get("head_chars", 150)], 0
        elif scope == "tail":
            n = cfg.get("tail_chars", 200)
            base_off = max(0, len(text) - n)
            region = text[base_off:]
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
                raw.append(Hit(rule, cfg["name"], sev, base_off + m.start(),
                               base_off + m.end(), m.group(0), rx.get("desc", ""), hint))

        thr = cfg.get("density_per_800")
        if thr and chars > 0:
            allowed = max(thr, math.ceil(chars / 800 * thr))
            if len(raw) < allowed:
                continue
        hits.extend(raw)
    return hits


def _similar_len(m: re.Match) -> bool:
    gs = [g for g in m.groups() if g]
    if len(gs) < 3:
        return False
    lens = [len(g) for g in gs[:3]]
    return max(lens) - min(lens) <= 2


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
            shared = len(set(title) & set(body))
            if content_len(nxt) <= 15 and shared >= 2:
                hits.append(Hit("P2", "空转与预告", "mid", offsets[j],
                                offsets[j] + len(lines[j]), nxt[:30],
                                "标题下的空转句", "标题下第一句就写真内容。"))
            break
    return hits


def compute_metrics(text: str, cfg_all: dict, genre: str, active: set[str],
                    lexicon: dict) -> list[dict]:
    sents = split_sentences(text)
    lens = [content_len(s) for _, s in sents]
    lens = [n for n in lens if n > 0]
    paras = paragraphs(text)
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
        strong = cv < c.get("strong_below", 0.25)
        add("S2", "句长变异系数", round(cv, 3), f"≥ {c.get('warn_below', 0.35)}",
            cv < c.get("warn_below", 0.35), "high" if strong else "mid", c.get("hint", ""))

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
        if tot:
            rate = hitn / tot
            add("S7", "段末金句率", f"{rate:.0%} ({hitn}/{tot})",
                f"≤ {c.get('warn_above', 0.6):.0%}", rate > c.get("warn_above", 0.6),
                "mid", c.get("hint", ""))

    # S7 连续短句
    c = cfg_all.get("S7_staccato_run", {})
    if "S7_staccato_run" in active and lens:
        mx = run = 0
        for n in lens:
            run = run + 1 if n <= c.get("max_len", 8) else 0
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
        add(key.split("_")[0], label, f"{d:.1f} ({cnt})", f"≤ {thr}", d > thr,
            c.get("severity", "mid"), c.get("hint", ""))

    # W1 密度
    c = cfg_all.get("W1_per_1k", {})
    if "W1_per_1k" in active and "W1" in lexicon:
        cnt = sum(text.count(w) for w in lexicon["W1"].get("words", []))
        d = cnt / k
        add("W1", "AI 高频词/千字", f"{d:.1f} ({cnt})", f"≤ {c.get('warn_above', 2.0)}",
            d > c.get("warn_above", 2.0), "high", "")

    # W3 连接词密度
    if "W3" in lexicon and "W3" in active and sents:
        dens = lexicon["W3"].get("density_per_sentence", {})
        thr = dens.get(genre, dens.get("default", 0.25))
        cnt = sum(text.count(w) for w in lexicon["W3"].get("words", []))
        d = cnt / len(sents)
        add("W3", "连接词/句", f"{d:.2f} ({cnt}/{len(sents)})", f"≤ {thr}", d > thr,
            "mid", lexicon["W3"].get("hint", ""))

    # R1 不确定表达（越少越糟）
    c = cfg_all.get("R1_uncertainty_count", {})
    key = "R1_uncertainty_markers"
    if "R1_uncertainty_count" in active and key in lexicon and chars >= c.get("min_chars", 400):
        cnt = count_positive(text, lexicon[key])
        add("R1", "不确定表达处数", cnt, f"≥ {c.get('warn_below', 1)}",
            cnt < c.get("warn_below", 1), "high", c.get("hint", ""))

    return rows


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

def build_active(cfg: dict, genre: str) -> set[str]:
    all_keys = set(cfg["lexicon"]) | set(cfg["regex_rules"]) | set(cfg["metrics"])
    skip = set(cfg["genres"].get(genre, {}).get("skip", []))
    active = {k for k in all_keys if k not in skip}
    for s in skip:  # 支持用基础 ID 屏蔽（如 skip: ["P6"]）
        active = {k for k in active if not k.startswith(s + "_") and k != s}
    return active


def analyze(raw: str, cfg: dict, genre: str) -> dict:
    text = preprocess(raw)
    active = build_active(cfg, genre)
    chars = content_len(text)

    hits = scan_lexicon(text, cfg["lexicon"], active)
    hits += scan_regex_rules(text, cfg["regex_rules"], active, chars)
    hits += scan_empty_headers(text, active)
    hits.sort(key=lambda h: h.start)

    metrics = compute_metrics(text, cfg["metrics"], genre, active, cfg["lexicon"])

    # 体裁加严：strict 列表里的规则，命中一律按强信号报
    strict = set(cfg["genres"].get(genre, {}).get("strict", []))
    if strict:
        def is_strict(rid: str) -> bool:
            return rid in strict or rid.split("_")[0] in {s.split("_")[0] for s in strict}
        for h in hits:
            if is_strict(h.rule):
                h.sev = "high"
        for m in metrics:
            if m["flagged"] and is_strict(m["key"]):
                m["severity"] = "high"

    starts = line_index(text)
    sents = split_sentences(text)

    counts: dict[str, int] = {}
    for h in hits:
        counts[h.rule] = counts.get(h.rule, 0) + 1

    return {
        "genre": genre,
        "stats": {"chars": chars, "sentences": len(sents), "paragraphs": len(paragraphs(text))},
        "metrics": metrics,
        "hits": [h.as_dict(text, starts) for h in hits],
        "counts": counts,
        "severity_totals": {
            "high": sum(1 for h in hits if h.sev == "high") +
                    sum(1 for m in metrics if m["flagged"] and m["severity"] == "high"),
            "mid": sum(1 for h in hits if h.sev == "mid") +
                   sum(1 for m in metrics if m["flagged"] and m["severity"] == "mid"),
        },
        "strict": cfg["genres"].get(genre, {}).get("strict", []),
    }


def render(res: dict, source: str, cfg: dict) -> str:
    st, out = res["stats"], []
    out.append("# gr-content-ai-avoid 自检报告\n")
    out.append(f"来源：{source}　体裁：{res['genre']}　"
               f"正文 {st['chars']} 字 / {st['sentences']} 句 / {st['paragraphs']} 段\n")

    out.append("\n## 量化指标\n")
    if res["metrics"]:
        out.append("| 指标 | 当前值 | 阈值 | 判定 |")
        out.append("| --- | --- | --- | --- |")
        for m in res["metrics"]:
            mark = f"{SEV_ICON.get(m['severity'], '⚠️')} 超标" if m["flagged"] else "✅"
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
    out.append(f"🔴 {tot['high']} 处　⚠️ {tot['mid']} 处")
    if res["counts"]:
        top = sorted(res["counts"].items(), key=lambda kv: -kv[1])[:6]
        names = {**{k: v["name"] for k, v in cfg["lexicon"].items()},
                 **{k: v["name"] for k, v in cfg["regex_rules"].items()}}
        out.append("优先处理：" + "　".join(f"{k} {names.get(k,'')}({v})" for k, v in top))
    if res["strict"]:
        out.append(f"本体裁加严：{', '.join(res['strict'])}")

    out.append("\n---\n")
    out.append("脚本只查机械指标，**每一处都要人工复核再改**，会有误伤。")
    out.append("语义层（C 层内容套路、R 层真实感）脚本测不了，按 `references/rules.md` 自己过一遍。")
    out.append("尤其确认：全文有没有一处承认「我不确定 / 我没想清楚」（R1）——没有的话一定像 AI。")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="gr-content-ai-avoid 机械自检")
    ap.add_argument("path", help="待检文件路径，或 - 表示从 stdin 读")
    ap.add_argument("--genre", default="default", help="体裁，见 references/genre-profiles.md")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--patterns", default=None, help="自定义 patterns.json 路径")
    ap.add_argument("--fail-on", choices=["never", "high", "any"], default="never",
                    help="命中时的退出码策略，默认 never（总是 0）")
    args = ap.parse_args()

    pfile = Path(args.patterns) if args.patterns else Path(__file__).with_name("patterns.json")
    if not pfile.exists():
        print(f"找不到词表文件：{pfile}", file=sys.stderr)
        return 2
    try:
        cfg = json.loads(pfile.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"patterns.json 解析失败：{e}", file=sys.stderr)
        return 2

    if args.genre not in cfg["genres"]:
        print(f"未知体裁 {args.genre}，可选：{', '.join(cfg['genres'])}", file=sys.stderr)
        return 2

    if args.path == "-":
        raw, source = sys.stdin.read(), "stdin"
    else:
        p = Path(args.path)
        if not p.exists():
            print(f"找不到文件：{p}", file=sys.stderr)
            return 2
        raw, source = p.read_text(encoding="utf-8", errors="replace"), p.name

    if not raw.strip():
        print("文件为空。", file=sys.stderr)
        return 2

    res = analyze(raw, cfg, args.genre)
    print(json.dumps(res, ensure_ascii=False, indent=2) if args.json
          else render(res, source, cfg))

    tot = res["severity_totals"]
    if args.fail_on == "high" and tot["high"] > 0:
        return 1
    if args.fail_on == "any" and (tot["high"] or tot["mid"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
