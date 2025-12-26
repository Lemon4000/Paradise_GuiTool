"""
固件烧录Worker
实现HEX文件烧录到下位机的完整状态机
"""
from PySide6.QtCore import QObject, Signal, QTimer
from enum import Enum
from typing import Optional
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
        self.max_consecutive_errors = 15  # 最大连续错误数
        self.verify_retries = 0  # VERIFY阶段单独计数
        self.max_verify_retries = 30  # VERIFY阶段允许更多重试
        self.debug_mode = False  # 调试模式：手动推进、提示期望响应
        self.crc_accumulate_count = 0  # CRC累加次数计数器
        self.accumulated_crc_list = []  # 存储每块参与累加的CRC值
        self.err_crc = 0  # 错误CRC计数
        self.err_format = 0  # 格式错误计数
        self.err_data = 0  # 数据错误计数
        self.err_total = 0  # 总错误计数
        self.flash_start_ts = None  # 烧录开始时间戳
        self.init_retry_delay = 50  # 初始化重试延迟(ms)，默认50ms
        self.init_start_time = None  # 初始化开始时间（用于计算总时间）
        self.init_timeout = 5000  # 初始化总超时时间(ms)
        self.program_retry_delay = 50  # 编程数据重试延迟(ms)，默认50ms
        self.program_start_time = None  # 当前数据块发送开始时间
        self.program_timeout = 2000  # 单个数据块总超时时间(ms)

        # 超时定时器
        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self._on_timeout)

    def _log_error(self, err_type: str, expected: str, actual: str, frame: Optional[bytes]):
        """统一记录错误并统计次数。"""
        self.err_total += 1
        if err_type == "CRC_MISMATCH":
            self.err_crc += 1
        elif err_type == "FORMAT_ERROR":
            self.err_format += 1
        elif err_type == "DATA_MISMATCH":
            self.err_data += 1

        frame_hex = frame.hex().upper() if frame else "(无帧)"
        self.sigLog.emit(
            f"[ERROR] {err_type} #{self.err_total} (CRC:{self.err_crc},FMT:{self.err_format},DATA:{self.err_data}) "
            f"期望:{expected} 实际:{actual} 帧:{frame_hex}"
        )
        self.sigErrorDetail.emit(err_type, expected, actual)

    def start_flash(self, ser, hex_file_path: str, debug_mode: bool = False):
        """开始烧录"""
        try:
            self.ser = ser
            self.state = FlashState.IDLE
            self.retry_count = 0
            self.current_block_index = 0
            self.total_data_crc = 0
            self.consecutive_errors = 0
            self.verify_retries = 0
            self.debug_mode = debug_mode
            self.crc_accumulate_count = 0  # 重置累加计数器
            self.accumulated_crc_list = []  # 重置CRC值列表
            self.err_crc = 0
            self.err_format = 0
            self.err_data = 0
            self.err_total = 0
            self.flash_start_ts = time.time()

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
            if self.flash_start_ts is not None:
                duration = time.time() - self.flash_start_ts
                self.sigLog.emit(f"烧录耗时 {duration:.2f} 秒")
                self.flash_start_ts = None
            self.sigProgress.emit(100, "烧录成功")
            self.sigCompleted.emit(True, "固件烧录成功")
        elif new_state == FlashState.FAILED:
            self.timeout_timer.stop()
            if self.flash_start_ts is not None:
                duration = time.time() - self.flash_start_ts
                self.sigLog.emit(f"烧录耗时 {duration:.2f} 秒")
                self.flash_start_ts = None
            self.sigCompleted.emit(False, "固件烧录失败")

    def _send_init_command(self, is_retry: bool = False):
        """发送初始化命令: !HEX;[CRC]
        
        Args:
            is_retry: 是否为重试发送
        """
        try:
            # 首次发送：记录开始时间
            if not is_retry:
                self.init_start_time = time.time()
                self.sigLog.emit("发送初始化命令...")
            else:
                # 重试：检查总时间是否超过5秒
                elapsed_ms = (time.time() - self.init_start_time) * 1000
                if elapsed_ms >= self.init_timeout:
                    self.sigLog.emit(f"初始化总超时 ({elapsed_ms:.0f}ms >= {self.init_timeout}ms)")
                    self._transition_to(FlashState.FAILED)
                    return
                self.sigLog.emit(f"重试发送初始化命令 (已用时:{elapsed_ms:.0f}ms)...")
            
            tx_start = (self.cfg.get('TxStart', '!') or '!')[0]
            payload = f"{tx_start}HEX;".encode('ascii')
            frame = self._build_frame(payload)

            self.ser.write(frame)
            self.sigFrameSent.emit(frame.hex())
            self.last_sent_crc = self._get_frame_crc(frame)

            self.state = FlashState.WAIT_INIT
            self.sigProgress.emit(5, "等待初始化响应...")
            
            # 首次发送：启动周期性重试定时器
            if not is_retry and not self.debug_mode:
                self.timeout_timer.start(self.init_retry_delay)  # 按用户设置的间隔触发重试

            # 调试模式提示期望响应
            if self.debug_mode:
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
                self.timeout_timer.stop()  # 停止周期性定时器
                self._log_error("CRC_MISMATCH", calc_crc.hex().upper(), recv_crc.hex().upper(), frame)
                self._retry_or_fail(5000, immediate=True)
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
                self.timeout_timer.stop()  # 停止周期性定时器
                self.sigLog.emit(f"初始化响应格式错误")
                self._log_error("FORMAT_ERROR", expected, received, frame)
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
                self._log_error("CRC_MISMATCH", calc_crc.hex().upper(), recv_crc.hex().upper(), frame)
                self._retry_or_fail(10000, immediate=True)
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
                self._log_error("FORMAT_ERROR", expected, received, frame)
                self._retry_or_fail(10000)

        except Exception as e:
            self.sigLog.emit(f"处理擦除响应异常: {str(e)}")
            self._retry_or_fail(10000)

    def _send_program_data(self, is_retry: bool = False):
        """发送编程数据: !HEX:START[addr].SIZE[size]，DATA[data];[CRC]
        
        Args:
            is_retry: 是否为重试发送
        """
        try:
            if self.current_block_index >= len(self.data_blocks):
                # 所有数据块发送完成
                self.sigLog.emit("所有数据块发送完成")
                self._transition_to(FlashState.VERIFY)
                return

            # 首次发送：记录开始时间
            if not is_retry:
                self.program_start_time = time.time()
            else:
                # 重试：检查总时间是否超过2秒
                elapsed_ms = (time.time() - self.program_start_time) * 1000
                if elapsed_ms >= self.program_timeout:
                    self.sigLog.emit(f"数据块{self.current_block_index + 1}总超时 ({elapsed_ms:.0f}ms >= {self.program_timeout}ms)")
                    self._retry_or_fail(2000)  # 使用常规重试机制
                    return

            # 获取当前数据块
            address, data = self.data_blocks[self.current_block_index]
            # 注意：不要在发送阶段累加数据块CRC，避免重试导致重复累加
            # 改为在收到该块成功回复后再累加（见 _handle_program_response）

            progress = int((self.current_block_index / len(self.data_blocks)) * 80) + 10
            if is_retry:
                elapsed_ms = (time.time() - self.program_start_time) * 1000
                self.sigLog.emit(f"重试发送数据块 {self.current_block_index + 1}/{len(self.data_blocks)} " +
                               f"(已用时:{elapsed_ms:.0f}ms, 地址:0x{address:08X})")
            else:
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
            self.sigProgress.emit(progress, f"编程数据块 {self.current_block_index + 1}/{len(self.data_blocks)}...")

            # 首次发送：启动周期性重试定时器
            if not is_retry and not self.debug_mode:
                self.timeout_timer.start(self.program_retry_delay)  # 按用户设置的间隔触发重试

            if self.last_sent_crc:
                exp_crc = self.last_sent_crc.hex().upper()
            else:
                exp_crc = "(未知CRC)"
            if self.debug_mode:
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
                self._log_error("CRC_MISMATCH", calc_crc.hex().upper(), recv_crc.hex().upper(), frame)
                self._retry_or_fail(2000, immediate=True)
                return

            # 解析响应: #HEX:REPLY[上一帧CRC];[CRC]
            rx_start = (self.cfg.get('RxStart', '#') or '#')[0]
            
            # 期望格式: #HEX:REPLY[hex_crc];
            # 其中[hex_crc]是16进制数据，不是ASCII字符串
            expected_prefix = f"{rx_start}HEX:REPLY"
            
            # 找到REPLY后的部分
            if not payload.startswith(expected_prefix.encode('ascii')):
                self.timeout_timer.stop()  # 停止周期性定时器
                payload_str = payload.decode('ascii', errors='ignore')
                self._log_error("FORMAT_ERROR", f"{expected_prefix}[hex];", payload_str, frame)
                self._retry_or_fail(2000)
                return

            # 提取[hex_crc]部分: REPLY之后到;之前的内容
            prefix_len = len(expected_prefix)
            # 找到;的位置
            semicolon_pos = payload.find(b';', prefix_len)
            if semicolon_pos == -1:
                self.timeout_timer.stop()  # 停止周期性定时器
                payload_str = payload.decode('ascii', errors='ignore')
                self._log_error("FORMAT_ERROR", f"{expected_prefix}[hex];", payload_str, frame)
                self._retry_or_fail(2000)
                return
            
            # 提取回复的CRC (16进制字节)
            reply_crc_bytes = payload[prefix_len:semicolon_pos]

            # 验证回复的CRC是否匹配上次发送的CRC
            if self.last_sent_crc:
                if reply_crc_bytes != self.last_sent_crc:
                    self.timeout_timer.stop()  # 停止周期性定时器
                    sent_crc_hex = self.last_sent_crc.hex().upper()
                    reply_crc_hex = reply_crc_bytes.hex().upper()
                    self._log_error("DATA_MISMATCH", sent_crc_hex, reply_crc_hex, frame)
                    self._retry_or_fail(2000)
                    return

            self.sigLog.emit(f"数据块 {self.current_block_index + 1} 编程成功")
            if self.last_sent_crc:
                self.sigVerifyOk.emit(self.last_sent_crc.hex().upper(), reply_crc_bytes.hex().upper())

            # 在收到成功回复后，累加该数据帧的帧CRC到总CRC（避免重试重复累加）
            # 帧CRC = last_sent_crc（已在发送时计算）
            try:
                if self.last_sent_crc:
                    frame_crc = int.from_bytes(self.last_sent_crc, byteorder='little')  # 小端转整数
                    self.total_data_crc = (self.total_data_crc + frame_crc) & 0xFFFF
                    self.crc_accumulate_count += 1
                    self.accumulated_crc_list.append(frame_crc)  # 保存帧CRC
                    self.sigLog.emit(f"[累加{self.crc_accumulate_count}次] 块{self.current_block_index + 1} 帧CRC=0x{frame_crc:04X}, 累计总CRC=0x{self.total_data_crc:04X}")
            except Exception:
                pass

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
            # 输出所有参与累加的帧CRC值
            self.sigLog.emit(f"=" * 60)
            self.sigLog.emit(f"参与累加的帧CRC列表 (共{len(self.accumulated_crc_list)}个):")
            self.sigLog.emit(f"说明: 每个值是对应数据帧的帧CRC（小端格式整数），ENDCRC = 所有帧CRC直接相加")
            crc_str_list = []
            for i, crc in enumerate(self.accumulated_crc_list):
                crc_str_list.append(f"0x{crc:04X}")
                if (i + 1) % 8 == 0:
                    self.sigLog.emit(f"  {', '.join(crc_str_list)}")
                    crc_str_list = []
            if crc_str_list:  # 输出剩余的
                self.sigLog.emit(f"  {', '.join(crc_str_list)}")
            self.sigLog.emit(f"=" * 60)
            self.sigLog.emit(f"发送校验命令 (总CRC:0x{self.total_data_crc:04X})...")
            tx_start = (self.cfg.get('TxStart', '!') or '!')[0]
            # ENDCRC后跟2字节的原始CRC数据（大端序），而不是ASCII字符串
            header = f"{tx_start}HEX:ENDCRC".encode('ascii')
            crc_bytes = self.total_data_crc.to_bytes(2, byteorder='big')
            payload = header + crc_bytes + b';'
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
                self._log_error("CRC_MISMATCH", calc_crc.hex().upper(), recv_crc.hex().upper(), frame)
                self._retry_or_fail(2000, immediate=True)
                return

            # 解析响应
            rx_start = (self.cfg.get('RxStart', '#') or '#')[0]

            # 检查是否是REPLY响应
            payload_str = payload.decode('ascii', errors='ignore')
            expected_prefix = f"{rx_start}HEX:REPLY"

            if not payload_str.startswith(expected_prefix):
                self._log_error("FORMAT_ERROR", f"{expected_prefix}[hex];", payload_str, frame)
                self._retry_or_fail(2000, immediate=True)
                return

            # 提取回复的CRC (REPLY后到;之前的内容)
            prefix_len = len(expected_prefix)
            semicolon_pos = payload_str.find(';')
            
            if semicolon_pos == -1:
                self._log_error("FORMAT_ERROR", f"{expected_prefix}[hex];", payload_str, frame)
                self._retry_or_fail(2000, immediate=True)
                return
            
            reply_crc_str = payload_str[prefix_len:semicolon_pos]  # 提取[hex]部分

            # 验证回复的总CRC
            expected_crc = f"{self.total_data_crc:04X}"
            reply_crc_clean = reply_crc_str.replace(' ', '').upper()

            if reply_crc_clean != expected_crc:
                self._log_error("DATA_MISMATCH", expected_crc, reply_crc_str, frame)
                self._retry_or_fail(2000, immediate=True)
                return

            self.sigLog.emit("校验成功")
            self.sigVerifyOk.emit(expected_crc, reply_crc_str)
            self.timeout_timer.stop()
            self.consecutive_errors = 0  # 重置连续错误计数
            self.verify_retries = 0  # 重置VERIFY重试计数
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
            
            # 调试模式跳过时，也要累加当前帧的帧CRC（模拟成功场景）
            try:
                if self.last_sent_crc:
                    frame_crc = int.from_bytes(self.last_sent_crc, byteorder='little')  # 小端转整数
                    self.total_data_crc = (self.total_data_crc + frame_crc) & 0xFFFF
                    self.crc_accumulate_count += 1
                    self.accumulated_crc_list.append(frame_crc)  # 保存帧CRC
                    self.sigLog.emit(f"[累加{self.crc_accumulate_count}次] 块{self.current_block_index + 1} 帧CRC=0x{frame_crc:04X}, 累计总CRC=0x{self.total_data_crc:04X}")
            except Exception:
                pass
            
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

    def _retry_or_fail(self, timeout_ms: int, immediate: bool = False):
        """重试或失败，immediate=True 时先立即重发一次。"""
        # 初始化阶段：使用时间控制而非次数控制
        if self.state == FlashState.WAIT_INIT:
            elapsed_ms = (time.time() - self.init_start_time) * 1000
            if elapsed_ms >= self.init_timeout:
                self.sigLog.emit(f"初始化总超时 ({elapsed_ms:.0f}ms >= {self.init_timeout}ms)")
                self._transition_to(FlashState.FAILED)
                return
            
            retry_delay = self.init_retry_delay
            if immediate:
                self.sigLog.emit(f"初始化重试，立即重发 (已用时:{elapsed_ms:.0f}ms)")
                self._send_init_command(is_retry=True)
                self.timeout_timer.start(retry_delay)  # 重启周期性定时器
            else:
                self.sigLog.emit(f"初始化重试，延迟{retry_delay}ms... (已用时:{elapsed_ms:.0f}ms)")
                def retry_and_restart():
                    self._send_init_command(is_retry=True)
                    self.timeout_timer.start(retry_delay)
                QTimer.singleShot(retry_delay, retry_and_restart)
            return
        
        # PROGRAM阶段：使用时间控制而非次数控制
        if self.state == FlashState.WAIT_PROGRAM:
            elapsed_ms = (time.time() - self.program_start_time) * 1000
            if elapsed_ms >= self.program_timeout:
                self.sigLog.emit(f"数据块{self.current_block_index + 1}总超时 ({elapsed_ms:.0f}ms >= {self.program_timeout}ms)")
                # 超时后使用常规重试次数机制
                self.retry_count += 1
                self.consecutive_errors += 1
                if self.retry_count >= self.max_retries or self.consecutive_errors >= self.max_consecutive_errors:
                    self.sigLog.emit(f"重试次数超限，停止烧录")
                    self._transition_to(FlashState.FAILED)
                    return
                # 常规重试：延迟后重新发送当前块
                self.sigLog.emit(f"延迟1000ms后重试数据块{self.current_block_index + 1}...")
                QTimer.singleShot(1000, lambda: self._send_program_data(is_retry=False))  # 重置时间
                return
            
            retry_delay = self.program_retry_delay
            if immediate:
                self.sigLog.emit(f"数据块{self.current_block_index + 1}重试，立即重发 (已用时:{elapsed_ms:.0f}ms)")
                self._send_program_data(is_retry=True)
                self.timeout_timer.start(retry_delay)  # 重启周期性定时器
            else:
                self.sigLog.emit(f"数据块{self.current_block_index + 1}重试，延迟{retry_delay}ms... (已用时:{elapsed_ms:.0f}ms)")
                def retry_and_restart():
                    self._send_program_data(is_retry=True)
                    self.timeout_timer.start(retry_delay)
                QTimer.singleShot(retry_delay, retry_and_restart)
            return
        
        # VERIFY阶段使用独立的重试计数
        if self.state == FlashState.WAIT_VERIFY:
            self.verify_retries += 1
            max_retries = self.max_verify_retries
            current_retries = self.verify_retries
            retry_delay = 500  # VERIFY阶段延迟500ms
        else:
            self.retry_count += 1
            self.consecutive_errors += 1
            max_retries = self.max_retries
            current_retries = self.retry_count
            retry_delay = 1000  # 其他阶段延迟1000ms
            
            # 检查连续错误是否过多（仅非VERIFY阶段）
            if self.consecutive_errors >= self.max_consecutive_errors:
                self.sigLog.emit(f"连续错误{self.consecutive_errors}次，停止烧录")
                self._transition_to(FlashState.FAILED)
                return
            
        if current_retries < max_retries:
            # 首次重试且请求立即重发，则直接调用一次
            if immediate and current_retries == 1:
                self.sigLog.emit(f"重试 ({current_retries}/{max_retries})，立即重发")
                self._do_retry()
                return
            self.sigLog.emit(f"重试 ({current_retries}/{max_retries})，延迟{retry_delay}ms...")
            QTimer.singleShot(retry_delay, self._do_retry)
        else:
            self.sigLog.emit(f"重试次数超限 ({current_retries}/{max_retries})")
            self._transition_to(FlashState.FAILED)
    
    def _do_retry(self):
        """执行重试（延迟调用）"""
        # 重新发送当前状态的命令
        if self.state == FlashState.WAIT_INIT:
            self._send_init_command(is_retry=True)
        elif self.state == FlashState.WAIT_ERASE:
            self._send_erase_command()
        elif self.state == FlashState.WAIT_PROGRAM:
            self._send_program_data(is_retry=True)
        elif self.state == FlashState.WAIT_VERIFY:
            self._send_verify_command()

    def _on_timeout(self):
        """超时处理"""
        # 初始化阶段：周期性重试触发
        if self.state == FlashState.WAIT_INIT:
            elapsed_ms = (time.time() - self.init_start_time) * 1000
            if elapsed_ms >= self.init_timeout:
                self.sigLog.emit(f"初始化总超时 ({elapsed_ms:.0f}ms >= {self.init_timeout}ms)")
                self._transition_to(FlashState.FAILED)
            else:
                # 重发并重启定时器
                self._send_init_command(is_retry=True)
                self.timeout_timer.start(self.init_retry_delay)
        # PROGRAM阶段：周期性重试触发
        elif self.state == FlashState.WAIT_PROGRAM:
            elapsed_ms = (time.time() - self.program_start_time) * 1000
            if elapsed_ms >= self.program_timeout:
                self.sigLog.emit(f"数据块{self.current_block_index + 1}总超时 ({elapsed_ms:.0f}ms >= {self.program_timeout}ms)")
                # 使用常规重试机制
                self._retry_or_fail(2000)
            else:
                # 重发并重启定时器
                self._send_program_data(is_retry=True)
                self.timeout_timer.start(self.program_retry_delay)
        else:
            self.sigLog.emit(f"等待响应超时 (状态: {self.state.name})")
            self._retry_or_fail(500)

    def abort(self):
        """中止烧录"""
        self.timeout_timer.stop()
        self.state = FlashState.FAILED
        self.sigLog.emit("烧录已中止")
        self.sigCompleted.emit(False, "烧录已被用户中止")
