#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""获取A股正确周涨跌"""
import yfinance as yf, pandas as pd, json

indices = [
    ('000001.SS', '上证指数'),
    ('399001.SZ', '深证成指'),
    ('399006.SZ', '创业板指'),
    ('000300.SS', '沪深300'),
    ('000688.SS', '科创50'),
]

res = {}
for ticker, name in indices:
    df = yf.Ticker(ticker).history(start='2026-04-09', end='2026-04-25')
    df.index = pd.to_datetime(df.index).tz_localize(None)
    df = df.sort_index()
    p10 = float(df.loc['2026-04-10', 'Close'])
    p24 = float(df.loc['2026-04-24', 'Close'])
    pct = round((p24 - p10) / p10 * 100, 2)
    res[name] = {'prev_fri': round(p10, 2), 'this_fri': round(p24, 2), 'pct': pct}
    print(f"{name}: {p10:.2f} -> {p24:.2f} ({pct:+.2f}%)")

with open('data/correct_prices.json', 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
print("Done")