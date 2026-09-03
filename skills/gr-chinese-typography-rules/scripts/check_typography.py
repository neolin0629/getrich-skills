#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gr-chinese-typography-rules 机械自检脚本。

只报告，不改写。分两级：

    error —— 确定性问题，几乎不会误判（ASCII 直引号、中文里的半角标点、标点堆叠……）
    warn  —— 需要语境判断的候选问题（单位空格、引号风格、中英文粘连……），人工确认后再改

代码块、行内代码、URL、Markdown 链接目标（可见文字仍检查）、HTML 标签、frontmatter、公式一律屏蔽，不参与检查。

用法：
    python3 check_typography.py 稿子.md
    python3 check_typography.py 稿子.md --level error   # 只看确定性问题
    python3 check_typography.py 稿子.md --json
    python3 check_typography.py 稿子.md --fail-on error # 有 error 时退出码 1
    echo "文本" | python3 check_typography.py -
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CJK = r"一-鿿㐀-䶿"
CJK_PUNCT = r"，。；：！？、（）【】《》「」『』——…"

LEVEL_ICON = {"error": "🔴", "warn": "⚠️"}


# --------------------------------------------------------------------------- #
# 预处理：屏蔽保护内容，偏移保持不变
# --------------------------------------------------------------------------- #

URL_CHARS = r"A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%"

MASK_PATTERNS = [
    re.compile(r"\A---\n.*?\n---\n", re.S),      # frontmatter
    re.compile(r"```.*?```", re.S),               # 围栏代码块
    re.compile(r"~~~.*?~~~", re.S),
    re.compile(r"\$\$.*?\$\$", re.S),             # 块级公式
    re.compile(r"`[^`\n]+`"),                     # 行内代码
    re.compile(r"\$[^$\n]+\$"),                   # 行内公式
    re.compile(rf"https?://[{URL_CHARS}]+"),       # 裸 URL（不吞后面的中文正文）
    re.compile(r"<[^>\n]{1,120}>"),               # HTML 标签
    re.compile(r"^[ \t]{4,}\S.*$", re.M),         # 缩进代码块
]

# Markdown 链接 / 图片：只屏蔽目标 `(...)`，可见文字 `[...]` 仍参与检查
LINK_TARGET = re.compile(r"!?\[[^\]\n]*\]\(([^)\n]*)\)")

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def blank_span(out: list[str], start: int, end: int) -> None:
    for i in range(start, end):
        if out[i] != "\n":
            out[i] = " "


def blank_out(text: str, pattern: re.Pattern) -> str:
    """把匹配区域替换成等长空格，保持字符偏移不变。"""
    out = list(text)
    for m in pattern.finditer(text):
        blank_span(out, m.start(), m.end())
    return "".join(out)


def blank_group(text: str, pattern: re.Pattern, group: int) -> str:
    """只屏蔽指定捕获组，其余匹配内容（如链接可见文字）保留参与检查。"""
    out = list(text)
    for m in pattern.finditer(text):
        blank_span(out, m.start(group), m.end(group))
    return "".join(out)


