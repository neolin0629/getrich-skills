#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zhihu-scraper: 用 Playwright 真实浏览器抓取知乎回答或文章，保存为 Markdown

用法:
    python scrape.py <zhihu_url> [--output <dir>]

Cookie 配置（首次运行需要）:
    python scrape.py --save-cookie "你的cookie字符串"
    # 或手动创建文件: ~/.zhihu_cookie（Linux/macOS）或 %USERPROFILE%\\.zhihu_cookie（Windows）
    # 文件内容直接就是 cookie 字符串（一行，无引号）

Cookie 文件格式:
    _zap=xxx; z_c0=xxx; ...
    （在 Chrome DevTools → Network → 请求头中复制 "Cookie:" 的值即可）
"""

import sys
import re
import os
import json
import argparse
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

# Windows 控制台 UTF-8 输出
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# 依赖检测
# ---------------------------------------------------------------------------
def ensure_deps():
    missing = []
    for pkg, import_name in [
        ("playwright", "playwright"),
        ("bs4", "bs4"),
        ("html2text", "html2text"),
        ("requests", "requests"),
        ("newspaper3k", "newspaper"),
        ("lxml_html_clean", "lxml_html_clean"),
    ]:
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pkg)
    if missing:
        import subprocess
        print(f"[zhihu-scraper] 安装缺少的依赖: {', '.join(missing)}")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet"] + missing)

ensure_deps()

# ============================================================
# 【可配置】默认保存路径（可按需修改）
# 首次运行时会自动检测并提示用户设置
# ============================================================
DEFAULT_OUTPUT_DIR = Path(r"{默认保存路径 - 首次运行自动设置}")
DEFAULT_IMAGES_DIR = Path(r"{默认配图路径 - 首次运行自动设置}")

# ============================================================
# 首次运行检测
# ============================================================
def check_first_run():
    """检测是否为首次运行，打印配置提示"""
    cookie_path = get_cookie_path()
    config_file = cookie_path.parent / ".zhihu_scraper_configured"
    
    # 检查是否已配置过
    if config_file.exists():
        return False  # 已配置过
    
    # 首次运行提示
    print("=" * 60)
    print("   zhihu-scraper 首次运行配置")
    print("=" * 60)
    print()
    print("【1】Cookie 配置（仅知乎需要）")
    print("    步骤：")
    print("    1. Chrome 打开 zhihu.com 并登录")
    print("    2. F12 → Network → 刷新页面 → 点击请求")
    print("    3. Request Headers 中复制 'cookie:' 的值")
    print("    4. 告诉AI: '保存我的知乎 Cookie'，然后粘贴字符串")
    print()
    print(f"    Cookie 保存路径: {cookie_path}")
    print()
    print("【2】保存路径配置")
    print(f"    文章目录: {DEFAULT_OUTPUT_DIR}")
    print(f"    配图目录: {DEFAULT_IMAGES_DIR}")
    print()
    print("    如需修改，请告诉AI: '修改zhihu-scraper保存路径'")
    print()
    print("=" * 60)
    
    # 标记已提示过（不标记为已配置，只标记已提示）
    try:
        config_file.write_text("first_run_shown", encoding="utf-8")
    except:
        pass
    
    return True

from bs4 import BeautifulSoup
import html2text as _html2text
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout


# ---------------------------------------------------------------------------
# Cookie 文件管理
# ---------------------------------------------------------------------------
def get_cookie_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("USERPROFILE", str(Path.home())))
    else:
        base = Path.home()
    return base / ".zhihu_cookie"


def load_cookie() -> str:
    """从 cookie 文件读取内容，文件不存在或为空时返回空字符串"""
    path = get_cookie_path()
    if path.exists():
        content = path.read_text(encoding="utf-8").strip()
        if content:
            return content
    return ""


def save_cookie(cookie_str: str) -> None:
    """保存 cookie 到文件"""
    path = get_cookie_path()
    path.write_text(cookie_str.strip(), encoding="utf-8")
    print(f"[zhihu-scraper] Cookie 已保存到: {path}")


# ---------------------------------------------------------------------------
# URL 类型判断
# ---------------------------------------------------------------------------
def classify_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path
    if "zhuanlan.zhihu.com" in host and re.match(r"^/p/\d+", path):
        return "article"
    if "zhihu.com" in host:
        if re.search(r"/answer/\d+", path):
            return "answer"
        if re.match(r"^/question/\d+/?$", path):
            return "question"
    return "unknown"


# ---------------------------------------------------------------------------
# 图片下载：将 HTML 中的 <img> 下载到本地，替换为本地路径
# ---------------------------------------------------------------------------
import hashlib, uuid

def download_images(html: str, images_dir: Path) -> tuple[str, list[str]]:
    """
    遍历 HTML 中所有 <img>，下载到 images_dir。
    返回 (替换后的HTML, 下载的图片路径列表)。
    """
    soup = BeautifulSoup(html, "html.parser")
    images_dir = Path(images_dir)
    downloaded = []

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if not src or src.startswith("data:"):
            continue

        # 跳过 SVG 图标（体积小无意义）
        if src.endswith(".svg") or "emoji" in src or "data:image" in src:
            continue

        # 生成唯一文件名，避免同名冲突
        ext = Path(urlparse(src).path).suffix or ".jpg"
        if ext.lower() not in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
            ext = ".jpg"
        filename = f"{uuid.uuid4().hex[:8]}{ext}"
        local_path = images_dir / filename

        try:
            img_resp = requests.get(src, headers=HEADERS_IMG, timeout=15, stream=True)
            img_resp.raise_for_status()
            images_dir.mkdir(parents=True, exist_ok=True)
            with open(local_path, "wb") as f:
                for chunk in img_resp.iter_content(8192):
                    f.write(chunk)
            downloaded.append(str(local_path))
            # 替换为相对路径（兼容 Obsidian）
            img["src"] = f"./配图/{filename}"
            img["data-src"] = ""  # 清除懒加载属性
        except Exception as e:
            print(f"    [img] 下载失败（图片保留原链接）: {src[:60]}... 原因: {e}")
            continue

    return str(soup), downloaded


HEADERS_IMG = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.zhihu.com/",
}


# ---------------------------------------------------------------------------
# HTML → Markdown
# ---------------------------------------------------------------------------
def html_to_markdown(html_fragment: str) -> str:
    # 先清理 SVG 占位符（知乎常用的占位图）
    soup = BeautifulSoup(html_fragment, "html.parser")
    for svg in soup.find_all("svg"):
        parent = svg.find_parent()
        if parent and parent.name == "span":
            parent.decompose()
        else:
            svg.decompose()
    # 也清理 data:image/svg+xml 的 img
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if "svg" in src.lower() or src.startswith("data:"):
            img.decompose()

    converter = _html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = False
    converter.body_width = 0
    converter.protect_links = True
    converter.wrap_links = False
    return converter.handle(str(soup)).strip()


# ---------------------------------------------------------------------------
# Cookie 字符串解析 → playwright cookies 列表
# ---------------------------------------------------------------------------
def parse_cookie_str(cookie_str: str, domain: str = ".zhihu.com") -> list:
    cookies = []
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" not in item:
            continue
        name, _, value = item.partition("=")
        cookies.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": domain,
            "path": "/",
        })
    return cookies


# ---------------------------------------------------------------------------
# Playwright 页面加载
# ---------------------------------------------------------------------------
def fetch_page(url: str, cookie_str: str = "") -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            viewport={"width": 1280, "height": 900},
        )

        if cookie_str.strip():
            domain = ".zhihu.com" if "zhihu.com" in url and "zhuanlan" not in url else ".zhuanlan.zhihu.com"
            context.add_cookies(parse_cookie_str(cookie_str, domain))
            print(f"[zhihu-scraper] 已注入 {len(parse_cookie_str(cookie_str))} 个 Cookie")

        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot}", lambda route: route.abort())

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except PWTimeout:
            pass

        for sel in [".RichContent-inner", ".Post-RichTextContainer", ".RichText", "article"]:
            try:
                page.wait_for_selector(sel, timeout=8000)
                break
            except PWTimeout:
                continue

        for expand_sel in ["button.ContentItem-expandButton", "div.RichContent-expandButton"]:
            try:
                btn = page.query_selector(expand_sel)
                if btn:
                    btn.click()
                    page.wait_for_timeout(800)
            except Exception:
                pass

        html = page.content()
        browser.close()
    return html


# ---------------------------------------------------------------------------
# 知乎回答解析
# ---------------------------------------------------------------------------
def scrape_answer(url: str, cookie_str: str = "", out_dir: Path = None) -> dict:
    print("[zhihu-scraper] 启动浏览器加载页面...")
    html = fetch_page(url, cookie_str)
    # 下载图片并替换链接
    if out_dir:
        print("[zhihu-scraper] 下载配图...")
        html, downloaded_imgs = download_images(html, DEFAULT_IMAGES_DIR)
        print(f"[zhihu-scraper] 配图下载完成: {len(downloaded_imgs)} 张")
    else:
        downloaded_imgs = []
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h1", class_=re.compile(r"QuestionHeader-title")) or soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "未知问题"

    author_tag = (
        soup.find("span", class_=re.compile(r"AuthorInfo-name"))
        or soup.find("a", class_=re.compile(r"AuthorInfo-name"))
    )
    author_name = author_tag.get_text(strip=True) if author_tag else "未知作者"

    vote_tag = soup.find("button", class_=re.compile(r"VoteButton--up"))
    vote_count = vote_tag.get_text(strip=True) if vote_tag else ""

    m = re.search(r"/answer/(\d+)", url)
    answer_id = m.group(1) if m else None
    content_div = None
    if answer_id:
        content_div = soup.find("div", attrs={"data-za-detail-view-id": answer_id})
    if not content_div:
        content_div = soup.find("div", class_=re.compile(r"RichContent-inner"))
    if not content_div:
        content_div = soup.find("div", class_=re.compile(r"RichText"))

    content_md = (
        html_to_markdown(str(content_div)) if content_div
        else "（内容提取失败，知乎可能需要登录，请检查 Cookie 是否有效）"
    )

    return {
        "type": "answer",
        "title": title,
        "author": author_name,
        "vote_count": vote_count,
        "content_md": content_md,
        "url": url,
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# 知乎专栏文章解析
# ---------------------------------------------------------------------------
def scrape_article(url: str, cookie_str: str = "", out_dir: Path = None) -> dict:
    print("[zhihu-scraper] 启动浏览器加载页面...")
    html = fetch_page(url, cookie_str)
    if out_dir:
        print("[zhihu-scraper] 下载配图...")
        html, downloaded_imgs = download_images(html, DEFAULT_IMAGES_DIR)
        print(f"[zhihu-scraper] 配图下载完成: {len(downloaded_imgs)} 张")
    else:
        downloaded_imgs = []
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("h1", class_=re.compile(r"Post-Title")) or soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else "未知文章"

    author_tag = (
        soup.find("a", class_=re.compile(r"AuthorInfo-name"))
        or soup.find("span", class_=re.compile(r"AuthorInfo-name"))
    )
    author_name = author_tag.get_text(strip=True) if author_tag else "未知作者"

    content_div = (
        soup.find("div", class_=re.compile(r"Post-RichTextContainer"))
        or soup.find("div", class_=re.compile(r"RichText"))
    )
    content_md = (
        html_to_markdown(str(content_div)) if content_div
        else "（内容提取失败，请检查 Cookie 是否有效）"
    )

    voteup_tag = soup.find("button", class_=re.compile(r"VoteButton"))
    voteup = voteup_tag.get_text(strip=True) if voteup_tag else ""

    return {
        "type": "article",
        "title": title,
        "author": author_name,
        "vote_count": voteup,
        "content_md": content_md,
        "url": url,
        "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------------------------------------------------------------------------
# Markdown 组装
# ---------------------------------------------------------------------------

# Obsidian 双向链接模板
OBSIDIAN_TEMPLATE = """---
title: "{{title}}"
source: "{{source}}"
author:
  - "{{author}}"
