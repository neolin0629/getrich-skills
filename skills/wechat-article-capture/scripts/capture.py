#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信公众号文章抓取脚本
用法: python capture.py <url> [输出目录] [文件名]
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime
import urllib.parse


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_CONFIG = {
    "output_dir": "wechat-captures",
    "image_dir_name": "配图",
    "source": "微信",
    "default_tags": ["公众号"],
    "category": "待分类",
    "status": "inbox",
    "timeout": 15,
    "filename_max_length": 200,
    "headers": {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://mp.weixin.qq.com/",
    },
}

ENV_PREFIX = "WECHAT_CAPTURE_"


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


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """移除文件名中的非法字符"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = name.strip()
    return name[:max_length] if name else "untitled"


def parse_date(date_str: str) -> str:
    """解析各种日期格式，返回 YYYY-MM-DD"""
    patterns = [
        (
            r'(\d{4})年(\d{1,2})月(\d{1,2})日',
            lambda m: f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
        ),
        (
            r'(\d{4})-(\d{1,2})-(\d{1,2})',
            lambda m: f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
        ),
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


def parse_timestamp_date(html: str) -> str | None:
    """从微信脚本变量中解析发布时间戳。"""
    patterns = [
        r'var\s+create_time\s*=\s*["\']?(\d{10})["\']?',
        r'var\s+ct\s*=\s*["\']?(\d{10})["\']?',
        r'createTimestamp\s*=\s*["\']?(\d{10})["\']?',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return datetime.fromtimestamp(int(match.group(1))).strftime("%Y-%m-%d")
    return None


def clean_meta_text(value: str) -> str:
    """还原微信元数据中的 HTML 实体和 JS 转义。"""
    value = value.replace(r'\x26', '&')
    return html_lib.unescape(value).strip()


def _merge_config(base: dict, override: dict) -> dict:
    """合并配置，headers 单独做浅合并。"""
    merged = dict(base)
    headers = dict(base.get("headers", {}))
    for key, value in override.items():
        if value is None:
            continue
        if key == "headers" and isinstance(value, dict):
            headers.update({str(k): str(v) for k, v in value.items() if v is not None})
        else:
            merged[key] = value
    merged["headers"] = headers
    return merged


def _load_json_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"配置文件必须是 JSON object: {path}")
    return data


def _parse_list_env(value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []
    if value.startswith("["):
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError("default_tags 环境变量 JSON 值必须是数组")
        return [str(item) for item in parsed]
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_config() -> dict:
    env = os.environ
    config = {}
    simple_keys = {
        "output_dir": "OUTPUT_DIR",
        "image_dir_name": "IMAGE_DIR_NAME",
        "source": "SOURCE",
        "category": "CATEGORY",
        "status": "STATUS",
    }
    for key, suffix in simple_keys.items():
        value = env.get(f"{ENV_PREFIX}{suffix}")
        if value:
            config[key] = value

    if env.get(f"{ENV_PREFIX}TIMEOUT"):
        config["timeout"] = int(env[f"{ENV_PREFIX}TIMEOUT"])
    if env.get(f"{ENV_PREFIX}FILENAME_MAX_LENGTH"):
        config["filename_max_length"] = int(env[f"{ENV_PREFIX}FILENAME_MAX_LENGTH"])
    if env.get(f"{ENV_PREFIX}DEFAULT_TAGS"):
        config["default_tags"] = _parse_list_env(env[f"{ENV_PREFIX}DEFAULT_TAGS"])

    return config


def _cli_config(args: argparse.Namespace) -> dict:
    config = {}
    output_dir = args.output_dir_option or args.output_dir
    if output_dir:
        config["output_dir"] = output_dir
    if args.image_dir_name:
        config["image_dir_name"] = args.image_dir_name
    if args.timeout is not None:
        config["timeout"] = args.timeout
    return config


def _resolve_config_path(args: argparse.Namespace) -> Path:
    config_path = args.config or os.environ.get(f"{ENV_PREFIX}CONFIG")
    if config_path:
        return Path(config_path).expanduser()
    return SKILL_DIR / "config.json"


def load_config(args: argparse.Namespace) -> dict:
    config_path = _resolve_config_path(args)
    config = _merge_config(DEFAULT_CONFIG, _load_json_config(config_path))
    config = _merge_config(config, _env_config())
    config = _merge_config(config, _cli_config(args))

    config["timeout"] = int(config.get("timeout") or DEFAULT_CONFIG["timeout"])
    config["filename_max_length"] = int(
        config.get("filename_max_length") or DEFAULT_CONFIG["filename_max_length"]
    )
    if not isinstance(config.get("default_tags"), list):
        config["default_tags"] = DEFAULT_CONFIG["default_tags"]
    config["default_tags"] = [str(tag) for tag in config["default_tags"] if str(tag).strip()]
    config["output_dir"] = Path(str(config["output_dir"])).expanduser()
    config["image_dir_name"] = str(config.get("image_dir_name") or "配图")
    return config


def is_wechat_article_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and hostname == "mp.weixin.qq.com"


def check_dependencies() -> list[str]:
    missing = []
    for module_name, package_name in [
        ("requests", "requests"),
        ("bs4", "beautifulsoup4"),
        ("html2text", "html2text"),
    ]:
        try:
            __import__(module_name)
        except ModuleNotFoundError:
            missing.append(package_name)
    return missing


def build_session(headers: dict) -> requests.Session:
    import requests

    session = requests.Session()
    session.headers.update(headers)
    return session


def fetch_article(session, url: str, timeout: int) -> str:
    """抓取微信文章页面"""
    resp = session.get(url, timeout=timeout, allow_redirects=True)
    resp.raise_for_status()
    resp.encoding = 'utf-8'
    return resp.text


def extract_metadata(html: str) -> dict:
    """从HTML中提取元数据"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, 'html.parser')
    meta = {}

    # 标题
    og_title = soup.find('meta', attrs={'property': 'og:title'})
    if og_title:
        meta['title'] = clean_meta_text(og_title.get('content', ''))
    if not meta.get('title'):
        h1 = soup.find('h1', class_='rich_media_title')
        if h1:
            meta['title'] = h1.get_text(strip=True)

    # 描述/摘要
    og_desc = soup.find('meta', attrs={'property': 'og:description'})
    if og_desc:
        meta['description'] = clean_meta_text(og_desc.get('content', ''))

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
            author = author_tag.get('content', '') or author_tag.get_text(strip=True)
            if author:
                meta['author'] = clean_meta_text(author)
                author_found = True

    if not author_found:
        meta['author'] = '未知公众号'

    # 发布日期
    date_tag = soup.find('em', id='publish_time')
    if not date_tag:
        date_tag = soup.find('span', class_='rich_media_meta rich_media_meta_text')
    if date_tag:
        date_text = date_tag.get_text(strip=True)
        if date_text:
            meta['date'] = parse_date(date_text)
    if not meta.get('date'):
        timestamp_date = parse_timestamp_date(html)
        if timestamp_date:
            meta['date'] = timestamp_date
    if not meta.get('date'):
        meta['date'] = datetime.now().strftime("%Y-%m-%d")

    # 描述/摘要
    desc = soup.find('meta', attrs={'name': 'description'})
    if desc and not meta.get('description'):
        meta['description'] = clean_meta_text(desc.get('content', ''))

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


