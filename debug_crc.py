#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug tool: Compare ENDCRC calculation between host and device
"""

import sys
from hex_parser import HexParser
from Usart_Para_FK import _crc16_modbus

def debug_crc_calculation(hex_file_path, block_size=2048):
    """
    Show detailed CRC calculation for each block
    """
    print(f"=" * 60)
    print(f"Debugging HEX file: {hex_file_path}")
    print(f"Block size: {block_size} bytes")
    print(f"=" * 60)
    
    # ½âÎöHEXÎÄ¼þ
    parser = HexParser()
    try:
        if not parser.parse_file(hex_file_path):
            print("Failed to parse HEX file")
            return
    except Exception as e:
        print(f"Failed to parse HEX file: {e}")
        return
    
    if not parser.data_map:
        print("HEX file data is empty")
        return
    
    # Get address range
    start_addr = parser.min_address
    end_addr = parser.max_address
    print(f"Address range: 0x{start_addr:08X} - 0x{end_addr:08X}")
    print(f"Total size: {end_addr - start_addr + 1} bytes")
    print()
    
    # Split into blocks and calculate CRC
    current_addr = start_addr
    block_index = 0
    total_crc = 0
    crc_list = []
    
    print(f"{'Block':<6} {'Address':<12} {'Length':<10} {'CRC16':<10} {'Total CRC':<12}")
    print("-" * 60)
    
    while current_addr <= end_addr:
        # Extract one block of data
        block_data = bytearray()
        for offset in range(block_size):
            addr = current_addr + offset
            if addr in parser.data_map:
                block_data.append(parser.data_map[addr])
            else:
                block_data.append(0xFF)
        
        # Calculate CRC for this block
        block_crc = _crc16_modbus(bytes(block_data))
        total_crc += block_crc
        crc_list.append(block_crc)
        
        # Display info
        print(f"{block_index:<6} 0x{current_addr:08X}  {len(block_data):<10} "
              f"0x{block_crc:04X}    0x{total_crc & 0xFFFF:04X}")
        
        # Next block
        current_addr += block_size
        block_index += 1
        
        # Check if all data has been processed
        if current_addr > end_addr:
            break
    
    # Final result
    end_crc = total_crc & 0xFFFF
    print("-" * 60)
    print(f"Total blocks: {block_index}")
    print(f"ENDCRC (16-bit truncated): 0x{end_crc:04X} ({end_crc})")
    print()
    
    # Show detailed CRC list (for device comparison)
    print("CRC value for each block (for device comparison):")
    for i, crc in enumerate(crc_list):
        print(f"  Block{i}: 0x{crc:04X} ({crc})", end="")
        if (i + 1) % 4 == 0:
            print()  # New line every 4 blocks
        else:
            print(" | ", end="")
    print()
    print()
    
    # Show byte order info
    print("ENDCRC byte order (big-endian):")
    print(f"  High byte: 0x{(end_crc >> 8) & 0xFF:02X}")
    print(f"  Low byte: 0x{end_crc & 0xFF:02X}")
    print(f"  Send sequence: {(end_crc >> 8) & 0xFF:02X} {end_crc & 0xFF:02X}")
    print()
    
    # C code verification
    print("Device C code verification:")
    print("=" * 60)
    print("uint16_t end_crc = 0;")
    print(f"uint16_t crc_values[{block_index}] = {{")
    for i in range(0, len(crc_list), 8):
        line_crcs = crc_list[i:i+8]
        line_str = ", ".join([f"0x{crc:04X}" for crc in line_crcs])
        print(f"    {line_str},")
    print("};")
    print(f"\nfor(int i = 0; i < {block_index}; i++) {{")
    print("    end_crc += crc_values[i];")
    print("}")
    print(f"// Final end_crc = 0x{end_crc:04X}")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_crc.py <HEX_file_path> [block_size]")
        print("Example: python debug_crc.py NationFlyMotor.hex 2048")
        sys.exit(1)
    
    hex_file = sys.argv[1]
    block_size = int(sys.argv[2]) if len(sys.argv) > 2 else 2048
    
    debug_crc_calculation(hex_file, block_size)
