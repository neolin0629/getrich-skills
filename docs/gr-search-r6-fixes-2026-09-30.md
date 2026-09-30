# gr-search 第六期审核修复记录

日期：2026-09-30。工作区版本：1.2.6 → 1.2.7。

依据：[第六期审核](gr-search-code-review-2026-09-30-r6.md)。两个 P3 已修复；工作区原有修改保留。

## 行为变化

1. **历史比分、汇率按年份解释。** 只有股价主题（`股价`、`stock price`）中的裸四位数字默认按价格解释。天气、比分、汇率中的过去年份不再触发隐式日级时效。例如 `2022世界杯决赛比分`、`比分 2018 欧冠决赛`、`2022 World Cup final live score`、`美元兑人民币汇率2019`，均不收紧为 120 秒缓存，也不因日级陈旧惩罚而把历史首条结果调到今日结果之后。显式「年」、英文年份语境、货币或点位单位和价格动词的覆盖规则保留。
2. **常见阅读章节保留短资料链接。** 扩充 `See also`、`Further reading`、`Related`、`Links`、`Bibliography` 以及中文阅读、相关链接、外部链接、推荐资源等标题识别。没有把任意“相关”“推荐”子串都当成资料语境。同级章节会重置保护范围，明确的纯文本导航标签仍优先过滤。

## 修改文件

| 文件 | 用途 |
| --- | --- |
| `skills/gr-search/scripts/fusion.py` | 裸年份默认解释仅为股价保留价格例外 |
| `skills/gr-search/scripts/render.py` | 阅读及资料章节标题规则 |
| `skills/gr-search/SKILL.md` | 1.2.7 版本及对应行为说明 |
| `tests/gr-search/test_r6_regressions.py` | 85 项回归：实际查询 TTL、排序，短正文与预算选段，三种标题形式，资料保护范围及菜单过滤 |
| `tests/gr-search/test_r5_regressions.py` | 将 `汇率2000`、`比分2019` 的旧预期改为历史；r6 已确认原预期有误 |
| `tests/gr-search/mutants.py` | 两个 R6 变异体，并更新因年份变量调整而变化的旧锚点 |
| `tests/gr-search/README.md` | 验证记录及本文链接 |

## 验证结果

新增用例在修复前的 1.2.6 上为 **61 failed、24 passed**，确认能复现两类问题。修复后：

| 检查 | 结果 |
| --- | --- |
| R6、R5、历史审核、检索质量、选段五个文件 | 334 passed |
| Python 3.14.7，全仓库，包含性能测试 | 1,247 passed，5 subtests passed |
| Python 3.10，gr-search，排除墙钟性能测试 | 1,020 passed，1 deselected，5 subtests passed |
| 持久脚本 `mutants.py R6`，完整 gr-search 非性能测试范围 | baseline 1,020 passed；2/2 个变异体产生真实测试失败 |
| 全部变异体静态检查 | 149 个锚点均存在，替换后语法有效；未重跑全部变异体 |
| 技能格式检查 | `Skill is valid!` |
| `git diff --check` | 通过 |

实际命令（仓库根目录）如下。Python 3.14 的环境由 uv 准备，包含 pytest 和 click：

```bash
uv run --python /opt/homebrew/bin/python3 --with pytest --with click python -m pytest tests/gr-search/test_r6_regressions.py tests/gr-search/test_r5_regressions.py tests/gr-search/test_review_regressions.py tests/gr-search/test_retrieval_quality.py tests/gr-search/test_passages.py -q -p no:cacheprovider --tb=short
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python tests/gr-search/mutants.py R6
uv run --python 3.10 --with pytest --with click python -m pytest tests/gr-search/ -q -p no:cacheprovider -m 'not perf'
uv run --python /opt/homebrew/bin/python3 --with pyyaml python /Users/linnan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/gr-search
git diff --check
```

uv 缓存访问受沙箱限制，经授权准备测试环境后执行。变异脚本仅操作临时副本，基础设施错误不计为捕获。

## 离线回放

复用 9 月 29 日的两份双源 raw，分别载入修复前 1.2.6 快照与修复后的脚本，以采集日冻结日期。
每个版本按 8,000 / 15,000 / 30,000 字符预算回放，共 12 次渲染。源调用为 0，所有前后输出逐字符一致，均未超预算。

| 查询 | 8,000 档字符数 | 15,000 档字符数 | 30,000 档字符数 |
| --- | ---: | ---: | ---: |
| 北京天气 | 7,664 | 13,905 | 18,895 |
| 最新的 AI 研究 | 7,370 | 14,508 | 25,767 |

三档天气输出中的“微信公众号”“扫码随时看天气”“台风列表”“老黄历”均为零；现有 tianqi/eastday 和 OpenAI 类导航回归仍通过。

实际命令：

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python /private/tmp/gr_search_r6_replay.py
```

快照和回放结果仅保存在本机临时目录，未添加原始数据 fixture：

`/var/folders/y8/7kv3_9s97tl4j6q1y1_8ldjc0000gn/T/gr-search-r6-fix-d0r7no3d/`

本轮没有新增联网搜索、模型作答或质量评分。标题和年份仍是启发式判断，回放一致不代表消除了所有搜索噪声。

已安装的 `/Users/linnan/.agents/skills/gr-search/` 仍为 1.2.2；本次修复仅在工作区 1.2.7 生效。
