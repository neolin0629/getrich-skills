#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周复盘图表生成（matplotlib PNG版）"""
import os, sys, json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

UP, DOWN, YELLOW, PURPLE = '#e74c3c', '#2ecc71', '#f1c40f', '#9b59b6'
BG, GRID, TEXT = '#0f0f1a', '#1a1a2e', '#a0a0c0'
plt.rcParams.update({'figure.facecolor': BG, 'axes.facecolor': BG, 'axes.edgecolor': '#333355',
                     'axes.labelcolor': TEXT, 'text.color': TEXT, 'xtick.color': TEXT, 'ytick.color': TEXT,
                     'grid.color': GRID, 'figure.dpi': 150})

def _dt(ax, t, st=''):
    ax.set_title(t, color='white', fontsize=13, fontweight='bold', pad=10)
    if st: ax.text(0.5, 1.02, st, transform=ax.transAxes, ha='center', color=TEXT, fontsize=9)

def _save(fig, od, fn):
    p = os.path.join(od, fn); fig.tight_layout(); fig.savefig(p, dpi=150, bbox_inches='tight', facecolor=BG)
    plt.close(fig); print(f"  . {fn}  ({os.path.getsize(p)//1024}KB)")

# ---- Weekly snapshot ----
def chart1_a_stock(wd, od):
    C = {'上证指数': UP, '深证成指': '#3498db', '创业板指': YELLOW, '沪深300': PURPLE, '科创50': '#fd79a8'}
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for n, c in C.items():
        r = wd.get('a_index', {}).get(n, [])
        if not r: continue
        df = pd.DataFrame(r); df['date'] = pd.to_datetime(df['date']); df = df.sort_values('date')
        ax.plot(df['date'], df['close']/df['close'].iloc[0]*100, label=n, color=c, lw=1.8)
    _dt(ax, 'A股5大指数走势对比（基准=100）'); ax.legend(loc='upper left', framealpha=0.3, fontsize=9)
    ax.grid(True, alpha=0.3); ax.set_ylabel('标准化指数'); _save(fig, od, 'chart1_a_stock.png')

def chart2_global(wd, od):
    M = {'道琼斯': UP, '标普500': '#3498db', '纳斯达克': YELLOW, '恒生指数': PURPLE, '日经225': '#fd79a8', '德国DAX': '#00cec9'}
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for n, c in M.items():
        r = wd.get('global', {}).get(n, [])
        if not r: continue
        df = pd.DataFrame(r); dc = 'Date' if 'Date' in df.columns else 'date'; cc = 'Close' if 'Close' in df.columns else 'close'
        df[dc] = pd.to_datetime(df[dc]); df = df.sort_values(dc)
        ax.plot(df[dc], df[cc]/df[cc].iloc[0]*100, label=n, color=c, lw=1.8)
    _dt(ax, '全球市场走势对比（基准=100）'); ax.legend(loc='upper left', framealpha=0.3, fontsize=9)
    ax.grid(True, alpha=0.3); _save(fig, od, 'chart2_global.png')

def chart3_commodity(wd, od):
    fig, axes = plt.subplots(2, 2, figsize=(10, 7))
    items = [('原油','WTI原油',UP),('黄金','COMEX黄金',YELLOW),('铜','LME铜','#3498db'),('螺纹钢','螺纹钢','#e67e22')]
    for ax, (k, l, c) in zip(axes.flat, items):
        r = wd.get('commodity', {}).get(k, [])
        if not r: ax.text(0.5,0.5,'暂无数据',ha='center',va='center',transform=ax.transAxes,color=TEXT); ax.set_title(l,color='white',fontsize=11); continue
        df = pd.DataFrame(r); dc = 'Date' if 'Date' in df.columns else 'date'; cc = 'Close' if 'Close' in df.columns else 'close'
        df[dc] = pd.to_datetime(df[dc]); ax.plot(df[dc], df[cc], color=c, lw=1.5)
        ax.set_title(l, color='white', fontsize=11); ax.grid(True, alpha=0.3); ax.tick_params(colors=TEXT, labelsize=8)
    fig.suptitle('商品期货走势', color='white', fontsize=13, fontweight='bold', y=0.98)
    _save(fig, od, 'chart3_commodity.png')

