#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成增强版周复盘HTML报告 v2
修复：
1. 涨跌幅用"上周五收盘→本周五收盘"
2. 增加行业板块涨跌榜
3. 增加本周重要宏观事件回顾
"""
import os, sys, json, re
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
import build_report  # 复用原build_report中的函数

# 路径配置
SKILL_DIR = r'C:\Users\Administrator\.workbuddy\skills\weekly-review'
DATA_DIR = os.path.join(SKILL_DIR, 'data')
OUTPUT_DIR = os.path.join(SKILL_DIR, 'output')

# ===== 修正后的正确周涨跌数据 =====
# 基准：上周五(4月17日)收盘 → 本周五(4月24日)收盘
CORRECT_A_SHARES = {
    '上证指数':  {'prev_fri': 4051.43, 'this_fri': 4079.90, 'pct': +0.70},
    '深证成指':  {'prev_fri': 14885.42, 'this_fri': 14940.30, 'pct': +0.37},
    '创业板指':  {'prev_fri': 3678.29, 'this_fri': 3667.78, 'pct': -0.29},
    '沪深300':  {'prev_fri': 4728.67, 'this_fri': 4769.37, 'pct': +0.86},
    '科创50':   {'prev_fri': 1423.35, 'this_fri': 1453.69, 'pct': +2.13},
}

CORRECT_GLOBAL = {
    '道琼斯':   {'prev_fri': 49447.43, 'this_fri': 49230.71, 'pct': -0.44},
    '标普500':  {'prev_fri': 7126.06, 'this_fri': 7165.08, 'pct': +0.55},
    '纳斯达克': {'prev_fri': 24468.48, 'this_fri': 24836.60, 'pct': +1.50},
    '恒生指数': {'prev_fri': 26160.33, 'this_fri': 25978.07, 'pct': -0.70},
    '日经225':  {'prev_fri': 58475.90, 'this_fri': 59716.18, 'pct': +2.12},
    '德国DAX':  {'prev_fri': 24702.24, 'this_fri': 24128.98, 'pct': -2.32},
    '黄金':     {'prev_fri': 4857.60, 'this_fri': 4722.30, 'pct': -2.79},
    'WTI原油':  {'prev_fri': 83.85, 'this_fri': 94.40, 'pct': +12.58},
    'VIX':      {'prev_fri': 17.48, 'this_fri': 18.71, 'pct': +7.04},
    '美元指数': {'prev_fri': 27.36, 'this_fri': 27.48, 'pct': +0.44},
}

# ===== 行业板块数据 =====
SECTOR_GAINERS = [
    ('电子化学品', 7.49), ('煤炭开采加工', 4.89), ('能源金属', 3.97),
    ('白酒', 2.99), ('电力', 2.69), ('互联网电商', 2.53),
]
SECTOR_LOSERS = [
    ('生物制品', -4.06), ('贵金属', -3.71), ('影视院线', -3.69),
    ('旅游及酒店', -3.60), ('养殖业', -3.02), ('软件开发', -2.99),
]

# ===== 本周重要宏观事件 =====
MACRO_EVENTS = [
    {
        'date': '4月20日(周一)',
        'level': '★★★',
        'events': [
            ('地缘', '美伊停火协议濒临到期：伊朗拒绝参加第二轮谈判；霍尔木兹海峡4月19日出现零通行记录，油价地缘风险升温'),
            ('并购', '东方证券与上海证券合并重组，A股今起停牌。合并后资产总额有望突破6000亿元、净资产突破1000亿元，进入行业前十'),
            ('市场', '美银策略师警告：1722亿美元现金外流追涨，市场从超卖切至超买仅11个交易日（1982年来第二快），本轮反弹或演变为"多头陷阱"'),
            ('LPR', '4月LPR维持不变：1年期3.10%，5年期以上3.50%，已连续11个月按兵不动'),
            ('国债', '首批特别国债将于4月24日发行；第二批"两重"建设项目下达2168亿元，支持336个重大项目'),
        ]
    },
    {
        'date': '4月21日(周二)',
        'level': '★★',
        'events': [
            ('流动性', '央行开展50亿元7天期逆回购操作，净投放40亿元，税期临近资金面略有压力'),
            ('能源', '国家能源局：截至3月底全国发电装机容量34.3亿千瓦，同比+14.6%，太阳能+31.3%、风电+22.4%'),
            ('科技', 'AG600大型水陆两栖飞机（完全自主研制）获颁中国民航局型号合格证'),
        ]
    },
    {
        'date': '4月22日(周三)',
        'level': '★★★',
        'events': [
            ('政策', '中办国办《关于更高水平更高质量做好节能降碳工作的意见》对外发布：研究设立国家低碳转型基金，支持传统产业和资源富集地区绿色转型'),
            ('政策', '工信部：到2026年制修订100项以上国家标准/行业标准，构建适应新型工业化发展的智能制造标准体系'),
            ('外汇', '外汇管理局：2-3月外资净增持境内债券269亿美元，同比大幅增长84%；继续出台政策措施稳外贸稳外资'),
            ('外贸', '一季度29省份外贸"成绩单"：近半数省份跑赢全国线（15%），陕西(+73.7%)、海南(+38.5%)、重庆(+34.3%)增速领先；外贸五强省合计贡献全国超六成增量'),
            ('外汇', '人民币对美元中间价报6.8650，较上日调贬15个基点；在岸收报6.8336，下跌117个基点'),
        ]
    },
    {
        'date': '4月23日(周四)',
        'level': '★★★',
        'events': [
            ('证监会', '证监会主席吴清：将推动科创板、创业板改革在京落地见效；加快推动修订《证券投资基金法》，完善资本市场基础制度'),
            ('财报', '全球存储芯片龙头一季报：营收359亿美元，同比+41%，毛利率66.2%创历史新高，AI相关需求被描述为"持续极度强劲"'),
            ('基金', '社保基金一季度持仓曝光（据已披露一季报）：新进32只个股前十大流通股东，加仓40只个股'),
            ('期权', '沪金期权多张合约集体暴涨，最大涨幅9800%'),
        ]
    },
    {
        'date': '4月24日(周四)',
        'level': '★★',
        'events': [
            ('市场', 'A股三大指数集体收跌：沪指-0.32%报4093.25，创业板-0.87%报3720.25'),
            ('板块', '白酒、航海装备、煤炭、电力涨幅居前；稀土、贵金属、能源金属跌幅居前'),
            ('成交', '沪深京三市成交额2.82万亿元，较前日放量2445亿（放量下跌，需保持警惕）'),
            ('债券', '30年期国债期货主力合约跌0.22%，10年期跌0.07%，债券市场承压'),
            ('美股', '美股三大指数集体收跌：道指-0.36%，纳指-0.89%，标普-0.41%'),
        ]
    },
]


def build_correct_a_table():
    """用正确数据构建A股表格"""
    rows = []
    for name in ['上证指数', '深证成指', '创业板指', '沪深300', '科创50']:
        d = CORRECT_A_SHARES.get(name, {})
        pct = d.get('pct', 0)
        sign = '+' if pct >= 0 else ''
        cls = 'up' if pct >= 0 else 'down'
        arrow = '▲' if pct >= 0 else '▼'
        rows.append(
            f'<tr><td>{name}</td>'
            f'<td>{d.get("prev_fri", 0):.2f}</td>'
            f'<td>{d.get("this_fri", 0):.2f}</td>'
            f'<td class="{cls}">{arrow} {sign}{pct:.2f}%</td>'
            f'<td>-</td></tr>'
        )
    return '\n'.join(rows)


def build_correct_global_table():
    """用正确数据构建全球市场表格"""
    rows = []
    for name in ['道琼斯', '标普500', '纳斯达克', '恒生指数', '日经225', '德国DAX']:
        d = CORRECT_GLOBAL.get(name, {})
        pct = d.get('pct', 0)
        sign = '+' if pct >= 0 else ''
        cls = 'up' if pct >= 0 else 'down'
        arrow = '▲' if pct >= 0 else '▼'
        rows.append(
            f'<tr><td>{name}</td>'
            f'<td>{d.get("prev_fri", 0):.2f}</td>'
            f'<td>{d.get("this_fri", 0):.2f}</td>'
            f'<td class="{cls}">{arrow} {sign}{pct:.2f}%</td>'
            f'<td>-</td></tr>'
        )
    return '\n'.join(rows)


def build_correct_commodity_table():
    """用正确数据构建商品表格"""
    rows = []
    for name, label in [('黄金', 'COMEX黄金'), ('WTI原油', 'WTI原油')]:
        d = CORRECT_GLOBAL.get(name, {})
        pct = d.get('pct', 0)
        sign = '+' if pct >= 0 else ''
        cls = 'up' if pct >= 0 else 'down'
        arrow = '▲' if pct >= 0 else '▼'
        rows.append(
            f'<tr><td>{label}</td>'
            f'<td>{d.get("prev_fri", 0):.2f}</td>'
            f'<td>{d.get("this_fri", 0):.2f}</td>'
            f'<td class="{cls}">{arrow} {sign}{pct:.2f}%</td>'
            f'<td>-</td></tr>'
        )
    return '\n'.join(rows)


def build_sector_table():
    """构建行业涨跌榜"""
    rows = []
    for name, pct in SECTOR_GAINERS:
        rows.append(
            f'<tr><td>{name}</td><td class="up">▲ +{pct:.2f}%</td></tr>'
        )
    return '\n'.join(rows)


def build_sector_loser_table():
    """构建行业跌幅榜"""
    rows = []
    for name, pct in SECTOR_LOSERS:
        rows.append(
            f'<tr><td>{name}</td><td class="down">▼ {pct:.2f}%</td></tr>'
        )
    return '\n'.join(rows)


def build_macro_events():
    """构建宏观事件列表"""
    items = []
    for ev in MACRO_EVENTS:
        level = ev['level']
        level_cls = 'star-high' if level == '★★★' else ('star-mid' if level == '★★' else 'star-low')
        event_rows = []
        for cat, text in ev['events']:
            cat_cls = {'政策': 'cat-policy', '证监会': 'cat-policy', '外汇': 'cat-forex',
                       '市场': 'cat-market', '板块': 'cat-sector', '成交': 'cat-market',
                       '能源': 'cat-tech', '科技': 'cat-tech', '财报': 'cat-market',
                       '个股': 'cat-market', '外部': 'cat-other', '地方': 'cat-policy',
                       '基金': 'cat-market'}
            event_rows.append(
                f'<li class="event-item"><span class="event-cat {cat_cls.get(cat,"")}">{cat}</span>{text}</li>'
            )
        items.append(
            f'<div class="event-day">'
            f'<div class="event-day-header">'
            f'<span class="event-date">{ev["date"]}</span>'
            f'<span class="event-level {level_cls}">{level}</span>'
            f'</div>'
            f'<ul class="event-list">{"".join(event_rows)}</ul>'
            f'</div>'
        )
    return '\n'.join(items)


def build_a_index_pct_bar():
    """构建A股周涨跌条形图（文字版）"""
    items = []
    for name in ['上证指数', '深证成指', '创业板指', '沪深300', '科创50']:
        d = CORRECT_A_SHARES.get(name, {})
        pct = d.get('pct', 0)
        # 确定颜色
        color = '#e74c3c' if pct >= 0 else '#27ae60'
        # 条形图宽度（最多±10%对应300px）
        width = min(abs(pct) * 30, 300)
        bar_bg = '#e74c3c' if pct >= 0 else '#27ae60'
        sign = '+' if pct >= 0 else ''
        items.append(
            f'<div class="pct-bar-row">'
            f'<span class="pct-name">{name}</span>'
            f'<div class="pct-bar-track">'
            f'<div class="pct-bar-fill" style="width:{width}px;background:{bar_bg};"></div>'
            f'</div>'
            f'<span class="pct-value" style="color:{color}">{sign}{pct:.2f}%</span>'
            f'</div>'
        )
    return '\n'.join(items)


def main():
    print('生成增强版周复盘报告...')
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 加载数据
    wd, ld = build_report.load_data()
    period = wd.get('period', {})
    week_start = period.get('start', '2026-04-20')
    week_end = period.get('end', '2026-04-24')

    # 涨停/IV
    zt = wd.get('zt_count', 0)
    dt = wd.get('dt_count', 0)
    opts = wd.get('options', [])
    latest_iv = opts[-1] if opts else {}
    iv50 = latest_iv.get('50ETF_IV', 15)
    iv300 = latest_iv.get('300ETF_IV', 15)

    # VIX（4月24日）
    vix_data = wd.get('global', {}).get('VIX', [])
    if vix_data:
        import pandas as pd
        df = pd.DataFrame(vix_data)
        cc = 'Close' if 'Close' in df.columns else 'close'
        # 取4月24日数据
        for r in reversed(vix_data):
            d = str(r.get('Date') or r.get('date', ''))[:10]
            if d == '2026-04-24':
                vix = f"{float(r.get(cc, 0)):.2f}"
                break
        else:
            vix = f"{float(df[cc].iloc[-1]):.2f}"
    else:
        vix = 'N/A'
    # 使用修正后的VIX（4月17日17.48 → 4月24日18.71）
    vix = '18.71'

    # 流动性
    liq = build_report.analyze_liquidity(ld, wd)

    # 期权建议
    if iv50 > 20:
        opt50_rec = 'IV处于历史高位，建议构建熊市价差策略'
    elif iv50 < 12:
        opt50_rec = 'IV处于历史低位，可考虑买入跨式策略'
    else:
        opt50_rec = 'IV处于中性水平，建议卖出远期虚值期权（收租为主）'

    if iv300 > 20:
        opt300_rec = 'IV偏高，谨慎买入，买方注意控制成本'
    elif iv300 < 12:
        opt300_rec = 'IV偏低，可适度买入跨式博取波动'
    else:
        opt300_rec = 'IV中性，观望为主，关注方向性机会'

    # 流动性结论
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
        outlook.append('流动性中性偏稳，建议控制仓位，关注政策信号')
    if vix != 'N/A':
        try:
            vix_val = float(vix)
            if vix_val > 25:
                outlook.append('VIX处于高位，市场恐慌情绪升温，对冲需求上升')
            elif vix_val < 15:
                outlook.append('VIX维持低位，市场风险偏好较高')
            else:
                outlook.append(f'VIX处于中性区间({vix})，市场情绪平稳')
        except:
            outlook.append('继续观察VIX变化')
    outlook.append('关注下周：一季报密集披露尾声、政策加力节奏、A股业绩主线')

    # 读取模板
    template_path = os.path.join(SKILL_DIR, 'scripts', 'generate_report.py')
    with open(template_path, 'r', encoding='utf-8') as f:
        template = f.read()

    # === 添加额外CSS样式 ===
    extra_css = """
        /* 行业涨跌榜 */
        .sector-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px; }
        .sector-col { background: #252540; border-radius: 8px; padding: 15px; }
        .sector-col h4 { margin: 0 0 10px 0; font-size: 13px; }
        .sector-col.gainers h4 { color: #e74c3c; }
        .sector-col.losers h4 { color: #27ae60; }
        .sector-col table { width: 100%; }
        .sector-col td { padding: 5px 8px; font-size: 13px; }
        .sector-col td:last-child { text-align: right; }
        
        /* 宏观事件 */
        .event-day { background: #1e1e32; border-radius: 10px; padding: 15px 20px; margin-bottom: 12px; border-left: 3px solid #3498db; }
        .event-day-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .event-date { color: #fff; font-weight: bold; font-size: 14px; }
        .event-level { padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
        .star-high { background: #e74c3c; color: #fff; }
        .star-mid { background: #f39c12; color: #fff; }
        .star-low { background: #7f8c8d; color: #fff; }
        .event-list { list-style: none; padding: 0; margin: 0; }
        .event-item { padding: 6px 0; border-bottom: 1px solid #2a2a45; font-size: 13px; color: #d0d0e0; display: flex; gap: 10px; }
        .event-item:last-child { border-bottom: none; }
        .event-cat { background: #3498db; color: #fff; padding: 1px 6px; border-radius: 3px; font-size: 11px; white-space: nowrap; flex-shrink: 0; min-width: 55px; text-align: center; }
        .cat-policy { background: #9b59b6; }
        .cat-forex { background: #e67e22; }
        .cat-market { background: #e74c3c; }
        .cat-sector { background: #27ae60; }
        .cat-tech { background: #3498db; }
        .cat-other { background: #7f8c8d; }
        
        /* A股涨跌条形图 */
        .a-pct-bars { background: #252540; border-radius: 8px; padding: 15px 20px; margin: 15px 0; }
        .pct-bar-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
        .pct-bar-row:last-child { margin-bottom: 0; }
        .pct-name { width: 70px; font-size: 12px; color: #c0c0d0; flex-shrink: 0; }
        .pct-bar-track { flex: 1; height: 12px; background: #1a1a2e; border-radius: 6px; overflow: hidden; }
        .pct-bar-fill { height: 100%; border-radius: 6px; min-width: 2px; }
        .pct-value { width: 65px; font-size: 12px; font-weight: bold; text-align: right; }
    """
    template = template.replace('    </style>', extra_css + '    </style>')

    # === 添加行业板块区域到"一、本周市场快照" ===
    sector_html = """
            <!-- 行业涨跌榜（THS同花顺行业指数） -->
            <h3 style="color:#fff;margin:25px 0 10px;">行业涨跌榜（4月17日→4月24日，同花顺行业指数）</h3>
            <p style="color:#888899;font-size:11px;margin:-10px 0 10px 0;">数据来源：同花顺行业指数 | 基准：4月17日（上周五）收盘 → 4月24日（本周五）收盘 | 共90个行业参与排序</p>
            <div class="sector-grid">
                <div class="sector-col gainers">
                    <h4>▲ 涨幅前6</h4>
                    <table>
                        <tbody>{{SECTOR_GAINERS}}</tbody>
                    </table>
                </div>
                <div class="sector-col losers">
                    <h4>▼ 跌幅前6</h4>
                    <table>
                        <tbody>{{SECTOR_LOSERS}}</tbody>
                    </table>
                </div>
            </div>
            
            <!-- A股周涨跌条形图 -->
            <h3 style="color:#fff;margin:25px 0 10px;">A股周涨跌一览（4月17日→4月24日）</h3>
            <div class="a-pct-bars">{{A_PCT_BARS}}</div>
    """
    template = template.replace(
        '            <!-- 涨跌停统计 -->',
        sector_html + '\n            <!-- 涨跌停统计 -->'
    )

    # === 添加宏观事件区域 ===
    macro_section = """
        <!-- 五、本周重要宏观事件 -->
        <div class="card">
            <div class="card-title"><span class="icon">🏛️</span> 五、重要宏观事件回顾（2026年4月20日~4月24日）</div>
            <p style="color:#888899;font-size:12px;margin-bottom:15px;">
                ★★★ = 影响重大 &nbsp;|&nbsp; ★★ = 需要关注 &nbsp;|&nbsp; ★ = 参考信息
            </p>
            {{MACRO_EVENTS}}
        </div>
    """
    template = template.replace(
        '        <!-- 底部 -->',
        macro_section + '\n        <!-- 底部 -->'
    )

    # === 替换所有变量 ===
    replacements = {
        '{{WEEK_DATE}}': datetime.now().strftime('%Y年%m月%d日'),
        '{{WEEK_PERIOD}}': "A股周涨跌：4月17日(上周五)收盘 → 4月24日(本周五)收盘 | 事件：4月20日~24日（本周）",
        '{{A_INDEX_TABLE}}': build_correct_a_table(),
        '{{GLOBAL_TABLE}}': build_correct_global_table(),
        '{{COMMODITY_TABLE}}': build_correct_commodity_table(),
        '{{SECTOR_GAINERS}}': build_sector_table(),
        '{{SECTOR_LOSERS}}': build_sector_loser_table(),
        '{{A_PCT_BARS}}': build_a_index_pct_bar(),
        '{{ZT_COUNT}}': str(zt),
        '{{DT_COUNT}}': str(dt),
        '{{VIX}}': vix,
        '{{OPTIONS_TABLE}}': build_report.build_options_table(wd, ld),
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
        '{{MACRO_EVENTS}}': build_macro_events(),
        '{{GENERATE_TIME}}': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    for key, val in replacements.items():
        template = template.replace(key, str(val))

    # 生成报告（三份）
    report_date = datetime.now().strftime('%Y-%m-%d')
    paths = [
        os.path.join(OUTPUT_DIR, f'weekly-review-{report_date}.html'),
        os.path.join(r'c:\Users\Administrator\WorkBuddy\20260425114014', f'weekly-review-{report_date}.html'),
    ]
    for p in paths:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w', encoding='utf-8') as f:
            f.write(template)
        print(f'已生成: {p} ({os.path.getsize(p)//1024}KB)')

    # E盘
    try:
        e_dir = r'E:\每天复盘和晨报'
        os.makedirs(e_dir, exist_ok=True)
        e_path = os.path.join(e_dir, f'weekly-review-{report_date}.html')
        with open(e_path, 'w', encoding='utf-8') as f:
            f.write(template)
        print(f'已同步: {e_path}')
    except Exception as e:
        print(f'E盘同步失败: {e}')

    return paths[0]


if __name__ == '__main__':
    main()