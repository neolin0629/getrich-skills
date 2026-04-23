---
name: wechat-article-capture
description: 微信公众号文章抓取与入库。将微信文章URL转换为Markdown文件，自动下载配图到本地、添加frontmatter，存入指定目录。代码块格式由AI事后整理。触发词：抓取微信文章、微信公众号、wechat、微信文章转markdown、公众号文章入库、保存微信文章、微信收藏
---

# wechat-article-capture — 微信公众号文章抓取入库

## 功能说明

接收微信公众号文章 URL → 抓取全文内容 → 下载图片到本地 → 转换为 Markdown → 存入指定目录（默认 `5-收件箱/微信收藏/`）

**代码块格式由 AI 事后整理**（微信每行代码是独立HTML标签，脚本自动合并不可靠）

## 输入

- **URL**：微信公众号文章完整地址（`https://mp.weixin.qq.com/s/xxx`）
- **目标目录**（可选）：默认 `C:\Users\Administrator\Nutstore\1\Miller\5-收件箱\微信收藏\`
- **文件名**（可选）：默认用文章标题自动命名

## 输出

`.md` 文件 + `配图/` 子目录，文件结构示例：

```
5-收件箱/微信收藏/
├── 量化小助手：LSTM在日内交易中的实战应用.md
└── 配图/
    ├── img_000_4d8216f7f628.gif
    ├── img_001_8f18712cbd47.jpg
    └── ...
```

`.md` 包含标准化 frontmatter：

```yaml
---
title: "文章标题"
source: "微信"
author:
  - "公众号名称"
created: YYYY-MM-DD
tags: ["公众号", "待分类"]
category: 待分类
status: inbox
description: "文章摘要"
---

正文内容（Markdown格式，图片引用本地配图/路径）
```

## 使用方式

### 方式一：直接对话中使用
发送公众号文章 URL，我会自动完成抓取、入库、整理代码块。

### 方式二：命令行调用
```powershell
# 基本用法（默认保存到 5-收件箱）
python "C:\Users\Administrator\.workbuddy\skills\wechat-article-capture\scripts\capture.py" "<文章URL>"

# 指定保存目录
python "C:\Users\Administrator\.workbuddy\skills\wechat-article-capture\scripts\capture.py" "<文章URL>" "C:\目标目录"

# 指定文件名
python "C:\Users\Administrator\.workbuddy\skills\wechat-article-capture\scripts\capture.py" "<文章URL>" "" "自定义文件名"
```

## 执行流程

### 阶段1：脚本抓取
1. 验证 URL 是否为微信文章地址
2. 请求文章页面（模拟浏览器 headers）
3. 提取：标题、公众号名、发布日期、摘要、hashtag标签
4. 定位正文区域，提取 `<img data-src>` 图片URL
5. 用 `__IMG_N__` 标记记录图片位置，HTML → Markdown 转换
6. 下载图片到 `配图/` 子目录，替换标记为本地引用 `![](配图/xxx.jpg)`
7. 清理页脚（微信号、网址、点赞提示）
8. 生成 frontmatter，写入目标文件
9. 输出文件路径：`[OK] 已保存: <filepath>`

### 阶段2：AI 整理代码块
脚本执行完成后，AI 自动执行：
1. 读取刚保存的 `.md` 文件
2. 检查代码块状态：微信文章的代码块会被 html2text 拆分为多个单行 ```...``` 块
3. **重新请求文章 URL**，从 HTML 的 `code-snippet__fix` 结构中提取完整多行代码
4. 用完整代码替换 markdown 中的分散单行代码块
5. 写回文件
6. 输出完成摘要

## 技术说明

- 使用 `requests` + `BeautifulSoup` + `html2text` 抓取
- **仅限公开已发布文章**，无需登录
- **图片本地化**：从 `<img data-src>` 提取 `mmbiz.qpic.cn` 真实 URL，下载到 `配图/` 子目录，markdown 中引用本地路径
- 图片扩展名从 `wx_fmt` 查询参数推断，并根据 Content-Type 修正
- **代码块由 AI 整理**：微信每行代码是独立HTML标签，html2text 转换后代码行被正文分隔。AI 通过重新请求文章HTML，从 `code-snippet__fix` 结构中提取完整代码，替换到 markdown 中
- 文件名自动清理非法字符，长度限制 200 字
