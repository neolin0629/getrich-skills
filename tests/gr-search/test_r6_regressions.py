"""R6：历史比赛与汇率的查询策略，常见阅读章节中的短资料引用。"""

import copy
import datetime
import json

import pytest

import config
import fusion
import gr_search
import render
import sources


@pytest.mark.parametrize('query, fresh', [
    ('2022世界杯决赛比分', False), ('比分 2018 欧冠决赛', False),
    ('2022 World Cup final live score', False), ('美元兑人民币汇率2019', False),
    ('USD exchange rate 2020', False), ('比分2019', False), ('汇率2000', False),
    ('北京天气2025', False), ('AAPL stock price in 2021', False),
    ('茅台股价 2000 元', True), ('茅台股价2050', True), ('stock price 2010', True),
    ('stock price below 2000 USD', True), ('汇率 2000 点', True),
    ('比分3:1', True), ('美元兑人民币汇率7.2', True),
    ('2027 World Cup live score', True), ('2027美元兑人民币汇率', True),
])
def test_historical_topics_keep_cache_policy_and_source_order(query, fresh, monkeypatch, capsys):
    """真实编排入口：历史查询不收紧缓存，也不把旧的首条资料降到今日报价之后。"""
    class FixedDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 30)

    monkeypatch.setattr(datetime, 'date', FixedDate)
    seen = []

    def fake_search(cfg, text, opts):
        seen.append(opts['cache_ttl'])
        return sources.SourceResult('doubao', docs=[
            sources.Doc('https://example.test/archive', 'Archived record',
                        'Historical match or rate record.', '', 'doubao', 1, publish='2022-12-18'),
            sources.Doc('https://example.test/current', 'Current record',
                        'Current match or rate record.', '', 'doubao', 2, publish='2026-09-30'),
        ])

    monkeypatch.setattr(sources, 'doubao_search', fake_search)
    args = gr_search.build_parser().parse_args([
        'search', query, '--source', 'doubao', '--no-cache', '--no-dump', '--json'])
    assert gr_search.run_search(args, copy.deepcopy(config.DEFAULTS)) == 0
    output = json.loads(capsys.readouterr().out)
    assert output['diagnostics']['fresh'] is fresh
    assert output['diagnostics']['strong_fresh'] is fresh
    assert seen == [120 if fresh else None]
    if not fresh:
        assert [doc['url'] for doc in output['docs']] == [
            'https://example.test/archive', 'https://example.test/current']


@pytest.mark.parametrize('heading', [
    '参考资料', 'See also', 'Further reading', '相关阅读', '延伸阅读', '相关链接',
    'Related resources', 'External links', 'Bibliography', '推荐阅读', '外部链接',
])
@pytest.mark.parametrize('style', ['atx', 'linked', 'setext'])
@pytest.mark.parametrize('fits', [True, False])
def test_reading_sections_preserve_short_links_without_protecting_next_menu(heading, style, fits):
    """整页和预算选段都保留资料；下一同级章节中的菜单仍需剔除。"""
    title = {'atx': '## ' + heading,
             'linked': f'[## {heading}](https://article.example/section)',
             'setext': heading + '\n----------------'}[style]
    urls = ['https://peps.python.org/pep-0008/', 'https://black.readthedocs.io/',
            'https://docs.astral.sh/ruff/']
    names = ['PEP 8', 'Black', 'Ruff']
    links = '\n\n'.join(f'- [{name}]({url})' for name, url in zip(names, urls))
    body = '# Python 代码风格工具\n\n这些工具用于 Python 项目。\n\n' + title + '\n\n' + links
    body += '\n\n这些工具可配合使用。\n\n## 网站导航\n\n首页\n\n'
    body += '[天气](https://nav.example/weather)\n\n[新闻](https://nav.example/news)'
    body += '\n\n## 背景\n\n' + ('无关背景说明。' * 800 if not fits else '其他说明。')
    query = 'Python 代码风格 工具' if fits else 'Python PEP 8 Black Ruff 代码风格 工具'
    item = fusion.Merged('https://article.example/style', query, body, '',
                         sources={'doubao': 1}, body_source='doubao')
    output = render.render(query=query, items=[item], cards=[], budget=8000, profile='compact',
                           stats=[], errors=[], elapsed=0, dump_path=None)
    assert all(url in output for url in urls)
    assert 'https://nav.example/' not in output


def test_plain_navigation_still_wins_inside_a_reading_section():
    """资料章节内混入明确菜单标签时仍过滤，扩充标题不能成为整章导航豁免。"""
    body = ('# Python 工具\n\n## See also\n\n首页\n\n'
            '[天气](https://nav.example/weather)\n\n[新闻](https://nav.example/news)\n\n'
            'Python 工具的使用说明。')
    item = fusion.Merged('https://article.example/tools', 'Python 工具', body, '',
                         sources={'doubao': 1}, body_source='doubao')
    output = render.render(query='Python 工具', items=[item], cards=[], budget=8000, profile='compact',
                           stats=[], errors=[], elapsed=0, dump_path=None)
    assert 'https://nav.example/' not in output
    assert 'Python 工具的使用说明。' in output
