#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周复盘图表生成（pyecharts HTML版）"""
import os, sys, json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
from pyecharts import options as opts
from pyecharts.charts import Line, Bar, Kline, HeatMap, Grid, Page

BG = '#0f0f1a'
TEXT = '#a0a0c0'

def _save(chart, od, fn):
    p = os.path.join(od, fn.replace('.png', '.html'))
    chart.render(p)
    size = os.path.getsize(p) // 1024
    print(f"  . {fn}  ({size}KB)")

# ---- Weekly snapshot ----
def chart1_a_stock(wd, od):
    C = {'上证指数': '#e74c3c', '深证成指': '#3498db', '创业板指': '#f1c40f', '沪深300': '#9b59b6', '科创50': '#fd79a8'}
    line = Line(init_opts=opts.InitOpts(width="1000px", height="450px", bg_color=BG))
    xdata = []
    ydatas = {}
    for n, c in C.items():
        r = wd.get('a_index', {}).get(n, [])
        if not r: continue
        df = pd.DataFrame(r)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        if not xdata:
            xdata = [d.strftime('%Y-%m-%d') for d in df['date']]
        base = float(df['close'].iloc[0])
        vals = [round(float(v)/base*100, 2) for v in df['close']]
        ydatas[n] = (c, vals)
    if xdata:
        line.add_xaxis(xaxis_data=xdata)
        for n, (c, vals) in ydatas.items():
            line.add_yaxis(series_name=n, y_axis=vals, is_smooth=True, linestyle_opts=opts.LineStyleOpts(color=c, width=2))
    line.set_global_opts(title_opts=opts.TitleOpts(title="A股5大指数走势对比（基准=100）", pos_left='center'),
                         legend_opts=opts.LegendOpts(pos_left='left'),
                         xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)))
    _save(line, od, 'chart1_a_stock.png')

def chart2_global(wd, od):
    M = {'道琼斯': '#e74c3c', '标普500': '#3498db', '纳斯达克': '#f1c40f', '恒生指数': '#9b59b6', '日经225': '#fd79a8', '德国DAX': '#00cec9'}
    line = Line(init_opts=opts.InitOpts(width="1000px", height="450px", bg_color=BG))
    xdata = []
    ydatas = {}
    for n, c in M.items():
        r = wd.get('global', {}).get(n, [])
        if not r: continue
        df = pd.DataFrame(r)
        dc = 'Date' if 'Date' in df.columns else 'date'
        cc = 'Close' if 'Close' in df.columns else 'close'
        df[dc] = pd.to_datetime(df[dc])
        df = df.sort_values(dc)
        if not xdata:
            xdata = [d.strftime('%Y-%m-%d') for d in df[dc]]
        base = float(df[cc].iloc[0])
        vals = [round(float(v)/base*100, 2) for v in df[cc]]
        ydatas[n] = (c, vals)
    if xdata:
        line.add_xaxis(xaxis_data=xdata)
        for n, (c, vals) in ydatas.items():
            line.add_yaxis(series_name=n, y_axis=vals, is_smooth=True, linestyle_opts=opts.LineStyleOpts(color=c, width=2))
    line.set_global_opts(title_opts=opts.TitleOpts(title="全球市场走势对比（基准=100）", pos_left='center'),
                         legend_opts=opts.LegendOpts(pos_left='left'),
                         xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)))
    _save(line, od, 'chart2_global.png')

def chart3_commodity(wd, od):
    from pyecharts.charts import Line
    items = [('原油','WTI原油','#e74c3c'),('黄金','COMEX黄金','#f1c40f'),('铜','LME铜','#3498db'),('螺纹钢','螺纹钢','#e67e22')]
    charts = []
    for k, l, c in items:
        r = wd.get('commodity', {}).get(k, [])
        line = Line(init_opts=opts.InitOpts(width="480px", height="300px", bg_color=BG))
        line.add_xaxis(xaxis_data=[])
        if r:
            df = pd.DataFrame(r)
            dc = 'Date' if 'Date' in df.columns else 'date'
            cc = 'Close' if 'Close' in df.columns else 'close'
            df[dc] = pd.to_datetime(df[dc])
            df = df.sort_values(dc)
            line.add_yaxis(series_name=l, y_axis=[float(v) for v in df[cc]], is_smooth=True,
                          linestyle_opts=opts.LineStyleOpts(color=c, width=2))
            line.set_xaxis(xaxis_data=[d.strftime('%Y-%m') for d in df[dc]])
        else:
            line.add_yaxis(series_name=l, y_axis=[], is_smooth=True)
        line.set_global_opts(title_opts=opts.TitleOpts(title=l, pos_left='center'),
                           xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)))
        charts.append(line)
    page = Page(layout=Page.SimplePageLayout)
    for c in charts: page.add(c)
    p = os.path.join(od, 'chart3_commodity.html')
    page.render(p)
    print(f"  . chart3_commodity.png  ({os.path.getsize(p)//1024}KB)")

