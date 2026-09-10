"""跨源证据完整性、默认并行和缓存原子性的行为回归。"""
import copy
import datetime
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import config
import fusion
import gr_search
import sources
from sources import Doc


def document(source, rank, **overrides):
    fields = dict(url=f'https://{source}.example/{rank}', title='研究报告与政策执行情况',
                  body='正文', site=source, source=source, rank=rank)
    fields.update(overrides)
    return Doc(**fields)


def test_long_common_intro_does_not_merge_different_reports():
    prefix = '这是研究方法与经济背景的公共说明。' * 120
    docs = [document('doubao', 1, body=prefix + '甲公司在国内经营设备制造业务。' * 100),
            document('parallel', 1, body=prefix + '乙公司在海外提供医疗护理服务。' * 100)]
    merged = fusion.merge(docs)
    assert len(merged) == 2
    assert [(x.url, x.body) for x in merged] == [(x.url, x.body) for x in docs]


@pytest.mark.parametrize('body', ['Access denied', '登录后查看全文', 'Service temporarily unavailable'])
def test_error_pages_are_not_cross_source_evidence(body):
    assert len(fusion.merge([document('doubao', 1, body=body), document('parallel', 1, body=body)])) == 2


def test_representative_keeps_reference_fields_together():
    first = document('doubao', 1, url='https://example.com/report', title='旧标题',
                     body='短摘要', publish='2025-01-01', authority=1, rank_score=.9)
    second = document('parallel', 1, url='https://www.example.com/report', title='更新标题',
                      body='这份完整正文来自更新页面。' * 30, publish='2026-01-01')
    result, = fusion.merge([first, second])
    assert (result.url, result.title, result.body, result.publish, result.authority, result.rank_score) == (
        second.url, second.title, second.body, second.publish, None, None)
    assert result.also_urls == [first.url]
    assert result.sources == {'doubao': 1, 'parallel': 1}


def test_metadata_does_not_override_cross_source_rank():
    docs = []
    for source in ('doubao', 'parallel'):
        for rank in range(1, 11):
            metadata = dict(authority=1, rank_score=1.) if source == 'doubao' else {}
            docs.append(fusion._from_doc(document(source, rank, **metadata)))
    ranked = fusion.rank(docs, config.DEFAULTS)
    assert sum('parallel' in d.sources for d in ranked[:10]) == 5
    assert next(i for i, d in enumerate(ranked) if d.sources == {'parallel': 1}) < next(
        i for i, d in enumerate(ranked) if d.sources == {'doubao': 10})
    assert [d.url for d in fusion.rank(list(reversed(docs)), config.DEFAULTS)] == [d.url for d in ranked]


def test_overlap_is_counted_once_by_rrf():
    one = fusion._from_doc(document('doubao', 1))
    both = fusion._from_doc(document('doubao', 10))
    both.sources['parallel'] = 10
    fusion.rank([one, both], config.DEFAULTS)
    assert both.score == pytest.approx(2 / 70)
    assert both.score > one.score


@pytest.mark.parametrize('value', ['2099-01-01', '2099', '2099-99-99', '2026-13-45', {}, None])
@pytest.mark.parametrize('strong', [False, True])
def test_invalid_or_future_publish_not_rewarded(value, strong):
    assert fusion._recency_bonus(value, strong) == 0


def test_freshness_is_relative_to_rank():
    doc = fusion._from_doc(document('parallel', 1, publish=datetime.date.today().isoformat()))
    fusion.rank([doc], config.DEFAULTS, fresh=True, strong_fresh=True)
    assert doc.score == pytest.approx(1.2 / 61)


@pytest.mark.parametrize('value', ['unknown', float('nan'), float('inf'), -1, 2, True, {}])
def test_bad_metadata_downgrades_without_losing_document(value):
    docs, _ = sources._map_custom({'Result': {'WebResults': [
        {'Url': 'https://a.example', 'Title': '有效文章', 'Summary': '有效内容',
         'SortId': -60, 'RankScore': value, 'AuthInfoLevel': 'bad', 'PublishTime': {}}]}})
    assert len(docs) == 1
    assert (docs[0].rank, docs[0].rank_score, docs[0].authority, docs[0].publish) == (1, None, None, None)
    assert fusion.rank(fusion.merge(docs), config.DEFAULTS)[0].score > 0


def test_both_providers_use_one_based_array_order():
    a, _ = sources._map_custom({'Result': {'WebResults': [dict(Title=str(i), SortId=10-i) for i in range(3)]}})
    b = sources._map_parallel({'results': [dict(title=str(i)) for i in range(3)]})
    assert [d.rank for d in a] == [d.rank for d in b] == [1, 2, 3]


@pytest.mark.parametrize('fence', ['```', '~~~~'])
def test_code_fences_preserve_navigation_words_and_links(fence):
    body = f'{fence}markdown\n登录\n[Linux](https://a) [Windows](https://b)\n{fence}'
    assert sources.clean_text(body) == body
    assert sources.clean_text('登录\n正文\n[返回顶部](https://a)') == '正文'


