# Release（发布）目录

此目录存放已打包的应用版本。

## 目录结构

```
release/
├── UsartGUI_v2.0.0.zip       # 应用包（带版本号）
├── v2.0.0_RELEASE_NOTES.txt  # 发布说明
└── README.md                  # 本说明
```

## 使用方法

### 自动打包和发布（推荐）

在项目根目录运行：

```powershell
# 快捷方式（最简单）
powershell scripts/release.ps1

# 或完整命令
powershell scripts/build_and_release.ps1
```

### 脚本参数

```powershell
# 默认：单文件 exe 并自增版本号
powershell scripts/build_and_release.ps1

# 打成文件夹模式（需要更多运行时依赖）
powershell scripts/build_and_release.ps1 -OneFile $false

# 仅构建，不递增版本（用于测试）
powershell scripts/build_and_release.ps1 -SkipVersionIncrement
```

## 自动化流程

脚本执行步骤：

1. ? **解析版本号** - 从 `version.py` 读取当前版本
2. ? **递增版本** - 修订号 +1（如 2.0.0 → 2.0.1）
3. ? **更新配置** - 修改 `version.py` 中的 `__version__`
4. ? **清理旧文件** - 删除 `build/`、`dist/`、`*.spec`
5. ? **构建 exe** - 使用 PyInstaller 打包应用
6. ? **打包 zip** - 创建版本化的 zip 文件
7. ? **生成说明** - 创建发布说明文档

## 版本管理

- 版本格式：**X.Y.Z**（主.次.修订）
- 每次打包自动递增修订号
- 版本信息同步到：
  - `version.py` - 应用源码
  - zip 文件名 - 已发布版本
  - release 说明 - 发布文档

## 发布包内容

每个 zip 包包含：

- `UsartGUI.exe` - 主应用程序
- `config/` - 配置文件夹
  - `A组.csv` - 参数映射
  - `Protocol.csv` - 通信协议配置
  - `user_config.json` - 用户配置
  - 其他配置文件

## 常见问题

### Q: 怎样重置版本号？
A: 直接编辑 `version.py` 中的 `__version__` 即可，下次打包会以该版本号为基础递增。

### Q: 可以跳过版本递增吗？
A: 可以，使用 `-SkipVersionIncrement` 参数。

### Q: 如何分发？
A: 直接分享 `release/` 下的 zip 文件即可。

### Q: 如何回滚到旧版本？
A: `release/` 目录保留了所有历史版本，直接使用对应的 zip 即可。

---

更新时间：$(Get-Date -Format "yyyy-MM-dd")
