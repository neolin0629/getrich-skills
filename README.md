# getrich-skills

一套面向联网搜索、中文内容创作和 Obsidian 文档处理的 AI Skill 集合，适用于 Claude Code、Codex 等支持 Skill 的 Agent。

## 安装

将全部 Skill 全局安装到 Claude Code 和 Codex：

```bash
npx skills add neolin0629/getrich-skills -a claude-code -a codex -g -y
```

只安装其中一个 Skill，用 `--skill` 指定名称：

```bash
npx skills add neolin0629/getrich-skills --skill gr-search -a claude-code -g -y
```

全局安装的文件位于 `~/.agents/skills/<skill-name>/`，再链接到各 Agent 的 Skill 目录。用 `npx skills list -g` 可以查看实际路径。安装完成后，重启对应的 AI 客户端。

后续更新或卸载：

```bash
npx skills update -g
npx skills remove -g --skill gr-search
```

如果只想试用、不安装，可以用 `npx skills use neolin0629/getrich-skills@gr-search` 生成一段使用该 Skill 的提示词。

## Skill 一览

| Skill | 功能 |
| --- | --- |
| `gr-search` | 同时调用豆包搜索和 Parallel，去重融合后按字符预算选取相关段落，支持图片搜索与正文抓取 |
| `gr-chinese-typography-rules` | 检查或统一中文排版，覆盖中英文空格、标点、引号、数字、日期和金融表达，附机械自检脚本 |
| `gr-content-ai-avoid` | 保留事实与作者风格，按 6 层、39 条规则减少套话，提供脚本候选与人工复核 |
| `gr-ob-fix-color-tags` | 用全角括号包裹 Obsidian 笔记中的十六进制颜色代码（`#FFFFFF` → `（#FFFFFF）`），避免被识别为标签；处理前会询问目标目录 |
| `gr-ob-rm-prompts-formatter` | 批量删除 Obsidian 笔记开头的 YAML frontmatter，默认处理 `prompts/` 目录，可指定其他目录 |

安装后，可以直接描述任务，也可以显式指定 Skill 名称。例如：

```text
使用 gr-search 搜索豆包搜索的计费方式
使用 gr-chinese-typography-rules 检查这篇稿子的排版
```

`gr-chinese-typography-rules` 负责排版，`gr-content-ai-avoid` 负责表达；创作中文内容时可配合使用。

两个 `gr-ob-*` Skill 依赖 shell 命令批量改写文件，仅支持 macOS / Linux。`gr-ob-rm-prompts-formatter` 是破坏性操作，执行前请确认目标目录已纳入 Git 且工作区干净，或已提前备份。

## 各 Skill 的特点

### gr-search：兼顾信源覆盖和上下文预算

一次调用并行检索豆包和 Parallel：豆包补中文站点、结构化直答和行业过滤，Parallel 补英文与长尾信源。两路结果等权融合，按问题选取相关正文段落，避免大段搜索结果占满上下文。全量结果保存在本地 JSON 中，追问时可直接读取未展开的内容。跨 URL 只合并标题与正文完全一致的结果，相似页面之间的版本、条件和措辞差异都会保留，便于核对。

### gr-chinese-typography-rules：统一格式时保留原意和技术内容

把中英文空格、标点、数字、日期等常见问题放进同一套检查流程，适合中英文混排的文章、技术文档和数据报告。检查结果区分格式错误、风格建议与语义疑点，原文已有的合法风格优先保留。代码、链接、公式和原文引用受保护；附带脚本定位机械问题，再结合语境复核，每处修改都有依据。

### gr-content-ai-avoid：让表达更具体，同时守住事实和作者风格

从词汇、句法、结构、内容、真实感和格式六个层次检查空泛套话与机械重复，适合文章、社交平台笔记和口播稿。事实、原意和作者风格优先：保留观点力度、限定条件与必要术语，不为增加「真实感」编造经历。39 条规则配合体裁设置、脚本候选和人工复核，只改值得改的段落，合理表达不必为了消除命中而改写。