published: {{date}}
created: {{date}}
description: "{{description}}"
tags:
  - ""
status: inbox
---

# {{title}}

## 核心要点

{{content}}

## 与我的工作关联
- 

## 行动项
- [ ] 
"""


def build_markdown(data: dict, use_obsidian_template: bool = True) -> str:
    """构建 Markdown 内容，可选 Obsidian 模板格式"""

    if use_obsidian_template:
        # 使用 Obsidian 双向链接模板
        # 提取前200字作为描述
        desc = data["content_md"][:200].replace("\n", " ").strip() if data["content_md"] else ""
        date_str = datetime.now().strftime("%Y-%m-%d")

        content = OBSIDIAN_TEMPLATE
        content = content.replace("{{title}}", data["title"])
        content = content.replace("{{source}}", data["url"])
        content = content.replace("{{author}}", data["author"])
        content = content.replace("{{date}}", date_str)
        content = content.replace('{{description}}', desc)
        content = content.replace("{{content}}", data["content_md"])

        return content
    else:
        # 使用原有简洁格式
        lines = [f"# {data['title']}", ""]
        lines.append(f"> **作者**：{data['author']}")
        if data.get("vote_count"):
            lines.append(f"> **赞同数**：{data['vote_count']}")
        lines.append(f"> **来源**：[{data['url']}]({data['url']})")
        lines.append(f"> **抓取时间**：{data['scraped_at']}")
        lines += ["", "---", "", data["content_md"], ""]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 文件名
# ---------------------------------------------------------------------------
def safe_filename(title: str, max_len: int = 60) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", title)
    name = re.sub(r"\s+", "_", name.strip())
    return (name[:max_len] if len(name) > max_len else name) or "zhihu_content"


# ---------------------------------------------------------------------------
# Cookie 文件不存在时的引导信息（供 AI skill 层解析并呈现给用户）
# ---------------------------------------------------------------------------
COOKIE_NEED_GUIDE = """
=== COOKIE_NEED ===
首次使用需要配置一次知乎 Cookie，步骤如下：

