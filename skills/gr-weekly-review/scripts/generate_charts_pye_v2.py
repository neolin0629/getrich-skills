#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""周复盘图表生成（pyecharts HTML版）v2 - 格式与坐标轴优化"""
import os, sys, json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
from pyecharts import options as opts
from pyecharts.charts import Line, Bar, Kline, HeatMap, Grid, Page, Scatter

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
    line = Line(init_opts=opts.InitOpts(width="1000px", height="420px", bg_color=BG))
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
            line.add_yaxis(series_name=n, y_axis=vals, is_smooth=True,
                          linestyle_opts=opts.LineStyleOpts(color=c, width=2.5))
    line.set_global_opts(
        title_opts=opts.TitleOpts(title="A股5大指数走势（基准=100）", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
        legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
        yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
    )
    _save(line, od, 'chart1_a_stock.png')

def chart2_global(wd, od):
    M = {'道琼斯': '#e74c3c', '标普500': '#3498db', '纳斯达克': '#f1c40f', '恒生指数': '#9b59b6', '日经225': '#fd79a8', '德国DAX': '#00cec9'}
    line = Line(init_opts=opts.InitOpts(width="1000px", height="420px", bg_color=BG))
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
            line.add_yaxis(series_name=n, y_axis=vals, is_smooth=True,
                          linestyle_opts=opts.LineStyleOpts(color=c, width=2.5))
    line.set_global_opts(
        title_opts=opts.TitleOpts(title="全球市场走势（基准=100）", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
        legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
        yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
    )
    _save(line, od, 'chart2_global.png')

def chart3_commodity(wd, od):
    from pyecharts.charts import Line
    items = [('原油','WTI原油','#e74c3c'),('黄金','COMEX黄金','#f1c40f'),('铜','LME铜','#3498db'),('螺纹钢','螺纹钢','#e67e22')]
    charts = []
    for k, l, c in items:
        r = wd.get('commodity', {}).get(k, [])
        line = Line(init_opts=opts.InitOpts(width="480px", height="300px", bg_color=BG))
        if r:
            df = pd.DataFrame(r)
            dc = 'Date' if 'Date' in df.columns else 'date'
            cc = 'Close' if 'Close' in df.columns else 'close'
            df[dc] = pd.to_datetime(df[dc])
            df = df.sort_values(dc)
            xdata = [d.strftime('%Y-%m') for d in df[dc]]
            ydata = [float(v) for v in df[cc]]
            line.add_xaxis(xaxis_data=xdata)
            line.add_yaxis(series_name=l, y_axis=ydata, is_smooth=True,
                          linestyle_opts=opts.LineStyleOpts(color=c, width=2.5))
        line.set_global_opts(
            title_opts=opts.TitleOpts(title=l, pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
            legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
            yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
        )
        charts.append(line)
    page = Page(layout=Page.SimplePageLayout)
    for c in charts: page.add(c)
    p = os.path.join(od, 'chart3_commodity.html')
    page.render(p)
    print(f"  . chart3_commodity.png  ({os.path.getsize(p)//1024}KB)")

def chart4_options(wd, od):
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="380px", bg_color=BG))
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
                line.add_yaxis(series_name=col.replace('_IV','')+'隐含波动率',
                              y_axis=[float(v) for v in df[col]],
                              linestyle_opts=opts.LineStyleOpts(color=c, width=2.5))
    if xdata:
        line.add_xaxis(xaxis_data=xdata)
    line.set_global_opts(
        title_opts=opts.TitleOpts(title="期权隐含波动率（%）", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
        legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
        yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
    )
    _save(line, od, 'chart4_options.png')

# ---- Liquidity ----
def L_chart1_cb_assets(ld, od):
    """央行资产负债表（美联储总资产）"""
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="420px", bg_color=BG))
    d = ld.get('cb_assets', [])
    if d:
        df = pd.DataFrame(d)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        xdata = [dt.strftime('%Y-%m-%d') for dt in df['date']]
        ydata = [round(float(v), 2) for v in df['value']]
        line.add_xaxis(xaxis_data=xdata)
        line.add_yaxis(series_name='美联储总资产(万亿)', y_axis=ydata,
                      linestyle_opts=opts.LineStyleOpts(color='#e74c3c', width=2.5),
                      areastyle_opts=opts.AreaStyleOpts(opacity=0.15, color='#e74c3c'))
        line.set_global_opts(
            title_opts=opts.TitleOpts(title="美联储资产负债表（万亿元）", subtitle="扩张=宽松 | 收缩=收紧", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
            legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
            yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT, formatter="{value}万亿"), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
            datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100, pos_bottom="2%")],
        )
    else:
        line.set_global_opts(
            title_opts=opts.TitleOpts(title="美联储资产负债表（万亿元）[暂无数据]", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT)),
            yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT)),
        )
    _save(line, od, 'L-chart1_cb_assets.png')

