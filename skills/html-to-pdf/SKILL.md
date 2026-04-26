---
name: html-to-pdf
description: |
  将本地或在线 HTML 生成 PDF，尤其适合把 markdown-themes 生成的主题 HTML、文章 HTML、报告 HTML、
  周报 HTML、网页快照导出为可打印 PDF。触发：html 转 pdf、HTML 生成 PDF、网页导出 PDF、
  markdown-themes 生成 PDF、文章 PDF、报告 PDF、打印 PDF。
---

# html-to-pdf

把 HTML 稳定导出为 PDF。优先用于 `markdown-themes` 生成的 HTML，也可处理普通本地 HTML 或线上页面。

## 默认流程

1. 确认输入是本地 `.html` 文件或 `http(s)` URL。
2. 如果输入来自 `markdown-themes`，直接使用生成的 HTML；不要重新改主题 CSS，除非用户要求。
3. 使用脚本导出 PDF：

```bash
python3 skills/html-to-pdf/scripts/html_to_pdf.py input.html
```

指定输出路径：

```bash
python3 skills/html-to-pdf/scripts/html_to_pdf.py input.html --output output.pdf
```

常用打印参数：

```bash
python3 skills/html-to-pdf/scripts/html_to_pdf.py input.html \
  --format A4 \
  --media print \
  --prefer-css-page-size
```

## 输出规则

- 默认输出到输入文件同目录，文件名同 stem，扩展名改为 `.pdf`。
- 默认纸张为 `A4`，打印背景为开启，等待页面加载完成后再打印。
- 默认 Chrome 打印页边距为 `0`，避免彩色 / 米色页面导出后出现白边；正文留白交给 HTML/CSS 控制。
- 默认使用 `print` media；如果页面专门为屏幕展示设计，可用 `--media screen`。
- 对使用 `@page` 定义纸张或边距的 HTML，优先加 `--prefer-css-page-size`。
- 对含远程图片、Web Font、图表或延迟渲染脚本的页面，加 `--wait-ms 1000` 到 `3000`。
- 如果明确想保留浏览器打印白边，可显式传 `--margin 12mm` 或其他值。

## 与 markdown-themes 配合

先由 `markdown-themes` 生成 HTML：

```bash
python3 skills/markdown-themes/scripts/render_markdown.py article.md --theme Knowledge-Base --output article.html
```

再生成 PDF：

```bash
python3 skills/html-to-pdf/scripts/html_to_pdf.py article.html --output article.pdf --prefer-css-page-size
```

对 Kami、markdown-themes 这类已经在 HTML/CSS 中控制页面背景和留白的文档，不要额外传 `--margin`，否则 Chrome 会在 PDF 纸张外层加一圈白色打印边距。

如果 PDF 分页不理想，优先在 HTML/CSS 中补打印样式，例如：

```css
@page {
  size: A4;
  margin: 14mm;
}

h1, h2, h3 {
  break-after: avoid;
}

pre, blockquote, table, img {
  break-inside: avoid;
}
```

## 质量检查

生成后至少检查：

- 脚本是否输出 `[OK] PDF saved:`。
- PDF 文件存在且大小非 0。
- 对正式交付件，打开或渲染抽查首页、目录页、图表页和末页，确认字体、图片、分页、背景色正常。

## 故障处理

- 报找不到浏览器：安装 Chrome / Chromium / Edge，或设置 `CHROME_PATH=/path/to/browser`。
- 本地图片或 CSS 丢失：确认 HTML 与资源的相对路径没有移动；脚本会允许本地文件互相访问。
- 远程资源没加载完：增加 `--wait-ms`，必要时改用本地资源。
- 背景色或背景图没出现：确认没有覆盖 `printBackground`，脚本默认已经开启背景打印。
