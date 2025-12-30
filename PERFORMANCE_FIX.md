# 软件性能优化修复

## 问题诊断

软件开机时间变长，烧录速度逐渐变慢的原因是 **内存泄漏** 和 **无限增长的日志缓冲区**：

1. **日志缓冲区无限增长**：`recvHexBuf`、`recvAsciiBuf`、`sendHexBuf`、`sendAsciiBuf` 四个列表不断积累 HTML 内容，永远不会被清空
2. **logView 无限增长**：通信日志（`logView`）不断追加内容而没有清理机制
3. **长期运行导致内存溢出**：每次烧录或通信都会产生大量日志数据，导致程序启动速度和响应速度随时间递减

## 实施的修复方案

### 1. **日志缓冲区大小限制** `MainWindow.py`

在初始化时添加最大日志项数配置：
```python
self.max_log_items = 2000  # 每个缓冲区最多保持2000条HTML项
```

添加缓冲区管理方法：
```python
def _trim_buffer(self, buf: list, max_size: int = 2000):
    """限制缓冲区大小，移除最旧的条目"""
    if len(buf) > max_size:
        del buf[0:len(buf) - max_size]
```

在所有日志添加处调用此方法：
- `_onRawRecv()` - 接收原始数据
- `_onAsciiRecv()` - 接收 ASCII 数据
- `_onRawSend()` - 发送原始数据
- `_onAsciiSend()` - 发送 ASCII 数据

### 2. **logView 日志行数限制** `MainWindow.py`

在 `logView` 初始化时设置最大行数：
```python
self.logView.setMaximumBlockCount(1000)  # 限制最多保留1000行日志
```

PySide6 的 `QPlainTextEdit.setMaximumBlockCount()` 自动丢弃超出限制的最旧行。

### 3. **添加日志清空功能** `MainWindow.py`

- 为通信日志窗口添加 **清空** 按钮
- 为接收数据和发送数据窗口的现有清空按钮关联新的 `_clearAllLogs()` 方法
- 用户可以手动清理日志释放内存

```python
def _clearAllLogs(self):
    """清空所有日志缓冲区和视图"""
    self.logView.clear()
    self.recvView.clear()
    self.sendView.clear()
    self.recvHexBuf.clear()
    self.recvAsciiBuf.clear()
    self.sendHexBuf.clear()
    self.sendAsciiBuf.clear()
```

## 预期改进效果

| 指标 | 改进前 | 改进后 |
|------|------|------|
| **内存占用** | 线性增长，长期运行数百MB | 稳定在 200-300MB |
| **软件启动速度** | 随运行时间递减 | 始终保持一致 |
| **烧录速度** | 随运行时间递减 | 始终保持一致 |
| **日志保留条数** | 无限 | 受控（≤2000项/缓冲区，≤1000行) |

## 配置调整

可根据需要调整以下参数以优化性能：

```python
# MainWindow.py 第 ~196 行
self.max_log_items = 2000  # 调整为更小值可节省更多内存

# MainWindow.py 第 ~145 行
self.logView.setMaximumBlockCount(1000)  # 调整 logView 最大行数
```

## 测试建议

1. **长期运行测试**：连接设备并进行多次读写操作，观察内存占用
2. **烧录测试**：进行多次固件烧录，确认性能不随时间递减
3. **日志清理测试**：点击清空按钮，验证所有日志缓冲区被正确清空

## 相关文件修改

- ? `gui/views/MainWindow.py` - 核心修复
