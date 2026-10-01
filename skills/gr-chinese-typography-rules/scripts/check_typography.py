#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gr-chinese-typography-rules 机械自检脚本。

只报告，不改写。分两级：

    error —— 按本技能默认风格可明确定位的问题，仍需确认保护边界
    warn  —— 需要语境判断的候选问题（单位空格、引号风格、中英文粘连……），人工确认后再改

屏蔽常见 Markdown 代码、链接目标、引用块、frontmatter、HTML 标签与注释、显式公式。
这不是完整 Markdown 解析器；普通引号中的原话、未标记配置、命令与标识符仍需人工识别。
输入统一按 LF 处理（自动归一化 CRLF）。

用法：
    python3 check_typography.py 稿子.md
    python3 check_typography.py 稿子.md --level error   # 只看默认规则问题
    python3 check_typography.py 稿子.md --json
    python3 check_typography.py 稿子.md --profile finance # 启用金融正文规则
    python3 check_typography.py 稿子.md --fail-on error # 有 error 时退出码 1
    echo "文本" | python3 check_typography.py -
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CJK = (
    "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    "\U00020000-\U0002a6df\U0002a700-\U0002ee5f"
    "\U0002f800-\U0002fa1f\U00030000-\U0003347f"
)

LEVEL_ICON = {"error": "🔴", "warn": "⚠️"}


# --------------------------------------------------------------------------- #
# 预处理：屏蔽保护内容，偏移保持不变
# --------------------------------------------------------------------------- #

URL_CHARS = r"A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%"

# 屏蔽用的占位符：私用区字符，不会被任何规则当作真实空白或标点匹配，
# 避免「屏蔽掉的区域」被规则误判成两侧字符之间存在真实空格（见 cjk-md-space 一类问题）。
MASK_CHAR = ""

MASK_PATTERNS = [
    re.compile(r"<!--.*?(?:-->|\Z)", re.S),
    re.compile(r"(?<!\\)\$\$.*?(?<!\\)\$\$", re.S),
    re.compile(r"(?<![\\$])\$(?!\s)(?:[^$\n]*?[^\s\\$])\$(?![\d$])"),
    re.compile(r"\\\(.*?\\\)|\\\[.*?\\\]", re.S),
    re.compile(rf"https?://[{URL_CHARS}]+"),           # 裸 URL（不吞后面的中文正文）
    re.compile(r"</?[A-Za-z][^>\n]*>|<![A-Z][^>\n]*>"),
    re.compile(r"^[ ]{0,3}\[[^]\n]+\]:[^\n]*(?:\n[ \t]+[\"'(][^\n]*)?", re.M),
]

ISO_DATE = re.compile(r"(?<![0-9-])\d{4}-(?:0[1-9]|1[0-2])(?:-\d{2})?(?![0-9-])")
FINANCE_RULES = {"thousands", "math-space"}
# 有明确标签或结构的编号；只屏蔽数值，附近正文仍须检查。
IDENTIFIERS = [
    re.compile(r"(?<![A-Za-z0-9])ISBN(?:-1[03])?[ \t]*[:：]?[ \t]*(?P<value>\d[\d-]*[\dXx])\b", re.I),
    re.compile(r"(?:电话|手机|联系|Tel\.?)[ \t]*[:：]?[ \t]*(?P<value>(?:\+86[- ]?)?(?:1[3-9]\d{9}|0\d{2,3}-\d{7,8}))(?!\d)", re.I),
    re.compile(r"(?:股票代码|证券代码|代码)[ \t]*[:：]?[ \t]*(?P<value>\d{6})(?!\d)"),
    re.compile(r"[（(](?P<value>\d{6})[）)]"),
]


def blank_span(out: list[str], start: int, end: int) -> None:
    for i in range(start, end):
        if out[i] != "\n":
            out[i] = MASK_CHAR


def blank_out(text: str, pattern: re.Pattern) -> str:
    """把匹配区域替换成等长占位符，保持字符偏移不变。"""
    out = list(text)
    for m in pattern.finditer(text):
        blank_span(out, m.start(), m.end())
    return "".join(out)


