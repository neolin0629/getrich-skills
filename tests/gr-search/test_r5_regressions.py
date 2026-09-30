"""R5 的结构性回归：完整渲染、资源身份和实际搜索时效参数。"""

import copy
import datetime
import json

import pytest

import config
import fusion
import gr_search
import render
import sources


def rendered(body, query, source='doubao'):
    item = fusion.Merged('https://article.example/page', query, body, '',
                         sources={source: 1}, body_source=source)
    return render.render(query=query, items=[item], cards=[], budget=8000,
                         profile='compact', stats=[], errors=[], elapsed=0, dump_path=None)


@pytest.mark.parametrize('container', ['fenced', 'indented', 'paragraph'])
def test_fallback_deletes_navigation_by_position(container):
    """相同菜单先出现在代码或叙述中时，删后面的菜单，不能篡改前面的示例。"""
    links = '\n'.join(f'* [{label}](https://nav.example/{path})'
                      for label, path in [('首页', 'home'), ('天气', 'weather'), ('新闻', 'news')])
    if container == 'fenced':
        protected = '```text\n' + links + '\n```'
        menu = links
    elif container == 'indented':
        protected = '    首页\n\n    print("preserved")'
        menu = '首页\n\n' + links
    else:
        protected = '操作示例：\n首页\n此处只是操作说明。'
        menu = '首页\n\n' + links
    out = rendered(protected + '\n\n' + menu + '\n\n' + '背景说明。' * 500, '菜单模板')
    assert '\n'.join('    ' + line for line in protected.splitlines()) in out
    assert out.count('https://nav.example/home') == (1 if container == 'fenced' else 0)
    assert out.count('首页') == 1


def test_sentence_fragment_does_not_delete_its_whole_source_paragraph():
    protected = '一段说明。' * 130 + '\n首页'
    menu = '首页\n\n[天气](https://nav.example/weather)\n\n[新闻](https://nav.example/news)'
    out = rendered(protected + '\n\n' + menu + '\n\n' + '背景说明。' * 500, '模板信息')
    assert '\n'.join('    ' + line for line in protected.splitlines()) in out
    assert 'https://nav.example/' not in out


@pytest.mark.parametrize('budget, profile', [(8000, 'compact'), (15000, 'standard'), (30000, 'full')])
def test_fitting_body_still_removes_real_menu_and_preserves_code(budget, profile):
    """正文装得下也要过滤菜单，不能让 full 档重新输出小预算已经去掉的菜单。"""
    links = '\n'.join(f'- [{label}](https://nav.example/{i})'
                      for i, label in enumerate(['首页', '天气', '新闻']))
    code = '```text\n' + links + '\n```'
    body = code + '\n\n' + links + '\n\n湿度 77%，温度 24 ℃。'
    item = fusion.Merged('https://article.example/page', '北京天气', body, '',
                         sources={'doubao': 1}, body_source='doubao')
    out = render.render(query='北京天气', items=[item], cards=[], budget=budget,
                        profile=profile, stats=[], errors=[], elapsed=0, dump_path=None)
    assert '\n'.join('    ' + line for line in code.splitlines()) in out
    assert out.count('https://nav.example/0') == 1
    assert '湿度 77%' in out and '温度 24 ℃' in out


@pytest.mark.parametrize('heading', ['# 接口规范', '[# 接口规范](https://article.example/api)'])
def test_two_short_references_are_not_a_menu_with_their_heading(heading):
    links = '- [RFC](https://docs.example/rfc)\n\n- [API](https://docs.example/api)'
    out = rendered(heading + '\n\n' + links + '\n\n' + '背景说明。' * 500, '接口规范')
    assert 'https://docs.example/rfc' in out and 'https://docs.example/api' in out


@pytest.mark.parametrize('heading', ['# SQLite 官方资料', '# SQLite references'])
def test_explicit_reference_section_keeps_short_titles(heading):
    links = '\n\n'.join(f'- [{name}](https://sqlite.org/{i})'
                        for i, name in enumerate(['SQL Syntax', 'C API', 'File Format']))
    body = heading + '\n\nSQLite 官方资料入口如下。\n\n' + links
    body += '\n\n# 网站导航\n\n[首页](https://nav.example/home)\n\n'
    body += '[天气](https://nav.example/weather)\n\n[新闻](https://nav.example/news)\n\n'
    body += '背景说明。' * 500
    out = rendered(body, '整理 SQLite 官方资料链接')
    assert all(f'https://sqlite.org/{i}' in out for i in range(3))
    assert 'https://nav.example/' not in out


