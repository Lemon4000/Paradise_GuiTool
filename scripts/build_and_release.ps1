# -*- coding: utf-8 -*-
<#
.SYNOPSIS
  自动构建、打包和发布 exe
  
.DESCRIPTION
  此脚本会：
  1. 自动递增版本号（修订号+1）
  2. 更新 version.py
  3. 构建 exe（默认打成一体exe）
  4. 将 exe 打包成 zip
  5. 放入 release 目录并添加版本后缀
  
.PARAMETER OneFile
  是否打包成单个exe文件（默认 $true）
  
.PARAMETER SkipVersionIncrement
  是否跳过版本递增（仅用于测试）
  
.EXAMPLE
  .\build_and_release.ps1
  .\build_and_release.ps1 -OneFile $false
#>

param(
    [switch]$OneFile = $true,
    [switch]$SkipVersionIncrement = $false
)

# 获取项目根目录（脚本在 scripts 子目录下）
# 方法：获取当前工作目录（用户应在项目根目录执行）
$ProjectRoot = Get-Location

# ============================================================================
# 配置
# ============================================================================
$AppName = "UsartGUI"
$VersionFile = Join-Path $ProjectRoot "version.py"
$ReleaseDir = Join-Path $ProjectRoot "release"
$DistDir = Join-Path $ProjectRoot "dist"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Paradise GuiTool - 自动构建和发布脚本" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

# ============================================================================
# 第1步：解析和递增版本号
# ============================================================================
Write-Host "`n[1] 处理版本号..." -ForegroundColor Yellow

if (-not (Test-Path $VersionFile)) {
    Write-Host "? 找不到 version.py: $VersionFile" -ForegroundColor Red
    exit 1
}

# 读取 version.py
$versionContent = Get-Content $VersionFile -Encoding UTF8 -Raw
$versionMatch = [regex]::Match($versionContent, '__version__\s*=\s*"([^"]+)"')

if ($versionMatch.Success) {
    $currentVersion = $versionMatch.Groups[1].Value
    Write-Host "? 当前版本: $currentVersion"
} else {
    Write-Host "? 无法解析版本号" -ForegroundColor Red
    exit 1
}

# 解析版本号 (major.minor.patch)
$versionParts = $currentVersion -split '\.'
if ($versionParts.Count -ne 3) {
    Write-Host "? 版本格式错误，应为 X.Y.Z 格式" -ForegroundColor Red
    exit 1
}

$major = [int]$versionParts[0]
$minor = [int]$versionParts[1]
$patch = [int]$versionParts[2]

# 递增修订号 (patch)
if (-not $SkipVersionIncrement) {
    $patch++
    $newVersion = "$major.$minor.$patch"
    
    # 更新 version.py
    $newVersionContent = $versionContent -replace '__version__\s*=\s*"[^"]+"', "__version__ = `"$newVersion`""
    Set-Content -Path $VersionFile -Value $newVersionContent -Encoding UTF8 -NoNewline
    
    Write-Host "? 版本已更新: $currentVersion → $newVersion" -ForegroundColor Green
} else {
    $newVersion = $currentVersion
    Write-Host "??  跳过版本递增（测试模式）" -ForegroundColor Cyan
}

# ============================================================================
# 第2步：清理旧的构建文件
# ============================================================================
Write-Host "`n[2] 清理旧的构建文件..." -ForegroundColor Yellow

$buildDir = Join-Path $ProjectRoot "build"
if (Test-Path $buildDir) {
    Remove-Item -Recurse -Force $buildDir -ErrorAction SilentlyContinue
    Write-Host "? 已清理 build 目录"
}

if (Test-Path $DistDir) {
    Remove-Item -Recurse -Force $DistDir -ErrorAction SilentlyContinue
    Write-Host "? 已清理 dist 目录"
}

$specFile = Join-Path $ProjectRoot "$AppName.spec"
if (Test-Path $specFile) {
    Remove-Item $specFile -Force -ErrorAction SilentlyContinue
    Write-Host "? 已删除 spec 文件"
}

# ============================================================================
# 第3步：构建 exe
# ============================================================================
Write-Host "`n[3] 构建 exe..." -ForegroundColor Yellow

$buildMode = if ($OneFile) { "-F" } else { "-D" }
$buildModeName = if ($OneFile) { "单文件" } else { "文件夹" }

Push-Location $ProjectRoot

try {
    Write-Host "运行 PyInstaller..." -ForegroundColor Gray
    
    python -m PyInstaller $buildMode `
        --noconsole `
        --icon "ICON.png" `
        -n $AppName `
        "gui/main.py" `
        --add-data "config;config" `
        --hidden-import serial.tools.list_ports_windows `
        --hidden-import serial.tools.list_ports `
        --clean
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "? PyInstaller 构建失败 (错误码: $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "? exe 构建完成 ($buildModeName 模式)" -ForegroundColor Green
    
} finally {
    Pop-Location
}

# 检查构建输出
$exePath = $null
if ($OneFile) {
    $exePath = Join-Path $DistDir "$AppName.exe"
} else {
    $exePath = Join-Path $DistDir $AppName "$AppName.exe"
}

if (-not (Test-Path $exePath)) {
    Write-Host "? 找不到构建的 exe 文件: $exePath" -ForegroundColor Red
    exit 1
}

Write-Host "? exe 文件: $exePath" -ForegroundColor Green

# 重要：复制 config 目录到 dist（用于打包 zip）
Write-Host "? 复制配置文件..." -ForegroundColor Yellow
$configSource = Join-Path $ProjectRoot "config"
$configDest = Join-Path $DistDir "config"

if (Test-Path $configSource) {
    if (Test-Path $configDest) {
        Remove-Item -Recurse -Force $configDest
    }
    Copy-Item -Recurse $configSource $configDest -Force
    Write-Host "? 配置文件已复制: config/" -ForegroundColor Green
} else {
    Write-Host "??  警告：找不到 config 目录" -ForegroundColor Yellow
}

# ============================================================================
# 第4步：创建 release 目录和打包
# ============================================================================
Write-Host "`n[4] 打包成 zip..." -ForegroundColor Yellow

if (-not (Test-Path $ReleaseDir)) {
    New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
    Write-Host "? 创建 release 目录: $ReleaseDir"
}

# 确定源目录（要打包的内容）
$sourceDir = if ($OneFile) {
    $DistDir
} else {
    Join-Path $DistDir $AppName
}

if (-not (Test-Path $sourceDir)) {
    Write-Host "? 找不到源目录: $sourceDir" -ForegroundColor Red
    exit 1
}

# 生成 zip 文件名
$zipFileName = "${AppName}_v${newVersion}.zip"
$zipPath = Join-Path $ReleaseDir $zipFileName

# 如果 zip 已存在，删除
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
    Write-Host "? 已删除旧的 zip 文件"
}

