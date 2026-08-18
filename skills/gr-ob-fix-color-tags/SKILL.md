---
name: gr-ob-fix-color-tags
description: |
  批量把 Obsidian 笔记里的十六进制颜色代码用全角括号包起来（#FFFFFF → （#FFFFFF）），避免 # 被识别为标签。在用户指定的目录下扫描 .md 文件，已包裹的跳过。跨平台：Windows PowerShell / macOS / Linux。
  触发方式：/gr-ob-fix-color-tags、/gr-fix-color-tags、/转义颜色代码、「fix color tags」
---

# gr-ob-fix-color-tags：Obsidian 颜色代码括号包裹工具

把指定目录下 markdown 文件中的十六进制颜色代码用全角括号包裹，避免 `#` 被 Obsidian 识别为标签。

**执行前先问用户要处理哪个目录**，不要默认全库扫描。

## 处理规则

- **匹配**：`#` + 6 到 8 位十六进制字符（大小写均可，贪婪匹配，`#FFFFFF80` 这类带透明度的不会被截成 6 位）
- **替换**：`#FFFFFF` → `（#FFFFFF）`
- **跳过已包裹**：前面已经是 `（` 的不再处理，脚本可重复执行
- **范围**：用户指定目录下的 `.md` 文件

---

## 执行脚本

### 🍎 macOS / 🐧 Linux

把 `TARGET` 改成用户指定的目录：

```bash
TARGET="./prompts"
find "$TARGET" -type f -name "*.md" -print0 | while IFS= read -r -d '' f; do
    perl -i -pe 's/(?<!（)#([A-Fa-f0-9]{6,8})/（#$1）/g' "$f"
    echo "✅ $f"
done
```

### 🪟 Windows (PowerShell)

用 `[char]0xFF08 / 0xFF09` 构造全角括号，避免旧版控制台粘贴 CJK 字符时编码出错：

```powershell
$Target = ".\prompts"
$L = [char]0xFF08
$R = [char]0xFF09
Get-ChildItem -Path $Target -Recurse -Filter *.md | ForEach-Object {
    $content = Get-Content $_.FullName -Raw -Encoding UTF8
    $new = $content -replace "(?<!$L)#([A-Fa-f0-9]{6,8})", "$L#`$1$R"
    if ($new -ne $content) {
        Set-Content -Path $_.FullName -Value $new -Encoding UTF8 -NoNewline
        Write-Host "✅ $($_.Name)"
    }
}
```

---

## 验证

找出还没被包裹的颜色代码，无输出表示处理完成。

**macOS / Linux**（`-CSD -Mutf8` 让 perl 按字符而不是字节处理全角括号）：
```bash
find "$TARGET" -type f -name "*.md" -print0 | xargs -0 perl -CSD -Mutf8 -ne \
    'print "$ARGV:$.: $&\n" while /(?<!（)#[A-Fa-f0-9]{6,8}/g'
```

**Windows (PowerShell)**：
```powershell
Get-ChildItem -Path $Target -Recurse -Filter *.md |
    Select-String -Pattern "(?<!$L)#[A-Fa-f0-9]{6,8}"
```

---

**已知边界**：只处理 6 到 8 位十六进制，CSS 的 3 位简写（`#FFF`）不在范围内——它和 Obsidian 普通标签无法从形式上区分。