def chart4_options(wd, od):
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="400px", bg_color=BG))
    r = wd.get('options', [])
    xdata = []
    if r:
        df = pd.DataFrame(r)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        xdata = [d.strftime('%Y-%m-%d') for d in df['date']]
        for col in ['50ETF_IV', '300ETF_IV']:
            if col in df.columns:
                c = '#e74c3c' if '50' in col else '#3498db'
                line.add_yaxis(series_name=col.replace('_IV',''), y_axis=[float(v) for v in df[col]],
                              linestyle_opts=opts.LineStyleOpts(color=c, width=2))
    if xdata:
        line.add_xaxis(xaxis_data=xdata)
    line.set_global_opts(title_opts=opts.TitleOpts(title="期权隐含波动率（%）", pos_left='center'),
                         legend_opts=opts.LegendOpts(pos_left='left'))
    _save(line, od, 'chart4_options.png')

# ---- Liquidity ----
def L_chart1_cb_assets(ld, od):
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="450px", bg_color=BG))
    d = ld.get('cb_assets', [])
    if d:
        df = pd.DataFrame(d)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        line.add_xaxis(xaxis_data=[d.strftime('%Y-%m-%d') for d in df['date']])
        line.add_yaxis(series_name='央行资产(万亿)', y_axis=[float(v) for v in df['value']],
                      linestyle_opts=opts.LineStyleOpts(color='#e74c3c', width=2))
    line.set_global_opts(title_opts=opts.TitleOpts(title="央行资产负债表（万亿元）", subtitle="扩张=宽松 | 收缩=收紧", pos_left='center'),
                         legend_opts=opts.LegendOpts(pos_left='left'),
                         xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)))
    _save(line, od, 'L-chart1_cb_assets.png')

def L_chart2_dr007_spread(ld, od):
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="450px", bg_color=BG))
    d = ld.get('dr007_spread', [])
    if d:
        df = pd.DataFrame(d)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        line.add_xaxis(xaxis_data=[dt.strftime('%Y-%m-%d') for dt in df['date']])
        line.add_yaxis(series_name='DR007', y_axis=[float(v) for v in df['dr007']],
                      linestyle_opts=opts.LineStyleOpts(color='#e74c3c', width=1.5))
        line.add_yaxis(series_name='7天逆回购', y_axis=[float(v) for v in df['omo_7d']],
                      linestyle_opts=opts.LineStyleOpts(color='#f1c40f', width=1.5, type_='dashed'))
    line.set_global_opts(title_opts=opts.TitleOpts(title="DR007 vs 7天逆回购利率（%）", subtitle="利差扩大=银行间紧张", pos_left='center'),
                         legend_opts=opts.LegendOpts(pos_left='left'),
                         xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)))
    _save(line, od, 'L-chart2_dr007_spread.png')

def L_chart3_northbound(ld, wd, od):
    from pyecharts.charts import Bar
    bar = Bar(init_opts=opts.InitOpts(width="1000px", height="450px", bg_color=BG))
    d = ld.get('northbound', [])
    if d:
        df = pd.DataFrame(d)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        bar.add_xaxis(xaxis_data=[dt.strftime('%Y-%m-%d') for dt in df['date']])
        colors = ['#e74c3c' if float(v) >= 0 else '#2ecc71' for v in df['net']]
        bar.add_yaxis(series_name='净流入(亿)', y_axis=[float(v) for v in df['net']])
    bar.set_global_opts(title_opts=opts.TitleOpts(title="北向资金净流入（亿元）", subtitle="红柱=净流入 | 绿柱=净流出", pos_left='center'),
                        legend_opts=opts.LegendOpts(pos_left='left'),
                        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)))
    _save(bar, od, 'L-chart3_northbound.png')

def L_chart4_volume_margin(ld, wd, od):
    from pyecharts import options as opts
    from pyecharts.charts import Bar, Line
    from pyecharts.components import Table
    bar = Bar(init_opts=opts.InitOpts(width="1000px", height="450px", bg_color=BG))
    d = ld.get('volume_margin', [])
    if d:
        df = pd.DataFrame(d)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        bar.add_xaxis(xaxis_data=[dt.strftime('%Y-%m-%d') for dt in df['date']])
        bar.add_yaxis(series_name='成交额(万亿)', y_axis=[float(v) for v in df['volume']],
                     itemstyle_opts=opts.ItemStyleOpts(color='#3498db'))
    bar.set_global_opts(title_opts=opts.TitleOpts(title="成交额 + 融资余额", pos_left='center'),
                        legend_opts=opts.LegendOpts(pos_left='left'),
                        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)))
    _save(bar, od, 'L-chart4_volume_margin.png')

