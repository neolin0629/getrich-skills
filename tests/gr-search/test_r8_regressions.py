"""R8：中文资料短语与标题网址边界，验证完整渲染中的引用保留及菜单剔除。"""

import pytest

import fusion
import render


def heading(text, style):
    if style == 'linked':
        return f'[## {text}](https://article.example/section)'
    if style == 'setext':
        return text + '\n--------'
    return '## ' + text


def display(body, query):
    item = fusion.Merged('https://article.example/report', query, body, '',
                         sources={'doubao': 1}, body_source='doubao')
    return render.render(query=query, items=[item], cards=[], budget=8000, profile='compact',
                         stats=[], errors=[], elapsed=0, dump_path=None)


@pytest.mark.parametrize('title', ['公司资料', '个人资料', '投资参考', '今日参考价',
                                    '基本资料', '下载资料', '文献栏目'])
@pytest.mark.parametrize('style', ['atx', 'linked', 'setext'])
def test_chinese_category_names_do_not_protect_site_tabs(title, style):
    """栏目名含资料或参考，不等于正式资料清单。"""
    menu = '\n\n'.join(f'- [{name}](https://tabs.example/{i})'
                         for i, name in enumerate(['行情', '资讯', '财务', '股东']))
    body = '# 茅台股价\n\n茅台股价的变动说明。\n\n' + heading(title, style) + '\n\n' + menu
    output = display(body, '茅台股价')
    assert 'https://tabs.example/' not in output
    assert '茅台股价的变动说明。' in output


@pytest.mark.parametrize('title', ['参考资料', '参考文献', '相关资料', '学习资料',
                                    'Python 3.14 官方资料', 'Python 官方文档'])
@pytest.mark.parametrize('style', ['atx', 'linked', 'setext'])
def test_explicit_chinese_reference_phrases_preserve_short_citations(title, style):
    links = '\n\n'.join(f'- [{name}](https://docs.example/{i})'
                         for i, name in enumerate(['PEP 8', 'Black', 'Ruff']))
    body = '# Python 工具\n\nPython 项目说明。\n\n' + heading(title, style) + '\n\n' + links
    output = display(body, 'Python 代码风格 工具')
    assert all(f'https://docs.example/{i}' in output for i in range(3))


@pytest.mark.parametrize('url', ['<https://w.example/resources/bj>',
                                  'https://w.example/references/bj',
                                  'HTTP://w.example/documentation/bj'])
@pytest.mark.parametrize('style', ['atx', 'linked', 'setext'])
def test_title_autolinks_and_bare_urls_do_not_protect_city_menus(url, style):
    """网址是展示数据，其路径关键词不能让无关标题获得资料保护。"""
    menu = '\n\n'.join(f'- [{city}](https://cities.example/{i})'
                         for i, city in enumerate(['北京天气', '上海天气', '广州天气']))
    body = '北京天气：温度 24 ℃，湿度 77%。\n\n' + heading('北京天气 ' + url, style) + '\n\n' + menu
    output = display(body, '北京天气')
    assert 'https://cities.example/' not in output
    assert '温度 24 ℃' in output and '湿度 77%' in output
    assert url in output


@pytest.mark.parametrize('url', ['<https://w.example/featured/topics>',
                                  'https://w.example/热门/排行',
                                  'https://w.example/company/resources'])
@pytest.mark.parametrize('before', [True, False])
@pytest.mark.parametrize('style', ['atx', 'linked', 'setext'])
def test_real_reference_title_survives_adjacent_urls(url, before, style):
    """剥离网址不能吞掉两侧的真实资料短语，也不能让 URL 的排除词拒绝资料。"""
    title = (url + ' 参考资料') if before else ('参考资料 ' + url)
    links = '\n\n'.join(f'- [{name}](https://docs.example/{i})'
                         for i, name in enumerate(['PEP 8', 'Black', 'Ruff']))
    body = '# Python 工具\n\nPython 项目说明。\n\n' + heading(title, style) + '\n\n' + links
    output = display(body, 'Python 代码风格 工具')
    assert all(f'https://docs.example/{i}' in output for i in range(3))
    assert url in output