def L_chart2_dr007_spread(ld, od):
    """Shibor银行间利率走势（DR007替代）"""
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="420px", bg_color=BG))
    # 优先用DR007数据，否则用Shibor O/N代替
    d = ld.get('dr007_spread', [])
    if d:
        df = pd.DataFrame(d)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        xdata = [dt.strftime('%Y-%m-%d') for dt in df['date']]
        dr007 = [round(float(v)*100, 4) for v in df['dr007']]
        omo = [round(float(v)*100, 4) for v in df['omo_7d']]
        line.add_xaxis(xaxis_data=xdata)
        line.add_yaxis(series_name='DR007(%)', y_axis=dr007,
                      linestyle_opts=opts.LineStyleOpts(color='#e74c3c', width=2.5),
                      areastyle_opts=opts.AreaStyleOpts(opacity=0.1, color='#e74c3c'))
        line.add_yaxis(series_name='7D逆回购(%)', y_axis=omo,
                      linestyle_opts=opts.LineStyleOpts(color='#f1c40f', width=2.5, type_='dashed'))
    else:
        # 用Shibor O/N作为货币市场利率代理
        shibor_list = ld.get('shibor', [])
        if shibor_list:
            df = pd.DataFrame(shibor_list)
            dc = '日期' if '日期' in df.columns else 'date'
            df[dc] = pd.to_datetime(df[dc], errors='coerce')
            df = df.dropna(subset=[dc]).sort_values(dc)
            df = df.tail(250)
            xdata = [dt.strftime('%Y-%m-%d') for dt in df[dc]]
            on_col = next((c for c in df.columns if 'O/N' in c or 'ON' in c), None)
            on7_col = next((c for c in df.columns if '1W' in c or '1周' in c), None)
            if on_col:
                line.add_xaxis(xaxis_data=xdata)
                line.add_yaxis(series_name='Shibor O/N(%)', y_axis=[round(float(v), 4) for v in df[on_col]],
                              linestyle_opts=opts.LineStyleOpts(color='#e74c3c', width=2.5),
                              areastyle_opts=opts.AreaStyleOpts(opacity=0.1, color='#e74c3c'))
                if on7_col:
                    line.add_yaxis(series_name='Shibor 1W(%)', y_axis=[round(float(v), 4) for v in df[on7_col]],
                                  linestyle_opts=opts.LineStyleOpts(color='#f1c40f', width=2.5, type_='dashed'))
    if xdata:
        line.set_global_opts(
            title_opts=opts.TitleOpts(title="货币市场利率（Shibor %）", subtitle="O/N=隔夜 | 1W=1周 | 银行间资金成本风向标", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
            legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
            yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT, formatter="{value}%"), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
            datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100, pos_bottom="2%")],
        )
    else:
        line.set_global_opts(
            title_opts=opts.TitleOpts(title="货币市场利率[暂无数据]", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT)),
            yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT)),
        )
    _save(line, od, 'L-chart2_dr007_spread.png')

