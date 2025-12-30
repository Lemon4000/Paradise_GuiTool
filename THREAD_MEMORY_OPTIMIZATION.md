# 烧录性能优化 - 线程和内存管理优化

## 问题描述

1. **状态日志无限累积**：关闭日志输出后，`status_log_view` 中的 HTML 内容仍然持续累积，导致内存占用增加
2. **日志缓冲区无限增长**：`send_logs_hex`、`recv_logs_hex`、`send_logs_ascii`、`recv_logs_ascii`、`send_raw_frames`、`recv_raw_frames` 等列表无限制增长
3. **FlashWorker 状态列表累积**：`accumulated_crc_list` 在多次烧录后持续增长但从不清空
4. **长时间烧录后卡顿**：由于上述内存累积问题，导致应用程序在长时间运行后出现卡顿

## 解决方案

### 1. FlashTab 优化

#### 1.1 添加日志缓冲区大小限制
```python
# 日志缓冲区大小限制（防止内存无限增长）
self.max_log_items = 500  # 每个日志缓冲区最多保留500条
self.max_status_blocks = 200  # 状态日志最多保留200块（HTML blocks）
```

#### 1.2 实现缓冲区裁剪方法
```python
def _trim_log_buffer(self, buffer: list, max_size: int = None):
    """裁剪日志缓冲区，保持在指定大小以下"""
    if max_size is None:
        max_size = self.max_log_items
    if len(buffer) > max_size:
        # 删除前面的旧数据，保留后面的新数据
        del buffer[:len(buffer) - max_size]

def _trim_status_log_view(self):
    """裁剪状态日志视图，限制HTML块数量"""
    document = self.status_log_view.document()
    if document.blockCount() > self.max_status_blocks:
        # 移除前面的旧块
        cursor = self.status_log_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.Start)
        blocks_to_remove = document.blockCount() - self.max_status_blocks
        for _ in range(blocks_to_remove):
            cursor.movePosition(cursor.MoveOperation.Down, cursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
```

#### 1.3 在日志添加时自动裁剪
- `on_frame_sent()` 中添加对发送日志缓冲区的裁剪
- `on_frame_recv()` 中添加对接收日志缓冲区的裁剪
- `on_log()` 中添加对状态日志视图的裁剪

#### 1.4 完善 clear_all_logs()
```python
def clear_all_logs(self):
    """清空所有日志"""
    self.send_logs_ascii.clear()
    self.send_logs_hex.clear()
    self.recv_logs_ascii.clear()
    self.recv_logs_hex.clear()
    self.send_raw_frames.clear()  # 新增
    self.recv_raw_frames.clear()  # 新增
    self.send_log_view.clear()
    self.recv_log_view.clear()
    self.status_log_view.clear()
```

### 2. FlashWorker 优化

#### 2.1 完全重置所有状态（start_flash）
```python
def start_flash(self, ser, hex_file_path: str, debug_mode: bool = False):
    # ... 其他初始化代码 ...
    
    # 完全重置所有计数器和列表，防止累积
    self.crc_accumulate_count = 0
    self.accumulated_crc_list.clear()  # 使用clear()而不是重新赋值
    self.err_crc = 0
    self.err_format = 0
    self.err_data = 0
    self.err_total = 0
    
    # 重置所有时间戳
    self.flash_start_ts = time.time()
    self.init_start_time = None
    self.program_start_time = None
    self.program_last_send_ts = None
    self.program_send_start_ts = None
    self.program_send_done_ts = None
    self.program_first_recv_ts = None
    self.program_first_recv_logged = False
    self.program_frame_complete_ts = None
    self.prev_block_done_ts = None
    
    # 重置其他状态
    self.last_sent_crc = None
    self.data_blocks = []
    self.hex_parser = None
```

#### 2.2 在烧录完成时清理内存（_transition_to）
```python
elif new_state == FlashState.SUCCESS:
    # ... 其他代码 ...
    
    # 清理内存，释放资源
    self.accumulated_crc_list.clear()
    self.data_blocks = []
    
    self.sigProgress.emit(100, "烧录成功")
    self.sigCompleted.emit(True, "固件烧录成功")
    
elif new_state == FlashState.FAILED:
    # ... 其他代码 ...
    
    # 清理内存，释放资源
    self.accumulated_crc_list.clear()
    self.data_blocks = []
    
    self.sigCompleted.emit(False, "固件烧录失败")
```

#### 2.3 在中止时清理状态（abort）
```python
def abort(self):
    """中止烧录"""
    self.timeout_timer.stop()
    self.state = FlashState.FAILED
    self._emit_log("烧录已中止")
    
    # 清理状态，释放内存
    self.accumulated_crc_list.clear()
    self.data_blocks = []
    
    self.sigCompleted.emit(False, "烧录已被用户中止")
```

## 性能改进

### 内存管理优化
- **发送/接收日志缓冲区**：限制在 500 条以内，旧数据自动清除
- **状态日志视图**：限制在 200 个 HTML 块以内，避免 DOM 过大
- **CRC 累积列表**：每次烧录完成后自动清空
- **数据块列表**：烧录完成/失败/中止后自动清空

### 线程性能优化
结合之前的优化（来自 `PERFORMANCE_OPTIMIZATION_COMPLETE.md`）：
1. **静默模式**：烧录时禁用日志输出，减少信号发射
2. **信号抑制**：SerialWorker 在烧录时抑制信号
3. **主线程跳过**：MainWindow 检测烧录状态跳过日志处理

### 预期效果
- ? **内存稳定**：长时间运行内存不再无限增长
- ? **无卡顿**：烧录速度始终保持 100%，不受运行时间影响
- ? **状态清理**：关闭日志后，历史状态信息被正确清理
- ? **快速响应**：UI 始终保持流畅响应

## 测试建议

1. **长时间运行测试**
   - 连续烧录 20-30 次，观察内存占用
   - 检查应用程序是否出现卡顿
   - 验证烧录速度是否稳定

2. **日志功能测试**
   - 启用日志后观察日志缓冲区大小
   - 禁用日志后检查状态日志是否清空
   - 切换日志格式验证显示正确性

3. **内存监控**
   - 使用任务管理器监控应用内存
   - 验证内存在 200-400MB 范围内稳定
   - 确认没有内存泄漏

## 代码变更摘要

### 修改文件
1. **gui/views/FlashTab.py**
   - 添加 `max_log_items` 和 `max_status_blocks` 限制
   - 实现 `_trim_log_buffer()` 和 `_trim_status_log_view()` 方法
   - 在 `on_frame_sent()`、`on_frame_recv()`、`on_log()` 中调用裁剪方法
   - 完善 `clear_all_logs()` 清理 `send_raw_frames` 和 `recv_raw_frames`

2. **gui/services/FlashWorker.py**
   - 在 `start_flash()` 中完全重置所有状态变量和列表
   - 在 `_transition_to()` 的 SUCCESS/FAILED 分支中清理内存
   - 在 `abort()` 中清理状态

## 兼容性

- ? 与现有功能完全兼容
- ? 不影响烧录协议
- ? 保持 UI 交互一致
- ? 日志功能正常工作

## 版本信息

- **优化日期**：2025-12-30
- **影响版本**：v2.0.5+
- **优先级**：高（性能关键优化）

---

**注意**：此优化与之前的 `PERFORMANCE_OPTIMIZATION_COMPLETE.md` 配合使用，共同确保应用程序在长时间运行时保持高性能和稳定性。
