# 豆包搜索 API 字段参考

> 来源：火山引擎官方文档（Custom 版 `docs/87772/2272953`、Global 版 `docs/87772/2548026`），
> 2026-09-03 实抓。**改动请求体之前先核对本文件，不要凭记忆写字段名。**

## gr-search 只用 Custom 版

Global 版的字段表仍保留在本文档中作参考，但 `sources.py` **不再实现它**。原因：

1. **计费**：Global 仅支持按量后付费，**吃不到订阅套餐额度**，只能消耗每月 500 次免费额度；
   Custom 两种计费模式都支持。对有订阅套餐的账号，走 Global 等于把免费额度烧在能力更弱的版本上。
2. **能力可替代**：Global 相对 Custom 的独占项只有四个 ——
   全球站点覆盖、可控摘要长度（≤3000 token）、`IcpHostOnly`、图搜图（`SearchType=visual`）。
   前两个由 Parallel 覆盖得更好（Custom 的 `Content` 直接给全文，比 Global 的片段更完整）；
   `IcpHostOnly` 对国内优先的 Custom 意义不大；图搜图本 skill 未使用。
3. **能力更弱**：Global 没有如意卡片、没有 `Industry`、没有原生 `Sites`/`TimeRange`
   （需高级语法）、没有 `RankScore`，单次上限 20 条（Custom 50 条），平均时延 1053ms（Custom 700ms）。

需要图搜图时再单独接 Global，不要为此把整条主链路切过去。

## ⚠️ 最容易踩的坑：字段名大小写

两版请求体**一律 PascalCase**。服务端用 Go 实现，JSON 反序列化对大小写不敏感
（`query` 能匹配上 `Query`），但**下划线形式匹配不上**——`doc_count` 不等于 `DocCount`，
差的是下划线而不是大小写。

结果是：传错的字段被**静默丢弃，不报错**，服务端按默认值处理。
huashu-doubao-search 这个 MCP 就栽在这里，实测传 `count=20` 只回 10 条、
传 `snippet_length=2000` 仍被按默认 500 token 截断、传 `images=0` 照样返图，
而作者把这个 bug 误判成了服务端行为写进文档。

`gr_search.py search --dry-run` 就是为核对这件事准备的：打印请求体但不发请求。

## 通用

| 项 | Custom 版 | Global 版 |
| --- | --- | --- |
| URL | `https://open.feedcoopapi.com/search_api/web_search` | `https://open.feedcoopapi.com/search_api/global_search` |
| Method | POST | POST |
| 鉴权 | `Authorization: Bearer <API_KEY>` | 同左 |
| 限流 | 10 QPS（账号维度） | 5 QPS（与 Custom 相互独立） |
| 免费额度 | 每账号每月 500 次，两版共用，优先消耗 | 同左 |
| 计费 | 按量后付费 + 订阅套餐 | 仅按量后付费 |

超 QPS 不要客户端重试，用官方队列模式：`EnableWaiting: true` + `MaxWaitTime`（毫秒，≤10000，默认 5000）。

## Custom 版请求

| 字段 | 二级 | 类型 | 说明 |
| --- | --- | --- | --- |
| `Query` | | String | **必填**，1~100 字符，过长截断，**不支持多词搜索** |
| `SearchType` | | String | **必填**，`web` / `image` |
| `Count` | | Number | web ≤50（默认 10）；image ≤5 |
| `EnableWaiting` | | Boolean | 队列模式，默认 false |
| `MaxWaitTime` | | Number | 队列等待上限，毫秒，≤10000，默认 5000 |
| `Filter` | `NeedContent` | Boolean | 仅返回有正文的结果，默认 false |
| | `NeedUrl` | Boolean | 仅返回有 Url 的结果（会滤掉如意结果），默认 false |
| | `Sites` | String | 限定站点，`\|` 分隔，最多 20 个，需完整域名 |
| | `BlockHosts` | String | 屏蔽站点，`\|` 分隔，最多 **5** 个 |
| | `AuthInfoLevel` | Number | `0` 不限；`1` 仅【非常权威】（会滤掉如意结果） |
| `TimeRange` | | String | `OneDay` / `OneWeek` / `OneMonth` / `OneYear` / `YYYY-MM-DD..YYYY-MM-DD` |
| `QueryControl` | `QueryRewrite` | Boolean | Query 改写，会增加耗时，默认 false |
| `ContentFormats` | | String | `text`（默认）/ `markdown` |
| `Industry` | | String | `finance` / `game` / `health` / `gov`（会滤掉如意结果） |

文搜图额外的 `Filter` 子字段：`ImageWidthMin` / `ImageHeightMin` / `ImageWidthMax` / `ImageHeightMax` /
`ImageShapes`（`Array<String>`，枚举 `横长方形` / `竖长方形` / `方形`）。

## Custom 版响应

`ResponseMetadata{RequestId, Action, Version, Service, Region, Error}` + `Result`。

`Result`：`ResultCount` / `WebResults[]` / `ImageResults[]` / `SearchContext{SearchType, OriginQuery}` /
`TimeCost` / `LogId` / `CardResults[]`。