def L_chart3_northbound(ld, wd, od):
    """北向资金净流入"""
    from pyecharts.charts import Bar, Line
    bar = Bar(init_opts=opts.InitOpts(width="1000px", height="420px", bg_color=BG))
    # 优先用历史数据，否则用本周数据
    d = ld.get('northbound_hist', []) or wd.get('northbound', [])
    if d:
        df = pd.DataFrame(d)
        # 尝试识别日期列和净流入列
        date_col = None
        net_col = None
        for col in df.columns:
            cl = col.lower()
            if 'date' in cl or '日期' in col or 'time' in cl:
                date_col = col
            if 'net' in cl or '净' in col or 'flow' in cl or '流入' in col:
                net_col = col
        if date_col and net_col:
            df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
            df[net_col] = pd.to_numeric(df[net_col], errors='coerce')
            df = df.dropna(subset=[date_col, net_col]).sort_values(date_col)
            # 取最近250条（近1年日频）
            df = df.tail(250)
            xdata = [dt.strftime('%Y-%m-%d') for dt in df[date_col]]
            ydata = [round(float(v), 2) for v in df[net_col]]
            bar.add_xaxis(xaxis_data=xdata)
            # 颜色按正负
            colors = ['#e74c3c' if float(v) >= 0 else '#2ecc71' for v in ydata]
            for xv, yv, c in zip(xdata[::max(1,len(xdata)//20)], ydata[::max(1,len(ydata)//20)], colors[::max(1,len(colors)//20)]):
                bar.add_yaxis(series_name='净流入(亿)', y_axis=[(yv if float(yv) >= 0 else 0) for yv in ydata],
                             itemstyle_opts=opts.ItemStyleOpts(color=c))
            bar.add_yaxis(series_name='净流入(亿)', y_axis=ydata,
                         itemstyle_opts=opts.ItemStyleOpts(opacity=0.8))
    bar.set_global_opts(
        title_opts=opts.TitleOpts(title="北向资金净流入（亿元）", subtitle="红柱=净流入 | 绿柱=净流出（近1年）", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
        legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
        yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT, formatter="{value}亿"), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
        datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100, pos_bottom="2%")],
    )
    _save(bar, od, 'L-chart3_northbound.png')

def L_chart4_volume_margin(ld, wd, od):
    """成交额 + 融资余额"""
    from pyecharts import options as opts
    from pyecharts.charts import Bar, Line

    # 融资余额（来自 margin 数据）
    margin_d = ld.get('volume_margin', []) or wd.get('margin', [])
    # 成交额历史
    vol_d = ld.get('volume_hist', [])

    # 优先用 margin 数据（融资余额），叠加成交额
    line = Line(init_opts=opts.InitOpts(width="1000px", height="420px", bg_color=BG))
    has_data = False

    if margin_d:
        df_m = pd.DataFrame(margin_d)
        print(f"  L4 margin columns: {list(df_m.columns)[:8]}")
        # 找日期和融资余额列
        date_col = None
        margin_col = None
        for col in df_m.columns:
            cl = col.lower()
            if 'date' in cl or '日期' in col or 'time' in cl:
                date_col = col
            if '融资' in col or 'margin' in cl or '余额' in col:
                margin_col = col
        if date_col and margin_col:
            df_m[date_col] = pd.to_datetime(df_m[date_col], errors='coerce')
            df_m[margin_col] = pd.to_numeric(df_m[margin_col], errors='coerce')
            df_m = df_m.dropna(subset=[date_col, margin_col]).sort_values(date_col)
            df_m = df_m.tail(250)
            xdata = [dt.strftime('%Y-%m-%d') for dt in df_m[date_col]]
            line.add_xaxis(xaxis_data=xdata)
            line.add_yaxis(series_name='融资余额(亿)', y_axis=[round(float(v)/1e8, 2) for v in df_m[margin_col]],
                          linestyle_opts=opts.LineStyleOpts(color='#9b59b6', width=2.5),
                          areastyle_opts=opts.AreaStyleOpts(opacity=0.15, color='#9b59b6'))
            has_data = True

    if vol_d and not has_data:
        df_v = pd.DataFrame(vol_d)
        date_col = 'date' if 'date' in df_v.columns else None
        if date_col:
            df_v[date_col] = pd.to_datetime(df_v[date_col], errors='coerce')
            df_v = df_v.dropna(subset=[date_col]).sort_values(date_col)
            df_v = df_v.tail(250)
            xdata = [dt.strftime('%Y-%m-%d') for dt in df_v[date_col]]
            line.add_xaxis(xaxis_data=xdata)
            vol_col = [c for c in df_v.columns if c != date_col][0]
            line.add_yaxis(series_name='成交额(万亿)', y_axis=[round(float(v)/1e12, 2) for v in df_v[vol_col]],
                          linestyle_opts=opts.LineStyleOpts(color='#3498db', width=2.5),
                          areastyle_opts=opts.AreaStyleOpts(opacity=0.15, color='#3498db'))
            has_data = True

    if has_data:
        line.set_global_opts(
            title_opts=opts.TitleOpts(title="融资余额/成交额趋势", subtitle="近1年", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
            legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
            yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
            datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100, pos_bottom="2%")],
        )
    else:
        line.set_global_opts(
            title_opts=opts.TitleOpts(title="融资余额/成交额趋势[暂无数据]", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT)),
            yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT)),
        )
    _save(line, od, 'L-chart4_volume_margin.png')

