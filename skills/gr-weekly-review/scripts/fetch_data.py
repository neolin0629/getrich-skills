#!/usr/bin/env python3
"""
周复盘数据采集脚本
数据源：AkShare + yfinance + FRED API
输出：weekly_data.json + liquidity_data.json

用法：
  python fetch_data.py [--start YYYYMMDD] [--end YYYYMMDD] [--fred-key KEY]

  不传参时，自动计算本周一至周五日期。
  FRED key 默认使用内置key（8906388170c2b7df3a9724617e36dafd）
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

import akshare as ak
import pandas as pd

# 设置编码
sys.stdout.reconfigure(encoding='utf-8')

# ===== 内置FRED API Key（用户提供的key）=====
DEFAULT_FRED_KEY = "8906388170c2b7df3a9724617e36dafd"


def safe_call(func, *args, default=None, warn_name=None, **kwargs):
    """安全调用API，失败时打印WARN继续"""
    name = warn_name or func.__name__
    try:
        result = func(*args, **kwargs)
        if result is None or (hasattr(result, '__len__') and len(result) == 0):
            print(f"[WARN] {name} returned empty")
            return default
        return result
    except Exception as e:
        print(f"[WARN] {name} failed: {e}")
        return default


def get_trade_dates(start, end):
    """获取A股交易日列表"""
    try:
        df = ak.tool_trade_date_hist_sina()
        dates = pd.to_datetime(df['trade_date'])
        mask = (dates >= start) & (dates <= end)
        return dates[mask].dt.strftime('%Y-%m-%d').tolist()
    except Exception:
        # 降级：返回工作日
        dates = pd.date_range(start, end, freq='B')
        return dates.strftime('%Y-%m-%d').tolist()


def fetch_a_index_daily(start, end):
    """A股5大指数日线"""
    indices = {
        '上证指数': 'sh000001',
        '深证成指': 'sz399001',
        '创业板指': 'sz399006',
        '沪深300': 'sh000300',
        '科创50': 'sh000688',
    }
    result = {}
    for name, symbol in indices.items():
        df = safe_call(
            ak.stock_zh_index_daily, symbol=symbol,
            warn_name=f'stock_zh_index_daily({symbol})',
            default=pd.DataFrame()
        )
        if df is not None and not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            df = df[(df['date'] >= start) & (df['date'] <= end)]
            result[name] = df.to_dict('records')
            print(f"  ✅ {name}: {len(df)} rows")
        else:
            result[name] = []
            print(f"  ⚠️ {name}: no data")
    return result


def fetch_etf_daily(start, end):
    """ETF日线（50ETF/300ETF）"""
    etfs = {'50ETF': '510050', '300ETF': '510300'}
    result = {}
    for name, symbol in etfs.items():
        df = safe_call(
            ak.fund_etf_hist_em, symbol=symbol, period='daily',
            start_date=start.replace('-', ''),
            end_date=end.replace('-', ''),
            adjust='qfq',
            warn_name=f'fund_etf_hist_em({symbol})',
            default=pd.DataFrame()
        )
        if df is not None and not df.empty:
            result[name] = df.to_dict('records')
            print(f"  ✅ {name}: {len(df)} rows")
        else:
            result[name] = []
            print(f"  ⚠️ {name}: no data")
    return result


def fetch_northbound():
    """全市场主力资金流向（替代北向资金：AkShare eastmoney接口自2024年8月起停更，改用全市场主力资金流向，数据完整且最近）
    注：原北向资金接口(stock_hsgt_hist_em) eastmoney已停更净买额数据；
    stock_market_fund_flow 提供全市场主力/超大单/大单净流入，是更好的资金面代理指标。
    """
    df = safe_call(
        ak.stock_market_fund_flow,
        warn_name='stock_market_fund_flow',
        default=pd.DataFrame()
    )
    if df is not None and not df.empty:
        print(f"  ✅ 全市场主力资金: {len(df)} rows")
        return df.to_dict('records')
    print("  ⚠️ 全市场主力资金: no data")
    return []


def fetch_margin():
    """融资融券（拉取1年历史，用于L-chart4趋势图）"""
    df = safe_call(
        ak.stock_margin_sse,
        start_date=(datetime.now() - timedelta(days=365)).strftime('%Y%m%d'),
        end_date=datetime.now().strftime('%Y%m%d'),
        warn_name='stock_margin_sse',
        default=pd.DataFrame()
    )
    if df is not None and not df.empty:
        print(f"  ✅ 融资融券: {len(df)} rows")
        return df.to_dict('records')
    print("  ⚠️ 融资融券: no data")
    return []


def fetch_zt_pool(date_str):
    """涨停池"""
    df = safe_call(
        ak.stock_zt_pool_em, date=date_str,
        warn_name=f'stock_zt_pool_em({date_str})',
        default=pd.DataFrame()
    )
    if df is not None and not df.empty:
        return len(df)
    return 0


def fetch_dt_pool(date_str):
    """跌停池"""
    df = safe_call(
        ak.stock_zt_pool_dtgc_em, date=date_str,
        warn_name=f'stock_zt_pool_dtgc_em({date_str})',
        default=pd.DataFrame()
    )
    if df is not None and not df.empty:
        return len(df)
    return 0


def fetch_options_iv():
    """期权隐含波动率（50ETF QVIX + 沪深300 QVIX - 历史序列）"""
    result = []
    
    # 1. 50ETF QVIX（波动率指数）
    try:
        df_50 = safe_call(ak.index_option_50etf_qvix, warn_name='index_option_50etf_qvix', default=pd.DataFrame())
        if df_50 is not None and not df_50.empty:
            # 格式化数据
            df_50['date'] = pd.to_datetime(df_50['date'])
            df_50 = df_50.sort_values('date').tail(250)  # 最近250个交易日
            df_50 = df_50.rename(columns={'close': '50ETF_IV'})
            result = df_50[['date', '50ETF_IV']].to_dict('records')
            print(f"  [OK] 50ETF QVIX: {len(result)} rows, latest={result[-1]['50ETF_IV'] if result else 'N/A'}")
    except Exception as e:
        print(f"  [WARN] 50ETF QVIX failed: {e}")
    
    # 2. 沪深300 ETF QVIX
    try:
        df_300 = safe_call(ak.index_option_300etf_qvix, warn_name='index_option_300etf_qvix', default=pd.DataFrame())
        if df_300 is not None and not df_300.empty:
            df_300['date'] = pd.to_datetime(df_300['date'])
            df_300 = df_300.sort_values('date').tail(250)
            df_300 = df_300.rename(columns={'close': '300ETF_IV'})
            # 合并到result
            if result:
                df_result = pd.DataFrame(result)
                df_300_reset = df_300[['date', '300ETF_IV']].reset_index(drop=True)
                df_result['date'] = pd.to_datetime(df_result['date'])
                df_300_reset['date'] = pd.to_datetime(df_300_reset['date'])
                df_merged = pd.merge(df_result, df_300_reset, on='date', how='outer').sort_values('date')
                result = df_merged.to_dict('records')
            else:
                result = df_300[['date', '300ETF_IV']].to_dict('records')
            print(f"  [OK] 300ETF QVIX: merged, latest={result[-1].get('300ETF_IV', 'N/A') if result else 'N/A'}")
    except Exception as e:
        print(f"  [WARN] 300ETF QVIX failed: {e}")
    
    return result if result else []


def fetch_shibor():
    """Shibor利率（用于L-chart7趋势图，保留全量历史）"""
    df = safe_call(
        ak.macro_china_shibor_all,
        warn_name='macro_china_shibor_all',
        default=pd.DataFrame()
    )
    if df is not None and not df.empty:
        print(f"  ✅ Shibor: {len(df)} rows")
        return df.to_dict('records')
    print("  ⚠️ Shibor: no data")
    return []


def fetch_dr007_spread():
    """DR007 + 7天逆回购利率（利差=DR007-OMO）- 使用Shibor数据"""
    result = []
    try:
        # 使用Shibor数据作为货币市场利率代理
        shibor_df = safe_call(ak.macro_china_shibor_all, warn_name='shibor', default=pd.DataFrame())
        if shibor_df is not None and not shibor_df.empty:
            print(f"  [OK] Shibor raw: {len(shibor_df)} rows, cols={list(shibor_df.columns[:5])}")
            
            # 找日期列（可能是'日期'或'date'）
            dc = '日期' if '日期' in shibor_df.columns else 'date'
            
            # 找1W Shibor作为DR007代理（7天期，更接近DR007）
            w1_col = None
            for c in shibor_df.columns:
                if '1W' in c:
                    w1_col = c
                    break
            
            on_col = None
            for c in shibor_df.columns:
                if 'O/N' in c and '定价' in c:
                    on_col = c
                    break
            
            if w1_col:
                shibor_df[dc] = pd.to_datetime(shibor_df[dc], errors='coerce')
                shibor_df = shibor_df.dropna(subset=[dc, w1_col])
                shibor_df = shibor_df.sort_values(dc)
                
                # 转换为小数形式
                shibor_df['dr007'] = pd.to_numeric(shibor_df[w1_col], errors='coerce') / 100
                # OMO 7天逆回购利率约1.8%（2024年水平）
                shibor_df['omo_7d'] = 0.018
                
                # 用正确的列名
                df_out = shibor_df[[dc, 'dr007', 'omo_7d']].tail(250).copy()
                df_out = df_out.rename(columns={dc: 'date'})
                result = df_out.to_dict('records')
                print(f"  [OK] DR007(Shibor 1W): {len(result)} rows")
            elif on_col:
                shibor_df[dc] = pd.to_datetime(shibor_df[dc], errors='coerce')
                shibor_df = shibor_df.dropna(subset=[dc, on_col])
                shibor_df = shibor_df.sort_values(dc)
                shibor_df['dr007'] = pd.to_numeric(shibor_df[on_col], errors='coerce') / 100
                shibor_df['omo_7d'] = 0.018
                df_out = shibor_df[[dc, 'dr007', 'omo_7d']].tail(250).copy()
                df_out = df_out.rename(columns={dc: 'date'})
                result = df_out.to_dict('records')
                print(f"  [OK] DR007(Shibor O/N): {len(result)} rows")
            else:
                print(f"  [WARN] DR007: no suitable column found, cols={list(shibor_df.columns)}")
    except Exception as e:
        print(f"  [WARN] DR007 failed: {e}")
    return result


def fetch_cb_assets():
    """央行总资产（用FRED的美联储总资产WALCL）"""
    import requests
    fred_key = DEFAULT_FRED_KEY
    base_url = "https://api.stlouisfed.org/fred/series/observations"
    end = datetime.now().strftime('%Y-%m-%d')
    start = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')  # 2年
    try:
        params = {
            'series_id': 'WALCL',
            'api_key': fred_key,
            'file_type': 'json',
            'observation_start': start,
            'observation_end': end,
            'frequency': 'w',
        }
        resp = requests.get(base_url, params=params, timeout=30)
        data = resp.json()
        if 'observations' in data:
            obs = [{'date': o['date'], 'value': float(o['value'])/1e4}  # 转为万亿元
                   for o in data['observations'] if o['value'] != '.']
            print(f"  ✅ 美联储总资产(WALCL): {len(obs)} obs")
            return obs
    except Exception as e:
        print(f"  ⚠️ WALCL: {e}")
    return []


def fetch_northbound_history():
    """北向资金历史（沪深港通持股数据）"""
    result = []
    try:
        # 沪深港通持股汇总
        df = safe_call(
            ak.stock_hsgt_north_hold_stock_em,
            warn_name='stock_hsgt_north_hold_stock_em',
            default=pd.DataFrame()
        )
        if df is not None and not df.empty:
            print(f"  ✅ 北向持股: {len(df)} rows")
            result.extend(df.to_dict('records'))
    except Exception as e:
        print(f"  ⚠️ 北向持股: {e}")
    # 尝试北向资金流向日频
    try:
        df2 = safe_call(
            ak.stock_hsgt_hist_em, symbol="北上",
            warn_name='stock_hsgt_hist_em(北上)',
            default=pd.DataFrame()
        )
        if df2 is not None and not df2.empty:
            print(f"  ✅ 北向资金流向: {len(df2)} rows")
            result.extend(df2.to_dict('records'))
    except Exception as e:
        print(f"  ⚠️ 北向资金流向: {e}")
    return result


def fetch_volume_history():
    """全市场成交额历史（1年）"""
    try:
        df = safe_call(
            ak.stock_board_industry_name_em,
            warn_name='stock_board_industry_name_em(成交额)',
            default=pd.DataFrame()
        )
        # 全A成交额用指数成交额替代
        df2 = safe_call(
            ak.stock_zh_index_daily, symbol="sh000001",
            warn_name='stock_zh_index_daily(sh000001_vol)',
            default=pd.DataFrame()
        )
        if df2 is not None and not df2.empty:
            df2['date'] = pd.to_datetime(df2['date'])
            df2 = df2[df2['date'] >= datetime.now() - timedelta(days=730)]
            print(f"  ✅ 全A成交额: {len(df2)} rows")
            return df2[['date', 'volume']].rename(columns={'volume': 'volume'}).to_dict('records')
    except Exception as e:
        print(f"  ⚠️ 成交额: {e}")
    return []


def fetch_global_yfinance(start, end):
    """yfinance全球市场数据"""
    try:
        import yfinance as yf
    except ImportError:
        print("[WARN] yfinance not installed, skip global data")
        return {}

    tickers = {
        '道琼斯': '^DJI', '标普500': '^GSPC', '纳斯达克': '^IXIC',
        '恒生指数': '^HSI', '日经225': '^N225', '德国DAX': '^GDAXI',
        '黄金': 'GC=F', 'WTI原油': 'CL=F', 'VIX': '^VIX',
        '美元指数': 'UUP',   # PowerShares DB美元指数ETF（tracks DXY，无需FRED key）
    }
    result = {}
    for name, code in tickers.items():
        try:
            ticker = yf.Ticker(code)
            # 1年数据用于趋势图
            df = ticker.history(period="1y")
            if df is not None and not df.empty:
                # 提取本周数据
                df_week = df.loc[start:end] if start and end else df.tail(5)
                result[name] = {
                    'weekly': df_week.reset_index().to_dict('records'),
                    'yearly': df.reset_index().to_dict('records'),
                }
                print(f"  ✅ {name}: weekly={len(df_week)}, yearly={len(df)}")
            else:
                result[name] = {'weekly': [], 'yearly': []}
                print(f"  ⚠️ {name}: no data")
        except Exception as e:
            result[name] = {'weekly': [], 'yearly': []}
            print(f"  ⚠️ {name}: {e}")
    return result


def fetch_fred_data(fred_key, start, end):
    """FRED API数据（美联储/欧央行/日央行/美元/汇率）"""
    if not fred_key:
        print("[WARN] No FRED API key, skip FRED data")
        return {}

    import requests

    series = {
        # 央行总资产
        '美联储总资产': 'WALCL',
        '欧央行总资产': 'ECBASSETSW',   # FRED: Central Bank Assets for Euro Area (Weekly)
        '日央行总资产': 'JPNASSETS',      # FRED: Bank of Japan Total Assets (Monthly)
        # 利率
        'EFFR': 'EFFR',
        'SOFR': 'SOFR',
        # 汇率
        '美元指数': 'DTWEXBGS',
        'USDCNY': 'DEXCHUS',
        # 其他
        '央行互换': 'SWAPT',
        '美国10Y国债': 'DGS10',
    }

    base_url = "https://api.stlouisfed.org/fred/series/observations"
    result = {}

    for name, sid in series.items():
        try:
            params = {
                'series_id': sid,
                'api_key': fred_key,
                'file_type': 'json',
                'observation_start': start,
                'observation_end': end,
            }
            # 周度数据用frequency=w，月度数据用frequency=m
            if sid in ['WALCL', 'SWAPT', 'ECBASSETSW']:
                params['frequency'] = 'w'
            elif sid == 'JPNASSETS':
                params['frequency'] = 'm'   # 日央行月频

            resp = requests.get(base_url, params=params, timeout=30)
            data = resp.json()
            if 'observations' in data:
                obs = data['observations']
                result[name] = [
                    {'date': o['date'], 'value': o['value']}
                    for o in obs if o['value'] != '.'
                ]
                print(f"  ✅ {name}({sid}): {len(result[name])} obs")
            else:
                result[name] = []
                print(f"  ⚠️ {name}({sid}): no observations")
        except Exception as e:
            result[name] = []
            print(f"  ⚠️ {name}({sid}): {e}")

    return result


def fetch_macro_csi_m2():
    """中国社会融资规模 + M2（用于L-chart5社融-M2剪刀差）"""
    result = {}

    # 社融增量
    df_csi = safe_call(
        ak.macro_china_bank_financing,
        warn_name='macro_china_bank_financing',
        default=pd.DataFrame()
    )
    if df_csi is not None and not df_csi.empty:
        # 找社融同比列（通常叫'社会融资规模增量(亿元)'或类似）
        # 先打印可用列，再选同比列
        print(f"  ✅ 社融: {len(df_csi)} rows, columns={list(df_csi.columns[:8])}")
        result['social_financing'] = df_csi.to_dict('records')
    else:
        result['social_financing'] = []
        print("  ⚠️ 社融: no data")

    # M2货币供应
    df_m2 = safe_call(
        ak.macro_china_money_supply,
        warn_name='macro_china_money_supply',
        default=pd.DataFrame()
    )
    if df_m2 is not None and not df_m2.empty:
        print(f"  ✅ M2: {len(df_m2)} rows, columns={list(df_m2.columns[:6])}")
        result['m2'] = df_m2.to_dict('records')
    else:
        result['m2'] = []
        print("  ⚠️ M2: no data")

    return result


def main():
    parser = argparse.ArgumentParser(description='周复盘数据采集')
    parser.add_argument('--start', help='开始日期 YYYY-MM-DD')
    parser.add_argument('--end', help='结束日期 YYYY-MM-DD')
    parser.add_argument('--fred-key', help='FRED API Key')
    args = parser.parse_args()

    # 动态计算本周日期
    today = datetime.now()
    friday = today
    while friday.weekday() != 4:  # 找到本周五
        friday += timedelta(days=1)
    monday = friday - timedelta(days=4)

    start = args.start or monday.strftime('%Y-%m-%d')
    end = args.end or friday.strftime('%Y-%m-%d')

    # 1年趋势数据起始日
    trend_start = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    print(f"📊 周复盘数据采集")
    print(f"   本周: {start} ~ {end}")
    print(f"   趋势: {trend_start} ~ {end}")
    print()

    # ===== Step 1: 全球市场 =====
    print("=== Step 1: 全球市场数据 (yfinance) ===")
    global_data = fetch_global_yfinance(start, end)

    # FRED数据（优先用args的key，其次用内置key）
    print("\n=== Step 1b: FRED数据 ===")
    fred_key = args.fred_key or DEFAULT_FRED_KEY
    fred_data = fetch_fred_data(fred_key, trend_start, end)

    # ===== Step 2: A股现货 =====
    print("\n=== Step 2: A股现货数据 (AkShare) ===")
    a_index = fetch_a_index_daily(start, end)
    etf = fetch_etf_daily(start, end)
    northbound = fetch_northbound()
    margin = fetch_margin()
    options_iv = fetch_options_iv()

    # 涨跌停
    zt_count = fetch_zt_pool(end.replace('-', ''))
    dt_count = fetch_dt_pool(end.replace('-', ''))
    print(f"  涨停: {zt_count}, 跌停: {dt_count}")

    # ===== Step 3: 流动性数据 =====
    print("\n=== Step 3: 流动性数据 ===")
    shibor = fetch_shibor()
    # 社融+M2宏观数据（用于L-chart5）
    csi_m2 = fetch_macro_csi_m2()
    # DR007利差
    dr007_spread = fetch_dr007_spread()
    # 央行资产
    cb_assets = fetch_cb_assets()
    # 北向资金历史
    northbound_hist = fetch_northbound_history()
    # 成交额历史
    volume_hist = fetch_volume_history()

    # ===== 保存数据 =====
    output_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(output_dir, '..', 'data')
    os.makedirs(data_dir, exist_ok=True)

    weekly_data = {
        'period': {'start': start, 'end': end},
        'a_index': a_index,
        'etf': etf,
        'northbound': northbound,
        'margin': margin,
        'zt_count': zt_count,
        'dt_count': dt_count,
        'global': {k: v.get('weekly', []) for k, v in global_data.items()},
        'options': options_iv,  # 期权隐含波动率
    }

    liquidity_data = {
        'period': {'start': trend_start, 'end': end},
        'shibor': shibor,
        'fred': fred_data,
        'csi_m2': csi_m2,
        'global_yearly': {k: v.get('yearly', []) for k, v in global_data.items()},
        # 补充流动性图表数据
        'cb_assets': cb_assets,               # L-chart1
        'dr007_spread': dr007_spread,          # L-chart2
        'northbound': northbound,             # L-chart3 (本周)
        'northbound_hist': northbound_hist,   # L-chart3 (历史)
        'volume_margin': margin,              # L-chart4 融资余额
        'volume_hist': volume_hist,           # L-chart4 成交额
    }

    weekly_path = os.path.join(data_dir, 'weekly_data.json')
    liquidity_path = os.path.join(data_dir, 'liquidity_data.json')

    with open(weekly_path, 'w', encoding='utf-8') as f:
        json.dump(weekly_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ weekly_data.json saved ({os.path.getsize(weekly_path)} bytes)")

    with open(liquidity_path, 'w', encoding='utf-8') as f:
        json.dump(liquidity_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"✅ liquidity_data.json saved ({os.path.getsize(liquidity_path)} bytes)")

    # 数据验证统计
    all_files = [weekly_path, liquidity_path]
    normal = sum(1 for p in all_files if os.path.getsize(p) > 100)
    empty = sum(1 for p in all_files if os.path.getsize(p) <= 100)
    print(f"\n📊 数据验证: 正常={normal} | 空={empty} | 总计={len(all_files)}")


if __name__ == '__main__':
    main()