def mask_blocks(text: str) -> str:
    """保守屏蔽块结构；未闭合围栏延伸到文件末尾。"""
    out = list(text)
    lines = text.splitlines(keepends=True)
    fence = None
    frontmatter = False
    quote = False
    list_indents: list[int] = []
    callout_end = 0
    offset = 0
    for index, line in enumerate(lines):
        if index < callout_end:
            offset += len(line)
            continue
        body = line.rstrip("\r\n")
        if index == 0 and body.lstrip("\ufeff") == "---":
            frontmatter = True
        if frontmatter:
            blank_span(out, offset, offset + len(line))
            if index > 0 and body in ("---", "..."):
                frontmatter = False
        elif fence:
            blank_span(out, offset, offset + len(line))
            expanded = body.expandtabs(4)
            closer = r"[ ]{0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}[ \t]*"
            # 收尾行可以退回顶层；按列表内容列匹配时只能去掉缩进，不能切掉围栏字符。
            if re.fullmatch(closer, expanded) or (
                not expanded[:fence[2]].strip()
                and re.fullmatch(closer, expanded[fence[2]:])
            ):
                fence = None
        else:
            expanded = body.expandtabs(4)
            indent = len(expanded) - len(expanded.lstrip(' '))
            # 列表的缩进以内容列为基准；再缩进四列才是代码。
            while list_indents and body.strip() and indent < list_indents[-1]:
                list_indents.pop()
            content_indent = list_indents[-1] if list_indents else 0
            logical = expanded[content_indent:]
            indented_code = bool(body.strip()) and indent >= content_indent + 4
            item = re.match(r"( *)(?:[-+*]|\d{1,9}[.)])([ \t]+)", expanded)
            if item and not indented_code:
                content_indent = item.end()
                list_indents.append(content_indent)
                logical = expanded[item.end():]
            opener = re.match(r"[ ]{0,3}(`{3,}|~{3,})(.*)$", logical)
            callout = re.match(r"[ ]{0,3}>[ \t]?\[![A-Za-z0-9_-]+\][+-]?", body)
            if callout and not quote and not indented_code:
                callout_end = mask_callout(lines, index, out, offset)
            elif opener and not (opener[1][0] == "`" and "`" in opener[2]):
                fence = (opener[1][0], len(opener[1]), content_indent)
                blank_span(out, offset, offset + len(line))
            else:
                if not body.strip():
                    quote = False
                if re.match(r"[ ]{0,3}>", body):
                    quote = True
                if quote or indented_code:
                    blank_span(out, offset, offset + len(line))
        offset += len(line)
    return "".join(out)


def mask_callout(lines: list[str], index: int, out: list[str], offset: int) -> int:
    """去掉 callout 的外层引用标记，递归检查内部；映射回原始偏移。"""
    inner = []
    positions = []
    while index < len(lines):
        line = lines[index]
        prefix = re.match(r"[ ]{0,3}>[ \t]?", line)
        if not prefix and not line.strip():
            break
        start = prefix.end() if prefix else 0
        blank_span(out, offset, offset + start)
        for pos in range(start, len(line)):
            inner.append(line[pos])
            positions.append(offset + pos)
        offset += len(line)
        index += 1
    inner_text = ''.join(inner)
    marker = re.match(r"\[![A-Za-z0-9_-]+\][+-]?", inner_text)
    inner_text = MASK_CHAR * marker.end() + inner_text[marker.end():]
    for pos, char in zip(positions, preprocess(inner_text)):
        out[pos] = char
    return index


def mask_inline_code(text: str) -> str:
    out = list(text)
    runs = list(re.finditer(r"`+", text))
    next_same = {}
    closing = {}
    for index in range(len(runs) - 1, -1, -1):
        length = len(runs[index][0])
        closing[index] = next_same.get(length)
        next_same[length] = index
    index = 0
    while index < len(runs):
        end = closing[index]
        if end is None:
            index += 1
        else:
            blank_span(out, runs[index].start(), runs[end].end())
            index = end + 1
    return "".join(out)


def mask_link_targets(text: str) -> str:
    """保留标签，屏蔽嵌套及转义括号组成的目标和可选标题。"""
    out = list(text)
    for match in re.finditer(r"!?\[\[(?P<target>[^\]\n|]+)(?:\|[^\]\n]*)?\]\]", text):
        if '|' in match[0] and not match[0].startswith('!'):
            blank_span(out, match.start(), match.end('target') + 1)
        else:
            blank_span(out, match.start(), match.end())
    for match in re.finditer(r"\]\(", text):
        start = match.end() - 1
        depth = 1
        pos = start + 1
        quote = None
        while pos < len(text) and depth:
            if text[pos] == "\\":
                pos += 2
                continue
            if quote:
                if text[pos] == quote:
                    quote = None
            elif text[pos] in "\"'" and text[pos - 1].isspace():
                quote = text[pos]
            elif text[pos] == "<" and pos == start + 1:
                quote = ">"
            elif text[pos] == "(":
                depth += 1
            elif text[pos] == ")":
                depth -= 1
            pos += 1
        if depth == 0:
            blank_span(out, start, pos)
    return "".join(out)


