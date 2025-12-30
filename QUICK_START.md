# ? 快速参考 - 一键打包发布

## 最简单的方式（复制粘贴）

### 方式 1：PowerShell（推荐）

```powershell
cd "c:\Users\Lemon\Documents\编程卡上位机"
powershell -ExecutionPolicy Bypass -File "scripts\build_and_release.ps1"
```

### 方式 2：双击 .bat 文件

直接双击：`scripts\release.bat`

### 方式 3：快捷脚本

```powershell
powershell -ExecutionPolicy Bypass -File "scripts\release.ps1"
```

---

## 打包后输出位置

? **release/** 目录

```
release/
├── UsartGUI_v2.0.3.zip          ← 应用包（用户下载此文件）
├── v2.0.3_RELEASE_NOTES.txt     ← 发布说明
└── 其他文件
```

---

## 什么时候自动执行？

| 时间 | 操作 |
|------|------|
| **打包前** | 自动递增版本号（2.0.2 → 2.0.3） |
| **打包时** | 自动构建 exe + 压缩成 zip |
| **打包后** | 自动生成发布说明和日志 |

---

## 版本号在哪里？

? **version.py**

```python
__version__ = "2.0.3"  # 当前版本
```

**下次打包自动变为：2.0.4**

---

## 如果遇到问题？

### 问题 1：脚本无法运行
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 问题 2：找不到 Python
确保 Python 已安装：
```powershell
python --version
```

### 问题 3：缺少 PyInstaller
安装依赖：
```powershell
pip install pyinstaller
```

### 问题 4：清理旧文件后重试
```powershell
Remove-Item -Recurse build, dist -Force -ErrorAction SilentlyContinue
```

---

## 用户如何使用应用？

用户收到 `UsartGUI_v2.0.3.zip` 后：

1. ? 解压 zip 文件
2. ? 双击 `UsartGUI.exe` 运行

**完毕！无需安装任何东西。**

---

## 更多信息

- ? [完整使用指南](release/BUILD_AND_RELEASE_GUIDE.md)
- ? [项目完成说明](RELEASE_SETUP_COMPLETE.md)
- ? [性能优化详情](PERFORMANCE_FIX.md)

---

**只需一条命令，自动打包、版本管理、发布！**

```powershell
powershell -ExecutionPolicy Bypass -File "scripts\build_and_release.ps1"
```
