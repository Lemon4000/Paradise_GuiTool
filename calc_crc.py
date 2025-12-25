import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from hex_parser import HexParser
import Usart_Para_FK as proto

def calculate_endcrc(hex_file_path, block_size=256):
    print(f"Parsing HEX file: {hex_file_path}")
    
    parser = HexParser()
    if not parser.parse_file(hex_file_path):
        print("Failed to parse HEX file")
        return None
    
    blocks = parser.get_data_blocks(block_size=block_size)
    total_bytes = parser.get_data_bytes()
    
    print(f"Total data bytes: {total_bytes}")
    print(f"Total blocks: {len(blocks)}")
    print(f"Address range: 0x{parser.min_address:08X} - 0x{parser.max_address:08X}")
    print()
    
    total_crc = 0
    
    for i, (address, data) in enumerate(blocks):
        block_crc = proto._crc16_modbus(data)
        total_crc = (total_crc + block_crc) & 0xFFFF
        
        print(f"Block {i+1}/{len(blocks)}: Addr=0x{address:08X}, Size={len(data)} bytes, CRC=0x{block_crc:04X}, Total=0x{total_crc:04X}")
    
    print()
    print(f"=" * 60)
    print(f"ENDCRC: 0x{total_crc:04X} ({total_crc})")
    print(f"=" * 60)
    
    return total_crc

if __name__ == '__main__':
    hex_file = r"c:\Users\Lemon\Documents\xwechat_files\wxid_b74qff291pde22_b2ce\msg\file\2025-12\NationFlyMotor.hex"
    
    if os.path.exists(hex_file):
        print("Using block_size=2048 (same as FlashWorker)")
        print("=" * 60)
        calculate_endcrc(hex_file, block_size=2048)
    else:
        print(f"File not found: {hex_file}")