@pytest.mark.parametrize('heading_kind', ['atx', 'linked', 'setext'])
@pytest.mark.parametrize('count', [2, 3, 5])
@pytest.mark.parametrize('language', ['zh', 'en'])
def test_descriptive_reference_lists_survive_all_heading_forms(heading_kind, count, language):
    """标题不贡献菜单票数，描述性资料列表也不能因多了一条引用而消失。"""
    query = 'Python 3.14 版本信息' if language == 'zh' else 'Python 3.14 version details'
    names = (['官方文档', '更新说明', '安装指南', '语言参考', '标准库参考'] if language == 'zh'
             else ['official documentation', 'release notes', 'installation guide',
                   'language reference', 'standard library reference'])
    urls = [f'https://docs.python.org/3.14/resource-{i}' for i in range(count)]
    headings = {'atx': '# ' + query, 'linked': f'[# {query}](https://article.example/python)',
                'setext': query + '\n======================'}
    links = '\n\n'.join(f'- [Python 3.14 {name}]({url})' for name, url in zip(names, urls))
    background = '背景说明与历史沿革。' if language == 'zh' else 'Unrelated background history. '
    out = rendered(headings[heading_kind] + '\n\n' + links + '\n\n' + background * 400, query)
    assert all(url in out for url in urls)
    assert out.count(background) < 5


@pytest.mark.parametrize('route', ['/login', '/portal/reports', '/account/profile',
                                   '/search?q=x', '!/login'])
def test_spa_route_names_do_not_define_resource_equivalence(route):
    docs = [sources.Doc('https://app.example/', 'Application home', 'Welcome home. ' * 20, '', 'doubao', 1),
            sources.Doc('https://app.example/#' + route, 'Independent route', 'Route-specific data. ' * 20,
                        '', 'parallel', 1)]
    items = fusion.rank(fusion.merge(docs), config.DEFAULTS)
    assert {item.body for item in items} == {doc.body for doc in docs}
    assert len(items) == 2
    assert all(len(item.sources) == 1 and item.score == pytest.approx(1 / 61) for item in items)


def test_identical_portal_article_still_merges_by_content():
    base = 'https://blog.example/article/'
    body = 'The complete article has the same facts and text in both responses. ' * 10
    docs = [sources.Doc(base, 'Identical article title', body, '', 'doubao', 1),
            sources.Doc(base + '#/portal/', 'Identical article title', body, '', 'parallel', 1)]
    assert fusion.canonical_url(docs[0].url) != fusion.canonical_url(docs[1].url)
    merged = fusion.rank(fusion.merge(docs), config.DEFAULTS)
    assert len(merged) == 1 and merged[0].body == body
    assert {merged[0].url, *merged[0].also_urls} == {doc.url for doc in docs}
    assert merged[0].score == pytest.approx(2 / 61)


@pytest.mark.parametrize('query, expected', [
    ('茅台股价 2000元', True), ('茅台股价 2000 元', True),
    ('stock price below 2000 USD', True), ('茅台股价跌破 1999 元', True),
    ('北京天气2025', False), ('上海天气2024', False), ('北京天气 2025', False),
    ('北京2025年天气', False), ('weather Beijing 2019', False),
    ('茅台股价 2019 年', False), ('茅台股价跌破2019年低点', False),
    ('茅台股价2000', True), ('stock price 2010', True), ('汇率2000', False),
    ('比分2019', False), ('茅台股价2050', True), ('北京天气2027', True),
    ('茅台股价 1999 港元', True), ('stock price 2010 RMB', True),
    ('stock price at $1999', True), ('茅台股价报 1999', True),
    ('AAPL stock price in 2021', False), ('stock price during 2019', False),
    ('exchange rate for 2020', False), ('stock price in 2000 USD', True),
])
def test_year_and_price_context_controls_search_policy(query, expected, monkeypatch, capsys):
    """用实际编排入口守住日级排序和 TTL；源为假函数，不读配置或触网。"""
    class FixedDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2026, 9, 30)
    monkeypatch.setattr(datetime, 'date', FixedDate)
    seen = []
    def fake_source(cfg, text, opts):
        seen.append(opts['cache_ttl'])
        return sources.SourceResult('doubao', docs=[
            sources.Doc('https://example.test/result', 'Synthetic result', 'Synthetic data.', '', 'doubao', 1)])
    monkeypatch.setattr(sources, 'doubao_search', fake_source)
    args = gr_search.build_parser().parse_args(['search', query, '--source', 'doubao',
                                               '--no-cache', '--no-dump', '--json'])
    assert gr_search.run_search(args, copy.deepcopy(config.DEFAULTS)) == 0
    flags = json.loads(capsys.readouterr().out)['diagnostics']
    assert flags['fresh'] is expected and flags['strong_fresh'] is expected
    assert seen == [120 if expected else None]
