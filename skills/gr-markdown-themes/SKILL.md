---
name: gr-markdown-themes
description: |
  将 Markdown / md 文档转换为带主题样式的 HTML，并根据文章内容推荐合适主题。
  触发：markdown 转 html、md 转 html、Markdown 转换成 HTML、文章排版成 HTML、给 Markdown 套主题、
  选择文章主题、公众号 / 博客 / 知识库 / 研报 Markdown HTML 排版。
  每次使用前必须先读取 references/theme-reference.md，再扫描 assets/*.css，按内容类型、读者、
  情绪和结构复杂度选择主题；若新增或删除主题，同步更新主题参考文档。
---

# gr-markdown-themes

把 Markdown 文档转换成带主题 CSS 的 HTML。这个 skill 的核心不是“随便套个皮”，而是先判断文章气质，再选主题。

## 每次调用流程

1. 先读取 `references/theme-reference.md`，把它作为主题选择的真源。
2. 再扫描 `assets/*.css`，确认当前实际存在的主题文件。
3. 如果发现 CSS 主题存在但参考文档没有记录，先快速检查该 CSS 的字体、色彩、标题、引用、代码块和表格风格，再补充参考文档。
4. 分析 Markdown 内容：
   - 内容类型：知识库、论文、故事、商业、技术、清单、观点文、视觉传播稿等。
   - 读者场景：公众号、博客、内部文档、课程讲义、社媒长图文、展示型页面。
   - 风格需求：克制、正式、温暖、复古、醒目、未来感、高级感。
   - 结构复杂度：标题层级、代码块、表格、引用、图片、长段落密度。
5. 选择 1 个主推荐主题；必要时给 1 个备选主题和取舍理由。
6. 转换 HTML。默认使用：

```bash
python3 skills/gr-markdown-themes/scripts/render_markdown.py input.md --theme Knowledge-Base
```

指定输出路径：

```bash
python3 skills/gr-markdown-themes/scripts/render_markdown.py input.md --theme Academic-Paper --output output.html
```

列出当前主题：

```bash
python3 skills/gr-markdown-themes/scripts/render_markdown.py --list-themes
```

检查主题参考文档是否覆盖全部 CSS：

```bash
python3 skills/gr-markdown-themes/scripts/check_theme_reference.py
```

## 选择规则

- 用户指定主题时，优先使用用户指定主题；如果主题不存在，列出可选主题并说明。
- 用户没有指定主题时，必须根据 `references/theme-reference.md` 推荐，不要只按文件名猜。
- `Template.css` 只作为开发新主题的模板，不用于正式文章转换。
- `g2.css`、`zj.css` 是 Typora 风格主题，偏向长文、打印、个人知识库；其他多数主题是 WeMD 风格，偏向公众号 / HTML 文章。
- 技术文章有大量代码块时，优先选择代码块可读性强的主题：`Knowledge-Base`、`Cyberpunk-Neon`、`Academic-Paper`。
- 正式研报、论文、课程讲义优先：`Academic-Paper`、`zj`、`g2`。
- 叙事、访谈、复盘、随笔优先：`Sunset-Film`、`Morandi-Forest`、`Luxury-Gold`。
- 传播型强、需要一眼抓人的内容优先：`Neo-Brutalism`、`Bauhaus`、`Aurora-Glass`、`Cyberpunk-Neon`。
- 使用 `Kami` 主题时，提示用户推荐字体：中文正文 / 标题使用仓耳今楷 02（当前放在 `skills/gr-markdown-themes/fonts/`），代码使用 JetBrains Mono；缺失时会回退到系统宋体和系统等宽字体。

## 维护机制

新增主题：

1. 把 CSS 放到 `assets/`。
2. 确认选择器适配：推荐使用 `#wemd`；Typora 主题可用 `#write`。
3. 在 `references/theme-reference.md` 增加一节，写清楚视觉特征、适合内容、不适合内容、选择关键词。
4. 运行 `python3 skills/gr-markdown-themes/scripts/check_theme_reference.py`，确认主题和参考文档一致。

删除主题：

1. 删除 `assets/` 里的 CSS。
2. 同步删除或标注 `references/theme-reference.md` 中对应主题。
3. 再运行 `check_theme_reference.py`，确认没有残留推荐。

修改主题：

1. 如果只改 CSS 细节但主题定位不变，不需要改参考文档。
2. 如果视觉气质、适用场景、代码块 / 表格表现发生变化，必须同步更新参考文档。