@pytest.mark.parametrize('body', [
    '```python\ntext = """a\n\n\nb"""\nother = "a\u200bb"\n```',
    '    text = """a\n\n\n    b"""',
])
def test_code_string_literals_keep_whitespace_and_unicode(body):
    assert sources.clean_text(body) == body


def test_default_dispatch_starts_both_sources_before_waiting(monkeypatch, capsys):
    barrier = threading.Barrier(2)
    def search(source):
        def run(*args, **kwargs):
            barrier.wait(timeout=2)
            return sources.SourceResult(source, docs=[document(source, 1)])
        return run
    monkeypatch.setattr(sources, 'doubao_search', search('doubao'))
    monkeypatch.setattr(sources, 'parallel_search', search('parallel'))
    args = gr_search.build_parser().parse_args(['search', '普通资料查询', '--json', '--no-dump'])
    assert gr_search.run_search(args, copy.deepcopy(config.DEFAULTS)) == 0
    out = json.loads(capsys.readouterr().out)
    assert out['diagnostics']['dispatch'] == 'parallel'
    assert out['diagnostics']['effective_dedup_threshold'] == 1.0
    assert out['diagnostics']['dedup_mode'] == 'exact_body'
    assert all(not v['failed'] for v in out['diagnostics']['sources'].values())
    assert len(out['docs']) == 2
    assert out['session_id']


@pytest.mark.parametrize('argv', [[], ['--force-all'], ['--card-shortcircuit']])
def test_card_shortcircuit_is_explicit(monkeypatch, capsys, argv):
    calls = []
    def doubao(*args, **kwargs):
        calls.append('doubao')
        return sources.SourceResult('doubao', docs=[document('doubao', 1)], cards=[{'CardType':'WeatherCard'}])
    def parallel(*args, **kwargs):
        calls.append('parallel')
        return sources.SourceResult('parallel', docs=[document('parallel', 1)])
    monkeypatch.setattr(sources, 'doubao_search', doubao)
    monkeypatch.setattr(sources, 'parallel_search', parallel)
    args = gr_search.build_parser().parse_args(['search', '天气', '--no-dump', '--json', *argv])
    assert gr_search.run_search(args, copy.deepcopy(config.DEFAULTS)) == 0
    assert set(calls) == ({'doubao'} if argv == ['--card-shortcircuit'] else {'doubao', 'parallel'})


def test_cache_write_is_atomic_for_concurrent_readers_and_writers(tmp_path, monkeypatch):
    target = tmp_path / 'cache.json'
    config.secure_write(target, json.dumps({'old': True}))
    ready = threading.Barrier(3)
    release = threading.Event()
    replace = config.os.replace
    def gated_replace(src, dst):
        ready.wait(timeout=3)
        assert release.wait(3)
        replace(src, dst)
    monkeypatch.setattr(config.os, 'replace', gated_replace)
    values = [{'long': 'x' * 20000}, {'short': True}]
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(config.secure_write, target, json.dumps(v)) for v in values]
        try:
            ready.wait(timeout=3)
            assert json.loads(target.read_text()) == {'old': True}
        finally:
            release.set()
        for f in futures:
            f.result(timeout=3)
    assert json.loads(target.read_text()) in values
    assert target.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.iterdir()) == [target]


def test_failed_replace_preserves_old_cache(tmp_path, monkeypatch):
    target = tmp_path / 'cache.json'
    config.secure_write(target, '{"old": true}')
    def fail(*args):
        raise OSError('simulated replace failure')
    monkeypatch.setattr(config.os, 'replace', fail)
    with pytest.raises(OSError):
        config.secure_write(target, '{"new": true}')
    assert json.loads(target.read_text()) == {'old': True}
    assert list(tmp_path.iterdir()) == [target]


def test_migration_is_previewed_and_preserves_unrelated_settings(tmp_path, monkeypatch):
    path = tmp_path / 'config.json'
    raw = {'card_shortcircuit': True, 'fusion': {'weight_parallel': .7, 'rrf_k': 70},
           'doubao': {'api_key': 'test-sentinel'}, 'output': {'dump_dir': '/custom'}, 'custom': [1, 2]}
    path.write_text(json.dumps(raw))
    monkeypatch.setattr(config, 'CONFIG_PATH', path)
    monkeypatch.setattr(config, 'CONFIG_DIR', tmp_path)
    changes = config.migrate_defaults()
    assert set(changes) == {'card_shortcircuit', 'fusion.weight_parallel'}
    assert json.loads(path.read_text()) == raw
    config.migrate_defaults(apply=True)
    updated = json.loads(path.read_text())
    assert updated['fusion'] == {'weight_doubao': 1., 'weight_parallel': 1., 'rrf_k': 70}
    assert updated['card_shortcircuit'] is False
    for key in ('doubao', 'output', 'custom'):
        assert updated[key] == raw[key]
    assert config.migrate_defaults() == {}