### WebItem

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `Id` / `SortId` | String / Number | 结果 ID、排序 ID |
| `Title` / `SiteName` / `Url` / `LogoUrl` | String | |
| `Snippet` | String | 约 200 字。**官方原文：字数限制导致缺失相关信息，仅建议用于搜索结果的列表展示，强烈不建议用于大模型场景** |
| `Summary` | String | 500~1000 字，正文中与 query 相关的片段。**官方原文：同时考虑内容完整性和字数长度，推荐用于大模型场景** |
| `Content` | String | 完整正文 |
| `PublishTime` | String | ISO，如 `2025-05-30T19:35:24+08:00` |
| `RankScore` | Float | 相关性得分 0~1 |
| `AuthInfoDes` | String | `非常权威` / `正常权威` / `一般权威` / `一般不权威` |
| `AuthInfoLevel` | Number | `1` / `2` / `3` / `4`，与上一行对应 |
| `ContentFormats` | String | 实际返回的正文格式 |
| `InlineImages` | Array | `{Width, Height, ImageUrl, Alt}`，仅部分权威站点有 |
| `RuyiInfo.Type` | String | 仅 `SiteName="火山如意"` 时有值，取值见 `ruyi-cards.md` |

> **正文字段优先级**：`Summary` → `Content` → `Snippet`。这是官方给的建议，不要图省事直接用 `Snippet`。

### ImageItem

`Id` / `SortId` / `Title` / `SiteName` / `Url` / `PublishTime` / `RankScore`，
以及 `Image{Url, Width, Height, Shape, BlurDes, Category, Watermark, Features{EntityType, EntitySubType, Description, StyleType}}`。

- `Shape`：`横长方形`（宽 > 高×1.2）/ `竖长方形`（宽 < 高×1.2）/ `方形`
- `BlurDes`：`清晰` / `一般清晰` / `模糊`
- `Watermark`：`1` 有水印 / `0` 无水印

## Global 版请求

| 字段 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `Query` | String | - | **必填**，1~100 字符，不支持多词搜索 |
| `SearchType` | String | `web` | `web` / `image` / `visual`（图搜图） |
| `DocCount` | Number | 10 | **最多 20**，文搜图时默认 5 |
| `MaxSnippetLength` | Number | 500 | 单片段最大 **tokens**（不是字符），传入 >0 生效，**最大 3000**，推荐 1000 以内 |
| `MaxImageCountPerDoc` | Number | 3 | 单条结果最多返回的图片数，传入 >0 生效，最多 10 |
| `EnableWaiting` / `MaxWaitTime` | Boolean / Number | false / 5000 | 队列模式 |
| `Filter.IcpHostOnly` | Boolean | false | 仅在国内 ICP 备案站点中搜索 |

文搜图额外：`ImageFilter.{ShortEdgePixelMin, ShortEdgePixelMax, AspectRatioMin, AspectRatioMax}`
（宽高比定义为 `height / width`）。

图搜图额外：`ImageQuery.{Url | ImageBase64}`（二选一，Base64 不带 `data:` 前缀）、
`ImageQuery.RegionOfInterest.{XMin, YMin, XMax, YMax}`（相对坐标 0~1）。

## Global 版响应

`Result`：`TotalDocCount` / `Documents[]` / `ErrorCode` / `ErrorMsg`。

### GlobalSearchDocument

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `Rank` | Number | 排序位置，**由 0 开始** |
| `Url` / `Title` | String | |
| `Snippet` | Array | `{Type: "text"\|"image", Text, Image{Width, Height, ImageUrl, Alt}}` —— 文本片段和图片是混在同一个数组里的 |
| `DocumentInfo` | Object | `{ContentCharCount, ContentTokenCount, Filetype, PublishTime}`，`Filetype` 取值 `webpage` / `pdf` / `image` |
| `HostInfo` | Object | `{Hostname, IconUrl, AuthorityLevel}` |

`AuthorityLevel` 是**字符串**（Custom 是数值）：`very_high` / `high` / `normal`。
`sources.py` 里把它映射成 Custom 的 1/2/3 刻度以便统一排序。

## 两版能力差异速查

| 能力 | Custom | Global |
| --- | :-: | :-: |
| 如意结构化卡片 `CardResults` | ✅ | ❌ |
| `Industry` 行业搜索 | ✅ | ❌ |
| `Sites` / `BlockHosts` 站点过滤 | ✅ | ❌ |
| `TimeRange` 时效过滤 | ✅ | ❌ |
| `RankScore` 相关度分数 | ✅ | ❌（只有名次） |
| `QueryRewrite` | ✅ | ❌ |
| `ContentFormats: markdown` | ✅ | ❌ |
| 完整正文 `Content` | ✅ | ❌（只有片段） |
| 片段长度上限 | 由 `Summary` 决定（500~1000 字） | 3000 tokens |
| 全球站点覆盖 | 较弱 | ✅ |
| `IcpHostOnly` | ❌ | ✅ |
| 图搜图 `visual` | ❌ | ✅ |
| 结果条数上限 | 50 | 20 |

## 错误码

| 码 | 说明 | 处理 |
| --- | --- | --- |
| `10400` | 通用参数错误 | 检查 `Query` 是否为空、字段类型 |
| `10403` | 账号或权限错误 | 检查 API Key、服务开通状态 |
| `10408` | 服务未付费开通 | 控制台确认 |
| `10409` | 套餐模式不支持 | 豆包搜索当前仅支持后付费 |
| `10410` / `10412` | 无可用套餐 / 额度不足 | 检查套餐 |
| `10500` / `10501` | 内部错误 / 免费额度链路失败 | **可重试**（`sources.py` 对这两个码做一次退避重试） |
| `700429` | 频率超限 | 降低频率；本 skill 用 `EnableWaiting` 队列模式规避 |
| `700901` | APIKey 无效 | 检查 `Authorization: Bearer <key>` |

错误可能出现在两个位置，都要检查：
`ResponseMetadata.Error{CodeN, Code, Message}`（接口层）和 `Result.{ErrorCode, ErrorMsg}`（业务层）。
