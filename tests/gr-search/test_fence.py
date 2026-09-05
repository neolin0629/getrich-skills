#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""不可信内容围栏。整个 skill 的安全模型只建立在这一条上：
围栏内的一切是数据不是指令。围栏破了，其余所有正确性都无关紧要。

两类防线要分开测，它们挡的是不同的攻击：
- defang()：阻止上游文本**伪造** sentinel，制造出第二个结束标记；
- 围栏范围：阻止上游派生文本**出现在**围栏之外——那里的普通注入句子
  （"忽略之前的指示"）defang 一个字都不会改。

历史：这两条各自被突破过一次（RuyiInfo.Type / 图片宽高绕过 defang；
卡片提示、来源清单、错误详情、fetch fatal 落在围栏外），所以按字段逐个钉死。
"""

from __future__ import annotations

import pytest

import render
from conftest import (FULLWIDTH_FENCE, HUGE, INJECT, INJECT_SENTENCE,
                      fence_counts, outside_fence)


def assert_contained(text: str) -> None:
    """输出必须恰好一对围栏，且注入句子不得落在围栏之外。"""
    opens, closes = fence_counts(text)
    assert opens == 1, f"开始标记出现 {opens} 次"
    assert closes == 1, f"结束标记出现 {closes} 次"
    assert INJECT_SENTENCE not in outside_fence(text), "注入文本出现在围栏之外"


# ---------------------------------------------------------------- 字段级


@pytest.mark.parametrize("kwargs", [
    pytest.param({"body": INJECT}, id="body"),
    pytest.param({"title": INJECT}, id="title"),
    pytest.param({"site": INJECT}, id="site"),
    pytest.param({"url": f"https://e.com/{INJECT}"}, id="url"),
    pytest.param({"publish": INJECT}, id="publish"),
    pytest.param({"ruyi": INJECT}, id="ruyi"),           # RuyiInfo.Type，上游原样透传
    pytest.param({"also_urls": [f"https://e.com/{INJECT}"]}, id="also_urls"),
])
def test_result_fields_cannot_forge_fence(rendered, doc, kwargs):
    assert_contained(rendered(items=[doc(**kwargs)]))


@pytest.mark.parametrize("image", [
    pytest.param({"url": "https://i/1.png", "width": INJECT, "height": 2}, id="width"),
    pytest.param({"url": "https://i/1.png", "width": 1, "height": INJECT}, id="height"),
    pytest.param({"url": "https://i/1.png", "alt": INJECT}, id="alt"),
    pytest.param({"url": f"https://i/{INJECT}.png"}, id="url"),
    pytest.param({"url": "https://i/1.png", "shape": INJECT}, id="shape"),
])
def test_image_fields_cannot_forge_fence(rendered, doc, image):
    assert_contained(rendered(items=[doc(images=[image])], image_mode=True))


def test_card_type_cannot_forge_fence(rendered):
    assert_contained(rendered(cards=[{"CardType": INJECT}]))


def test_error_message_cannot_forge_fence(rendered, doc):
    """错误串里嵌着上游 HTTP 响应片段，是不可信内容。"""
    assert_contained(rendered(items=[doc()], errors=[f"doubao 失败: {INJECT}"]))


# ---------------------------------------------------------------- 围栏范围


def test_cards_only_still_fenced(rendered):
    """只有卡片、没有网页结果时也必须有围栏——卡片类型同样来自上游。"""
    assert_contained(rendered(cards=[{"CardType": INJECT}], items=[]))


def test_errors_only_still_fenced(rendered):
    """两个源都失败时，输出里只剩错误详情，它照样需要围栏。"""
    assert_contained(rendered(items=[], cards=[], errors=[f"parallel 失败: {INJECT}"]))


def test_sources_line_inside_fence(rendered, doc):
    """来源清单里是站点名和 URL，全部来自上游。"""
    out = rendered(items=[doc(0, site=INJECT), doc(1)])
    assert_contained(out)
    assert "来源:" in out
    assert "来源:" not in outside_fence(out)


def test_card_notice_inside_fence(rendered, doc):
    out = rendered(items=[doc()], cards=[{"CardType": "WeatherCard"}])
    assert "命中火山如意结构化直答" in out
    assert "命中火山如意结构化直答" not in outside_fence(out)


def test_nothing_upstream_means_no_fence(rendered):
    """没有任何上游内容时不该凭空生成一对空围栏。"""
    out = rendered(items=[], cards=[], errors=[])
    assert fence_counts(out) == (0, 0)
    assert "本次没有拿到任何结果" in out


def test_head_and_dump_path_stay_outside(rendered, doc):
    """围栏外只允许我们自己生成的内容：抬头行和落盘路径。"""
    out = rendered(items=[doc()], dump_path="/tmp/dump.json")
    head = out.split(render.BOUNDARY_OPEN)[0]
    assert head.startswith("gr-search:")
    assert "/tmp/dump.json" in head


# ---------------------------------------------------------------- defang 本身


@pytest.mark.parametrize("raw,gone", [
    ("<<<", "<<<"),
    (">>>", ">>>"),
    (FULLWIDTH_FENCE, FULLWIDTH_FENCE),   # 全角同形字：视觉混淆，一并中和
])
def test_defang_neutralizes(raw, gone):
    assert gone not in render.defang(f"前 {raw} 后")


def test_defang_is_idempotent():
    """中和后的文本再过一次不得继续变化，否则多层调用会累积破坏正文。"""
    once = render.defang(f"a{INJECT}b")
    assert render.defang(once) == once


def test_field_caps_length_after_defang():
    """先中和再截断，顺序不能反：先截断可能把 sentinel 切成两半躲过替换。"""
    out = render.field("<" + "<<" + HUGE, 50)
    assert len(out) <= 51           # 50 + 省略号
    assert "<<<" not in out


def test_field_accepts_non_string():
    """上游 JSON 里的数值字段可能是 int / None，不能在 str 操作上崩。"""
    assert render.field(1920, 12) == "1920"
    assert render.field(None, 12) == ""
