# gr-search 测试

## 跑

仓库里没有 `pyproject.toml`（这是个 skills 仓库，不是 Python 项目），
所以用 `uv run --with` 临时拉 pytest，不落任何依赖文件：

```bash
uv run --python "$(which python3)" --with pytest --with click pytest tests/gr-search/ -q
```

`--python "$(which python3)"` 不能省。SKILL.md 里跑脚本用的是系统 `python3`，
而 `uv run` 默认会自己挑一个解释器——两者不同版本时，版本相关的行为就漏测了。
真实踩过：`date.fromisoformat("20260904")` 在 3.11+ 接受、3.10 拒绝，
测试跑在 3.10 上时那个缺陷根本复现不出来。

也建议在支持的最低版本上跑一遍（本仓库是 3.10）：

```bash
uv run --python 3.10 --with pytest --with click pytest tests/gr-search/ -q
```

只跑某一类：

```bash
uv run --python "$(which python3)" --with pytest --with click pytest tests/gr-search/test_fence.py -q
```

`--with click` 是给 `test_dash_objective_survives_click_parsing` 用的：
它拿**真实的 click 解析器**验证以 `-` 开头的 objective 确实被当成位置参数。
只断言"我们拼了 `--`"是不够的——那还是在照惯例假设解析器的行为。

**所有用例都不触网、不读写用户真实配置。** 涉及配置的走 `tmp_path`，
涉及源调用的注入假函数，跑真实 CLI 的子进程换掉 `HOME`。

## 文件

| 文件 | 守什么 |
| --- | --- |
| `test_fence.py` | 不可信内容围栏。整个 skill 的安全模型只有这一条 |
| `test_budget.py` | 输出预算：既不许超支，也不许把正文挤光 |
| `test_fetch.py` | `--max-chars` 是 stdout 总预算；fetch 路径的围栏 |
| `test_config.py` | 坏配置不得让 `config doctor` 自己起不来；密钥权限；缓存清理 |
| `test_fusion.py` | 时效判定、URL 归一化、去重、RRF 排序 |
| `test_cli.py` | 输入校验先于源调用；session 语义；缓存指纹；时效判定范围；dry-run |
| `mutants.py` | 变异自检脚本（非 pytest 用例，单独跑，见下） |

标了 `@pytest.mark.perf` 的是墙钟性能断言，会因机器负载偶发变红。
正常运行照跑，变异自检时用 `-m "not perf"` 排除——那种红不代表"变异被抓住"，
只会制造假阳性。

## 写新用例时

这套测试是三轮独立审核逐条打出来的，几乎每个用例背后都有一个真实塌过的缺陷，
docstring 里写的就是当时的故障现象。**加断言时请一并写清它防的是什么**——
"assert 长度 <= budget" 谁都看得懂，但看不出它防的是"一个 10000 字符的标题
把输出撑到两万"。

两类失败要分开守，历史上两边都塌过：

- **超支**：上游字段无上限 → 一条结果击穿整个预算；
- **欠支**：预算被元信息吃光 → 结果全变成光秃秃的标题，一条摘要都没有。

第二种更隐蔽：输出看着正常、长度也没超，但最有价值的内容没了。
用例的元信息长度必须贴近真实（见 `test_budget.heavy`）——
字段太短就撑不满预算，也就复现不出这类故障。

**预算类的边界不要手挑，扫网格。** 这条是两次栽跟头换来的：手挑的
n=6 / budget 400~1200 恰好避开了全部真正会超的组合（n=1 / budget 425、450…）。
参见 `test_budget_holds_across_the_grid`。

低于硬下限时允许超预算——围栏永远不参与截断。但超出量必须有界、不随输入增长，
这条由 `test_below_floor_output_is_bounded` 和 `test_combined_floor_does_not_track_input` 守。

下限随**段的种类**抬高（各段都要保住"首条"），也随字段是否极端而不同。
当前扫出来的实测值（超支只出现在这个 budget 以下）：

| 模式 | 正常字段 | 极端字段 |
| --- | --- | --- |
| 文本 | ≤298 | ≤388 |
| 图片 | ≤199 | ≤250 |
| fetch | — | ≤175 |

段的种类抬高下限是设计使然，段的**规模**（结果数、字段长度）抬高下限就是缺陷——
这条界线才是这几个用例真正在守的东西。这些数字都是扫出来的，不是估的；
改动相关逻辑后重新扫一遍再改常量。

**同一类缺陷要在中英文两侧都修。** `now` 命中 `snowflake` 那次只修了英文正则，
中文侧仍是裸子串——`日本月刊`/`成本月度`命中「本月」、`出现在`命中「现在」、
`应当前往`命中「当前」，整整晚了几轮才被发现。修边界类问题时把两种语言一起过一遍。

**同一类缺陷也要在所有调用点都修。** 上一条的兄弟版本：`parallel-cli` 的自由文本
被 click 当成选项，`search` 那条（objective）修了 `--` 终止符，同一个文件里的
`extract`（URL 位置参数）漏了一整轮——而 URL 多半来自上一次 search 落盘 JSON 的
`docs[].url`，是上游可控字段。修完一处就 grep 一遍还有谁在拼同样形状的 argv。

