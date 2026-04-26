#!/usr/bin/env python3
"""Render Markdown as themed HTML using local CSS assets."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = SKILL_DIR / "assets"
ALLOWED_RAW_HTML_TAGS = {
    "a", "abbr", "b", "br", "center", "cite", "code", "del", "div", "em", "i",
    "kbd", "mark", "p", "rp", "rt", "ruby", "s", "small", "span", "strong",
    "sub", "sup", "u",
}
CODE_KEYWORDS = {
    "java": {
        "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
        "class", "const", "continue", "default", "do", "double", "else", "enum",
        "extends", "final", "finally", "float", "for", "goto", "if", "implements",
        "import", "instanceof", "int", "interface", "long", "native", "new", "package",
        "private", "protected", "public", "return", "short", "static", "strictfp",
        "super", "switch", "synchronized", "this", "throw", "throws", "transient",
        "try", "void", "volatile", "while",
    },
    "python": {
        "and", "as", "assert", "async", "await", "break", "class", "continue",
        "def", "del", "elif", "else", "except", "False", "finally", "for",
        "from", "global", "if", "import", "in", "is", "lambda", "None", "nonlocal",
        "not", "or", "pass", "raise", "return", "True", "try", "while", "with",
        "yield",
    },
}


def available_themes() -> dict[str, Path]:
    themes: dict[str, Path] = {}
    for path in sorted(ASSETS_DIR.glob("*.css")):
        themes[path.stem.lower()] = path
    return themes


def resolve_theme(theme: str) -> Path:
    candidate = Path(theme)
    if candidate.exists():
        return candidate.resolve()

    themes = available_themes()
    key = theme.removesuffix(".css").lower()
    if key in themes:
        return themes[key]

    names = ", ".join(path.stem for path in themes.values())
    raise SystemExit(f"Unknown theme: {theme}\nAvailable themes: {names}")


def strip_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index in range(1, min(len(lines), 80)):
        if lines[index].strip() == "---":
            return "\n".join(lines[index + 1 :]).lstrip()
    return text


def sanitize_raw_html_tag(tag: str) -> str:
    match = re.match(r"</?\s*([a-zA-Z][\w:-]*)", tag)
    if not match:
        return html.escape(tag, quote=False)
    name = match.group(1).lower()
    if name not in ALLOWED_RAW_HTML_TAGS:
        return html.escape(tag, quote=False)

    cleaned = re.sub(r"\s+on\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", tag, flags=re.IGNORECASE)
    cleaned = re.sub(r"javascript\s*:", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def inline_markdown(text: str, footnotes: list[dict[str, str]] | None = None) -> str:
    protected_spans: list[str] = []

    def keep(value: str) -> str:
        protected_spans.append(value)
        return f"@@PROTECTED{len(protected_spans) - 1}@@"

    def keep_link(match: re.Match[str]) -> str:
        label = match.group(1)
        href = match.group(2)
        title = match.group(3) or match.group(4)
        if title and footnotes is not None:
            number = len(footnotes) + 1
            footnotes.append({
                "label": html.unescape(plain_text(label)),
                "target": html.unescape(href),
                "title": html.unescape(title),
            })
            return keep(
                f'<span class="footnote-word">{label}</span>'
                f'<sup class="footnote-ref" id="fnref-{number}">'
                f'<a href="#fn-{number}">[{number}]</a>'
                f'</sup>'
            )
        if not re.match(r"^(?:https?://|mailto:|#|/|\./|\../)", href):
            return match.group(0)
        return keep(f'<a href="{html.escape(href, quote=True)}">{label}</a>')

    source = re.sub(r"`([^`]+)`", lambda m: keep(f"<code>{html.escape(m.group(1), quote=False)}</code>"), text)
    source = re.sub(r"</?[a-zA-Z][^>]*>", lambda m: keep(sanitize_raw_html_tag(m.group(0))), source)
    escaped = html.escape(source, quote=False)
    escaped = re.sub(
        r"\$(?!\$)(.+?)(?<!\\)\$",
        lambda m: keep(f'<span class="math-inline">\\({m.group(1)}\\)</span>'),
        escaped,
    )
    escaped = re.sub(
        r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+(?:"[^"]*"|&quot;[^&]*&quot;))?\)',
        lambda m: keep(
            f'<img src="{html.escape(m.group(2), quote=True)}" '
            f'alt="{html.escape(m.group(1), quote=True)}">'
        ),
        escaped,
    )
    escaped = re.sub(
        r'\[([^\]]+)\]\(([^)\s]+)(?:\s+(?:"([^"]*)"|&quot;([^&]*)&quot;))?\)',
        keep_link,
        escaped,
    )
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"==([^=]+)==", r"<mark>\1</mark>", escaped)
    escaped = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", escaped)
    for index, value in enumerate(protected_spans):
        escaped = escaped.replace(f"@@PROTECTED{index}@@", value)
    return escaped


def plain_text(markdown: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", markdown)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_~=#]", "", text)
    return html.unescape(text).strip()


def slugify(text: str, used: dict[str, int]) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", plain_text(text).lower()).strip("-")
    slug = slug or "section"
    count = used.get(slug, 0)
    used[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count + 1}"


def collect_headings(lines: list[str]) -> list[dict[str, str | int]]:
    headings: list[dict[str, str | int]] = []
    used: dict[str, int] = {}
    in_fence = False
    in_math = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("$$"):
            if stripped.count("$$") == 1:
                in_math = not in_math
            continue
        if in_math:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
        if heading:
            text = heading.group(2).strip()
            headings.append({
                "level": len(heading.group(1)),
                "text": text,
                "id": slugify(text, used),
            })
    return headings


def render_toc(headings: list[dict[str, str | int]]) -> str:
    toc_headings = [item for item in headings if int(item["level"]) in {2, 3}]
    if not toc_headings:
        toc_headings = headings
    if not toc_headings:
        return ""
    min_level = min(int(item["level"]) for item in toc_headings)
    items = ['<nav class="markdown-toc" aria-label="目录">', '<div class="markdown-toc-title">目录</div>', '<ol>']
    for item in toc_headings:
        level = int(item["level"])
        depth = max(0, level - min_level)
        label = inline_markdown(str(item["text"]))
        href = html.escape(str(item["id"]), quote=True)
        items.append(f'<li class="toc-level-{depth}"><a href="#{href}">{label}</a></li>')
    items.extend(["</ol>", "</nav>"])
    return "\n".join(items)


def is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", cell or "") for cell in cells)


def render_table(lines: list[str], footnotes: list[dict[str, str]] | None = None) -> str:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    header = rows[0]
    body = rows[2:]
    out = ["<table>", "<thead><tr>"]
    out.extend(f"<th>{inline_markdown(cell, footnotes)}</th>" for cell in header)
    out.append("</tr></thead>")
    if body:
        out.append("<tbody>")
        for row in body:
            out.append("<tr>")
            out.extend(f"<td>{inline_markdown(cell, footnotes)}</td>" for cell in row)
            out.append("</tr>")
        out.append("</tbody>")
    out.append("</table>")
    return "\n".join(out)


def render_heading(level: int, text: str, heading_id: str) -> str:
    content = inline_markdown(text.strip())
    safe_id = html.escape(heading_id, quote=True)
    return (
        f'<h{level} id="{safe_id}">'
        f'<span class="prefix"></span>'
        f'<span class="content">{content}</span>'
        f'<span class="suffix"></span>'
        f"</h{level}>"
    )


def render_math_block(lines: list[str]) -> str:
    content = "\n".join(lines).strip()
    return f'<div class="math-block">\\[\n{html.escape(content)}\n\\]</div>'


def highlight_code(code: str, language: str) -> str:
    escaped = html.escape(code)
    language_key = language.lower()

    protected: list[str] = []

    def keep(value: str, cls: str) -> str:
        protected.append(f'<span class="hljs-{cls}">{value}</span>')
        return f"@@CODE{len(protected) - 1}@@"

    escaped = re.sub(r"(&quot;.*?&quot;|&#x27;.*?&#x27;)", lambda m: keep(m.group(1), "string"), escaped)
    if language_key in {"java", "javascript", "typescript", "python", "bash", "shell", "diff"}:
        escaped = re.sub(r"(//.*?$|#.*?$)", lambda m: keep(m.group(1), "comment"), escaped, flags=re.MULTILINE)
    if language_key in {"java", "python"}:
        keywords = "|".join(sorted(CODE_KEYWORDS[language_key], key=len, reverse=True))
        escaped = re.sub(rf"\b({keywords})\b", r'<span class="hljs-keyword">\1</span>', escaped)
    if language_key == "diff":
        escaped = re.sub(r"^(\+.*)$", r'<span class="hljs-addition">\1</span>', escaped, flags=re.MULTILINE)
        escaped = re.sub(r"^(-.*)$", r'<span class="hljs-deletion">\1</span>', escaped, flags=re.MULTILINE)
    for index, value in enumerate(protected):
        escaped = escaped.replace(f"@@CODE{index}@@", value)
    return escaped


def render_code_block(code_lines: list[str], language: str) -> str:
    language_key = language.strip().lower()
    class_name = "hljs" + (f" language-{html.escape(language_key, quote=True)}" if language_key else "")
    language_label = html.escape(language_key or "text", quote=True)
    code = highlight_code("\n".join(code_lines), language_key)
    return f'<pre class="code-block" data-language="{language_label}"><code class="{class_name}">{code}</code></pre>'


def render_image_slider(line: str) -> str | None:
    stripped = line.strip()
    if not (stripped.startswith("<") and stripped.endswith(">")):
        return None
    inner = stripped[1:-1].strip()
    matches = list(re.finditer(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+(?:"[^"]*"|&quot;[^&]*&quot;))?\)', inner))
    if len(matches) < 2:
        return None
    consumed = re.sub(r'!\[[^\]]*\]\([^)]+\)', "", inner)
    if consumed.replace(",", "").strip():
        return None
    slides = ['<div class="markdown-slider" role="region" aria-label="横屏滑动图片">']
    for index, match in enumerate(matches, 1):
        alt = html.escape(match.group(1) or f"图片 {index}", quote=True)
        src = html.escape(match.group(2), quote=True)
        slides.append(f'<figure class="markdown-slide"><img src="{src}" alt="{alt}"><figcaption>{alt}</figcaption></figure>')
    slides.append("</div>")
    return "\n".join(slides)


def render_footnotes(footnotes: list[dict[str, str]]) -> str:
    if not footnotes:
        return ""

    items = ['<section class="footnotes-sep" aria-label="参考资料">', "<h2>参考资料</h2>"]
    for index, note in enumerate(footnotes, 1):
        title = html.escape(note["title"] or note["label"], quote=False)
        target = note["target"]
        if re.match(r"^https?://", target):
            safe_href = html.escape(target, quote=True)
            value = f'<a href="{safe_href}">{html.escape(target, quote=False)}</a>'
        else:
            value = html.escape(target, quote=False)
        items.append(
            f'<div class="footnote-item" id="fn-{index}">'
            f'<p><span class="footnote-num">[{index}]</span>{title}: {value} '
            f'<a class="footnote-backref" href="#fnref-{index}">↩</a></p>'
            f'</div>'
        )
    items.append("</section>")
    return "\n".join(items)


def markdown_to_html(markdown: str) -> tuple[str, str]:
    lines = strip_frontmatter(markdown).splitlines()
    headings = collect_headings(lines)
    heading_index = 0
    blocks: list[str] = []
    footnotes: list[dict[str, str]] = []
    first_heading = ""
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        fence = re.match(r"^```([\w.+-]*)\s*$", stripped)
        if fence:
            language = fence.group(1)
            index += 1
            code_lines: list[str] = []
            fence_start = index - 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            else:
                print(
                    f"Warning: unclosed code fence (language={language!r}) near "
                    f"line {fence_start + 1}; remaining content consumed.",
                    file=sys.stderr,
                )
            blocks.append(render_code_block(code_lines, language))
            continue

        slider = render_image_slider(stripped)
        if slider:
            blocks.append(slider)
            index += 1
            continue

        if stripped == "[TOC]":
            blocks.append(render_toc(headings))
            index += 1
            continue

        if stripped.startswith("$$"):
            math_lines: list[str] = []
            rest = stripped[2:]
            if rest.endswith("$$") and len(rest) > 2:
                math_lines.append(rest[:-2])
                index += 1
            else:
                if rest:
                    math_lines.append(rest)
                index += 1
                while index < len(lines):
                    math_line = lines[index].strip()
                    if math_line.endswith("$$"):
                        if math_line[:-2]:
                            math_lines.append(math_line[:-2])
                        index += 1
                        break
                    math_lines.append(lines[index])
                    index += 1
            blocks.append(render_math_block(math_lines))
            continue

        heading = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2)
            heading_id = str(headings[heading_index]["id"]) if heading_index < len(headings) else slugify(text, {})
            heading_index += 1
            if not first_heading and level == 1:
                first_heading = re.sub(r"<[^>]+>", "", inline_markdown(text))
            blocks.append(render_heading(level, text, heading_id))
            index += 1
            continue

        if re.fullmatch(r"[-*_]\s*[-*_]\s*[-*_][\-*_ ]*", stripped):
            blocks.append("<hr>")
            index += 1
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip()[1:].strip())
                index += 1
            paragraphs: list[list[str]] = []
            current: list[str] = []
            for part in quote_lines:
                if part:
                    current.append(part)
                else:
                    if current:
                        paragraphs.append(current)
                        current = []
            if current:
                paragraphs.append(current)
            if not paragraphs:
                paragraphs = [[]]
            inner = "\n".join(
                f"<p>{inline_markdown(' '.join(p), footnotes)}</p>"
                for p in paragraphs
            )
            blocks.append(f"<blockquote>{inner}</blockquote>")
            continue

        if "|" in stripped and index + 1 < len(lines) and is_table_separator(lines[index + 1]):
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index].strip():
                table_lines.append(lines[index])
                index += 1
            blocks.append(render_table(table_lines, footnotes))
            continue

        list_match = re.match(r"^\s*((?:[-*+])|\d+[.)])\s+(.+)$", line)
        if list_match:
            ordered = bool(re.match(r"\d", list_match.group(1)))
            tag = "ol" if ordered else "ul"
            items: list[str] = []
            while index < len(lines):
                item_match = re.match(r"^\s*((?:[-*+])|\d+[.)])\s+(.+)$", lines[index])
                if not item_match:
                    break
                item_ordered = bool(re.match(r"\d", item_match.group(1)))
                if item_ordered != ordered:
                    break
                items.append(f"<li>{inline_markdown(item_match.group(2).strip(), footnotes)}</li>")
                index += 1
            blocks.append(f"<{tag}>\n" + "\n".join(items) + f"\n</{tag}>")
            continue

        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index]
            next_stripped = next_line.strip()
            if not next_stripped:
                break
            if (
                next_stripped.startswith("```")
                or next_stripped.startswith("$$")
                or next_stripped == "[TOC]"
                or re.match(r"^(#{1,6})\s+", next_stripped)
                or next_stripped.startswith(">")
                or re.match(r"^\s*((?:[-*+])|\d+[.)])\s+", next_line)
                or re.fullmatch(r"[-*_]\s*[-*_]\s*[-*_][\-*_ ]*", next_stripped)
                or render_image_slider(next_stripped)
            ):
                break
            if "|" in next_stripped and index + 1 < len(lines) and is_table_separator(lines[index + 1]):
                break
            paragraph_lines.append(next_stripped)
            index += 1
        blocks.append(f"<p>{inline_markdown(' '.join(paragraph_lines), footnotes)}</p>")

    footnotes_html = render_footnotes(footnotes)
    if footnotes_html:
        blocks.append(footnotes_html)
    return "\n\n".join(blocks), first_heading


def build_html(markdown_path: Path, css_path: Path, content_html: str, title: str) -> str:
    css = css_path.read_text(encoding="utf-8")
    safe_title = html.escape(title or markdown_path.stem)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <script>
    window.MathJax = {{
      loader: {{load: ['[tex]/mhchem']}},
      tex: {{
        inlineMath: [['\\\\(', '\\\\)']],
        displayMath: [['\\\\[', '\\\\]']],
        packages: {{'[+]': ['mhchem']}}
      }},
      svg: {{fontCache: 'global'}}
    }};
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-svg.js"></script>
  <style>
  :root {{
    --toc-bg: #faf9f5;
    --toc-border: #e8e6dc;
    --toc-title-color: #1B365D;
    --toc-link-color: #3d3d3a;
    --footnotes-border: #e8e6dc;
    --footnote-num-color: #6b6a64;
    --slider-track-bg: #e8e6dc;
    --slider-thumb-bg: #b8b7b0;
  }}
{css}
  .math-inline svg,
  .math-block svg {{
    max-width: 100%;
  }}
  .math-block {{
    overflow-x: auto;
    margin: 18px 0;
  }}
  .markdown-toc {{
    background: var(--toc-bg);
    border: 1px solid var(--toc-border);
    border-radius: 6px;
    padding: 16px 18px;
    margin: 18px 0 24px;
  }}
  .markdown-toc-title {{
    color: var(--toc-title-color);
    font-weight: 500;
    margin-bottom: 8px;
  }}
  .markdown-toc ol {{
    list-style: none;
    margin: 0;
    padding: 0;
  }}
  .markdown-toc li {{
    margin: 5px 0;
  }}
  .markdown-toc .toc-level-1 {{ padding-left: 18px; }}
  .markdown-toc .toc-level-2 {{ padding-left: 36px; }}
  .markdown-toc .toc-level-3 {{ padding-left: 54px; }}
  .markdown-toc a {{
    color: var(--toc-link-color);
    text-decoration: none;
    border-bottom: 0;
  }}
  .footnote-word {{
    font-weight: 600;
  }}
  .footnote-ref {{
    vertical-align: super;
    font-size: 0.72em;
    line-height: 0;
    margin-left: 2px;
  }}
  .footnote-ref a,
  .footnote-backref {{
    color: inherit;
    text-decoration: none;
    border-bottom: 0;
  }}
  .footnotes-sep {{
    border-top: 1px solid var(--footnotes-border);
    padding-top: 20px;
    margin-top: 48px;
  }}
  .footnotes-sep h2 {{
    margin-top: 0;
  }}
  .footnote-item p {{
    margin: 8px 0;
  }}
  .footnote-num {{
    display: inline-block;
    min-width: 28px;
    margin-right: 8px;
    color: var(--footnote-num-color);
  }}
  .markdown-slider {{
    display: flex;
    gap: 14px;
    overflow-x: auto;
    scroll-snap-type: x mandatory;
    padding: 0 0 14px;
    margin: 18px 0;
  }}
  .markdown-slider::-webkit-scrollbar {{ height: 10px; }}
  .markdown-slider::-webkit-scrollbar-track {{ background: var(--slider-track-bg); border-radius: 999px; }}
  .markdown-slider::-webkit-scrollbar-thumb {{ background: var(--slider-thumb-bg); border-radius: 999px; }}
  .markdown-slide {{
    flex: 0 0 84%;
    margin: 0;
    scroll-snap-align: start;
  }}
  .markdown-slide img {{
    width: 100%;
    margin: 0;
    display: block;
  }}
  </style>
</head>
<body>
  <main id="wemd">
    <article id="write">
{content_html}
    </article>
  </main>
</body>
</html>
"""


