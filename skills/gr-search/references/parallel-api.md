# Parallel 搜索接入参考

## 当前实现：走 CLI

`sources.py` 通过子进程调用 `parallel-cli`，这是唯一已实测验证过的通路。

```bash
parallel-cli search "<objective>" -q "<kw>" --json \
  --max-results 10 --excerpt-max-chars-total 24000 \
  --mode basic --client-model claude-opus-5 --session-id <id> -o <out.json>
```

结果必须从 `-o` 文件读，不要读 stdout —— 输出量常超过 harness 的 stdout 上限而被截断。

已实测的响应结构（2026-09-03）：

```json
{ "search_id": "...", "session_id": "...", "status": "...",
  "results": [{ "url": "...", "title": "...", "publish_date": "2021-08-20", "excerpts": ["..."] }],
  "usage": {}, "warnings": [] }
```

**没有相关度分数，只有数组顺序。** 所以 `fusion.py` 必须以名次做 RRF，
而不是拿 Parallel 的分数去和豆包的 `RankScore` 直接比。

### 常用参数

- `--mode turbo|fast|basic|advanced` —— 默认 `basic`；`turbo` 最快最便宜（仅英日）；`advanced` 用于多步难题
- `--after-date YYYY-MM-DD` / `--include-domains` / `--exclude-domains` / `--location <ISO 3166-1 alpha-2>`
- `--excerpt-max-chars-per-result`（最小 1000）/ `--excerpt-max-chars-total`（默认 60000）

### 鉴权

两条路，`parallel_env()` 优先用密钥，没有则回落本机 OAuth：

1. **API Key**：环境变量 `PARALLEL_API_KEY`（**已确认**，见官方 SDK：
   `new Parallel({ apiKey: process.env.PARALLEL_API_KEY })`）。换机器时用这条。
2. **OAuth**：`parallel-cli login`，凭据存在 `~/.config/parallel-web-tools/auth.json`。

`parallel-cli auth --json` 返回 `{authenticated, method, env_var_set, has_stored_credentials, stored_overridden_by_env, ...}`。
`config doctor` 会读这个来判断密钥是否真的被 CLI 读到 —— 配了密钥但 `env_var_set` 仍为 `false`，
说明变量名不对，改配置项 `parallel.api_key_env`。

## HTTP 直连兜底

`config.json` 的 `parallel.transport` 有三档：`auto`（默认，有 CLI 用 CLI，否则有密钥走 HTTP）、
`cli`、`http`。HTTP 通路只需要 API Key，用于没装 `parallel-cli` 的机器。

契约来自官方 OpenAPI（`https://docs.parallel.ai/public-openapi.json`，v0.1.2），已逐字核对。

- Base URL：`https://api.parallel.ai`
- 鉴权：header `x-api-key`（securitySchemes.ApiKeyAuth），**不是** `Authorization: Bearer`

### `POST /v1/search`（V1SearchRequest）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `search_queries` | Array\<String\> | **必填**。关键词查询，每条 3~6 个词，官方建议给 2~3 条 |
| `objective` | String? | 自然语言目标，需自包含足够上下文 |
| `mode` | String? | `turbo` / `fast` / `basic` / `advanced`，**省略时默认 advanced**（注意 CLI 默认是 basic） |
| `max_chars_total` | Int? | 所有结果 excerpt 的总字符上限 |
| `session_id` / `client_model` | String? | 跨 search/extract 调用串联上下文 / 声明消费模型 |
| `advanced_settings` | Object? | `max_results`、`source_policy`、`fetch_policy`、`excerpt_settings`、`location` |

**`max_results` 在 `advanced_settings` 里，不在顶层。**
`source_policy`：`include_domains` / `exclude_domains` / `after_date`(YYYY-MM-DD)。
`include_domains` 非空时 `exclude_domains` 被忽略；两者合计不超过 200 条。

响应 `V1SearchResponse`：`search_id` / `results[]` / `warnings` / `usage` / `session_id`，
`results[]` 元素为 `{url, title?, publish_date?, excerpts[]}` —— 与 CLI 输出一致，**无相关度分数**。

### `POST /v1/extract`（V1ExtractRequest）

`urls`（必填，**最多 20 个**）、`objective`、`search_queries`、`max_chars_total`、
`session_id`、`client_model`、`advanced_settings`。
整页正文通过 `advanced_settings.full_content` 开启（`true` 或 `{max_chars_per_result: N}`），**默认关闭**。

响应：`extract_id` / `results[]{url,title,publish_date,excerpts[],full_content}` /
**`errors[]{url,error_type,http_status_code,content}`** / `session_id`。
抓取失败的 URL 落在 `errors` 而不是 `results`，不要当成"没有结果"。

### 一个有利的差异

`V1SearchRequest` 和 `V1ExtractRequest` 都是 `additionalProperties: false`，
字段名写错会返回 **422 Request validation error**，而不是被静默丢弃。
这点比豆包友好得多 —— 豆包传错字段名不报错、直接走默认值，
huashu 的 `doc_count` bug 就是这么潜伏下来的。

### 其他端点（本 skill 未使用）

`/v1/tasks/*`（深度研究，含 TaskGroup 批量）、`/v1beta/findall/*`（实体发现）、
`/v1/monitors/*`（定期监测网页变化）、`/v1/responses`（OpenAI Responses 兼容接口，
`model="parallel"`、`reasoning.effort` 控制研究深度、返回带 URL 引用标注）。
这些能力已有官方 skill 覆盖，gr-search 专注搜索本身，不重复造。
