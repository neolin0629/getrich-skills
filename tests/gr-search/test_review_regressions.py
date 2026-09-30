"""第二期审核的行为回归；使用合成数据，不读取凭据或访问网络。"""

import copy
import datetime
import json

import pytest

import config
import fusion
import gr_search
import render
import sources


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    monkeypatch.delenv(config.DOUBAO_ENV, raising=False)
    monkeypatch.delenv(config.PARALLEL_ENV_DEFAULT, raising=False)
    value = copy.deepcopy(config.DEFAULTS)
    value['output']['dump_dir'] = str(tmp_path)
    value['cache']['enabled'] = False
    return value


@pytest.fixture
def today(monkeypatch):
    class FixedDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 30)
    monkeypatch.setattr(datetime, 'date', FixedDate)


@pytest.mark.parametrize('source', ['doubao', 'parallel'])
@pytest.mark.parametrize('separator', ['\n', '\r', '\x00', '密'])
def test_invalid_key_never_reaches_transport_or_output(cfg, monkeypatch, tmp_path, capsys, source, separator):
    """拒绝会让 header 抛出含密钥异常的字符，连传输函数也不能调用。"""
    secret = 'FAKE-REVIEW-PREFIX-123456789' + separator + 'FAKE-REVIEW-SUFFIX-987654321'
    cfg[source]['api_key'] = secret
    monkeypatch.setattr(sources, 'resolve_transport', lambda _: 'http')
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid key reached a network transport')
    monkeypatch.setattr(sources.urllib.request, 'urlopen', forbidden)
    args = gr_search.build_parser().parse_args(['search', 'test', '--source', source, '--no-cache', '--json'])
    assert gr_search.run_search(args, cfg) == 1
    output = capsys.readouterr()
    for text in (output.out + output.err, *[p.read_text() for p in tmp_path.glob('*.json')]):
        assert 'Invalid API key' in text
        assert 'FAKE-REVIEW-PREFIX' not in text
        assert 'FAKE-REVIEW-SUFFIX' not in text
    assert len(list(tmp_path.glob('*.json'))) == 1


@pytest.mark.parametrize('source', ['doubao', 'parallel'])
@pytest.mark.parametrize('as_bytes', [False, True])
def test_unexpected_source_exception_redacts_escaped_key(cfg, monkeypatch, tmp_path, capsys, source, as_bytes):
    """兜底异常不得绕过脱敏，包括 bytes repr 中已转义的换行。"""
    secret = 'FAKE-REVIEW-PREFIX-123456789\nFAKE-REVIEW-SUFFIX-987654321'
    cfg[source]['api_key'] = secret
    def fail(*args, **kwargs):
        raise RuntimeError(repr(secret.encode() if as_bytes else secret))
    monkeypatch.setattr(sources, source + '_search', fail)
    args = gr_search.build_parser().parse_args(['search', 'test', '--source', source, '--no-cache'])
    assert gr_search.run_search(args, cfg) == 1
    for text in (capsys.readouterr().out, *[p.read_text() for p in tmp_path.glob('*.json')]):
        assert 'RuntimeError' in text and '已脱敏' in text
        assert 'FAKE-REVIEW-PREFIX' not in text
        assert 'FAKE-REVIEW-SUFFIX' not in text


@pytest.mark.parametrize('route', ['doubao', 'search-http', 'search-cli', 'fetch-http', 'fetch-cli'])
def test_each_adapter_exception_exit_redacts_keys(cfg, monkeypatch, route):
    """直接检查适配器出口，不能依靠编排层的第二道防线掩盖遗漏。"""
    secret = "FAKE-REVIEW-'quoted-key'\\123456789"
    cfg['doubao']['api_key'] = cfg['parallel']['api_key'] = secret
    monkeypatch.setattr(sources, 'resolve_transport', lambda _: 'http' if route.endswith('http') else 'cli')
    monkeypatch.setattr(sources.time, 'sleep', lambda _: None)
    def fail(*args, **kwargs):
        raise OSError('Header rejected: ' + repr(secret.encode()))
    monkeypatch.setattr(sources, '_post_json', fail)
    monkeypatch.setattr(sources, '_post_parallel', fail)
    monkeypatch.setattr(sources.subprocess, 'run', fail)
    if route == 'doubao':
        error = sources.doubao_search(cfg, 'test', {'no_cache': True}).error
    elif route.startswith('search'):
        error = sources.parallel_search(cfg, 'test', [], {'no_cache': True}).error
    else:
        _, error, _ = sources.parallel_extract(cfg, ['https://example.com'], 'test', 1000)
    assert error and 'OSError' in error and '已脱敏' in error
    assert 'FAKE-REVIEW' not in error