def warn_theme_fonts(css_path: Path) -> None:
    if css_path.stem.lower() != "kami":
        return

    required = [
        SKILL_DIR / "fonts" / "仓耳今楷02-W04.ttf",
        SKILL_DIR / "fonts" / "仓耳今楷02-W05.ttf",
    ]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        print(
            "Font notice: Kami works best with TsangerJinKai02. "
            f"Missing: {', '.join(missing)}. It will fall back to system serif fonts.",
            file=sys.stderr,
        )
    else:
        print(
            "Font notice: Kami uses TsangerJinKai02 from skills/markdown-themes/fonts; "
            "JetBrains Mono is recommended for code blocks if installed.",
            file=sys.stderr,
        )


def list_themes() -> None:
    for path in available_themes().values():
        marker = " (template)" if path.stem.lower() == "template" else ""
        print(f"{path.stem}{marker}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Markdown as themed HTML.")
    parser.add_argument("input", nargs="?", type=Path, help="Markdown input file")
    parser.add_argument("--theme", default="Knowledge-Base", help="Theme name or CSS path")
    parser.add_argument("--output", "-o", type=Path, help="HTML output path")
    parser.add_argument("--list-themes", action="store_true", help="List CSS themes and exit")
    args = parser.parse_args()

    if args.list_themes:
        list_themes()
        return 0

    if args.input is None:
        parser.error("input is required unless --list-themes is used")

    markdown_path = args.input.resolve()
    if not markdown_path.exists():
        raise SystemExit(f"Input not found: {markdown_path}")

    css_path = resolve_theme(args.theme)
    warn_theme_fonts(css_path)
    markdown = markdown_path.read_text(encoding="utf-8")
    content_html, title = markdown_to_html(markdown)
    output = args.output or markdown_path.with_name(f"{markdown_path.stem}-{css_path.stem}.html")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_html(markdown_path, css_path, content_html, title), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
