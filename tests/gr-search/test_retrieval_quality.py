"""审核案例的合成回归：边界、跨语言、时效和导航噪声。全部离线。"""
import datetime

import pytest

import config
import fusion
import gr_search
import render
import sources


@pytest.fixture
def today(monkeypatch):
    class FixedDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 29)
    monkeypatch.setattr(datetime, 'date', FixedDate)
    return FixedDate.today()


@pytest.mark.parametrize('word', ['portrait', 'Lai', 'trained', 'said', 'ai_model', 'email'])
def test_ai_does_not_select_substrings(word):
    body = 'Useful original opening.\n\n' + 'Neutral filler. ' * 60 + '\n\n' + word
    assert render._fit_body(body, 150, query='ai') == render._fit_body(body, 150)


@pytest.mark.parametrize('query, evidence', [
    ('ai', '中文AI研究支持边界。'), ('ai', 'AI: useful evidence.'),
    ('22.04', 'Version 22.04 is supported.'), ('api.v2', 'Use api.v2 here.'),
    ('Ubuntu22.04', 'Ubuntu 22.04 is supported.'),
])
def test_precise_terms_still_select_evidence(query, evidence):
    body = 'Unrelated long opening. ' * 70 + '\n\n' + evidence
    assert evidence in '\n'.join(render._fit_body(body, 150, query=query))


@pytest.mark.parametrize('query', ['最新的 ai 研究', 'AI research evaluation', 'ai avatar 最新研究'])
def test_parallel_sparse_matches_keep_upstream_excerpt(query):
    body = ('Enzyme design breakthrough leads this weekly review.\n\n'
            + 'The original selected evidence continues. ' * 50 + '\n\n'
            + 'AI avatar portrait.')
    assert render._fit_body(body, 250, query=query, body_source='parallel') == render._fit_body(body, 250)


def test_parallel_good_same_language_matches_can_select():
    body = 'Generic opening. ' * 100 + '\n\nAI research evaluates enzyme design.'
    out = render._fit_body(body, 180, query='AI research', body_source='parallel')
    assert 'AI research evaluates enzyme design.' in '\n'.join(out)


def test_body_source_follows_representative_and_reaches_renderer():
    long = 'Upstream selected discovery.\n\n' + 'Selected evidence. ' * 150 + '\n\nAI avatars.'
    docs = [sources.Doc(url='https://example.com', title='Title', body='short', site='', source='doubao', rank=1),
            sources.Doc(url='https://example.com', title='Title', body=long, site='', source='parallel', rank=2)]
    merged = fusion.merge(docs)
    assert merged[0].body_source == 'parallel'
    text, _ = render.render_results(merged, 500, query='最新 ai 研究')
    assert 'Upstream selected discovery.' in text
    assert 'AI avatars.' not in text


def test_term_limit_keeps_input_order_across_languages():
    terms = render._query_terms('北京天气 ' + ' '.join(f'word{i}' for i in range(80)))
    assert len(terms) == 64
    assert {'北京', '京天', '天气', 'word0'} <= terms
    assert 'word79' not in terms


def test_weather_navigation_does_not_displace_forecast():
    menu = '[北京天气](https://a.example) [上海天气](https://b.example) [广州天气](https://c.example)'
    evidence = '北京天气预报：明天晴，10–20℃，阵风6–7级。'
    body = (menu + '\n\n') * 30 + evidence + '\n\n' + menu
    out = '\n'.join(render._fit_body(body, 160, query='北京天气'))
    assert evidence in out
    assert '[上海天气]' not in out


@pytest.mark.parametrize('block', [
    '|[北京](https://a.example)|[上海](https://b.example)|10℃|',
    '```\n[北京](https://a.example) [上海](https://b.example)\n```',
    'See [study](https://a.example) and [data](https://b.example) for the full experimental method and limitations.',
])
def test_linked_evidence_is_not_a_menu(block):
    assert not render._link_menu(block)


def test_recency_decays_by_days_and_crosses_year_smoothly(today, monkeypatch):
    assert fusion._recency_bonus('2026-09-29') == pytest.approx(.03)
    assert fusion._recency_bonus('2026-08-30') == pytest.approx(.015)
    assert fusion._recency_bonus('2026-01-02') < .001
    class January(datetime.date):
        @classmethod
        def today(cls):
            return cls(2026, 1, 3)
    monkeypatch.setattr(datetime, 'date', January)
    assert 0 < fusion._recency_bonus('2026-01-02') - fusion._recency_bonus('2025-12-30') < .003
    assert fusion._recency_bonus('2026') == 0


