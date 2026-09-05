#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输出预算。这里守两个方向的失败，历史上两边都塌过：

- **超支**：上游字段无上限 → 一条结果击穿整个预算（标题 10000 字符 → 输出两万）；
- **欠支**：预算被元信息吃光 → 结果全变成光秃秃的标题+链接，一条摘要都没有。

第二种更隐蔽：输出看着正常、长度也没超，但最有价值的正文没了。
"""

from __future__ import annotations

import pytest

import render
from conftest import HUGE


# ---------------------------------------------------------------- 不得超支


@pytest.mark.parametrize("count,budget", [
    (1, 250), (1, 8000), (5, 8000), (10, 500),
    (17, 15000), (50, 8000), (3, 30000), (100, 15000),
])
def test_output_fits_budget(rendered, doc, count, budget):
    out = rendered(items=[doc(i) for i in range(count)], budget=budget)
    assert len(out) <= budget, f"超支 {len(out) - budget} 字符"
    assert out.strip(), "预算内却输出为空"


@pytest.mark.parametrize("field", ["title", "site"])
def test_single_huge_field_cannot_blow_budget(rendered, doc, field):
    """首条结果无条件输出，挡不住超长字段——只能靠字段自身限长。"""
    out = rendered(items=[doc(**{field: HUGE})], budget=8000)
    assert len(out) <= 8000


def test_huge_url_cannot_blow_budget(rendered, doc):
    out = rendered(items=[doc(url=f"https://e.com/{HUGE}")], budget=8000)
    assert len(out) <= 8000


def test_huge_image_url_cannot_blow_budget(rendered, doc):
    out = rendered(items=[doc(images=[{"url": f"https://i/{HUGE}.png"}])],
                   budget=8000, image_mode=True)
    assert len(out) <= 8000


def test_floor_is_bounded_and_input_independent(rendered, doc):
    """预算极小时允许有固定硬下限（围栏本身不参与截断），
    但这个下限必须**有界**，且不随上游字段规模增长。"""
    from fusion import Merged

    sizes = {
        "正常": rendered(items=[doc()], budget=250, dump_path=None),
        "超长标题": rendered(items=[Merged(url="https://e.com/a", title=HUGE, body="b", site="e")],
                         budget=250, dump_path=None),
        "超长URL": rendered(items=[Merged(url=f"https://e.com/{HUGE}", title="t", body="b", site="e")],
                         budget=250, dump_path=None),
        "全超长": rendered(items=[Merged(url=f"https://e.com/{HUGE}", title=HUGE, body=HUGE,
                                      site=HUGE, ruyi=HUGE, publish=HUGE)],
                        budget=250, dump_path=None),
    }
    lengths = {k: len(v) for k, v in sizes.items()}
    # 上限收得比"看起来够宽松"更紧：原来写 2000，于是 1164 字符的超额一路绿灯
    # 通过——一个过松的边界和没有边界是一回事。
    assert max(lengths.values()) < 700, lengths


# ---------------------------------------------------------------- 不得欠支


@pytest.mark.parametrize("count,budget", [(1, 8000), (5, 8000), (17, 15000), (50, 8000)])
def test_results_always_carry_some_body(doc, count, budget):
    _, detailed = render.render_results([doc(i) for i in range(count)], budget)
    assert detailed > 0, "所有结果都没有摘要"


def heavy(index):
    """真实世界的元信息长度：新闻标题几十字、URL 常带长 slug。

    这个长度是本用例的关键——元信息短的话，开销怎么算都撑不满预算，
    也就复现不出"正文预算被扣成 0"的原始故障。
    """
    from fusion import Merged

    return Merged(
        url=f"https://news.example.com/{index}/2026/09/04/"
            f"{'article-slug-segment-' * 3}{index}",
        title=f"第 {index} 条：关于进一步优化某某领域营商环境的若干措施正式发布并自即日起施行",
        body="这是一段没有换行的长摘要正文。" * 40,
        site=f"news{index}.example.com",
        publish="2026-09-04",
    )


@pytest.mark.parametrize("count,budget", [(30, 8000), (50, 8000), (50, 15000), (100, 15000)])
def test_heavy_metadata_does_not_starve_bodies(count, budget):
    """回归：50 条 / budget 8000 曾展示 31 条标题、detailed=0。

    症结是先扣掉**全部**候选项的元信息开销、再分正文预算——
    不展示的候选凭什么占预算。带摘要的少数条目远比无摘要的多数有用。
    """
    body, detailed = render.render_results([heavy(i) for i in range(count)], budget)
    assert detailed > 0, "所有结果都没有摘要"
    assert len(body) <= budget


def test_bodies_are_preferred_over_more_headlines():
    """元信息不得吃掉超过一半预算：宁可少展示几条，也不要一屏光秃秃的标题。"""
    items = [heavy(i) for i in range(50)]
    body, detailed = render.render_results(items, 8000)
    headlines = sum(1 for line in body.splitlines() if line.startswith("["))
    assert detailed >= headlines // 8, f"{headlines} 条标题只有 {detailed} 条带摘要"


@pytest.mark.parametrize("budget", [250, 500, 1000, 2000])
def test_single_line_body_is_truncated_not_dropped(budget):
    """回归：正文装不下的那一行必须**再截短**，不能整行丢弃。

    Parallel 的 excerpt 和豆包的 Summary 多半是不带换行的一整段，
    整行丢弃 = 这条结果的正文彻底消失，只剩标题和 URL。
    """
    from fusion import Merged

    item = Merged(url="https://e.com/a", title="T", body="没有换行的一整段摘要。" * 300, site="e.com")
    body, detailed = render.render_results([item], budget)
    assert detailed == 1
    assert len(body) <= budget


def test_omitted_results_are_announced(doc):
    """装不下的结果必须明确注明省略了几条，绝不静默丢弃。"""
    body, _ = render.render_results([doc(i) for i in range(50)], 3000)
    assert "另有" in body and "未展开" in body


def test_omitted_count_is_accurate(doc):
    items = [doc(i) for i in range(30)]
    body, _ = render.render_results(items, 2000)
    shown = sum(1 for line in body.splitlines() if line.startswith("["))
    assert f"另有 {len(items) - shown} 条" in body


# ---------------------------------------------------------------- 卡片段


@pytest.mark.parametrize("count", [10, 100, 1000])
def test_card_notice_respects_budget(rendered, count):
    """回归：render_cards 曾声明了 budget 参数却从不使用，
    1000 个未知 CardType 能产出四万多字符。"""
    cards = [{"CardType": f"Unknown{i}"} for i in range(count)]
    text = render.render_cards(cards, budget=100)
    assert len(text) < 250, f"{count} 个卡片产出 {len(text)} 字符"


def test_card_notice_size_does_not_track_input():
    """长度不得随输入规模线性增长。

    类型名用等宽的合成值，把变量收敛到唯一合法的那个——省略计数的位数。
    卡片数翻 1000 倍，输出只应长出几位数字。
    """
    def notice(count):
        return render.render_cards([{"CardType": f"Unknown{i:06d}"} for i in range(count)], 100)

    assert len(notice(100_000)) - len(notice(100)) <= 3


def test_card_notice_reports_omission():
    cards = [{"CardType": f"Unknown{i}"} for i in range(50)]
    assert "类从略" in render.render_cards(cards, budget=100)


def test_known_card_types_use_chinese_labels():
    assert "天气" in render.render_cards([{"CardType": "WeatherCard"}])


def test_duplicate_card_types_collapse():
    text = render.render_cards([{"CardType": "WeatherCard"}] * 5)
    assert text.count("天气") == 1


# ---------------------------------------------------------------- 分配器


def test_allocate_returns_empty_on_zero_budget():
    """返回空列表是合法的，但调用方必须补齐——
    历史上 zip() 因此把所有结果一起吃掉，输出直接变空。"""
    assert render._allocate(5, 0) == []


def test_allocate_recycles_capped_surplus():
    """头部撞上 _MAX_BODY 的富余额度要回流给尾部，否则浪费近 1/3 预算。"""
    shares = render._allocate(17, 60000)
    assert all(s <= render._MAX_BODY for s in shares)
    assert min(shares) >= render._MIN_BODY


def test_allocate_is_decreasing():
    shares = render._allocate(10, 10000)
    assert shares == sorted(shares, reverse=True)


# ---------------------------------------------------------------- 错误详情


def test_huge_error_cannot_blow_budget(rendered, doc):
    """回归：注入 10000 字符错误后，budget=8000 实测输出 10144。

    豆包的 ResponseMetadata.Error.Message 当前没有长度上限，这是真实可达路径。
    """
    out = rendered(items=[doc()], budget=8000, errors=["doubao 失败: " + HUGE])
    assert len(out) <= 8000


def test_many_errors_cannot_blow_budget(rendered, doc):
    out = rendered(items=[doc()], budget=8000,
                   errors=[f"源{i} 失败: " + "详情" * 200 for i in range(20)])
    assert len(out) <= 8000


def test_first_error_survives_tiny_budget(rendered, doc):
    """预算再紧也要让用户知道"有源失败了"，不能让输出看起来一切正常。"""
    out = rendered(items=[doc()], budget=300, errors=["doubao 失败: 余额不足"])
    assert "⚠" in out


def test_dropped_errors_are_counted(rendered, doc):
    out = rendered(items=[doc()], budget=2000,
                   errors=[f"源{i} 失败: " + "详情" * 100 for i in range(10)])
    assert "条错误详情从略" in out


# 围栏 + 抬头 + 首条无条件渲染构成一个固定硬下限（实测约 251 字符）。
# 围栏永远不参与截断——缺半道围栏比超预算严重得多——所以低于这个值的 budget
# 本来就不可能满足。它是常量，不随结果数或字段长度增长。
_HARD_FLOOR = 300


def _grid(count, body_len, budget):
    from fusion import Merged

    items = [Merged(url=f"https://site{i}.example.com/a/b/{i}", title=f"标题{i}" * 4,
                    body="正文。" * body_len, site=f"site{i}.example.com")
             for i in range(count)]
    return render.render(query="q", items=items, cards=[], budget=budget, profile="p",
                         stats=[f"doubao {count}"], errors=[], elapsed=0.1, dump_path=None)


@pytest.mark.parametrize("count", [1, 2, 3, 5, 8, 15, 30])
def test_budget_holds_across_the_grid(count):
    """来源块过去只扣内容长度，漏算 "来源: " 前缀和前导空行，稳定超支几个字符。

    扫一整片网格而不是挑几个点——上一版手挑了 n=6 / budget 400~1200，
    恰好全部避开了真正会超的组合（n=1 / budget 425、450…）。
    预算的边界靠猜是猜不中的，只能扫。
    """
    overruns = [(budget, body_len, len(out))
                for budget in range(_HARD_FLOOR, 2100, 25)
                for body_len in (50, 200, 800, 3000)
                if len(out := _grid(count, body_len, budget)) > budget]
    assert not overruns, f"{len(overruns)} 组超支，样例 {overruns[:5]}"


@pytest.mark.parametrize("count", [1, 5, 30])
def test_below_floor_output_is_bounded(count):
    """低于硬下限时允许超预算，但超出量必须**有界且不随输入增长**——
    这正是"围栏造成的固定下限可以接受、上游字段造成的无上限超额不可以"的分界。"""
    worst = max(len(_grid(count, body_len, budget))
                for budget in range(1, _HARD_FLOOR, 25)
                for body_len in (50, 800, 3000))
    assert worst < 600, f"下限区输出 {worst} 字符，已随输入膨胀"


# 每多一类"首条无条件保留"的段，硬下限就抬高一截：围栏 53 + 卡片提示前后缀 53
# + 首条错误最短 24 + 省略提示预留 40 + 抬头 + 首条结果。三段齐全时实测下限 416
# ——这个数字是**扫出来的**，不是估的（扫法见下方两个用例）。
# 关键性质不是这个数字本身，而是它**只随段的种类增长、不随输入规模增长**
# ——由 test_combined_floor_does_not_track_input 单独守。
_COMBINED_FLOOR = 425


def test_errors_results_and_cards_combined(rendered, doc):
    """回归：错误、结果、卡片三处各自"首条无条件保留"，叠在一起把小预算撑破：
    budget=400 结果+长错误 → 458；budget=500 再加卡片 → 536。

    要保住的是"某个源失败了"这个事实，不是 300 字符的详情——详情在落盘 JSON 里。
    """
    overruns = []
    for budget in range(_COMBINED_FLOOR, 2100, 25):
        for cards in ([], [{"CardType": "WeatherCard"}], [{"CardType": f"U{i}"} for i in range(5)]):
            for n_err in (1, 2, 5):
                out = rendered(items=[doc(i) for i in range(3)], cards=cards, budget=budget,
                               errors=["doubao 失败: " + HUGE] * n_err, dump_path=None)
                if len(out) > budget:
                    overruns.append((budget, len(cards), n_err, len(out)))
    assert not overruns, f"{len(overruns)} 组超支，样例 {overruns[:5]}"


def test_failure_fact_survives_even_when_detail_cannot(rendered, doc):
    """详情可以被压到最短，但"有源失败了"这件事不能丢——
    丢了它，输出看起来一切正常，而结果其实少了一半。"""
    for budget in range(_HARD_FLOOR, 900, 50):
        out = rendered(items=[doc()], budget=budget, errors=["doubao 失败: " + HUGE],
                       dump_path=None)
        assert "⚠" in out and "doubao" in out, f"budget={budget} 丢失了失败提示"


def test_error_detail_grows_with_budget(rendered, doc):
    """预算宽裕时详情要给足，不能一律压到最短。"""
    short = rendered(items=[doc()], budget=350, errors=["doubao 失败: " + "详" * 500], dump_path=None)
    long = rendered(items=[doc()], budget=8000, errors=["doubao 失败: " + "详" * 500], dump_path=None)
    assert long.count("详") > short.count("详")


def test_combined_floor_does_not_track_input(rendered, doc):
    """三段齐全时的硬下限必须有界，且不随结果数、错误数、卡片数或字段长度增长。

    这是"围栏造成的固定下限可以接受、上游内容造成的无上限超额不可以"的分界线：
    段的**种类**抬高下限是设计使然，段的**规模**抬高下限就是缺陷。
    """
    def worst(n_items, n_err, n_cards, blow):
        payload = HUGE if blow else "详情"
        return max(
            len(rendered(items=[doc(i) for i in range(n_items)],
                         cards=[{"CardType": f"U{i}"} for i in range(n_cards)],
                         errors=[f"源{i} 失败: " + payload for i in range(n_err)],
                         budget=budget, dump_path=None))
            for budget in range(1, _COMBINED_FLOOR, 20))

    small = worst(1, 1, 1, blow=False)
    huge = worst(100, 50, 200, blow=True)
    assert huge < 600, f"下限区最长 {huge}"
    assert huge - small < 200, f"下限随输入从 {small} 涨到 {huge}"


# ---------------------------------------------------------------- 图片模式

_IMAGE_FLOOR = 320  # 围栏 + 抬头 + 首行图片（各字段都已压到地板）


def _image_item(count=1):
    from fusion import Merged

    return Merged(url="https://e.com/a", title=HUGE, body="b", site="e",
                  images=[{"url": "https://i.example.com/" + HUGE, "width": HUGE,
                           "height": HUGE, "alt": HUGE, "shape": HUGE,
                           "blur": HUGE, "watermark": HUGE} for _ in range(count)])


@pytest.mark.parametrize("n_images", [1, 5, 50])
@pytest.mark.parametrize("cards,errors", [
    ([], []),
    ([{"CardType": "WeatherCard"}], []),
    ([{"CardType": f"U{i}"} for i in range(20)], ["doubao 失败: " + HUGE] * 5),
])
def test_image_mode_fits_budget(rendered, n_images, cards, errors):
    """回归：图片首行无条件输出，而 URL/描述/note 用的是固定字段上限、
    不随 remaining 收缩——极端字段下 budget=300 输出 560、到 789 仍可能超支。

    根因是**每个字段各自取上限**：每个都"没超自己的上限"，加起来照样撑破预算。
    整行必须共用一份额度。
    """
    overruns = [(budget, len(out))
                for budget in range(_IMAGE_FLOOR, 2000, 25)
                if len(out := rendered(items=[_image_item(n_images)], cards=cards,
                                       errors=errors, budget=budget, image_mode=True,
                                       dump_path=None)) > budget]
    assert not overruns, f"{len(overruns)} 组超支，样例 {overruns[:5]}"


def test_image_floor_is_bounded(rendered):
    worst = max(len(rendered(items=[_image_item(50)],
                             cards=[{"CardType": f"U{i}"} for i in range(20)],
                             errors=["doubao 失败: " + HUGE] * 5,
                             budget=budget, image_mode=True, dump_path=None))
                for budget in range(1, _IMAGE_FLOOR, 10))
    assert worst < 600, f"图片模式下限区输出 {worst} 字符"


def test_image_row_still_readable_under_pressure(rendered):
    """压缩不能把图片行压成认不出来的东西——URL 至少要留出可辨认的长度。"""
    out = rendered(items=[_image_item()], budget=600, image_mode=True, dump_path=None)
    assert "https://i.example.com/" in out


# ---------------------------------------------------------------- 抬头行


def test_huge_query_cannot_blow_budget(rendered, doc):
    """query 来自用户而非公网，但它同样不该让输出突破总预算：
    10000 字符查询 / budget=8000 曾输出 10088，总预算就不是硬上限了。"""
    out = render.render(query="Q" * 10000, items=[doc()], cards=[], budget=8000,
                        profile="p", stats=["doubao 1"], errors=[], elapsed=0.1,
                        dump_path=None)
    assert len(out) <= 8000


# ---------------------------------------------------------------- 卡片省略计数


def test_card_omission_counts_types_not_occurrences():
    """回归：一个被省略的类型重复 100 次会显示"100 类从略"，实际只有一类。"""
    cards = [{"CardType": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}] * 100 + \
            [{"CardType": "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"}] * 100 + \
            [{"CardType": "WeatherCard"}]
    text = render.render_cards(cards, budget=100)
    assert "等 100 类从略" not in text
    assert "等 2 类从略" in text or "等 1 类从略" in text


@pytest.mark.perf
def test_card_notice_is_fast_on_many_cards():
    """去重要用 set：卡片数可以很大，扫 list 会退化成 O(n²) 真的卡住。"""
    import time

    start = time.monotonic()
    render.render_cards([{"CardType": f"U{i}"} for i in range(200_000)], budget=100)
    assert time.monotonic() - start < 2.0


# ---------------------------------------------------------------- 极端元信息

_EXTREME_FLOOR = 400  # 扫出来的：极端字段下超支只出现在 budget ≤ 388


def _extreme(count=1):
    from fusion import Merged

    return [Merged(url="https://e.com/" + HUGE, title=HUGE, body=HUGE, site=HUGE,
                   publish=HUGE, ruyi=HUGE, also_urls=["https://a/" + HUGE] * 3,
                   images=[{"url": "https://i/" + HUGE, "width": HUGE, "height": HUGE,
                            "alt": HUGE, "shape": HUGE}])
            for _ in range(count)]


@pytest.mark.parametrize("count", [1, 5, 50])
@pytest.mark.parametrize("image_mode", [False, True])
def test_extreme_metadata_fits_budget(rendered, count, image_mode):
    """回归：元信息各字段各自取固定上限（标题 200 + 站点 80 + URL 300 + 如意 40），
    每个都"没超自己的上限"，加起来让无条件输出的首条撑到 1164 字符。

    这和图片行是同一个坑：**一行要共用一份额度**，不能各取各的。
    """
    overruns = [(budget, len(out))
                for budget in range(_EXTREME_FLOOR, 1600, 25)
                for cards in ([], [{"CardType": "WeatherCard"}])
                for errors in ([], ["doubao 失败: " + HUGE])
                if len(out := rendered(items=_extreme(count), cards=cards, errors=errors,
                                       budget=budget, image_mode=image_mode,
                                       dump_path=None)) > budget]
    assert not overruns, f"{len(overruns)} 组超支，样例 {overruns[:5]}"


@pytest.mark.parametrize("image_mode", [False, True])
def test_extreme_floor_is_bounded(rendered, image_mode):
    """下限区允许超支，但必须有界且不随字段长度或结果数增长。"""
    worst = max(len(rendered(items=_extreme(n), cards=[{"CardType": f"U{i}"} for i in range(20)],
                             errors=["doubao 失败: " + HUGE] * 5, budget=budget,
                             image_mode=image_mode, dump_path=None))
                for n in (1, 50) for budget in range(1, _EXTREME_FLOOR, 20))
    assert worst < 700, f"极端字段下限区输出 {worst} 字符"


def test_meta_line_shares_one_allowance():
    """直接盯住根因：整行额度小的时候，各字段必须一起缩。"""
    from fusion import Merged

    item = Merged(url="u", title=HUGE, body="b", site=HUGE, publish=HUGE, ruyi=HUGE)
    assert len(render._meta_line(1, item, budget=120)) <= 160
    assert len(render._meta_line(1, item, budget=400)) > len(render._meta_line(1, item, budget=120))


def test_card_dedup_uses_raw_type_not_truncated_label():
    """两个只在第 41 个字符之后才不同的 CardType，截断后的显示标签相同，
    按标签去重会把它们错误地合并成一类。"""
    a = "U" + "A" * 60
    b = "U" + "A" * 60 + "DIFFERENT"
    text = render.render_cards([{"CardType": a}, {"CardType": b}], budget=CARD_ROOM)
    assert "等 1 类从略" in text or text.count("…") == 2


CARD_ROOM = 200


# ---------------------------------------------------------------- 分段自身的预算
#
# 出口有一道兜底截断，能让总长永远合规——代价是它会**掩盖各分段自身的缺陷**。
# 实测过：把图片行的字段上限改回固定值、把来源行的前缀开销去掉，端到端断言
# 全部照样通过。所以每个分段都要有直接针对它自己的用例，
# 并用 `_assemble` 断言正常预算下压根不需要兜底。


def _assemble_overflow(items, budget, cards=(), errors=(), image_mode=False):
    _parts, overflow, _slot = render._assemble(
        query="q", items=list(items), cards=list(cards), budget=budget, profile="p",
        stats=["doubao 1"], errors=list(errors), elapsed=0.1, dump_path=None,
        image_mode=image_mode)
    return overflow


# 各分段自己都有保底（卡片提示 53、错误详情 24、元信息/URL 各 48…）。
# 这些保底加起来超过总预算时，靠分段自己是收不住的，只能由出口兜底——
# 实测这种情况只出现在 budget ≤ 1100（极端字段 + 卡片 + 多条错误 + 长 query + 长路径）。
# 这条线以上，分段自身就必须算得清清楚楚，一个字符都不该指望兜底。
_SEGMENT_CLEAN_FLOOR = 1150


@pytest.mark.parametrize("image_mode", [False, True])
@pytest.mark.parametrize("count", [1, 5, 50])
def test_no_segment_overspends_before_the_safety_net(doc, count, image_mode):
    """预算充足时各分段加起来就该合规，兜底截断不该被用到。

    两种模式都必须用极端字段：非图片分支一度用的是普通 `doc()`，字段太短撑不满预算，
    于是"元信息不随预算收缩"这个缺陷在这条用例下照样绿——变异测试才把它抓出来。
    """
    items = _extreme(count)
    bad = [(budget, over) for budget in range(_SEGMENT_CLEAN_FLOOR, 2400, 25)
           for cards in ([], [{"CardType": "WeatherCard"}])
           if (over := _assemble_overflow(items, budget, cards, ["doubao 失败: " + HUGE],
                                          image_mode)) > 0]
    assert not bad, f"{len(bad)} 组依赖兜底截断才不超支，样例 {bad[:5]}"


def test_safety_net_only_absorbs_the_sum_of_floors():
    """兜底截断只该在"各分段保底之和 > 预算"时出手。

    需要它兜的量必须（a）有界，（b）**不随输入规模增长**——那才说明它兜的是
    保底之和这个常量，而不是某个分段的核算错误。极小预算下这个量接近所有保底
    之和（围栏 53 + 抬头 48 + 卡片 53 + 错误 24 + 元信息 48 + URL 48 …）。
    """
    def worst(n):
        return max(_assemble_overflow(_extreme(n), budget, [{"CardType": "WeatherCard"}],
                                      ["doubao 失败: " + HUGE], image_mode)
                   for image_mode in (False, True)
                   for budget in range(1, _SEGMENT_CLEAN_FLOOR, 25))

    small, large = worst(1), worst(50)
    assert large < 500, f"兜底要处理的超额达 {large}"
    assert large - small < 60, f"超额随结果数从 {small} 涨到 {large}，那不是保底之和"


def test_shedding_actually_reduces_the_floor_overflow():
    """盯住逐段削减本身是否在起作用。

    注意不能用 `_assemble` 的 overflow 来测：那是**削减之前**的值，
    削减做没做它都一样——我第一版就测错了对象，变异体照样绿。
    要测的是 `render()` 最终输出的长度。

    实测：逐段削减时下限区最长超出 233；退化成只裁正文则为 300。
    上限贴着 233 留余量，写宽到 500 就又检测不出来了。
    """
    from fusion import Merged

    def out_len(budget, n, cards, errors):
        items = [Merged(url="https://e.com/" + HUGE, title=HUGE, body="", site=HUGE,
                        publish=HUGE, ruyi=HUGE, also_urls=["https://a/" + HUGE] * 3)
                 for _ in range(n)]
        return len(render.render(query="Q" * 5000, items=items, cards=cards, budget=budget,
                                 profile="p", stats=["doubao 1"], errors=errors,
                                 elapsed=0.1, dump_path="/tmp/" + "d" * 800 + ".json"))

    worst = max(out_len(budget, n, cards, errors) - budget
                for n in (1, 50)
                for cards in ([{"CardType": "WeatherCard"}],
                              [{"CardType": f"U{i}"} for i in range(20)])
                for errors in (["doubao 失败: " + HUGE],)
                for budget in range(1, 500, 7))
    assert worst < 280, f"下限区最长超出 {worst}，逐段削减可能退化成了只裁正文"


def test_render_images_respects_its_own_budget():
    """直接盯住 render_images：拿到多少额度就只能用多少，一个字符都不许多。

    这里**不留任何逃生门**。原先写成 `<= budget or len(table) < 200`，
    于是 24 和 43 字符的超额一路绿灯——图片行有两道防线（按比例分配上限、
    首行收尾截断），单独打掉任何一道都只造成几十字符的超额，
    在整体渲染那一层又被另一道和出口兜底吸收掉，端到端断言完全看不见。
    分段级的断言就得严到能看见这几十个字符。
    """
    overruns = [(budget, len(table))
                for budget in range(_IMAGE_TABLE_FLOOR, 1500, 7)
                if len(table := render.render_images(_extreme(20), budget)) > budget]
    assert not overruns, f"{len(overruns)} 组超额，样例 {overruns[:5]}"


# render_images 自身的下限：一行图片再怎么压也有最短形态（实测超额只出现在 budget ≤ 57）
_IMAGE_TABLE_FLOOR = 64


def test_render_images_floor_is_bounded():
    worst = max(len(render.render_images(_extreme(20), budget))
                for budget in range(1, _IMAGE_TABLE_FLOOR))
    assert worst < 120, f"render_images 下限区输出 {worst} 字符"


def test_render_sources_line_respects_its_own_budget(doc):
    """不留余量：原来写 `<= budget + 40`，那 40 的宽限正好盖住了
    "首条无条件保留 + 固定 MAX_SITE 上限"造成的 80 多字符超额。"""
    overruns = [(budget, len(line))
                for budget in range(1, 900)
                for items in ([doc(i) for i in range(50)], _extreme(50))
                if len(line := render.render_sources_line(items, budget)) > budget]
    assert not overruns, f"{len(overruns)} 组超额，样例 {overruns[:5]}"


@pytest.mark.parametrize("budget", [48, 120, 300, 800])
def test_meta_line_respects_its_own_budget(budget):
    from fusion import Merged

    item = Merged(url="u", title=HUGE, body="b", site=HUGE, publish=HUGE, ruyi=HUGE)
    assert len(render._meta_line(1, item, budget)) <= budget + 40


# ---------------------------------------------------------------- 抬头与落盘路径


_LONG_DUMPS = {
    "长目录": "/" + ("deep/" * 200) + "grs-q-1757000000-ab12cd34.json",
    "长文件名": "/tmp/" + "d" * 1000 + ".json",
    "正常": "/tmp/grs-q-1757000000-ab12cd34.json",
}


@pytest.mark.parametrize("label", list(_LONG_DUMPS))
def test_dump_path_cannot_blow_budget(doc, label):
    """回归：出口的兜底截断只压正文，压不到抬头和落盘路径。
    1000 字符的 dump_dir 配 budget=425 曾输出 1402 字符——
    "总预算是硬上限"这个承诺就此不成立。"""
    overruns = [(budget, len(out))
                for budget in range(_HARD_FLOOR, 2000, 25)
                if len(out := render.render(
                    query="q", items=[doc()], cards=[], budget=budget, profile="p",
                    stats=["doubao 1"], errors=[], elapsed=0.1,
                    dump_path=_LONG_DUMPS[label])) > budget]
    assert not overruns, f"{len(overruns)} 组超支，样例 {overruns[:5]}"


def test_normal_dump_path_is_shown_in_full(doc):
    """路径截断了就没法用。正常长度必须原样给出，否则 agent 追问时找不到文件。"""
    path = _LONG_DUMPS["正常"]
    out = render.render(query="q", items=[doc()], cards=[], budget=15000, profile="p",
                        stats=["doubao 1"], errors=[], elapsed=0.1, dump_path=path)
    assert path in out


@pytest.mark.parametrize("label", ["长目录", "长文件名"])
def test_oversized_dump_path_degrades_but_still_informs(doc, label):
    """放不下时也要让用户知道"落盘了、去哪找"，而不是给一个截断过的假路径。"""
    out = render.render(query="q", items=[doc()], cards=[], budget=500, profile="p",
                        stats=["doubao 1"], errors=[], elapsed=0.1,
                        dump_path=_LONG_DUMPS[label])
    assert "全量结果" in out and "dump_dir" in out
    assert _LONG_DUMPS[label] not in out


def test_query_echo_shrinks_with_budget(doc):
    """抬头行里的 query 回显也要随预算收缩。"""
    small = render.render(query="Q" * 10000, items=[doc()], cards=[], budget=300, profile="p",
                          stats=["doubao 1"], errors=[], elapsed=0.1, dump_path=None)
    large = render.render(query="Q" * 10000, items=[doc()], cards=[], budget=15000, profile="p",
                          stats=["doubao 1"], errors=[], elapsed=0.1, dump_path=None)
    assert small.count("Q") < large.count("Q")
    assert len(small) <= 300


# ---------------------------------------------------------------- 多个保底段组合


def test_all_guaranteed_segments_combined(doc):
    """回归：长 query、长 dump 路径、卡片、错误、复杂结果**单独测都合规**，
    组合后超出 185 字符——因为出口只裁正文，而正文本来就短甚至为空时无处消化。

    这是"分开测都过、组合就崩"的第二次出现（第一次在 fetch 的告警×紧预算）。
    保底段之间会互相叠加，必须显式扫组合网格。
    """
    from fusion import Merged

    def items(n, body_len):
        return [Merged(url="https://news.example.com/a/" + "seg/" * 20, title="标题" * 30,
                       body="正文。" * body_len, site="news.example.com", publish="2026-09-04",
                       ruyi="WeatherCard", also_urls=["https://a/" + "x" * 200] * 3)
                for _ in range(n)]

    overruns = []
    for n in (1, 3, 20):
        for body_len in (0, 1, 3, 10, 200):          # body_len=0 是关键：正文无处可裁
            for cards in ([], [{"CardType": "WeatherCard"}],
                          [{"CardType": f"U{i}"} for i in range(20)]):
                for errors in ([], ["doubao 失败: " + "E" * 5000], ["e" + "E" * 5000] * 5):
                    for dump in (None, "/tmp/" + "d" * 800 + ".json", "/" + ("deep/" * 200) + "g.json"):
                        for query in ("q", "Q" * 5000):
                            for budget in range(_COMBINED_FLOOR, 1400, 29):
                                out = render.render(
                                    query=query, items=items(n, body_len), cards=cards,
                                    budget=budget, profile="p", stats=["doubao 1"],
                                    errors=errors, elapsed=0.1, dump_path=dump)
                                if len(out) > budget:
                                    overruns.append((budget, len(out), n, body_len))
    assert not overruns, f"{len(overruns)} 组超支，样例 {overruns[:5]}"


def test_shedding_preserves_the_fence_and_failure_fact(doc):
    """削减有优先级：来源清单和卡片提示可以整段丢，
    但围栏、抬头和"某个源失败了"这个事实必须留住。"""
    from fusion import Merged

    out = render.render(
        query="Q" * 5000,
        items=[Merged(url="https://e.com/" + "x" * 300, title="标题" * 30, body="",
                      site="site.example.com", ruyi="WeatherCard")],
        cards=[{"CardType": "WeatherCard"}], budget=_COMBINED_FLOOR, profile="p",
        stats=["doubao 1"], errors=["doubao 失败: 余额不足"], elapsed=0.1,
        dump_path="/tmp/grs-q-1.json")
    assert render.BOUNDARY_OPEN in out and render.BOUNDARY_CLOSE in out
    assert out.startswith("gr-search:")
    assert "⚠" in out and "doubao" in out
    assert len(out) <= _COMBINED_FLOOR


@pytest.mark.parametrize("filler", ["a ", "错 ", "x ", "x"])
def test_shed_never_deletes_the_whole_error_line(filler):
    """回归：`cut` 已经保证留够地板，`rstrip()` 却会再压下去一截 ——
    27 字符的错误行、floor=_MIN_ERROR=24，切到 24 之后 rstrip 掉一个尾随空格
    就是 23，判定"不足地板"于是**整段置空**，输出里一个 ⚠ 都不剩。
    一个字符的尾随空格，把"少削 1 个字符"升级成"整条源失败通知消失"，
    而输出看着一切正常、结果其实少了一半 —— 正是 `_fit_errors` 要防的那件事。

    边界不手挑：尾随空白落在哪个位置取决于消息长度与预算的组合，扫网格。
    """
    lost = []
    for pad in range(0, 26):
        message = "doubao 失败: HTTP 500 " + filler * pad
        for budget in range(60, 260):
            out = render.render(query="q", items=[], cards=[], budget=budget, profile="p",
                                stats=[], errors=[message], elapsed=0.1, dump_path=None)
            if "⚠" not in out:
                lost.append((budget, len(message)))
    assert not lost, f"{len(lost)} 组把整条源失败通知删光了，样例 {lost[:5]}"


@pytest.mark.parametrize("tail", ["", " ", "   ", "　"])
def test_shed_never_deletes_the_whole_result_block(tail):
    """正文段同理（floor=_MIN_BODY_TAIL）：正文尾部带空白时，整个
    「元信息 + URL + 正文」块会被一起删光，围栏里只剩空白 —— 而它是
    floor>0 的段，合约是"留住地板长度"，不是"可以整段丢"。"""
    from fusion import Merged

    lost = []
    for body_len in (1, 8, 40, 200):
        item = Merged(url="https://e.example.com/a/1", title="标题标题标题",
                      body="正文内容" * body_len + tail, site="e.example.com",
                      publish="2026-09-01", sources={"doubao": 0})
        for budget in range(60, 400):
            out = render.render(query="q", items=[item], cards=[], budget=budget,
                                profile="p", stats=["doubao 1"], errors=[],
                                elapsed=0.1, dump_path=None)
            if render.BOUNDARY_OPEN in out and "[1]" not in out:
                lost.append((budget, body_len))
    assert not lost, f"{len(lost)} 组把整条结果块删光了，样例 {lost[:5]}"


# ---------------------------------------------------------------- 未落盘时不许谎称可恢复


@pytest.mark.parametrize("dump_path,should_promise", [
    ("/tmp/grs-q-1757000000-ab12cd34.json", True),
    (None, False),   # --no-dump，或落盘失败后 dump_path 被置回 None
])
def test_truncation_hint_matches_dump_reality(doc, dump_path, should_promise):
    """回归：卡片、结果、错误详情被预算裁掉时一律说"见落盘 JSON"，
    可 --no-dump 或落盘失败时那些内容事实上已经无法恢复。
    这种谎话比省略本身更糟——它让人以为还有得救。"""
    out = render.render(
        query="q", items=[doc(i) for i in range(30)],
        cards=[{"CardType": f"U{i}"} for i in range(30)], budget=900, profile="p",
        stats=["doubao 1"], errors=["doubao 失败: " + HUGE] * 3, elapsed=0.1,
        dump_path=dump_path)
    promised = "见落盘 JSON" in out or "在落盘 JSON 的 cards 字段" in out
    assert promised is should_promise
    if not should_promise:
        assert "未落盘" in out, "既然不能恢复，就要明说"


@pytest.mark.parametrize("dumped", [True, False])
def test_each_truncating_segment_reports_the_truth(dumped):
    """三处裁剪各自都要说实话，不能只改其中一处。"""
    from fusion import Merged

    cards = render.render_cards([{"CardType": f"U{i}"} for i in range(30)], 100, dumped)
    body, _ = render.render_results(
        [Merged(url=f"https://s{i}.com/{i}", title="标题" * 10, body="正文。" * 80,
                site=f"s{i}.com") for i in range(30)], 600, dumped)
    errors = render._fit_errors(["doubao 失败: " + HUGE] * 5, 200, dumped)

    for text in (cards, body, "\n".join(errors)):
        if "落盘" in text or "未落盘" in text:
            assert ("见落盘 JSON" in text or "在落盘 JSON" in text) is dumped, text[-60:]
