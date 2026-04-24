#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成周复盘HTML报告"""
import os, sys, json, re
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# 路径配置
SKILL_DIR = r'C:\Users\Administrator\.workbuddy\skills\weekly-review'
DATA_DIR = os.path.join(SKILL_DIR, 'data')
OUTPUT_DIR = r'C:\Users\Administrator\WorkBuddy\20260423133038\output'
WORKSPACE = r'c:\Users\Administrator\WorkBuddy\20260423133038'
TEMPLATE_PATH = os.path.join(SKILL_DIR, 'scripts', 'generate_report.py')

# 颜色（中国股市惯例）
UP = '#e74c3c'      # 红涨
DOWN = '#27ae60'    # 绿跌
YELLOW = '#f1c40f'  # 黄

def load_data():
    """加载数据"""
    with open(os.path.join(DATA_DIR, 'weekly_data.json'), encoding='utf-8') as f:
        wd = json.load(f)
    with open(os.path.join(DATA_DIR, 'liquidity_data.json'), encoding='utf-8') as f:
        ld = json.load(f)
    return wd, ld

def calc_pct(first, last):
    """计算涨跌幅"""
    if first and first != 0:
        return (last - first) / first * 100
    return 0

def format_pct(pct):
    """格式化涨跌幅"""
    sign = '+' if pct >= 0 else ''
    cls = 'up' if pct >= 0 else 'down'
    arrow = '▲' if pct >= 0 else '▼'
    return f'<span class="{cls}">{arrow} {sign}{pct:.2f}%</span>'

def build_a_index_table(wd):
    """构建A股指数表格"""
    rows = []
    indices = ['上证指数', '深证成指', '创业板指', '沪深300', '科创50']
    for name in indices:
        data = wd.get('a_index', {}).get(name, [])
        if data:
            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            first = df['close'].iloc[0]
            last = df['close'].iloc[-1]
            pct = calc_pct(first, last)
            rows.append(f'<tr><td>{name}</td><td>{first:.2f}</td><td>{last:.2f}</td><td>{format_pct(pct)}</td><td>-</td></tr>')
    return '\n'.join(rows)

def build_global_table(wd):
    """构建全球市场表格"""
    rows = []
    markets = ['道琼斯', '标普500', '纳斯达克', '恒生指数', '日经225', '德国DAX']
    for name in markets:
        data = wd.get('global', {}).get(name, [])
        if data and len(data) >= 2:
            df = pd.DataFrame(data)
            dc = 'Date' if 'Date' in df.columns else 'date'
            cc = 'Close' if 'Close' in df.columns else 'close'
            df[dc] = pd.to_datetime(df[dc])
            df = df.sort_values(dc)
            first = df[cc].iloc[0]
            last = df[cc].iloc[-1]
            pct = calc_pct(first, last)
            rows.append(f'<tr><td>{name}</td><td>{first:.2f}</td><td>{last:.2f}</td><td>{format_pct(pct)}</td><td>-</td></tr>')
    return '\n'.join(rows)

def build_commodity_table(wd):
    """构建商品期货表格"""
    rows = []
    items = [('WTI原油', 'WTI'), ('黄金', 'COMEX黄金')]
    for name, label in items:
        data = wd.get('global', {}).get(name, [])
        if data and len(data) >= 2:
            df = pd.DataFrame(data)
            dc = 'Date' if 'Date' in df.columns else 'date'
            cc = 'Close' if 'Close' in df.columns else 'close'
            df[dc] = pd.to_datetime(df[dc])
            df = df.sort_values(dc)
            first = df[cc].iloc[0]
            last = df[cc].iloc[-1]
            pct = calc_pct(first, last)
            rows.append(f'<tr><td>{label}</td><td>{first:.2f}</td><td>{last:.2f}</td><td>{format_pct(pct)}</td><td>-</td></tr>')
    return '\n'.join(rows)

def build_options_table(wd, ld):
    """构建期权分析表格"""
    opts = wd.get('options', [])
    if not opts:
        return '<tr><td colspan="4">暂无数据</td></tr>'
    
    # 最新期权数据
    latest = opts[-1] if opts else {}
    rows = []
    
    # 50ETF
    iv50 = latest.get('50ETF_IV', 0)
    if iv50:
        level = '偏高' if iv50 > 20 else '适中' if iv50 > 12 else '偏低'
        rows.append(f'<tr><td>50ETF</td><td>{iv50:.2f}%</td><td>-</td><td>{level}</td></tr>')
    
    # 300ETF
    iv300 = latest.get('300ETF_IV', 0)
    if iv300:
        level = '偏高' if iv300 > 20 else '适中' if iv300 > 12 else '偏低'
        rows.append(f'<tr><td>300ETF</td><td>{iv300:.2f}%</td><td>-</td><td>{level}</td></tr>')
    
    return '\n'.join(rows) if rows else '<tr><td colspan="4">暂无数据</td></tr>'

