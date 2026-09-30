"""R7：资料保护只依赖标题文字和明确短语，文章标题不能保护整页菜单。"""

import pytest

import fusion
import render


def display(body, query='美联储 利率'):
    item = fusion.Merged('https://article.example/report', query, body, '',
                         sources={'doubao': 1}, body_source='doubao')
    return render.render(query=query, items=[item], cards=[], budget=8000, profile='compact',
                         stats=[], errors=[], elapsed=0, dump_path=None)


def heading(text, style, level=2):
    hashes = '#' * level
    if style == 'linked':
        return f'[{hashes} {text}](https://article.example/section)'
    if style == 'setext':
        return text + '\n' + ('========' if level == 1 else '--------')
    return f'{hashes} {text}'


MENU = '\n\n'.join(f'- [{name}](https://nav.example/{i})'
                     for i, name in enumerate(['Home', 'About', 'Contact', 'Careers']))
REFERENCES = '\n\n'.join(f'- [{name}](https://docs.example/{i})'
                           for i, name in enumerate(['PEP 8', 'Black', 'Ruff']))


@pytest.mark.parametrize('title', [
    'Quick Links', 'Related', '阅读排行', '热门推荐', 'Related Posts', 'Related articles',
    'Featured Links', 'StreetStats 101 | Related Topics', 'Related ETFs',
    'Quick External Links', 'Featured Related Resources', '热门相关阅读',
])
@pytest.mark.parametrize('style', ['atx', 'linked', 'setext'])
def test_recommendation_or_footer_headings_do_not_protect_short_menus(title, style):
    """页脚及推荐区有 related/links/阅读词，不代表它是资料章节。"""
    body = '# 新闻\n\n美联储利率决定将在会议后公布。\n\n'
    body += heading(title, style) + '\n\n' + MENU + '\n\n其他正文。'
    output = display(body)
    assert 'https://nav.example/' not in output
    assert '美联储利率决定将在会议后公布。' in output


@pytest.mark.parametrize('title', ['相关阅读', '延伸阅读', '推荐阅读', '相关链接', '参考资料',
                                    'See also', 'Further reading', 'Related reading',
                                    'Related resources', 'Useful links', 'External links'])
def test_explicit_reference_phrases_still_keep_short_citations(title):
    body = '# Python 工具\n\nPython 项目说明。\n\n## ' + title + '\n\n' + REFERENCES
    output = display(body, 'Python 代码风格 工具')
    assert all(f'https://docs.example/{i}' in output for i in range(3))


@pytest.mark.parametrize('title', [
    '[## 北京天气](https://w.example/resources/bj)',
    '[## 北京天气](https://w.example/bj "Related resources")',
    '## [北京天气](https://w.example/resources/bj "References")',
    '[北京天气](https://w.example/resources/bj)\n--------',
    '[## 北京天气](https://w.example/(page)/resources)',
    '## [北京天气](https://w.example/(page)/resources)',
    '[北京天气](https://w.example/(page)/resources)\n--------',
])
def test_link_targets_and_title_attributes_do_not_supply_reference_context(title):
    """URL 和链接 title 属性中的关键词不是可见标题，不得改变菜单判定。"""
    links = '\n\n'.join(f'- [{city}](https://cities.example/{i})'
                         for i, city in enumerate(['北京天气', '上海天气', '广州天气']))
    body = '北京天气预报：温度 24 ℃，湿度 77%。\n\n' + title + '\n\n' + links
    output = display(body, '北京天气')
    assert 'https://cities.example/' not in output
    assert '温度 24 ℃' in output and '湿度 77%' in output


@pytest.mark.parametrize('title', ['2026 年度阅读报告', 'AI-related report', 'Fed-related news'])
def test_article_titles_do_not_protect_navigation_before_or_after_body_heading(title):
    body = '# ' + title + '\n\n' + MENU + '\n\n## 正文\n\n美联储利率政策说明。\n\n' + MENU
    output = display(body)
    assert 'https://nav.example/' not in output
    assert '美联储利率政策说明。' in output


@pytest.mark.parametrize('style', ['atx', 'linked', 'setext'])
def test_level_one_reference_context_stops_at_the_next_heading(style):
    """一级资料标题仍保留眼前引用，但下面的正文子标题不能继承全篇豁免。"""
    body = heading('Python 参考资料', style, level=1) + '\n\n' + REFERENCES
    body += '\n\n## 正文\n\nPython 工具的使用说明。\n\n' + MENU
    output = display(body, 'Python 工具')
    assert all(f'https://docs.example/{i}' in output for i in range(3))
    assert 'https://nav.example/' not in output
    assert 'Python 工具的使用说明。' in output


def test_nested_reference_subsections_keep_context_until_peer_heading():
    """一级标题的范围限制不应破坏普通资料章节对下级小节的保护。"""
    body = '# Python 工具\n\n## 参考资料\n\n### 格式检查\n\n' + REFERENCES
    body += '\n\n## 站点菜单\n\n' + MENU + '\n\n其他说明。'
    output = display(body, 'Python 工具')
    assert all(f'https://docs.example/{i}' in output for i in range(3))
    assert 'https://nav.example/' not in output
