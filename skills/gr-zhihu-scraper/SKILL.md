---
name: gr-zhihu-scraper
description: >
  网页剪藏工具 - 抓取知乎回答/专栏文章或通用网页，保存为 Markdown。
  支持知乎回答（zhihu.com/question/.../answer/...）、知乎专栏（zhuanlan.zhihu.com/p/...），
  以及微信公众号、博客、新闻等各类网页。
  触发词：知乎、zhihu、剪藏、网页转MD、保存文章、网页剪藏、抓取链接。
---

# Zhihu Scraper —— 网页剪藏 Skill

## 概述

将任意网页文章保存为本地 Markdown 文件，支持：

- **知乎内容**：知乎回答、知乎专栏文章（需要配置 Cookie）
- **通用网页**：微信公众号、博客、新闻等（直接抓取）
- **Obsidian 模板**：输出包含 frontmatter 的双向链接格式
- **配图下载**：自动下载正文配图，过滤 logo/广告等无关图片

## 触发条件

满足以下任意一条即激活本 Skill：

- 用户发送了包含 `zhihu.com` 或 `zhuanlan.zhihu.com` 的链接
- 用户发送了其他网页 URL（微信公众号、博客、新闻等）
- 用户说："剪藏这个"、"网页转 Markdown"、"保存这篇文章"、"抓取链接"

## 网站分类

| 网站类型 | 抓取方式                    | Cookie |
| ---- | ----------------------- | ------ |
| 知乎   | Playwright 浏览器 + Cookie | 需要     |
| 其他网站 | newspaper3k 直接请求        | 不需要    |

## 工作流程

### 【首次运行】自动配置提示

**首次运行时，脚本会自动打印配置提示**，包括：

1. **Cookie 配置说明**（仅知乎需要）
2. **当前保存路径**（可告诉AI修改）

### 流程一：配置知乎 Cookie（如未配置）

知乎有反爬限制，首次使用需要配置 Cookie：

1. 在 Chrome 中打开并登录 **[zhihu.com](https://www.zhihu.com)**
2. 按 **F12** 打开开发者工具，切到 **Network（网络）** 选项卡
3. 刷新页面，点击任意 `www.zhihu.com` 的请求
4. 在右侧 **Request Headers** 中找到 `cookie:` 字段
5. 复制冒号**后面**的整段字符串
6. 告诉 AI："**保存我的知乎 Cookie**"，然后把字符串粘贴给 AI

### 流程二：抓取网页内容

1. 运行抓取脚本：
   
   ```bash
   <python> "<skill_dir>/scripts/scrape.py" "<URL>"
   ```

2. **检查脚本输出**：
   
   - 知乎 URL 若出现 `=== COOKIE_NEED ===` → 引导用户配置 Cookie
   - 若出现 `"has_code": true` → 文章包含代码，需要 AI 格式化
   - 若出现 `--- METADATA_JSON ---` → 抓取成功

3. **AI 后处理（如检测到代码）**：
   
   - 读取抓取的 Markdown 文件
   - 识别代码块并优化格式（语言标注、缩进、语法高亮）
   - 重写文件

4. 向用户汇报结果（保存路径、标题、作者）

## 输出文件格式

### Markdown 文件（Obsidian 双向链接模板）

```markdown
---
title: "文章标题"
source: "https://example.com/article"
author:
  - "作者名"
published: 2026-04-27
created: 2026-04-27
description: "文章描述..."
tags:
  - ""
status: inbox
---

# 文章标题

## 核心要点

正文内容...

## 与我的工作关联
- 

## 行动项
- [ ] 
```

## 路径配置

脚本顶部常量可按需修改：

```python
DEFAULT_OUTPUT_DIR = Path(r"\网页剪藏")
DEFAULT_IMAGES_DIR = Path(r"\网页剪藏\配图")
```

## 注意事项

| 情况           | 处理方式                    |
| ------------ | ----------------------- |
| Cookie 文件不存在 | 引导用户按流程配置（仅知乎需要）        |
| 正文提取失败       | Cookie 可能过期，或网站反爬限制     |
| 标题含特殊字符      | 脚本自动清理，生成合法文件名          |
| 同名文件已存在      | 自动在文件名末尾追加时间戳           |
| 通用网页抓取失败     | newspaper3k 限制，部分网站可能失败 |

## 脚本参数

```bash
python scrape.py <URL> [选项]

参数:
  URL                      知乎回答/文章 URL 或其他网页 URL

选项:
  --output, -o <目录>      输出目录（默认：剪藏入库目录）
  --save-cookie <字符串>   保存知乎 Cookie（仅首次需要）
  --simple                 使用简洁模板而非 Obsidian 模板
```

## 脚本位置

`scripts/scrape.py` —— 核心脚本

## 更新日志

| 日期         | 更新内容                           |
| ---------- | ------------------------------ |
| 2026-04-27 | v2.1 - 首次运行自动打印Cookie和路径配置提示   |
| 2026-04-27 | v2.0 - 融合通用网页抓取，添加 Obsidian 模板 |
