@echo off
REM -*- coding: utf-8 -*-
REM 构建和发布脚本（Windows 批处理启动器）

chcp 65001 > nul
setlocal enabledelayedexpansion

echo.
echo ════════════════════════════════════════════════
echo     Paradise GuiTool - 自动打包和发布
echo ════════════════════════════════════════════════
echo.

REM 获取脚本路径
set SCRIPT_DIR=%~dp0
set BUILD_SCRIPT=%SCRIPT_DIR%build_and_release.ps1

if not exist "%BUILD_SCRIPT%" (
    echo ? 找不到构建脚本: %BUILD_SCRIPT%
    pause
    exit /b 1
)

echo ? 启动构建和发布流程...
echo.

REM 运行 PowerShell 脚本
powershell -NoProfile -ExecutionPolicy Bypass -File "%BUILD_SCRIPT%"

if errorlevel 1 (
    echo.
    echo ? 打包失败！
    pause
    exit /b 1
)

echo.
echo ? 打包完成！
echo.
pause
