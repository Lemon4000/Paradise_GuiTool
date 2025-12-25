"""
固件烧录标签页
支持拖拽HEX文件并烧录到下位机
"""
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QFrame, QGroupBox, QMessageBox, QComboBox, QDockWidget, QMainWindow, QCheckBox, QSplitter
)
from PySide6.QtGui import QFontDatabase
import os
from gui.services.FlashWorker import FlashWorker, FlashState
from hex_parser import HexParser


class DropArea(QFrame):
    """拖拽区域"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.setMinimumHeight(150)
        self.setStyleSheet("""
            DropArea {
                background-color: #f0f0f0;
                border: 2px dashed #999;
                border-radius: 8px;
            }
            DropArea:hover {
                background-color: #e0e0e0;
                border-color: #666;
            }
        """)

        layout = QVBoxLayout(self)
        self.label = QLabel("拖入HEX文件到此处\n或点击选择文件")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-size: 14pt; color: #666;")
        layout.addWidget(self.label)

        self.file_path = None
        self.parent_widget = parent

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path.lower().endswith('.hex'):
                self.file_path = file_path
                self.label.setText(f"已选择:\n{os.path.basename(file_path)}")
                if self.parent_widget:
                    self.parent_widget.on_file_selected(file_path)
            else:
                self.label.setText("请选择.hex文件")

    def mousePressEvent(self, event):
        """点击选择文件"""
        if self.parent_widget:
            self.parent_widget.on_browse_clicked()

    def clear(self):
        """清空选择"""
        self.file_path = None
        self.label.setText("拖入HEX文件到此处\n或点击选择文件")


class FlashTab(QWidget):
    """固件烧录标签页"""
    def __init__(self, parent=None, config_manager=None):
        super().__init__(parent)
        self.main_window = parent if isinstance(parent, QMainWindow) else None
        self.config_manager = config_manager  # 配置管理器
        self.serial_port = None
        self.serial_worker = None  # 串口worker引用
        self.flash_worker = None
        self.hex_file_path = None
        self.is_flashing = False
        self.debug_mode = False
        # 日志配色（固定）
        self.addr_color = "#F75BC6"  # 247,91,198
        self.hex_color = "#41FF41"   # 65,255,65
        self.ascii_color = "#FFB000" # 255,176,0

        self._init_ui()

    # ---------------- 日志格式化工具 ----------------
    @staticmethod
    def _hex_dump(hex_str: str, width: int = 16, base_address: int | None = None, return_parts: bool = False, html_color: bool = False, addr_color: str | None = None, hex_color: str | None = None, ascii_color: str | None = None):
        """HEX字符串美观输出: 十六进制+ASCII，全量显示不截断。

        base_address: 如果提供，地址列显示为绝对地址 (0xXXXXXXXX)，否则为偏移 0000.
        return_parts: 为 True 时返回 (整体文本, 地址列, HEX列, ASCII列)。
        html_color: 为 True 时返回HTML格式彩色文本。
        """
        try:
            data = bytes.fromhex(hex_str)
        except Exception:
            return ("[格式错误]", "", "", "") if return_parts else "[格式错误]"

        total = len(data)
        lines = []
        addr_lines = []
        hex_lines = []
        ascii_lines = []
        base = base_address if base_address is not None else 0
        
        # 颜色定义：地址、HEX、ASCII（可外部传入）
        addr_color = addr_color or "#4A90E2"
        hex_color = hex_color or "#50C878"
        ascii_color = ascii_color or "#FF8C42"
        
        for i in range(0, total, width):
            chunk = data[i:i + width]
            hex_part = ' '.join(f"{b:02X}" for b in chunk)
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            addr_val = base + i
            addr_str = f"0x{addr_val:08X}" if base_address is not None else f"{i:04X}"
            
            if html_color:
                line = f'<span style="color:{addr_color};">{addr_str}</span>: <span style="color:{hex_color};">{hex_part:<{width * 3 - 1}}</span> |<span style="color:{ascii_color};">{ascii_part}</span>|'
                lines.append(line)
            else:
                lines.append(f"{addr_str}: {hex_part:<{width * 3 - 1}} |{ascii_part}|")
            
            addr_lines.append(addr_str)
            hex_lines.append(hex_part)
            ascii_lines.append(ascii_part)

        if html_color:
            lines.append(f'<span style="color:#999;">总长度 {total} 字节</span>')
            if total >= 2:
                crc = data[-2:]
                lines.append(f'<span style="color:#999;">CRC(末尾2字节假定为CRC16): 0x{crc.hex().upper()}</span>')
        else:
            lines.append(f"总长度 {total} 字节")
            if total >= 2:
                crc = data[-2:]
                lines.append(f"CRC(末尾2字节假定为CRC16): 0x{crc.hex().upper()}")

        if return_parts:
            return '\n'.join(lines), '\n'.join(addr_lines), '\n'.join(hex_lines), '\n'.join(ascii_lines)
        return '\n'.join(lines)

    @staticmethod
    def _ascii_preview(hex_str: str) -> str:
        """ASCII预览：不可打印替换为.，不截断。"""
        try:
            data = bytes.fromhex(hex_str)
        except Exception:
            return "[格式错误]"

        return ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)

    def _init_dock_logs(self, show_immediately: bool = False):
        """保留接口以兼容旧逻辑，但当前使用内嵌日志，不再创建Dock。"""
        return

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)

        # 主区域左右分栏：左侧文件信息，右侧控制/进度
        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        # 文件选择区域（左）
        file_group = QGroupBox("HEX文件")
        file_layout = QVBoxLayout(file_group)

        self.drop_area = DropArea(self)
        self.drop_area.setMinimumHeight(200)
        file_layout.addWidget(self.drop_area)

        info_layout = QHBoxLayout()
        self.lbl_file_size = QLabel("文件大小: --")
        self.lbl_data_blocks = QLabel("数据块: --")
        self.lbl_address_range = QLabel("地址范围: --")
        info_layout.addWidget(self.lbl_file_size)
        info_layout.addWidget(self.lbl_data_blocks)
        info_layout.addWidget(self.lbl_address_range)
        info_layout.addStretch()
        file_layout.addLayout(info_layout)

        # 右侧控制区域
        right_wrap = QWidget()
        right_layout = QVBoxLayout(right_wrap)
        right_layout.setSpacing(10)

        # 控制按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.clicked.connect(self.on_browse_clicked)

        self.chk_debug = QCheckBox("调试模式(手动下一步)")
        self.chk_debug.setToolTip("启用后发送指令后无需等待回应，点击‘下一步’手动推进流程，日志会提示期望回应。")

        self.btn_start = QPushButton("开始烧录")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.on_start_clicked)
        self.btn_start.setStyleSheet("QPushButton { font-weight: bold; font-size: 11pt; padding: 8px; }")

        self.btn_abort = QPushButton("中止")
        self.btn_abort.setEnabled(False)
        self.btn_abort.clicked.connect(self.on_abort_clicked)

        self.btn_next_step = QPushButton("下一步")
        self.btn_next_step.setEnabled(False)
        self.btn_next_step.setToolTip("调试模式下，手动进入下一步")
        self.btn_next_step.clicked.connect(self.on_next_step_clicked)

        btn_layout.addWidget(self.btn_browse)
        btn_layout.addWidget(self.chk_debug)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_abort)
        btn_layout.addWidget(self.btn_next_step)
        right_layout.addLayout(btn_layout)

        # 进度条
        progress_group = QGroupBox("烧录进度")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("就绪")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.lbl_status)

        right_layout.addWidget(progress_group)

        # 日志控件（统一用于 Dock）
        self.log_format = QComboBox()
        self.log_format.addItems(['完整HEX', 'ASCII预览', '地址列', 'HEX列', 'ASCII列'])
        self.log_format.setCurrentText('完整HEX')
        self.log_format.currentTextChanged.connect(self.on_log_format_changed)

        self.send_log_view = QTextEdit()
        self.send_log_view.setReadOnly(True)
        self.recv_log_view = QTextEdit()
        self.recv_log_view.setReadOnly(True)
        self.status_log_view = QTextEdit()
        self.status_log_view.setReadOnly(True)
        self._apply_monospace(self.send_log_view)
        self._apply_monospace(self.recv_log_view)
        self._apply_monospace(self.status_log_view)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(6)
        ctrl_layout.addWidget(QLabel("显示格式:"))
        ctrl_layout.addWidget(self.log_format)
        ctrl_layout.addStretch()
        btn_clear_log = QPushButton("清空日志")
        btn_clear_log.clicked.connect(self.clear_all_logs)
        ctrl_layout.addWidget(btn_clear_log)
        right_layout.addLayout(ctrl_layout)

        # 固定配色，无调色板

        right_layout.addStretch()

        content_layout.addWidget(file_group, 5)
        content_layout.addWidget(right_wrap, 2)
        content_layout.setStretch(0, 5)
        content_layout.setStretch(1, 2)
        main_layout.addLayout(content_layout)

        # 内嵌日志区域：顶部发送/接收横向分栏，底部状态信息可上下拖动
        self.log_group = QGroupBox("烧录日志")
        log_group_layout = QVBoxLayout(self.log_group)

        top_split = QSplitter(Qt.Horizontal)
        top_split.addWidget(self._wrap_log_panel("发送数据", self.send_log_view))
        top_split.addWidget(self._wrap_log_panel("接收数据", self.recv_log_view))

        main_split = QSplitter(Qt.Vertical)
        main_split.addWidget(top_split)
        main_split.addWidget(self._wrap_log_panel("状态信息", self.status_log_view))
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 1)

        log_group_layout.addWidget(main_split)
        main_layout.addWidget(self.log_group, 3)

        # 缓存日志数据
        self.send_logs_ascii = []
        self.send_logs_hex = []
        self.recv_logs_ascii = []
        self.recv_logs_hex = []
        self.send_raw_frames = []  # 仅存储HEX字符串原文
        self.recv_raw_frames = []

    def _wrap_log_panel(self, title: str, widget: QWidget) -> QWidget:
        wrap = QGroupBox(title)
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(widget)
        return wrap

    def _apply_monospace(self, widget: QTextEdit):
        try:
            mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
            widget.setFont(mono)
        except Exception:
            pass

    def _get_colors(self):
        return self.addr_color, self.hex_color, self.ascii_color

    def _guess_base_address(self, hex_str: str) -> int | None:
        """尝试从帧里解析 START 后的地址 (HEX:STARTXXXXXXXX)。失败则返回 None。"""
        try:
            data = bytes.fromhex(hex_str)
            text = data.decode('latin1', errors='ignore')
            key = "HEX:START"
            idx = text.find(key)
            if idx != -1 and len(text) >= idx + len(key) + 8:
                addr_str = text[idx + len(key): idx + len(key) + 8]
                if all(c in '0123456789ABCDEFabcdef' for c in addr_str):
                    return int(addr_str, 16)
        except Exception:
            return None
        return None

    def _update_column_display(self, view: QTextEdit, raw_frames: list, column_type: str):
        """显示特定列数据供用户直接选中复制，带颜色。"""
        # 颜色定义
        addr_color, hex_color, ascii_color = self._get_colors()
        
        lines = []
        for hex_str in raw_frames:
            base = self._guess_base_address(hex_str)
            dump, addr_col, hex_col, ascii_col = self._hex_dump(hex_str, base_address=base, return_parts=True)
            if column_type == '地址列':
                colored = f'<span style="color:{addr_color};">{addr_col}</span>'
                lines.append(colored)
            elif column_type == 'HEX列':
                colored = f'<span style="color:{hex_color};">{hex_col}</span>'
                lines.append(colored)
            elif column_type == 'ASCII列':
                colored = f'<span style="color:{ascii_color};">{ascii_col}</span>'
                lines.append(colored)
        html = '<div style="white-space: pre; font-family: monospace;">' + '<br><br>'.join(lines) + '</div>'
        view.setHtml(html)

    def on_browse_clicked(self):
        """浏览文件"""
        from PySide6.QtWidgets import QFileDialog
        import os
        
        # 获取上次使用的目录
        initial_dir = ""
        if self.config_manager:
            last_path = self.config_manager.get_last_hex_path()
            if last_path and os.path.exists(os.path.dirname(last_path)):
                initial_dir = os.path.dirname(last_path)
            elif os.path.exists(last_path):
                initial_dir = last_path
        
        # 如果没有历史路径或路径不存在，使用根目录
        if not initial_dir:
            initial_dir = os.getcwd()
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择HEX文件",
            initial_dir,
            "HEX Files (*.hex);;All Files (*.*)"
        )
        if file_path:
            self.on_file_selected(file_path)
            self.drop_area.file_path = file_path
            self.drop_area.label.setText(f"已选择:\n{os.path.basename(file_path)}")
            
            # 保存到配置
            if self.config_manager:
                self.config_manager.set_last_hex_path(file_path)

    def on_file_selected(self, file_path: str):
        """文件选择回调"""
        self.hex_file_path = file_path
        self.status_log_view.append(f"选择文件: {file_path}")
        
        # 保存到配置
        if self.config_manager:
            self.config_manager.set_last_hex_path(file_path)

        # 解析文件获取信息
        try:
            parser = HexParser()
            if parser.parse_file(file_path):
                total_bytes = parser.get_data_bytes()
                blocks = parser.get_data_blocks(block_size=256)
                self.lbl_file_size.setText(f"文件大小: {total_bytes} 字节")
                self.lbl_data_blocks.setText(f"数据块: {len(blocks)}")

                if parser.min_address is not None and parser.max_address is not None:
                    self.lbl_address_range.setText(
                        f"地址范围: 0x{parser.min_address:08X} - 0x{parser.max_address:08X}"
                    )

                self.btn_start.setEnabled(True)
                self.status_log_view.append("HEX文件解析成功")
            else:
                self.status_log_view.append("HEX文件解析失败")
                self.btn_start.setEnabled(False)

        except Exception as e:
            self.status_log_view.append(f"解析文件异常: {str(e)}")
            self.btn_start.setEnabled(False)

    def on_start_clicked(self):
        """开始烧录"""
        if not self.hex_file_path:
            QMessageBox.warning(self, "警告", "请先选择HEX文件")
            return

        if not self.serial_port:
            QMessageBox.warning(self, "警告", "请先连接串口")
            return

        # 确认开始烧录
        reply = QMessageBox.question(
            self,
            "确认烧录",
            "确定要开始烧录固件吗？\n烧录过程中请勿断开串口连接。",
            QMessageBox.Yes | QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # 开始烧录
        self.is_flashing = True
        self.debug_mode = self.chk_debug.isChecked()
        self.btn_start.setEnabled(False)
        self.btn_abort.setEnabled(True)
        self.btn_next_step.setEnabled(self.debug_mode)
        self.btn_browse.setEnabled(False)
        self.progress_bar.setValue(0)
        self.clear_all_logs()

        # 启用透传模式
        if self.serial_worker:
            self.serial_worker.setPassthroughMode(True)

        # 创建worker
        self.flash_worker = FlashWorker()
        self.flash_worker.sigProgress.connect(self.on_progress)
        self.flash_worker.sigCompleted.connect(self.on_completed)
        self.flash_worker.sigLog.connect(self.on_log)
        self.flash_worker.sigFrameSent.connect(self.on_frame_sent)
        self.flash_worker.sigFrameRecv.connect(self.on_frame_recv)
        self.flash_worker.sigErrorDetail.connect(self.on_error_detail)
        self.flash_worker.sigVerifyOk.connect(self.on_verify_ok)

        # 启动烧录
        self.flash_worker.start_flash(self.serial_port, self.hex_file_path, debug_mode=self.debug_mode)

    def on_abort_clicked(self):
        """中止烧录"""
        if self.flash_worker:
            self.flash_worker.abort()
        self.btn_next_step.setEnabled(False)

    def on_progress(self, percent: int, message: str):
        """进度更新"""
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(message)

    def on_completed(self, success: bool, message: str):
        """烧录完成"""
        self.is_flashing = False
        self.debug_mode = False
        self.btn_start.setEnabled(True)
        self.btn_abort.setEnabled(False)
        self.btn_browse.setEnabled(True)
        self.btn_next_step.setEnabled(False)

        # 禁用透传模式
        if self.serial_worker:
            self.serial_worker.setPassthroughMode(False)

        if success:
            QMessageBox.information(self, "成功", message)
            self.lbl_status.setText("烧录成功")
        else:
            QMessageBox.critical(self, "失败", message)
            self.lbl_status.setText("烧录失败")

    def on_log(self, message: str):
        """状态日志消息"""
        import time
        timestamp = time.strftime("%H:%M:%S")
        self.status_log_view.append(f"[{timestamp}] {message}")

    def on_frame_sent(self, hex_str: str):
        """发送帧"""
        import time
        timestamp = time.strftime("%H:%M:%S")

        try:
            data_len = len(bytes.fromhex(hex_str))
        except Exception:
            data_len = 0

        # HEX格式（分行dump + CRC展示，带颜色）
        base = self._guess_base_address(hex_str)
        ac, hc, asc = self._get_colors()
        dump = self._hex_dump(hex_str, base_address=base, html_color=True, addr_color=ac, hex_color=hc, ascii_color=asc)
        self.send_logs_hex.append(f'<span style="color:#CCC;">[{timestamp}] TX len={data_len}B</span>\n{dump}')
        self.send_raw_frames.append(hex_str)

        # ASCII预览（不可打印替换为.，仅预览）
        preview = self._ascii_preview(hex_str)
        head_hex = ' '.join([hex_str[i:i+2] for i in range(0, min(len(hex_str), 64), 2)]).upper()
        self.send_logs_ascii.append(
            f"[{timestamp}] TX len={data_len}B\nHEX头部: {head_hex}\nASCII预览: {preview}")

        # 更新显示
        self._update_send_display()

    def on_frame_recv(self, hex_str: str):
        """接收帧"""
        import time
        timestamp = time.strftime("%H:%M:%S")

        try:
            data_len = len(bytes.fromhex(hex_str))
        except Exception:
            data_len = 0

        # HEX格式（分行dump + CRC展示，带颜色）
        base = self._guess_base_address(hex_str)
        ac, hc, asc = self._get_colors()
        dump = self._hex_dump(hex_str, base_address=base, html_color=True, addr_color=ac, hex_color=hc, ascii_color=asc)
        self.recv_logs_hex.append(f'<span style="color:#CCC;">[{timestamp}] RX len={data_len}B</span>\n{dump}')
        self.recv_raw_frames.append(hex_str)

        # ASCII预览（不可打印替换为.，仅预览）
        preview = self._ascii_preview(hex_str)
        head_hex = ' '.join([hex_str[i:i+2] for i in range(0, min(len(hex_str), 64), 2)]).upper()
        self.recv_logs_ascii.append(
            f"[{timestamp}] RX len={data_len}B\nHEX头部: {head_hex}\nASCII预览: {preview}")

        # 更新显示
        self._update_recv_display()

    def on_error_detail(self, error_type: str, expected: str, received: str):
        """详细错误信息"""
        import time
        timestamp = time.strftime("%H:%M:%S")

        if error_type == "CRC_MISMATCH":
            msg = f'<span style="color: red; font-weight: bold;">[{timestamp}] CRC校验失败!</span><br>'
            msg += f'  期望: <span style="color: blue;">{expected}</span><br>'
            msg += f'  实际: <span style="color: red;">{received}</span>'
            self.status_log_view.append(msg)
        elif error_type == "DATA_MISMATCH":
            msg = f'<span style="color: orange; font-weight: bold;">[{timestamp}] 数据内容错误!</span><br>'
            msg += f'  期望: <span style="color: blue;">{expected}</span><br>'
            msg += f'  实际: <span style="color: red;">{received}</span>'
            self.status_log_view.append(msg)
        elif error_type == "FORMAT_ERROR":
            msg = f'<span style="color: red; font-weight: bold;">[{timestamp}] 格式错误!</span><br>'
            msg += f'  期望格式: <span style="color: blue;">{expected}</span><br>'
            msg += f'  接收内容: <span style="color: red;">{received}</span>'
            self.status_log_view.append(msg)

    def on_verify_ok(self, expected: str, received: str):
        """校验成功"""
        import time
        timestamp = time.strftime("%H:%M:%S")
        msg = f'<span style="color: green; font-weight: bold;">[{timestamp}] 校验成功!</span><br>'
        msg += f'  期望: <span style="color: green;">{expected}</span><br>'
        msg += f'  实际: <span style="color: green;">{received}</span>'
        self.status_log_view.append(msg)

    def on_next_step_clicked(self):
        """调试模式：手动下一步"""
        if self.flash_worker:
            self.flash_worker.step_next()
        else:
            self.status_log_view.append("[WARN] 尚未开始烧录，无法下一步")

    def on_log_format_changed(self, format_text: str):
        """日志格式切换"""
        self._update_send_display()
        self._update_recv_display()

    def _update_send_display(self):
        """更新发送日志显示"""
        fmt = self.log_format.currentText()
        if fmt == '完整HEX':
            html = '<div style="white-space: pre; font-family: monospace;">' + '<br>'.join(self.send_logs_hex) + '</div>'
            self.send_log_view.setHtml(html)
        elif fmt == 'ASCII预览':
            self.send_log_view.setPlainText('\n'.join(self.send_logs_ascii))
        elif fmt in ('地址列', 'HEX列', 'ASCII列'):
            self._update_column_display(self.send_log_view, self.send_raw_frames, fmt)
        else:
            html = '<div style="white-space: pre; font-family: monospace;">' + '<br>'.join(self.send_logs_hex) + '</div>'
            self.send_log_view.setHtml(html)

        # 滚动到底部
        cursor = self.send_log_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.send_log_view.setTextCursor(cursor)

    def _update_recv_display(self):
        """更新接收日志显示"""
        fmt = self.log_format.currentText()
        if fmt == '完整HEX':
            html = '<div style="white-space: pre; font-family: monospace;">' + '<br>'.join(self.recv_logs_hex) + '</div>'
            self.recv_log_view.setHtml(html)
        elif fmt == 'ASCII预览':
            self.recv_log_view.setPlainText('\n'.join(self.recv_logs_ascii))
        elif fmt in ('地址列', 'HEX列', 'ASCII列'):
            self._update_column_display(self.recv_log_view, self.recv_raw_frames, fmt)
        else:
            html = '<div style="white-space: pre; font-family: monospace;">' + '<br>'.join(self.recv_logs_hex) + '</div>'
            self.recv_log_view.setHtml(html)

        # 滚动到底部
        cursor = self.recv_log_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.recv_log_view.setTextCursor(cursor)

    def clear_all_logs(self):
        """清空所有日志"""
        self.send_logs_ascii.clear()
        self.send_logs_hex.clear()
        self.recv_logs_ascii.clear()
        self.recv_logs_hex.clear()
        self.send_log_view.clear()
        self.recv_log_view.clear()
        self.status_log_view.clear()

    def set_serial_port(self, ser, worker=None):
        """设置串口"""
        self.serial_port = ser
        self.serial_worker = worker
        if ser and self.hex_file_path:
            self.btn_start.setEnabled(True)
        else:
            self.btn_start.setEnabled(False)

    def handle_received_data(self, data: bytes):
        """处理接收到的数据"""
        if self.is_flashing and self.flash_worker:
            self.flash_worker.handle_received_frame(data)