def _download_images(
    img_urls: list,
    article_dir: Path,
    image_dir_name: str,
    session: requests.Session,
    timeout: int,
) -> dict:
    """
    下载图片到 article_dir/image_dir_name/ 目录。
    img_urls: 已提取的图片 URL 列表。
    返回 {序号: 本地路径} 映射。
    """
    if not img_urls:
        print("[配图] 未发现可下载的图片URL")
        return {}

    img_dir = article_dir / image_dir_name
    img_dir.mkdir(parents=True, exist_ok=True)

    idx_to_local = {}
    valid_count = sum(1 for u in img_urls if u)
    print(f"[配图] 提取到 {valid_count} 张图片，开始下载...")

    for idx, src in enumerate(img_urls):
        if not src:
            continue

        fname = _get_safe_filename(src, idx)
        fpath = img_dir / fname
        ext = Path(fname).suffix

        if fpath.exists():
            idx_to_local[idx] = fpath
            continue

        try:
            resp = session.get(src, timeout=timeout, stream=True)
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
                fname = f"{Path(fname).stem}{actual_ext}"
                fpath = img_dir / fname

            with fpath.open('wb') as f:
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
            img_dir.rmdir()
        except Exception:
            pass
    return idx_to_local


def _replace_image_markers(md: str, img_map: dict, article_dir: Path) -> str:
    """将 markdown 中的 __IMG_N__ 标记替换为本地图片引用"""
    for idx_str, local_path in img_map.items():
        try:
            rel_path = Path(local_path).relative_to(article_dir).as_posix()
        except ValueError:
            rel_path = Path(local_path).as_posix()
        marker = f'__IMG_{idx_str}__'
        md = md.replace(marker, f'![]({rel_path})')
    # 清理未替换的标记
    md = re.sub(r'__IMG_\d+__', '', md)
    return md


