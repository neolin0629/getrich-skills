# 数据源清单

## A股数据（AkShare）

| 接口 | 数据 | 说明 |
|------|------|------|
| `stock_zh_index_daily(symbol)` | 指数日线 | 上证/深证/创业板/沪深300/科创50 |
| `stock_zt_pool_em(date)` | 涨停池 | 当日涨停家数 |
| `stock_zt_pool_dtgc_em(date)` | 跌停池 | 当日跌停家数 |
| `stock_margin_sse(start, end)` | 融资融券 | 融资余额历史 |

## 全球市场（yfinance）

| 代码 | 数据 | 说明 |
|------|------|------|
| ^DJI | 道琼斯 | 美股 |
| ^GSPC | 标普500 | 美股 |
| ^IXIC | 纳斯达克 | 美股 |
| ^HSI | 恒生指数 | 港股 |
| ^N225 | 日经225 | 日股 |
| ^GDAXI | 德国DAX | 欧股 |
| GC=F | COMEX黄金 | 黄金 |
| CL=F | WTI原油 | 原油 |
| ^VIX | VIX恐慌指数 | 波动率 |

## 流动性数据

### AkShare

| 接口 | 数据 | 说明 |
|------|------|------|
| `macro_china_shibor_all()` | Shibor全期限 | O/N, 1W, 3M, 1Y等 |
| `macro_china_money_supply()` | M2/M1货币供应 | 月频，同比/环比 |
| `macro_china_bank_financing()` | 社融数据 | 月频，增量/增速 |

### FRED API

| 系列ID | 数据 | 频率 |
|--------|------|------|
| WALCL | 美联储总资产 | 周 |
| ECBASSETSW | 欧央行总资产 | 周 |
| JPNASSETS | 日央行总资产 | 月 |
| EFFR | 联邦基金利率 | 日 |
| SOFR | 担保隔夜融资利率 | 日 |

## 期权数据（AkShare）

| 接口 | 数据 | 说明 |
|------|------|------|
| `index_option_50etf_qvix()` | 50ETF QVIX | 波动率指数，日频 |
| `index_option_300etf_qvix()` | 300ETF QVIX | 波动率指数，日频 |

## 央行买断式逆回购

| 来源 | 说明 |
|------|------|
| `scripts/fetch_pbc_repo.py` | 央行官网爬取脚本 |
| `data/pbc_outright_repo.csv` | 输出CSV，字段：操作日期/到期日/期限/金额 |

## 踩坑记录

| 接口 | 问题 | 解决方案 |
|------|------|----------|
| `option_50etf_vol_sina` | 不存在 | 改用`index_option_50etf_qvix` |
| `stock_hsgt_hist_em("北上")` | 参数错误 | 已移除，数据源不稳定 |
| `money_market_return` | 无DR007列 | 用Shibor 1W替代 |
| Shibor O/N列名 | 'O/N-定价' | 需检查实际列名 |