def get_signal(level):
    """获取信号灯"""
    if level >= 2:
        return 'green', 'green', 'green'
    elif level == 1:
        return 'yellow', 'yellow', 'yellow'
    else:
        return 'red', 'red', 'red'

def analyze_liquidity(ld, wd):
    """分析流动性状态"""
    result = {}
    
    # Tier1: 全球流动性（SOFR/EFFR趋势）
    fred = ld.get('fred', {})
    effr_data = fred.get('EFFR', [])
    if effr_data and len(effr_data) >= 2:
        effr_latest = float(effr_data[-1]['value'])
        effr_first = float(effr_data[-20]['value']) if len(effr_data) >= 20 else float(effr_data[0]['value'])
        if effr_latest > effr_first * 1.02:
            result['t1'] = ('red', '美元收紧')
        elif effr_latest < effr_first * 0.98:
            result['t1'] = ('green', '美元宽松')
        else:
            result['t1'] = ('yellow', '美元中性')
    else:
        result['t1'] = ('yellow', '待观察')
    
    # Tier2: 中国宏观（M2同比/Shibor）
    csi_m2 = ld.get('csi_m2', {})
    m2_data = csi_m2.get('m2', [])
    if m2_data and len(m2_data) >= 2:
        df_m2 = pd.DataFrame(m2_data)
        col = '货币和准货币(M2)-同比增长'
        if col in df_m2.columns:
            m2_yoy = float(df_m2[col].iloc[-1])
            if m2_yoy > 12:
                result['t2'] = ('green', f'M2同比{m2_yoy:.1f}%')
            elif m2_yoy > 10:
                result['t2'] = ('yellow', f'M2同比{m2_yoy:.1f}%')
            else:
                result['t2'] = ('red', f'M2同比{m2_yoy:.1f}%')
        else:
            result['t2'] = ('yellow', '待观察')
    else:
        result['t2'] = ('yellow', '待观察')
    
    # Tier3: A股微观（融资余额趋势）
    margin = ld.get('volume_margin', [])
    if margin and len(margin) >= 30:
        df_margin = pd.DataFrame(margin)
        margin_latest = float(df_margin['融资余额'].iloc[-1])
        margin_30d = float(df_margin['融资余额'].iloc[-30])
        if margin_latest > margin_30d * 1.05:
            result['t3'] = ('green', '融资扩张')
        elif margin_latest < margin_30d * 0.95:
            result['t3'] = ('red', '融资收缩')
        else:
            result['t3'] = ('yellow', '融资平稳')
    else:
        result['t3'] = ('yellow', '待观察')
    
    # 综合
    colors = {'green': 2, 'yellow': 1, 'red': 0}
    score = sum(colors.get(result.get(f't{i}', ('yellow',''))[0], 1) for i in [1,2,3])
    if score >= 4:
        result['total'] = ('green', '整体宽松')
    elif score >= 2:
        result['total'] = ('yellow', '整体中性')
    else:
        result['total'] = ('red', '整体收紧')
    
    return result

def get_vix(wd):
    """获取VIX值"""
    vix_data = wd.get('global', {}).get('VIX', [])
    if vix_data:
        df = pd.DataFrame(vix_data)
        cc = 'Close' if 'Close' in df.columns else 'close'
        return f"{df[cc].iloc[-1]:.2f}"
    return 'N/A'

