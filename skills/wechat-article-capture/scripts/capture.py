#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信公众号文章抓取脚本
用法: python capture.py <url> [输出目录] [文件名]
"""

import sys
import os
import re
import requests
from bs4 import BeautifulSoup
import html2text
from datetime import datetime
import urllib.parse
import hashlib

# ---------- 配置 ----------
DEFAULT_OUTPUT_DIR = r"C:\Users\Administrator\Nutstore\1\Miller\5-收件箱\微信收藏"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://mp.weixin.qq.com/",
}

TIMEOUT = 15


def extract_article_id(url: str) -> str:
    """从URL中提取文章ID或用URL生成短哈希作为文件名备选"""
    match = re.search(r'mid=(\w+)|sn=(\w+)', url)
    if match:
        for g in match.groups():
            if g:
                return g[:16]
    match = re.search(r'/s/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    return hashlib.md5(url.encode()).hexdigest()[:12]


def sanitize_filename(name: str) -> str:
    """移除文件名中的非法字符"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = name.strip()
    return name[:200] if name else "untitled"


def parse_date(date_str: str) -> str:
    """解析各种日期格式，返回 YYYY-MM-DD"""
    patterns = [
        (r'(\d{4})年(\d{1,2})月(\d{1,2})日', r'\1-\2-\3'),
        (r'(\d{4})-(\d{1,2})-(\d{1,2})', r'\1-\2-\3'),
        (r'([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})', lambda m: datetime.strptime(
            f"{m.group(3)} {m.group(1)} {m.group(2)}", "%Y %b %d").strftime("%Y-%m-%d")),
    ]
    for pattern, repl in patterns:
        m = re.search(pattern, date_str)
        if m:
            if callable(repl):
                return repl(m)
            return re.sub(pattern, repl, date_str)
    return datetime.now().strftime("%Y-%m-%d")


def fetch_article(url: str):
    """抓取微信文章页面"""
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    return resp.text


def extract_metadata(html: str) -> dict:
    """从HTML中提取元数据"""
    soup = BeautifulSoup(html, 'html.parser')
    meta = {}

    # 标题
    og_title = soup.find('meta', attrs={'property': 'og:title'})
    if og_title:
        meta['title'] = og_title.get('content', '').strip()
    if not meta.get('title'):
        h1 = soup.find('h1', class_='rich_media_title')
        if h1:
            meta['title'] = h1.get_text(strip=True)

    # 描述/摘要
    og_desc = soup.find('meta', attrs={'property': 'og:description'})
    if og_desc:
        meta['description'] = og_desc.get('content', '').strip()

    # 作者/公众号名
    full_text = soup.get_text()
    author_found = False

    m = re.search(r'微信号\s*[\|｜]\s*(.{2,20}?)(?=\s*(?:www\.|财神|点赞|转发|分享|投稿|你的|$))', full_text)
    if m:
        candidate = m.group(1).strip()
        if candidate and candidate not in ('你的转载或投稿', ''):
            meta['author'] = candidate
            author_found = True

    if not author_found:
        author_tag = soup.find('meta', attrs={'name': 'author'})
        if not author_tag:
            author_tag = soup.find('meta', attrs={'property': 'og:site_name'})
        if not author_tag:
            author_tag = soup.find('a', class_=re.compile(r'rich_media_meta.*nickname'))
        if not author_tag:
            author_tag = soup.find('span', class_=re.compile(r'rich_media_meta.*nickname'))
        if author_tag:
            meta['author'] = author_tag.get_text(strip=True)
            author_found = True

    if not author_found:
        meta['author'] = '未知公众号'

    # 发布日期
    date_tag = soup.find('em', id='publish_time')
    if not date_tag:
        date_tag = soup.find('span', class_='rich_media_meta rich_media_meta_text')
    if date_tag:
        date_text = date_tag.get_text(strip=True)
        meta['date'] = parse_date(date_text)
    if not meta.get('date'):
        meta['date'] = datetime.now().strftime("%Y-%m-%d")

    # 描述/摘要
    desc = soup.find('meta', attrs={'name': 'description'})
    if desc and not meta.get('description'):
        meta['description'] = desc.get('content', '').strip()

    # 自动提取文末 hashtag 作为标签
    full_text = soup.get_text()
    hashtags = re.findall(r'#([^\s#]+)', full_text)
    if hashtags:
        seen = set()
        tags = []
        for tag in hashtags:
            t = tag.strip()
            if t and t not in seen and len(t) < 20:
                seen.add(t)
                tags.append(t)
                if len(tags) >= 8:
                    break
        if tags:
            meta['tags'] = tags

    return meta, soup


