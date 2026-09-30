# gr-search 第五期审核修复记录

日期：2026-09-30。工作区版本：1.2.5 → 1.2.6。

依据：[第五期审核](gr-search-code-review-2026-09-30-r5.md)。本次保留工作区已有修改，只处理审核涉及的行为、回归用例和对应文档；未提交或同步已安装副本。

## 修复结果

| 审核问题 | 本次处理 | 验证 |
| --- | --- | --- |
| 同文菜单误删代码或段落 | 分段记录原始行区间，删除直接使用区间；拆句片段不删除其整个源段落 | 围栏代码、缩进代码、普通段落及长段落均有完整渲染回归 |
| 弹窗名称误合并 SPA | 删除 `_UI_FRAGMENT` 名称规则；保留路径、hashbang 和状态参数，继续剥离文本指令 | 不同正文分别保留、各计 `1/61`；同标题同正文仍经严格内容去重合并 |
| 资料列表被当成导航 | 标题不计票并打断连续段；结合锚文本长度、导航标签和明确资料章节判断 | 普通、链接、Setext 标题 × 2/3/5 条资料 × 中英文全部保留；现有天气菜单用例通过 |
| 带空格价格单位误判年份 | 允许单位前空白，结合价格动词、货币符号和主题判定 | 实际 `run_search()` 的时效标志及 TTL 回归通过 |
| 紧贴中文的历史年份误判实时 | 天气裸数字默认按年份，股价、汇率、比分裸数字默认按数值；显式「年」优先 | 「北京天气2025」「上海天气2024」恢复历史查询 |

`code-review` 子 Agent 未读取本轮结论，独立通过公开入口发现两个补充反例，也已修复并复核：

- `SQLite 官方资料` 章节中的 `SQL Syntax / C API / File Format` 是短标题资料，不能因长度短而全部清空。原复现的 1,100 字符预算下，三个链接全部保留，实际输出 827 字符。
- `AAPL stock price in 2021` 明确要求历史年份。加入 `in/during/for YEAR` 语境判断后，`fresh=False`、`strong_fresh=False`、`cache_ttl=None`，历史资料保持在今日报价之前；带货币单位的数字仍按价格解释。

## 修改文件

- `skills/gr-search/scripts/render.py`：原始行区间、导航和资料判定。
- `skills/gr-search/scripts/fusion.py`：URL 身份、年份与价格区分。
- `skills/gr-search/SKILL.md`：版本与实际行为说明。
- `tests/gr-search/test_r5_regressions.py`：60 项新回归。
- `tests/gr-search/test_review_regressions.py`：删除两个要求任意 portal 路由都与首页等价的旧断言，文本指令用例保留；不同正文和相同正文的替代断言在新文件中。
- `tests/gr-search/mutants.py`：新增 11 个 R5 变异体，替换过时规则并更新锚点。
- `tests/gr-search/README.md` 与本文：验证与限制记录。

## 测试与变异验证

本次直接使用已有 uv 缓存环境，未安装依赖。实际执行的命令如下（均在仓库根目录）：

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/jtXcsbNHuJ6Sd6pk/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/V6TCQlrqrtDHPs6S/bin/python -m pytest tests/gr-search/ -q -p no:cacheprovider -m 'not perf'
```

| 范围 | 结果 |
| --- | --- |
| Python 3.14，全仓库（包含性能测试） | 1,162 passed，5 subtests passed |
| Python 3.10，gr-search，排除墙钟性能测试 | 935 passed，1 deselected，5 subtests passed |
| R5、历史审核、检索质量、选段四个文件 | 249 passed |
| 变异定向验证 | baseline 249 passed；20/20 个变异体均产生真实测试失败 |
| 全部变异体静态检查 | 147 个锚点均存在，替换后 Python 语法有效；未运行全量变异集 |
| `quick_validate.py skills/gr-search` | `Skill is valid!` |
| `git diff --check` | 通过 |

最初在未修复的 1.2.5 上执行首批 48 项新用例，30 项失败、18 项通过；这确认测试能复现故障。后续新增边界用例形成最终 60 项。

变异验证在临时副本中执行。定向驱动 `/private/tmp/gr_search_r5_mutants.py` 调用仓库 `mutants.main()`，标签为 `R5`、`R3`、`空行分隔菜单`，仅将每次 pytest 范围限定为上述四个文件；使用 `-m 'not perf'`，基础设施错误不计捕获。实际命令：

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/jtXcsbNHuJ6Sd6pk/bin/python /private/tmp/gr_search_r5_mutants.py
```

临时驱动清理后，可用持久脚本重新验证同一批变异体（此命令每次运行完整 gr-search 非性能测试，耗时更长）：

```bash
uv run --python "$(which python3)" --with pytest --with click python tests/gr-search/mutants.py R5 R3 空行分隔菜单
```

## 真实结果离线回放

复用 9 月 29 日保存的「北京天气」「最新的 ai 研究」两份 raw。同一题目、同一原始输入，日期冻结为采集日，分别载入修复前 1.2.5 快照和修复后的脚本。每版本三个预算，共 12 次渲染；回放禁止网络及传输子进程，源调用数为 0。

| 查询 | 预算 | 修复前字符数 | 修复后字符数 |
| --- | ---: | ---: | ---: |
| 北京天气 | 8,000 | 7,664 | 7,664 |
| 北京天气 | 15,000 | 13,624 | 13,905 |
| 北京天气 | 30,000 | 20,360 | 18,895 |
| 最新的 AI 研究 | 8,000 | 7,338 | 7,370 |
| 最新的 AI 研究 | 15,000 | 14,613 | 14,508 |
| 最新的 AI 研究 | 30,000 | 25,767 | 25,767 |

全部未超预算，结果数分别保持 19 和 20。逐段查看前后差异后确认：

- 8,000 字符天气输出完全一致。三档均未出现「微信公众号」「扫码随时看天气」「台风列表」「老黄历」这些已过滤的菜单标记；现有真实形态的 tianqi/eastday 测试通过。
- tianqi 当前天气页面仍保留温度、湿度、风向。描述性链接的新规则会保留更多长新闻标题；AI 日报在 15,000 档从往期列表转为保留当期条目。总预算重新分配，因此其他结果也会出现选段变化，并非只有问题所在的一行发生变化。
- 补齐原先“正文能装下就跳过去菜单”的路径：30,000 档也按原始行区间过滤确认的菜单，tianqi/eastday 的上述菜单标记归零；天气实况与逐小时预报保留。代码保护和菜单删除通过三个预算的完整渲染用例验证。

原始数据未加入测试 fixture。修复前快照、回放 JSON 和逐段差异仅保存在本机临时目录：

`/var/folders/y8/7kv3_9s97tl4j6q1y1_8ldjc0000gn/T/gr-search-r5-fix-dion9wx4/`

实际回放命令：

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/jtXcsbNHuJ6Sd6pk/bin/python /private/tmp/gr_search_r5_replay.py
```

## 剩余限制

菜单过滤作用于带查询目标的搜索展示，原始落盘正文不改动。导航与资料的判断仍是启发式。没有明确资料语境的短链接清单仍可能歧义；保留长标题也可能增加相关新闻噪声。未进行新的联网采样、模型作答或质量评分，字符数不代表质量分数。

已安装的 `/Users/linnan/.agents/skills/gr-search/` 未改动，仍是 1.2.2；本次修复仅在工作区 1.2.6 生效。
