# gr-search 代码审核（第四期）：1.2.5 独立复审

日期：2026-09-30

对象：工作区未提交的 `1.2.5`。

参考：[第三期审核](/Volumes/myssd/project/getrich-skills/docs/gr-search-code-review-2026-09-30-r3.md)、[1.2.5 修复记录](/Volumes/myssd/project/getrich-skills/tests/gr-search/README.md:490)。

## 结论

**确认 3 个 P2、1 个 P3。** 两个 P2 是本次修复引入的问题，另一个 P2 和 P3 属于旧问题未完整修复。
原有的“链接标题与后续数据使用单换行时丢失天气数据”反例已修复，普通标题下的两条资料链接也已保留。

| 级别 | 问题 | 状态 |
| --- | --- | --- |
| P2 | 菜单删除可能命中前面代码块中的同文行，清空代码而留下实际菜单 | 本次新增回归 |
| P2 | 通用弹窗 fragment 规则把合法 SPA 内容路由与首页合并 | 本次新增规则造成的误合并 |
| P2 | 链接标题计入菜单数量后，两条相关资料链接仍全部消失；三条以上的资料列表也被过滤 | 原问题仅部分修复 |
| P3 | 价格与货币单位之间有空格时，价格仍被当成历史年份 | R3 P3-1 未完整修复 |

本轮使用新的 `code-review` 子 Agent 独立审查；主 Agent 复核 R3 反例、追加组合输入并运行测试。
所有发现均有离线复现，不依据版本号或修复说明直接判定通过。本轮只新增此报告。

## 1. [P2] 按文本定位菜单会误删代码块

**位置**：[render.py:594](/Volumes/myssd/project/getrich-skills/skills/gr-search/scripts/render.py:594)，594–597 行。

`_drop_units()` 接收的是待删单元的文字，没有原始行位置。它从文件开头查找第一次出现的同文行，
而 `cursor` 只在待删单元之间推进。当代码示例先包含菜单模板，真正导航稍后出现时，
查找命中代码里的内容，绕过了分段阶段对代码块的保护。

### 复现

```python
menu = (
    "* [首页](https://nav.example/home)\n"
    "* [天气](https://nav.example/weather)\n"
    "* [新闻](https://nav.example/news)"
)
body = "```text\n" + menu + "\n```\n\n" + menu + "\n\n" + "背景说明。" * 500
```

查询“菜单模板”，单条豆包正文，使用完整 `render.render()` 的 `compact/8000` 入口。
当前输出中的代码块变为：

````text
```text
```
````

而代码块后真正的三行菜单仍保留。对照修复前 1.2.3 快照，相同输入的代码块完整保留。
这不是选段省略整个代码块，而是在代码围栏内部删除了原有内容，可能使用户复制错误示例。
完整 `docs[].body` 不受本次渲染删除影响。

**建议**：分段时携带原始行区间，按区间删除；若需要重新定位，应连同保留单元一起追踪位置。
增加“代码块先出现相同菜单、真实菜单后出现”的全链路回归，验证代码逐行保留且真实导航被剔除。

## 2. [P2] 弹窗例外错误归并合法 SPA 路由

**位置**：[fusion.py:126](/Volumes/myssd/project/getrich-skills/skills/gr-search/scripts/fusion.py:126)，126–127 行；
匹配表位于 [fusion.py:31](/Volumes/myssd/project/getrich-skills/skills/gr-search/scripts/fusion.py:31)。

`_UI_FRAGMENT` 在任意站点上把 `portal`、`login`、`account`、`search` 等名称及其子路径当成弹窗。
但这些名称也可以是独立内容路由。Ghost 博客的 `#/portal/` 样本不足以证明其他站点的同名路由等价于首页。

### 复现

| 输入 URL | 当前 `canonical_url()` |
| --- | --- |
| `https://app.example/` | `//app.example/` |
| `https://app.example/#/login` | `//app.example/` |
| `https://app.example/#/portal/reports` | `//app.example/` |

分别向 `merge()` 传入首页和路由页面两条 `Doc`，标题、正文不同，来自不同源，名次均为 1。
实测只保留一条正文，并标为 `{'doubao': 1, 'parallel': 1}`；RRF 合计为 `2/61`，
而独立页面本应各自保留、各为 `1/61`。作为对照，`#/install` 仍能与首页分开。

该规则重新引入了不同资源被错误折叠的问题，影响正常结果层的证据完整性及排名。
本轮直接验证当前行为，没有用尚未修复 fragment 的旧 1.2.3 来证明版本间差异。

**建议**：只有能确认属于同页弹窗时才去掉 fragment；缺少站点或页面证据时保留路由，
或交由已有的严格正文等价规则去重。浏览器文本高亮 `:~:text=` 可以单独处理。
补充首页与 `#/portal/reports`、`#/account/profile` 等内容路由同时返回时的正文保留和来源计分用例。

## 3. [P2] 链接标题使两条正文资料重新被判为导航

**位置**：[render.py:305](/Volumes/myssd/project/getrich-skills/skills/gr-search/scripts/render.py:305)，305–311 行。

把菜单门槛从 2 提高到 3，只解决了普通标题下恰好两条资料链接的样例。
链接形式的标题自身也会贡献一条链接，从而让标题和两条正文资料全部被判为菜单。

### 复现