def main():
    print('生成周复盘报告...')
    
    # 加载数据
    wd, ld = load_data()
    period = wd.get('period', {})
    week_start = period.get('start', datetime.now().strftime('%Y-%m-%d'))
    week_end = period.get('end', datetime.now().strftime('%Y-%m-%d'))
    
    # 构建各部分
    a_index_table = build_a_index_table(wd)
    global_table = build_global_table(wd)
    commodity_table = build_commodity_table(wd)
    options_table = build_options_table(wd, ld)
    
    # 涨跌停
    zt = wd.get('zt_count', 0)
    dt = wd.get('dt_count', 0)
    vix = get_vix(wd)
    
    # 流动性分析
    liq = analyze_liquidity(ld, wd)
    
    # 期权建议
    opts = wd.get('options', [])
    latest_iv = opts[-1] if opts else {}
    iv50 = latest_iv.get('50ETF_IV', 15)
    iv300 = latest_iv.get('300ETF_IV', 15)
    
    if iv50 > 20:
        opt50_rec = 'IV处于历史高位，建议构建熊市价差策略'
    elif iv50 < 12:
        opt50_rec = 'IV处于历史低位，可考虑买入跨式策略'
    else:
        opt50_rec = 'IV处于中性水平，建议卖出远期虚值期权'
    
    if iv300 > 20:
        opt300_rec = 'IV偏高，谨慎买入'
    elif iv300 < 12:
        opt300_rec = 'IV偏低，可适度买入'
    else:
        opt300_rec = 'IV中性，观望为主'
    
    # 流动性结论
    t1_color = {'green': '#27ae60', 'yellow': '#f1c40f', 'red': '#e74c3c'}[liq['t1'][0]]
    t2_color = {'green': '#27ae60', 'yellow': '#f1c40f', 'red': '#e74c3c'}[liq['t2'][0]]
    t3_color = {'green': '#27ae60', 'yellow': '#f1c40f', 'red': '#e74c3c'}[liq['t3'][0]]
    
    liq_global = f"美联储{liq['t1'][1]}，{'美债收益率上行' if liq['t1'][0] == 'red' else '美债收益率下行' if liq['t1'][0] == 'green' else '收益率震荡'}"
    liq_macro = f"中国{liq['t2'][1]}，{'货币政策积极' if liq['t2'][0] == 'green' else '货币政策稳健' if liq['t2'][0] == 'yellow' else '信用扩张放缓'}"
    liq_micro = f"A股{liq['t3'][1]}，{'杠杆资金入场' if liq['t3'][0] == 'green' else '杠杆资金观望' if liq['t3'][0] == 'yellow' else '去杠杆持续'}"
    
    # 下周展望
    outlook = []
    if liq['total'][0] == 'green':
        outlook.append('流动性整体宽松背景下，风险资产有望继续表现')
    elif liq['total'][0] == 'red':
        outlook.append('流动性收紧中，需警惕风险资产回调压力')
    else:
        outlook.append('流动性中性，建议控制仓位，等待方向明朗')
    
    if vix != 'N/A' and float(vix) > 25:
        outlook.append('VIX处于高位，市场恐慌情绪升温，对冲需求上升')
    elif vix != 'N/A' and float(vix) < 15:
        outlook.append('VIX维持低位，市场风险偏好较高')
    
    outlook.append('关注下周重要宏观数据发布对市场情绪的影响')
    
    # 读取模板
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template = f.read()
    
    # 替换变量
    replacements = {
        '{{WEEK_DATE}}': datetime.now().strftime('%Y年%m月%d日'),
        '{{WEEK_PERIOD}}': f"{week_start} ~ {week_end}",
        '{{A_INDEX_TABLE}}': a_index_table,
        '{{GLOBAL_TABLE}}': global_table,
        '{{COMMODITY_TABLE}}': commodity_table,
        '{{ZT_COUNT}}': str(zt),
        '{{DT_COUNT}}': str(dt),
        '{{VIX}}': vix,
        '{{OPTIONS_TABLE}}': options_table,
        '{{OPTIONS_50}}': opt50_rec,
        '{{OPTIONS_300}}': opt300_rec,
        '{{SIGNAL_T1}}': liq['t1'][0],
        '{{SIGNAL_T1_DESC}}': liq['t1'][1],
        '{{SIGNAL_T2}}': liq['t2'][0],
        '{{SIGNAL_T2_DESC}}': liq['t2'][1],
        '{{SIGNAL_T3}}': liq['t3'][0],
        '{{SIGNAL_T3_DESC}}': liq['t3'][1],
        '{{SIGNAL_TOTAL}}': liq['total'][0],
        '{{SIGNAL_TOTAL_DESC}}': liq['total'][1],
        '{{LIQ_GLOBAL}}': liq_global,
        '{{LIQ_MACRO}}': liq_macro,
        '{{LIQ_MICRO}}': liq_micro,
        '{{OUTLOOK_1}}': outlook[0] if len(outlook) > 0 else '继续观察市场动向',
        '{{OUTLOOK_2}}': outlook[1] if len(outlook) > 1 else '保持谨慎',
        '{{OUTLOOK_3}}': outlook[2] if len(outlook) > 2 else '等待机会',
        '{{GENERATE_TIME}}': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    for key, val in replacements.items():
        template = template.replace(key, str(val))
    
    # 生成报告
    report_date = datetime.now().strftime('%Y-%m-%d')
    report_path = os.path.join(WORKSPACE, f'weekly-review-{report_date}.html')
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(template)
    
    size = os.path.getsize(report_path) // 1024
    print(f'报告已生成: {report_path} ({size}KB)')
    return report_path

if __name__ == '__main__':
    main()
