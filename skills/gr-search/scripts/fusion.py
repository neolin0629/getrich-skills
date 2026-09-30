#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨源去重与融合排序。

两级去重：
1. URL 归一化后完全相同 → 直接合并
2. 同标题且完整正文严格相同 → 合并，并保留全部 URL

不同 URL 的近似正文分别保留，避免否定词、条件和代码差异被相似度淹没。

排序用 RRF（Reciprocal Rank Fusion）：两个源的分数不可比
（Custom 有 0~1 的 RankScore，Global 和 Parallel 只有名次），
只有名次是共同语言；相关度和权威等级仅展示，不直接跨源加分。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sources import Doc

# 只删除明确的跟踪参数；t、lang、source 等通用名称可能决定页面内容。
_TRACKING_PREFIXES = ("utm_",)
_TRACKING_EXACT = {
    "spm", "gclid", "yclid", "msclkid", "vd_source",
    "share_source", "share_medium", "share_token", "shareid",
}
_HOST_PREFIXES = ("www.", "m.", "mobile.", "wap.", "amp.")
# 日级时效词：问"今天最高气温"时，去年的同题报道是干扰项而不是补充
_FRESH_STRONG = ("今天", "今日", "现在", "实时", "刚刚", "当前")
# 强时效词必须是弱时效词的子集，否则会出现 is_strong_fresh_query 为真、
# is_fresh_query 却为假的自相矛盾（「当前油价」一度就是这样）。
_FRESH_WORDS = _FRESH_STRONG + ("最新", "近期", "本周", "本月")

# 英文词必须按边界匹配，不能用子串：`now` 会命中 snowflake / knowledge / known，
# 把「Snowflake database docs」误判成时效查询——既走 120 秒短缓存，又给旧文档降权。
# 但不能用 `\b`：Python 的 \w 把中文也算词字符，「价格now走势」里 now 两侧
# 都不成边界，反而漏判。改成只把 ASCII 字母数字下划线视为"词内"，中文相邻即成边界。
# 下划线保留在排除集里是有意的：now_playing / current_events 是标识符，不是时效诉求。
_EN_BOUND = (r"(?<![A-Za-z0-9_])(?:%s)(?![A-Za-z0-9_])")
_FRESH_WORDS_EN = re.compile(_EN_BOUND % "latest|today|current|recent|now|breaking", re.IGNORECASE)
_FRESH_STRONG_EN = re.compile(_EN_BOUND % "today|now|breaking", re.IGNORECASE)

# 中文没有词间空格，但裸子串同样会误命中——这是英文侧 now/snowflake 的中文版本，
# 一度只修了英文：「日本月刊」「成本月度分摊」命中本月，「出现在哪个版本」命中现在，
# 「应当前往」命中当前。误判的代价是掉进 120 秒短缓存（重复调用重复付费）
# 并按年份重排，对一个纯资料查询完全是负作用。
#
# 不引分词器：几十兆的依赖换这点收益不划算，而且误判的代价只是缓存档位和排序，
# 不是正确性。改用"左邻字黑名单"——列出会与时效词首字组成**别的词**的那些字。
# 这挡不住所有情况（"这本月刊"仍会漏），但把实际会碰到的那批全部挡掉了。
_CN_LEFT_BLOCKERS = {
    # X本：日本 / 成本 / 资本 / 版本 / 基本 / 根本 / 剧本 / 课本 / 文本 / 样本…
    # 以及"这本 / 那本 / 一本"这类量词短语
    "本周": "日成资版基根剧课文样副脚原标范台蓝读抄摹这那该某几一两三四五六七八九十半整",
    "本月": "日成资版基根剧课文样副脚原标范台蓝读抄摹这那该某几一两三四五六七八九十半整",
    "现在": "出表体展浮涌显呈实兑",   # 出现在 / 表现在 / 体现在 / 实现在…
    "当前": "应理相适恰正妥停担充",   # 应当前 / 相当前 / 正当前…
    "实时": "真确属事着落务写",       # 真实时 / 确实时 / 事实时…
    "今日": "如当至",                 # 如今日 / 当今日
    "今天": "如当至",
    "近期": "附邻靠接临远最贴",       # 附近期 / 邻近期…
    "最新": "",
    "刚刚": "",
}


def _cn_fresh_hit(text: str, words) -> bool:
    """中文时效词命中判定：命中位置的左邻字不能是"会组成别的词"的那些字。"""
    for word in words:
        blockers = _CN_LEFT_BLOCKERS.get(word, "")
        start = 0
        while True:
            at = text.find(word, start)
            if at < 0:
                break
            if at == 0 or text[at - 1] not in blockers:
                return True
            start = at + 1
    return False