def _get_safe_filename(url: str, idx: int) -> str:
    """从图片URL生成安全文件名，优先从 wx_fmt 参数和路径推断扩展名"""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    ext = os.path.splitext(path)[1]

    # 微信图片 URL 路径通常以 /640 结尾，无扩展名
    # 优先从 wx_fmt 查询参数获取真实格式
    if not ext or len(ext) > 5:
        qs = urllib.parse.parse_qs(parsed.query)
        fmt = qs.get('wx_fmt', [''])[0].lower()
        fmt_map = {'jpeg': '.jpg', 'jpg': '.jpg', 'png': '.png', 'gif': '.gif', 'webp': '.webp'}
        ext = fmt_map.get(fmt, '')

    # 备选：从路径段推断（如 /mmbiz_jpg/ → .jpg）
    if not ext or len(ext) > 5:
        for seg, e in [('mmbiz_jpg', '.jpg'), ('mmbiz_png', '.png'), ('mmbiz_gif', '.gif'), ('mmbiz_webp', '.webp')]:
            if seg in path:
                ext = e
                break

    if not ext or len(ext) > 5:
        ext = '.jpg'

    safe = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"img_{idx:03d}_{safe}{ext}"


def _download_images(img_urls: list, article_dir: str, session_headers: dict) -> dict:
    """
    下载图片到 article_dir/配图/ 目录。
    img_urls: 已提取的图片 URL 列表。
    返回 {序号: 本地路径} 映射。
    """
    if not img_urls:
        print(f"[配图] 未发现可下载的图片URL")
        return {}

    img_dir = os.path.join(article_dir, '配图')
    os.makedirs(img_dir, exist_ok=True)

    idx_to_local = {}
    valid_count = sum(1 for u in img_urls if u)
    print(f"[配图] 提取到 {valid_count} 张图片，开始下载...")

    for idx, src in enumerate(img_urls):
        if not src:
            continue

        fname = _get_safe_filename(src, idx)
        fpath = os.path.join(img_dir, fname)
        ext = os.path.splitext(fname)[1]

        if os.path.exists(fpath):
            idx_to_local[idx] = fpath
            continue

        try:
            img_headers = dict(session_headers)
            img_headers['Referer'] = 'https://mp.weixin.qq.com/'
            resp = requests.get(src, headers=img_headers, timeout=20, stream=True)
            resp.raise_for_status()
            content_type = resp.headers.get('Content-Type', '')
            if 'text' in content_type and 'html' in content_type:
                print(f"[配图] 跳过非图片响应: {fname}")
                continue
            chunk = next(resp.iter_content(1024), b'')
            if not chunk:
                continue
            # 根据 Content-Type 修正扩展名
            actual_ext = ext
            if 'png' in content_type:
                actual_ext = '.png'
            elif 'gif' in content_type:
                actual_ext = '.gif'
            elif 'webp' in content_type:
                actual_ext = '.webp'
            elif 'jpeg' in content_type or 'jpg' in content_type:
                actual_ext = '.jpg'
            if actual_ext != ext:
                fname = fname.replace(ext, actual_ext)
                fpath = os.path.join(img_dir, fname)

            with open(fpath, 'wb') as f:
                f.write(chunk)
                for chunk2 in resp.iter_content(8192):
                    f.write(chunk2)
            idx_to_local[idx] = fpath
            print(f"[配图] 下载成功: {fname}")
        except Exception as e:
            print(f"[配图] 下载失败 [{fname}]: {e}")
            continue

    downloaded = len(idx_to_local)
    if downloaded > 0:
        print(f"[配图] 完成，共下载 {downloaded} 张")
    else:
        print(f"[配图] 全部下载失败")
        try:
            os.rmdir(img_dir)
        except Exception:
            pass
    return idx_to_local


def _replace_image_markers(md: str, img_map: dict, article_dir: str) -> str:
    """将 markdown 中的 __IMG_N__ 标记替换为本地图片引用"""
    for idx_str, local_path in img_map.items():
        try:
            rel_path = os.path.relpath(local_path, article_dir).replace('\\', '/')
        except ValueError:
            rel_path = local_path.replace('\\', '/')
        marker = f'__IMG_{idx_str}__'
        md = md.replace(marker, f'![]({rel_path})')
    # 清理未替换的标记
    md = re.sub(r'__IMG_\d+__', '', md)
    return md


