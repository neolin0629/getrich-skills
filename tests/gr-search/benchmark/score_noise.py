#!/usr/bin/env python3
"""Aggregate blind human labels for every displayed result; no network or auto-labeling."""
import argparse
import json
from pathlib import Path


def score(rows):
    """Rows describe all visible results in one anonymous packet/budget/repeat.

    visible_chars counts the entire visible result block, including metadata.
    Unknown labels must be resolved before scoring, not silently treated as clean.
    """
    seen = set()
    for row in rows:
        if not isinstance(row.get('id'), str) or not row['id'] or row['id'] in seen:
            raise ValueError('Every displayed result needs a unique nonempty id')
        seen.add(row['id'])
        if type(row.get('visible_chars')) is not int or row['visible_chars'] <= 0:
            raise ValueError('visible_chars must be a positive integer')
        if any(type(row.get(key)) is not bool for key in ('relevant', 'stale', 'navigation')):
            raise ValueError('All results need explicit boolean relevance, stale and navigation labels')
    count = len(rows)
    noisy = [r for r in rows if not r['relevant'] or r['stale'] or r['navigation']]
    chars = sum(r['visible_chars'] for r in rows)
    return {
        'displayed_results': count,
        'visible_result_chars': chars,
        'relevance_precision': sum(r['relevant'] for r in rows) / count if count else None,
        'noise_rate': len(noisy) / count if count else None,
        'noisy_result_char_share': sum(r['visible_chars'] for r in noisy) / chars if chars else None,
        'stale_results': sum(r['stale'] for r in rows),
        'navigation_results': sum(r['navigation'] for r in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('labels', type=Path, help='JSON array of labels for all visible result blocks')
    args = parser.parse_args()
    try:
        rows = json.loads(args.labels.read_text(encoding='utf-8'))
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError('Expected a JSON array of result objects')
        report = score(rows)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
