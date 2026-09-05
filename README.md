# getrich-skills

一套面向联网搜索、内容创作和 Obsidian 文档处理的 AI Skill 集合，目前包含 5 个 Skill。

## 安装

使用以下命令，将全部 Skill 全局安装到 Claude Code 和 Codex：

```bash
npx skills add neolin0629/getrich-skills -a claude-code -a codex -g -y
```

也可以通过 `@` 或 `--skill` 只安装一个 Skill：

```bash
npx skills use neolin0629/getrich-skills@gr-search | claude
npx skills use neolin0629/getrich-skills --skill gr-search --agent claude-code
```

安装完成后，重启对应的 AI 客户端。

## Skill 一览

| Skill | 功能 |
| --- | --- |
| `gr-search` | 同时调用豆包搜索和 Parallel，去重融合后按 token 预算压缩输出，支持图片搜索与正文抓取 |
| `gr-chinese-typography-rules` | 检查或统一中文排版，覆盖中英文空格、标点、引号、数字、日期和金融表达，附机械自检脚本 |
| `gr-content-ai-avoid` | 按 6 个层级、39 条规则规避中文写作中的 AI 指纹，并提供脚本自检 |
| `gr-ob-fix-color-tags` | 用全角括号包裹 Obsidian `prompts/` 目录中的十六进制颜色代码，避免被识别为标签 |
| `gr-ob-rm-prompts-formatter` | 批量删除 Obsidian `prompts/` 目录中 Markdown 文件开头的 YAML frontmatter |

安装后，可以直接描述任务，也可以显式指定 Skill 名称。例如：

```text
使用 gr-search 搜索豆包搜索的计费方式
使用 gr-chinese-typography-rules 检查这篇稿子的排版
```

`gr-chinese-typography-rules` 负责排版，`gr-content-ai-avoid` 负责表达；创作中文内容时可配合使用。

## 可选依赖

`gr-search` 不需要 pip 依赖（纯标准库），但需要：

```bash
# Parallel CLI（用于补充信源和抓取网页正文）
uv tool install "parallel-web-tools[cli]"
```

以及一个[豆包搜索](https://console.volcengine.com/search-infinity/web-search) API Key。首次使用时**由你本人在终端**执行下面的命令写入（不回显、不进命令行历史）：

```bash
python3 skills/gr-search/scripts/gr_search.py config set-key doubao
```

[Parallel](https://platform.parallel.ai/home) 侧可以跑 `/parallel-cli-setup` 走 OAuth 登录；换机器时也可以用
`config set-key parallel` 配置 API Key，避免每台机器重新登录。
配置完成后用 `config doctor` 检查两个源是否都可用。

各 Skill 的具体用法和限制以对应目录内的 `SKILL.md` 为准。

## 目录结构

```text
.
├── skills/
│   ├── gr-chinese-typography-rules/
│   ├── gr-content-ai-avoid/
│   ├── gr-ob-fix-color-tags/
│   ├── gr-ob-rm-prompts-formatter/
│   └── gr-search/
└── tests/
    └── gr-search/
```

## 开发与测试

测试套件统一维护在根目录 `tests/` 下，与分发给 Agent 的 `skills/` 解耦。使用 `npx skills add` 安装 Skill 时，只会打包对应 `skills/<skill-name>` 目录，不会将测试代码分发至用户的 Agent 目录中。

在仓库根目录下运行测试（无需安装项目依赖，由 `uv` 临时拉取 pytest）：

```bash
uv run --python "$(which python3)" --with pytest --with click pytest tests/gr-search/ -q
```

运行变异自检（验证测试用例的有效性与缺陷捕获能力）：

```bash
uv run --python "$(which python3)" --with pytest --with click python tests/gr-search/mutants.py
```

## License

MIT
