# Paradise GuiTool - 自动打包和发布指南

## 概述

本项目现已实现**完整的自动化打包、版本管理和发布流程**。每次打包时，版本号会自动递增，生成的 exe 和配置文件会被打包成 zip 格式，并放置在 `release` 目录中。

## 快速开始

### 方法 1：PowerShell 脚本（推荐）

在项目根目录打开 PowerShell，运行：

```powershell
# 最简单的方式
powershell -ExecutionPolicy Bypass -File "scripts\build_and_release.ps1"

# 或者快捷脚本
powershell -ExecutionPolicy Bypass -File "scripts\release.ps1"
```

### 方法 2：批处理文件（Windows 用户）

双击运行：
```
scripts\release.bat
```

### 方法 3：直接运行脚本

```powershell
# 在项目根目录
cd "c:\Users\Lemon\Documents\编程卡上位机"
.\scripts\release.ps1
```

## 工作流程

脚本执行的完整步骤：

```
[1] 处理版本号
   └─ 读取 version.py
   └─ 解析当前版本（如：2.0.2）
   └─ 递增修订号（2.0.2 → 2.0.3）
   └─ 更新 version.py 中的 __version__

[2] 清理旧的构建文件
   └─ 删除 build/ 目录
   └─ 删除 dist/ 目录
   └─ 删除 UsartGUI.spec 文件

[3] 构建 exe
   └─ 运行 PyInstaller
   └─ 编译 GUI 应用
   └─ 打包依赖和配置文件
   └─ 生成单个 UsartGUI.exe（约 47MB）

[4] 打包成 zip
   └─ 收集 exe 和 config 目录
   └─ 压缩成 zip 文件（带版本号）
   └─ 例如：UsartGUI_v2.0.3.zip

[5] 生成发布信息
   └─ 创建 RELEASE_NOTES.txt
   └─ 记录版本、时间和更新说明
```

## 文件说明

### 脚本文件

```
scripts/
├── build_and_release.ps1   # 核心构建脚本（强烈推荐）
├── release.ps1             # 快捷启动器（PowerShell）
├── release.bat             # 快捷启动器（批处理）
└── run.ps1                 # 快速运行脚本
```

### 发布目录

```
release/
├── UsartGUI_v2.0.0.zip
├── UsartGUI_v2.0.1.zip
├── UsartGUI_v2.0.2.zip
├── UsartGUI_v2.0.3.zip
├── v2.0.0_RELEASE_NOTES.txt
├── v2.0.1_RELEASE_NOTES.txt
├── v2.0.2_RELEASE_NOTES.txt
├── v2.0.3_RELEASE_NOTES.txt
├── README.md
└── （所有历史版本都保留）
```

## 版本管理

### 当前版本

当前版本存储在：`version.py`

```python
__version__ = "2.0.3"
```

### 版本格式

版本采用 **X.Y.Z** 格式（语义版本控制）：

- **X** - 主版本号（如发生不兼容的 API 变化时递增）
- **Y** - 次版本号（如添加新功能时递增）
- **Z** - 修订号（如修复 bug 时递增，**自动递增**）

### 手动修改版本

若需修改主或次版本号，直接编辑 `version.py`：

```python
# 例如，要发布 3.0.0
__version__ = "3.0.0"

# 下次打包时会自动递增为 3.0.1
```

## 脚本参数

### 基本用法

```powershell
# 默认：单文件 exe，自动递增版本号
.\scripts\build_and_release.ps1

# 打成文件夹模式（不推荐，需要更多运行时依赖）
.\scripts\build_and_release.ps1 -OneFile $false

# 仅测试构建，不递增版本
.\scripts\build_and_release.ps1 -SkipVersionIncrement
```

## 发布包内容

每个 zip 包包含：

```
UsartGUI_v2.0.3.zip
├── UsartGUI.exe          # 主应用程序（约 47MB）
└── config/               # 配置目录
    ├── A组.csv           # 参数映射表
    ├── Protocol.csv      # 通信协议配置
    ├── user_config.json  # 用户配置
    └── 其他配置文件
```

