---
name: ob-fix-color-tags
description: |
  批量转义 Obsidian 中颜色代码前的 # 号，避免被识别为标签。
  扫描所有 prompts/ 目录下的 .md 文件，将 #FFFFFF 格式转为 \#FFFFFF。
  跨平台支持：Windows PowerShell / Linux / macOS zsh/bash
  触发方式：/ob-fix-color-tags、/fix-color-tags、/转义颜色代码、「fix color tags」
---

# ob-fix-color-tags：Obsidian 颜色代码标签转义工具

你的任务是：批量扫描并转义 markdown 文件中颜色代码前的 `#` 号，避免被 Obsidian 识别为标签。

## 处理规则

- **匹配模式**：`#` + 6 位十六进制字符（大小写均可）
- **转义方式**：在 `#` 前加反斜杠 `\` → `\#FFFFFF`
- **范围限制**：只处理路径中包含 `prompts/` 目录的 `.md` 文件
- **跳过已转义**：`\#` 开头的颜色代码不再重复处理

---

## 跨平台执行脚本

### 🪟 Windows (PowerShell)

在项目根目录执行：

```powershell
$files = Get-ChildItem -Path . -Recurse -Filter *.md | Where-Object { $_.DirectoryName -match "prompts" }
$count = 0
foreach ($f in $files) {
    $content = Get-Content $f.FullName -Raw -Encoding UTF8
    $newContent = $content -replace '(?<!\\)#([A-Fa-f0-9]{6})', '\#$1'
    if ($newContent -ne $content) {
        Set-Content -Path $f.FullName -Value $newContent -Encoding UTF8 -NoNewline
        Write-Host "✅ $($f.Name)"
        $count++
    }
}
Write-Host "`n🎉 完成！共处理 $count 个文件"
```

---

### 🍎 macOS / 🐧 Linux (zsh/bash)

在项目根目录执行：

**方法一：使用 perl（推荐，跨平台一致性好）**
```bash
find . -type d -name "prompts" -exec find {} -name "*.md" \; | while read file; do
    perl -i -pe 's/(?<!\\)#([A-Fa-f0-9]{6})/\\#$1/g' "$file"
    echo "✅ $file"
done
echo -e "\n🎉 完成！"
```

**方法二：使用 sed（Linux/macOS 默认自带）**
```bash
find . -path "*/prompts/*.md" -type f | while read file; do
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS sed
        sed -i '' 's/#\([A-Fa-f0-9]\{6\}\)/\\#\1/g' "$file"
    else
        # GNU/Linux sed
        sed -i 's/#\([A-Fa-f0-9]\{6\}\)/\\#\1/g' "$file"
    fi
    echo "✅ $file"
done
echo -e "\n🎉 完成！"
```

---

## 验证（所有平台通用）

处理完成后用 grep 验证是否还有未转义的颜色代码：
```bash
grep -rE "(?<!\\)#[A-Fa-f0-9]{6}" --include="*.md" . 2>/dev/null | wc -l
```

输出 `0` 表示全部处理完成。

---

## 平台兼容性说明

| 平台 | 推荐工具 | 原因 |
|---|---|---|
| Windows | PowerShell | 系统自带，编码处理最稳妥 |
| macOS | perl | 避免 BSD sed 和 GNU sed 的语法差异 |
| Linux | perl / sed | 两者均可，perl 语法更统一 |
