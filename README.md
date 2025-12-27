# Paradise GuiTool

电调参数配置与固件烧录上位机工具

## 功能特性

### ? 核心功能
- **参数读写配置** - 支持电调参数的读取和写入
- **固件烧录** - 支持HEX文件的固件烧录功能
- **串口通信** - 自动检测串口设备，实时显示通信日志

### ? 高级功能
- **波特率管理**
  - 内置常用波特率（9600-2000000）
  - 支持添加自定义波特率（300-3000000）
  - 可设置默认波特率
  - 可删除自定义波特率
  
- **日志输出控制**
  - 烧录标签页新增“启用日志输出”复选框，实时开关日志
  - 关闭时仍然接收并推进状态机，只是停止界面日志渲染
  - 详见 [config/日志控制功能说明.md](config/%E6%97%A5%E5%BF%97%E6%8E%A7%E5%88%B6%E5%8A%9F%E8%83%BD%E8%AF%B4%E6%98%8E.md)
  
- **配置记忆**
  - 自动保存上次使用的波特率
  - 记忆最后使用的HEX文件路径
  - 配置文件自动管理（config/user_config.json）

- **用户界面**
  - 暗色主题设计
  - 参数表格排序和筛选
  - 实时通信日志（支持HEX/ASCII显示）
  - 固件烧录进度显示

## 快速开始

### 下载和安装

1. 从 [Releases](https://github.com/Lemon4000/CoderCard-FKKK/releases) 下载最新版本
2. 解压 `Paradise_GuiToolV{版本}.zip`
3. 运行 `UsartGUI.exe`

### 使用说明

#### 参数配置
1. 连接设备到电脑
2. 选择串口和波特率
3. 点击"连接"
4. 点击"读取"获取当前参数
5. 修改参数后点击"写入"

#### 固件烧录
1. 切换到"固件烧录"标签页
2. 拖拽或选择HEX文件
3. 确保串口已连接
4. 点击"开始烧录"

#### 波特率管理
1. 点击波特率旁的 ? 按钮
2. 在对话框中管理波特率列表
3. 可添加、删除、设为默认

## 开发

### 环境要求
- Python 3.11+
- PySide6
- pyserial
- openpyxl

### 本地运行
```bash
# 安装依赖
pip install -r requirements.txt

# 运行程序
python gui/main.py
# 或（推荐）
python -m gui.main
```

### 构建EXE
```bash
# 使用PyInstaller构建
python -m PyInstaller gui/main.py -F --noconsole --icon ICON.png -n UsartGUI --add-data "config;config" --add-data "gui/resources;gui/resources"
```

## 技术栈

- **UI框架**: PySide6 (Qt for Python)
- **串口通信**: pyserial
- **数据解析**: openpyxl, csv
- **打包工具**: PyInstaller
- **CI/CD**: GitHub Actions

## 配置文件

### 协议配置 (config/Protocol.csv)
定义通信协议参数（前导码、校验和类型、波特率等）

### 参数映射 (config/A组.csv)
定义参数名称、地址、类型和映射关系

### 用户配置 (config/user_config.json)
自动生成和管理的用户偏好设置

## 固件烧录协议要点

- 烧录时开启透传模式：避免自动解析/自动回复干扰。
  - 入口：见 [gui/views/FlashTab.py](gui/views/FlashTab.py#L493-L501)
- 数据块发送：`!HEX:START[addr].SIZE[size],DATA[binary];[CRC]`
  - `DATA` 后携带原始二进制数据，而非 ASCII HEX
  - 帧 CRC 参与总 CRC 累加（按小端整数直接相加，取 16 位）
- 编程回复：`#HEX:REPLY[CRC];[CRC]`
  - `[CRC]` 为原始字节（`CRC16_MODBUS` 为 2 字节，`SUM8` 为 1 字节），不是 ASCII
  - 固定长度提取 CRC 字段，允许 CRC 字节等于分号 `0x3B`，不会被截断
  - 实现：见 [gui/services/FlashWorker.py](gui/services/FlashWorker.py#L432-L480)
- 校验命令：`!HEX:ENDCRC[total_crc];[CRC]`
  - `total_crc` 发送为 2 字节（当前实现为大端），设备回复 `#HEX:REPLY` 的总 CRC 为原始两字节
  - 回复端序兼容：接受小端或大端两种形式，见 [gui/services/FlashWorker.py](gui/services/FlashWorker.py#L600-L647)

## 异常与断开处理

- 串口读线程异常/断开：立即发出错误并断开连接，停止读循环
  - 实现：见 [gui/services/SerialWorker.py](gui/services/SerialWorker.py#L1-L260)
- 主窗口收到断开：若正在烧录则立刻中止，并弹窗提示“串口已断开，烧录已中止”
  - 实现：见 [gui/views/MainWindow.py](gui/views/MainWindow.py#L200-L280)

## 构建脚本

- PowerShell 构建：见 [scripts/build.ps1](scripts/build.ps1)
  - 示例：`pwsh scripts/build.ps1 -Name UsartGUI -OneFile`
  - 自动打包 `config` 与 `gui/resources` 到发行包

## 更新日志

### v1.0.0
- ? 初始版本发布
- ? 参数读写功能
- ? 固件烧录功能
- ? 波特率管理
- ? 配置记忆
- ? 串口自动检测

### v1.1.0
- 新增：烧录日志实时开关（复选框），默认值可在配置中设置
- 修复：`#HEX:REPLY` 的 CRC 字段按固定长度解析，避免 CRC 包含分号时被截断
- 优化：VERIFY 阶段按原始二进制处理并兼容端序，避免因大小端不一致误报
- 增强：串口断开检测与中止烧录流程，防止误连其他串口继续烧录

## 许可证

MIT License

## 作者

Lemon

---

**自动构建**: 本项目使用 GitHub Actions 自动构建和发布
