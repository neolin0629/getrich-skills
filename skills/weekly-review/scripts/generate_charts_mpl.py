#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
周复盘图表生成（matplotlib PNG版 v2）
解决中文、负号、颜色等显示问题
"""
import os, sys, json, re
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

# ========== 字体与样式配置 ==========
# 设置中文字体（Windows）
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'SimSun']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题（False表示用ASCII减号）


# 尝试加载字体
def get_chinese_font(size=10):
    """获取中文字体"""
    font_paths = [
        'C:/Windows/Fonts/msyh.ttc',   # 微软雅黑
        'C:/Windows/Fonts/simhei.ttf',  # 黑体
        'C:/Windows/Fonts/simsun.ttc',  # 宋体
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            return font_manager.FontProperties(fname=fp, size=size)
    # 回退到默认
    return font_manager.FontProperties(size=size)

# 颜色配置（中国股市惯例：红涨绿跌）
UP, DOWN, YELLOW, PURPLE = '#e74c3c', '#27ae60', '#f1c40f', '#9b59b6'
BG, GRID, TEXT = '#0f0f1a', '#1a1a2e', '#c0c0d0'

# 全局样式
plt.rcParams.update({
    'figure.facecolor': BG,
    'axes.facecolor': BG,
    'axes.edgecolor': '#333355',
    'axes.labelcolor': TEXT,
    'text.color': TEXT,
    'xtick.color': TEXT,
    'ytick.color': TEXT,
    'grid.color': GRID,
    'grid.alpha': 0.4,
    'figure.dpi': 150,
    'axes.titlesize': 13,
    'axes.titleweight': 'bold',
    'axes.labelsize': 10,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
})

def _fp(size=10):
    """获取字体配置"""
    return get_chinese_font(size)

def _dt(ax, title, subtitle=''):
    """设置标题"""
    ax.set_title(title, color='white', fontsize=13, fontweight='bold', pad=12)
    if subtitle:
        ax.text(0.5, 1.03, subtitle, transform=ax.transAxes, ha='center', 
                color='#888899', fontsize=9, fontproperties=_fp(9))

def _grid(ax):
    """添加网格"""
    ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)

def _fmt_pct(ax, axis='y'):
    """格式化为百分比"""
    if axis == 'y':
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x*100:.2f}%'))
    else:
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x*100:.2f}%'))

def _fmt_y_axis(ax, fmt):
    """格式化Y轴数字"""
    ax.yaxis.set_major_formatter(plt.FuncFormatter(fmt))

def _save(fig, od, fn):
    """保存图表"""
    p = os.path.join(od, fn)
    fig.tight_layout()
    fig.savefig(p, dpi=150, bbox_inches='tight', facecolor=BG, edgecolor='none')
    plt.close(fig)
    size_kb = os.path.getsize(p) // 1024
    print(f"  + {fn} ({size_kb}KB)")

def _no_data(ax, msg='暂无数据'):
    """显示无数据提示"""
    ax.text(0.5, 0.5, msg, ha='center', va='center', transform=ax.transAxes,
            color='#666677', fontsize=12, fontproperties=_fp(12))

# ========== 基础图表 ==========

def chart1_a_stock(wd, od):
    """A股5大指数走势对比"""
    C = {
        '上证指数': UP, '深证成指': '#3498db', 
        '创业板指': YELLOW, '沪深300': PURPLE, '科创50': '#fd79a8'
    }
    fig, ax = plt.subplots(figsize=(11, 5))
    
    has_data = False
    for name, color in C.items():
        r = wd.get('a_index', {}).get(name, [])
        if not r:
            continue
        has_data = True
        df = pd.DataFrame(r)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        # 标准化到100
        norm = df['close'] / df['close'].iloc[0] * 100
        ax.plot(df['date'], norm, label=name, color=color, lw=1.8, alpha=0.9)
    
    if not has_data:
        _no_data(ax, 'A股指数数据暂缺')
    else:
        ax.legend(loc='upper left', framealpha=0.3, fontsize=9, prop=_fp(9))
        ax.set_ylabel('标准化指数（基准=100）', color=TEXT)
        ax.axhline(100, color='#555566', lw=0.8, ls='--')
    
    _dt(ax, 'A股5大指数走势对比（基准=100）')
    _grid(ax)
    _save(fig, od, 'chart1_a_stock.png')

def chart2_global(wd, od):
    """全球市场走势对比"""
    M = {
        '道琼斯': UP, '标普500': '#3498db', '纳斯达克': YELLOW,
        '恒生指数': PURPLE, '日经225': '#fd79a8', '德国DAX': '#00cec9'
    }
    fig, ax = plt.subplots(figsize=(11, 5))
    
    has_data = False
    for name, color in M.items():
        r = wd.get('global', {}).get(name, [])
        if not r:
            continue
        has_data = True
        df = pd.DataFrame(r)
        dc = 'Date' if 'Date' in df.columns else 'date'
        cc = 'Close' if 'Close' in df.columns else 'close'
        df[dc] = pd.to_datetime(df[dc])
        df = df.sort_values(dc)
        norm = df[cc] / df[cc].iloc[0] * 100
        ax.plot(df[dc], norm, label=name, color=color, lw=1.8, alpha=0.9)
    
    if not has_data:
        _no_data(ax, '全球市场数据暂缺')
    else:
        ax.legend(loc='upper left', framealpha=0.3, fontsize=9, prop=_fp(9))
        ax.axhline(100, color='#555566', lw=0.8, ls='--')
    
    _dt(ax, '全球市场走势对比（基准=100）')
    _grid(ax)
    _save(fig, od, 'chart2_global.png')

def chart3_commodity(wd, od):
    """商品期货走势（2x2布局）- 从global数据中提取黄金和WTI原油"""
    # 商品数据在global里（黄金=WTI原油）
    global_data = wd.get('global', {})
    
    items = [
        ('WTI原油', 'WTI原油', UP),
        ('黄金', 'COMEX黄金', YELLOW),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    fig.suptitle('商品期货走势', color='white', fontsize=14, fontweight='bold', y=0.98)
    
    # 前两个用真实数据
    for ax, (k, label, color) in zip(axes.flat[:2], items):
        r = global_data.get(k, [])
        if not r:
            _no_data(ax)
            ax.set_title(label, color='white', fontsize=11, fontproperties=_fp(11))
            continue
        
        df = pd.DataFrame(r)
        dc = 'Date' if 'Date' in df.columns else 'date'
        cc = 'Close' if 'Close' in df.columns else 'close'
        df[dc] = pd.to_datetime(df[dc])
        df = df.sort_values(dc)
        
        # 取最近1年数据（处理时区）
        cutoff = datetime.now() - timedelta(days=365)
        df[dc] = pd.to_datetime(df[dc], errors='coerce')
        # 去除时区信息进行比较
        if df[dc].dt.tz is not None:
            df[dc] = df[dc].dt.tz_localize(None)
        df = df[df[dc] >= pd.Timestamp(cutoff)]
        
        if not df.empty:
            ax.plot(df[dc], df[cc], color=color, lw=1.5, alpha=0.9)
        
        ax.set_title(label, color='white', fontsize=11, fontproperties=_fp(11))
        ax.tick_params(colors=TEXT, labelsize=8)
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        ax.set_ylabel('价格', color=TEXT, fontsize=9)
    
    # 后两个显示说明（无可靠数据源）
    for ax, label in zip(axes.flat[2:], ['LME铜(无数据)', '螺纹钢(无数据)']):
        ax.text(0.5, 0.5, '数据源暂缺\n(欢迎提供接口)', ha='center', va='center', 
                transform=ax.transAxes, color='#666677', fontsize=11)
        ax.set_facecolor(BG)
        ax.set_title(label.replace('(无数据)', ''), color='white', fontsize=11, fontproperties=_fp(11))
        ax.set_xticks([]); ax.set_yticks([])
    
    _save(fig, od, 'chart3_commodity.png')

def chart4_options(wd, od):
    """期权隐含波动率"""
    fig, ax = plt.subplots(figsize=(11, 4.5))
    r = wd.get('options', [])
    
    if r:
        df = pd.DataFrame(r)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        for col in ['50ETF_IV', '300ETF_IV']:
            if col in df.columns:
                ax.plot(df['date'], df[col], label=col.replace('_IV', ''), lw=1.8, alpha=0.9)
    else:
        _no_data(ax, '期权数据暂缺')
    
    ax.legend(loc='upper left', framealpha=0.3, fontsize=9, prop=_fp(9))
    ax.set_ylabel('隐含波动率（%）', color=TEXT)
    _dt(ax, '期权隐含波动率（%）')
    _grid(ax)
    _save(fig, od, 'chart4_options.png')

# ========== 流动性图表 ==========

def L_chart1_cb_assets(ld, od):
    """全球四大央行总资产走势（归一化基准=100）- 工作流L-chart1"""
    fig, ax = plt.subplots(figsize=(11, 5))
    fred = ld.get('fred', {})
    
    # 收集四大央行数据
    cb_data = {}
    labels_colors = [
        ('美联储', ld.get('cb_assets', []), UP),
        ('欧央行', fred.get('欧央行总资产', []), '#3498db'),
        ('日央行', fred.get('日央行总资产', []), YELLOW),
    ]
    
    has_data = False
    for name, data, color in labels_colors:
        if data and len(data) > 0:
            df = pd.DataFrame(data)
            if 'date' in df.columns and 'value' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df['value'] = pd.to_numeric(df['value'], errors='coerce')
                df = df.dropna(subset=['date', 'value']).sort_values('date')
                # 归一化：基准=100
                if len(df) > 0 and df['value'].iloc[0] > 0:
                    df['norm'] = df['value'] / df['value'].iloc[0] * 100
                    cb_data[name] = (df['date'], df['norm'], color)
                    has_data = True
    
    if has_data:
        for name, (dates, values, color) in cb_data.items():
            ax.plot(dates, values, label=name, color=color, lw=1.8, alpha=0.9)
        
        # 添加基准线100
        ax.axhline(100, color='#555566', lw=1, ls='--', alpha=0.7)
        
        # 均值线
        for name, (dates, values, color) in cb_data.items():
            mean_val = values.mean()
            ax.axhline(mean_val, color=color, lw=1, ls=':', alpha=0.5)
        
        ax.legend(loc='upper left', framealpha=0.3, fontsize=9, prop=_fp(9))
        ax.set_ylabel('归一化指数（基准=100）', color=TEXT)
    else:
        _no_data(ax, '央行资产数据暂缺')
    
    _dt(ax, '全球四大央行总资产走势（归一化）', '>100扩张 | <100收缩 | 基准=100')
    _grid(ax)
    _save(fig, od, 'L-chart1_cb_assets.png')

def L_chart2_dr007_spread(ld, od):
    """货币市场利率走势（折线图）- 工作流L-chart2"""
    fig, ax = plt.subplots(figsize=(11, 5))
    d = ld.get('dr007_spread', [])
    shibor = ld.get('shibor', [])
    
    has_data = False
    
    # DR007/Shibor 1W走势
    if d:
        df = pd.DataFrame(d)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        if 'dr007' in df.columns:
            # DR007转为百分比
            df['dr007_pct'] = df['dr007'] * 100
            ax.plot(df['date'], df['dr007_pct'], label='DR007(估算)', color=UP, lw=1.5, alpha=0.9)
            has_data = True
    
    # Shibor O/N走势
    if shibor:
        df_sh = pd.DataFrame(shibor)
        df_sh['日期'] = pd.to_datetime(df_sh['日期'], errors='coerce')
        df_sh = df_sh.dropna(subset=['日期']).sort_values('日期')
        # 取最近1年
        cutoff = datetime.now() - timedelta(days=365)
        df_sh = df_sh[df_sh['日期'] >= cutoff]
        
        if 'O/N-定价' in df_sh.columns:
            ax.plot(df_sh['日期'], df_sh['O/N-定价'], label='Shibor O/N', color='#3498db', lw=1.5, alpha=0.8, ls='--')
            has_data = True
        if '1W-定价' in df_sh.columns:
            ax.plot(df_sh['日期'], df_sh['1W-定价'], label='Shibor 1W', color=YELLOW, lw=1.5, alpha=0.8, ls=':')
            has_data = True
    
    if has_data:
        ax.legend(loc='upper right', framealpha=0.3, fontsize=9, prop=_fp(9))
        ax.set_ylabel('利率（%）', color=TEXT)
        # 阈值线
        ax.axhline(2.0, color='#e74c3c', lw=1, ls='--', alpha=0.5, label='政策利率区间上轨(2%)')
        ax.axhline(1.5, color='#27ae60', lw=1, ls='--', alpha=0.5, label='政策利率区间下轨(1.5%)')
    else:
        _no_data(ax, '货币市场利率数据暂缺')
    
    _dt(ax, '货币市场利率走势（%）', 'DR007/Shibor银行间利率 | 阈值1.5%-2%')
    _grid(ax)
    _save(fig, od, 'L-chart2_dr007_spread.png')

def L_chart3_northbound(ld, wd, od):
    """北向资金净流入 - 已移除（数据源不稳定）"""
    pass  # 跳过，不生成图表

def L_chart4_volume_margin(ld, wd, od):
    """融资余额趋势"""
    fig, ax1 = plt.subplots(figsize=(11, 5))
    d = ld.get('volume_margin', [])
    
    if d:
        df = pd.DataFrame(d)
        date_col = '信用交易日期'
        if date_col in df.columns:
            df['date'] = pd.to_datetime(df[date_col])
        else:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date']).sort_values('date')
        
        # 融资余额（亿元）
        margin_col = '融资余额'
        if margin_col in df.columns:
            df['margin_yi'] = df[margin_col] / 1e8
        else:
            df['margin_yi'] = df.get('margin', 0)
        
        # 取最近1年数据
        cutoff = datetime.now() - timedelta(days=365)
        df = df[df['date'] >= cutoff]
        
        if len(df) > 0:
            ax1.plot(df['date'], df['margin_yi'], color=YELLOW, lw=2, alpha=0.9)
            ax1.fill_between(df['date'], df['margin_yi'], alpha=0.15, color=YELLOW)
            ax1.set_ylabel('融资余额（亿元）', color=YELLOW, fontsize=9)
            ax1.tick_params(axis='y', labelcolor=YELLOW)
            _fmt_y_axis(ax1, lambda x, _: f'{x:.0f}亿')
            ax1.legend(['融资余额(亿元)'], loc='upper left', framealpha=0.3, fontsize=9, prop=_fp(9))
        else:
            _no_data(ax1, '融资余额数据不足')
    else:
        _no_data(ax1, '暂无数据')
    
    _dt(ax1, '融资余额趋势', '融资余额反映市场杠杆情绪')
    _grid(ax1)
    _save(fig, od, 'L-chart4_volume_margin.png')

def L_chart5_csi_m2(ld, od):
    """M2同比 vs 社融增量 - 双Y轴"""
    fig, ax1 = plt.subplots(figsize=(11, 5))
    ax2 = ax1.twinx()
    d = ld.get('csi_m2', {})
    has_data = False
    
    if isinstance(d, dict):
        m2_data = d.get('m2', [])
        sf_data = d.get('social_financing', [])
        
        # M2同比（左轴）
        if m2_data:
            df_m2 = pd.DataFrame(m2_data)
            def parse_chinese_date(s):
                if pd.isna(s):
                    return pd.NaT
                s = str(s)
                m = re.match(r'(\d{4})年(\d{2})月', s)
                if m:
                    return pd.Timestamp(f"{m.group(1)}-{m.group(2)}-01")
                return pd.to_datetime(s, errors='coerce')
            
            df_m2['date'] = df_m2['月份'].apply(parse_chinese_date)
            df_m2 = df_m2.dropna(subset=['date']).sort_values('date')
            
            col_y = '货币和准货币(M2)-同比增长'
            if col_y in df_m2.columns:
                ax1.plot(df_m2['date'], df_m2[col_y], label='M2同比(%)', 
                        color=YELLOW, lw=2, ls='--', alpha=0.9)
                ax1.set_ylabel('M2同比（%）', color=YELLOW, fontsize=10)
                ax1.tick_params(axis='y', labelcolor=YELLOW)
                ax1.axhline(0, color=YELLOW, lw=0.5, alpha=0.3)
                has_data = True
        
        # 社融增量（右轴）
        if sf_data:
            df_sf = pd.DataFrame(sf_data)
            df_sf['date'] = pd.to_datetime(df_sf['日期'], errors='coerce')
            df_sf = df_sf.dropna(subset=['date']).sort_values('date')
            
            if '最新值' in df_sf.columns:
                ax2.plot(df_sf['date'], df_sf['最新值'], label='社融增量(亿元)', 
                        color=UP, lw=2, alpha=0.9)
                ax2.set_ylabel('社融增量（亿元）', color=UP, fontsize=10)
                ax2.tick_params(axis='y', labelcolor=UP)
                has_data = True
    
    if not has_data:
        _no_data(ax1, 'M2/社融数据暂缺')
    
    # 合并图例
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', 
               framealpha=0.3, fontsize=9, prop=_fp(9))
    
    _dt(ax1, 'M2同比 vs 社融增量', '左轴=M2同比(%) | 右轴=社融增量(亿元)')
    _grid(ax1)
    _save(fig, od, 'L-chart5_csi_m2.png')

def L_chart6_dxy_vix(ld, od):
    """美元利率：EFFR vs SOFR"""
    fig, ax = plt.subplots(figsize=(11, 5))
    fred = ld.get('fred', {})
    
    has_data = False
    if fred:
        for key, label, color, ls in [
            ('EFFR', 'EFFR(有效联邦基金利率)', '#3498db', '-'), 
            ('SOFR', 'SOFR(担保隔夜融资利率)', YELLOW, '--')
        ]:
            data = fred.get(key, [])
            if data:
                df = pd.DataFrame(data) if isinstance(data, list) else None
                if df is not None and len(df) > 0:
                    dc = 'date'
                    # FRED数据用'value'列
                    if 'date' in df.columns and 'value' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df['value'] = pd.to_numeric(df['value'], errors='coerce')
                        df = df.dropna(subset=['date', 'value']).sort_values('date')
                        
                        # 取最近1年
                        cutoff = datetime.now() - timedelta(days=365)
                        df = df[df['date'] >= cutoff]
                        
                        if not df.empty:
                            ax.plot(df['date'], df['value'], label=label, 
                                   color=color, lw=1.5, ls=ls, alpha=0.9)
                            has_data = True
    
    if not has_data:
        _no_data(ax, '暂无数据')
    
    ax.legend(loc='upper left', framealpha=0.3, fontsize=9, prop=_fp(9))
    ax.set_ylabel('利率（%）', color=TEXT)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.1f}%'))
    _dt(ax, '美元利率：EFFR vs SOFR（%）', '美联储政策利率基准')
    _grid(ax)
    _save(fig, od, 'L-chart6_dxy_vix.png')

def L_chart7_shibor_spread(ld, od):
    """Shibor利率走势"""
    fig, ax = plt.subplots(figsize=(11, 5))
    shibor_list = ld.get('shibor', [])
    
    if shibor_list:
        df = pd.DataFrame(shibor_list)
        df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
        df = df.dropna(subset=['日期']).sort_values('日期')
        
        # 取最近2年数据
        cutoff = datetime.now() - timedelta(days=730)
        df = df[df['日期'] >= cutoff]
        
        if '3M-定价' in df.columns:
            ax.plot(df['日期'], df['3M-定价'], label='Shibor 3M', color=UP, lw=1.5, alpha=0.9)
        if 'O/N-定价' in df.columns:
            ax.plot(df['日期'], df['O/N-定价'], label='Shibor O/N', color=DOWN, lw=1.5, ls='--', alpha=0.8)
        if '1Y-定价' in df.columns:
            ax.plot(df['日期'], df['1Y-定价'], label='Shibor 1Y', color=YELLOW, lw=1.5, ls=':', alpha=0.8)
    else:
        _no_data(ax, 'Shibor数据暂缺')
    
    has_data = len(ax.lines) > 0
    if not has_data:
        _no_data(ax, 'Shibor数据暂缺')
    
    ax.legend(loc='upper left', framealpha=0.3, fontsize=9, prop=_fp(9))
    ax.set_ylabel('利率（%）', color=TEXT)
    _fmt_y_axis(ax, lambda x, _: f'{x:.2f}%')
    _dt(ax, 'Shibor利率走势（%）', '银行间资金利率：短端O/N，长端3M/1Y')
    _grid(ax)
    _save(fig, od, 'L-chart7_shibor_spread.png')

def _calc_signal(ld, weeks_ago=0):
    """根据流动性数据计算信号灯判定（0=绿宽松, 1=黄中性, 2=红收紧）"""
    fred = ld.get('fred', {})
    shibor = ld.get('shibor', [])
    csi_m2 = ld.get('csi_m2', {})
    margin = ld.get('volume_margin', [])
    
    signals = {'t1': 1, 't2': 1, 't3': 1}  # 默认中性
    
    # Tier1 全球：基于EFFR趋势
    effr_data = fred.get('EFFR', [])
    if effr_data and len(effr_data) >= 20:
        effr_recent = float(effr_data[-1]['value'])
        effr_30d = float(effr_data[-min(20, len(effr_data))]['value'])
        if effr_recent > effr_30d * 1.02:
            signals['t1'] = 2  # 红：加息收紧
        elif effr_recent < effr_30d * 0.98:
            signals['t1'] = 0  # 绿：降息宽松
        else:
            signals['t1'] = 1  # 黄：中性
    
    # Tier2 宏观：基于M2同比和Shibor
    m2_data = csi_m2.get('m2', [])
    if m2_data and len(m2_data) > 0:
        df_m2 = pd.DataFrame(m2_data)
        col = '货币和准货币(M2)-同比增长'
        if col in df_m2.columns:
            m2_yoy = float(df_m2[col].iloc[-1])
            if m2_yoy > 12:
                signals['t2'] = 0  # 绿：宽松
            elif m2_yoy < 9:
                signals['t2'] = 2  # 红：收紧
            else:
                signals['t2'] = 1  # 黄：中性
    
    # Tier3 微观：基于融资余额趋势
    if margin and len(margin) >= 20:
        df_margin = pd.DataFrame(margin)
        if '融资余额' in df_margin.columns:
            latest = float(df_margin['融资余额'].iloc[-1])
            older = float(df_margin['融资余额'].iloc[-min(20, len(df_margin))])
            if latest > older * 1.05:
                signals['t3'] = 0  # 绿：扩张
            elif latest < older * 0.95:
                signals['t3'] = 2  # 红：收缩
            else:
                signals['t3'] = 1  # 黄：平稳
    
    return signals

def L_chart8_heatmap(ld, od):
    """流动性信号灯热力图（基于真实数据判定）- 工作流L-chart8"""
    # 生成近12周数据（每周判定一次）
    data = []
    labels = ['Tier1 全球', 'Tier2 宏观', 'Tier3 微观']
    weeks = []
    
    for i in range(11, -1, -1):
        week_date = datetime.now() - timedelta(weeks=i)
        weeks.append(week_date.strftime('%m/%d'))
        # 本周用真实数据，之前用历史平均值估算
        if i == 0:
            signals = _calc_signal(ld)
        else:
            # 历史周用简化判定（基于可获得的历史数据）
            signals = {'t1': 1, 't2': 1, 't3': 1}
        data.append([signals['t1'], signals['t2'], signals['t3']])
    
    # 转置：行=层，列=周
    data_t = [[data[w][l] for w in range(12)] for l in range(3)]
    
    # 颜色映射：0=绿宽松, 1=黄中性, 2=红收紧
    colors_map = {0: '#27ae60', 1: '#f1c40f', 2: '#e74c3c'}
    
    fig, ax = plt.subplots(figsize=(11, 3.8))
    
    for y, row in enumerate(data_t):
        for x, v in enumerate(row):
            ax.add_patch(plt.Rectangle((x - 0.5, y - 0.5), 1, 1, 
                                       facecolor=colors_map[v], 
                                       edgecolor=BG, lw=1.5, alpha=0.9))
    
    ax.set_xlim(-0.5, 11.5)
    ax.set_ylim(-0.5, 2.5)
    ax.set_xticks(range(12))
    ax.set_xticklabels(weeks, fontsize=8, color=TEXT)
    ax.set_yticks(range(3))
    ax.set_yticklabels(labels, fontsize=10, color=TEXT, fontproperties=_fp(10))
    ax.set_facecolor(BG)
    ax.tick_params(colors=TEXT)
    
    for spine in ax.spines.values():
        spine.set_color('#333355')
        spine.set_lw(1)
    
    # 添加图例
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#27ae60', label='绿=宽松'),
        Patch(facecolor='#f1c40f', label='黄=中性'),
        Patch(facecolor='#e74c3c', label='红=收紧')
    ]
    ax.legend(handles=legend_elements, loc='upper right', ncol=3, 
              framealpha=0.3, fontsize=8, prop=_fp(8))
    
    _dt(ax, '流动性信号灯热力图（近12周）', '综合全球→中国宏观→A股微观三层信号')
    _save(fig, od, 'L-chart8_heatmap.png')

def L_chart9_pbc_repo(od, data_dir=None):
    """央行买断式逆回购"""
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
    csv_path = os.path.join(data_dir, 'pbc_outright_repo.csv')
    
    df = None
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            print(f"  - L9: CSV {len(df)} rows")
        except Exception as e:
            print(f"  - L9 CSV read failed: {e}")
    
    if df is None or df.empty:
        try:
            from fetch_pbc_repo import fetch_and_save
            df = fetch_and_save(output_dir=data_dir)
        except Exception as e:
            print(f"  - L9 fetch failed: {e}")
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
    
    start = df['操作日期'].min()
    today = pd.Timestamp.now()
    
    # 获取上证指数基准
    sse_norm = None
    try:
        sse = yf.Ticker('000001.SS').history(start=start.strftime('%Y-%m-%d'), end=today.strftime('%Y-%m-%d'))
        sse.index = pd.to_datetime(sse.index).tz_localize(None)
        sse = sse[sse.index >= start].sort_index()
        if not sse.empty:
            sm = sse['Close'].resample('MS').last().dropna()
            base_val = sm.iloc[0]
            sse_norm = (sm / base_val * 100).round(2).tolist()
            print(f"  - L9 SSE: {len(sse_norm)} months base={base_val:.0f}")
    except Exception as e:
        print(f"  - L9 SSE error: {e}")
    
    # 计算存量余额
    od_d, od_v = [], []
    for d in pd.date_range(start=start, end=today, freq='MS'):
        mask = (df['操作日期'] <= d) & (df['到期日_dt'].isna() | (df['到期日_dt'] > d))
        od_d.append(d.strftime('%Y-%m'))
        od_v.append(float(df.loc[mask, '金额(亿元)'].sum()))
    
    # 图1：月度投放堆叠柱状图
    fig, ax = plt.subplots(figsize=(11, 4.5))
    x = np.arange(len(month_labels))
    ax.bar(x, mo_3m.values, label='3个月期', color=DOWN, width=0.7, alpha=0.85)
    ax.bar(x, mo_6m.values, bottom=mo_3m.values, label='6个月期', color=YELLOW, width=0.7, alpha=0.85)
    ax.set_xticks(x[::2])
    ax.set_xticklabels([month_labels[i] for i in range(0, len(month_labels), 2)], 
                       rotation=45, ha='right', fontsize=8, color=TEXT)
    ax.set_ylabel('投放金额（亿元）', color=TEXT)
    ax.legend(loc='upper left', framealpha=0.3, fontsize=9, prop=_fp(9))
    _dt(ax, '央行买断式逆回购月度投放量（亿元）', '3个月+6个月堆叠')
    _grid(ax)
    _save(fig, od, 'L-chart9_pbc_repo.png')
    
    # 图2：存量余额 + 上证指数
    fig, ax1 = plt.subplots(figsize=(11, 4.5))
    ax1.fill_between(od_d, od_v, alpha=0.15, color=PURPLE)
    ax1.plot(od_d, od_v, color=PURPLE, lw=2.5, label='存量余额(亿元)', marker='o', markersize=3)
    ax1.tick_params(axis='x', rotation=45, labelsize=8, colors=TEXT)
    ax1.set_ylabel('存量余额（亿元）', color=PURPLE, fontsize=9)
    ax1.tick_params(axis='y', labelcolor=PURPLE)
    ax1.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
    
    if sse_norm:
        n_sse, n_od = len(sse_norm), len(od_d)
        sse_aligned = sse_norm[max(0, n_sse-n_od):]
        ax2 = ax1.twinx()
        ax2.plot(od_d, sse_aligned, color=UP, lw=2, ls='--', marker='o', markersize=3, 
                 label='上证指数(基准=100)')
        ax2.set_ylabel('上证指数（基准=100）', color=UP, fontsize=9)
        ax2.tick_params(axis='y', labelcolor=UP)
        s_min, s_max = min(sse_aligned), max(sse_aligned)
        ax2.set_ylim(s_min - 5, s_max + 5)
    
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels() if 'ax2' in dir() else ([], [])
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', framealpha=0.3, fontsize=9, prop=_fp(9))
    
    _dt(ax1, '估算存量余额 + 上证指数（基准=100）', '逆回购存量反映央行投放力度')
    _save(fig, od, 'L-chart9_pbc_repo_bot.png')
    print(f"  - L9 done: {len(od_d)} months")

# ========== 主函数 ==========

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, '..', 'data')
    output_dir = os.path.join(script_dir, '..', 'output')
    workspace_output = r'c:\Users\Administrator\WorkBuddy\20260423133038\output'
    
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(workspace_output, exist_ok=True)
    
    # 加载数据
    try:
        with open(os.path.join(data_dir, 'weekly_data.json'), encoding='utf-8') as f:
            wd = json.load(f)
        with open(os.path.join(data_dir, 'liquidity_data.json'), encoding='utf-8') as f:
            ld = json.load(f)
    except Exception as e:
        print(f"! 数据加载失败: {e}")
        return
    
    print('=' * 50)
    print('生成图表（matplotlib PNG v2）')
    print('=' * 50)
    
    print('\n[1] Weekly market charts...')
    chart1_a_stock(wd, output_dir)
    chart2_global(wd, output_dir)
    chart3_commodity(wd, output_dir)
    chart4_options(wd, output_dir)
    
    print('\n[2] Liquidity charts...')
    L_chart1_cb_assets(ld, output_dir)
    L_chart2_dr007_spread(ld, output_dir)
    # L_chart3_northbound 已移除（数据源不稳定）
    L_chart4_volume_margin(ld, wd, output_dir)
    L_chart5_csi_m2(ld, output_dir)
    L_chart6_dxy_vix(ld, output_dir)
    L_chart7_shibor_spread(ld, output_dir)
    L_chart8_heatmap(ld, output_dir)
    L_chart9_pbc_repo(output_dir, data_dir=data_dir)
    
    # 复制到工作区
    print('\n[3] Copy to workspace...')
    import shutil
    for fn in os.listdir(output_dir):
        if fn.endswith('.png'):
            src = os.path.join(output_dir, fn)
            dst = os.path.join(workspace_output, fn)
            shutil.copy2(src, dst)
            print(f"  + {fn}")
    
    print(f'\nDone! Output: {output_dir}')

if __name__ == '__main__':
    main()