def test_fetch_unexpected_exception_is_safe(cfg, monkeypatch, capsys):
    secret = 'FAKE-REVIEW-FETCH-123456789'
    cfg['parallel']['api_key'] = secret
    def fail(*args, **kwargs):
        raise RuntimeError(secret)
    monkeypatch.setattr(sources, 'parallel_extract', fail)
    args = gr_search.build_parser().parse_args(['fetch', 'https://example.com'])
    assert gr_search.run_fetch(args, cfg) == 1
    output = capsys.readouterr().err
    assert secret not in output and '已脱敏' in output
    assert output.count(render.BOUNDARY_OPEN) == output.count(render.BOUNDARY_CLOSE) == 1


def test_doctor_reports_invalid_key_without_crashing(cfg, monkeypatch, tmp_path, capsys):
    """请求前校验不能让用于诊断错误配置的 doctor 自身崩溃。"""
    cfg['parallel']['api_key'] = 'FAKE-REVIEW-DOCTOR-123456789\nCOPIED-EXTRA-TEXT'
    monkeypatch.setattr(config, 'CONFIG_PATH', tmp_path / 'missing-config.json')
    monkeypatch.setattr(gr_search.shutil, 'which', lambda _: '/synthetic/parallel-cli')
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid key reached a subprocess')
    monkeypatch.setattr(gr_search.subprocess, 'run', forbidden)
    args = gr_search.build_parser().parse_args(['config', 'doctor'])
    assert gr_search.run_config(args, cfg) == 0
    output = capsys.readouterr().out
    assert 'Invalid API key' in output
    assert 'FAKE-REVIEW-DOCTOR' not in output and 'COPIED-EXTRA-TEXT' not in output


@pytest.mark.parametrize('a,b', [
    ('https://docs.example/#/install', 'https://docs.example/#/auth'),
    ('https://docs.example/#!/install', 'https://docs.example/#!/auth'),
    ('https://docs.example/#page=install', 'https://docs.example/#page=auth'),
    ('https://example.com:8443/api', 'https://example.com:9443/api'),
    ('https://[::1]:8443/api', 'https://[::1]:9443/api'),
])
def test_distinct_resources_keep_both_bodies_and_source_scores(a, b):
    docs = [sources.Doc(a, 'Install', 'Run installation.', '', 'doubao', 1),
            sources.Doc(b, 'Auth', 'Create a token before authenticating.', '', 'parallel', 1)]
    merged = fusion.rank(fusion.merge(docs), config.DEFAULTS)
    assert len(merged) == 2
    assert {d.body for d in merged} == {d.body for d in docs}
    assert all(d.score == pytest.approx(1 / 61) for d in merged)


@pytest.mark.parametrize('a,b', [
    ('https://example.com:443/a', 'https://example.com/a'),
    ('http://example.com:80/a', 'http://example.com/a'),
    ('https://example.com/a#section', 'https://example.com/a'),
    ('https://[::1]:443/a', 'https://[::1]/a'),
])
def test_default_ports_and_document_anchors_still_fold(a, b):
    assert fusion.canonical_url(a) == fusion.canonical_url(b)


@pytest.mark.parametrize('query', [
    '北京天气如何', '上海天气怎么样', '北京天气为什么这么热', '茅台股价走势如何',
    'how is the weather in Tokyo', "what's the weather in London", 'why is the weather so hot in Tokyo',
    '国庆10月1日北京天气', '北京2026年10月1日天气', '北京20261001天气',
    'Beijing weather 2026-10-01', '北京2027年1月1日天气',
])
def test_live_questions_and_future_forecasts_are_fresh(today, query):
    assert fusion.is_fresh_query(query)
    assert fusion.is_strong_fresh_query(query)


@pytest.mark.parametrize('query', [
    '北京9月29日天气', '北京2026年9月29日天气', '北京20250930天气',
    '北京2025年天气', '天气预测模型如何实现', 'how weather forecasting models work',
    'why weather models fail', '汇率原理是什么', 'Beijing weather yesterday',
])
def test_history_and_background_remain_non_live(today, query):
    assert not fusion.is_fresh_query(query)
    assert not fusion.is_strong_fresh_query(query)


@pytest.mark.parametrize('path', ['/p/20160102', '/item/19991231', '/p/20260901', '/19991231.html'])
def test_numeric_ids_do_not_override_publication(today, path):
    item = fusion.Merged('https://example.com' + path, 'Article', '', '', publish='2026-09-30')
    assert fusion._ranking_date(item) == item.publish