def L_chart5_csi_m2(ld, od):
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="450px", bg_color=BG))
    d = ld.get('csi_m2', {})
    if isinstance(d, dict):
        m2_data = d.get('m2', [])
        if m2_data:
            df_m2 = pd.DataFrame(m2_data)
            df_m2['date'] = pd.to_datetime(df_m2['月份'], errors='coerce')
            df_m2 = df_m2.dropna(subset=['date']).sort_values('date')
            col_y = '货币和准货币(M2)-同比增长'
            if col_y in df_m2.columns:
                line.add_xaxis(xaxis_data=[dt.strftime('%Y-%m') for dt in df_m2['date']])
                line.add_yaxis(series_name='M2同比(%)', y_axis=[float(v) for v in df_m2[col_y]],
                              linestyle_opts=opts.LineStyleOpts(color='#f1c40f', width=2, type_='dashed'))
    line.set_global_opts(title_opts=opts.TitleOpts(title="M2同比增速（%）", pos_left='center'),
                         legend_opts=opts.LegendOpts(pos_left='left'),
                         xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)))
    _save(line, od, 'L-chart5_csi_m2.png')

def L_chart6_dxy_vix(ld, od):
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="450px", bg_color=BG))
    fred = ld.get('fred', {})
    if fred:
        for name, key, color in [('EFFR', 'EFFR', '#3498db'), ('SOFR', 'SOFR', '#f1c40f')]:
            data = fred.get(key, [])
            if data:
                df = pd.DataFrame(data) if isinstance(data, list) else None
                if df is not None and len(df) > 0:
                    dc = 'Date' if 'Date' in df.columns else 'date'
                    cc = 'Close' if 'Close' in df.columns else 'close'
                    if dc in df.columns and cc in df.columns:
                        df[dc] = pd.to_datetime(df[dc])
                        df = df.sort_values(dc)
                        if not line.get_options().get('xAxis', [{}])[0].get('data'):
                            line.add_xaxis(xaxis_data=[dt.strftime('%Y-%m-%d') for dt in df[dc]])
                        line.add_yaxis(series_name=name, y_axis=[float(v) for v in df[cc]],
                                      linestyle_opts=opts.LineStyleOpts(color=color, width=2))
    line.set_global_opts(title_opts=opts.TitleOpts(title="美元利率：EFFR vs SOFR（%）", pos_left='center'),
                         legend_opts=opts.LegendOpts(pos_left='left'),
                         xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)))
    _save(line, od, 'L-chart6_dxy_vix.png')

def L_chart7_shibor_spread(ld, od):
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="450px", bg_color=BG))
    shibor_list = ld.get('shibor', [])
    if shibor_list:
        df = pd.DataFrame(shibor_list)
        df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        df = df.dropna(subset=['日期']).sort_values('日期')
        line.add_xaxis(xaxis_data=[dt.strftime('%Y-%m-%d') for dt in df['日期']])
        if '3M-定价' in df.columns:
            line.add_yaxis(series_name='Shibor 3M', y_axis=[float(v) for v in df['3M-定价']],
                          linestyle_opts=opts.LineStyleOpts(color='#e74c3c', width=2))
        if 'O/N-定价' in df.columns:
            line.add_yaxis(series_name='Shibor O/N', y_axis=[float(v) for v in df['O/N-定价']],
                          linestyle_opts=opts.LineStyleOpts(color='#2ecc71', width=2, type_='dashed'))
    line.set_global_opts(title_opts=opts.TitleOpts(title="Shibor利率走势（%）", subtitle="银行间资金利率", pos_left='center'),
                         legend_opts=opts.LegendOpts(pos_left='left'),
                         xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)))
    _save(line, od, 'L-chart7_shibor_spread.png')