def extract_content(soup: BeautifulSoup):
    """提取正文内容区域，返回 (markdown, img_urls)"""
    # 微信文章主体
    content_div = soup.find('div', id='js_content') or soup.find('div', class_='rich_media_content')

    if not content_div:
        content_div = soup.find('div', class_='article-content') or soup.find('div', class_='entry-content')

    if not content_div:
        raise ValueError("无法定位文章正文区域，请确认URL是否正确")

    # 移除干扰元素
    for tag in content_div.find_all(['script', 'style', 'iframe', 'noscript', 'audio']):
        tag.decompose()

    # 移除微信文章页脚
    for selector in [
        'div.js_bottom_area',
        'div.rich_media_extra',
        'div#js_pc_qr_code',
        'div.rich_media QR code',
        'div.profile_container',
    ]:
        for footer in content_div.select(selector):
            footer.decompose()

    for tag in content_div.find_all(string=re.compile(r'微信号\s*\|')):
        parent = tag.find_parent()
        if parent:
            parent.decompose()

    # 图片提取：先提取 data-src URL，再做位置标记
    img_tags = content_div.find_all('img')
    img_urls = []
    for idx, img in enumerate(img_tags):
        src = img.get('data-src', '') or img.get('src', '')
        if src and 'mmbiz.qpic.cn' in src:
            img_urls.append(src)
        else:
            img_urls.append('')  # 占位，保持索引对齐
        # 替换为位置标记
        marker = soup.new_tag('p')
        marker.string = f'__IMG_{idx}__'
        img.replace_with(marker)

    # 转 Markdown
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.ignore_emphasis = False
    h.body_width = 0
    h.unicode_snob = True

    markdown = h.handle(str(content_div))
    md = markdown.strip()

    # 移除文末页脚（微信号块、网址、点赞提示等）
    # 注意：使用 [^\n] 代替 . 以避免跨行吞掉 __IMG_N__ 标记
    footer_patterns = [
        r'\n*微信号\s*[\|｜]\s*[^\n]+',
        r'\n+www\.\S+',
        r'\n+财神都在点赞[^\n]*',
        r'\n+请用您发财的手[^\n]*',
        r'\n+分享、推荐和[^*\n]*',
        r'\n{3,}$',
    ]
    for pattern in footer_patterns:
        md = re.sub(pattern, '', md, flags=re.IGNORECASE)

    # 移除全文开头的"点击上方蓝字"引导语
    md = re.sub(r'\*\*\s*点击上方蓝字\s*\|.*?\*\*', '', md, flags=re.DOTALL).strip()

    return md, img_urls


def build_frontmatter(meta: dict) -> str:
    """构建 YAML frontmatter"""
    title = meta.get('title', '未命名文章')
    author = meta.get('author', '未知公众号')
    date = meta.get('date', datetime.now().strftime('%Y-%m-%d'))
    description = meta.get('description', '')
    tags = meta.get('tags', [])

    default_tags = ['公众号']
    all_tags = (tags + [t for t in default_tags if t not in (tags or [])]) if tags else default_tags
    tags_str = ', '.join(f'"{t}"' for t in all_tags) if all_tags else ''

    description = description.replace('"', '\\"')

    fm = f'''---
title: "{title}"
source: "微信"
author:
  - "{author}"
created: {date}
tags: [{tags_str}]
category: 待分类
status: inbox
description: "{description}"
---

'''
    return fm


def save_markdown(filepath: str, content: str):
    """确保目录存在，写入文件"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"[OK] 已保存: {filepath}")


def main():
    # 解决 Windows PowerShell 控制台 GBK 编码问题
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

    if len(sys.argv) < 2:
        print("用法: python capture.py <url> [输出目录] [文件名]")
        sys.exit(1)

    url = sys.argv[1].strip()

    if 'mp.weixin.qq.com' not in url:
        print("[错误] 必须是微信公众号文章地址 (mp.weixin.qq.com)")
        sys.exit(1)

    output_dir = sys.argv[2].strip() if len(sys.argv) > 2 else DEFAULT_OUTPUT_DIR
    custom_filename = sys.argv[3].strip() if len(sys.argv) > 3 else None

    print(f"[抓取中] {url}")

    # 1. 抓取
    html = fetch_article(url)

    # 2. 提取元数据
    meta, soup = extract_metadata(html)

    title = meta.get('title', '')
    if not title:
        print("[警告] 无法提取标题，使用默认名")
        title = "未命名文章"

    # 3. 提取正文
    print("[解析中] 提取正文内容...")
    try:
        md_content, img_urls = extract_content(soup)
    except ValueError as e:
        print(f"[错误] {e}")
        sys.exit(1)

    # 4. 确定保存路径
    if custom_filename:
        filename = sanitize_filename(custom_filename)
        if not filename.endswith('.md'):
            filename += '.md'
    else:
        filename = sanitize_filename(title) + '.md'

    filepath = os.path.join(output_dir, filename)

    if os.path.exists(filepath):
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(filepath):
            filepath = os.path.join(output_dir, f"{base}_{counter}{ext}")
            counter += 1

    article_dir = os.path.dirname(filepath)

    # 5. 下载图片到 配图/ 子目录
    img_map = _download_images(img_urls, article_dir, HEADERS)

    # 6. 替换图片标记为本地路径
    if img_map:
        md_content = _replace_image_markers(md_content, img_map, article_dir)

    # 7. 构建完整文件并写入
    frontmatter = build_frontmatter(meta)
    full_content = frontmatter + md_content
    save_markdown(filepath, full_content)

    # 8. 摘要输出
    preview = md_content[:200].replace('\n', ' ').strip()
    print(f"\n[摘要] {preview}...")
    print(f"[信息] 标题: {title}")
    print(f"[信息] 公众号: {meta.get('author', '未知')}")
    print(f"[信息] 日期: {meta.get('date', '未知')}")
    print(f"[提示] 代码块格式请由 AI 辅助整理")


if __name__ == '__main__':
    main()