@pytest.mark.parametrize('path', ['/2026/07/09/weather', '/2026-07-09', '/20260709.html', '/20260709_forecast'])
def test_explicit_date_paths_still_demote_stale_snapshots(today, path):
    item = fusion.Merged('https://example.com' + path, 'Weather', '', '', publish='2026-09-30')
    assert fusion._ranking_date(item) == '2026-07-09'


@pytest.mark.parametrize('title', ['回顾2026年9月1日开学首日', '2026年9月1日开学活动后续报道',
                                  '回顾2026年9月1日天气', 'Recap of weather on 2026-09-01'])
def test_event_title_does_not_replace_publication_date(today, title):
    item = fusion.Merged('https://example.com/news', title, '', '', publish='2026-09-30')
    assert fusion._ranking_date(item) == item.publish


@pytest.mark.parametrize('title_attribute', [' "天气查询"', " '天气查询'", ''])
def test_navigation_with_titles_and_separate_list_items_does_not_hide_forecast(title_attribute):
    menu = '\n\n'.join(f'- [{city}天气](https://example.com/{i}{title_attribute})'
                       for i, city in enumerate(['北京', '上海', '广州', '杭州']))
    evidence = '北京天气预报：明天晴，10–20℃，阵风6–7级。'
    body = ('首页\n\n' + menu + '\n\n天气\n\n微信公众号\n\n扫码随时看天气\n\n') * 5 + evidence
    out = '\n'.join(render._fit_body(body, 160, query='北京天气', body_source='doubao'))
    assert evidence in out
    assert '微信公众号' not in out and '扫码随时看天气' not in out
    assert '[上海天气]' not in out


def test_plain_navigation_does_not_win_fallback_budget():
    body = ('首页\n\n天气\n\n微信公众号\n\n扫码随时看天气\n\n') * 20
    body += '# 北京天气\n\n2026年9月30日\n\n24 ℃\n\n多云 22–30℃\n\n湿度 77%'
    out = '\n'.join(render._fit_body(body, 180, query='北京天气', body_source='doubao'))
    assert '24 ℃' in out and '多云 22–30℃' in out
    assert '扫码随时看天气' not in out


@pytest.mark.parametrize('heading', ['# 北京天气', '[# 北京天气](https://example.com/beijing)'])
def test_numeric_weather_fields_inherit_their_section(heading):
    body = ('首页\n\n天气\n\n' + heading + '\n\n2026年9月30日\n\n24 ℃\n\n多云 22–30℃\n\n湿度 77%\n\n'
            + '一周天气 15天天气 30天天气 历史天气\n\n' * 30 + '\n\n# 无关信息\n\n其他城市湿度 60%')
    out = '\n'.join(render._fit_body(body, 240, query='北京天气', body_source='doubao'))
    assert '24 ℃' in out and '多云 22–30℃' in out and '湿度 77%' in out
    assert '2026年9月30日' in out
    assert '一周天气 15天天气' not in out and '其他城市' not in out


@pytest.mark.parametrize('unit', [
    '```\n[weather](https://a.example) [data](https://b.example)\n```',
    '| [weather](https://a.example) | [data](https://b.example) | 23℃ |',
    'See [weather](https://a.example "observations") and [data](https://b.example) for detailed limitations.',
    '[weather](https://a.example) [data](https://b.example) 23℃',
    '北京天气晴，23℃',
])
def test_navigation_keeps_code_tables_citations_and_short_facts(unit):
    assert render._navigation_units([unit]) == [False]


@pytest.mark.parametrize('source', ['doubao', 'parallel'])
def test_cross_language_excerpt_keeps_upstream_opening(source):
    body = ('Enzyme design breakthrough leads this weekly review.\n\n'
            + 'Selected research evidence. ' * 50 + '\n\nAI avatars.\n\nLee / Calvin K. / Lai')
    out = render._fit_body(body, 250, query='最新的 ai 研究', body_source=source)
    assert out == render._fit_body(body, 250)
    assert 'Calvin' not in '\n'.join(out)


# ---------------------------------------------------------------- 第三期审核（1.2.5）


def _render_one(body, query, title='资料', url='https://article.example/page'):
    item = fusion.Merged(url=url, title=title, body=body, site='', sources={'doubao': 1},
                         body_source='doubao')
    return render.render(query=query, items=[item], cards=[], budget=8000, profile='compact',
                         stats=[], errors=[], elapsed=0, dump_path='/tmp/synthetic-run.json')