def extract_content(soup: BeautifulSoup):
    """提取正文内容区域，返回 (markdown, img_urls)"""
    import html2text

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


def _yaml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def build_frontmatter(meta: dict, config: dict) -> str:
    """构建 YAML frontmatter"""
    title = meta.get('title', '未命名文章')
    author = meta.get('author', '未知公众号')
    date = meta.get('date', datetime.now().strftime('%Y-%m-%d'))
    description = meta.get('description', '')
    tags = meta.get('tags', [])

    default_tags = config.get("default_tags", [])
    all_tags = (tags + [t for t in default_tags if t not in (tags or [])]) if tags else default_tags
    tags_str = json.dumps(all_tags, ensure_ascii=False)

    fm = f'''---
title: {_yaml_string(title)}
source: {_yaml_string(config.get("source", "微信"))}
author:
  - {_yaml_string(author)}
created: {date}
tags: {tags_str}
category: {_yaml_string(config.get("category", "待分类"))}
status: {_yaml_string(config.get("status", "inbox"))}
description: {_yaml_string(description)}
---

'''
    return fm


def save_markdown(filepath: Path, content: str):
    """确保目录存在，写入文件"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with filepath.open('w', encoding='utf-8') as f:
        f.write(content)
    print(f"[OK] 已保存: {filepath}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="抓取微信公众号文章并保存为 Markdown。")
    parser.add_argument("url", help="微信公众号文章 URL")
    parser.add_argument("output_dir", nargs="?", help="兼容旧用法：输出目录")
    parser.add_argument("filename", nargs="?", help="兼容旧用法：自定义文件名")
    parser.add_argument("--output-dir", dest="output_dir_option", help="输出目录")
    parser.add_argument("--filename", dest="filename_option", help="自定义文件名")
    parser.add_argument("--config", help="配置文件路径，默认读取 skill 目录下的 config.json")
    parser.add_argument("--image-dir-name", help="图片子目录名，默认 配图")
    parser.add_argument("--timeout", type=int, help="请求超时时间，单位秒")
    return parser


def _resolve_output_path(output_dir: Path, filename: str) -> Path:
    filepath = output_dir / filename
    if filepath.exists():
        base = filepath.stem
        ext = filepath.suffix
        counter = 1
        while filepath.exists():
            filepath = output_dir / f"{base}_{counter}{ext}"
            counter += 1
    return filepath


def main():
    # 解决 Windows PowerShell 控制台 GBK 编码问题
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

    parser = build_parser()
    args = parser.parse_args()
    url = args.url.strip()

    if not is_wechat_article_url(url):
        print("[错误] 必须是微信公众号文章地址 (mp.weixin.qq.com)")
        sys.exit(1)

    try:
        config = load_config(args)
    except Exception as e:
        print(f"[错误] 读取配置失败: {e}")
        sys.exit(1)

    missing = check_dependencies()
    if missing:
        print(f"[错误] 缺少依赖: {', '.join(missing)}")
        print(f"[提示] 请先安装: python -m pip install {' '.join(missing)}")
        sys.exit(1)

    custom_filename = (args.filename_option or args.filename or "").strip() or None
    session = build_session(config["headers"])

    print(f"[抓取中] {url}")

    # 1. 抓取
    html = fetch_article(session, url, config["timeout"])

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
        filename = sanitize_filename(custom_filename, config["filename_max_length"])
        if not filename.endswith('.md'):
            filename += '.md'
    else:
        filename = sanitize_filename(title, config["filename_max_length"]) + '.md'

    filepath = _resolve_output_path(config["output_dir"], filename)
    article_dir = filepath.parent

    # 5. 下载图片到配置的图片子目录
    img_map = _download_images(
        img_urls,
        article_dir,
        config["image_dir_name"],
        session,
        config["timeout"],
    )

    # 6. 替换图片标记为本地路径
    if img_map:
        md_content = _replace_image_markers(md_content, img_map, article_dir)

    # 7. 构建完整文件并写入
    frontmatter = build_frontmatter(meta, config)
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