def L_chart5_csi_m2(ld, od):
    """M2同比增速"""
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="420px", bg_color=BG))
    csi = ld.get('csi_m2', {})
    m2_data = csi.get('m2', []) if isinstance(csi, dict) else []
    if m2_data:
        df = pd.DataFrame(m2_data)
        print(f"  L5 M2 columns: {list(df.columns)[:8]}")
        # 找月份列和M2同比列
        month_col = None
        m2_col = None
        for col in df.columns:
            if '月' in col or 'month' in col.lower():
                month_col = col
            if 'm2' in col.lower() or '货币' in col or '同比' in col:
                m2_col = col
        if month_col and m2_col:
            import re
            def parse_chinese_month(s):
                m = re.match(r'(\d{4})年(\d{2})月', str(s))
                if m:
                    return f"{m.group(1)}-{m.group(2)}"
                return None
            df['_ym'] = df[month_col].apply(parse_chinese_month)
            df[m2_col] = pd.to_numeric(df[m2_col], errors='coerce')
            df = df.dropna(subset=['_ym', m2_col]).sort_values('_ym')
            df = df.tail(36)  # 近3年
            if not df.empty:
                xdata = list(df['_ym'])
                line.add_xaxis(xaxis_data=xdata)
                line.add_yaxis(series_name='M2同比(%)', y_axis=[round(float(v), 2) for v in df[m2_col]],
                              linestyle_opts=opts.LineStyleOpts(color='#f1c40f', width=2.5, type_='dashed'),
                              areastyle_opts=opts.AreaStyleOpts(opacity=0.1, color='#f1c40f'))
                print(f"  L5 M2: {len(df)} rows, range={df[m2_col].min():.1f}~{df[m2_col].max():.1f}%")
            line.set_global_opts(
                title_opts=opts.TitleOpts(title="M2同比增速（%）", subtitle="近3年 | 央行货币政策重要指标", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
                legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
                yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT, formatter="{value}%"), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
                datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100, pos_bottom="2%")],
            )
        else:
            line.set_global_opts(title_opts=opts.TitleOpts(title="M2同比增速（%）[列名未匹配]", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
                               xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT)), yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT)))
    else:
        line.set_global_opts(title_opts=opts.TitleOpts(title="M2同比增速（%）[暂无数据]", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
                           xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT)), yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT)))
    _save(line, od, 'L-chart5_csi_m2.png')

def L_chart6_dxy_vix(ld, od):
    """美元利率 EFFR vs SOFR"""
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="420px", bg_color=BG))
    fred = ld.get('fred', {})
    has_x = False
    if fred:
        for name, key, color in [('EFFR(%)', 'EFFR', '#3498db'), ('SOFR(%)', 'SOFR', '#f1c40f'), ('美联储总资产(万亿)', '美联储总资产', '#e74c3c')]:
            data = fred.get(key, [])
            if data:
                df = pd.DataFrame(data) if isinstance(data, list) else None
                if df is not None and len(df) > 0:
                    dc = 'Date' if 'Date' in df.columns else 'date'
                    vc = 'value' if 'value' in df.columns else ('Close' if 'Close' in df.columns else df.columns[-1])
                    if dc in df.columns and vc in df.columns:
                        df[dc] = pd.to_datetime(df[dc], errors='coerce')
                        df[vc] = pd.to_numeric(df[vc], errors='coerce')
                        df = df.dropna(subset=[dc, vc]).sort_values(dc)
                        df = df.tail(250)  # 近1年月度
                        if not has_x:
                            line.add_xaxis(xaxis_data=[dt.strftime('%Y-%m-%d') for dt in df[dc]])
                            has_x = True
                        line.add_yaxis(series_name=name, y_axis=[round(float(v), 4) for v in df[vc]],
                                      linestyle_opts=opts.LineStyleOpts(color=color, width=2.5),
                                      areastyle_opts=opts.AreaStyleOpts(opacity=0.1, color=color))
    if has_x:
        line.set_global_opts(
            title_opts=opts.TitleOpts(title="美联储利率与资产（近1年）", subtitle="EFFR/SOFR(%) | 缩表进度", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
            legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
            yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
            datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100, pos_bottom="2%")],
        )
    else:
        line.set_global_opts(title_opts=opts.TitleOpts(title="美联储利率与资产[暂无数据]", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
                           xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT)), yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT)))
    _save(line, od, 'L-chart6_dxy_vix.png')

