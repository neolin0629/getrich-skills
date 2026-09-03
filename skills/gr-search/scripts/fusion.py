#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨源去重与融合排序。

两级去重：
1. URL 归一化后完全相同 → 直接合并
2. 正文字符 3-gram 的 Jaccard 相似度 ≥ 阈值 → 合并

用字符 3-gram 而不是分词，是因为它对中英文都成立且不需要额外依赖；
候选规模只有几十篇，O(n²) 比较在纯 Python 下也只有毫秒级，不值得引入 SimHash。

排序用 RRF（Reciprocal Rank Fusion）：两个源的分数不可比
（Custom 有 0~1 的 RankScore，Global 和 Parallel 只有名次），
只有名次是共同语言，所以以名次为主、分数只作小幅加成。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sources import Doc

# 跟踪与会话参数，去掉后不影响页面内容
_TRACKING_PREFIXES = ("utm_", "ga_", "fb_", "gclid", "yclid", "msclkid")
_TRACKING_EXACT = {
    "spm", "from", "ref", "referer", "referrer", "source", "src", "scene", "chksm",
    "share", "share_source", "share_medium", "share_token", "shareid", "sharer",
    "lang", "redirect", "_t", "t", "timestamp", "sessionid", "session_id",
    "wfr", "for", "sid", "seid", "vd_source", "isappinstalled", "weibo_id",
}
_HOST_PREFIXES = ("www.", "m.", "mobile.", "wap.", "amp.")
_PUNCT = re.compile(r"[\s　-〿＀-￯!-/:-@\[-`{-~]+")
_FRESH_WORDS = ("最新", "今天", "今日", "近期", "刚刚", "实时", "现在", "本周", "本月",
                "latest", "today", "current", "recent", "now", "breaking")
# 日级时效词：问"今天最高气温"时，去年的同题报道是干扰项而不是补充
_FRESH_STRONG = ("今天", "今日", "现在", "实时", "刚刚", "当前", "today", "now", "breaking")


def canonical_url(url: str) -> str:
    """URL 归一化：同一篇文章的不同入口应当折叠成同一个键。"""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()

    host = (parts.hostname or "").lower()
    for prefix in _HOST_PREFIXES:
        if host.startswith(prefix) and len(host) > len(prefix) + 3:
            host = host[len(prefix):]
            break

    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_EXACT
        and not any(k.lower().startswith(p) for p in _TRACKING_PREFIXES)
    ]

    path = parts.path
    for suffix in ("/index.html", "/index.htm", "/index.php"):
        if path.endswith(suffix):
            path = path[: -len(suffix) + 1]
            break
    if len(path) > 1:
        path = path.rstrip("/")

    return urlunsplit(("", host, path, urlencode(sorted(kept)), ""))


# 标题短于这个长度就不做同标题合并——"北京天气预报"这类通用标题
# 在不同站点上确实是不同页面，长标题才是转载的可靠信号
_TITLE_MIN = 8


def _norm_title(title: str) -> str:
    """标题归一化，用于识别跨站转载。"""
    return _PUNCT.sub("", (title or "")).lower()