def preprocess(raw: str) -> str:
    text = mask_inline_code(mask_blocks(raw))
    text = mask_link_targets(text)
    for pat in MASK_PATTERNS:
        text = blank_out(text, pat)
    out = list(text)
    for pattern in IDENTIFIERS:
        for match in pattern.finditer(text):
            blank_span(out, match.start('value'), match.end('value'))
    text = ''.join(out)
    return text


def line_col(raw: str, offset: int) -> tuple[int, int]:
    line = raw.count("\n", 0, offset) + 1
    last_nl = raw.rfind("\n", 0, offset)
    return line, offset - last_nl


def snippet(raw: str, start: int, end: int, pad: int = 12) -> str:
    a = max(0, raw.rfind("\n", 0, start) + 1, start - pad)
    b = min(len(raw), end + pad)
    nl = raw.find("\n", end)
    if nl != -1:
        b = min(b, nl)
    s = raw[a:b].strip()
    return ("…" if a > 0 and raw[a - 1] != "\n" else "") + s + ("…" if b < len(raw) and raw[b:b + 1] != "\n" else "")


# --------------------------------------------------------------------------- #
# 规则：(id, level, 正则, 说明, 建议)
# --------------------------------------------------------------------------- #

RULES: list[tuple[str, str, re.Pattern, str, str]] = [
    (
        "ascii-quote",
        "error",
        re.compile(rf"[\"'][ \t]*(?=[{CJK}])|(?<=[{CJK}])[ \t]*[\"']"),
        "中文正文出现 ASCII 直引号 U+0022 / U+0027",
        "改用「」（本项目偏好）或 “”，全文统一（SKILL 3.3）",
    ),
    (
        "bad-ellipsis",
        "error",
        re.compile(rf"。{{3,}}|(?<=[{CJK}])\.{{3,}}|\.{{3,}}(?=[{CJK}])"),
        "省略号写法错误",
        "改用 ……（U+2026 连用两次，SKILL 3.2）",
    ),
    (
        "dup-punct",
        "error",
        re.compile(rf"([！？。，、；：])\1|[！？]{{3,}}|(?<=[{CJK}])[!?]{{2,}}"),
        "标点堆叠",
        "只保留一个；允许 ？！ 单次并用（SKILL 3.5）",
    ),
    (
        "ascii-comma",
        "error",
        re.compile(rf"(?<=[{CJK}])[,;!?]"),
        "中文后面跟了半角标点",
        "改成全角 ，；！？（SKILL 3.2）",
    ),
    (
        "ascii-colon",
        "error",
        re.compile(rf"(?<=[{CJK}]):(?!\d)"),
        "中文后面跟了半角冒号",
        "改成全角 ：（SKILL 3.2）",
    ),
    (
        "cjk-colon-digit",
        "warn",
        re.compile(rf"(?<=[{CJK}]):(?=\d)"),
        "中文后面的半角冒号紧跟数字",
        "标签、说明性文字后通常应改全角 ：；若确实是时间或比例（如 9:05、3:5）可保留半角（SKILL 3.2）",
    ),
    (
        "ascii-period",
        "error",
        re.compile(rf"(?<=[{CJK}])\.(?!\.)(?![A-Za-z0-9]{{1,5}}\b)"),
        "中文后面跟了半角句号",
        "改成全角 。（SKILL 3.2）",
    ),
    (
        "single-ellipsis",
        "warn",
        re.compile(rf"(?<![…])…(?![…])"),
        "单个省略号 …",
        "中文省略号是 ……（两个 U+2026）；英文句内部保留 ... 属正常（SKILL 3.2）",
    ),
    (
        "bad-dash",
        "error",
        re.compile(rf"(?<=[{CJK}])-{{2,}}|-{{2,}}(?=[{CJK}])|(?<!—)—(?!—)(?=[{CJK}])|(?<=[{CJK}])—(?!—)"),
        "破折号写法错误",
        "改用 ——（两个 U+2014，SKILL 3.2）",
    ),
    (
        "fullwidth-colon-time",
        "warn",
        re.compile(r"\d[ \t]*：[ \t]*\d"),
        "数字之间使用了全角冒号，可能是时间或比例",
        "确认是时间后改成半角冒号，如 15:00；比例等语境另行判断（SKILL 3.8）",
    ),
    (
        "pct-space",
        "warn",
        re.compile(r"\d[ \t]+(?:[%‰]|°(?![CF]))"),
        "数字与 % / ° 之间有空格",
        "默认紧贴数字：15%、33°；25 °C 属温度单位，不套用角度规则（SKILL 3.1）",
    ),
    (
        "fullwidth-digit",
        "warn",
        re.compile(r"[０-９]+"),
        "使用了全角数字",
        "数字用半角，设计稿 / 海报对齐场景除外（SKILL 3.2）",
    ),
    (
        "heading-trailing-punct",
        "error",
        re.compile(r"^[ ]{0,3}#{1,6}[ \t]+.*[。，、；：](?:[ \t]+#+)?[ \t]*$", re.M),
        "标题末尾有点号",
        "删掉；？！」》…… 可保留（SKILL 3.5）",
    ),
    (
        "halfwidth-paren-cn",
        "warn",
        re.compile(rf"\([^()\n]*[{CJK}][^()\n]*\)"),
        "半角括号里含中文",
        "中文正文用全角括号（）；英文括注保持半角（SKILL 3.4）",
    ),
    (
        "range-hyphen",
        "warn",
        re.compile(r"[\d%°][ \t]*[-~—][ \t]*\d"),
        "区间可能用了 hyphen、~ 或 em dash 连接",
        "本项目偏好「至」或 en dash –；全角浪纹线 ～ 可保留，日期和编号里的 - 不用改（SKILL 3.6）",
    ),
    (
        "range-unit",
        "warn",
        re.compile(r"\d[ \t]*[–—][ \t]*\d+(?:\.\d+)?[ \t]*%"),
        "百分比区间可能只有右端带百分号",
        "百分比建议两端明确：67%–89%；3–5 kg 等共用单位可保留，不补猜缺失单位（SKILL 3.6）",
    ),
    (
        "math-space",
        "warn",
        re.compile(rf"(?<=[{CJK}\w])[=<>≤≥≈≠]|[=<>≤≥≈≠](?=[\w{CJK}])"),
        "比较符号前后没有空格",
        "数学符号前后加半角空格：夏普 > 1.5（financial-notation 一）",
    ),
    (
        "cjk-latin-glue",
        "warn",
        re.compile(rf"(?<=[{CJK}])[A-Za-z0-9]|[A-Za-z0-9](?=[{CJK}])"),
        "中文与英文 / 数字之间缺空格",
        "加空格；专有名词官方写法（如「豆瓣FM」）除外（SKILL 3.1）",
    ),
    (
        "cjk-md-space",
        "warn",
        re.compile(rf"(?<=[{CJK}])[ \t]+\*\*(?=[{CJK}])|(?<=[{CJK}])\*\*[ \t]+(?=[{CJK}])"),
        "Markdown 加粗标记与中文之间有空格",
        "格式标记不算英文，不加空格（SKILL 3.1）",
    ),
    (
        "thousands",
        "warn",
        re.compile(r"(?<![A-Za-z0-9_,.])\d{5,}(?![A-Za-z0-9_,.])"),
        "5 位以上数字未加千位分隔符",
        "加半角逗号：3,000,000；年份、编号、股票代码不加（financial-notation 四）",
    ),
]


