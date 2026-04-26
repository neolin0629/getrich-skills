---
name: weekly-review
description: "A股·期权·全球市场·商品期货·流动性 周复盘。执行完整10步工作流，采集全球市场+A股+期权+流动性数据，生成包含1年期趋势图和本周快照图的深色HTML周报。触发词：周复盘、复盘本周、weekly review、流动性周报、周报生成。"
---

# 周复盘完整工作流 Skill

## 概述

本skill执行A股·期权·全球市场·商品期货·流动性周复盘，输出一份深色主题HTML周报，包含：
- **本周快照图**（chart1-4）：A股5大指数 + 全球市场 + 商品期货 + 期权IV
- **流动性监测仪表盘**（L-chart1-9）：央行资产 + 货币市场利率 + 融资余额 + M2社融 + 美元利率 + Shibor + 信号灯 + 买断式逆回购
- **宏观事件**（★★★/★★/★分级）
- **下周展望 + 操作建议**

## 铁律

> 价格数据绝对不能错，优先级高于一切。

0. **【最高优先】时间区间必须确认**：每次收到复盘指令，立即询问用户确认时间窗口，Step 0强制执行
1. **所有行情数据必须实测**：从AkShare/yfinance/FRED获取，不得预估、不得凭记忆
2. **日期动态计算**：本周=A股实际交易日，不得写死日期
3. **周涨跌基准**：**上周五收盘 → 本周五收盘**，不得用周一开盘/收盘做分母
4. **错误零容忍**：发现数据有误立即修正，不得带错输出

## 执行流程（11步）

> **⚠️ 铁律0（最高优先）：每次执行前必须先确认时间区间，不得自行推断。**

### Step 0: 确认时间区间（强制）
收到"复盘本周"或类似指令后，**立即停止**，主动询问：

> "**请确认复盘时间窗口。** 默认按A股实际交易日计算：当前日期为`{今天}`，请告知本周是哪个区间？例如：4月20日(周一)~4月24日(周五)，是否正确？"

- **用户确认后**才进入Step 1。
- 如用户未指定，推算逻辑：
  - 找到当前日期所在的A股交易周
  - 周一 = 该周第一个交易日
  - 周五 = 该周最后一个交易日（A股不调休）
  - **必须用`ak.tool_trade_date_hist_sina()`实时获取实际交易日来验证**，不得用calendar推断
  - 确认后打印：`本周交易区间：{周一} ~ {周五}，共N个交易日`
- 禁止在未获确认前执行Step 1。

### Step 1: 全球市场数据采集（yfinance + FRED）

```python
yfinance: 道指(^DJI)/纳指(^IXIC)/标普(^GSPC)/恒生(^HSI)/日经(^N225)/DAX(^GDAXI)/黄金(GC=F)/原油(CL=F)/VIX(^VIX)
FRED API: WALCL/EFFR/SOFR/DTWEXBGS/DEXCHUS
```

### Step 2: A股现货数据采集（AkShare）

```python
stock_zh_index_daily(): 上证/深证/创业板/沪深300/科创50
stock_zt_pool_em(): 涨停池
stock_zt_pool_dtgc_em(): 跌停池
stock_margin_sse(): 融资融券
```

### Step 3: 流动性数据采集（AkShare + FRED + 央行爬取）

```python
AkShare: Shibor(O/N,1W,3M,1Y)/融资余额/社融/M1/M2/同花顺行业指数(股票)

**行业板块周涨跌**（Step 2补充）：必须用同花顺行业指数计算，不得用新浪spot单日数据。
```python
# 获取同花顺全部行业列表
df_list = ak.stock_board_industry_name_ths()
# code_to_name = dict(zip(df_list['code'], df_list['name']))

# 获取单个行业历史数据（symbol=行业代码）
df = ak.stock_board_industry_index_ths(symbol='881121', start_date='YYYYMMDD', end_date='YYYYMMDD')
# 周涨跌 = (周五收盘 / 上周五收盘 - 1) * 100%
```
FRED: 美联储总资产(WALCL)/EFFR/SOFR/欧央行/日央行
央行爬取: scripts/fetch_pbc_repo.py → data/pbc_outright_repo.csv
期权IV: index_option_50etf_qvix / index_option_300etf_qvix
```

### Step 4: 数据清洗与交叉核验

- 统一格式 `{date, close, pct_chg}`
- A股周期: 表格行数=本周实际交易日天数
- 周涨跌重算
- 保存 `weekly_data.json` + `liquidity_data.json`

### Step 5: 流动性指标计算 + 信号灯判定