# 压缩
try {
    # 使用 .NET 的 ZipFile 来创建压缩包
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    
    if ($OneFile) {
        # 单文件模式：手动收集 exe 和 config 目录
        $tempDir = New-Item -ItemType Directory -Force -Path (Join-Path $env:TEMP "$AppName-temp-$(Get-Random)")
        
        # 复制 exe
        $exeSource = Join-Path $DistDir "$AppName.exe"
        if (Test-Path $exeSource) {
            Copy-Item $exeSource $tempDir -Force
            Write-Host "   ? 已添加 $AppName.exe"
        } else {
            Write-Host "   ??  找不到 exe 文件" -ForegroundColor Yellow
        }
        
        # 复制 config 目录
        $configSource = Join-Path $DistDir "config"
        if (Test-Path $configSource) {
            Copy-Item -Recurse $configSource $tempDir -Force
            Write-Host "   ? 已添加 config 目录"
        } else {
            Write-Host "   ??  找不到 config 目录" -ForegroundColor Yellow
        }
        
        # 创建 zip
        [System.IO.Compression.ZipFile]::CreateFromDirectory($tempDir, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $false)
        
        Remove-Item -Recurse -Force $tempDir
    } else {
        # 文件夹模式：直接压缩整个目录
        [System.IO.Compression.ZipFile]::CreateFromDirectory($sourceDir, $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $false)
    }
    
    $zipSize = (Get-Item $zipPath).Length / 1MB
    Write-Host "? zip 已创建: $zipFileName (大小: $([Math]::Round($zipSize, 2)) MB)" -ForegroundColor Green
    
} catch {
    Write-Host "? 压缩失败: $_" -ForegroundColor Red
    exit 1
}

# ============================================================================
# 第5步：生成发布信息
# ============================================================================
Write-Host "`n[5] 生成发布信息..." -ForegroundColor Yellow

$releaseInfo = @"
# Paradise GuiTool 发布信息

## 版本: v$newVersion
发布时间: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

## 文件信息
- 文件: $zipFileName
- 大小: $([Math]::Round((Get-Item $zipPath).Length / 1MB, 2)) MB
- 位置: release/

## 更新内容
- 修复内存泄漏问题（日志缓冲区无限增长）
- 优化软件性能
- 改进版本管理系统

## 安装说明
1. 解压 zip 文件
2. 运行 UsartGUI.exe

---
`n发布脚本自动生成于: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@

$releaseInfoPath = Join-Path $ReleaseDir "v${newVersion}_RELEASE_NOTES.txt"
Set-Content -Path $releaseInfoPath -Value $releaseInfo -Encoding UTF8

Write-Host "? 发布信息已生成: v${newVersion}_RELEASE_NOTES.txt" -ForegroundColor Green

# ============================================================================
# 完成
# ============================================================================
Write-Host "`n============================================" -ForegroundColor Green
Write-Host "? 打包和发布完成！" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green

Write-Host @"

? 发布汇总:
  应用: $AppName
  版本: v$newVersion
  模式: $buildModeName exe
  输出: release/$zipFileName
  
? 文件位置:
  $zipPath
  
? 下次打包会自动递增版本号为 v$($major).$($minor).$($patch + 1)

"@ -ForegroundColor Cyan

Write-Host "按任意键继续..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
