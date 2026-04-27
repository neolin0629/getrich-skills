# getrich-skill

一套面向量化投资、内容创作和效率提升的 WorkBuddy AI Skill 集合，涵盖周复盘自动化、微信文章抓取、Markdown 排版主题、HTML 转 PDF、中文写作规范等场景。

---

## 安装

使用 `npx skills` CLI 安装单个 skill：

```bash
# 安装所有skills
npx skills add https://github.com/buyixiao/getrich-skill -g -y
```
在安转的项目中可以选择给那些支持的客户的安装。

> **提示**：安装后重启 AI 客户端，skill 即自动激活。技能汇总安装在 `~/.agents/skills/` 目录下。
> claude code 是安转在 `~/.claude/skills/` 下。workbuddy 可以识别安装在 `~/.codebuddy/skills/` 下的skills。

---

## Skills 一览

| Skill | 一句话介绍 |
|---|---|
| [weekly-review](#-weekly-review--a-股周复盘) | A 股·期权·全球市场·流动性自动化周报 |
| [wechat-article-capture](#-wechat-article-capture--微信文章抓取入库) | 微信公众号文章一键转 Markdown 入库 |
| [markdown-themes](#-markdown-themes--markdown-主题排版) | Markdown 转带主题的 HTML，支持多种视觉风格 |
| [html-to-pdf](#-html-to-pdf--网页导出-pdf) | 本地/在线 HTML 稳定导出为 PDF |
| [chinese-typography-rules](#-chinese-typography-rules--中文排版规范) | 中英文空格、全角标点、数学符号等中文排版规则 |
| [content-ai-avoid](#-content-ai-avoid--去-ai-味写作指令) | 22 条规避 AI 写作指纹的动笔前自检清单 |

---

## 📊 weekly-review — A 股周复盘

**触发词**：`周复盘`、`复盘本周`、`weekly review`、`流动性周报`

自动完成 10 步工作流，生成深色主题 HTML 周报，涵盖行情、流动性、期权和宏观事件。

### 报告包含

- **本周快照图**（4 张）：A 股 5 大指数 + 全球市场 + 商品期货 + 期权 IV
- **流动性监测仪表盘**（9 张）：央行资产 + 货币市场利率 + 融资余额 + M2 社融 + 美元利率 + Shibor + 信号灯 + 买断式逆回购
- **宏观事件**：按重要性 ★★★ / ★★ / ★ 分级
- **下周展望 + 操作建议**

### 数据来源

| 优先级 | 数据源 | 覆盖范围 |
|---|---|---|
| P1 | AkShare | A 股现货 / 国内宏观 / 期权 IV |
| P1 | yfinance | 全球指数 / 商品期货 |
| P1 | FRED API | 美联储总资产 / 美元利率 |
| P2 | 央行网站爬取 | 买断式逆回购月度数据 |

### 快捷命令

```
复盘本周        ← 执行完整 10 步流程，生成 HTML 报告
流动性周报      ← 仅执行流动性数据采集 + 信号灯 + 图表
修正图表        ← 重新生成所有图表 PNG
```

### 核心脚本

```bash
skills/weekly-review/scripts/fetch_data.py          # 数据采集
skills/weekly-review/scripts/generate_charts_mpl.py # 图表生成（matplotlib 深色主题）
skills/weekly-review/scripts/build_report_v2.py     # HTML 报告生成
skills/weekly-review/scripts/fetch_pbc_repo.py      # 央行买断式逆回购爬取
```

> **注意**：中国股市颜色规范——涨 = 红色 `#e74c3c`，跌 = 绿色 `#27ae60`。

---

## 📥 wechat-article-capture — 微信文章抓取入库

**触发词**：`抓取微信文章`、`微信公众号`、`wechat`、`微信文章转 markdown`、`公众号文章入库`

将微信公众号文章 URL 转换为本地 Markdown，自动下载配图、生成标准化 frontmatter，存入指定目录。

### 用法

**直接对话中使用**：发送文章 URL，AI 自动完成抓取 + 入库 + 代码块整理。

**命令行调用**：

```bash
# 基本用法（保存到当前目录 wechat-captures/）
python skills/wechat-article-capture/scripts/capture.py "https://mp.weixin.qq.com/s/xxx"

# 指定输出目录
python skills/wechat-article-capture/scripts/capture.py "URL" --output-dir "./inbox/wechat"

# 指定文件名
python skills/wechat-article-capture/scripts/capture.py "URL" --filename "自定义文件名"
```

### 输出结构

```
wechat-captures/
├── 文章标题.md
└── 配图/
    ├── img_000_4d8216f7.gif
    └── img_001_8f18712c.jpg
```

Markdown 文件含标准 frontmatter（`title` / `source` / `author` / `created` / `tags` / `status` / `description`）。

### 配置

复制 `config.example.json` 为 `config.json`，可自定义输出目录、图片子目录名、默认标签等。配置优先级：CLI 参数 > 环境变量 > `config.json` > 内置默认值。

> **仅支持公开已发布文章**，无需登录微信。

---

## 🎨 markdown-themes — Markdown 主题排版

**触发词**：`markdown 转 html`、`md 转 html`、`给 Markdown 套主题`、`公众号 / 博客 / 研报排版`

根据文章气质智能推荐主题，将 Markdown 转换为带视觉样式的 HTML。

### 用法

```bash
# 使用推荐主题转换
python skills/markdown-themes/scripts/render_markdown.py article.md --theme Knowledge-Base

# 指定输出路径
python skills/markdown-themes/scripts/render_markdown.py article.md --theme Academic-Paper --output out.html

# 列出所有可用主题
python skills/markdown-themes/scripts/render_markdown.py --list-themes
```

### 主题选择指南

| 场景 | 推荐主题 |
|---|---|
| 技术文章 / 知识库（含代码块） | `Knowledge-Base`、`Cyberpunk-Neon`、`Academic-Paper` |
| 正式研报 / 论文 / 课程讲义 | `Academic-Paper`、`zj`、`g2` |
| 叙事 / 复盘 / 随笔 | `Sunset-Film`、`Morandi-Forest`、`Luxury-Gold` |
| 传播型 / 需要一眼抓人的内容 | `Neo-Brutalism`、`Bauhaus`、`Aurora-Glass` |
| 高品质长文排版（推荐字体：仓耳今楷 02） | `Kami` |

### 与 html-to-pdf 配合

```bash
# 先渲染 HTML
python skills/markdown-themes/scripts/render_markdown.py article.md --theme Knowledge-Base --output article.html

# 再导出 PDF
python skills/html-to-pdf/scripts/html_to_pdf.py article.html --prefer-css-page-size
```

---

## 📄 html-to-pdf — 网页导出 PDF

**触发词**：`html 转 pdf`、`网页导出 PDF`、`文章 PDF`、`报告 PDF`

将本地 HTML 文件或在线页面稳定导出为 PDF，基于 Chromium/Chrome 无头打印。

### 用法

```bash
# 基本用法（输出到同目录，同名 .pdf）
python skills/html-to-pdf/scripts/html_to_pdf.py input.html

# 指定输出路径
python skills/html-to-pdf/scripts/html_to_pdf.py input.html --output report.pdf

# A4 纸 + 打印媒体 + 尊重 CSS 页面尺寸
python skills/html-to-pdf/scripts/html_to_pdf.py input.html \
  --format A4 \
  --media print \
  --prefer-css-page-size

# 含远程图片 / 延迟渲染的页面，增加等待时间
python skills/html-to-pdf/scripts/html_to_pdf.py input.html --wait-ms 2000
```

### 常见问题

| 问题 | 解决方案 |
|---|---|
| 找不到浏览器 | 安装 Chrome / Chromium / Edge，或设置 `CHROME_PATH=/path/to/browser` |
| 本地图片 / CSS 丢失 | 确认 HTML 与资源的相对路径未移动 |
| 背景色未出现 | 脚本默认开启 `printBackground`，检查是否被覆盖 |
| 远程资源未加载 | 增加 `--wait-ms 1000` 至 `3000` |

---

## ✍️ chinese-typography-rules — 中文排版规范

**触发词**：`写中文`、`中文文案`、`排版规范`、`公众号`、`小红书`、`研报`

写作时自动遵循中文内容的排版规则，包括：

- **空格**：中英文之间加空格、中文与数字之间加空格
- **标点**：全角标点、直角引号 `「」`、省略号 `……`、破折号 `——`
- **大小写**：专有名词按官方写法（GitHub / iPhone / macOS）
- **数字**：半角数字，单位规则统一
- **数学与金融**：比较符号前后加空格（`夏普 > 1.5`），正负号紧贴数字（`+2.3%`）
- **用字规范**："的 / 地 / 得"区分，人称代词使用规范

与 `content-ai-avoid` 联动——任何中文写作均同时遵循本排版规则。

---

## 🤖 content-ai-avoid — 去 AI 味写作指令

**触发词**：`写文章`、`写笔记`、`写公众号`、`写小红书`、`润色`、`避免 AI 味`

动笔前强制自检，规避 22 种 AI 写作指纹，产出更接近人类自然写作风格的内容。

### 适用场景

公众号长文、小红书笔记、微博、短视频文案、商业文案、金融 / 量化分析报告、立人设内容。

### 核心原则

1. **有话要说**：先想清楚核心观点，技巧是包装，不是填充
2. **保留毛边**：没想通的地方留着，不要磨平
3. **动笔前三问**：核心一句话是什么？哪里没想通？读者只能记住什么？

### 22 条规避清单（节选）

| 类别 | 典型 AI 行为 | 正确做法 |
|---|---|---|
| 论证 | 堵住所有反驳 | 只回应真实被问过的反驳 |
| 情绪 | 通篇斩钉截铁 | 不确定的地方写出来 |
| 修辞 | 段段收束金句 | 全文最多一两个爆发句 |
| 语言 | 滥用「然而」「事实上」「值得注意的是」 | 写完删掉一半连接词 |
| 结构 | 结尾「愿你…」「共勉」 | 直接删掉最后一段 |

金融 / 量化内容特别适用：不确定性必须写出来（`#9`），避免「本质上市场是 XX」的大命题（`#22`）。

---

## 环境依赖

```bash
# Python（各 skill 脚本均需）
pip install requests beautifulsoup4 html2text  # wechat-article-capture
pip install akshare yfinance fredapi matplotlib pandas  # weekly-review
pip install playwright  # html-to-pdf（需同时安装浏览器）
playwright install chromium
```

---

## 目录结构

```
getrich-skill/
├── skills/
│   ├── weekly-review/          # A 股周复盘
│   ├── wechat-article-capture/ # 微信文章抓取入库
│   ├── markdown-themes/        # Markdown 主题渲染
│   ├── html-to-pdf/            # HTML 转 PDF
│   ├── chinese-typography-rules/ # 中文排版规范
│   └── content-ai-avoid/       # 去 AI 味写作指令
└── README.md
```

---

## License

MIT
