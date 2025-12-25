import sys
from hex_parser import HexParser
from Usart_Para_FK import _crc16_modbus

def main(hex_path):
    parser = HexParser()
    if not parser.parse_file(hex_path):
        print("parse failed")
        return
    start_addr = parser.min_address
    block_size = 2048
    # build first block
    data = bytearray()
    for i in range(block_size):
        addr = start_addr + i
        data.append(parser.data_map.get(addr, 0xFF))
    header = f"!HEX:START{start_addr:08X},SIZE{len(data)},DATA".encode('ascii')
    payload = header + bytes(data) + b';'
    crc = _crc16_modbus(payload)
    # little-endian bytes
    bs = bytes([crc & 0xFF, (crc >> 8) & 0xFF])
    print(f"First frame CRC (value): 0x{crc:04X}")
    print(f"First frame CRC bytes (LE): {bs.hex().upper()}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python calc_first_frame_crc.py <hex_path>")
        sys.exit(1)
    main(sys.argv[1])
