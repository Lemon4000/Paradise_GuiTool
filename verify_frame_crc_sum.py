"""
验证帧CRC累加计算
计算每一帧的帧CRC，然后直接累加得到ENDCRC
"""
import sys
from hex_parser import HexParser
import Usart_Para_FK

def calculate_frame_crc_sum(hex_file, block_size=2048):
    """计算所有帧CRC的累加和"""
    parser = HexParser()
    parser.load_file(hex_file)
    blocks = parser.get_blocks(block_size)
    
    total_frame_crc = 0
    frame_crc_list = []
    
    print(f"HEX文件: {hex_file}")
    print(f"数据块大小: {block_size} 字节")
    print(f"总块数: {len(blocks)}")
    print("=" * 80)
    
    for i, (address, data) in enumerate(blocks, 1):
        # 构造帧payload（不包含前导符和帧CRC）
        header = f"!HEX:START{address:08X},SIZE{len(data)},DATA".encode('ascii')
        payload = header + data + b';'
        
        # 计算帧CRC
        frame_crc = Usart_Para_FK._crc16_modbus(payload)
        
        # 累加（直接相加，截断到16位）
        total_frame_crc = (total_frame_crc + frame_crc) & 0xFFFF
        frame_crc_list.append(frame_crc)
        
        if i <= 5 or i > len(blocks) - 5:  # 只显示前5个和后5个
            print(f"块{i:3d}: 地址=0x{address:08X}, 帧CRC=0x{frame_crc:04X}, 累计=0x{total_frame_crc:04X}")
        elif i == 6:
            print("  ...")
    
    print("=" * 80)
    print(f"\n所有帧CRC值（每行8个）:")
    for i in range(0, len(frame_crc_list), 8):
        chunk = frame_crc_list[i:i+8]
        crc_strs = [f"0x{crc:04X}" for crc in chunk]
        print(f"  {', '.join(crc_strs)}")
    
    print("=" * 80)
    print(f"\n最终 ENDCRC (所有帧CRC直接相加): 0x{total_frame_crc:04X} (十进制: {total_frame_crc})")
    print("=" * 80)
    
    return total_frame_crc, frame_crc_list

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"用法: python {sys.argv[0]} <hex文件路径>")
        sys.exit(1)
    
    hex_file = sys.argv[1]
    calculate_frame_crc_sum(hex_file, block_size=2048)