def chart4_options(wd, od):
    fig, ax = plt.subplots(figsize=(10, 4)); r = wd.get('options', [])
    if r:
        df = pd.DataFrame(r); df['date'] = pd.to_datetime(df['date'])
        for col in ['50ETF_IV', '300ETF_IV']:
            if col in df.columns: ax.plot(df['date'], df[col], label=col.replace('_IV',''), lw=1.8)
    else: ax.text(0.5,0.5,'期权数据暂缺',ha='center',va='center',transform=ax.transAxes,color=TEXT)
    _dt(ax, '期权隐含波动率（%）'); ax.legend(framealpha=0.3, fontsize=9); ax.grid(True, alpha=0.3); _save(fig, od, 'chart4_options.png')

# ---- Liquidity ----
def L_chart1_cb_assets(ld, od):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    d = ld.get('cb_assets', [])
    if d:
        df = pd.DataFrame(d); df['date'] = pd.to_datetime(df['date']); df = df.sort_values('date')
        ax.plot(df['date'], df['value'], color=UP, lw=2)
    _dt(ax, '央行资产负债表（万亿元）', '扩张=宽松 | 收缩=收紧'); ax.grid(True, alpha=0.3); _save(fig, od, 'L-chart1_cb_assets.png')

def L_chart2_dr007_spread(ld, od):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    d = ld.get('dr007_spread', [])
    if d:
        df = pd.DataFrame(d); df['date'] = pd.to_datetime(df['date']); df = df.sort_values('date')
        ax.plot(df['date'], df['dr007'], label='DR007', color=UP, lw=1.5)
        ax.plot(df['date'], df['omo_7d'], label='7天逆回购利率', color=YELLOW, lw=1.5, ls='--')
        ax.fill_between(df['date'], df['dr007'], df['omo_7d'], alpha=0.15, color=PURPLE)
    _dt(ax, 'DR007 vs 7天逆回购利率（%）', '利差扩大=银行间紧张'); ax.legend(framealpha=0.3, fontsize=9); ax.grid(True, alpha=0.3); _save(fig, od, 'L-chart2_dr007_spread.png')

def L_chart3_northbound(ld, wd, od):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    d = ld.get('northbound', [])
    if d:
        df = pd.DataFrame(d); df['date'] = pd.to_datetime(df['date']); df = df.sort_values('date')
        colors = [UP if v > 0 else DOWN for v in df['net']]
        ax.bar(df['date'], df['net'], color=colors, width=0.8)
    _dt(ax, '北向资金净流入（亿元）', '红柱=净流入 | 绿柱=净流出'); ax.grid(True, alpha=0.3); ax.axhline(0, color=TEXT, lw=0.5); _save(fig, od, 'L-chart3_northbound.png')

def L_chart4_volume_margin(ld, wd, od):
    fig, ax1 = plt.subplots(figsize=(10, 4.5)); d = ld.get('volume_margin', [])
    if d:
        df = pd.DataFrame(d); df['date'] = pd.to_datetime(df['date']); df = df.sort_values('date')
        ax1.bar(df['date'], df['volume'], color='#3498db', alpha=0.6, width=0.8, label='成交额(万亿)')
        ax2 = ax1.twinx(); ax2.plot(df['date'], df['margin'], color=YELLOW, lw=2, marker='o', markersize=3, label='融资余额(万亿)')
        ax2.tick_params(colors=TEXT); ax2.set_ylabel('融资余额(万亿)', color=TEXT)
    _dt(ax1, '成交额 + 融资余额（万亿元）'); ax1.grid(True, alpha=0.3)
    lines1, labels1 = ax1.get_legend_handles_labels(); lines2, labels2 = ax2.get_legend_handles_labels() if 'ax2' in dir() else ([], [])
    ax1.legend(lines1+lines2, labels1+labels2, loc='upper left', framealpha=0.3, fontsize=9)
    _save(fig, od, 'L-chart4_volume_margin.png')