1. 在 Chrome 中打开并登录 zhihu.com
2. 按 F12 → 切到 Network（网络）选项卡
3. 刷新页面，点击任意 www.zhihu.com 的请求
4. 在右侧 Request Headers 中找到 "cookie:" 字段
5. 复制冒号后面的整段字符串
6. 将 Cookie 字符串粘贴给 AI，告诉 AI "保存我的知乎 Cookie"

Cookie 文件路径: {cookie_path}
=== COOKIE_NEED ===
"""


# ---------------------------------------------------------------------------
# 通用网页抓取（用于非知乎网站）
# ---------------------------------------------------------------------------
def scrape_general(url: str, out_dir: Path = None) -> dict:
    """使用 newspaper3k 抓取通用网页内容"""

    try:
        from newspaper import Article as NPArticle

        article = NPArticle(url)
        article.download()
        article.parse()

        title = article.title or "无标题"
        authors = article.authors if article.authors else []
        author_str = authors[0] if authors else ""
        publish_date = article.publish_date.strftime("%Y-%m-%d") if article.publish_date else datetime.now().strftime("%Y-%m-%d")
        description = article.meta_description or ""

        # 获取正文内容（纯文本）
        content = article.text

        if not content:
            content = "（内容提取失败，可能需要反爬处理）"

        return {
            "type": "general",
            "title": title,
            "author": author_str,
            "publish_date": publish_date,
            "description": description[:200] if description else "",
            "content_md": content,
            "url": url,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    except Exception as e:
        return {
            "type": "general",
            "title": "抓取失败",
            "author": "",
            "publish_date": "",
            "description": "",
            "content_md": f"抓取失败: {e}",
            "url": url,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def main():
    # 首次运行检测
    is_first_run = check_first_run()
    
    parser = argparse.ArgumentParser(description="抓取知乎回答/文章或通用网页，保存为 Markdown")
    parser.add_argument("url", nargs="?", help="知乎回答/文章 URL 或其他网页 URL")
    parser.add_argument("--output", "-o", default=str(DEFAULT_OUTPUT_DIR), help=f"输出目录（默认：{DEFAULT_OUTPUT_DIR}）")
    parser.add_argument("--save-cookie", nargs="?", const="", help="保存 Cookie 到本地文件（仅用于知乎）")
    parser.add_argument("--simple", action="store_true", help="使用简洁模板而非 Obsidian 模板")
    args = parser.parse_args()

    script_path = __file__

    # ---- 模式 1：保存 Cookie ----
    if args.save_cookie is not None:
        if not args.save_cookie:
            print("[zhihu-scraper] 请在命令行参数中传入 Cookie 字符串，例如：")
            print(f"  python \"{script_path}\" --save-cookie \"你的cookie值\"")
            print()
            print("获取方法：在 Chrome DevTools → Network 中复制请求头 Cookie 值")
            sys.exit(1)
        save_cookie(args.save_cookie)
        print("[zhihu-scraper] Cookie 保存成功！以后无需再传入 Cookie 参数。")
        sys.exit(0)

    # ---- 模式 2：抓取内容 ----
    if not args.url:
        print(f"[zhihu-scraper] 用法: python {script_path} <URL> [--output <目录>] [--simple]")
        sys.exit(1)

    url = args.url.strip()
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    use_obsidian = not args.simple

    # 判断是否为知乎 URL
    if "zhihu.com" in url.lower():
        # 知乎抓取需要 Cookie
        url_type = classify_url(url)
        print(f"[zhihu-scraper] URL 类型: {url_type}")
        print(f"[zhihu-scraper] 正在抓取: {url}")

        cookie_str = load_cookie()
        if not cookie_str:
            cookie_path = str(get_cookie_path())
            print(COOKIE_NEED_GUIDE.format(cookie_path=cookie_path))
            sys.exit(1)

        if url_type == "article":
            data = scrape_article(url, cookie_str, out_dir)
        elif url_type in ("answer", "question"):
            data = scrape_answer(url, cookie_str, out_dir)
        else:
            print(f"[zhihu-scraper] 无法识别的知乎 URL: {url}")
            sys.exit(1)
    else:
        # 通用网页抓取
        print(f"[zhihu-scraper] 正在抓取通用网页: {url}")
        data = scrape_general(url, out_dir)

    # 构建 Markdown（默认使用 Obsidian 模板）
    md_content = build_markdown(data, use_obsidian_template=use_obsidian)

    filename = safe_filename(data["title"]) + ".md"
    filepath = out_dir / filename
    if filepath.exists():
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        filepath = out_dir / (safe_filename(data["title"]) + f"_{ts}.md")

    filepath.write_text(md_content, encoding="utf-8")
    print(f"[zhihu-scraper] 已保存: {filepath}")
    print(f"  标题: {data['title']}")
    print(f"  作者: {data['author']}")

    # 检测是否有代码内容（供 AI 后处理）
    code_indicators = ['def ', 'class ', 'import ', 'from ', 'function', 'const ',
                       'let ', 'var ', '=>', '```', 'if (', 'for (', 'while (',
                       'print(', 'return ', '.get_', '.value_counts', 'stock',
                       'import pandas', 'import numpy', 'import tushare', 'plt.', 'df[']
    has_code = any(indicator in md_content for indicator in code_indicators)
    if has_code:
        print("[zhihu-scraper] 检测到代码内容，可调用 AI 格式化代码块")

    print("\n--- METADATA_JSON ---")
    print(json.dumps({
        "saved_path": str(filepath),
        "title": data["title"],
        "author": data["author"],
        "type": data["type"],
        "url": url,
        "has_code": has_code,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
