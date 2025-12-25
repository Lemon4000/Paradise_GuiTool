from PySide6.QtCore import QObject, Signal
import Usart_Para_FK as proto
from concurrent.futures import ThreadPoolExecutor

class SerialWorker(QObject):
    sigConnected = Signal(bool)
    sigFrameSent = Signal(str)
    sigFrameRecv = Signal(str)
    sigReadDone = Signal(dict)
    sigWriteDone = Signal(bool)
    sigError = Signal(str)
    sigRawRecv = Signal(str)
    sigAsciiRecv = Signal(str)
    sigRawSend = Signal(str)
    sigAsciiSend = Signal(str)
    sigReadFailed = Signal()
    sigReplyOk = Signal(str, str)
    sigReplyMismatch = Signal(str)
    sigRecvBreak = Signal()

    def __init__(self):
        super().__init__()
        self.port = None
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.current_cfg = proto._read_protocol_cfg()
        self.ser = None
        self._reading = False
        self._last_tx_crc = None
        self._passthrough_mode = False  # 透传模式，用于固件烧录

    def shutdown(self):
        try:
            self.executor.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    def connectPort(self, port: str):
        try:
            self.ser = proto._open_port(self.current_cfg, port)
            self.port = port
            self._reading = True
            self.executor.submit(self._read_loop)
            self.sigConnected.emit(True)
        except Exception as e:
            self.sigConnected.emit(False)
            self.sigError.emit(str(e))

    def disconnectPort(self):
        self._reading = False
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.port = None
        self.sigConnected.emit(False)

    def readGroup(self, group: str):
        if not self.port:
            self.sigError.emit('未连接串口')
            return
        req = proto.build_read_request(group, self.current_cfg)
        self.sigFrameSent.emit(req.hex())
        self.sigRawSend.emit(req.hex())
        pre = bytes.fromhex(self.current_cfg.get('Preamble','FC')) if self.current_cfg.get('Preamble','FC') else b''
        algo = self.current_cfg.get('Checksum','CRC16_MODBUS').upper()
        cs_len = 2 if algo=='CRC16_MODBUS' else (1 if algo=='SUM8' else 0)
        ascii_payload = req[len(pre):len(req)-cs_len].decode('ascii') if len(req)>len(pre)+cs_len else ''
        self.sigAsciiSend.emit(ascii_payload)
        try:
            if self.ser:
                self.ser.write(req)
                self._last_tx_crc = req[-cs_len:] if cs_len else None
        except Exception as e:
            self.sigError.emit(str(e))

    def writeGroup(self, group: str, values: dict):
        if not self.port:
            self.sigError.emit('未连接串口')
            return
        frame = proto.build_frame(group, values, self.current_cfg)
        self.sigFrameSent.emit(frame.hex())
        self.sigRawSend.emit(frame.hex())
        pre = bytes.fromhex(self.current_cfg.get('Preamble','FC')) if self.current_cfg.get('Preamble','FC') else b''
        algo = self.current_cfg.get('Checksum','CRC16_MODBUS').upper()
        cs_len = 2 if algo=='CRC16_MODBUS' else (1 if algo=='SUM8' else 0)
        ascii_payload = frame[len(pre):len(frame)-cs_len].decode('ascii') if len(frame)>len(pre)+cs_len else ''
        self.sigAsciiSend.emit(ascii_payload)
        try:
            if self.ser:
                self.ser.write(frame)
                self.sigWriteDone.emit(True)
                self._last_tx_crc = frame[-cs_len:] if cs_len else None
        except Exception as e:
            self.sigError.emit(str(e))

    def setBaudRate(self, baud: int):
        self.current_cfg['Baud'] = str(baud)

    def setPassthroughMode(self, enabled: bool):
        """设置透传模式（固件烧录时使用）"""
        self._passthrough_mode = enabled

    def sendExit(self):
        if not self.port:
            self.sigError.emit('未连接串口')
            return
        try:
            cfg = self.current_cfg
            tx_start = (cfg.get('TxStart','!') or '!')[0]
            algo = cfg.get('Checksum','CRC16_MODBUS').upper()
            pre_bytes = bytes.fromhex(cfg.get('Preamble','')) if cfg.get('Preamble','') else b''
            payload = bytes([ord(tx_start)]) + b'EXIT;'
            cs = proto._checksum_bytes(payload, algo)
            frame = pre_bytes + payload + cs
            self.sigFrameSent.emit(frame.hex())
            self.sigRawSend.emit(frame.hex())
            try:
                self.sigAsciiSend.emit(f"{tx_start}EXIT;")
            except Exception:
                pass
            if self.ser:
                self.ser.write(frame)
                self._last_tx_crc = cs
        except Exception as e:
            self.sigError.emit(str(e))

    def _read_loop(self):
        try:
            cfg = self.current_cfg
            pre = bytes.fromhex(cfg.get('Preamble','FC')) if cfg.get('Preamble','FC') else b''
            algo = cfg.get('Checksum','CRC16_MODBUS').upper()
            
            tx_start_char = (cfg.get('TxStart','!') or '!')[0]
            tx_start_byte = tx_start_char.encode('latin1')
            
            rx_start_char = (cfg.get('RxStart','#') or '#')[0]
            rx_start_byte = rx_start_char.encode('latin1')
            
            cs_len = 2 if algo=='CRC16_MODBUS' else (1 if algo=='SUM8' else 0)
            pre_len = len(pre)
            recent = bytearray()
            
            while self._reading and self.ser:
                b = self.ser.read(1)
                if not b:
                    continue
                
                # Filter echoed TX frames (starting with !)
                if b == tx_start_byte:
                    # Consume until ; + CRC
                    # Do NOT emit signals for these bytes
                    while self._reading and self.ser:
                        c = self.ser.read(1)
                        if not c:
                            break
                        if c == b';':
                            if cs_len:
                                self.ser.read(cs_len)
                            break
                    continue

                # Handle RX frames (starting with #) or other data
                try:
                    self.sigRawRecv.emit(b.hex())
                    self.sigAsciiRecv.emit(b.decode('latin1'))
                except Exception:
                    pass
                
                recent += b
                if pre_len and len(recent) > pre_len:
                    recent = recent[-pre_len:]
                
                if b == rx_start_byte:
                    payload = bytearray(b)
                    while self._reading and self.ser:
                        c = self.ser.read(1)
                        if not c:
                            break
                        try:
                            self.sigRawRecv.emit(c.hex())
                            self.sigAsciiRecv.emit(c.decode('latin1'))
                        except Exception:
                            pass
                        payload += c
                        if c == b';':
                            cs = b''
                            if cs_len:
                                cs = self.ser.read(cs_len)
                                try:
                                    self.sigRawRecv.emit(cs.hex())
                                    self.sigAsciiRecv.emit(cs.decode('latin1'))
                                except Exception:
                                    pass

                            # Frame complete, emit Break
                            self.sigRecvBreak.emit()

                            frame = (pre if pre_len and recent == pre else b'') + bytes(payload) + cs
                            try:
                                self.sigFrameRecv.emit(frame.hex())
                            except Exception:
                                pass

                            # 在透传模式下，跳过自动处理和回复
                            if self._passthrough_mode:
                                break

                            # self.sigAsciiRecv already emitted stream
                            pl = bytes(payload)
                            is_reply = pl.startswith(b'#REPLY:') and pl.endswith(b';')
                            if is_reply:
                                data_region = pl[len(b'#REPLY:'):-1]
                                dr = data_region
                                # support ascii hex like "6B A0"
                                try:
                                    text = dr.decode('ascii')
                                    s = text.replace(' ', '').upper()
                                    if len(s) % 2 == 0 and all(ch in '0123456789ABCDEF' for ch in s):
                                        dr = bytes(int(s[i:i+2], 16) for i in range(0, len(s), 2))
                                except Exception:
                                    pass
                                calc_reply_cs = proto._checksum_bytes(pl, algo)
                                reply_crc_hex = ' '.join(f'{b:02X}' for b in (cs or b''))
                                if cs_len and cs != calc_reply_cs:
                                    self.sigReplyMismatch.emit(f'回复帧CRC校验失败 (Exp:{calc_reply_cs.hex().upper()}, Got:{cs.hex().upper()})')
                                else:
                                    sent_crc_hex = ' '.join(f'{b:02X}' for b in (dr or b''))
                                    if self._last_tx_crc and dr != self._last_tx_crc:
                                        msg = f'回复携带的上位机CRC不匹配 (Exp:{self._last_tx_crc.hex().upper()}, Got:{dr.hex().upper()})'
                                        self.sigReplyMismatch.emit(msg)
                                    else:
                                        self.sigReplyOk.emit(sent_crc_hex, reply_crc_hex)
                            parsed = None
                            try:
                                parsed = proto.parse_frame(frame, cfg)
                            except Exception:
                                parsed = None
                            if parsed:
                                try:
                                    self.sigReadDone.emit(parsed)
                                except Exception:
                                    pass
                                # auto reply with received CRC and this frame CRC
                                try:
                                    tx_start = (cfg.get('TxStart','!') or '!')[0]
                                    algo = cfg.get('Checksum','CRC16_MODBUS').upper()
                                    pre_bytes = bytes.fromhex(cfg.get('Preamble','')) if cfg.get('Preamble','') else b''
                                    recv_crc_hex = ' '.join([f'{b:02X}' for b in cs]) if cs_len else ''
                                    payload_bytes = bytes([ord(tx_start)]) + b'REPLY:' + (cs if cs_len else b'') + b';'
                                    reply_cs = proto._checksum_bytes(payload_bytes, algo)
                                    reply_frame = pre_bytes + payload_bytes + reply_cs
                                    self.sigFrameSent.emit(reply_frame.hex())
                                    self.sigRawSend.emit(reply_frame.hex())
                                    self.sigAsciiSend.emit(f"!REPLY:{recv_crc_hex};")
                                    if self.ser:
                                        self.ser.write(reply_frame)
                                except Exception:
                                    pass
                            else:
                                if not is_reply:
                                    try:
                                        self.sigReadFailed.emit()
                                        self.sigError.emit('接收校验失败')
                                    except Exception:
                                        pass
                            break
        except Exception as e:
            try:
                self.sigError.emit(str(e))
            except Exception:
                pass
