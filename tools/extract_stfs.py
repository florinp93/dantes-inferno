#!/usr/bin/env python3
"""Extract an STFS container (Xbox 360 CON/PIRS/LIVE) to a directory."""
import struct
import sys
import os
import math

BLOCK_SIZE = 0x1000
BLOCKS_PER_HASH_LEVEL = [170, 28900, 4913000]
END_OF_CHAIN = 0xFFFFFF
ENTRIES_PER_DIR_BLOCK = 0x40  # 0x1000 / 0x40 = 0x40 entries
DIR_ENTRY_SIZE = 0x40

def load_uint24_le(data):
    return data[0] | (data[1] << 8) | (data[2] << 16)

def block_to_offset_stfs(block_index, header_size, blocks_per_hash_table):
    base = BLOCKS_PER_HASH_LEVEL[0]
    block = block_index
    for i in range(3):
        block += ((block_index + base) // base) * blocks_per_hash_table
        if block_index < base:
            break
        base *= BLOCKS_PER_HASH_LEVEL[0]
    rounded_header = ((header_size + BLOCK_SIZE - 1) // BLOCK_SIZE) * BLOCK_SIZE
    return rounded_header + (block << 12)

def get_hash_entry(file_data, block_index, header_size, blocks_per_hash_table):
    """Get the hash entry for a given block index, returning (next_block, level0_next)."""
    # Calculate which hash table block contains this block's hash
    if block_index < BLOCKS_PER_HASH_LEVEL[0]:
        hash_block = 0
    else:
        block = (block_index // BLOCKS_PER_HASH_LEVEL[0]) * blocks_per_hash_table
        block += ((block_index // BLOCKS_PER_HASH_LEVEL[1]) + 1) * blocks_per_hash_table
        # This is more complex - for simplicity, use the same formula as the C++ code
        # Level 0 hash block number
        if block_index < BLOCKS_PER_HASH_LEVEL[0]:
            hash_block = 0
        else:
            hash_block = (block_index // BLOCKS_PER_HASH_LEVEL[0]) * blocks_per_hash_table
            hash_block += ((block_index // BLOCKS_PER_HASH_LEVEL[1]) + 1) * blocks_per_hash_table

    # Offset within the hash table
    entry_index = block_index % BLOCKS_PER_HASH_LEVEL[0]

    # Hash table is at the beginning of the hash block
    hash_offset = block_to_offset_stfs(hash_block, header_size, blocks_per_hash_table)
    # Each hash entry is 0x18 bytes
    entry_offset = hash_offset + entry_index * 0x18

    if entry_offset + 0x18 > len(file_data):
        return None

    entry_data = file_data[entry_offset:entry_offset + 0x18]
    # StfsHashEntry: 0x14 bytes hash, 3 bytes level0_next_block, 1 byte flags
    next_block = load_uint24_le(entry_data[0x14:0x17])
    return next_block

def extract_stfs(stfs_path, output_dir):
    with open(stfs_path, 'rb') as f:
        file_data = f.read()

    # Parse header
    magic = file_data[0:4]
    print(f"Magic: {magic}")

    # XContentHeader: magic(4) + signature(0x228) + licenses(0x100) + content_id(0x14) + header_size(4)
    header_size = struct.unpack('>I', file_data[0x344:0x348])[0]
    print(f"Header size: {header_size:#x}")

    if header_size == 0:
        header_size = 0x971A  # sizeof(StfsHeader)

    # XContentMetadata starts at 0x344
    # Volume type at offset 0x344 + 0x23B = 0x57F (be<uint32_t>)
    # Actually, let me find the volume_descriptor in the metadata
    # XContentMetadata is 0x93D6 bytes, but we need specific fields

    # The STFS volume descriptor is at offset 0x371 within the metadata
    # metadata starts at 0x344
    # volume_descriptor is at metadata + 0x355 = 0x344 + 0x355 = 0x699
    # Actually, let me calculate from the struct layout

    # XContentMetadata layout (from stfs_xbox.h):
    # ... many fields ...
    # volume_descriptor (StfsVolumeDescriptor, 0x24 bytes) at some offset
    # data_file_count (be<uint32_t>) after volume_descriptor
    # volume_type (be<uint32_t>) after data_file_size

    # Let me just read the key fields from known offsets
    # The StfsVolumeDescriptor is at offset 0x371 in the metadata
    # metadata starts at 0x344 in the file
    # So volume_descriptor.stfs is at 0x344 + 0x371 = 0x6B5

    # Actually, let me be more precise. Looking at the struct:
    # XContentMetadata has many fields before volume_descriptor
    # Let me search for the descriptor_length == 0x24 pattern

    # From the struct: StfsVolumeDescriptor starts with descriptor_length (uint8) = 0x24
    # Let me find it by searching for the pattern

    # Actually, let me use the known offset from the struct sizes
    # XContentMetadata fields before volume_descriptor:
    # content_size(8) + execution_info(variable + console_id(5) + profile_id(8)
    # The volume_descriptor is a union at a specific offset

    # Let me just read from the STFS header directly
    # The metadata.volume_type is at a known offset
    # From the struct: be<XContentVolumeType> volume_type
    # XContentVolumeType: kStfs=0, kSvod=1

    # Let me find the volume descriptor by trying the standard offset
    # In the XContentMetadata struct, volume_descriptor is at offset 0x355
    # So in the file: 0x344 (metadata start) + 0x355 = 0x699

    # StfsVolumeDescriptor at 0x699:
    # descriptor_length (1) = 0x24
    # version (1)
    # flags (1)
    # file_table_block_count (2, be)
    # file_table_block_number_raw (3, le)
    # ...

    vd_offset = 0x344 + 0x355  # 0x699

    # Verify descriptor_length
    desc_len = file_data[vd_offset]
    print(f"Descriptor length at 0x{vd_offset:X}: {desc_len:#x}")

    if desc_len != 0x24:
        # Try another offset - search for descriptor_length == 0x24
        print("Searching for STFS volume descriptor...")
        for off in range(0x344, min(0x344 + 0x1000, len(file_data) - 0x24)):
            if file_data[off] == 0x24 and file_data[off + 1] in (0, 1, 2):
                # Check if file_table_block_count is reasonable
                ftbc = struct.unpack('>H', file_data[off + 3:off + 5])[0]
                if 0 < ftbc < 100:
                    vd_offset = off
                    print(f"Found volume descriptor at 0x{off:X}, file_table_block_count={ftbc}")
                    break

    descriptor_length = file_data[vd_offset]
    version = file_data[vd_offset + 1]
    flags_byte = file_data[vd_offset + 2]
    file_table_block_count = struct.unpack('>H', file_data[vd_offset + 3:vd_offset + 5])[0]
    file_table_block_number = load_uint24_le(file_data[vd_offset + 5:vd_offset + 8])

    read_only = (flags_byte & 1) != 0
    blocks_per_hash_table = 1 if read_only else 2

    print(f"Volume descriptor at 0x{vd_offset:X}:")
    print(f"  descriptor_length: {descriptor_length:#x}")
    print(f"  version: {version}")
    print(f"  flags: {flags_byte:#x} (read_only={read_only})")
    print(f"  file_table_block_count: {file_table_block_count}")
    print(f"  file_table_block_number: {file_table_block_number}")
    print(f"  blocks_per_hash_table: {blocks_per_hash_table}")

    # Read file table blocks
    all_entries = []
    table_block_index = file_table_block_number

    for n in range(file_table_block_count):
        offset = block_to_offset_stfs(table_block_index, header_size, blocks_per_hash_table)
        print(f"  File table block {n} at offset 0x{offset:X}")

        if offset + BLOCK_SIZE > len(file_data):
            print(f"  ERROR: offset beyond file size")
            break

        # Read directory entries
        for m in range(ENTRIES_PER_DIR_BLOCK):
            entry_offset = offset + m * DIR_ENTRY_SIZE
            entry_data = file_data[entry_offset:entry_offset + DIR_ENTRY_SIZE]

            if entry_data[0] == 0:
                break  # Done

            name_bytes = entry_data[0:40]
            name_len = name_bytes[39] & 0x3F if len(name_bytes) > 39 else 0
            # Actually, flags are at offset 40
            flags_byte2 = entry_data[40]
            name_length = flags_byte2 & 0x3F
            is_directory = (flags_byte2 & 0x80) != 0
            is_contiguous = (flags_byte2 & 0x40) != 0

            valid_data_blocks = load_uint24_le(entry_data[41:44])
            allocated_data_blocks = load_uint24_le(entry_data[44:47])
            start_block_number = load_uint24_le(entry_data[47:50])
            directory_index = struct.unpack('>H', entry_data[50:52])[0]
            length = struct.unpack('>I', entry_data[52:56])[0]

            name = name_bytes[:name_length].decode('ascii', errors='replace').rstrip('\x00')

            print(f"  Entry {m}: name='{name}' dir={is_directory} len={length} "
                  f"start_block={start_block_number} dir_idx={directory_index}")

            all_entries.append({
                'name': name,
                'is_directory': is_directory,
                'length': length,
                'start_block': start_block_number,
                'directory_index': directory_index,
                'valid_data_blocks': valid_data_blocks,
                'allocated_data_blocks': allocated_data_blocks,
                'is_contiguous': is_contiguous,
            })

        # Get next table block
        next_block = get_hash_entry(file_data, table_block_index, header_size, blocks_per_hash_table)
        if next_block is None or next_block == END_OF_CHAIN:
            break
        table_block_index = next_block

    # Build directory tree and extract files
    os.makedirs(output_dir, exist_ok=True)

    # Create directory structure first
    dir_paths = {0xFFFF: output_dir}
    for i, entry in enumerate(all_entries):
        if entry['is_directory']:
            parent_path = dir_paths.get(entry['directory_index'], output_dir)
            dir_path = os.path.join(parent_path, entry['name'])
            os.makedirs(dir_path, exist_ok=True)
            dir_paths[i + 1] = dir_path  # +1 because root is index 0

    # Extract files
    for i, entry in enumerate(all_entries):
        if entry['is_directory']:
            continue

        parent_path = dir_paths.get(entry['directory_index'], output_dir)
        file_path = os.path.join(parent_path, entry['name'])
        print(f"Extracting: {file_path} ({entry['length']} bytes)")

        remaining = entry['length']
        block_index = entry['start_block']

        with open(file_path, 'wb') as out:
            while remaining > 0 and block_index != END_OF_CHAIN:
                block_offset = block_to_offset_stfs(block_index, header_size, blocks_per_hash_table)
                to_read = min(BLOCK_SIZE, remaining)

                if block_offset + to_read > len(file_data):
                    print(f"  WARNING: block offset 0x{block_offset:X} beyond file size")
                    break

                out.write(file_data[block_offset:block_offset + to_read])
                remaining -= to_read

                if entry['is_contiguous']:
                    block_index += 1
                else:
                    next_block = get_hash_entry(file_data, block_index, header_size, blocks_per_hash_table)
                    if next_block is None:
                        break
                    block_index = next_block

    print(f"\nExtraction complete to: {output_dir}")
    return all_entries

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: extract_stfs.py <stfs_file> <output_dir>")
        sys.exit(1)
    extract_stfs(sys.argv[1], sys.argv[2])
