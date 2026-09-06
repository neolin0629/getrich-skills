#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""去重、融合排序与时效判定。

时效判定不只影响排序权重，还决定**能接受多旧的缓存**（120 秒 vs 30 分钟），
所以误判两个方向都有代价：漏判发旧货，误判则白白多花钱重搜。
"""

from __future__ import annotations

import pytest

import fusion
from sources import Doc


# ---------------------------------------------------------------- 时效词


@pytest.mark.parametrize("query", [
    "Snowflake database docs",      # snowflake 含 now
    "Kubernetes knowledge base",    # knowledge 含 now
    "known issues list",            # known 含 now
    "nowhere to run",
    "now_playing API",              # 标识符不是时效诉求
    "current_events schema",
    "Recently updated",             # recently ≠ recent
])
def test_english_substrings_are_not_fresh(query):
    """回归：曾用子串匹配，把「Snowflake database docs」判成时效查询——
    既走 120 秒短缓存，又给旧文档降权。"""
    assert not fusion.is_fresh_query(query)


@pytest.mark.parametrize("query", [
    "what is happening now", "latest release notes", "today's weather",
    "BREAKING news", "current price of gold", "recent changes",
])
def test_english_whole_words_are_fresh(query):
    assert fusion.is_fresh_query(query)


@pytest.mark.parametrize("query", [
    "价格now走势",      # 中英混排：\b 在中文边界上不成立，会漏判
    "今天的breaking消息",
])
def test_english_words_adjacent_to_cjk_are_fresh(query):
    assert fusion.is_fresh_query(query)


@pytest.mark.parametrize("query", [
    "最新消息", "今天天气", "今日油价", "近期新闻", "刚刚发生",
    "实时行情", "现在几点", "当前油价", "本周要闻", "本月数据",
])
def test_chinese_words_are_fresh(query):
    assert fusion.is_fresh_query(query)


@pytest.mark.parametrize("query", ["Python 装饰器原理", "什么是 RRF 融合排序", "SQL 窗口函数"])
def test_ordinary_queries_are_not_fresh(query):
    assert not fusion.is_fresh_query(query)


@pytest.mark.parametrize("query", ["今天天气", "当前油价", "实时行情", "刚刚发生",
                                   "breaking news", "what now"])
def test_strong_fresh_implies_fresh(query):
    """强时效必须蕴含弱时效。破了这条会出现 strong=True / fresh=False 的自相矛盾，
    进而 fresh 分支不生效、strong 的降权也就永远不会被调用。"""
    assert fusion.is_strong_fresh_query(query)
    assert fusion.is_fresh_query(query)


@pytest.mark.parametrize("query", ["最新消息", "本周要闻", "latest release"])
def test_weak_fresh_is_not_necessarily_strong(query):
    """「最新」是周级诉求，不该触发日级的陈旧内容降权。"""
    assert fusion.is_fresh_query(query)
    assert not fusion.is_strong_fresh_query(query)


# ---------------------------------------------------------------- URL 归一化


@pytest.mark.parametrize("a,b", [
    ("https://www.example.com/a", "https://example.com/a"),
    ("https://example.com/a?utm_source=x", "https://example.com/a"),
    ("https://example.com/a?spm=1&b=2", "https://example.com/a?b=2"),
    ("https://example.com/a?gclid=1", "https://example.com/a"),
    ("https://example.com/a?yclid=1", "https://example.com/a"),
    ("https://example.com/a?msclkid=1", "https://example.com/a"),
    ("https://example.com/a/", "https://example.com/a"),
    ("https://example.com/a/index.html", "https://example.com/a/"),
    ("https://m.example.com/a", "https://example.com/a"),
    ("https://example.com/a?b=1&c=2", "https://example.com/a?c=2&b=1"),
])
def test_urls_canonicalize_together(a, b):
    assert fusion.canonical_url(a) == fusion.canonical_url(b)


@pytest.mark.parametrize("a,b", [
    ("https://example.com/a", "https://example.com/b"),
    ("https://example.com/a?id=1", "https://example.com/a?id=2"),
    ("https://example.com/viewtopic.php?t=123", "https://example.com/viewtopic.php?t=456"),
    ("https://example.com/a?lang=en", "https://example.com/a?lang=zh"),
    ("https://example.com/a?print", "https://example.com/a"),
])
def test_distinct_urls_stay_distinct(a, b):
    assert fusion.canonical_url(a) != fusion.canonical_url(b)


def test_www_stripping_is_not_character_based():
    """回归：lstrip("www.") 是按字符集剥离，会把 wikipedia.org 削成 ikipedia.org。"""
    assert "wikipedia.org" in fusion.canonical_url("https://wikipedia.org/wiki/X")


def test_malformed_url_does_not_crash():
    assert fusion.canonical_url("http://[::1") is not None
    assert fusion.canonical_url("") == ""


# ---------------------------------------------------------------- 去重


def mkdoc(url, title="标题", body="正文", source="doubao", rank=1):
    return Doc(url=url, title=title, body=body, site="", source=source, rank=rank)


def test_same_url_across_sources_merges():
    merged = fusion.merge([
        mkdoc("https://www.example.com/a", source="doubao", rank=1),
        mkdoc("https://example.com/a", source="parallel", rank=3),
    ])
    assert len(merged) == 1
    assert merged[0].sources == {"doubao": 1, "parallel": 3}


def test_merge_records_alternate_url():
    merged = fusion.merge([
        mkdoc("https://example.com/a?utm_source=x", source="doubao"),
        mkdoc("https://example.com/a", source="parallel"),
    ])
    assert merged[0].also_urls


def test_reposts_with_similar_content_still_merge():
    """取消标题直通后，同一篇文章的转载仍按正文合并，并保留另一条来源链接。"""
    title = "国务院发布关于进一步优化营商环境的若干意见"
    body = "持续优化营商环境，完善市场准入制度，保护各类经营主体的合法权益。" * 20
    merged = fusion.merge([
        mkdoc("https://a.com/1", title=title, body=body),
        mkdoc("https://b.com/2", title=title, body=body + "编辑：乙站", source="parallel"),
    ])
    assert len(merged) == 1
    assert merged[0].sources == {"doubao": 1, "parallel": 1}
    assert merged[0].also_urls == ["https://b.com/2"]


@pytest.mark.parametrize("bodies", [
    ("Acme builds wind turbines; annual revenue was USD 42 million.",
     "Beacon operates supermarkets; annual revenue was EUR 930 million, driven by grocery sales."),
    ("", ""),
    ("", "Beacon operates supermarkets; annual revenue was EUR 930 million."),
])
def test_same_title_does_not_mix_independent_reports(bodies):
    """跨公司同名年报或缺失正文时必须保留两个来源，不能把链接与营收正文拼错。"""
    docs = [
        mkdoc("https://acme.example/report", title="2025 Annual Report", body=bodies[0]),
        mkdoc("https://beacon.example/report", title="2025 Annual Report",
              body=bodies[1], source="parallel"),
    ]
    merged = fusion.merge(docs)
    assert [(d.url, d.body, d.sources) for d in merged] == [
        (d.url, d.body, {d.source: d.rank}) for d in docs
    ]


@pytest.mark.parametrize("param", [
    "t", "lang", "from", "source", "src", "ref", "redirect", "timestamp", "sid", "weibo_id",
    "ga_page", "fb_page", "gclid_page",
])
def test_content_query_parameters_do_not_merge_distinct_pages(param):
    """通用参数和形似跟踪参数的名称可能标识内容，不能删除后用同 URL 规则强行合并。"""
    docs = [
        mkdoc(f"https://example.com/page?{param}=123", title="风电设备", body="风力发电设备研发"),
        mkdoc(f"https://example.com/page?{param}=456", title="商店经营",
              body="超级市场销售日常生活用品", source="parallel"),
    ]
    merged = fusion.merge(docs)
    assert [(d.url, d.body, d.sources) for d in merged] == [
        (d.url, d.body, {d.source: d.rank}) for d in docs
    ]


def test_short_generic_titles_do_not_merge():
    """「北京天气预报」这类通用短标题在不同站点上确实是不同页面。"""
    merged = fusion.merge([
        mkdoc("https://a.com/1", title="北京天气", body="甲" * 50),
        mkdoc("https://b.com/2", title="北京天气", body="乙" * 50),
    ])
    assert len(merged) == 2


def test_near_duplicate_body_merges():
    body = "这是一段足够长的正文，用来触发 3-gram 相似度判定。" * 10
    merged = fusion.merge([
        mkdoc("https://a.com/1", title="甲标题", body=body),
        mkdoc("https://b.com/2", title="乙标题", body=body + "尾部略有不同"),
    ])
    assert len(merged) == 1


def test_docs_without_url_or_title_are_dropped():
    assert fusion.merge([mkdoc("", title="", body="x")]) == []


def test_absorb_keeps_longer_body():
    merged = fusion.merge([
        mkdoc("https://example.com/a", body="短"),
        mkdoc("https://example.com/a", body="长得多的正文" * 20, source="parallel"),
    ])
    assert len(merged[0].body) > 10


# ---------------------------------------------------------------- 排序


def _cfg():
    return {"fusion": {"weight_doubao": 1.0, "weight_parallel": 0.7,
                       "rrf_k": 60, "dedup_jaccard": 0.75}}


def test_cross_source_hit_outranks_single_source():
    """两个独立检索系统都召回，是很强的质量信号。"""
    both = fusion.Merged(url="https://a.com", title="a", body="", site="a",
                         sources={"doubao": 5, "parallel": 5})
    one = fusion.Merged(url="https://b.com", title="b", body="", site="b",
                        sources={"doubao": 4})
    assert fusion.rank([one, both], _cfg())[0] is both


def test_ruyi_card_ranks_first():
    ruyi = fusion.Merged(url="https://a.com", title="a", body="", site="a",
                         sources={"doubao": 9}, ruyi="WeatherCard")
    plain = fusion.Merged(url="https://b.com", title="b", body="", site="b",
                          sources={"doubao": 1})
    assert fusion.rank([plain, ruyi], _cfg())[0] is ruyi


def test_strong_fresh_demotes_stale_content():
    """问"今天最高气温"时，去年的同题报道带着完全错误的温度值——
    只加分不减分不够，必须把陈旧内容压到尾部。"""
    old = fusion.Merged(url="https://a.com", title="a", body="", site="a",
                        sources={"doubao": 1}, publish="2019-05-01")
    new = fusion.Merged(url="https://b.com", title="b", body="", site="b",
                        sources={"doubao": 2}, publish="2026-09-04")
    assert fusion.rank([old, new], _cfg(), fresh=True, strong_fresh=True)[0] is new


def test_undated_content_is_not_demoted():
    """天气、行情类页面天天更新却常常没有 PublishTime，降权会误伤。"""
    assert fusion._recency_bonus(None, strong=True) == 0.0


@pytest.mark.parametrize("publish", ["2026-13-45", "昨天", "", "2026", "not-a-date", "0000-00-00"])
def test_malformed_publish_date_does_not_crash(publish):
    """发布时间是上游原样透传的字符串，格式五花八门，绝不能让它抛出去。"""
    bonus = fusion._recency_bonus(publish, strong=True)
    assert isinstance(bonus, float) and -1.0 <= bonus <= 1.0


def test_bad_month_day_falls_back_to_year_granularity():
    """月日不合法时退回年级判定，而不是整个丢弃——年份本身仍然是有效信息。
    「昨天」这种连年份都没有的才真正返回 0。"""
    assert fusion._recency_bonus("2026-13-45", strong=True) == fusion._recency_bonus("2026", strong=True)
    assert fusion._recency_bonus("昨天", strong=True) == 0.0


# ---------------------------------------------------------------- 显式日期区间的时效判定


def test_today_span_is_strong_fresh():
    """回归：`OneDay` 走短 TTL，但当天的 `2026-09-05..2026-09-05` 被当成普通查询。"""
    import datetime

    today = datetime.date.today().isoformat()
    assert fusion.time_range_is_fresh(f"{today}..{today}")
    assert fusion.time_range_is_strong_fresh(f"{today}..{today}")


def test_span_ending_today_is_fresh():
    import datetime

    today = datetime.date.today()
    week_ago = (today - datetime.timedelta(days=7)).isoformat()
    assert fusion.time_range_is_fresh(f"{week_ago}..{today.isoformat()}")


@pytest.mark.parametrize("span", [
    "2019-05-01..2019-05-01",     # 历史单日：走 30 分钟缓存完全正确
    "2019-01-01..2020-01-01",
    "1999-12-31..2000-01-01",
])
def test_historical_spans_are_not_fresh(span):
    """不能把所有单日区间都判成实时——历史查询走长缓存才对，
    误判只会白白多花钱重搜。"""
    assert not fusion.time_range_is_fresh(span)
    assert not fusion.time_range_is_strong_fresh(span)


@pytest.mark.parametrize("bad", ["", "OneCentury", "2026-13-45..2026-13-46", "not-a-span", None])
def test_malformed_span_does_not_crash(bad):
    assert fusion.time_range_is_fresh(bad) in (True, False)
    assert fusion.time_range_is_strong_fresh(bad) in (True, False)


@pytest.mark.parametrize("days_back,expect_strong", [
    (0, True),    # 当天
    (1, True),    # 昨天到今天：仍是窄日级
    (7, False),   # 最近一周：关心当前，但不该强制降权旧内容
    (365, False),
    (9000, False),  # 跨 20 多年
])
def test_wide_spans_are_fresh_but_not_strong(days_back, expect_strong):
    """回归：fresh 和 strong 共用"右端≥今天"一个条件，
    于是 `2000-01-01..今天` 也被判成日级强时效——区间里那些几十年前的资料
    被强制降权，而它们恰恰是这种跨年查询的正当结果。

    弱时效可以覆盖"触及当前"的区间；强时效只认覆盖今天的窄日级区间。
    """
    import datetime

    today = datetime.date.today()
    span = f"{(today - datetime.timedelta(days=days_back)).isoformat()}..{today.isoformat()}"
    assert fusion.time_range_is_fresh(span), "触及当前的区间应当算弱时效"
    assert fusion.time_range_is_strong_fresh(span) is expect_strong


def test_future_span_is_fresh_but_not_strong():
    """未来区间（天气预报之类）关心的是当前发布的内容，但没有"旧内容是干扰项"的语义。"""
    import datetime

    today = datetime.date.today()
    span = (f"{(today + datetime.timedelta(days=7)).isoformat()}.."
            f"{(today + datetime.timedelta(days=30)).isoformat()}")
    assert fusion.time_range_is_fresh(span)
    assert not fusion.time_range_is_strong_fresh(span)


def test_strong_span_implies_fresh_span():
    """强蕴含弱这条不变量，对日期区间同样成立。"""
    import datetime

    today = datetime.date.today()
    for days in range(0, 40):
        span = f"{(today - datetime.timedelta(days=days)).isoformat()}..{today.isoformat()}"
        if fusion.time_range_is_strong_fresh(span):
            assert fusion.time_range_is_fresh(span), span


# ---------------------------------------------------------------- 中文词边界


@pytest.mark.parametrize("query", [
    "日本月刊 订阅方式",      # 日本 + 月刊，不是「本月」
    "日本周边游 攻略",        # 日本 + 周边
    "成本月度分摊",           # 成本 + 月度
    "基本月供计算",
    "这本月刊",
    "出现在哪个版本",         # 出现 + 在，不是「现在」
    "表现在哪些方面",
    "应当前往的路线",         # 应当 + 前往，不是「当前」
    "真实时间戳格式",         # 真实 + 时间，不是「实时」
    "附近期刊查询",           # 附近 + 期刊，不是「近期」
    "版本管理",
])
def test_chinese_substrings_are_not_fresh(query):
    """回归：中文时效词是裸子串匹配，`本月`/`本周`/`现在`/`当前`/`实时` 会在
    无关词里命中，掉进 120 秒短缓存（重复调用重复付费）并被按年份重排。

    这正是英文侧为 now/snowflake 修掉的同一类问题——当时只修了英文。
    """
    assert not fusion.is_fresh_query(query), f"{query} 被误判为时效查询"
    assert not fusion.is_strong_fresh_query(query)


@pytest.mark.parametrize("query", [
    "本月数据", "本周要闻", "查本月账单", "统计本周新增",
    "当前油价", "现在几点", "今天天气", "今日油价",
    "实时行情", "最新消息", "刚刚发生", "近期新闻",
])
def test_chinese_fresh_words_still_match(query):
    """收窄不能把正常的时效查询一起挡掉。"""
    assert fusion.is_fresh_query(query), f"{query} 漏判"


def test_blocked_word_elsewhere_in_query_still_counts():
    """同一个词在别处正常出现时仍要命中——只挡被组词的那个位置。"""
    assert fusion.is_fresh_query("日本月刊 和 本月新刊")