def test_two_relevant_reference_links_survive_full_render():
    body = ('# Python 3.14 官方资料\n\n'
            '- [Python 3.14 官方文档](https://docs.python.org/3.14/)\n\n'
            '- [Python 3.14 更新说明](https://docs.python.org/3.14/whatsnew/3.14.html)\n\n'
            + '背景说明与历史沿革。' * 400)
    out = _render_one(body, 'Python 3.14 官方资料', 'Python 3.14 官方资料汇总')
    assert 'https://docs.python.org/3.14/)' in out
    assert 'whatsnew/3.14.html' in out


@pytest.mark.parametrize('menu', [
    # 3 个链接的门户菜单
    '\n\n'.join(f'- [{c}天气](https://example.com/{i})' for i, c in enumerate(['上海', '广州', '杭州'])),
    # 2 个链接夹着纯文本导航词
    '首页\n\n- [上海天气](https://example.com/sh)\n\n- [广州天气](https://example.com/gz)',
])
def test_real_portal_menus_are_still_navigation(menu):
    units = render._passage_units(menu)
    assert all(render._navigation_units(units))


@pytest.mark.parametrize('separator', ['\n', '\n\n'])
def test_linked_heading_does_not_swallow_following_data(separator):
    data = separator.join(['2026年9月30日', '24 ℃', '多云 22–30℃', '湿度 77%'])
    body = '这里是页面介绍。' * 400 + '\n\n[# 北京天气](https://weather.example/beijing)\n' + data
    out = _render_one(body, '北京天气', '北京天气', 'https://weather.example/beijing')
    assert '24 ℃' in out and '湿度 77%' in out


def test_linked_heading_is_its_own_unit():
    units = render._passage_units('[# 北京天气](https://a.example)\n24 ℃\n湿度 77%')
    assert units[0] == '[# 北京天气](https://a.example)'
    assert render._heading_level(units[0]) == 1
    assert render._heading_level('[# 北京天气](https://a.example)\n24 ℃') == 0


@pytest.mark.parametrize('query', ['茅台股价 2000元', '茅台股价跌破1999', '苹果股价 2010美元', '茅台股价2050'])
def test_price_numbers_are_not_historical_years(today, query):
    assert fusion.is_strong_fresh_query(query)


@pytest.mark.parametrize('query', ['北京天气 2025', '北京2025年天气', 'Beijing weather 2019'])
def test_standalone_past_years_remain_historical(today, query):
    assert not fusion.is_fresh_query(query)


@pytest.mark.parametrize('a,b', [
    ('https://a.example/p#:~:text=hello%20world', 'https://a.example/p'),
    ('https://a.example/p#intro:~:text=hello', 'https://a.example/p'),
])
def test_text_fragments_fold_into_the_page(a, b):
    assert fusion.canonical_url(a) == fusion.canonical_url(b)


def test_spa_routes_stay_distinct_after_fragment_cleanup():
    assert fusion.canonical_url('https://docs.example/#/install') != fusion.canonical_url('https://docs.example/#/auth')


def test_short_placeholder_key_only_redacts_whole_words(cfg):
    cfg['doubao']['api_key'] = 'test'
    out = sources.redact('HTTP 400 latest test result: contest key=test', cfg)
    assert 'latest' in out and 'contest' in out
    assert out.count('[已脱敏的密钥]') == 2


def test_long_key_is_still_redacted_inside_words(cfg):
    cfg['doubao']['api_key'] = 'sk-abcdefgh1234'
    assert 'abcdefgh' not in sources.redact('Bearer xsk-abcdefgh1234y failed', cfg)


def test_bare_value_lists_do_not_inherit_section_hits():
    wind = '\n\n'.join(['* 1级', '* 2级', '* 2级', '* 3级'] * 5)
    fact = '北京天气晴，最高气温 20℃，夜间北风。'
    body = '# 北京天气\n\n' + wind + '\n\n' + '页面说明。' * 300 + '\n\n' + fact
    out = '\n'.join(render._fit_body(body, 200, query='北京天气', body_source='doubao'))
    assert fact in out
    assert '* 2级' not in out


def test_fallback_keeps_table_rows_and_code_blank_lines():
    body = ('* [首页](https://a/x)\n* [天气](https://a/y)\n* [新闻](https://a/z)\n\n'
            '|日期|气温|\n|---|---|\n|9-30|10-20|\n\n```\na\n\nb\n```\n\n' + '说明文字。' * 300)
    out = [line.strip() for line in render._fit_body(body, 300, query='上海 空气 指数')]
    assert out[:3] == ['|日期|气温|', '|---|---|', '|9-30|10-20|']
    assert out[4:8] == ['```', 'a', '', 'b']
    assert '[首页]' not in '\n'.join(out)