def canonical_url(url: str) -> str:
    """URL 归一化：同一篇文章的不同入口应当折叠成同一个键。"""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return url.strip()

    host = (parts.hostname or "").lower()
    for prefix in _HOST_PREFIXES:
        if host.startswith(prefix) and len(host) > len(prefix) + 3:
            host = host[len(prefix):]
            break
    if ":" in host:  # IPv6 的括号也是 authority 的一部分。
        host = f"[{host}]"
    if port is not None and port != {"http": 80, "https": 443}.get(parts.scheme.lower()):
        host = f"{host}:{port}"

    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
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

    # 普通章节锚点可折叠，hash/hashbang 路由与状态参数指向独立资源。
    # 浏览器文本指令只决定高亮位置；不能凭 portal/login 等名字断言路由与首页等价。
    fragment = parts.fragment.split(":~:", 1)[0]
    if not (fragment.startswith(("/", "!")) or "=" in fragment):
        fragment = ""
    return urlunsplit(("", host, path, urlencode(sorted(kept)), fragment))


def _equivalent_key(item: Merged) -> tuple[str, str] | None:
    """仅合并同标题的完整相同正文；否定、标点、大小写和代码空白均有意义。"""
    title, body = (item.title or "").strip(), item.body or ""
    if len(title) < 8 or len(body) < 120:
        return None
    return title, body


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
    body_source: str = ""

    def absorb(self, doc: Doc) -> None:
        """选择正文更完整的一份作为代表，引用字段随代表一起切换。"""
        self.sources[doc.source] = min(self.sources.get(doc.source, doc.rank), doc.rank)
        urls = [self.url, *self.also_urls, doc.url]
        if len(doc.body or "") > len(self.body or ""):
            representative = _from_doc(doc)
            for name in ("url", "title", "body", "site", "publish", "authority", "rank_score", "ruyi", "body_source"):
                setattr(self, name, getattr(representative, name))
        self.also_urls = list(dict.fromkeys(u for u in urls if u and u != self.url))
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
        body_source=doc.source,
    )


def merge(docs: list[Doc], threshold: float = 0.75) -> list[Merged]:
    """先按 URL 选择完整代表，再跨 URL 合并严格相同正文。

    threshold 保留调用兼容性，不再允许相似度阈值丢弃非等价正文。
    """
    url_groups: list[Merged] = []
    by_url: dict[str, Merged] = {}

    for doc in docs:
        if not (doc.url or doc.title):
            continue
        key = canonical_url(doc.url)
        if key and key in by_url:
            by_url[key].absorb(doc)
            continue
        entry = _from_doc(doc)
        url_groups.append(entry)
        if key:
            by_url[key] = entry

    # 必须在 URL 代表不再变化后判断等价，避免后来更长的同 URL 摘要
    # 覆盖先前跨 URL 合并进来的不同正文。哈希索引同时避免两两正文比较。
    merged: list[Merged] = []
    by_content: dict[tuple[str, str], Merged] = {}
    for entry in url_groups:
        content_key = _equivalent_key(entry)
        hit = by_content.get(content_key) if content_key is not None else None
        if hit is None:
            merged.append(entry)
            if content_key is not None:
                by_content[content_key] = entry
            continue
        for source, rank in entry.sources.items():
            hit.sources[source] = min(hit.sources.get(source, rank), rank)
        hit.also_urls = list(dict.fromkeys(
            url for url in [*hit.also_urls, entry.url, *entry.also_urls] if url and url != hit.url))
        for image in entry.images:
            if image not in hit.images:
                hit.images.append(image)
    return merged


# 显式的相对时间范围本身就是时效诉求，比任何关键词都明确。
# 分档与中文时效词保持一致：OneDay 对应「今天」（日级，陈旧内容要压低），
# OneWeek/OneMonth 对应「本周/本月」（周月级，只加权不降权），
# OneYear 跨度太大，按普通查询处理，不必缩短缓存。
_TIME_RANGE_STRONG = {"OneDay"}
_TIME_RANGE_FRESH = {"OneDay", "OneWeek", "OneMonth"}


_SPAN = re.compile(r"(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})")


# 窄到这个跨度以内、且覆盖今天的区间，才算日级强时效
_STRONG_SPAN_DAYS = 1


def _parse_span(time_range: str | None):
    """把显式日期区间解析成 (start, end)，不是区间就返回 None。"""
    import datetime

    match = _SPAN.fullmatch((time_range or "").strip())
    if not match:
        return None
    try:
        return (datetime.date.fromisoformat(match.group(1)),
                datetime.date.fromisoformat(match.group(2)))
    except ValueError:
        return None


