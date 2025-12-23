from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton,
    QTableView, QStatusBar, QToolBar, QFileDialog, QDockWidget, QPlainTextEdit, QTextEdit, QLabel, QMessageBox
)
try:
    from gui.models.ParamTableModel import ParamTableModel
    from gui.services.SerialWorker import SerialWorker
except Exception:
    import sys, os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from gui.models.ParamTableModel import ParamTableModel
    from gui.services.SerialWorker import SerialWorker
import Usart_Para_FK as proto

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('电调参数上位机')
        self.resize(1000, 680)

        self.portBox = QComboBox()
        self.groupBox = QComboBox()
        self.groupBox.addItems(['A'])
        self.baudBox = QComboBox()
        self.baudBox.addItems(['9600','19200','38400','57600','115200','230400','460800','921600','2000000'])
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
        tb.addWidget(QLabel('组:'))
        tb.addWidget(self.groupBox)
        tb.addWidget(QLabel('波特率:'))
        tb.addWidget(self.baudBox)
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

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.addWidget(self.table)
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
        self._bindSignals()
        self._refreshPorts()
        self._updateButtons(False)
        try:
            cfg = proto._read_protocol_cfg()
            b = cfg.get('Baud','2000000')
            idx = self.baudBox.findText(str(b))
            self.baudBox.setCurrentIndex(idx if idx != -1 else self.baudBox.findText('2000000'))
        except Exception:
            self.baudBox.setCurrentIndex(self.baudBox.findText('2000000'))

    def _bindSignals(self):
        self.btnConnect.clicked.connect(self._onConnect)
        self.btnDisconnect.clicked.connect(self._onDisconnect)
        self.btnRead.clicked.connect(self._onRead)
        self.btnWrite.clicked.connect(self._onWrite)
        self.btnExit.clicked.connect(self._onExit)
        self.btnImport.clicked.connect(self._onImport)
        self.btnRefresh.clicked.connect(self._onRefresh)

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

    def _refreshPorts(self):
        try:
            import serial.tools.list_ports as lp
            self.portBox.clear()
            ports = [p.device for p in lp.comports()]
            self.portBox.addItems(ports)
        except Exception:
            self.portBox.clear()

    def _updateButtons(self, connected: bool):
        self.btnConnect.setEnabled(not connected)
        self.btnDisconnect.setEnabled(connected)
        self.btnRead.setEnabled(connected)
        self.btnWrite.setEnabled(connected)

    def _onConnect(self):
        port = self.portBox.currentText()
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
        try:
            self.worker.setBaudRate(int(text))
            self.status.showMessage('波特率已更新为 ' + text, 1500)
        except Exception:
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

    def _onConnected(self, ok: bool):
        self._updateButtons(ok)
        if ok:
            self._setStatusLight('green')
            self.status.showMessage('已连接', 3000)
        else:
            self._setStatusLight('red')
            self.model.reload(self.groupBox.currentText())
            self.status.showMessage('连接失败或已断开，映射已刷新', 3000)

    def _onFrameSent(self, hexstr: str):
        # Check if this is a REPLY frame (hex for REPLY: is 5245504C593A)
        # If it is an auto-reply, we don't expect a response, so don't turn yellow.
        if '5245504C593A' not in hexstr.upper():
            self._setStatusLight('yellow')
        self.logView.appendPlainText('SEND: ' + hexstr)

    def _onFrameRecv(self, hexstr: str):
        self.logView.appendPlainText('RECV: ' + hexstr)

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