def _shingles(text: str, size: int = 3) -> set[str]:
    """字符 n-gram 集合，用于近重复判断。"""
    normalized = _PUNCT.sub("", (text or "")[:1500]).lower()
    if len(normalized) < size:
        return {normalized} if normalized else set()
    return {normalized[i: i + size] for i in range(len(normalized) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    intersection = len(left & right)
    return intersection / (len(left) + len(right) - intersection)


@dataclass
class Merged:
    """合并后的文档。sources 记录每个源给它的名次，是 RRF 的输入。"""

    url: str
    title: str
    body: str
    site: str
    publish: str | None = None
    authority: int | None = None
    rank_score: float | None = None
    images: list[dict] = field(default_factory=list)
    sources: dict[str, int] = field(default_factory=dict)
    also_urls: list[str] = field(default_factory=list)
    ruyi: str | None = None
    score: float = 0.0

    def absorb(self, doc: Doc) -> None:
        """并入另一个源的同一篇文档，逐字段取更优的那个。"""
        self.sources.setdefault(doc.source, doc.rank)
        if doc.url and doc.url != self.url and doc.url not in self.also_urls:
            self.also_urls.append(doc.url)
        if len(doc.body or "") > len(self.body or ""):
            self.body = doc.body
        if len(doc.title or "") > len(self.title or ""):
            self.title = doc.title
        if not self.site and doc.site:
            self.site = doc.site
        if not self.publish and doc.publish:
            self.publish = doc.publish
        if doc.authority is not None and (self.authority is None or doc.authority < self.authority):
            self.authority = doc.authority
        if doc.rank_score is not None and (self.rank_score is None or doc.rank_score > self.rank_score):
            self.rank_score = doc.rank_score
        if doc.extra.get("ruyi") and not self.ruyi:
            self.ruyi = doc.extra["ruyi"]
        for image in doc.images:
            if image not in self.images:
                self.images.append(image)


def _from_doc(doc: Doc) -> Merged:
    site = doc.site
    if not site and doc.url:
        try:
            host = (urlsplit(doc.url).hostname or "").lower()
            # 注意不能用 lstrip("www.")——那是按字符集剥离，会把 wikipedia.org 削成 ikipedia.org
            site = host[4:] if host.startswith("www.") else host
        except ValueError:
            site = ""
    return Merged(
        url=doc.url,
        title=doc.title,
        body=doc.body,
        site=site,
        publish=doc.publish,
        authority=doc.authority,
        rank_score=doc.rank_score,
        images=list(doc.images),
        sources={doc.source: doc.rank},
        ruyi=doc.extra.get("ruyi"),
    )


def merge(docs: list[Doc], threshold: float = 0.75) -> list[Merged]:
    """两级去重。输入按源顺序给出，豆包在前，同分时豆包的版本胜出。"""
    merged: list[Merged] = []
    by_url: dict[str, Merged] = {}
    by_title: dict[str, Merged] = {}
    shingle_cache: list[set[str]] = []

    for doc in docs:
        if not (doc.url or doc.title):
            continue
        key = canonical_url(doc.url)
        if key and key in by_url:
            by_url[key].absorb(doc)
            continue

        # 同标题优先于正文相似度：新闻转载在各家站点的页眉页脚不同，
        # 正文 Jaccard 常常够不到阈值，但标题是逐字一致的。
        tkey = _norm_title(doc.title)
        hit: Merged | None = by_title.get(tkey) if len(tkey) >= _TITLE_MIN else None

        if hit is None:
            signature = _shingles(doc.body)
            if signature:
                for existing, existing_sig in zip(merged, shingle_cache):
                    if _jaccard(signature, existing_sig) >= threshold:
                        hit = existing
                        break
        else:
            signature = _shingles(doc.body)

        if hit is not None:
            hit.absorb(doc)
            if key:
                by_url.setdefault(key, hit)
            if len(tkey) >= _TITLE_MIN:
                by_title.setdefault(tkey, hit)
            continue

        entry = _from_doc(doc)
        merged.append(entry)
        shingle_cache.append(signature)
        if key:
            by_url[key] = entry
        if len(tkey) >= _TITLE_MIN:
            by_title[tkey] = entry
    return merged


def is_fresh_query(query: str) -> bool:
    """判断 query 是否带时效诉求，决定要不要按时间调权。"""
    lowered = (query or "").lower()
    return any(word in lowered for word in _FRESH_WORDS)


def is_strong_fresh_query(query: str) -> bool:
    """日级时效诉求，陈旧内容要被明确压低而不只是不加分。"""
    lowered = (query or "").lower()
    return any(word in lowered for word in _FRESH_STRONG)


def _recency_bonus(publish: str | None, strong: bool = False) -> float:
    """按发布时间调权。

    只加分不减分是不够的：问"今天最高气温"时，去年同题报道会带着完全错误的
    温度值挤进结果。所以对日级时效查询，陈旧内容要给负分压到尾部。
    降权只改顺序、不丢结果，比用 TimeRange 在服务端硬过滤安全 ——
    很多天气、行情类页面内容天天更新却没有 PublishTime，硬过滤会误伤。
    """
    if not publish:
        return 0.0
    import datetime

    text = publish.strip()
    today = datetime.date.today()
    full = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if full and strong:
        try:
            days = (today - datetime.date(*(int(g) for g in full.groups()))).days
        except ValueError:
            days = None
        if days is not None:
            if days <= 2:
                return 0.20
            if days <= 14:
                return 0.08
            if days <= 90:
                return 0.0
            if days <= 400:
                return -0.10
            return -0.20

    match = re.match(r"(\d{4})", text)
    if not match:
        return 0.0
    age = today.year - int(match.group(1))
    if age <= 0:
        return 0.12
    if age == 1:
        return 0.04
    return -0.08 if strong else 0.0


def rank(merged: list[Merged], cfg: dict, fresh: bool = False, strong_fresh: bool = False) -> list[Merged]:
    """RRF 融合排序，就地写入 score 并返回降序列表。"""
    conf = cfg["fusion"]
    k = float(conf.get("rrf_k", 60))
    weights = {
        "doubao": float(conf.get("weight_doubao", 1.0)),
        "parallel": float(conf.get("weight_parallel", 0.7)),
    }

    for item in merged:
        score = sum(
            weights.get(source, 0.5) / (k + position)
            for source, position in item.sources.items()
        )
        if len(item.sources) >= 2:
            score += 0.15  # 跨源互证：两个独立检索系统都召回，是很强的质量信号
        if item.ruyi:
            score += 0.25  # 火山如意是官方结构化直答，值得置顶
        if item.rank_score is not None:
            score += 0.10 * float(item.rank_score)
        score += {1: 0.08, 2: 0.04}.get(item.authority or 0, 0.0)
        if fresh:
            score += _recency_bonus(item.publish, strong=strong_fresh)
        item.score = score

    return sorted(merged, key=lambda d: d.score, reverse=True)
