"""Offline checks for evidence pairing, blinding and collection accounting."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('gr_benchmark', Path(__file__).with_name('benchmark.py'))
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)
READER_SPEC = importlib.util.spec_from_file_location('gr_packet_reader', Path(__file__).with_name('read_question.py'))
reader = importlib.util.module_from_spec(READER_SPEC)
READER_SPEC.loader.exec_module(reader)


class BenchmarkTests(unittest.TestCase):
    def test_reader_emits_entire_evidence_and_no_other_question(self):
        evidence = 'prefix\n' * 2000 + 'TAIL: exception is still present.'
        with tempfile.TemporaryDirectory() as directory:
            packet = Path(directory) / 'packet.json'
            packet.write_text(json.dumps({'questions': [
                {'id': 'C1', 'question': 'Limits?', 'evidence': evidence},
                {'id': 'C2', 'question': 'Do not emit this question', 'evidence': 'unrelated'},
            ]}))
            output = reader.emit_question(packet, 0)
            self.assertIn(evidence, output)
            self.assertTrue(output.splitlines()[-1].startswith('END_INPUT id=C1 chars='))
            self.assertNotIn('Do not emit this question', output)
            with self.assertRaises(ValueError):
                reader.emit_question(packet, -1)

    def test_question_set_preserves_pilot_and_balances_categories(self):
        questions = benchmark.question_set(benchmark.HERE / 'questions.json')
        self.assertEqual(len(questions), 32)
        self.assertEqual(set(benchmark.collections.Counter(q['category'] for q in questions).values()), {8})
        self.assertTrue(set(('C1', 'C2', 'E1', 'E2', 'T1', 'T2', 'D1', 'D2')) <= {q['id'] for q in questions})

    def test_cross_balanced_identities_and_repeat_swap(self):
        questions = benchmark.question_set(benchmark.HERE / 'questions.json')
        maps = benchmark.assignments(questions, 3, 42)
        self.assertEqual(maps, benchmark.assignments(questions, 3, 42))
        for category in {q['category'] for q in questions}:
            ids = [q['id'] for q in questions if q['category'] == category]
            for mapping in maps:
                self.assertEqual(sum(mapping[qid]['A'] == 'baseline' for qid in ids), 4)
                self.assertTrue(all(mapping[qid]['A'] != mapping[qid]['B'] for qid in ids))
        for q in questions:
            self.assertNotEqual(maps[0][q['id']]['A'], maps[1][q['id']]['A'])

    def test_packets_never_include_checks_references_or_version_labels(self):
        questions = benchmark.question_set(benchmark.HERE / 'questions.json', ['C1', 'C2'])
        rendered = {version: {q['id']: {'outputs': {'8000': {'evidence': 'same safe evidence'}}}
                              for q in questions} for version in ('baseline', 'candidate')}
        raws = {q['id']: {'timestamp': '2026-09-10T01:00:00+08:00'} for q in questions}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            benchmark.build_packets(questions, rendered, raws, [8000], 2, 9, root)
            packets = list((root / 'packets').glob('*.json'))
            self.assertEqual(len(packets), 4)
            for packet in packets:
                text = packet.read_text()
                for forbidden in ('reference_urls', 'checks', 'baseline', 'candidate', 'objective'):
                    self.assertNotIn(forbidden, text)
                self.assertEqual({q['id'] for q in json.loads(text)['questions']}, {'C1', 'C2'})
            self.assertTrue((root / 'private' / 'mapping.json').is_file())

    def test_historical_failed_or_cached_source_is_not_a_fresh_pair(self):
        raw = {'raw': {'doubao': {}, 'parallel': {}}, 'timestamp': '2026-09-10T00:00:00',
               'diagnostics': {'sources': {'doubao': {'cached': False, 'failed': False},
                                            'parallel': {'cached': True, 'failed': False}}}}
        self.assertFalse(benchmark.historical_collection(raw, 'C1')['paired_sources_ok'])
        raw['diagnostics']['sources']['parallel'].update(cached=False, failed=True)
        self.assertFalse(benchmark.historical_collection(raw, 'C1')['paired_sources_ok'])
        raw['diagnostics']['sources']['parallel']['failed'] = False
        self.assertTrue(benchmark.historical_collection(raw, 'C1')['paired_sources_ok'])

    def test_default_without_raw_cannot_collect(self):
        with patch.object(benchmark, 'worker') as worker, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                benchmark.main(['--baseline-scripts', '/missing', '--candidate-scripts', '/missing'])
        self.assertEqual(error.exception.code, 2)
        worker.assert_not_called()

    def test_collect_forces_both_sources_disables_cache_and_counts_actual_invocations(self):
        question = benchmark.question_set(benchmark.HERE / 'questions.json', ['C1'])[0]
        observed = {}
        defaults = {'cache': {'enabled': True}, 'card_shortcircuit': True,
                    'parallel': {'enabled': False}, 'output': {}}
        fake_config = types.SimpleNamespace(load_config=lambda: benchmark.copy.deepcopy(defaults))
        result = types.SimpleNamespace(cached=False, error=None, docs=[{}], warnings=[])
        fake_sources = types.SimpleNamespace(doubao_search=lambda *a: result, parallel_search=lambda *a: result)
        class Parser:
            def parse_args(self, argv):
                observed['argv'] = argv
                return object()
        with tempfile.TemporaryDirectory() as directory:
            raw_path = Path(directory) / 'raw.json'
            raw_path.write_text(json.dumps({'timestamp': '2026-09-10T00:00:00',
                                            'raw': {'doubao': {}, 'parallel': {}}}))
            def search(args, cfg):
                observed['cfg'] = cfg
                fake_sources.doubao_search(cfg)
                fake_sources.parallel_search(cfg)
                print(json.dumps({'dump': str(raw_path)}))
                return 0
            fake_search = types.SimpleNamespace(build_parser=Parser, run_search=search)
            with patch.dict('sys.modules', {'config': fake_config, 'sources': fake_sources, 'gr_search': fake_search}):
                data = benchmark._collect({'question': question, 'dump_dir': directory})
        self.assertFalse(observed['cfg']['cache']['enabled'])
        self.assertFalse(observed['cfg']['card_shortcircuit'])
        self.assertTrue(observed['cfg']['parallel']['enabled'])
        self.assertIn('--force-all', observed['argv'])
        self.assertIn('--no-cache', observed['argv'])
        self.assertEqual(data['collection']['logical_source_calls'], {'doubao': 1, 'parallel': 1})
        self.assertTrue(data['collection']['paired_sources_ok'])
        self.assertIsNone(data['collection']['billing_cost'])

    def test_replay_worker_blocks_transport_and_uses_full_selection_query(self):
        # Fake modules try socket/child-process transports during render. The worker
        # must block both, while old signatures still work in the integration run.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config.py').write_text("DEFAULTS={'fusion': {'dedup_jaccard': .9}}\n")
            (root / 'sources.py').write_text('def _map_custom(body): return [], []\ndef _map_parallel(body): return []\n')
            (root / 'fusion.py').write_text('def is_strong_fresh_query(q): return False\ndef is_fresh_query(q): return False\ndef merge(docs, threshold): return docs\ndef rank(docs, cfg, **kw): return docs\n')
            (root / 'render.py').write_text('''import socket, subprocess, datetime

def _assemble(selection_query=None): pass

def render(**kwargs):
    for f, args in ((socket.create_connection, (('127.0.0.1', 80),)), (subprocess.Popen, (['echo', 'unsafe'],))):
        try: f(*args)
        except RuntimeError: pass
        else: raise AssertionError('offline transport allowed')
    assert kwargs['query'] == 'full question'
    assert kwargs['selection_query'] == 'full question objective keyword'
    assert str(datetime.date.today()) == '2020-01-02'
    return 'safe evidence'
''')
            data = benchmark.worker(root, 'replay', {'raw': {'timestamp': '2020-01-02T00:00:00', 'raw': {}},
                'question': {'id': 'X1', 'question': 'full question', 'q': 'short', 'objective': 'objective', 'pq': ['keyword']},
                'budgets': [8000]})
        self.assertEqual(data['source_call_count'], 0)
        self.assertEqual(data['outputs']['8000']['visible_chars'], len('safe evidence'))


if __name__ == '__main__':
    unittest.main()