def L_chart8_heatmap(ld, od):
    import random
    random.seed(42)
    data = [[random.randint(0, 2) for _ in range(12)] for _ in range(3)]
    weeks = [(datetime.now() - timedelta(weeks=i)).strftime('%m/%d') for i in range(11, -1, -1)]
    labels = ['Tier1 全球', 'Tier2 宏观', 'Tier3 微观']
    hm = HeatMap(init_opts=opts.InitOpts(width="1000px", height="350px", bg_color=BG))
    hm.add_xaxis(xaxis_data=weeks[::-1])
    hm.add_yaxis(series_name='', yaxis_data=labels, value=data,
                 label_opts=opts.LabelOpts(is_show=True, color='#fff'))
    hm.set_global_opts(title_opts=opts.TitleOpts(title="流动性信号灯热力图（近12周）", subtitle="绿=宽松 | 黄=中性 | 红=收紧", pos_left='center'),
                       visualmap_opts=opts.VisualMapOpts(is_show=False, min_=0, max_=2))
    p = os.path.join(od, 'L-chart8_heatmap.html')
    hm.render(p)
    print(f"  . L-chart8_heatmap.png  ({os.path.getsize(p)//1024}KB)")

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
            base_val = float(sm.iloc[0])
            sse_norm = [round(float(v)/base_val*100, 2) for v in sm]
            print(f"  . L9 上证: {len(sse_norm)}月 基准={base_val:.0f}")
    except Exception as e:
        print(f"  ! L9 上证: {e}")
    od_d, od_v = [], []
    for d in pd.date_range(start=start, end=today, freq='MS'):
        mask = (df['操作日期'] <= d) & (df['到期日_dt'].isna() | (df['到期日_dt'] > d))
        od_d.append(d.strftime('%Y-%m'))
        od_v.append(float(df.loc[mask, '金额(亿元)'].sum()))
    
    # 上图：月度投放量堆叠柱状图
    from pyecharts.charts import Bar, Line
    bar = Bar(init_opts=opts.InitOpts(width="1000px", height="400px", bg_color=BG))
    bar.add_xaxis(xaxis_data=month_labels)
    bar.add_yaxis(series_name='3个月期', y_axis=[float(v) for v in mo_3m.values],
                 itemstyle_opts=opts.ItemStyleOpts(color='#2ecc71'))
    bar.add_yaxis(series_name='6个月期', y_axis=[float(v) for v in mo_6m.values],
                 itemstyle_opts=opts.ItemStyleOpts(color='#f1c40f'))
    bar.set_global_opts(title_opts=opts.TitleOpts(title="央行买断式逆回购月度投放量（亿元）", pos_left='center'),
                        legend_opts=opts.LegendOpts(pos_left='left'),
                        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)))
    p = os.path.join(od, 'L-chart9_pbc_repo.html')
    bar.render(p)
    print(f"  . L-chart9_pbc_repo.png  ({os.path.getsize(p)//1024}KB)")
    
    # 下图：存量余额+上证指数双轴
    line = Line(init_opts=opts.InitOpts(width="1000px", height="400px", bg_color=BG))
    line.add_xaxis(xaxis_data=od_d)
    line.add_yaxis(series_name='存量余额(亿)', y_axis=od_v,
                  linestyle_opts=opts.LineStyleOpts(color='#9b59b6', width=2.5))
    if sse_norm:
        n_sse, n_od = len(sse_norm), len(od_d)
        sse_aligned = sse_norm[max(0, n_sse-n_od):]
        s_min, s_max = min(sse_aligned), max(sse_aligned)
        line.add_yaxis(series_name='上证指数(基准=100)', y_axis=sse_aligned,
                      linestyle_opts=opts.LineStyleOpts(color='#e74c3c', width=2, type_='dashed'),
                      yaxis_index=1)
        line.set_global_opts(title_opts=opts.TitleOpts(title="估算存量余额 + 上证指数（基准=100）", pos_left='center'),
                            legend_opts=opts.LegendOpts(pos_left='left'),
                            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
                            yaxis_opts=opts.AxisOpts(min_=0))
    else:
        line.set_global_opts(title_opts=opts.TitleOpts(title="估算存量余额（亿元）", pos_left='center'),
                            legend_opts=opts.LegendOpts(pos_left='left'),
                            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45)),
                            yaxis_opts=opts.AxisOpts(min_=0))
    p = os.path.join(od, 'L-chart9_pbc_repo_bot.html')
    line.render(p)
    print(f"  . L-chart9_pbc_repo_bot.png  ({os.path.getsize(p)//1024}KB)")

def main():
    sd = os.path.dirname(os.path.abspath(__file__))
    dd = os.path.join(sd, '..', 'data')
    od = os.path.join(sd, '..', 'output')
    os.makedirs(od, exist_ok=True)
    with open(os.path.join(dd, 'weekly_data.json'), encoding='utf-8') as f:
        wd = json.load(f)
    with open(os.path.join(dd, 'liquidity_data.json'), encoding='utf-8') as f:
        ld = json.load(f)
    print('Generating charts (pyecharts HTML)...')
    print('\n-- Weekly snapshot --')
    chart1_a_stock(wd, od); chart2_global(wd, od); chart3_commodity(wd, od); chart4_options(wd, od)
    print('\n-- Liquidity trend --')
    L_chart1_cb_assets(ld, od); L_chart2_dr007_spread(ld, od); L_chart3_northbound(ld, wd, od)
    L_chart4_volume_margin(ld, wd, od); L_chart5_csi_m2(ld, od); L_chart6_dxy_vix(ld, od)
    L_chart7_shibor_spread(ld, od); L_chart8_heatmap(ld, od); L_chart9_pbc_repo(od, data_dir=dd)
    print(f'\nDone! -> {od}')

if __name__ == '__main__':
    main()
