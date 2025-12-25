from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QTextCursor, QIntValidator
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QTableView, QStatusBar, QToolBar, QFileDialog, QDockWidget, QPlainTextEdit, QTextEdit, QLabel, QMessageBox, QTabWidget, QLineEdit
)
try:
    from gui.models.ParamTableModel import ParamTableModel
    from gui.services.SerialWorker import SerialWorker
    from gui.services.ConfigManager import ConfigManager
    from gui.views.FlashTab import FlashTab
    from gui.views.BaudRateManagerDialog import BaudRateManagerDialog
except Exception:
    import sys, os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from gui.models.ParamTableModel import ParamTableModel
    from gui.services.SerialWorker import SerialWorker
    from gui.services.ConfigManager import ConfigManager
    from gui.views.FlashTab import FlashTab
    from gui.views.BaudRateManagerDialog import BaudRateManagerDialog
import Usart_Para_FK as proto

# Import version info
try:
    from version import __version__, __app_name__
except ImportError:
    __version__ = "1.0.0"
    __app_name__ = "Paradise GuiTool"

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'{__app_name__} v{__version__}')
        self.resize(1000, 680)
        
        # 初始化配置管理器
        self.config_manager = ConfigManager()

        self.portBox = QComboBox()
        self.portBox.setMinimumWidth(250)  # 增加宽度以显示详细信息
        self.port_device_map = {}  # 存储显示名称到设备名称的映射
        self.btnRefreshPort = QPushButton('🔄')  # 刷新串口按钮
        self.btnRefreshPort.setMaximumWidth(30)
        self.btnRefreshPort.setToolTip('刷新串口列表')
        
        self.groupBox = QComboBox()
        self.groupBox.addItems(['A'])
        
        # 创建波特率选择控件容器
        baudLayout = QHBoxLayout()
        baudLayout.setContentsMargins(0, 0, 0, 0)
        baudLayout.setSpacing(5)
        
        # 波特率下拉框（可编辑）
        self.baudBox = QComboBox()
        # 从配置管理器加载波特率列表
        baud_rates = self.config_manager.get_baud_rates()
        self.baudBox.addItems([str(b) for b in baud_rates])
        self.baudBox.setEditable(False)  # 初始为不可编辑（预设模式）
        self.baudBox.setInsertPolicy(QComboBox.NoInsert)  # 防止将自定义值插入列表
        self.baudBox.lineEdit().setValidator(QIntValidator(300, 3000000)) if self.baudBox.lineEdit() else None
        self.baudBox.setMinimumWidth(100)
        self.baudBox.setToolTip('选择预设波特率或输入自定义值')
        
        # 自定义波特率切换按钮
        self.customBaudBtn = QPushButton('自定义')
        self.customBaudBtn.setMaximumWidth(65)
        self.customBaudBtn.setCheckable(True)
        self.customBaudBtn.setToolTip('切换到自定义波特率输入')
        
        # 波特率管理按钮
        self.manageBaudBtn = QPushButton('⚙')
        self.manageBaudBtn.setMaximumWidth(30)
        self.manageBaudBtn.setToolTip('管理波特率列表')
        
        baudLayout.addWidget(QLabel('波特率:'))
        baudLayout.addWidget(self.baudBox)
        baudLayout.addWidget(self.customBaudBtn)
        baudLayout.addWidget(self.manageBaudBtn)
        
        baudWidget = QWidget()
        baudWidget.setLayout(baudLayout)
        
        self.btnConnect = QPushButton('连接')
        self.btnDisconnect = QPushButton('断开')
        self.btnRead = QPushButton('读取')
        self.btnWrite = QPushButton('写入')
        self.btnExit = QPushButton('退出编程')
        self.btnImport = QPushButton('导入映射')
        self.btnRefresh = QPushButton('刷新映射')

        self.lblStatusLight = QLabel()
        self.lblStatusLight.setFixedSize(20, 20)
        self._setStatusLight('red')

        tb = QToolBar()
        tb.addWidget(QLabel('状态:'))
        tb.addWidget(self.lblStatusLight)
        tb.addSeparator()
        tb.addWidget(QLabel('串口:'))
        tb.addWidget(self.portBox)
        tb.addWidget(self.btnRefreshPort)
        tb.addWidget(QLabel('组:'))
        tb.addWidget(self.groupBox)
        tb.addWidget(baudWidget)
        tb.addWidget(self.btnConnect)
        tb.addWidget(self.btnDisconnect)
        tb.addSeparator()
        tb.addWidget(self.btnRead)
        tb.addWidget(self.btnWrite)
        tb.addWidget(self.btnExit)
        tb.addSeparator()
        tb.addWidget(self.btnImport)
        tb.addWidget(self.btnRefresh)
        self.addToolBar(tb)

        self.table = QTableView()
        self.model = ParamTableModel('A')
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)

        # 参数表格标签页
        param_tab = QWidget()
        param_layout = QVBoxLayout(param_tab)
        param_layout.addWidget(self.table)

        # 固件烧录标签页（传入主窗口和配置管理器）
        self.flash_tab = FlashTab(self, self.config_manager)

        # 创建标签控件
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(param_tab, "参数配置")
        self.tab_widget.addTab(self.flash_tab, "固件烧录")

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addWidget(self.tab_widget)
        self.setCentralWidget(central)

        self.logDock = QDockWidget('通信日志', self)
        self.logView = QPlainTextEdit()
        self.logView.setReadOnly(True)
        self.logDock.setWidget(self.logView)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.logDock)

        self.recvDock = QDockWidget('接收数据', self)
        self.recvView = QTextEdit()
        self.recvView.setReadOnly(True)
        self.recvFormat = QComboBox()
        self.recvFormat.addItems(['HEX','ASCII'])
        self.recvFormat.setCurrentText('ASCII')
        recvWrap = QWidget()
        recvLay = QVBoxLayout(recvWrap)
        recvCtl = QHBoxLayout()
        btnRecvClear = QPushButton('清空')
        btnRecvClear.clicked.connect(lambda: self.recvView.clear())
        recvCtl.addWidget(QLabel('显示:'))
        recvCtl.addWidget(self.recvFormat)
        recvCtl.addWidget(btnRecvClear)
        recvLay.addLayout(recvCtl)
        recvLay.addWidget(self.recvView)
        self.recvDock.setWidget(recvWrap)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.recvDock)

        self.sendDock = QDockWidget('发送数据', self)
        self.sendView = QTextEdit()
        self.sendView.setReadOnly(True)
        self.sendFormat = QComboBox()
        self.sendFormat.addItems(['HEX','ASCII'])
        self.sendFormat.setCurrentText('ASCII')
        sendWrap = QWidget()
        sendLay = QVBoxLayout(sendWrap)
        sendCtl = QHBoxLayout()
        btnSendClear = QPushButton('清空')
        btnSendClear.clicked.connect(lambda: self.sendView.clear())
        sendCtl.addWidget(QLabel('显示:'))
        sendCtl.addWidget(self.sendFormat)
        sendCtl.addWidget(btnSendClear)
        sendLay.addLayout(sendCtl)
        sendLay.addWidget(self.sendView)
        self.sendDock.setWidget(sendWrap)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.sendDock)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        self.worker = SerialWorker()
        self.recvHexBuf = []
        self.recvAsciiBuf = []
        self.sendHexBuf = []
        self.sendAsciiBuf = []
        self.recvToggle = False
        self.sendToggle = False
        
        # 串口自动刷新定时器
        self.port_refresh_timer = QTimer()
        self.port_refresh_timer.timeout.connect(self._refreshPorts)
        self.port_refresh_timer.start(2000)  # 每2秒刷新一次
        
        self._bindSignals()
        self._refreshPorts()
        self._updateButtons(False)
        
        # 从配置管理器加载上次使用的波特率
        last_baud = self.config_manager.get_last_baud_rate()
        idx = self.baudBox.findText(str(last_baud))
        if idx != -1:
            self.baudBox.setCurrentIndex(idx)
        else:
            # 如果找不到，使用默认值
            default_baud = self.config_manager.get_default_baud_rate()
            idx = self.baudBox.findText(str(default_baud))
            if idx != -1:
                self.baudBox.setCurrentIndex(idx)

    def _bindSignals(self):
        self.btnConnect.clicked.connect(self._onConnect)
        self.btnDisconnect.clicked.connect(self._onDisconnect)
        self.btnRead.clicked.connect(self._onRead)
        self.btnWrite.clicked.connect(self._onWrite)
        self.btnExit.clicked.connect(self._onExit)
        self.btnImport.clicked.connect(self._onImport)
        self.btnRefresh.clicked.connect(self._onRefresh)
        self.btnRefreshPort.clicked.connect(self._onRefreshPortClicked)
        self.manageBaudBtn.clicked.connect(self._onManageBaudRates)

        self.worker.sigConnected.connect(self._onConnected)
        self.worker.sigFrameSent.connect(self._onFrameSent)
        self.worker.sigFrameRecv.connect(self._onFrameRecv)
        self.worker.sigReadDone.connect(self._onReadDone)
        self.worker.sigWriteDone.connect(self._onWriteDone)
        self.worker.sigError.connect(self._onError)
        self.worker.sigRawRecv.connect(self._onRawRecv)
        self.worker.sigAsciiRecv.connect(self._onAsciiRecv)
        self.worker.sigRawSend.connect(self._onRawSend)
        self.worker.sigAsciiSend.connect(self._onAsciiSend)
        self.worker.sigReadFailed.connect(self._onReadFailed)
        self.worker.sigReplyOk.connect(self._onReplyOk)
        self.worker.sigReplyMismatch.connect(self._onReplyMismatch)
        self.worker.sigRecvBreak.connect(self._onRecvBreak)
        self.recvFormat.currentTextChanged.connect(self._onRecvFormatChanged)
        self.sendFormat.currentTextChanged.connect(self._onSendFormatChanged)
        self.baudBox.currentTextChanged.connect(self._onBaudChange)
        self.baudBox.editTextChanged.connect(self._onBaudChange)
        self.customBaudBtn.toggled.connect(self._onCustomBaudToggle)

    def _refreshPorts(self):
        """刷新串口列表，保持当前选择"""
        try:
            import serial.tools.list_ports as lp
            
            # 保存当前选择的设备名称
            current_text = self.portBox.currentText()
            current_device = self.port_device_map.get(current_text, '')
            
            # 获取所有串口
            ports = list(lp.comports())
            
            # 构建新的端口列表和映射
            new_items = []
            new_map = {}
            
            for port in ports:
                # 格式: COM3 - USB Serial Port (CH340)
                display_name = f"{port.device}"
                if port.description and port.description != port.device:
                    display_name += f" - {port.description}"
                elif port.manufacturer:
                    display_name += f" - {port.manufacturer}"
                
                new_items.append(display_name)
                new_map[display_name] = port.device
            
            # 检查列表是否有变化
            current_items = [self.portBox.itemText(i) for i in range(self.portBox.count())]
            if new_items != current_items:
                # 列表有变化，更新
                self.portBox.clear()
                self.port_device_map = new_map
                self.portBox.addItems(new_items)
                
                # 尝试恢复之前的选择
                if current_device:
                    for i, (display, device) in enumerate(new_map.items()):
                        if device == current_device:
                            self.portBox.setCurrentIndex(i)
                            break
        except Exception as e:
            self.portBox.clear()
            self.port_device_map = {}

    def _updateButtons(self, connected: bool):
        self.btnConnect.setEnabled(not connected)
        self.btnDisconnect.setEnabled(connected)
        self.btnRead.setEnabled(connected)
        self.btnWrite.setEnabled(connected)

    def _onRefreshPortClicked(self):
        """手动刷新串口列表"""
        self._refreshPorts()
        self.status.showMessage('串口列表已刷新', 1500)
    
    def _onConnect(self):
        display_name = self.portBox.currentText()
        # 从映射中获取实际设备名称
        port = self.port_device_map.get(display_name, display_name)
        self.worker.connectPort(port)

    def _onDisconnect(self):
        self.worker.disconnectPort()
        self.model.reload(self.groupBox.currentText())

    def _onRead(self):
        group = self.groupBox.currentText()
        self.worker.readGroup(group)
        self.status.showMessage('读取中…', 2000)

    def _onWrite(self):
        group = self.groupBox.currentText()
        values = self.model.valuesDict()
        self.worker.writeGroup(group, values)
        self.status.showMessage('写入中…', 2000)

    def _onExit(self):
        self.worker.sendExit()
        self.status.showMessage('已发送退出编程', 2000)

    def _onBaudChange(self, text: str):
        """处理波特率变化（预设或自定义）"""
        if not text:
            return
        
        try:
            baud = int(text)
            if 300 <= baud <= 3000000:
                self.worker.setBaudRate(baud)
                mode = '自定义' if self.customBaudBtn.isChecked() else '预设'
                self.status.showMessage(f'✓ {mode}波特率 {baud} bps', 1500)
            else:
                self.status.showMessage(f'⚠ 波特率范围: 300-3000000 bps', 1500)
        except ValueError:
            pass

    def _onCustomBaudToggle(self, checked: bool):
        """处理自定义波特率切换"""
        if checked:
            # 启用自定义模式：下拉框变为可编辑输入框
            current_value = self.baudBox.currentText()
            self.baudBox.setEditable(True)
            self.baudBox.setCurrentText(current_value)
            self.customBaudBtn.setText('预设')
            # 确保验证器已设置
            if self.baudBox.lineEdit():
                self.baudBox.lineEdit().setValidator(QIntValidator(300, 3000000))
                self.baudBox.lineEdit().setPlaceholderText('输入波特率 (300-3000000)')
            self.baudBox.setFocus()
            self.baudBox.lineEdit().selectAll()
        else:
            # 禁用自定义模式：恢复为预设下拉框
            self.baudBox.setEditable(False)
            self.customBaudBtn.setText('自定义')
            # 应用当前预设波特率
            current_baud = self.baudBox.currentText()
            try:
                baud = int(current_baud)
                self.worker.setBaudRate(baud)
                self.status.showMessage(f'✓ 切换回预设波特率 {baud} bps', 1500)
            except ValueError:
                pass

    def _onImport(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择映射文件', 'config', 'Excel/CSV (*.xlsx *.csv)')
        if path:
            # 直接复制到 config 目录或提示用户放置；此处仅提示刷新
            self.status.showMessage('已选择映射文件，请放置到 config 并刷新', 3000)

    def _onRefresh(self):
        group = self.groupBox.currentText()
        self.model.reload(group)
        self.status.showMessage('映射已刷新', 2000)
    
    def _onManageBaudRates(self):
        """打开波特率管理对话框"""
        dialog = BaudRateManagerDialog(self.config_manager, self)
        if dialog.exec():
            # 对话框关闭后重新加载波特率列表
            current_baud = self.baudBox.currentText()
            self.baudBox.clear()
            baud_rates = self.config_manager.get_baud_rates()
            self.baudBox.addItems([str(b) for b in baud_rates])
            # 尝试恢复之前的选择
            idx = self.baudBox.findText(current_baud)
            if idx != -1:
                self.baudBox.setCurrentIndex(idx)
            self.status.showMessage('波特率列表已更新', 2000)

    def _onConnected(self, ok: bool):
        self._updateButtons(ok)
        if ok:
            self._setStatusLight('green')
            self.status.showMessage('已连接', 3000)
            # 更新烧录标签页的串口状态
            self.flash_tab.set_serial_port(self.worker.ser, self.worker)
        else:
            self._setStatusLight('red')
            self.model.reload(self.groupBox.currentText())
            self.status.showMessage('连接失败或已断开，映射已刷新', 3000)
            # 清除烧录标签页的串口状态
            self.flash_tab.set_serial_port(None, None)

    def _onFrameSent(self, hexstr: str):
        # Check if this is a REPLY frame (hex for REPLY: is 5245504C593A)
        # If it is an auto-reply, we don't expect a response, so don't turn yellow.
        if '5245504C593A' not in hexstr.upper():
            self._setStatusLight('yellow')
        self.logView.appendPlainText('SEND: ' + hexstr)

    def _onFrameRecv(self, hexstr: str):
        self.logView.appendPlainText('RECV: ' + hexstr)

        # 如果正在烧录，将帧转发给烧录标签页
        try:
            frame_bytes = bytes.fromhex(hexstr)
            self.flash_tab.handle_received_data(frame_bytes)
        except Exception:
            pass

    def _onRawRecv(self, hexstr: str):
        # Format: [RX] HEX...
        spaced = hexstr.upper() + ' '
        bg_color = '#C1FFC1' if self.recvToggle else '#F0FFF0' # Alternating Green
        html = f'<span style="background-color:{bg_color}; color:black;">{spaced}</span>'
        self.recvHexBuf.append(html)
        if self.recvFormat.currentText() == 'HEX':
            self.recvView.moveCursor(QTextCursor.MoveOperation.End)
            self.recvView.insertHtml(html)

    def _onAsciiRecv(self, s: str):
        # Escape HTML special chars if needed
        safe_s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        bg_color = '#C1FFC1' if self.recvToggle else '#F0FFF0'
        html = f'<span style="background-color:{bg_color}; color:black;">{safe_s}</span>'
        self.recvToggle = not self.recvToggle
        self.recvAsciiBuf.append(html)
        if self.recvFormat.currentText() == 'ASCII':
            self.recvView.moveCursor(QTextCursor.MoveOperation.End)
            self.recvView.insertHtml(html)

    def _onReadDone(self, data: dict):
        if data:
            self.model.updateValues(data)
            self.status.showMessage('读取成功', 2000)
        else:
            self.status.showMessage('读取失败', 3000)

    def _onWriteDone(self, ok: bool):
        self.status.showMessage('写入成功' if ok else '写入失败', 3000)

    def _onRawSend(self, hexstr: str):
        spaced = ' '.join([hexstr[i:i+2] for i in range(0, len(hexstr), 2)]).upper() + ' '
        bg_color = '#C1C1FF' if self.sendToggle else '#F0F0FF' # Alternating Blue
        html = f'<span style="background-color:{bg_color}; color:black;">{spaced}</span><br><br>'
        self.sendHexBuf.append(html)
        if self.sendFormat.currentText() == 'HEX':
            self.sendView.moveCursor(QTextCursor.MoveOperation.End)
            self.sendView.insertHtml(html)

    def _onAsciiSend(self, s: str):
        safe_s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
        bg_color = '#C1C1FF' if self.sendToggle else '#F0F0FF'
        html = f'<span style="background-color:{bg_color}; color:black;">{safe_s}</span><br><br>'
        self.sendToggle = not self.sendToggle
        self.sendAsciiBuf.append(html)
        if self.sendFormat.currentText() == 'ASCII':
            self.sendView.moveCursor(QTextCursor.MoveOperation.End)
            self.sendView.insertHtml(html)

    def _onError(self, msg: str):
        self.status.showMessage(msg, 3000)
        self.logView.appendPlainText('ERR: ' + msg)
        try:
            QMessageBox.critical(self, '错误', msg)
        except Exception:
            pass

    def _onReadFailed(self):
        try:
            self.model.setAllValuesError()
        except Exception:
            pass

    def _onRecvFormatChanged(self, text: str):
        self.recvView.clear()
        if text == 'HEX':
            # Buffers now contain HTML fragments
            full_html = ''.join(self.recvHexBuf)
            self.recvView.setHtml(full_html)
        else:
            full_html = ''.join(self.recvAsciiBuf)
            self.recvView.setHtml(full_html)
        self.recvView.moveCursor(QTextCursor.MoveOperation.End)

    def _setStatusLight(self, color: str):
        colors = {
            'red': '#FF0000',
            'green': '#00FF00',
            'blue': '#0000FF',
            'yellow': '#FFFF00'
        }
        c = colors.get(color, '#FF0000')
        self.lblStatusLight.setStyleSheet(f"background-color: {c}; border-radius: 10px; border: 1px solid gray;")

    def _onReplyOk(self, sent_crc: str, reply_crc: str):
        self._setStatusLight('blue')
        self.status.showMessage(f'收到回复 OK (SentCRC:{sent_crc}, ReplyCRC:{reply_crc})', 3000)

    def _onReplyMismatch(self, msg: str):
        self._setStatusLight('red')
        self._onError(msg)

    def _onRecvBreak(self):
        # Insert break in buffers and view
        # Add extra <br> to make a blank line
        html = '<br><br>'
        self.recvHexBuf.append(html)
        self.recvAsciiBuf.append(html)
        self.recvView.moveCursor(QTextCursor.MoveOperation.End)
        self.recvView.insertHtml(html)
        # Reset toggle to ensure next line starts with first color? 
        # Or keep alternating? Resetting might look cleaner for new block.
        self.recvToggle = False

    def _onSendFormatChanged(self, text: str):
        self.sendView.clear()
        if text == 'HEX':
            full_html = ''.join(self.sendHexBuf)
            self.sendView.setHtml(full_html)
        else:
            full_html = ''.join(self.sendAsciiBuf)
            self.sendView.setHtml(full_html)
        self.sendView.moveCursor(QTextCursor.MoveOperation.End)
    
    def closeEvent(self, event):
        try:
            # 保存当前波特率到配置
            current_baud_text = self.baudBox.currentText()
            try:
                current_baud = int(current_baud_text)
                self.config_manager.set_last_baud_rate(current_baud)
            except ValueError:
                pass
            
            self.worker.shutdown()
        except Exception:
            pass
        super().closeEvent(event)
        
if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
