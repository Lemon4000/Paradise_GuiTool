#!/usr/bin/env powershell
# -*- coding: utf-8 -*-
<#
.SYNOPSIS
  一键打包发布脚本（快捷启动器）
#>

$scriptDir = Split-Path -Parent $MyInvocation.MyCommandPath
$buildScript = Join-Path $scriptDir "build_and_release.ps1"

if (-not (Test-Path $buildScript)) {
    Write-Host "? 找不到构建脚本: $buildScript" -ForegroundColor Red
    exit 1
}

Write-Host "`n? 启动构建和发布流程..." -ForegroundColor Cyan

& $buildScript

Write-Host "`n? 流程完成！请检查 release 目录。" -ForegroundColor Green