```python
refs = (
    "- [Python 3.14 官方文档](https://docs.python.org/3.14/)\n\n"
    "- [Python 3.14 更新说明](https://docs.python.org/3.14/whatsnew/3.14.html)\n\n"
)
heading = "[# Python 3.14 官方资料](https://article.example/python)"
body = heading + "\n\n" + refs + "背景说明与历史沿革。" * 400
```

查询“Python 3.14 官方资料”，单条豆包正文，完整 `compact/8000` 渲染：

| 标题形式 | 当前输出字符数 | 两个资料链接 |
| --- | ---: | --- |
| 普通 `# Python 3.14 官方资料` | 427 | 均保留 |
| `[# Python 3.14 官方资料](url)` | 2245 | 均丢失，输出背景说明 |

旧 1.2.3 的链接标题样例输出 461 字符，两个链接均保留。当前将普通标题下的资料扩展为三条或四条时，
所有资料链接也会消失。因此这是原导航问题未完整修复，不能只用两链接回归通过来判定已解决。

**建议**：标题不应进入菜单计数；正文资源、参考资料列表不能仅凭链接数量删除。
同时测试普通标题、链接标题、两条及多条相关资料，并保留真实门户菜单的过滤回归。

## 4. [P3] 带空格的货币单位仍不能阻止年份误判

**位置**：[fusion.py:333](/Volumes/myssd/project/getrich-skills/skills/gr-search/scripts/fusion.py:333)，333–334 行。

独立四位数字规则只检查数字周围的空白或句读，没有继续识别后面的货币单位。
“2000元”现在按价格处理，但常见的“2000 元”或“2000 USD”仍被当作历史年份。
这些输入已经有明确单位，不属于 README 中披露的裸数字歧义。

### 复现

固定日期为 2026-09-30，替换豆包源为返回合成结果的本地函数，完整调用 `run_search()`，
使用 `--source doubao --no-cache --no-dump --json`，不设置显式时效参数：

| 查询 | `fresh` / `strong_fresh` | 传给源的时效缓存覆盖 |
| --- | --- | --- |
| 茅台股价 2000元 | True / True | 120 秒 |
| 茅台股价 2000 元 | False / False | 无，正常启用缓存时使用普通 TTL |
| stock price below 2000 USD | False / False | 无，正常启用缓存时使用普通 TTL |

对“茅台股价跌破 1999 元”的直接判定也为 False。漏判同时失去日级排序和短缓存策略。
探测关闭了实际缓存访问；表中仅记录传给源的 TTL 参数，没有测量缓存命中。
使用已支持的“股价 / stock price”主题，避免把主题覆盖不足误认为日期规则的问题。

**建议**：识别四位年份时排除数字后允许空白的货币或点位单位；保留“北京天气 2025”等历史查询的判断。
补充中文带空格单位和英文货币单位用例，不仅验证无空格的价格表达。

## R3 问题的当前状态

| R3 项目 | 本轮核验 |
| --- | --- |
| followup P2-1：资料链接丢失 | 普通标题加两条链接通过；链接标题及更多资料仍失败，见问题 3 |
| followup P2-2：链接标题吞掉数据 | 单换行、空行两种形式均保留温度、预报和湿度 |
| P3-1：价格数字当年份 | 无空格价格通过；带空格单位仍失败，见问题 4 |
| P3-2：弹窗与文本高亮 fragment | 已增加清理规则，但泛化到其他站点会误并合法路由，见问题 2 |
| P3-3：短占位密钥破坏错误文字 | `test` 独立出现时脱敏，`latest`、`contest` 保留；本轮未确认新问题 |
| P3-4：无上下文纯数值列表 | 连续纯风力数值反例的回归通过；仍为 README 已说明的启发式限制，不声称所有数值上下文均已解决 |
| P3-5：回退拆坏表格 | 原始表格连续行及代码空行用例通过；新删除方式的代码定位回归见问题 1 |

## 验证方式与限制

实际执行命令：

```bash
# Python 3.14，当前 gr-search 全量测试，包含性能用例
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/jtXcsbNHuJ6Sd6pk/bin/python \
  -m pytest tests/gr-search/ -q -p no:cacheprovider

# Python 3.10，审核回归与 benchmark 的定向测试
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/V6TCQlrqrtDHPs6S/bin/python \
  -m pytest tests/gr-search/test_review_regressions.py tests/gr-search/benchmark/test_benchmark.py \
  -q -p no:cacheprovider
```

结果分别为 **878 passed、5 subtests passed** 和 **107 passed、5 subtests passed**。
缓存解释器路径仅记录本机环境。上述测试通过，但没有覆盖本轮确认的四个反例。
`git diff --check` 通过；审核期间记录的 27 个技能和测试文件哈希均未改变。

正文复现统一使用单条 `Merged`，`body_source='doubao'`、`sources={'doubao': 1}`，
通过完整 `render.render()`，预算 8000、档位 `compact`；不是仅对内部极小预算函数做探测。
输出字符数含元信息，复现时更换标题、站点名或尾部路径会使其略有差异；是否保留证据才是判断标准。

代码块和链接标题组合问题由独立子 Agent 发现，主 Agent 交叉复现；SPA 路由及带单位价格问题由主 Agent
使用合成输入确认，子 Agent 另行复核了 SPA 规则的性质。短密钥异常出口和 benchmark 显式时效重算
也在审查范围内，未确认额外新缺陷。

本轮未联网、未读取真实配置或凭据、未重跑真实 raw 或变异集，也未重新进行答案质量评分。
安装目录仍标注 1.2.2；本轮以工作区 1.2.5 为修复复审对象，没有同步安装副本或修改代码。