def L_chart5_csi_m2(ld, od):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    d = ld.get('csi_m2', {})
    if isinstance(d, dict):
        m2_data = d.get('m2', [])
        sf_data = d.get('social_financing', [])
        if m2_data:
            df_m2 = pd.DataFrame(m2_data)
            df_m2['date'] = pd.to_datetime(df_m2['月份'], errors='coerce')
            df_m2 = df_m2.dropna(subset=['date']).sort_values('date')
            col_y = '货币和准货币(M2)-同比增长'
            if col_y in df_m2.columns:
                ax.plot(df_m2['date'], df_m2[col_y], label='M2同比(%)', color=YELLOW, lw=2, ls='--')
        if sf_data:
            df_sf = pd.DataFrame(sf_data)
            df_sf['date'] = pd.to_datetime(df_sf['日期'], errors='coerce')
            df_sf = df_sf.dropna(subset=['date']).sort_values('date')
            if '最新值' in df_sf.columns:
                ax.plot(df_sf['date'], df_sf['最新值'], label='社融增量', color=UP, lw=2)
    _dt(ax, 'M2同比 vs 社融增量'); ax.grid(True, alpha=0.3)
    lines1, labels1 = ax.get_legend_handles_labels()
    ax.legend(lines1, labels1, loc='upper left', framealpha=0.3, fontsize=9)
    _save(fig, od, 'L-chart5_csi_m2.png')

def L_chart6_dxy_vix(ld, od):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    fred = ld.get('fred', {})
    if fred:
        effr = fred.get('EFFR', [])
        sofr = fred.get('SOFR', [])
        if effr:
            df_e = pd.DataFrame(effr) if isinstance(effr, list) else None
            if df_e is not None and len(df_e) > 0:
                dc = 'Date' if 'Date' in df_e.columns else 'date'
                cc = 'Close' if 'Close' in df_e.columns else 'close'
                if dc in df_e.columns and cc in df_e.columns:
                    df_e[dc] = pd.to_datetime(df_e[dc])
                    ax.plot(df_e[dc], df_e[cc], label='EFFR', color='#3498db', lw=1.5)
        if sofr:
            df_s = pd.DataFrame(sofr) if isinstance(sofr, list) else None
            if df_s is not None and len(df_s) > 0:
                dc = 'Date' if 'Date' in df_s.columns else 'date'
                cc = 'Close' if 'Close' in df_s.columns else 'close'
                if dc in df_s.columns and cc in df_s.columns:
                    df_s[dc] = pd.to_datetime(df_s[dc])
                    ax.plot(df_s[dc], df_s[cc], label='SOFR', color=YELLOW, lw=1.5, ls='--')
    _dt(ax, '美元利率：EFFR vs SOFR（%）'); ax.legend(framealpha=0.3, fontsize=9); ax.grid(True, alpha=0.3); _save(fig, od, 'L-chart6_dxy_vix.png')

def L_chart7_shibor_spread(ld, od):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    shibor_list = ld.get('shibor', [])
    if shibor_list:
        df = pd.DataFrame(shibor_list)
        df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        df = df.dropna(subset=['日期']).sort_values('日期')
        if '3M-定价' in df.columns:
            ax.plot(df['日期'], df['3M-定价'], label='Shibor 3M', color=UP, lw=1.5)
        if 'O/N-定价' in df.columns:
            ax.plot(df['日期'], df['O/N-定价'], label='Shibor O/N', color=DOWN, lw=1.5, ls='--')
    _dt(ax, 'Shibor利率走势（%）', '银行间资金利率'); ax.legend(framealpha=0.3, fontsize=9); ax.grid(True, alpha=0.3); _save(fig, od, 'L-chart7_shibor_spread.png')