def preprocess(raw: str) -> str:
    text = raw
    text = blank_group(text, LINK_TARGET, 1)
    for pat in MASK_PATTERNS:
        text = blank_out(text, pat)
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
        "ascii-period",
        "error",
        re.compile(rf"(?<=[{CJK}])\.(?![A-Za-z0-9]{{1,5}}\b)"),
        "中文后面跟了半角句号",
        "改成全角 。（SKILL 3.2）",
    ),
    (
        "dup-punct",
        "error",
        re.compile(rf"([！？。，、；：])\1|[！？]{{3,}}|(?<=[{CJK}])[!?]{{2,}}"),
        "标点堆叠",
        "只保留一个；允许 ？！ 单次并用（SKILL 3.5）",
    ),
    (
        "bad-ellipsis",
        "error",
        re.compile(rf"。{{3,}}|(?<=[{CJK}])\.{{3,}}|\.{{3,}}(?=[{CJK}])"),
        "省略号写法错误",
        "改用 ……（U+2026 连用两次，SKILL 3.2）",
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
        re.compile(rf"(?<=[{CJK}])-{{2,}}|-{{2,}}(?=[{CJK}])|(?<=[{CJK}])—(?!—)(?=[{CJK}])"),
        "破折号写法错误",
        "改用 ——（两个 U+2014，SKILL 3.2）",
    ),
    (
        "fullwidth-colon-time",
        "error",
        re.compile(r"\d[ \t]*：[ \t]*\d"),
        "时间用了全角冒号",
        "时间用半角冒号，如 15:00（financial-notation 五）",
    ),
    (
        "pct-space",
        "error",
        re.compile(r"\d[ \t]+[%°‰]"),
        "数字与 % / ° 之间有空格",
        "紧贴数字：15%、33°（SKILL 3.1）",
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
        re.compile(r"^#{1,6} .*[。，、；：]\s*$", re.M),
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
        re.compile(r"\d[ \t]*[-~～][ \t]*\d"),
        "区间可能用了 hyphen 或 ~ 连接",
        "中文区间用「至」或 en dash –；ISO 日期里的 - 不用改（SKILL 3.6）",
    ),
    (
        "range-unit",
        "warn",
        re.compile(r"\d(?![%°])[ \t]*[–—][ \t]*\d+[ \t]*(%|[A-Za-z]{1,4}\b)"),
        "区间可能只有右端带单位",
        "两端都要带单位或百分号：67%–89%（SKILL 3.6）",
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
        re.compile(rf"(?<=[{CJK}])[ \t]+\*\*|\*\*[ \t]+(?=[{CJK}])"),
        "Markdown 加粗标记与中文之间有空格",
        "格式标记不算英文，不加空格（SKILL 3.1）",
    ),
    (
        "thousands",
        "warn",
        re.compile(r"(?<![\d,.])\d{5,}(?![\d,.])"),
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
    curly = len(re.findall(r"[“”‘’]", masked))
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

    spaced = re.findall(r"\d\s(KB|MB|GB|TB|Hz|MHz|GHz|Gbps|Mbps|kg|km|ms)\b", masked)
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

def check(raw: str) -> list[dict]:
    masked = preprocess(raw)
    findings: list[dict] = []
    seen_error: set[int] = set()

    for rule_id, level, pattern, why, fix in RULES:
        for m in pattern.finditer(masked):
            if not m.group().strip():
                continue
            if rule_id in ("range-hyphen", "ascii-comma") and in_iso_date(masked, m.start(), m.end()):
                continue
            if level == "error":
                # 同一位置只报一条，避免「。。。」同时命中堆叠和省略号两条规则
                if m.start() in seen_error:
                    continue
                seen_error.add(m.start())
            line, col = line_col(raw, m.start())
            findings.append({
                "rule": rule_id,
                "level": level,
                "line": line,
                "col": col,
                "text": snippet(raw, m.start(), m.end()),
                "why": why,
                "fix": fix,
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
    ap.add_argument("--fail-on", choices=["error", "warn"], default=None,
                    help="命中该级别时退出码为 1")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
    all_findings = check(raw)

    findings = all_findings
    if args.level != "all":
        findings = [f for f in findings if f["level"] == args.level]

    if args.json:
        print(json.dumps({"path": args.path, "findings": findings}, ensure_ascii=False, indent=2))
    elif not findings:
        print("✅ 未发现机械可检的排版问题（语境相关的仍需人工过一遍）")
    else:
        n_err = sum(1 for f in findings if f["level"] == "error")
        n_warn = len(findings) - n_err
        print(f"{args.path}：{n_err} 处确定性问题，{n_warn} 处候选问题\n")
        for f in findings:
            loc = f"{f['line']}:{f['col']}" if f["line"] else "全文"
            print(f"{LEVEL_ICON[f['level']]} {loc}  [{f['rule']}] {f['why']}")
            print(f"   原文：{f['text']}")
            print(f"   建议：{f['fix']}\n")
        print("候选问题（⚠️）需要结合语境判断，不要机械替换。")

    # 退出码看未过滤的完整结果，不受 --level 影响
    if args.fail_on == "error" and any(f["level"] == "error" for f in all_findings):
        return 1
    if args.fail_on == "warn" and all_findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
