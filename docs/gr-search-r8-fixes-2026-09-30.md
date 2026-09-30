# gr-search 第八期审核优化记录

日期：2026-09-30。工作区版本：1.2.8 → 1.2.9。

依据：[第八期审核](gr-search-code-review-2026-09-30-r8.md)。本轮同时处理中文资料关键词的 P3，以及用户明确要求的标题自动链接、裸网址观察。

## 行为变化

| 问题 | 修复 |
| --- | --- |
| 中文“资料／参考／文献”子串误保护站点栏目 | 改用参考资料、参考文献、相关资料、学习资料、官方资料、官方文档等明确短语；公司资料、个人资料、投资参考、今日参考价等标题不再保护标签菜单 |
| 标题直接写 URL 时，路径词仍参与资料判定 | 在判定文字中剥离 `<https://…>` 自动链接及裸 `http://`、`https://` URL，支持大小写；网址中的资料关键词和排除词均不参与判定 |

剥离只作用于章节判定文字。展示中的原始标题、网址、正文和落盘内容保留；网址前后的真实“参考资料”短语仍能保护引用。已有 Markdown 链接解析、一级及普通资料章节的保护范围保持原有行为。

## 修改文件

- `skills/gr-search/scripts/render.py`：明确中文资料短语，剥离标题自动链接和裸 URL。
- `skills/gr-search/SKILL.md`：1.2.9 版本及相应行为说明。
- `tests/gr-search/test_r8_regressions.py`：66 项完整渲染回归，覆盖三种标题形式、中文栏目、真实资料、网址关键词、网址排除词及其前后的真实资料文字。
- `tests/gr-search/mutants.py`：两个 R8 变异体。
- `tests/gr-search/README.md`：验证记录及本文链接。

工作区原有修改保留。旧审核与修复记录作为历史记录保留。

## 验证

66 项新用例在修复前的 1.2.8 上为 **45 failed、21 passed**。修复后结果如下：

| 检查 | 结果 |
| --- | --- |
| R8、R7、R6、R5、历史审核、检索质量、选段七个文件 | 461 passed |
| Python 3.14.7，全仓库，包含性能测试 | 1,374 passed，5 subtests passed |
| Python 3.10.21，gr-search，排除墙钟性能测试 | 1,147 passed，1 deselected，5 subtests passed |
| `mutants.py R8`，完整 gr-search 非性能测试范围 | baseline 1,147 passed；2/2 个变异体均产生真实测试失败 |
| 全部变异体静态检查 | 155 个锚点均存在，替换后 Python 语法有效；未重跑全量变异集 |
| 技能格式检查 | `Skill is valid!` |
| `git diff --check` | 通过 |

使用现有 uv 缓存环境，未新增依赖。实际命令在仓库根目录执行：

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python -m pytest tests/gr-search/test_r8_regressions.py tests/gr-search/test_r7_regressions.py tests/gr-search/test_r6_regressions.py tests/gr-search/test_r5_regressions.py tests/gr-search/test_review_regressions.py tests/gr-search/test_retrieval_quality.py tests/gr-search/test_passages.py -q -p no:cacheprovider --tb=short
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python -m pytest -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/w1yEGG3SFb2KUU2D/bin/python -m pytest tests/gr-search/ -q -p no:cacheprovider -m 'not perf'
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python tests/gr-search/mutants.py R8
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/ckn48gSxo1MW3lzT/bin/python /Users/linnan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/gr-search
git diff --check
```

## 真实正文与离线回放

同一批 23 次落盘、415 篇正文，分别载入修复前的 1.2.8 快照与修复后的脚本，直接调用分段及导航判定：

| 版本 | 有导航单元的正文 | 被判为导航的单元 |
| --- | ---: | ---: |
| 1.2.8 | 12 | 155 |
| 1.2.9 | 12 | 155 |

逐篇比较导航单元哈希，415 篇均无变化。该结果只证明这批样本的判定未退化，不代表所有网站的分类都正确。

两份 9 月 29 日的双源 raw，日期冻结为采集日，两个版本各按三档预算回放，共 12 次渲染。前后输出逐字符一致，均未超预算，源调用数为 0：

| 查询 | 8,000 档字符数 | 15,000 档字符数 | 30,000 档字符数 |
| --- | ---: | ---: | ---: |
| 北京天气 | 7,664 | 13,905 | 18,895 |
| 最新的 AI 研究 | 7,370 | 14,508 | 25,767 |

三档天气输出中的“微信公众号”“扫码随时看天气”“台风列表”“老黄历”均为零。

实际命令：

```bash
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python /private/tmp/gr_search_r8_corpus.py
PYTHONDONTWRITEBYTECODE=1 /Users/linnan/.cache/uv/archive-v0/4wDfp5ZdOGZS7g64/bin/python /private/tmp/gr_search_r8_replay.py
```

快照、导航单元哈希和回放结果仅保存在本机临时目录，没有将 raw 添加为测试 fixture：

`/var/folders/y8/7kv3_9s97tl4j6q1y1_8ldjc0000gn/T/gr-search-r8-fix-r1zofx1j/`

## 限制

资料标题与导航判定仍是启发式，未列入明确短语的陌生资料标题可能不能保护短引用。本轮未新增联网搜索、模型作答或质量评分，不将样本一致性解释为检索质量提升。

已安装的 `/Users/linnan/.agents/skills/gr-search/` 仍为 1.2.2，尚未同步；1.2.9 当前仅在工作区生效。
