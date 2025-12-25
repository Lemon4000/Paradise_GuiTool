"""
固件烧录Worker
实现HEX文件烧录到下位机的完整状态机
"""
from PySide6.QtCore import QObject, Signal, QTimer
from enum import Enum
import time
import Usart_Para_FK as proto
from hex_parser import HexParser


class FlashState(Enum):
    """烧录状态"""
    IDLE = 0
    INIT = 1           # 发送初始化命令 !HEX;[CRC]
    WAIT_INIT = 2      # 等待 #HEX;[CRC]
    ERASE = 3          # 发送擦除命令 !HEX:ESIZE[size];[CRC]
    WAIT_ERASE = 4     # 等待 #HEX:ERASE;[CRC]
    PROGRAM = 5        # 编程数据块
    WAIT_PROGRAM = 6   # 等待数据块回应 #HEX;REPLY:[CRC];[CRC]
    VERIFY = 7         # 发送校验命令 !HEX:ENDCRC[crc];[CRC]
    WAIT_VERIFY = 8    # 等待校验回应 #HEX;REPLY[crc];[CRC]
    SUCCESS = 9        # 烧录成功
    FAILED = 10        # 烧录失败


class FlashWorker(QObject):
    """固件烧录Worker"""

    # 信号定义
    sigProgress = Signal(int, str)  # 进度百分比, 状态消息
    sigCompleted = Signal(bool, str)  # 成功/失败, 消息
    sigLog = Signal(str)  # 日志消息
    sigFrameSent = Signal(str)  # 发送的帧(HEX)
    sigFrameRecv = Signal(str)  # 接收的帧(HEX)
    sigErrorDetail = Signal(str, str, str)  # 错误类型, 期望值, 实际值
    sigVerifyOk = Signal(str, str)  # 期望值, 实际值

    def __init__(self):
        super().__init__()
        self.state = FlashState.IDLE
        self.ser = None
        self.hex_parser = None
        self.data_blocks = []
        self.current_block_index = 0
        self.retry_count = 0
        self.max_retries = 20  # 最大重试20次，避免卡顿
        self.last_sent_crc = None
        self.total_data_crc = 0  # 累计数据CRC
        self.cfg = None
        self.consecutive_errors = 0  # 连续错误计数
        self.max_consecutive_errors = 5  # 最大连续错误数
        self.debug_mode = False  # 调试模式：手动推进、提示期望响应

        # 超时定时器
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

    def start_flash(self, ser, hex_file_path: str, debug_mode: bool = False):
        """开始烧录"""
        try:
            self.ser = ser
            self.state = FlashState.IDLE
            self.retry_count = 0
            self.current_block_index = 0
            self.total_data_crc = 0
            self.consecutive_errors = 0
            self.debug_mode = debug_mode

            # 读取配置
            self.cfg = proto._read_protocol_cfg()

            # 解析HEX文件
            self.sigLog.emit(f"正在解析HEX文件: {hex_file_path}")
            self.hex_parser = HexParser()
            if not self.hex_parser.parse_file(hex_file_path):
                self.sigCompleted.emit(False, "HEX文件解析失败")
                return

            # 获取数据块 (每块2048字节)
            self.data_blocks = self.hex_parser.get_data_blocks(block_size=2048)
            if not self.data_blocks:
                self.sigCompleted.emit(False, "HEX文件无有效数据")
                return

            total_bytes = sum(len(block[1]) for block in self.data_blocks)
            self.sigLog.emit(f"HEX文件解析完成: {len(self.data_blocks)}个数据块, 共{total_bytes}字节")
            self.sigProgress.emit(0, "准备烧录...")

            # 开始状态机
            self._transition_to(FlashState.INIT)

        except Exception as e:
            self.sigCompleted.emit(False, f"启动烧录失败: {str(e)}")

    def handle_received_frame(self, frame: bytes):
        """处理接收到的帧"""
        try:
            # 发出接收信号
            self.sigFrameRecv.emit(frame.hex())

            # 调试模式下只记录，不自动推进，等待手动“下一步”
            if self.debug_mode:
                self.sigLog.emit("调试模式：已收到数据，等待手动下一步")
                return

            # 根据当前状态处理
            if self.state == FlashState.WAIT_INIT:
                self._handle_init_response(frame)
            elif self.state == FlashState.WAIT_ERASE:
                self._handle_erase_response(frame)
            elif self.state == FlashState.WAIT_PROGRAM:
                self._handle_program_response(frame)
            elif self.state == FlashState.WAIT_VERIFY:
                self._handle_verify_response(frame)

        except Exception as e:
            self.sigLog.emit(f"处理接收帧异常: {str(e)}")

    def _transition_to(self, new_state: FlashState):
        """状态转换"""
        self.state = new_state
        self.retry_count = 0

        if new_state == FlashState.INIT:
            self._send_init_command()
        elif new_state == FlashState.ERASE:
            self._send_erase_command()
        elif new_state == FlashState.PROGRAM:
            self._send_program_data()
        elif new_state == FlashState.VERIFY:
            self._send_verify_command()
        elif new_state == FlashState.SUCCESS:
            self.timeout_timer.stop()
            self.sigProgress.emit(100, "烧录成功")
            self.sigCompleted.emit(True, "固件烧录成功")
        elif new_state == FlashState.FAILED:
            self.timeout_timer.stop()
            self.sigCompleted.emit(False, "固件烧录失败")

    def _send_init_command(self):
        """发送初始化命令: !HEX;[CRC]"""
        try:
            self.sigLog.emit("发送初始化命令...")
            tx_start = (self.cfg.get('TxStart', '!') or '!')[0]
            payload = f"{tx_start}HEX;".encode('ascii')
            frame = self._build_frame(payload)

            self.ser.write(frame)
            self.sigFrameSent.emit(frame.hex())
            self.last_sent_crc = self._get_frame_crc(frame)

            self.state = FlashState.WAIT_INIT
            if not self.debug_mode:
                self.timeout_timer.start(5000)  # 5秒超时
            self.sigProgress.emit(5, "等待初始化响应...")

            # 调试模式提示期望响应
            self._emit_expected(f"{(self.cfg.get('RxStart', '#') or '#')[0]}HEX;")

        except Exception as e:
            self.sigLog.emit(f"发送初始化命令失败: {str(e)}")
            self._transition_to(FlashState.FAILED)

    def _handle_init_response(self, frame: bytes):
        """处理初始化响应: #HEX;[CRC]"""
        try:
            # 提取实际接收的CRC
            recv_crc = self._get_frame_crc(frame)
            payload = self._extract_payload(frame)

            # 计算期望的CRC
            calc_crc = proto._checksum_bytes(payload, self.cfg.get('Checksum', 'CRC16_MODBUS'))

            # 验证CRC
            if recv_crc != calc_crc:
                self.sigLog.emit("初始化响应CRC校验失败")
                self.sigErrorDetail.emit("CRC_MISMATCH",
                                        calc_crc.hex().upper(),
                                        recv_crc.hex().upper())
                self._retry_or_fail(5000)
                return

            # 解析响应
            rx_start = (self.cfg.get('RxStart', '#') or '#')[0]
            expected = f"{rx_start}HEX;"
            received = payload.decode('ascii', errors='ignore')

            if received == expected:
                self.sigLog.emit("初始化成功")
                self.sigVerifyOk.emit(expected, received)
                self.timeout_timer.stop()
                self.consecutive_errors = 0  # 重置连续错误计数
                self._transition_to(FlashState.ERASE)
            else:
                self.sigLog.emit(f"初始化响应格式错误")
                self.sigErrorDetail.emit("FORMAT_ERROR", expected, received)
                self._retry_or_fail(5000)

        except Exception as e:
            self.sigLog.emit(f"处理初始化响应异常: {str(e)}")
            self._retry_or_fail(5000)

    def _send_erase_command(self):
        """发送擦除命令: !HEX:ESIZE[size/2048];[CRC]"""
        try:
            # 计算固件大小 (字节数 / 2048)
            total_bytes = sum(len(block[1]) for block in self.data_blocks)
            erase_blocks = (total_bytes + 2047) // 2048  # 向上取整

            self.sigLog.emit(f"发送擦除命令 (擦除{erase_blocks}个块)...")
            tx_start = (self.cfg.get('TxStart', '!') or '!')[0]
            payload = f"{tx_start}HEX:ESIZE{erase_blocks};".encode('ascii')
            frame = self._build_frame(payload)

            self.ser.write(frame)
            self.sigFrameSent.emit(frame.hex())
            self.last_sent_crc = self._get_frame_crc(frame)

            self.state = FlashState.WAIT_ERASE
            if not self.debug_mode:
                self.timeout_timer.start(10000)  # 10秒超时
            self.sigProgress.emit(10, "等待擦除完成...")

            self._emit_expected(f"{(self.cfg.get('RxStart', '#') or '#')[0]}HEX:ERASE;")

        except Exception as e:
            self.sigLog.emit(f"发送擦除命令失败: {str(e)}")
            self._transition_to(FlashState.FAILED)

    def _handle_erase_response(self, frame: bytes):
        """处理擦除响应: #HEX:ERASE;[CRC]"""
        try:
            # 提取实际接收的CRC
            recv_crc = self._get_frame_crc(frame)
            payload = self._extract_payload(frame)

            # 计算期望的CRC
            calc_crc = proto._checksum_bytes(payload, self.cfg.get('Checksum', 'CRC16_MODBUS'))

            # 验证CRC
            if recv_crc != calc_crc:
                self.sigLog.emit("擦除响应CRC校验失败")
                self.sigErrorDetail.emit("CRC_MISMATCH",
                                        calc_crc.hex().upper(),
                                        recv_crc.hex().upper())
                self._retry_or_fail(10000)
                return

            # 解析响应
            rx_start = (self.cfg.get('RxStart', '#') or '#')[0]
            expected = f"{rx_start}HEX:ERASE;"
            received = payload.decode('ascii', errors='ignore')

            if received == expected:
                self.sigLog.emit("擦除成功")
                self.sigVerifyOk.emit(expected, received)
                self.timeout_timer.stop()
                self.consecutive_errors = 0  # 重置连续错误计数
                self.total_data_crc = 0
                self._transition_to(FlashState.PROGRAM)
            else:
                self.sigLog.emit(f"擦除响应格式错误")
                self.sigErrorDetail.emit("FORMAT_ERROR", expected, received)
                self._retry_or_fail(10000)

        except Exception as e:
            self.sigLog.emit(f"处理擦除响应异常: {str(e)}")
            self._retry_or_fail(10000)

    def _send_program_data(self):
        """发送编程数据: !HEX:START[addr].SIZE[size]，DATA[data];[CRC]"""
        try:
            if self.current_block_index >= len(self.data_blocks):
                # 所有数据块发送完成
                self.sigLog.emit("所有数据块发送完成")
                self._transition_to(FlashState.VERIFY)
                return

            # 获取当前数据块
            address, data = self.data_blocks[self.current_block_index]
            # 计算数据块的CRC并累加到总CRC
            data_crc = proto._crc16_modbus(data)
            self.total_data_crc = (self.total_data_crc + data_crc) & 0xFFFF

            progress = int((self.current_block_index / len(self.data_blocks)) * 80) + 10
            self.sigLog.emit(f"发送数据块 {self.current_block_index + 1}/{len(self.data_blocks)} " +
                           f"(地址:0x{address:08X}, 大小:{len(data)}字节)")

            tx_start = (self.cfg.get('TxStart', '!') or '!')[0]
            # DATA后直接跟原始二进制数据，而不是ASCII字符串
            header = f"{tx_start}HEX:START{address:08X},SIZE{len(data)},DATA".encode('ascii')
            payload = header + data + b';'
            frame = self._build_frame(payload)

            self.ser.write(frame)
            self.sigFrameSent.emit(frame.hex())
            self.last_sent_crc = self._get_frame_crc(frame)

            self.state = FlashState.WAIT_PROGRAM
            if not self.debug_mode:
                self.timeout_timer.start(2000)  # 2秒超时
            self.sigProgress.emit(progress, f"编程数据块 {self.current_block_index + 1}/{len(self.data_blocks)}...")

            if self.last_sent_crc:
                exp_crc = self.last_sent_crc.hex().upper()
            else:
                exp_crc = "(未知CRC)"
            self._emit_expected(f"{(self.cfg.get('RxStart', '#') or '#')[0]}HEX:REPLY[{exp_crc}]")

        except Exception as e:
            self.sigLog.emit(f"发送编程数据失败: {str(e)}")
            self._transition_to(FlashState.FAILED)

    def _handle_program_response(self, frame: bytes):
        """处理编程响应: #HEX:REPLY[上一帧CRC];[CRC]"""
        try:
            # 提取实际接收的CRC
            recv_crc = self._get_frame_crc(frame)
            payload = self._extract_payload(frame)

            # 计算期望的CRC
            calc_crc = proto._checksum_bytes(payload, self.cfg.get('Checksum', 'CRC16_MODBUS'))

            # 验证CRC
            if recv_crc != calc_crc:
                self.sigLog.emit("编程响应CRC校验失败")
                self.sigErrorDetail.emit("CRC_MISMATCH",
                                        calc_crc.hex().upper(),
                                        recv_crc.hex().upper())
                self._retry_or_fail(2000)
                return

            # 解析响应: #HEX:REPLY[上一帧CRC];[CRC]
            rx_start = (self.cfg.get('RxStart', '#') or '#')[0]
            
            # 期望格式: #HEX:REPLY[hex_crc];
            # 其中[hex_crc]是16进制数据，不是ASCII字符串
            expected_prefix = f"{rx_start}HEX:REPLY"
            
            # 找到REPLY后的部分
            if not payload.startswith(expected_prefix.encode('ascii')):
                payload_str = payload.decode('ascii', errors='ignore')
                self.sigLog.emit(f"编程响应格式错误")
                self.sigErrorDetail.emit("FORMAT_ERROR", f"{expected_prefix}[hex];", payload_str)
                self._retry_or_fail(2000)
                return

            # 提取[hex_crc]部分: REPLY之后到;之前的内容
            prefix_len = len(expected_prefix)
            # 找到;的位置
            semicolon_pos = payload.find(b';', prefix_len)
            if semicolon_pos == -1:
                payload_str = payload.decode('ascii', errors='ignore')
                self.sigLog.emit(f"编程响应格式错误: 缺少分号")
                self.sigErrorDetail.emit("FORMAT_ERROR", f"{expected_prefix}[hex];", payload_str)
                self._retry_or_fail(2000)
                return
            
            # 提取回复的CRC (16进制字节)
            reply_crc_bytes = payload[prefix_len:semicolon_pos]

            # 验证回复的CRC是否匹配上次发送的CRC
            if self.last_sent_crc:
                if reply_crc_bytes != self.last_sent_crc:
                    sent_crc_hex = self.last_sent_crc.hex().upper()
                    reply_crc_hex = reply_crc_bytes.hex().upper()
                    self.sigLog.emit(f"回复CRC不匹配")
                    self.sigErrorDetail.emit("DATA_MISMATCH", sent_crc_hex, reply_crc_hex)
                    self._retry_or_fail(2000)
                    return

            self.sigLog.emit(f"数据块 {self.current_block_index + 1} 编程成功")
            if self.last_sent_crc:
                self.sigVerifyOk.emit(self.last_sent_crc.hex().upper(), reply_crc_bytes.hex().upper())

            self.timeout_timer.stop()
            self.consecutive_errors = 0  # 重置连续错误计数

            # 继续下一个数据块
            self.current_block_index += 1
            self._transition_to(FlashState.PROGRAM)

        except Exception as e:
            self.sigLog.emit(f"处理编程响应异常: {str(e)}")
            self._retry_or_fail(2000)

    def _send_verify_command(self):
        """发送校验命令: !HEX:ENDCRC[total_crc];[CRC]"""
        try:
            self.sigLog.emit(f"发送校验命令 (总CRC:0x{self.total_data_crc:04X})...")
            tx_start = (self.cfg.get('TxStart', '!') or '!')[0]
            payload = f"{tx_start}HEX:ENDCRC{self.total_data_crc:04X};".encode('ascii')
            frame = self._build_frame(payload)

            self.ser.write(frame)
            self.sigFrameSent.emit(frame.hex())
            self.last_sent_crc = self._get_frame_crc(frame)

            self.state = FlashState.WAIT_VERIFY
            if not self.debug_mode:
                self.timeout_timer.start(2000)  # 2秒超时
            self.sigProgress.emit(95, "等待校验结果...")

            self._emit_expected(f"{(self.cfg.get('RxStart', '#') or '#')[0]}HEX:REPLY[{self.total_data_crc:04X}]")

        except Exception as e:
            self.sigLog.emit(f"发送校验命令失败: {str(e)}")
            self._transition_to(FlashState.FAILED)

    def _handle_verify_response(self, frame: bytes):
        """处理校验响应: #HEX:REPLY[总CRC];[CRC]"""
        try:
            # 提取实际接收的CRC
            recv_crc = self._get_frame_crc(frame)
            payload = self._extract_payload(frame)

            # 计算期望的CRC
            calc_crc = proto._checksum_bytes(payload, self.cfg.get('Checksum', 'CRC16_MODBUS'))

            # 验证CRC
            if recv_crc != calc_crc:
                self.sigLog.emit("校验响应CRC校验失败")
                self.sigErrorDetail.emit("CRC_MISMATCH",
                                        calc_crc.hex().upper(),
                                        recv_crc.hex().upper())
                self._transition_to(FlashState.FAILED)
                return

            # 解析响应
            rx_start = (self.cfg.get('RxStart', '#') or '#')[0]

            # 检查是否是REPLY响应
            payload_str = payload.decode('ascii', errors='ignore')
            expected_prefix = f"{rx_start}HEX:REPLY"

            if not payload_str.startswith(expected_prefix):
                self.sigLog.emit(f"校验响应格式错误")
                self.sigErrorDetail.emit("FORMAT_ERROR", f"{expected_prefix}[hex];", payload_str)
                self._transition_to(FlashState.FAILED)
                return

            # 提取回复的CRC (REPLY后到;之前的内容)
            prefix_len = len(expected_prefix)
            semicolon_pos = payload_str.find(';')
            
            if semicolon_pos == -1:
                self.sigLog.emit(f"校验响应格式错误: 缺少分号")
                self.sigErrorDetail.emit("FORMAT_ERROR", f"{expected_prefix}[hex];", payload_str)
                self._transition_to(FlashState.FAILED)
                return
            
            reply_crc_str = payload_str[prefix_len:semicolon_pos]  # 提取[hex]部分

            # 验证回复的总CRC
            expected_crc = f"{self.total_data_crc:04X}"
            reply_crc_clean = reply_crc_str.replace(' ', '').upper()

            if reply_crc_clean != expected_crc:
                self.sigLog.emit(f"校验CRC不匹配")
                self.sigErrorDetail.emit("DATA_MISMATCH", expected_crc, reply_crc_str)
                self._transition_to(FlashState.FAILED)
                return

            self.sigLog.emit("校验成功")
            self.sigVerifyOk.emit(expected_crc, reply_crc_str)
            self.timeout_timer.stop()
            self.consecutive_errors = 0  # 重置连续错误计数
            self._transition_to(FlashState.SUCCESS)

        except Exception as e:
            self.sigLog.emit(f"处理校验响应异常: {str(e)}")
            self._transition_to(FlashState.FAILED)

    def _build_frame(self, payload: bytes) -> bytes:
        """构建完整帧"""
        preamble = self.cfg.get('Preamble', 'FC')
        pre_bytes = bytes.fromhex(preamble) if preamble else b''
        algo = self.cfg.get('Checksum', 'CRC16_MODBUS')
        cs = proto._checksum_bytes(payload, algo)
        return pre_bytes + payload + cs

    def _emit_expected(self, expected_text: str):
        """调试模式下提示期望响应内容"""
        if self.debug_mode:
            self.sigLog.emit(f"调试模式提示：期望收到 {expected_text}")

    def step_next(self):
        """调试模式下手动进入下一步"""
        if not self.debug_mode:
            self.sigLog.emit("当前非调试模式，无需手动下一步")
            return

        # 根据当前等待状态手动跳过
        if self.state == FlashState.WAIT_INIT:
            self.sigLog.emit("调试模式：跳过初始化响应，进入擦除")
            self.timeout_timer.stop()
            self.consecutive_errors = 0
            self._transition_to(FlashState.ERASE)
        elif self.state == FlashState.WAIT_ERASE:
            self.sigLog.emit("调试模式：跳过擦除响应，进入编程")
            self.timeout_timer.stop()
            self.consecutive_errors = 0
            self._transition_to(FlashState.PROGRAM)
        elif self.state == FlashState.WAIT_PROGRAM:
            self.sigLog.emit(f"调试模式：数据块 {self.current_block_index + 1} 直接视为成功，进入下一块")
            self.timeout_timer.stop()
            self.consecutive_errors = 0
            self.current_block_index += 1
            self._transition_to(FlashState.PROGRAM)
        elif self.state == FlashState.WAIT_VERIFY:
            self.sigLog.emit("调试模式：跳过校验响应，视为成功")
            self.timeout_timer.stop()
            self.consecutive_errors = 0
            self._transition_to(FlashState.SUCCESS)
        else:
            self.sigLog.emit(f"当前状态 {self.state.name} 无需手动下一步或已完成")

    def _get_frame_crc(self, frame: bytes) -> bytes:
        """获取帧的CRC部分"""
        algo = self.cfg.get('Checksum', 'CRC16_MODBUS').upper()
        cs_len = 2 if algo == 'CRC16_MODBUS' else (1 if algo == 'SUM8' else 0)
        return frame[-cs_len:] if cs_len else b''

    def _verify_frame_crc(self, frame: bytes) -> bool:
        """验证帧CRC"""
        preamble = self.cfg.get('Preamble', 'FC')
        pre_len = len(bytes.fromhex(preamble)) if preamble else 0
        algo = self.cfg.get('Checksum', 'CRC16_MODBUS').upper()
        cs_len = 2 if algo == 'CRC16_MODBUS' else (1 if algo == 'SUM8' else 0)

        if len(frame) < pre_len + 1 + cs_len:
            return False

        payload = frame[pre_len:len(frame)-cs_len] if cs_len else frame[pre_len:]
        cs_recv = frame[len(frame)-cs_len:] if cs_len else b''
        cs_calc = proto._checksum_bytes(payload, algo)

        return cs_recv == cs_calc

    def _extract_payload(self, frame: bytes) -> bytes:
        """提取帧的payload部分"""
        preamble = self.cfg.get('Preamble', 'FC')
        pre_len = len(bytes.fromhex(preamble)) if preamble else 0
        algo = self.cfg.get('Checksum', 'CRC16_MODBUS').upper()
        cs_len = 2 if algo == 'CRC16_MODBUS' else (1 if algo == 'SUM8' else 0)

        return frame[pre_len:len(frame)-cs_len] if cs_len else frame[pre_len:]

    def _retry_or_fail(self, timeout_ms: int):
        """重试或失败"""
        self.retry_count += 1
        self.consecutive_errors += 1
        
        # 检查连续错误是否过多
        if self.consecutive_errors >= self.max_consecutive_errors:
            self.sigLog.emit(f"连续错误{self.consecutive_errors}次，停止烧录")
            self._transition_to(FlashState.FAILED)
            return
            
        if self.retry_count < self.max_retries:
            self.sigLog.emit(f"重试 ({self.retry_count}/{self.max_retries})...")
            # 增加重试延迟，避免频繁发送
            QTimer.singleShot(200, self._do_retry)  # 延迟200ms后重试
        else:
            self.sigLog.emit("重试次数超限")
            self._transition_to(FlashState.FAILED)
    
    def _do_retry(self):
        """执行重试（延迟调用）"""
        # 重新发送当前状态的命令
        if self.state == FlashState.WAIT_INIT:
            self._send_init_command()
        elif self.state == FlashState.WAIT_ERASE:
            self._send_erase_command()
        elif self.state == FlashState.WAIT_PROGRAM:
            self._send_program_data()

    def _on_timeout(self):
        """超时处理"""
        self.sigLog.emit(f"等待响应超时 (状态: {self.state.name})")
        self._retry_or_fail(500)

    def abort(self):
        """中止烧录"""
        self.timeout_timer.stop()
        self.state = FlashState.FAILED
        self.sigLog.emit("烧录已中止")
        self.sigCompleted.emit(False, "烧录已被用户中止")