def _span_reaches_now(time_range: str | None) -> bool:
    """区间右端是否到达今天或更晚——即这次查询关心的是当前状态。

    `2019-05-01..2019-05-01` 是历史查询，走 30 分钟缓存完全正确，
    把所有单日区间都判成实时纯属浪费额度。
    """
    import datetime

    span = _parse_span(time_range)
    return bool(span) and span[1] >= datetime.date.today()


def _span_is_day_level(time_range: str | None) -> bool:
    """是否是**覆盖今天的窄日级区间**。

    强时效不能和弱时效共用"右端≥今天"这一个条件：`2000-01-01..今天` 跨了 26 年，
    它确实关心当前状态（弱时效成立），但把区间里那些几十年前的资料**强制降权**
    是错的——strong 的语义是"陈旧内容是干扰项"，跨年区间里旧资料恰恰是正当结果。
    """
    import datetime

    span = _parse_span(time_range)
    if not span:
        return False
    start, end = span
    today = datetime.date.today()
    return start <= today <= end and (end - start).days <= _STRONG_SPAN_DAYS


def time_range_is_fresh(time_range: str | None) -> bool:
    """--time-range 是否构成（周月级）时效诉求。"""
    return (time_range or "") in _TIME_RANGE_FRESH or _span_reaches_now(time_range)


def time_range_is_strong_fresh(time_range: str | None) -> bool:
    """--time-range 是否构成日级时效诉求。"""
    return (time_range or "") in _TIME_RANGE_STRONG or _span_is_day_level(time_range)


_LIVE_TOPIC_EN = re.compile(_EN_BOUND % "weather|stock price|exchange rate|live score", re.I)
_BACKGROUND_EN = re.compile(_EN_BOUND % (
    "history|historical|yesterday|last year|theory|algorithm|model|models|api|dataset|datasets|forecasting|research|paper|papers|documentation|tutorial"), re.I)
_PRICE_UNIT = re.compile(r"^\s*(?:元|块|美元|港元|点|%|(?:USD|RMB|CNY|HKD|pts)(?![A-Za-z]))", re.I)
_PRICE_PREFIX = re.compile(
    r"(?:跌破|突破|站上|收于|报|涨至|跌至|[$¥￥]|(?<![A-Za-z])(?:below|above|under|over|at))\s*$", re.I)


def _query_has_past_date(text: str) -> bool:
    """日期早于今天才是历史语境；没有年份的月日按今年解释。"""
    import datetime

    today = datetime.date.today()
    for match in _CONTENT_DATE.finditer(text):
        year, month, day, compact_month, compact_day = match.groups()
        try:
            if datetime.date(int(year), int(month or compact_month), int(day or compact_day)) < today:
                return True
        except ValueError:
            continue
    for match in re.finditer(r"(?<!\d)(\d{1,2})月(\d{1,2})日", text):
        # 完整日期已经处理，不能把未来年份的月日改成今年的历史日期。
        if re.search(r"\d{4}年$", text[:match.start()]):
            continue
        try:
            if datetime.date(today.year, *map(int, match.groups())) < today:
                return True
        except ValueError:
            continue
    # 裸数字的含义依赖主题，不依赖中文是否插入空格。明确的「年」优先，
    # 单位或价格动词排除数值；只有股价主题的裸数字默认按价格解释。
    stock_price = "股价" in text or bool(re.search(_EN_BOUND % "stock price", text, re.I))
    for match in re.finditer(r"(?<![A-Za-z0-9_])(?:19|20)\d{2}(?![A-Za-z0-9_])", text):
        if int(match.group()) >= today.year:
            continue
        prefix, suffix = text[:match.start()], text[match.end():]
        if re.match(r"\s*年", suffix):
            return True
        if _PRICE_UNIT.match(suffix) or _PRICE_PREFIX.search(prefix):
            continue
        if re.search(r"\b(?:in|during|for)\s+(?:the\s+year\s+)?$", prefix, re.I):
            return True
        if not stock_price:
            return True
    return False


def _implicit_fresh_query(text: str) -> bool:
    """只为行情式查询补隐式日级信号；历史日期、知识和开发问题不触发。"""
    topic = any(word in text for word in ("天气", "股价", "汇率", "比分")) or _LIVE_TOPIC_EN.search(text)
    background = (re.search(r"历史|往年|去年|昨天|昨日|原理|算法|模型|预测方法|接口|数据集|气候|研究|论文|文档|教程|是什么", text)
                  or _query_has_past_date(text)
                  or _BACKGROUND_EN.search(text))
    return bool(topic and not background)