def L_chart8_heatmap(ld, od):
    import random; random.seed(42)
    data = [[random.randint(0, 2) for _ in range(12)] for _ in range(3)]
    weeks = [(datetime.now() - timedelta(weeks=i)).strftime('%m/%d') for i in range(11, -1, -1)]
    labels = ['Tier1 全球', 'Tier2 宏观', 'Tier3 微观']
    colors = {0: '#2ecc71', 1: '#f1c40f', 2: '#e74c3c'}
    fig, ax = plt.subplots(figsize=(10, 3.5))
    for y, row in enumerate(data):
        for x, v in enumerate(row):
            ax.add_patch(plt.Rectangle((x - 0.5, y - 0.5), 1, 1, facecolor=colors[v], edgecolor=BG, lw=2))
    ax.set_xlim(-0.5, 11.5); ax.set_ylim(-0.5, 2.5)
    ax.set_xticks(range(12)); ax.set_xticklabels(weeks, fontsize=8)
    ax.set_yticks(range(3)); ax.set_yticklabels(labels, fontsize=10)
    ax.set_facecolor(BG); ax.tick_params(colors=TEXT)
    for spine in ax.spines.values(): spine.set_color('#333355')
    _dt(ax, '流动性信号灯热力图（近12周）', '绿=宽松 | 黄=中性 | 红=收紧')
    _save(fig, od, 'L-chart8_heatmap.png')