## gr-search 配置

`gr-search` 只用 Python 标准库，无需 pip 依赖。使用前需要配置两个搜索源的凭据，只配置其中一个时可以用 `--source doubao` 或 `--source parallel` 单源运行。

下面的命令假设 Skill 已全局安装；如果直接在克隆的仓库里运行，把 `GR` 改成 `skills/gr-search`。

```bash
GR=~/.agents/skills/gr-search
```

**豆包**：在[联网搜索控制台](https://console.volcengine.com/search-infinity/api-key)创建 API Key，然后**由你本人在终端**执行下面的命令写入。密钥不会回显，也不会进入命令行历史。不要把密钥发到对话里让 Agent 代填。

```bash
python3 "$GR/scripts/gr_search.py" config set-key doubao
```

**Parallel**（可选，用于补充信源和抓取网页正文）：

- 安装 CLI：`uv tool install "parallel-web-tools[cli]"`。未安装时会自动改用 HTTP 直连。
- 登录：已安装 Parallel 插件的 Claude Code 可以运行 `/parallel-cli-setup` 走 OAuth 登录；也可以在 [Parallel 控制台](https://platform.parallel.ai/home)获取 API Key，再执行 `python3 "$GR/scripts/gr_search.py" config set-key parallel`。换机器时推荐后者，免去每台机器重新登录。

配置完成后检查两个源是否可用：

```bash
python3 "$GR/scripts/gr_search.py" config doctor
```

配置文件位于 `~/.config/gr-search/config.json`。从旧版本升级时，已保存的旧配置会覆盖新版默认值，可以先预览再应用迁移：

```bash
python3 "$GR/scripts/gr_search.py" config migrate-defaults
python3 "$GR/scripts/gr_search.py" config migrate-defaults --apply
```

各 Skill 的具体用法和限制以对应目录内的 `SKILL.md` 为准。

## 目录结构

```text
.
├── .claude-plugin/
│   └── marketplace.json      # Skill 清单
├── skills/                   # 分发给 Agent 的 Skill
│   ├── gr-chinese-typography-rules/
│   ├── gr-content-ai-avoid/
│   ├── gr-ob-fix-color-tags/
│   ├── gr-ob-rm-prompts-formatter/
│   └── gr-search/
├── tests/                    # 测试，不随 Skill 分发
│   ├── gr-chinese-typography-rules/
│   ├── gr-content-ai-avoid/
│   └── gr-search/
└── prompts/                  # 个人提示词库，与 Skill 无关
```

## 开发与测试

测试统一维护在根目录 `tests/` 下，与分发给 Agent 的 `skills/` 解耦。使用 `npx skills add` 安装时只会打包对应的 `skills/<skill-name>` 目录，测试代码不会进入用户的 Agent 目录。

在仓库根目录运行测试（无需安装项目依赖，由 `uv` 临时拉取 pytest）：

```bash
uv run --python "$(which python3)" --with pytest --with click pytest tests/ -q
```

带 `perf` 标记的用例断言墙钟耗时，机器负载高时可能偶发失败；可以用 `-m 'not perf'` 排除。

运行变异自检，验证测试用例能否捕获注入的缺陷（会自动排除 `perf` 用例）：

```bash
uv run --python "$(which python3)" --with pytest --with click python tests/gr-search/mutants.py
```

## 感谢

`gr-content-ai-avoid` 借鉴了：

- [lieflat-less-ai-tone](https://github.com/larashero3-dotcom/lieflat-less-ai-tone)
- [humanizer](https://github.com/blader/humanizer)
- [Humanizer-zh](https://github.com/op7418/Humanizer-zh)

`gr-chinese-typography-rules` 借鉴了：

- [document-style-guide](https://github.com/ruanyf/document-style-guide)
- [chinese-style-guide](https://github.com/RightCapitalHQ/chinese-style-guide)

## License

MIT