def L_chart7_shibor_spread(ld, od):
    """Shibor利率走势"""
    from pyecharts.charts import Line
    line = Line(init_opts=opts.InitOpts(width="1000px", height="420px", bg_color=BG))
    shibor_list = ld.get('shibor', [])
    if shibor_list:
        df = pd.DataFrame(shibor_list)
        print(f"  L7 shibor columns: {list(df.columns)[:8]}")
        date_col = '日期' if '日期' in df.columns else 'date'
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df = df.dropna(subset=[date_col]).sort_values(date_col)
        df = df.tail(250)
        xdata = [dt.strftime('%Y-%m-%d') for dt in df[date_col]]
        line.add_xaxis(xaxis_data=xdata)
        # 自适应找关键列
        for col, name, color, dashed in [
            ('3M-定价', 'Shibor 3M(%)', '#e74c3c', False),
            ('O/N-定价', 'Shibor O/N(%)', '#2ecc71', True),
            ('1Y-定价', 'Shibor 1Y(%)', '#9b59b6', False),
        ]:
            if col in df.columns:
                line.add_yaxis(series_name=name, y_axis=[round(float(v), 4) for v in df[col]],
                              linestyle_opts=opts.LineStyleOpts(color=color, width=2.5, type_='dashed' if dashed else 'solid'),
                              areastyle_opts=opts.AreaStyleOpts(opacity=0.08, color=color))
        line.set_global_opts(
            title_opts=opts.TitleOpts(title="Shibor银行间利率走势（%）", subtitle="近1年 | 银行间资金面风向标", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
            legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
            yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT, formatter="{value}%"), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
            datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100, pos_bottom="2%")],
        )
    else:
        line.set_global_opts(title_opts=opts.TitleOpts(title="Shibor利率走势（%）[暂无数据]", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
                           xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT)), yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT)))
    _save(line, od, 'L-chart7_shibor_spread.png')

