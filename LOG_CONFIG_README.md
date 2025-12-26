# 日志输出控制说明

## 概述

本项目添加了一个全局的日志输出控制机制，通过修改配置文件可以灵活地启用或禁用日志输出。**特别是固件烧录标签页中的日志输出**。

## 配置文件位置

配置文件位于: **`config/config.py`**

## 配置项

### ENABLE_LOGGING (启用日志输出)
- **类型**: Boolean
- **默认值**: `False`
- **说明**: 
  - `True`: 启用所有日志输出（包括烧录日志）
  - `False`: 禁用所有日志输出（包括烧录日志）

### LOG_LEVEL (日志级别)
- **类型**: Integer
- **默认值**: `1`
- **说明** (仅在 `ENABLE_LOGGING=True` 时有效):
  - `0`: 仅输出错误和重要信息
  - `1`: 标准日志 (默认)
  - `2`: 详细调试日志

## 使用示例

### 禁用日志输出（默认）- 烧录标签页将不显示日志

编辑 `config/config.py`:
```python
ENABLE_LOGGING = False
```

### 启用日志输出 - 烧录标签页显示所有日志

编辑 `config/config.py`:
```python
ENABLE_LOGGING = True
```

## 受控的日志模块

以下模块中的日志输出受 ENABLE_LOGGING 配置控制：

### ? 已实现日志控制

1. **gui/services/FlashWorker.py** 
   - **烧录状态日志**（初始化、擦除、编程、校验等各个阶段）
   - **超时提示**（数据块超时等）
   - **重试信息**（重试次数、延迟提示等）
   - **错误统计**（CRC错误、格式错误、数据错误）
   - **进度信息**（解析HEX、发送数据块等）

2. **gui/views/FlashTab.py**
   - **HEX dump 显示**（时间戳、数据长度、CRC信息、总长度）
   - **发送/接收帧日志**（TX/RX 时间戳和长度信息）
   - **ASCII 预览日志**（时间戳和长度信息）

3. **gui/services/ConfigManager.py** 
   - 配置加载失败时的错误日志
   - 配置保存失败时的错误日志

4. **Usart_Para_FK.py** 
   - 作为命令行工具运行时的示例演示输出
   - 调试输出（构建/解析帧时）

5. **hex_parser.py** 
   - HEX文件解析失败时的错误日志
   - 行解析失败时的错误日志

## 使用示例

### 场景1：生产环境（无日志输出）

```python
# config/config.py
ENABLE_LOGGING = False
```

此时烧录标签页的所有日志窗口将保持空白：
- ? **不显示任何发送/接收帧**（包括 HEX dump）
- ? **不显示时间戳和长度信息**
- ? **不显示 CRC 和总长度信息**
- ? 只在出错时显示错误提示

**界面效果**：发送数据和接收数据日志窗口完全空白，烧录过程静默进行。

### 场景2：调试环境（显示所有日志）

```python
# config/config.py
ENABLE_LOGGING = True
```

此时烧录标签页会显示详细的烧录过程日志，便于问题排查。

## 注意事项

### 重要
1. ? **ENABLE_LOGGING 现在控制固件烧录日志** - 设置为 False 时烧录标签页的日志输出将被禁用
2. ? **所有模块日志都已正确实现** - FlashWorker、ConfigManager、Usart_Para_FK、hex_parser 的日志都受此控制
3. ?? **修改 `config/config.py` 后需要重启程序** 才能生效
4. ?? **`config/config.py` 必须使用 UTF-8 编码** - 不要手动修改编码格式

### 其他信息
- GUI 中的其他信息（如通信帧十六进制显示）不受此控制
- 独立脚本（如 `calc_crc.py` 等工具）不受此控制

## 验证日志控制是否生效

修改 `config/config.py` 后重启程序：

1. **设置 `ENABLE_LOGGING = False`** 后运行，烧录标签页中的日志输出应该被禁止
2. **设置 `ENABLE_LOGGING = True`** 后运行，烧录标签页中的日志输出应该正常显示

## 故障排除

### 问题：设置 ENABLE_LOGGING = False 但烧录标签页仍有日志

**可能的原因：**

1. **没有重启程序** - 修改配置后必须完全关闭并重启程序
2. **错误的日志来源** - 可能是来自其他地方的输出
3. **缓存问题** - Python 可能缓存了模块

**解决方案：**

- 确保修改了 `config/config.py` 的 ENABLE_LOGGING 值
- **完全关闭程序**（包括相关的所有进程）
- **重新打开程序**，应该看不到烧录日志了

### 问题：需要快速切换日志开关

**解决方案：**

直接编辑 `config/config.py` 文件，将 ENABLE_LOGGING 改为 True 或 False，然后重启程序即可立即生效。

## 技术实现

- **FlashWorker.py**: 添加了 `_emit_log()` 方法，根据 ENABLE_LOGGING 决定是否发送日志信号
- **所有日志调用**: 已从 `self.sigLog.emit()` 改为 `self._emit_log()`，确保日志受控制
- **导入机制**: 各模块在导入时自动从 config 模块读取 ENABLE_LOGGING 配置