```python
Tier 1 全球 → 🟢宽松/🟡中性/🔴收紧
  - 判定依据: EFFR趋势（加息→收紧，降息→宽松，持稳→中性）

Tier 2 宏观 → 🟢宽松/🟡中性/🔴收紧
  - 判定依据: M2同比（>12%→宽松，<9%→收紧）

Tier 3 微观 → 🟢宽松/🟡中性/🔴收紧
  - 判定依据: 融资余额趋势（扩张→宽松，收缩→收紧）
```

### Step 6: 图表生成（matplotlib PNG）

**本周快照图**（仅本周数据，4张）：
```python
chart1: A股5大指数标准化对比（基准=100）
chart2: 全球市场标准化对比（基准=100）
chart3: 商品期货走势（WTI原油/黄金）
chart4: 期权隐含波动率（50ETF QVIX / 300ETF QVIX）
```

**流动性趋势图**（1年数据，9张）：
```python
L-chart1: 全球四大央行总资产走势（归一化=100，美联储+欧央行+日央行）
L-chart2: 货币市场利率走势（DR007/Shibor O/N/Shibor 1W）
L-chart4: 融资余额趋势
L-chart5: M2同比 vs 社融增量（双Y轴）
L-chart6: EFFR vs SOFR（美元利率）
L-chart7: Shibor利率走势（O/N, 3M, 1Y）
L-chart8: 流动性信号灯热力图（基于_calc_signal()真实判定）
L-chart9: 央行买断式逆回购月度投放（3M+6M堆叠柱）
L-chart9_bot: 买断式逆回购存量余额+上证指数对比
```

**图表引擎**：matplotlib PNG，深色主题，Microsoft YaHei字体

### Step 7: 波动率/期权分析

- IV分位数（偏高/偏低）
- 期权策略建议（方向性/波动率/收租/价差）

### Step 8: 宏观事件 + 流动性文本

- **宏观事件**：仅覆盖用户确认的那一周（Step 0确认的时间窗口），不得擅自延伸至前后周
- 宏观事件按★★★/★★/★排序
- 流动性核心结论3句话（全球/宏观/微观方向）
- 拐点提示 + 下周重点 + 操作建议

### Step 9: 生成HTML报告

报告必须包含：
1. 本周走势图（chart1-4）
2. 流动性趋势图（L-chart1-9）
3. 信号灯判定结果
4. 流动性核心结论
5. 10项核查清单

### Step 10: 输出与交付

```python
HTML报告 → E:\每天复盘和晨报\weekly-review-YYYY-MM-DD-vN.html
配图PNG → output/
preview_url 在浏览器打开
deliver_attachments 交付文件
```

## 数据源优先级

| 优先级 | 数据源 | 用途 |
|--------|--------|------|
| P1-A | AkShare | A股/国内宏观 |
| P1-B | yfinance | 全球市场/商品 |
| P1-C | FRED API | 美联储/美元 |

## 快捷命令

| 命令 | 说明 |
|------|------|
| `复盘本周` | 执行完整10步流程，生成HTML报告 |
| `修正图表` | 重新生成图表 |
| `流动性周报` | 仅执行Step 3+5+6 |

## 踩坑记录

| 日期 | 问题 | 教训 |
|------|------|------|
| 2026-04-24 | HTML图表路径错误 | 图表路径应为`output/chart.png` |
| 2026-04-24 | pyecharts样式差 | 改用matplotlib PNG，深色主题 |
| 2026-04-24 | L-chart2利差柱状图数据不准 | 无真实OMO每日利率，改用利率走势折线图 |
| 2026-04-24 | L-chart8信号灯用随机数 | 改用`_calc_signal()`真实判定 |
| 2026-04-24 | L-chart3北向资金无数据 | 已移除，数据源不稳定 |
| 2026-04-26 | **日历基准错误**：把4月10日当"上周五" | 上周五=当前周一-3个自然日，必须用`ak.tool_trade_date_hist_sina()`验证 |
| 2026-04-26 | **行业周涨跌用单日数据充数**：`stock_sector_spot`只有当日涨跌 | 必须用`stock_board_industry_index_ths`计算累计周涨跌 |
| 2026-04-26 | **东方财富接口持续断开**：板块历史接口均报RemoteDisconnected | 同花顺`stock_board_industry_index_ths`可用，新浪接口`stock_sector_spot`备用 |
| 2026-04-26 | **周涨跌铁律写错**：铁律写成"（周五收盘-周一开盘）" | 应为"上周五收盘→本周五收盘"，东方财富断开不影响同花顺 |

## 核心脚本

| 脚本 | 功能 |
|------|------|
| `scripts/fetch_data.py` | 数据采集主脚本 |
| `scripts/generate_charts_mpl.py` | matplotlib图表生成 |
| `scripts/build_report_v2.py` | HTML报告生成（含行业/事件增强） |

## 中国股市颜色规范

- **涨 = 红色 (#e74c3c)**
- **跌 = 绿色 (#27ae60)**