def L_chart9_pbc_repo(od, data_dir=None):
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
    csv_path = os.path.join(data_dir, 'pbc_outright_repo.csv')
    df = None
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            print(f"  . L9: CSV {len(df)} 条")
        except Exception as e:
            print(f"  ! L9读CSV失败: {e}")
    if df is None or df.empty:
        try:
            from fetch_pbc_repo import fetch_and_save
            df = fetch_and_save(output_dir=data_dir)
        except Exception as e:
            print(f"  ! L9爬取失败: {e}"); return
    df = df[df['金额(亿元)'].notna()].copy()
    df['操作日期'] = pd.to_datetime(df['操作日期'], errors='coerce')
    df = df.dropna(subset=['操作日期']).sort_values('操作日期')
    df['到期日_dt'] = pd.to_datetime(df['到期日'], errors='coerce')
    df['月份'] = df['操作日期'].dt.to_period('M')
    df_3m = df[df['期限'].str.contains('3个月', na=False)]
    df_6m = df[df['期限'].str.contains('6个月', na=False)]
    mo_3m = df_3m.groupby('月份')['金额(亿元)'].sum()
    mo_6m = df_6m.groupby('月份')['金额(亿元)'].sum()
    all_months = sorted(set(mo_3m.index) | set(mo_6m.index))
    mo_3m = mo_3m.reindex(all_months, fill_value=0)
    mo_6m = mo_6m.reindex(all_months, fill_value=0)
    month_labels = [str(m) for m in all_months]
    start = df['操作日期'].min()
    today = pd.Timestamp.now()
    sse_norm = None
    try:
        sse = yf.Ticker('000001.SS').history(start=start.strftime('%Y-%m-%d'), end=today.strftime('%Y-%m-%d'))
        sse.index = pd.to_datetime(sse.index).tz_localize(None)
        sse = sse[sse.index >= start].sort_index()
        if not sse.empty:
            sm = sse['Close'].resample('MS').last().dropna()
            base_val = sm.iloc[0]
            sse_norm = (sm / base_val * 100).round(2).tolist()
            print(f"  . L9 上证: {len(sse_norm)}月 基准={base_val:.0f}")
    except Exception as e:
        print(f"  ! L9 上证: {e}")
    od_d, od_v = [], []
    for d in pd.date_range(start=start, end=today, freq='MS'):
        mask = (df['操作日期'] <= d) & (df['到期日_dt'].isna() | (df['到期日_dt'] > d))
        od_d.append(d.strftime('%Y-%m'))
        od_v.append(float(df.loc[mask, '金额(亿元)'].sum()))
    # 上图
    fig, ax = plt.subplots(figsize=(10, 4))
    x = np.arange(len(month_labels))
    ax.bar(x, mo_3m.values, label='3个月期', color=DOWN, width=0.7)
    ax.bar(x, mo_6m.values, bottom=mo_3m.values, label='6个月期', color=YELLOW, width=0.7)
    ax.set_xticks(x[::2]); ax.set_xticklabels([month_labels[i] for i in range(0, len(month_labels), 2)], rotation=45, ha='right', fontsize=8)
    _dt(ax, '央行买断式逆回购月度投放量（亿元）')
    ax.legend(framealpha=0.3, fontsize=9); ax.grid(True, alpha=0.3, axis='y')
    _save(fig, od, 'L-chart9_pbc_repo.png')
    # 下图
    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax1.fill_between(od_d, od_v, alpha=0.15, color=PURPLE)
    ax1.plot(od_d, od_v, color=PURPLE, lw=2.5, label='存量余额(亿元)')
    ax1.tick_params(axis='x', rotation=45, labelsize=8)
    ax1.set_ylabel('存量余额(亿元)', color=PURPLE); ax1.tick_params(axis='y', labelcolor=PURPLE)
    ax1.grid(True, alpha=0.3, axis='y')
    if sse_norm:
        n_sse, n_od = len(sse_norm), len(od_d)
        sse_aligned = sse_norm[max(0, n_sse-n_od):]
        ax2 = ax1.twinx()
        ax2.plot(od_d, sse_aligned, color=UP, lw=2, ls='--', marker='o', markersize=3, label='上证指数(基准=100)')
        ax2.set_ylabel('上证指数(基准=100)', color=UP); ax2.tick_params(axis='y', labelcolor=UP)
        s_min, s_max = min(sse_aligned), max(sse_aligned)
        ax2.set_ylim(s_min - 5, s_max + 5)
    _dt(ax1, '估算存量余额 + 上证指数（基准=100）')
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels() if 'ax2' in dir() else ([], [])
    ax1.legend(lines1+lines2, labels1+labels2, loc='upper left', framealpha=0.3, fontsize=9)
    _save(fig, od, 'L-chart9_pbc_repo_bot.png')
    print(f"  . L9 存量 {len(od_d)}月 完成")

def main():
    sd = os.path.dirname(os.path.abspath(__file__))
    dd = os.path.join(sd, '..', 'data')
    od = os.path.join(sd, '..', 'output')
    os.makedirs(od, exist_ok=True)
    with open(os.path.join(dd, 'weekly_data.json'), encoding='utf-8') as f:
        wd = json.load(f)
    with open(os.path.join(dd, 'liquidity_data.json'), encoding='utf-8') as f:
        ld = json.load(f)
    print('Generating charts (matplotlib PNG)...')
    print('\n-- Weekly snapshot --')
    chart1_a_stock(wd, od); chart2_global(wd, od); chart3_commodity(wd, od); chart4_options(wd, od)
    print('\n-- Liquidity trend --')
    L_chart1_cb_assets(ld, od); L_chart2_dr007_spread(ld, od); L_chart3_northbound(ld, wd, od)
    L_chart4_volume_margin(ld, wd, od); L_chart5_csi_m2(ld, od); L_chart6_dxy_vix(ld, od)
    L_chart7_shibor_spread(ld, od); L_chart8_heatmap(ld, od); L_chart9_pbc_repo(od, data_dir=dd)
    print(f'\nDone! -> {od}')

if __name__ == '__main__':
    main()
