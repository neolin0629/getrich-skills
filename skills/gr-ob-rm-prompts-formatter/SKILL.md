---
name: gr-ob-rm-prompts-formatter
description: |
  批量删除 Obsidian 笔记开头的 YAML frontmatter（Obsidian 属性区，`---` 包起来的那段），只保留正文。默认处理 prompts/ 目录下的 .md 文件，可指定其他目录。跨平台：Windows PowerShell / macOS / Linux。
  触发方式：/gr-ob-rm-prompts-formatter、/删除 frontmatter、/清理属性、「remove frontmatter」
---

# gr-ob-rm-prompts-formatter：批量删除 frontmatter

删除指定目录下 markdown 文件开头的 YAML frontmatter，只留正文。

**这是破坏性操作，执行前必须做两件事：**

1. 问用户要处理哪个目录（默认 `prompts/`），不要默认全库扫描。
2. 确认目录在 git 里且工作区干净，或者让用户先备份。跑完用 `git diff` 复查。

## 处理规则

- **匹配**：文件**最开头**的 `---` 到下一个单独成行的 `---`，连同后面的空行一起删除
- **不在开头的不动**：正文中间的 `---` 分隔线保留
- **没有 frontmatter 的文件跳过**，内容不变
- **只跑一次**：见文末「已知风险」

---

## 第一步：预览（先看要删什么）

把 `TARGET` 改成用户指定的目录。这一步只读，不改文件。

### 🍎 macOS / 🐧 Linux

```bash
TARGET="./prompts"
find "$TARGET" -type f -name "*.md" -print0 | xargs -0 perl -0777 -ne \
    'print "── $ARGV\n$1\n\n" if /\A---\r?\n(.*?)\r?\n?---[ \t]*\r?\n/s'
```

### 🪟 Windows (PowerShell)

```powershell
$Target = ".\prompts"
Get-ChildItem -Path $Target -Recurse -Filter *.md | ForEach-Object {
    $c = Get-Content $_.FullName -Raw -Encoding UTF8
    $m = [regex]::Match($c, "(?s)\A---\r?\n(.*?)\r?\n?---[ \t]*\r?\n")
    if ($m.Success) { Write-Host "── $($_.FullName)"; Write-Host $m.Groups[1].Value }
}
```

无输出说明没有文件带 frontmatter，到此为止。

---

## 第二步：执行删除

### 🍎 macOS / 🐧 Linux

```bash
find "$TARGET" -type f -name "*.md" -print0 | while IFS= read -r -d '' f; do
    perl -0777 -i -pe 's/\A---\r?\n.*?\r?\n?---[ \t]*\r?\n(\r?\n)*//s' "$f"
    echo "✅ $f"
done
```

### 🪟 Windows (PowerShell)

```powershell
Get-ChildItem -Path $Target -Recurse -Filter *.md | ForEach-Object {
    $content = Get-Content $_.FullName -Raw -Encoding UTF8
    $new = $content -replace "(?s)\A---\r?\n.*?\r?\n?---[ \t]*\r?\n(\r?\n)*", ""
    if ($new -ne $content) {
        Set-Content -Path $_.FullName -Value $new -Encoding UTF8 -NoNewline
        Write-Host "✅ $($_.Name)"
    }
}
```

---

## 第三步：验证

重跑第一步的预览命令，无输出表示删干净了。再用 `git diff` 确认删掉的都是 frontmatter。

---

## 已知风险

**不要重复执行。** 如果某个文件的正文恰好以 `---` 分隔线段落开头，第一次删掉 frontmatter 后，第二次会把这段正文当成 frontmatter 删掉。所以：先预览、跑一次、`git diff` 复查。

**边界**：只识别 `---` 作为结束标记，不支持 YAML 的 `...` 结束符（Obsidian 也不用）。