def in_iso_date(text: str, start: int, end: int) -> bool:
    return any(m.start() <= start and end <= m.end() for m in ISO_DATE.finditer(text))


# --------------------------------------------------------------------------- #
# 全文一致性检查
# --------------------------------------------------------------------------- #

def consistency_checks(masked: str) -> list[dict]:
    out: list[dict] = []

    corner = len(re.findall(r"[「」『』]", masked))
    # 中文字符和中文句读标点都可提示所在语境；完整英文段落、所有格不参与统一。
    quote_context = CJK + "，。；：！？、"
    curly = len(re.findall(rf"(?<=[{quote_context}])[ \t]*[“”‘’]|[“”‘’][ \t]*(?=[{quote_context}])", masked))
    if corner and curly:
        out.append({
            "rule": "quote-style-mix",
            "level": "warn",
            "line": 0,
            "col": 0,
            "text": f"「」×{corner} 与 “”×{curly} 并存",
            "why": "两种合法引号风格混用",
            "fix": "全文统一到一种（SKILL 3.3）",
        })

    spaced = re.findall(r"\d[ \t]+(KB|MB|GB|TB|Hz|MHz|GHz|Gbps|Mbps|kg|km|ms)\b", masked)
    glued = re.findall(r"\d(KB|MB|GB|TB|Hz|MHz|GHz|Gbps|Mbps|kg|km|ms)\b", masked)
    both = set(spaced) & set(glued)
    if both:
        out.append({
            "rule": "unit-space-mix",
            "level": "warn",
            "line": 0,
            "col": 0,
            "text": "、".join(sorted(both)),
            "why": "同一单位在文中既加空格又紧贴",
            "fix": "全文统一（SKILL 3.1）",
        })

    return out


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #

