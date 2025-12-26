"""
Intel HEX 文件解析器
支持解析标准的Intel HEX文件格式
"""
from typing import List, Tuple, Dict
import struct
import os
import sys

# 日志输出控制
ENABLE_LOGGING = True
try:
    # 尝试从 config 模块导入
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config.config import ENABLE_LOGGING
except (ImportError, ModuleNotFoundError):
    # 如果导入失败，使用默认值
    ENABLE_LOGGING = True


class HexRecord:
    """HEX记录类"""
    def __init__(self, address: int, data: bytes, record_type: int):
        self.address = address
        self.data = data
        self.record_type = record_type

    def __repr__(self):
        return f"HexRecord(addr=0x{self.address:08X}, len={len(self.data)}, type={self.record_type})"


class HexParser:
    """Intel HEX文件解析器"""

    # 记录类型
    DATA_RECORD = 0x00
    EOF_RECORD = 0x01
    EXTENDED_SEGMENT_ADDRESS = 0x02
    START_SEGMENT_ADDRESS = 0x03
    EXTENDED_LINEAR_ADDRESS = 0x04
    START_LINEAR_ADDRESS = 0x05

    def __init__(self):
        self.records: List[HexRecord] = []
        self.data_map: Dict[int, int] = {}  # address -> byte value
        self.min_address = None
        self.max_address = None

    def parse_file(self, filepath: str) -> bool:
        """解析HEX文件"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            self.records = []
            self.data_map = {}
            extended_address = 0

            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue

                if not line.startswith(':'):
                    raise ValueError(f"Line {line_num}: HEX记录必须以':'开头")

                # 解析记录
                record = self._parse_line(line[1:], extended_address)
                if record is None:
                    raise ValueError(f"Line {line_num}: 解析失败")

                self.records.append(record)

                # 处理不同类型的记录
                if record.record_type == self.DATA_RECORD:
                    # 数据记录
                    for i, byte_val in enumerate(record.data):
                        addr = record.address + i
                        self.data_map[addr] = byte_val

                        if self.min_address is None or addr < self.min_address:
                            self.min_address = addr
                        if self.max_address is None or addr > self.max_address:
                            self.max_address = addr

                elif record.record_type == self.EXTENDED_LINEAR_ADDRESS:
                    # 扩展线性地址
                    if len(record.data) == 2:
                        extended_address = struct.unpack('>H', record.data)[0] << 16

                elif record.record_type == self.EOF_RECORD:
                    # 文件结束
                    break

            return True

        except Exception as e:
            if ENABLE_LOGGING:
                print(f"解析HEX文件失败: {e}")
            return False

    def _parse_line(self, line: str, extended_address: int) -> HexRecord:
        """解析单行HEX记录"""
        try:
            # 移除空格和换行
            line = line.strip().replace(' ', '')

            # 解析各字段
            byte_count = int(line[0:2], 16)
            address = int(line[2:6], 16)
            record_type = int(line[6:8], 16)

            # 提取数据
            data_start = 8
            data_end = data_start + byte_count * 2
            data_hex = line[data_start:data_end]
            data = bytes.fromhex(data_hex)

            # 校验和
            checksum = int(line[data_end:data_end+2], 16)

            # 验证校验和
            calc_sum = byte_count + (address >> 8) + (address & 0xFF) + record_type
            calc_sum += sum(data)
            calc_sum = (~calc_sum + 1) & 0xFF

            if calc_sum != checksum:
                raise ValueError(f"校验和错误 (计算:{calc_sum:02X}, 实际:{checksum:02X})")

            # 计算完整地址
            full_address = extended_address + address

            return HexRecord(full_address, data, record_type)

        except Exception as e:
            if ENABLE_LOGGING:
                print(f"解析行失败: {e}")
            return None

    def get_data_blocks(self, block_size: int = 256) -> List[Tuple[int, bytes]]:
        """
        获取数据块列表
        返回: [(address, data_bytes), ...]
        """
        if not self.data_map:
            return []

        blocks = []
        addresses = sorted(self.data_map.keys())

        if not addresses:
            return []

        # 分块
        current_start = addresses[0]
        current_data = bytearray()

        for addr in addresses:
            # 如果地址不连续或超过块大小,创建新块
            if (addr != current_start + len(current_data)) or (len(current_data) >= block_size):
                if current_data:
                    blocks.append((current_start, bytes(current_data)))
                current_start = addr
                current_data = bytearray()

            current_data.append(self.data_map[addr])

        # 添加最后一个块
        if current_data:
            blocks.append((current_start, bytes(current_data)))

        return blocks

    def get_total_size(self) -> int:
        """获取固件总大小(字节)"""
        if self.min_address is None or self.max_address is None:
            return 0
        return self.max_address - self.min_address + 1

    def get_data_bytes(self) -> int:
        """获取实际数据字节数"""
        return len(self.data_map)


if __name__ == '__main__':
    # 测试代码
    parser = HexParser()
    if ENABLE_LOGGING:
        print("HEX解析器模块")
