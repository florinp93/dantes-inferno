#!/usr/bin/env python3
"""Examine XISO structure around the first XEX2 location."""
import struct

iso_path = r"D:\Zerk Cloud\Dante's Inferno\disc\Dante's Inferno (Europe) (En,De,It).iso"

def hexdump(data, offset=0, length=None):
    if length is None:
        length = len(data)
    for i in range(0, min(length, len(data)), 16):
        row = data[i:i+16]
        hex_str = ' '.join(f'{b:02X}' for b in row)
        ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in row)
        print(f"  {offset+i:08X}: {hex_str:<48}  {ascii_str}")

with open(iso_path, 'rb') as f:
    # Look at area around first XEX2 at 0xB2800
    print("=== Around first XEX2 (0xB2800) ===")
    f.seek(0xB2700)
    data = f.read(0x200)
    hexdump(data, 0xB2700, 0x200)
    
    # The XISO root directory for Xbox 360 is typically at the start of the game partition
    # Let's try to find it by looking at sectors 300-400
    print("\n=== Scanning sectors 300-400 for directory-like data ===")
    for sector in range(300, 400):
        f.seek(sector * 2048)
        data = f.read(2048)
        # Check if this sector has non-zero data
        if any(b != 0 for b in data[:64]):
            # Check if it looks like a directory table
            # XISO dir entries have name strings
            has_text = False
            for b in data:
                if 32 <= b < 127:
                    has_text = True
                    break
            if has_text:
                print(f"\nSector {sector} (0x{sector*2048:X}) has data:")
                hexdump(data, sector * 2048, 128)
    
    # Also check the area just before the first XEX2
    # The directory entry pointing to the XEX should be nearby
    print("\n=== Sectors 350-360 (around first XEX2 at sector 357) ===")
    for sector in range(350, 360):
        f.seek(sector * 2048)
        data = f.read(2048)
        if any(b != 0 for b in data[:64]):
            print(f"\nSector {sector} (0x{sector*2048:X}):")
            hexdump(data, sector * 2048, 256)
    
    # Try to find XISO root by looking for "default.xex" string
    print("\n=== Searching for 'default.xex' string ===")
    f.seek(0)
    chunk_size = 4 * 1024 * 1024
    offset = 0
    file_size = f.seek(0, 2)
    f.seek(0)
    
    target = b'default.xex'
    while offset < file_size:
        f.seek(offset)
        chunk = f.read(chunk_size + len(target))
        if not chunk:
            break
        pos = 0
        while True:
            idx = chunk.find(target, pos)
            if idx == -1:
                break
            abs_off = offset + idx
            print(f"Found 'default.xex' at 0x{abs_off:X} (sector {abs_off//2048})")
            # Show context around it
            ctx_start = max(0, idx - 32)
            f.seek(offset + ctx_start)
            ctx = f.read(128)
            print(f"  Context:")
            hexdump(ctx, offset + ctx_start, 128)
            pos = idx + 1
        offset += chunk_size
