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

## 更新日志

### v1.0.0
- ? 初始版本发布
- ? 参数读写功能
- ? 固件烧录功能
- ? 波特率管理
- ? 配置记忆
- ? 串口自动检测

## 许可证

MIT License

## 作者

Lemon

---

**自动构建**: 本项目使用 GitHub Actions 自动构建和发布