def check(raw: str, profile: str = "general") -> list[dict]:
    if profile not in ("general", "finance"):
        raise ValueError(f"Unknown profile: {profile}")
    masked = preprocess(raw)
    findings: list[dict] = []
    seen_error: set[int] = set()

    for rule_id, level, pattern, why, fix in RULES:
        if profile != "finance" and rule_id in FINANCE_RULES:
            continue
        for m in pattern.finditer(masked):
            hit = m.group()
            if not hit.strip() or set(hit) <= {MASK_CHAR}:
                continue
            if rule_id in ("range-hyphen", "ascii-comma") and in_iso_date(masked, m.start(), m.end()):
                continue
            hit_level, hit_fix = level, fix
            if rule_id == "bad-dash" and hit == "--" and re.match(r"[A-Za-z]", masked[m.end():]):
                hit_level = "warn"
                hit_fix = "可能是命令行参数；确认是参数时保留并用行内代码标记，确认是破折号时改用 ——（SKILL 3.2）"
            if hit_level == "error":
                # 先报告省略号、堆叠等具体问题，再忽略与其重叠的普通标点命中。
                if any(pos in seen_error for pos in range(m.start(), m.end())):
                    continue
                seen_error.update(range(m.start(), m.end()))
            line, col = line_col(raw, m.start())
            findings.append({
                "rule": rule_id,
                "level": hit_level,
                "line": line,
                "col": col,
                "text": snippet(raw, m.start(), m.end()),
                "why": why,
                "fix": hit_fix,
            })

    findings.extend(consistency_checks(masked))
    findings.sort(key=lambda f: (0 if f["level"] == "error" else 1, f["line"], f["col"]))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description="中文排版机械自检（只报告，不改写）")
    ap.add_argument("path", help="待检查文件，- 表示从 stdin 读")
    ap.add_argument("--level", choices=["error", "warn", "all"], default="all",
                    help="只显示指定级别，默认全部")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--profile", choices=["general", "finance"], default="general",
                    help="默认 general；finance 额外检查千位分隔符和比较符号空格")
    ap.add_argument("--fail-on", choices=["error", "warn"], default=None,
                    help="error：有 error 时返回 1；warn：有 error 或 warn 时返回 1")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")  # 统一换行，不依赖调用方是否已归一化
    all_findings = check(raw, profile=args.profile)

    findings = all_findings
    if args.level != "all":
        findings = [f for f in findings if f["level"] == args.level]

    fail_error = args.fail_on == "error" and any(f["level"] == "error" for f in all_findings)
    fail_warn = args.fail_on == "warn" and bool(all_findings)
    will_fail = fail_error or fail_warn
    # --fail-on 命中的等级被 --level 过滤掉时，触发原因不在下方列表里，需要单独说明
    hidden_trigger = will_fail and not any(
        args.fail_on == "warn" or f["level"] == "error" for f in findings
    )

    note = None
    if hidden_trigger:
        note = (
            f"--fail-on {args.fail_on} 命中，但 --level {args.level} 隐藏了触发项，"
            "去掉 --level 查看具体位置。"
        )

    if args.json:
        payload = {"path": args.path, "findings": findings}
        if note:
            payload["note"] = note
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif not findings:
        scope = "所选级别" if args.level != "all" else "机械可检"
        print(f"✅ 未发现{scope}的排版问题（语境相关的仍需人工过一遍）")
    else:
        n_err = sum(1 for f in findings if f["level"] == "error")
        n_warn = len(findings) - n_err
        print(f"{args.path}：{n_err} 处默认规则问题，{n_warn} 处候选问题\n")
        for f in findings:
            loc = f"{f['line']}:{f['col']}" if f["line"] else "全文"
            print(f"{LEVEL_ICON[f['level']]} {loc}  [{f['rule']}] {f['why']}")
            print(f"   原文：{f['text']}")
            print(f"   建议：{f['fix']}\n")
        print("候选问题（⚠️）需要结合语境判断，不要机械替换。")

    if note and not args.json:
        print(f"\n注意：{note}")

    return 1 if will_fail else 0


if __name__ == "__main__":
    sys.exit(main())