## 常见问题

### Q1: 如何分发应用？
**A:** 直接将 `release/` 下的 zip 文件分享给用户即可。用户只需：
1. 解压 zip 文件
2. 运行 UsartGUI.exe

### Q2: 我能否跳过自动版本递增？
**A:** 可以，使用 `-SkipVersionIncrement` 参数：
```powershell
.\scripts\build_and_release.ps1 -SkipVersionIncrement
```

### Q3: 打包失败，怎么办？
**A:** 检查以下几点：
1. 确保在项目根目录执行脚本
2. 确保 Python 已安装并在 PATH 中
3. 确保已安装 PyInstaller：`pip install pyinstaller`
4. 检查 ICON.png 文件存在
5. 尝试删除 `build/` 和 `dist/` 目录后重新运行

### Q4: 如何回滚到旧版本？
**A:** `release/` 目录保留了所有历史版本。只需将历史 zip 重新分发即可。

### Q5: 如何修改发布说明？
**A:** 编辑脚本中的发布信息部分（第5步），修改 `$releaseInfo` 变量。

## 配置文件

### build_config.ini

可选的配置文件（目前未启用，但已为未来扩展预留）：

```ini
[App]
Name=UsartGUI
Version=2.0.3

[Build]
OneFile=true
OptimizeLevel=1

[Release]
ReleaseDir=release
KeepHistory=true

[Package]
CompressionLevel=Optimal
```

## 故障排查

### 脚本无法执行

**错误信息：** `cannot be loaded because running scripts is disabled`

**解决方案：**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### PyInstaller 错误

**错误信息：** `cannot find python`

**解决方案：**
确保 Python 在 PATH 中：
```powershell
python --version
```

若不存在，添加 Python 安装目录到 PATH。

### 权限不足

**错误信息：** `Access Denied`

**解决方案：**
1. 关闭相关应用程序（如 antivirus 软件）
2. 运行管理员模式的 PowerShell
3. 清理 `build/` 目录

## 构建时间

首次构建可能需要 1-2 分钟（取决于系统性能），之后的构建会更快。

| 阶段 | 耗时 |
|-----|------|
| 版本处理 | < 1s |
| 清理 | < 2s |
| PyInstaller 编译 | 30-60s |
| 压缩 zip | 10-20s |
| 总计 | ~1-2 分钟 |

## 高级用法

### 批量构建

可以编写脚本多次调用打包脚本：

```powershell
# build_multiple.ps1
for ($i = 1; $i -le 3; $i++) {
    Write-Host "第 $i 次打包..."
    & .\scripts\build_and_release.ps1
    Start-Sleep -Seconds 30
}
```

### 与 CI/CD 集成

脚本可以集成到 GitHub Actions、GitLab CI 等：

```yaml
- name: Build Release
  run: |
    powershell -ExecutionPolicy Bypass -File "scripts/build_and_release.ps1"
```

## 维护建议

1. **定期检查 release 目录**：确保空间充足
2. **备份重要版本**：将稳定版本单独备份
3. **更新变更日志**：在 `RELEASE_NOTES.txt` 中记录更新内容
4. **测试新版本**：每次发布前在测试机上验证

## 更新历史

| 版本 | 日期 | 更新内容 |
|------|------|--------|
| 2.0.3 | 2025-12-30 | 自动构建系统完成 |
| 2.0.2 | 2025-12-30 | 修复内存泄漏 |
| 2.0.1 | 2025-12-30 | 性能优化 |
| 2.0.0 | - | 初始版本 |

## 相关文档

- [PERFORMANCE_FIX.md](../PERFORMANCE_FIX.md) - 性能优化说明
- [README.md](../README.md) - 项目说明
- [build_config.ini](../build_config.ini) - 构建配置

---

**最后更新：** 2025-12-30  
**维护者：** Lemon  
**联系方式：** 见项目文档
