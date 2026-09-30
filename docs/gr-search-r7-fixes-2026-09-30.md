# gr-search 第七期审核优化记录

日期：2026-09-30。工作区版本：1.2.7 → 1.2.8。

依据：[第七期审核](gr-search-code-review-2026-09-30-r7.md)。两个 P3 均已处理，改动集中在资料章节识别及其范围；年份、价格、URL 去重逻辑没有改动。

## 行为变化

| 问题 | 处理 |
| --- | --- |
| `related`、`links`、`阅读`误保护推荐及页脚菜单 | 改为明确短语，如 `Related reading`、`Related resources`、`Useful links`、`External links`、相关阅读、延伸阅读、推荐阅读；额外排除 posts、articles、stories、topics、quick、featured、排行、热门修饰词 |
| URL 或属性中的关键词被当成标题语义 | 只使用可见标题文字：剥离标题标记、链接目标、title 属性及 Setext 下划线；目标地址中的平衡括号和转义字符一并处理，避免留下 `/resources` 等残片 |
| 一级资料标题使后文全部获得保护 | 一级标题只保护到下一个任意层级标题，保留其紧邻的真实引用；二级及更低资料章节仍可保护下级小节，到同级或更高级标题重置 |

采用一级标题的范围限制，而不是完全禁用一级资料标题：已有 `# SQLite references` 等真实资料清单继续保留，后续正文中的菜单恢复正常判定。明确纯文本导航标签仍优先过滤。

`Quick Links`、`Related`、`阅读排行`、`Related Posts`、`Featured Links`、`AI-related report` 等反例不再为短菜单提供保护。链接标题 `[# 北京天气](https://w.example/resources/bj)` 的 URL 也不提供保护。

## 修改文件

- `skills/gr-search/scripts/render.py`：明确资料短语、排除修饰词、标题文字提取和保护范围。
- `skills/gr-search/SKILL.md`：1.2.8 版本及实际规则。
- `tests/gr-search/test_r7_regressions.py`：61 项完整渲染回归，覆盖三种标题、推荐菜单、真正资料、URL/title 属性、带括号链接以及章节边界。
- `tests/gr-search/mutants.py`：四个 R7 变异体；更新 R6 资料匹配变异体的代码锚点。
- `tests/gr-search/README.md`：验证记录及本文链接。

工作区已有修改均保留，旧审核及修复记录保持为历史记录。

## 测试

首批 58 项新用例在未修复的 1.2.7 上为 **43 failed、15 passed**。修复标题基本处理后，额外加入三个带括号链接地址用例，均能复现关键词残留；补齐处理后全部通过。

| 检查 | 最终结果 |
| --- | --- |
| R7、R6、R5、历史审核、检索质量、选段六个文件 | 395 passed |
| Python 3.14.7，全仓库，包含性能测试 | 1,308 passed，5 subtests passed |
| Python 3.10.21，gr-search，排除墙钟性能测试 | 1,081 passed，1 deselected，5 subtests passed |
| `mutants.py R7`，完整 gr-search 非性能测试范围 | baseline 1,081 passed；4/4 个变异体均产生真实测试失败 |
| 全部变异体静态检查 | 153 个锚点均存在，替换后 Python 语法有效；未重跑全量变异集 |
| 技能格式检查 | `Skill is valid!` |
| `git diff --check` | 通过 |

使用现有 uv 缓存环境，未新增依赖。实际命令在仓库根目录执行：

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python -m pytest tests/gr-search/test_r7_regressions.py tests/gr-search/test_r6_regressions.py tests/gr-search/test_r5_regressions.py tests/gr-search/test_review_regressions.py tests/gr-search/test_retrieval_quality.py tests/gr-search/test_passages.py -q -p no:cacheprovider --tb=short
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/w1yEGG3SFb2KUU2D/bin/python -m pytest tests/gr-search/ -q -p no:cacheprovider -m 'not perf'
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python tests/gr-search/mutants.py R7
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/ckn48gSxo1MW3lzT/bin/python /Users/linnan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/gr-search
git diff --check
```

## 真实正文对比

按 r7 建议，对同一批 **23 次落盘、415 篇正文**分别载入修复前 1.2.7 快照与最终 1.2.8。直接调用分段与导航判定，以 `_navigation_units` 返回 True 的单元为统计口径：

| 版本 | 触发导航判定的正文 | 导航单元 |
| --- | ---: | ---: |
| 1.2.7 | 12 | 155 |
| 1.2.8 | 12 | 155 |

不仅总数相同，逐篇比较被判为导航的单元哈希，**415 篇均无变化**。该检查验证这批正文的分类未退化，不代表在所有网站上都能准确区分菜单与引用。

此外，复用 9 月 29 日的「北京天气」「最新的 AI 研究」双源 raw，冻结采集日，两个版本分别按三个预算展示，共 12 次渲染。前后输出逐字符一致，无超预算，源调用为 0：

| 查询 | 8,000 档字符数 | 15,000 档字符数 | 30,000 档字符数 |
| --- | ---: | ---: | ---: |
| 北京天气 | 7,664 | 13,905 | 18,895 |
| 最新的 AI 研究 | 7,370 | 14,508 | 25,767 |

三档天气输出中的“微信公众号”“扫码随时看天气”“台风列表”“老黄历”均为零。

实际命令：

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python /private/tmp/gr_search_r7_corpus.py
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python /private/tmp/gr_search_r7_replay.py
```

快照、导航单元哈希和回放结果仅保存在本机临时目录；没有将 raw 加入测试 fixture：

`/var/folders/y8/7kv3_9s97tl4j6q1y1_8ldjc0000gn/T/gr-search-r7-fix-txps_u24/`

## 限制

章节短语和菜单判定仍是启发式，陌生资料标题或模糊的短链接清单仍可能被误判。本轮没有新增联网搜索、模型作答或质量评分，不将回放一致或字符数当成检索质量分数。

已安装的 `/Users/linnan/.agents/skills/gr-search/` 尚未同步；1.2.8 当前仅在工作区生效。