@pytest.mark.parametrize('strong', [False, True])
def test_dated_source_cannot_push_undated_runner_up_to_tail(today, strong):
    docs = [fusion.Merged(url=f'https://{source}.example/{rank}', title='Title', body='', site='',
                          sources={source: rank}, publish='2026-09-29' if source == 'doubao' else None)
            for source in ('doubao', 'parallel') for rank in range(1, 11)]
    ranked = fusion.rank(docs, config.DEFAULTS, fresh=True, strong_fresh=strong)
    assert next(i for i, item in enumerate(ranked) if item.sources == {'parallel': 2}) <= 5
    undated = next(item for item in docs if item.sources == {'parallel': 2})
    assert undated.score == pytest.approx(1 / 62)


@pytest.mark.parametrize('query', ['北京天气', '茅台股价', '美元人民币汇率', '皇马比分',
                                  'Beijing weather', 'Apple stock price', 'USD exchange rate', '茅台600519股价'])
def test_implicit_live_queries_are_strong(query):
    assert fusion.is_fresh_query(query)
    assert fusion.is_strong_fresh_query(query)


@pytest.mark.parametrize('query', ['北京历史天气', '北京2025年天气', '昨天北京天气', '汇率原理',
                                  '天气预测模型', '天气 API', '股价数据集', '比分算法',
                                  'historical Beijing weather', 'weather forecasting models', '北京20260709天气'])
def test_background_and_historical_queries_are_not_implicit_live(query):
    assert not fusion.is_fresh_query(query)
    assert not fusion.is_strong_fresh_query(query)


@pytest.mark.parametrize('query', ['最新天气研究', 'latest weather research'])
def test_research_recency_does_not_become_daily_live_query(query):
    assert fusion.is_fresh_query(query)
    assert not fusion.is_strong_fresh_query(query)


@pytest.mark.parametrize('title,url', [
    ('北京2026年7月9日天气', 'https://example.com/weather'),
    ('北京天气', 'https://example.com/20260709.html'),
    ('北京天气', 'https://example.com/2026/07/09/weather'),
])
def test_content_date_overrides_crawl_date_for_ranking(today, title, url):
    old = fusion.Merged(url=url, title=title, body='', site='', publish='2026-09-29', sources={'doubao': 1})
    live = fusion.Merged(url='https://live.example', title='实况', body='', site='', sources={'parallel': 2})
    assert fusion.rank([old, live], config.DEFAULTS, fresh=True, strong_fresh=True)[0] is live
    assert old.publish == '2026-09-29'


@pytest.mark.parametrize('title,url', [
    ('Invalid 2026-13-45', 'https://example.com'),
    ('Compare 2026-01-01 and 2026-09-01', 'https://example.com'),
    ('Title', 'https://example.com?tracking=20260709'),
])
def test_ambiguous_dates_fall_back_to_metadata(title, url):
    item = fusion.Merged(url=url, title=title, body='', site='', publish='2026-09-29')
    assert fusion._ranking_date(item) == item.publish


def test_q_reaches_selection_and_implicit_ttl(monkeypatch):
    captured = {}
    def fake(cfg, query, opts, **kwargs):
        captured['ttl'] = opts['cache_ttl']
        return sources.SourceResult('doubao', docs=[sources.Doc(
            url='https://example.com', title='天气', body='实况', site='', source='doubao', rank=1)])
    monkeypatch.setattr(sources, 'doubao_search', fake)
    monkeypatch.setattr(render, 'render', lambda **kw: captured.update(kw) or '')
    args = gr_search.build_parser().parse_args(['search', '查一下', '--q', '北京天气', '--source', 'doubao', '--no-dump'])
    assert gr_search.run_search(args, config.DEFAULTS) == 0
    assert '北京天气' in captured['selection_query']
    assert captured['ttl'] == 120


@pytest.mark.parametrize('time_range,ttl,strong', [
    ('OneYear', None, False), ('2019-01-01..2019-12-31', None, False),
    ('OneWeek', 120, False), ('OneDay', 120, True),
])
def test_explicit_range_overrides_implicit_weather(monkeypatch, time_range, ttl, strong):
    captured = {}
    def fake(cfg, query, opts, **kwargs):
        captured['ttl'] = opts['cache_ttl']
        return sources.SourceResult('doubao', docs=[])
    monkeypatch.setattr(sources, 'doubao_search', fake)
    monkeypatch.setattr(fusion, 'rank', lambda docs, cfg, **kwargs: captured.update(kwargs) or docs)
    monkeypatch.setattr(render, 'render', lambda **kw: '')
    args = gr_search.build_parser().parse_args([
        'search', '北京天气', '--time-range', time_range, '--source', 'doubao', '--no-dump'])
    gr_search.run_search(args, config.DEFAULTS)
    assert captured['ttl'] == ttl
    assert captured['strong_fresh'] is strong
