"""
固件烧录标签页
支持拖拽HEX文件并烧录到下位机
"""
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QFrame, QGroupBox, QMessageBox, QComboBox, QDockWidget, QMainWindow
)
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent if isinstance(parent, QMainWindow) else None
        self.serial_port = None
        self.serial_worker = None  # 串口worker引用
        self.flash_worker = None
        self.hex_file_path = None
        self.is_flashing = False

        self._init_ui()

    # ---------------- 日志格式化工具 ----------------
    @staticmethod
    def _hex_dump(hex_str: str, width: int = 16) -> str:
        """HEX字符串美观输出: 十六进制+ASCII，全量显示不截断。"""
        try:
            data = bytes.fromhex(hex_str)
        except Exception:
            return "[格式错误]"

        total = len(data)
        lines = []
        for i in range(0, total, width):
            chunk = data[i:i + width]
            hex_part = ' '.join(f"{b:02X}" for b in chunk)
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            lines.append(f"{i:04X}: {hex_part:<{width * 3 - 1}} |{ascii_part}|")

        lines.append(f"总长度 {total} 字节")
        if total >= 2:
            crc = data[-2:]
            lines.append(f"CRC(末尾2字节假定为CRC16): 0x{crc.hex().upper()}")

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
        """在主窗口创建烧录日志Dock，默认已停靠，可拖拽/浮动。"""
        if not self.main_window:
            return
        if self.dock_send:
            if show_immediately:
                self.dock_send.show(); self.dock_recv.show(); self.dock_status.show()
            return

        def make_dock(title: str, widget: QWidget, area=Qt.RightDockWidgetArea):
            dock = QDockWidget(title, self.main_window)
            dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
            dock.setAllowedAreas(Qt.AllDockWidgetAreas)
            dock.setWidget(widget)
            self.main_window.addDockWidget(area, dock)
            if show_immediately:
                dock.show()
            else:
                dock.hide()
            return dock

        send_wrap = QWidget()
        send_layout = QVBoxLayout(send_wrap)
        send_layout.addWidget(self.send_log_view)

        recv_wrap = QWidget()
        recv_layout = QVBoxLayout(recv_wrap)
        recv_layout.addWidget(self.recv_log_view)

        status_wrap = QWidget()
        status_layout = QVBoxLayout(status_wrap)
        status_layout.addWidget(self.status_log_view)

        self.dock_send = make_dock("烧录-发送数据", send_wrap, Qt.RightDockWidgetArea)
        self.dock_recv = make_dock("烧录-接收数据", recv_wrap, Qt.RightDockWidgetArea)
        self.dock_status = make_dock("烧录-状态信息", status_wrap, Qt.BottomDockWidgetArea)

        # 初始布局：让发送和接收并排（右侧区域），状态在底部
        self.main_window.tabifyDockWidget(self.dock_send, self.dock_recv)
        self.dock_send.raise_()

    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)

        # 文件选择区域
        file_group = QGroupBox("HEX文件")
        file_layout = QVBoxLayout(file_group)

        self.drop_area = DropArea(self)
        file_layout.addWidget(self.drop_area)

        # 文件信息显示
        info_layout = QHBoxLayout()
        self.lbl_file_size = QLabel("文件大小: --")
        self.lbl_data_blocks = QLabel("数据块: --")
        self.lbl_address_range = QLabel("地址范围: --")
        info_layout.addWidget(self.lbl_file_size)
        info_layout.addWidget(self.lbl_data_blocks)
        info_layout.addWidget(self.lbl_address_range)
        info_layout.addStretch()
        file_layout.addLayout(info_layout)

        main_layout.addWidget(file_group)

        # 控制按钮
        btn_layout = QHBoxLayout()
        self.btn_browse = QPushButton("浏览...")
        self.btn_browse.clicked.connect(self.on_browse_clicked)

        self.btn_start = QPushButton("开始烧录")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.on_start_clicked)
        self.btn_start.setStyleSheet("QPushButton { font-weight: bold; font-size: 11pt; padding: 8px; }")

        self.btn_abort = QPushButton("中止")
        self.btn_abort.setEnabled(False)
        self.btn_abort.clicked.connect(self.on_abort_clicked)

        btn_layout.addWidget(self.btn_browse)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_abort)
        main_layout.addLayout(btn_layout)

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

        main_layout.addWidget(progress_group)

        # 日志控件（统一用于 Dock）
        self.log_format = QComboBox()
        self.log_format.addItems(['ASCII', 'HEX'])
        self.log_format.setCurrentText('HEX')
        self.log_format.currentTextChanged.connect(self.on_log_format_changed)

        self.send_log_view = QTextEdit()
        self.send_log_view.setReadOnly(True)
        self.recv_log_view = QTextEdit()
        self.recv_log_view.setReadOnly(True)
        self.status_log_view = QTextEdit()
        self.status_log_view.setReadOnly(True)

        # 控制行（显示格式 + 清空）
        ctrl_layout = QHBoxLayout()
        ctrl_layout.addWidget(QLabel("显示格式:"))
        ctrl_layout.addWidget(self.log_format)
        ctrl_layout.addStretch()
        btn_clear_log = QPushButton("清空日志")
        btn_clear_log.clicked.connect(self.clear_all_logs)
        ctrl_layout.addWidget(btn_clear_log)
        main_layout.addLayout(ctrl_layout)

        # 创建并显示 Dock（默认停靠，支持拖拽/全屏浮动）
        self.dock_send = None
        self.dock_recv = None
        self.dock_status = None
        if self.main_window:
            self._init_dock_logs(show_immediately=True)

        # 缓存日志数据
        self.send_logs_ascii = []
        self.send_logs_hex = []
        self.recv_logs_ascii = []
        self.recv_logs_hex = []

    def on_browse_clicked(self):
        """浏览文件"""
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择HEX文件",
            "",
            "HEX Files (*.hex);;All Files (*.*)"
        )
        if file_path:
            self.on_file_selected(file_path)
            self.drop_area.file_path = file_path
            self.drop_area.label.setText(f"已选择:\n{os.path.basename(file_path)}")

    def on_file_selected(self, file_path: str):
        """文件选择回调"""
        self.hex_file_path = file_path
        self.status_log_view.append(f"选择文件: {file_path}")

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
        self.btn_start.setEnabled(False)
        self.btn_abort.setEnabled(True)
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
        self.flash_worker.start_flash(self.serial_port, self.hex_file_path)

    def on_abort_clicked(self):
        """中止烧录"""
        if self.flash_worker:
            self.flash_worker.abort()

    def on_progress(self, percent: int, message: str):
        """进度更新"""
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(message)

    def on_completed(self, success: bool, message: str):
        """烧录完成"""
        self.is_flashing = False
        self.btn_start.setEnabled(True)
        self.btn_abort.setEnabled(False)
        self.btn_browse.setEnabled(True)

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

        # HEX格式（分行dump + CRC展示，自动截断）
        dump = self._hex_dump(hex_str)
        self.send_logs_hex.append(f"[{timestamp}] TX len={data_len}B\n{dump}")

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

        # HEX格式（分行dump + CRC展示，自动截断）
        dump = self._hex_dump(hex_str)
        self.recv_logs_hex.append(f"[{timestamp}] RX len={data_len}B\n{dump}")

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

    def on_log_format_changed(self, format_text: str):
        """日志格式切换"""
        self._update_send_display()
        self._update_recv_display()

    def _update_send_display(self):
        """更新发送日志显示"""
        if self.log_format.currentText() == 'HEX':
            self.send_log_view.setPlainText('\n'.join(self.send_logs_hex))
        else:
            self.send_log_view.setPlainText('\n'.join(self.send_logs_ascii))

        # 滚动到底部
        cursor = self.send_log_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.send_log_view.setTextCursor(cursor)

    def _update_recv_display(self):
        """更新接收日志显示"""
        if self.log_format.currentText() == 'HEX':
            self.recv_log_view.setPlainText('\n'.join(self.recv_logs_hex))
        else:
            self.recv_log_view.setPlainText('\n'.join(self.recv_logs_ascii))

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