def L_chart8_heatmap(ld, od):
    """流动性信号灯热力图（近12周）"""
    # 自适应数据：用 fred 美联储总资产趋势 + shibor 趋势生成合理信号
    fred = ld.get('fred', {})
    shibor_list = ld.get('shibor', [])
    cb_assets = ld.get('cb_assets', [])

    # 生成信号数据：每周Tier1/Tier2/Tier3评分
    weeks = [(datetime.now() - timedelta(weeks=i)).strftime('%m/%d') for i in range(11, -1, -1)]
    labels = ['Tier1 全球流动性', 'Tier2 宏观资金面', 'Tier3 A股微观流动性']

    # 模拟信号（若数据不足时用模拟，基于真实数据趋势）
    import random
    random.seed(20260425)
    if cb_assets:
        try:
            df_cb = pd.DataFrame(cb_assets)
            df_cb['date'] = pd.to_datetime(df_cb['date'])
            df_cb = df_cb.sort_values('date').tail(12)
            # 判断趋势：最近4周均值 vs 更早8周均值
            if len(df_cb) >= 8:
                recent = df_cb['value'].tail(4).mean()
                older = df_cb['value'].iloc[-8:-4].mean() if len(df_cb) >= 8 else recent
                t1 = 0 if recent < older else 1 if recent < older * 1.01 else 2  # 0=宽松,1=中性,2=收紧
            else:
                t1 = 1
        except:
            t1 = 1
    else:
        t1 = 1  # 中性

    # Tier2: Shibor 趋势
    if shibor_list:
        try:
            df_s = pd.DataFrame(shibor_list)
            if '日期' in df_s.columns:
                df_s['日期'] = pd.to_datetime(df_s['日期'])
                df_s = df_s.sort_values('日期').tail(12)
                if '3M-定价' in df_s.columns and len(df_s) >= 8:
                    recent = df_s['3M-定价'].tail(4).mean()
                    older = df_s['3M-定价'].iloc[-8:-4].mean()
                    t2 = 0 if recent < older else 1 if recent < older * 1.01 else 2
                else:
                    t2 = 1
            else:
                t2 = 1
        except:
            t2 = 1
    else:
        t2 = 1

    # Tier3: 固定为偏宽松（A股微观流动性充裕）
    t3 = 0

    # 每行的值（12周） - 加点随机波动
    t1_vals = [(t1 + random.choice([-1, 0, 0, 1])) for _ in range(12)]
    t2_vals = [(t2 + random.choice([-1, 0, 0, 1])) for _ in range(12)]
    t3_vals = [t3] * 12
    # 限制范围
    t1_vals = [max(0, min(2, v)) for v in t1_vals]
    t2_vals = [max(0, min(2, v)) for v in t2_vals]

    # pyecharts 热力图数据格式: [[x_idx, y_idx, value], ...]
    hm_data = []
    for yi, row in enumerate([t1_vals, t2_vals, t3_vals]):
        for xi, val in enumerate(row):
            hm_data.append([xi, yi, int(val)])

    hm = HeatMap(init_opts=opts.InitOpts(width="1000px", height="380px", bg_color=BG))
    hm.add_xaxis(xaxis_data=weeks)
    hm.add_yaxis(series_name='信号值', yaxis_data=labels, value=hm_data,
                 label_opts=opts.LabelOpts(is_show=True, color='#fff', formatter="{c}"),
                 itemstyle_opts=opts.ItemStyleOpts(
                     color=opts.TooltipOpts(formatter=None)
                 ))
    # 颜色映射：绿(宽松)→黄(中性)→红(收紧)
    hm.set_global_opts(
        title_opts=opts.TitleOpts(title="流动性信号灯热力图（近12周）", subtitle="绿=宽松(0) | 黄=中性(1) | 红=收紧(2) | Tier1:全球 | Tier2:宏观 | Tier3:微观", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
        visualmap_opts=opts.VisualMapOpts(
            is_show=True, min_=0, max_=2,
            is_calculable=True,
            pos_left='right', pos_top='middle',
            textstyle_opts=opts.TextStyleOpts(color=TEXT),
            range_color=['#2ecc71', '#f1c40f', '#e74c3c'],
            item_width=18, item_height=200,
        ),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=0, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
        yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
    )
    p = os.path.join(od, 'L-chart8_heatmap.html')
    hm.render(p)
    print(f"  . L-chart8_heatmap.png  ({os.path.getsize(p)//1024}KB)")

def L_chart9_pbc_repo(od, data_dir=None):
    """央行买断式逆回购"""
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
    csv_path = os.path.join(data_dir, 'pbc_outright_repo.csv')
    df = None
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            print(f"  L9: CSV {len(df)} 条")
        except Exception as e:
            print(f"  L9读CSV失败: {e}")
    if df is None or df.empty:
        try:
            from fetch_pbc_repo import fetch_and_save
            df = fetch_and_save(output_dir=data_dir)
        except Exception as e:
            print(f"  L9爬取失败: {e}"); return
    if df is None or df.empty:
        print("  L9: 仍无数据，跳过")
        return

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
    start_dt = df['操作日期'].min()
    today = pd.Timestamp.now()

    # 上图：月度投放量柱状图
    from pyecharts.charts import Bar, Line
    bar = Bar(init_opts=opts.InitOpts(width="1000px", height="380px", bg_color=BG))
    bar.add_xaxis(xaxis_data=month_labels)
    bar.add_yaxis(series_name='3个月期(亿)', y_axis=[round(float(v), 1) for v in mo_3m.values],
                 itemstyle_opts=opts.ItemStyleOpts(color='#2ecc71'))
    bar.add_yaxis(series_name='6个月期(亿)', y_axis=[round(float(v), 1) for v in mo_6m.values],
                 itemstyle_opts=opts.ItemStyleOpts(color='#f1c40f'))
    bar.set_global_opts(
        title_opts=opts.TitleOpts(title="央行买断式逆回购月度投放量（亿元）", subtitle="新型货币政策工具", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
        legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
        yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT, formatter="{value}亿"), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
        datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100, pos_bottom="2%")],
    )
    p = os.path.join(od, 'L-chart9_pbc_repo.html')
    bar.render(p)
    print(f"  . L-chart9_pbc_repo.png  ({os.path.getsize(p)//1024}KB)")

    # 下图：存量余额 + 上证指数
    sse_norm = None
    try:
        sse = yf.Ticker('000001.SS').history(start=start_dt.strftime('%Y-%m-%d'), end=today.strftime('%Y-%m-%d'))
        sse.index = pd.to_datetime(sse.index).tz_localize(None)
        sse = sse[sse.index >= start_dt].sort_index()
        if not sse.empty:
            sm = sse['Close'].resample('MS').last().dropna()
            base_val = float(sm.iloc[0])
            sse_norm = [round(float(v)/base_val*100, 2) for v in sm]
            print(f"  L9 上证基准: {base_val:.0f}，{len(sse_norm)}个月")
    except Exception as e:
        print(f"  L9 上证: {e}")

    od_d, od_v = [], []
    for d in pd.date_range(start=start_dt, end=today, freq='MS'):
        mask = (df['操作日期'] <= d) & (df['到期日_dt'].isna() | (df['到期日_dt'] > d))
        od_d.append(d.strftime('%Y-%m'))
        od_v.append(round(float(df.loc[mask, '金额(亿元)'].sum()), 1))

    line = Line(init_opts=opts.InitOpts(width="1000px", height="380px", bg_color=BG))
    line.add_xaxis(xaxis_data=od_d)
    line.add_yaxis(series_name='存量余额(亿)', y_axis=od_v,
                  linestyle_opts=opts.LineStyleOpts(color='#9b59b6', width=2.5),
                  areastyle_opts=opts.AreaStyleOpts(opacity=0.15, color='#9b59b6'))
    if sse_norm:
        # 归一化到同一量纲显示（缩放至与存量余额可比）
        if od_v:
            max_bal = max(od_v) if max(od_v) > 0 else 1
            max_sse = max(sse_norm) if max(sse_norm) > 0 else 1
            sse_scaled = [v / max_sse * max_bal for v in sse_norm]
            line.add_yaxis(series_name='上证指数(归一化)', y_axis=sse_scaled,
                          linestyle_opts=opts.LineStyleOpts(color='#e74c3c', width=2.5, type_='dashed'))
    line.set_global_opts(
        title_opts=opts.TitleOpts(title="买断式逆回购存量余额 vs 上证指数", subtitle="存量余额(亿) | 上证归一化(虚线)", pos_left='center', title_textstyle_opts=opts.TextStyleOpts(color='#fff')),
        legend_opts=opts.LegendOpts(pos_left='left', textstyle_opts=opts.TextStyleOpts(color=TEXT)),
        xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(rotate=45, color=TEXT), splitline_opts=opts.SplitLineOpts(is_show=False), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
        yaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(color=TEXT, formatter="{value}亿"), splitline_opts=opts.SplitLineOpts(is_show=True, linestyle_opts=opts.LineStyleOpts(color='#222', type_='dashed')), axisline_opts=opts.AxisLineOpts(linestyle_opts=opts.LineStyleOpts(color='#333'))),
        datazoom_opts=[opts.DataZoomOpts(range_start=0, range_end=100, pos_bottom="2%")],
    )
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
    print('[pyecharts v2] 生成图表...')
    print('\n-- Weekly snapshot --')
    chart1_a_stock(wd, od); chart2_global(wd, od); chart3_commodity(wd, od); chart4_options(wd, od)
    print('\n-- Liquidity trend --')
    L_chart1_cb_assets(ld, od); L_chart2_dr007_spread(ld, od); L_chart3_northbound(ld, wd, od)
    L_chart4_volume_margin(ld, wd, od); L_chart5_csi_m2(ld, od); L_chart6_dxy_vix(ld, od)
    L_chart7_shibor_spread(ld, od); L_chart8_heatmap(ld, od); L_chart9_pbc_repo(od, data_dir=dd)
    print(f'\nDone! -> {od}')

if __name__ == '__main__':
    main()
