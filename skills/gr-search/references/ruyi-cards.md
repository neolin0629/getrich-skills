# 火山如意结构化卡片

> 仅 **Custom 版**返回。Global 版没有这个能力。
> 来源：`docs/87772/2272953`（CardType 清单）与 `docs/87772/2272956`（数据结构），2026-09-03 实抓。

## 是什么

火山如意是豆包搜索内置的一套结构化直答。query 命中时，除了普通网页结果，
还会在 `Result.CardResults[]` 返回结构化 JSON —— 天气就是真的温度和 AQI 数值，
汇率就是真的汇率，不需要模型从网页正文里猜。

同一批结果也会以 `WebItem` 形式出现（`SiteName="火山如意"`，`RuyiInfo.Type` 标明类型），
`CardResults` 是其中的子集。

**注意**：以下三个参数会**过滤掉如意结果**，需要卡片时不要开：
`Filter.NeedUrl=true`、`Filter.AuthInfoLevel=1`、`Industry`。

## 渲染策略：不展开卡片 JSON，读如意 WebItem

**结论来自实测，不是设计推演。** 2026-09-03 用 query「北京今日最高气温」命中 `WeatherCard`，
对比同一次调用里的两种呈现：

递归展平 `CardResults` 产出 60+ 行，且大量冗余 ——
`Date` / `ForecastTime` / `PredictTime` 三个字段值完全相同，
`Aqi` / `Value` 重复，`PubTime` / `PublishTime` 重复，
真正的温度藏在 `Condition` 里还被 2500 字符预算截断。

而同一批数据对应的**如意 WebItem** 是排好版的 markdown：

```text
# 北京市天气报告
## 2026年9月3日星期四 当前天气北京市, 温度: 31℃，湿度: 28%, 西南风 3级, 气压: 1011.0hPa…
空气质量：AQI指数: 44 (优)，主要污染物: --，PM2.5: 16.0 μg/m³…
逐小时预报
2026-09-03 星期四 15:00: 晴, 31℃, 西南风 3级…
```

卡片 JSON 是给前端搭 UI 组件用的，不是给模型读的。

所以 `render.py` 现在的做法是：

1. **不展开 `CardResults`**，只在输出顶部打一行「命中火山如意结构化直答（天气）」
2. 给带 `RuyiInfo` 的结果在 `fusion.rank` 里 **+0.25** 分，置顶到结果列表最前
3. 完整卡片 JSON 保留在落盘文件的 `cards` 字段，需要精确数值时去那里取

官方文档写明 `CardResults` 是 `WebResults` 中如意结果的**子集**，
所以卡片对应的 WebItem 必定在结果列表里 —— 这条保证了上述做法不会丢信息。

### 什么时候才该加手写格式化器

只有当某类卡片的 WebItem 文本明显劣于 JSON 时才值得。加之前必须先跑真实查询、
从落盘 JSON 的 `cards` 里拿到真实 payload 按字段名写，**不要照文档的卡片名猜字段** ——
官方只有 `WeatherCard` 给了完整内部结构，其余 16 种只列了名字和一句话说明。

## CardType 清单（17 种）

| `CardType` | 卡片 | 说明 |
| --- | --- | --- |
| `WeatherCard` | 天气 | 当日及未来天气、空气质量、生活指数 |
| `LotteryCard` | 彩票 | 开奖结果 |
| `MetalCard` | 贵金属 | 价格趋势 |
| `ExchangeRateCard` | 汇率 | 汇率换算 |
| `HolidayCard` | 节假日 | 节假日安排 |
| `HanziCard` | 汉字 | 拼音、结构、笔顺、释义 |
| `TrainScheduleCard` | 火车车次详情 | 按车次查站点与时间 |
| `TrainRouteCard` | 两地火车 | 车次、站点、票价 |
| `FlightRouteCard` | 两地航班 | 航班、时间、票价 |
| `SportsMatchCard` | 篮球足球赛事 | 对战信息 |
| `ActorWorksCard` | 明星作品 | 影视综作品及演员表 |
| `TaxEnquiryCard` | 个人所得税 | 税率查询 |
| `MacroEconomyCard` | 各地 GDP | 年度/季度 GDP 及增长 |
| `ZipcodeCard` | 邮政编码 | |
| `BasketballEventCard` | NBA/CBA 赛程 | |
| `BasketballMatchCard` | NBA/CBA 对战 | |
| `BasketballTeamCard` | NBA/CBA 球队 | 战绩、排名、阵容 |

> 文档中 `TrainSchedule Card` / `TrainRoute Card` / `FlightRoute Card` 的表格里带了空格，
> 判断为排版问题，实际应为无空格形式。代码里对未识别的 `CardType` 会原样显示，不会丢数据。

## RuyiInfo.Type 清单（WebItem 形式，范围更广）

`stock` 股票 · `weather` 天气 · `travel_restriction` 限行 · `oil_price` 油价 ·
`house_price` 房价/租金 · `metal` 贵金属 · `exchange_rate` 汇率 · `holiday_plan` 节假日 ·
`hot_media` 影视综 · `calendar` 日历/黄历 · `kefu_number` 客服电话 · `subway_line` 地铁线路 ·
`car_model` 车型 · `lottery` 彩票 · `local_service_guide` 本地办事指南 · `hanzi_detail` 汉字 ·
`shengxiao` 生肖 · `travel_food` 当地美食 · `constellation_detail` 星座运势 ·
`train_schedule` 火车车次 · `train_route` 两地火车 · `fligh_troute` 两地航班（**官方拼写如此**）·
`constellation` 星座 · `sports_match` 篮球足球赛事 · `guoxue_bihuazi` 笔画 · `hanzi_pianpang` 偏旁 ·
`gsw_shici` 古诗词 · `zipcode` 邮编 · `macro_economy` 各地 GDP · `tax_enquiry` 个税税率 ·
`actor_album` 明星作品 · `football_world_cup` 世界杯赛程 · `football_world_cup_matchup` 世界杯对战 ·
`gaokao_school` 高考院校 · `gaokao_major` 高校专业 · `gaokao_score_line` 高考分数线 ·
`gaokao_admit_score` 高校录取分 · `basketball_nba_event` NBA 赛程 · `basketball_nba_match` NBA 比赛 ·
`basketball_nba_team` NBA 球队 · `basketball_cba_event` CBA 赛程 · `basketball_cba_match` CBA 比赛 ·
`basketball_cba_team` CBA 球队

## WeatherCard 已知结构

唯一在官方文档里有完整示例的卡片，可以放心引用：

- `Aqi`：`{Aqi, CityName, Co, CoAqi, No2, No2Aqi, O3, O3Aqi, Pm10, Pm10Aqi, Pm25, Pm25Aqi, PrimaryPollutant, PubTime, QualityLevel, So2}`
- `AqiForecast`：数组，元素为 `{Aqi, Date, ForecastTime, PredictTime, PubTime, PublishTime, QualityLevel, Value}`
- `Condition`：`{Comfort, Condition, ConditionId, Dewpoint, …}`（文档示例在此处截断，其余字段未确认）

## 卡片短路

`gr_search.py` 默认双源并行，`card_shortcircuit` 为 `false`。
显式传入 `--card-shortcircuit` 或将配置设为 `true` 时，先调豆包；
若返回了卡片结果就跳过 Parallel，否则继续调用 Parallel。

`--force-all` 可覆盖已开启的短路策略，双源查询仍调用两路；单源及图片查询保留原有来源选择。
