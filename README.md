# getrich-skills

一套面向量化复盘、内容创作、网页剪藏和文档处理的 AI Skill 集合，目前包含 9 个 Skill。

## 安装

使用以下命令，将全部 Skill 全局安装到 Claude Code 和 Codex：

```bash
npx skills add neolin0629/getrich-skills -a claude-code -a codex -g -y
```

安装完成后，重启对应的 AI 客户端。

## Skill 一览

| Skill | 功能 |
| --- | --- |
| `gr-weekly-review` | 采集 A 股、期权、全球市场、商品和流动性数据，生成周复盘报告 |
| `gr-wechat-article-capture` | 将微信公众号文章转换为 Markdown，并下载正文图片、补充 frontmatter |
| `gr-zhihu-scraper` | 将知乎回答、知乎专栏或通用网页剪藏为 Markdown |
| `gr-markdown-themes` | 根据内容选择主题，将 Markdown 渲染为带样式的 HTML |
| `gr-html-to-pdf` | 使用 Chrome、Chromium 或 Edge 将本地 / 在线 HTML 导出为 PDF |
| `gr-chinese-typography-rules` | 统一中文排版，覆盖中英文空格、标点、数字、日期和金融表达 |
| `gr-content-ai-avoid` | 按 6 个层级、39 条规则规避中文写作中的 AI 指纹，并提供脚本自检 |
| `gr-ob-fix-color-tags` | 用全角括号包裹 Obsidian `prompts/` 目录中的十六进制颜色代码，避免被识别为标签 |
| `gr-ob-rm-prompts-formatter` | 批量删除 Obsidian `prompts/` 目录中 Markdown 文件开头的 YAML frontmatter |

安装后，可以直接描述任务，也可以显式指定 Skill 名称。例如：

```text
使用 gr-weekly-review 复盘本周
使用 gr-markdown-themes 把 article.md 转成 HTML
使用 gr-chinese-typography-rules 润色这段中文
```

`gr-chinese-typography-rules` 负责排版，`gr-content-ai-avoid` 负责表达；创作中文内容时可配合使用。

## 可选依赖

部分 Skill 包含 Python 脚本，按需安装依赖：

```bash
# 微信文章抓取
python3 -m pip install requests beautifulsoup4 html2text

# 知乎 / 网页剪藏
python3 -m pip install requests beautifulsoup4 html2text playwright
python3 -m playwright install chromium

# 量化周复盘
python3 -m pip install akshare yfinance pandas numpy matplotlib pyecharts requests beautifulsoup4
```

导出 PDF 还需要本机安装 Chrome、Chromium 或 Edge。知乎内容可能需要已登录账号的 Cookie；各 Skill 的具体用法和限制以对应目录内的 `SKILL.md` 为准。

## 目录结构

```text
skills/
├── gr-chinese-typography-rules/
├── gr-content-ai-avoid/
├── gr-html-to-pdf/
├── gr-markdown-themes/
├── gr-ob-fix-color-tags/
├── gr-ob-rm-prompts-formatter/
├── gr-wechat-article-capture/
├── gr-weekly-review/
└── gr-zhihu-scraper/
```

## License

MIT