def is_fresh_query(query: str, *, allow_implicit: bool = True) -> bool:
    """判断 query 是否带时效诉求，决定要不要按时间调权、以及能接受多旧的缓存。"""
    text = query or ""
    return (_cn_fresh_hit(text, _FRESH_WORDS) or bool(_FRESH_WORDS_EN.search(text))
            or (allow_implicit and _implicit_fresh_query(text)))


def is_strong_fresh_query(query: str, *, allow_implicit: bool = True) -> bool:
    """日级时效诉求，陈旧内容要被明确压低而不只是不加分。"""
    text = query or ""
    return (_cn_fresh_hit(text, _FRESH_STRONG) or bool(_FRESH_STRONG_EN.search(text))
            or (allow_implicit and _implicit_fresh_query(text)))


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

    if not isinstance(publish, str):
        return 0.0
    text = publish.strip()
    today = datetime.date.today()
    full = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if full:
        try:
            days = (today - datetime.date(*(int(g) for g in full.groups()))).days
        except ValueError:
            return 0.0
        if days < -1:
            return 0.0
        if strong:
            if days <= 2:
                return 0.03
            if days <= 14:
                return 0.01
            if days <= 90:
                return -0.10
            return -0.20
        # 30 天半衰期；最多 3%，约等于 k=60 时的两个名次。
        # 未知日期保持 0，不根据别的页面推测新鲜度；仅有年份也不奖励。
        return 0.03 * 2 ** (-max(days, 0) / 30)
    return 0.0


_CONTENT_DATE = re.compile(
    r"(?<!\d)(\d{4})(?:[-/年](\d{1,2})[-/月](\d{1,2})日?|(\d{2})(\d{2}))(?!\d)")
_PATH_DATE = re.compile(
    r"(?:^|/|_)(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?!\d)"
    r"|(?:^|/|_)(\d{4})(\d{2})(\d{2})(?=\.html?(?:$|/)|_)", re.I)
_EVENT_TITLE = re.compile(r"回顾|复盘|纪念|周年|历史|retrospect|recap|anniversary", re.I)


def _ranking_date(item: Merged) -> str | None:
    """行情快照标题和明确的日期路径可覆盖抓取日期，不改写 publish。

    普通新闻标题中的事件日期不等于发布日期。路径中的裸数字 ID 不当日期；
    紧凑日期文件名还需在发布时间前五年至后一年内，降低数字编号误识别。
    """
    import datetime

    try:
        path = urlsplit(item.url).path
    except ValueError:
        path = ""
    title = item.title if (not _EVENT_TITLE.search(item.title) and (
        any(word in item.title for word in ("天气", "股价", "汇率", "比分"))
        or _LIVE_TOPIC_EN.search(item.title))) else ""
    reference_year = datetime.date.today().year
    if item.publish:
        try:
            reference_year = datetime.date.fromisoformat(item.publish[:10]).year
        except ValueError:
            pass
    for text, pattern in ((title, _CONTENT_DATE), (path, _PATH_DATE)):
        dates = set()
        for match in pattern.finditer(text):
            if pattern is _CONTENT_DATE:
                year, month, day, compact_month, compact_day = match.groups()
                month, day = month or compact_month, day or compact_day
                compact = False
            else:
                year, month, day, compact_year, compact_month, compact_day = match.groups()
                compact = year is None
                year, month, day = year or compact_year, month or compact_month, day or compact_day
            try:
                value = datetime.date(int(year), int(month), int(day))
            except ValueError:
                continue
            if compact and not reference_year - 5 <= value.year <= reference_year + 1:
                continue
            dates.add(value)
        if len(dates) == 1:
            return dates.pop().isoformat()
    return item.publish


def rank(merged: list[Merged], cfg: dict, fresh: bool = False, strong_fresh: bool = False) -> list[Merged]:
    """RRF 融合排序，就地写入 score 并返回降序列表。"""
    conf = cfg["fusion"]
    k = float(conf.get("rrf_k", 60))
    weights = {
        "doubao": float(conf.get("weight_doubao", 1.0)),
        "parallel": float(conf.get("weight_parallel", 1.0)),
    }

    for item in merged:
        score = sum(
            weights.get(source, 0.5) / (k + position)
            for source, position in item.sources.items()
        )
        if fresh:
            score *= 1 + _recency_bonus(_ranking_date(item), strong=strong_fresh)
        item.score = score

    # 卡片是独立直答类型；普通网页用 RRF，稳定键不依赖源完成顺序。
    return sorted(merged, key=lambda d: (not bool(d.ruyi), -d.score, canonical_url(d.url), d.title))
