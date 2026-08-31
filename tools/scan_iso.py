#!/usr/bin/env python3
"""Scan Xbox 360 ISO for XEX2 magic and non-zero regions."""
import struct
import sys
import os

iso_path = sys.argv[1] if len(sys.argv) > 1 else r"D:\Zerk Cloud\Dante's Inferno\disc\Dante's Inferno (Europe) (En,De,It).iso"

file_size = os.path.getsize(iso_path)
print(f"ISO size: {file_size} bytes ({file_size/1024/1024:.1f} MB)")
print(f"Total sectors: {file_size // 2048}")
print()

# Search for XEX2 magic
XEX2 = b'XEX2'
chunk_size = 4 * 1024 * 1024  # 4MB chunks
found_xex = []

with open(iso_path, 'rb') as f:
    offset = 0
    while offset < file_size:
        f.seek(offset)
        chunk = f.read(chunk_size + 4)  # overlap for boundary
        if not chunk:
            break
        
        pos = 0
        while True:
            idx = chunk.find(XEX2, pos)
            if idx == -1:
                break
            abs_offset = offset + idx
            sector = abs_offset // 2048
            print(f"Found XEX2 at offset 0x{abs_offset:X} (sector {sector})")
            found_xex.append(abs_offset)
            if len(found_xex) >= 10:
                break
            pos = idx + 1
        
        if len(found_xex) >= 10:
            break
        offset += chunk_size
        if offset % (100 * 1024 * 1024) == 0:
            print(f"  scanned {offset // 1024 // 1024} MB...")

print(f"\nTotal XEX2 found: {len(found_xex)}")

# Also scan for non-zero regions to find game partition
print("\n=== Scanning for non-zero regions ===")
with open(iso_path, 'rb') as f:
    offset = 0
    in_nonzero = False
    region_start = 0
    last_nonzero_end = 0
    
    while offset < file_size:
        f.seek(offset)
        chunk = f.read(chunk_size)
        if not chunk:
            break
        
        is_nonzero = any(b != 0 for b in chunk)
        
        if is_nonzero and not in_nonzero:
            in_nonzero = True
            region_start = offset
        elif not is_nonzero and in_nonzero:
            in_nonzero = False
            region_end = offset
            size = region_end - region_start
            if size > 1024:  # only report regions > 1KB
                print(f"  0x{region_start:X} - 0x{region_end:X} ({size/1024:.0f} KB) sector {region_start//2048}")
        
        offset += chunk_size
    
    if in_nonzero:
        region_end = file_size
        size = region_end - region_start
        if size > 1024:
            print(f"  0x{region_start:X} - 0x{region_end:X} ({size/1024:.0f} KB) sector {region_start//2048}")

print("\nDone.")