**别让每个字段各自取上限。** 这条踩了两次：图片行的 URL 300 + 描述 40 + note 20，
以及元信息行的标题 200 + 站点 80 + URL 300 + 如意 40——每个字段都"没超自己的
上限"，加起来却让无条件输出的首条撑到 1164 字符。一行要共用一份额度，
见 `render_images` 和 `_meta_line`。

**边界写太松等于没写。** 这条栽过四次：`test_floor_is_bounded_and_input_independent`
一度断言 `< 2000`，于是 1164 的超额一路绿灯；`test_render_images_respects_its_own_budget`
写成 `<= budget or len(table) < 200`，那个 `or` 让 24 和 43 字符的超额全都溜过去；
来源行的断言留了 `+ 40` 的宽限，正好盖住 84 字符的超额；
兜底截断的断言写 `< 500`，盖住了"逐段削减退化成只裁正文"（233 → 300）。
上限要贴着实测值留一点余量，断言里不要留逃生门。

**还要确认自己测的是不是那个东西。** `_assemble` 返回的 overflow 是**削减之前**的值，
拿它去断言"逐段削减在起作用"永远测不出来——削减做没做它都一样。
要测削减就得测 `render()` 最终输出的长度。

**防线冗余会让端到端断言失明。** 图片行有两道防线（按比例分配上限、首行收尾截断），
单独打掉任何一道都只造成几十字符超额，又被另一道和 `render()` 出口的兜底吸收掉——
整体渲染的断言完全看不见。所以每个分段都要有**直接针对它自己**的用例
（`test_render_images_respects_its_own_budget`、`test_meta_line_respects_its_own_budget`…），
并用 `_assemble` 断言"正常预算下压根不需要兜底"
（`test_no_segment_overspends_before_the_safety_net`）。

`render()` 出口还有一道兜底截断：分段核算难免有个位数偏差（分隔空行、比例取整、
省略提示），而"总预算是硬上限"是对外承诺。与其指望每一处都算得分毫不差，
不如在出口把不变量兜住——只压缩围栏内的正文，围栏和抬头绝不参与截断。

### 变异自检

`mutants.py` 把每个已修缺陷逐个"改回去"，确认对应用例真的会红：

```bash
uv run --python "$(which python3)" --with pytest --with click python tests/gr-search/mutants.py
```

**它不碰当前工作树**：整个 skill 先复制到临时目录，变异只发生在副本上。
就地改写再 `finally` 还原在正常结束时确实能逐字节恢复，但 SIGKILL、断电或
并发编辑都可能留下一个变异体，甚至覆盖未提交的修改——复制到临时目录才是程序保证。

判定也必须严格：pytest 退出码里只有 **1** 表示"有用例失败"，2/3/4/5 是中断、
内部错误、用法错误、没收集到用例，那是测试基础设施坏了，不是变异被抓住。
脚本还会先跑一次 baseline，不绿就立即中止——基线不绿时每个变异体都会被误判成已捕获。

**别对 CLI 的参数解析想当然。** objective 直接跟在 `parallel-cli search` 后面，
以 `-` 开头时被 click 当成选项——`--help` 让 CLI 打印帮助后**正常退出**却不写结果，
我们随后崩在 JSONDecodeError 上。修法是 `["--", objective]`，
并且用 CLI 自带的那份 click 跑一遍验证（`test_dash_objective_survives_click_parsing`），
而不是"`--` 一般都支持"。

**裁掉内容时不要许无法兑现的承诺。** "见落盘 JSON" 在 `--no-dump` 或落盘失败时
就是谎话——那些内容事实上已经无法恢复。这种谎比省略本身更糟，它让人以为还有得救。
落盘状态要一路传到每个会裁剪的分段（`render_cards` / `render_results` / `_fit_errors`）。

这一步抓到过五次漏网，原因各不相同，都值得记住：

1. 用例数据太短——元信息撑不满预算，复现不出"正文被挤光"；
2. 扫描范围太窄——手挑的 budget 点全部避开了真正会超的组合；
3. 跑错 Python 版本——3.10 上 `fromisoformat` 的行为与 3.11+ 不同；
4. 变异体本身改得不彻底——只替换了多行字符串的第一行；
5. 修了代码却忘了配套用例——变异体照样绿；
6. 断言自己踩了子串陷阱——`fingerprint(parallel_secret)` 里含有子串
   `print(parallel_secret)`，裸 `in` 判断误报。和 `now` 命中 `snowflake`
   是同一个坑，这次栽在测试代码里；
7. 用例只在一种模式下用了极端数据——`test_no_segment_overspends_before_the_safety_net`
   的非图片分支用的是普通 `doc()`，字段太短撑不满预算；
8. 断言测错了对象——见上面 `_assemble` 的 overflow；
9. 变异体本身是非法 Python——pytest exit 4，被判为基础设施故障（这是对的，
   但清单要修好，否则那个缺陷等于没被覆盖）。

**等价变异体**：有些防线是冗余的，单独打掉任何一道都被另一道吸收
（图片行的两道、来源行的两道）。这类要合并成**一个同时退掉两道**的变异体，
而不是留两个永远抓不住的。

不做这一步的话，这些用例会一直绿着，而它们本该守的缺陷毫发无伤。
