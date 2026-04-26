#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""获取A股正确周涨跌（上周五4月10日 vs 本周五4月24日）"""
import yfinance as yf, pandas as pd, json

indices = [
    ('上证指数', '000001.SS'),
    ('深证成指', '399001.SZ'),
    ('创业板指', '399006.SZ'),
    ('沪深300', '000300.SS'),
    ('科创50', '000688.SS'),
]

res = {}
for name, tk in indices:
    df = yf.Ticker(tk).history(start='2026-04-09', end='2026-04-25')
    df.index = pd.to_datetime(df.index).tz_localize(None)
    p10 = float(df[df.index == '2026-04-10']['Close'].iloc[0])
    p24 = float(df[df.index == '2026-04-24']['Close'].iloc[0])
    pct = (p24 - p10) / p10 * 100
    res[name] = {'prev_fri': round(p10, 2), 'this_fri': round(p24, 2), 'pct': round(pct, 2)}
    print('%s: %.2f -> %.2f (%+.2f%%)' % (name, p10, p24, pct))

with open('data/correct_prices.json', 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print('Saved: data/correct_prices.json')