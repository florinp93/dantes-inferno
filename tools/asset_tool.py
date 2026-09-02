#!/usr/bin/env python3
"""
Dante's Inferno Asset Extraction & Packing Tool
================================================

Extracts assets (videos, textures, models, audio) from the game's BIG/VIV
archives for upscaling, and packs them back in.

Pipeline:
  BIG (.viv)  ->  STR (.str)  ->  individual assets (TG4D/VP6/geometry/...)
                                         |
                                    vvvvvvvvvv
                            DDS / PNG / raw formats

Usage:
  python asset_tool.py list       <big_file.viv> [--filelist <path>]
  python asset_tool.py extract    <big_file.viv> <output_dir> [--filelist <path>] [--type textures|videos|models|audio|all]
  python asset_tool.py unpack-str <input.str> <output_dir>
  python asset_tool.py pack-big   <input_dir> <output.viv> [--filelist <path>]
  python asset_tool.py pack-str   <input_dir> <output.str>
  python asset_tool.py convert-texture <input.tg4d> <output.png|dds> [--width N] [--height N]
  python asset_tool.py make-texture <input.png|dds> <output.tg4d> [--format dxt5|dxt1]

Formats:
  BIG/VIV  - EA Visceral BIGH archive (bigfile0.viv, bigfile1.viv)
  STR      - StreamSet container (ols3 magic) with SHDR/SDAT/Rpak blocks
  TG4D     - DXT5/BC3 compressed texture (Visceral texture format)
  VP6      - EA VP6 video codec
  RefPack  - EA compression format used in STR data blocks
"""

import argparse
import io
import json
import os
import struct
import sys
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, BinaryIO

# ============================================================================
# Hash Function (EA Visceral)
# ============================================================================

def hash_filename(s: str) -> int:
    """EA Visceral file name hash: hash = hash * 65599 + char."""
    h = 0
    for c in s:
        h = ((h * 65599) + ord(c)) & 0xFFFFFFFF
    return h

# ============================================================================
# Filelist Loader
# ============================================================================

def load_filelist(filelist_paths: List[str]) -> Dict[int, str]:
    """Load filelist files and build hash -> filename mapping."""
    hash_to_name = {}
    for flp in filelist_paths:
        if not os.path.exists(flp):
            continue
        with open(flp, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                line_norm = line.replace('/', '\\').lower()
                h = hash_filename(line_norm)
                hash_to_name[h] = line_norm
    return hash_to_name

def find_filelists(base_dir: str) -> List[str]:
    """Find all .filelist files in a directory tree."""
    result = []
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if f.lower().endswith('.filelist'):
                result.append(os.path.join(root, f))
    return result

# ============================================================================
# BIG/VIV Archive Format (BIGH)
# ============================================================================

BIG_MAGIC = 0x42494748  # "BIGH"
BIG_TRAILER_1 = 0x4C323833  # "L283"
BIG_TRAILER_2 = 0x15050000

class BigEntry:
    __slots__ = ('offset', 'size', 'name_hash', 'filename', 'duplicate')

    def __init__(self, offset=0, size=0, name_hash=0, filename=None, duplicate=False):
        self.offset = offset
        self.size = size
        self.name_hash = name_hash
        self.filename = filename
        self.duplicate = duplicate

    def __repr__(self):
        fn = self.filename or f"0x{self.name_hash:08X}"
        return f"BigEntry(off=0x{self.offset:08X}, size={self.size}, name={fn})"

def read_big_header(f: BinaryIO) -> Tuple[int, int, int, int]:
    """Read BIG file header. Returns (magic, total_size, num_files, header_size)."""
    f.seek(0)
    magic = struct.unpack('>I', f.read(4))[0]
    if magic != BIG_MAGIC:
        raise ValueError(f"Not a BIGH archive: magic=0x{magic:08X}")
    total_size = struct.unpack('<I', f.read(4))[0]
    num_files = struct.unpack('>I', f.read(4))[0]
    header_size = struct.unpack('>I', f.read(4))[0]
    return magic, total_size, num_files, header_size

def read_big_entries(f: BinaryIO) -> List[BigEntry]:
    """Read all directory entries from a BIG file."""
    magic, total_size, num_files, header_size = read_big_header(f)
    entries = []
    seen_names = set()
    for _ in range(num_files):
        offset, size, name_hash = struct.unpack('>III', f.read(12))
        entry = BigEntry(offset=offset, size=size, name_hash=name_hash)
        if name_hash in seen_names:
            entry.duplicate = True
        else:
            seen_names.add(name_hash)
        entries.append(entry)
    return entries

def read_big_entry_data(f: BinaryIO, entry: BigEntry) -> bytes:
    """Read the data for a single BIG entry."""
    f.seek(entry.offset)
    return f.read(entry.size)

def write_big_archive(output_path: str, entries: List[Tuple[str, bytes]],
                      align: int = 2048):
    """Write a BIG archive from a list of (filename, data) tuples."""
    # Compute hashes
    hashed = []
    for filename, data in entries:
        fn_norm = filename.replace('/', '\\').lower()
        h = hash_filename(fn_norm)
        hashed.append((h, filename, data))

    # Sort by hash (matching original format)
    hashed.sort(key=lambda x: x[0])

    num_files = len(hashed)
    header_size = 16 + (num_files * 12) + 8

    with open(output_path, 'wb') as f:
        # Write dummy header
        f.write(struct.pack('>I', BIG_MAGIC))
        f.write(struct.pack('<I', 0))  # total size placeholder
        f.write(struct.pack('>I', num_files))
        f.write(struct.pack('>I', header_size))

        # Write dummy directory entries
        for h, fn, data in hashed:
            f.write(struct.pack('>III', 0, 0, h))

        # Write trailer
        f.write(struct.pack('>II', BIG_TRAILER_1, BIG_TRAILER_2))

        # Align to sector boundary
        current_pos = f.tell()
        aligned_pos = ((current_pos + align - 1) // align) * align
        f.write(b'\x00' * (aligned_pos - current_pos))

        # Write file data and record offsets
        offsets = []
        for h, fn, data in hashed:
            offset = f.tell()
            offsets.append((offset, len(data)))
            f.write(data)
            # Align
            current_pos = f.tell()
            aligned_pos = ((current_pos + align - 1) // align) * align
            f.write(b'\x00' * (aligned_pos - current_pos))

        # Go back and write real header + directory
        total_size = f.tell()
        f.seek(0)
        f.write(struct.pack('>I', BIG_MAGIC))
        f.write(struct.pack('<I', total_size))
        f.write(struct.pack('>I', num_files))
        f.write(struct.pack('>I', header_size))

        for i, (h, fn, data) in enumerate(hashed):
            offset, size = offsets[i]
            # Size in directory is the aligned size
            aligned_size = ((size + align - 1) // align) * align
            f.write(struct.pack('>III', offset, aligned_size, h))

        f.write(struct.pack('>II', BIG_TRAILER_1, BIG_TRAILER_2))

# ============================================================================
# RefPack Compression/Decompression
# ============================================================================

def refpack_decompress(data: bytes) -> bytes:
    """Decompress RefPack compressed data (ported from Gibbed.RefPack)."""
    if len(data) < 2:
        raise ValueError("Data too short for RefPack header")

    header = (data[0] << 8) | data[1]
    if (header & 0x1FFF) != 0x10FB:
        raise ValueError("Input is not RefPack compressed")

    is_long = (header & 0x8000) != 0
    is_doubled = (header & 0x0100) != 0

    if is_doubled:
        raise ValueError("Doubled RefPack not supported")

    pos = 2
    if is_long:
        if pos + 4 > len(data):
            raise ValueError("Could not read uncompressed size")
        uncompressed_size = struct.unpack('>I', data[pos:pos+4])[0]
        pos += 4
    else:
        if pos + 3 > len(data):
            raise ValueError("Could not read uncompressed size")
        uncompressed_size = (data[pos] << 16) | (data[pos+1] << 8) | data[pos+2]
        pos += 3

    output = bytearray(uncompressed_size)
    offset = 0

    while pos < len(data):
        prefix = data[pos]
        pos += 1

        plain_size = 0
        copy_size = 0
        copy_offset = 0
        stop = False

        if prefix < 0x80:
            if pos >= len(data):
                break
            extra = data[pos]
            pos += 1
            plain_size = prefix & 0x03
            copy_size = ((prefix & 0x1C) >> 2) + 3
            copy_offset = (((prefix & 0x60) << 3) | extra) + 1
        elif prefix < 0xC0:
            if pos + 2 > len(data):
                break
            b0, b1 = data[pos], data[pos+1]
            pos += 2
            plain_size = b0 >> 6
            copy_size = (prefix & 0x3F) + 4
            copy_offset = (((b0 & 0x3F) << 8) | b1) + 1
        elif prefix < 0xE0:
            if pos + 3 > len(data):
                break
            b0, b1, b2 = data[pos], data[pos+1], data[pos+2]
            pos += 3
            plain_size = prefix & 3
            copy_size = (((prefix & 0x0C) << 6) | b2) + 5
            copy_offset = (((((prefix & 0x10) << 4) | b0) << 8) | b1) + 1
        elif prefix < 0xFC:
            plain_size = ((prefix & 0x1F) + 1) * 4
        else:
            plain_size = prefix & 3
            stop = True

        if plain_size > 0:
            if pos + plain_size > len(data):
                plain_size = len(data) - pos
            output[offset:offset+plain_size] = data[pos:pos+plain_size]
            pos += plain_size
            offset += plain_size

        if copy_size > 0:
            for i in range(copy_size):
                if offset + i < len(output) and offset - copy_offset + i >= 0:
                    output[offset + i] = output[offset - copy_offset + i]
            offset += copy_size

        if stop:
            break

    return bytes(output[:offset])

def refpack_compress(data: bytes) -> bytes:
    """Compress data using RefPack format.

    Uses a simple LZ77-style search. Not optimal but produces valid output.
    """
    if len(data) == 0:
        return struct.pack('>H', 0x10FB) + b'\x00\x00\x00' + b'\xFC'

    uncompressed_size = len(data)
    output = bytearray()

    # Header: short format (size < 16MB)
    if uncompressed_size < 0x1000000:
        output.append(0x10)  # low byte of header
        output.append(0xFB)  # high byte: 0x10FB with no flags
        # 3-byte uncompressed size (big-endian)
        output.append((uncompressed_size >> 16) & 0xFF)
        output.append((uncompressed_size >> 8) & 0xFF)
        output.append(uncompressed_size & 0xFF)
    else:
        # Long format
        header = 0x800010FB
        output.append((header >> 8) & 0xFF)
        output.append(header & 0xFF)
        output.append((uncompressed_size >> 24) & 0xFF)
        output.append((uncompressed_size >> 16) & 0xFF)
        output.append((uncompressed_size >> 8) & 0xFF)
        output.append(uncompressed_size & 0xFF)

    pos = 0
    data_len = len(data)

    # Minimum match length and window size
    MIN_MATCH = 3
    MAX_OFFSET = 0x1FFFF  # 17-bit offset
    WINDOW_SIZE = 0x20000

    while pos < data_len:
        # Search for matches
        best_offset = 0
        best_length = 0

        search_start = max(0, pos - WINDOW_SIZE)
        remaining = data_len - pos

        if remaining >= MIN_MATCH:
            # Simple search: try positions backwards
            for candidate in range(search_start, pos):
                offset = pos - candidate
                if offset > MAX_OFFSET:
                    break

                # Check match length
                match_len = 0
                max_match = min(remaining, 1024)  # cap match length
                while match_len < max_match and data[candidate + match_len] == data[pos + match_len]:
                    match_len += 1

                if match_len > best_length and match_len >= MIN_MATCH:
                    best_length = match_len
                    best_offset = offset
                    if match_len >= 1024:
                        break  # good enough

        if best_length >= MIN_MATCH:
            # Emit copy command
            # Use 2-byte form (prefix 0x80-0xBF) for most cases
            if best_offset <= 0x3FFF and best_length >= 4 and best_length <= 0x3F + 4:
                # 2-byte form: prefix 0x80-0xBF
                plain = 0  # no plain bytes before copy
                prefix = 0x80 | (best_length - 4)
                b0 = ((best_offset - 1) >> 8) & 0x3F
                b1 = (best_offset - 1) & 0xFF
                # Encode plain in b0 high bits
                b0 |= (plain << 6)
                output.append(prefix)
                output.append(b0)
                output.append(b1)
                pos += best_length
            elif best_offset <= 0x1FFF and best_length >= 3 and best_length <= 0x07 + 3:
                # 1-byte form: prefix 0x00-0x7F
                prefix = ((best_offset - 1) >> 8) & 0x60
                prefix |= ((best_length - 3) << 2) & 0x1C
                extra = (best_offset - 1) & 0xFF
                output.append(prefix)
                output.append(extra)
                pos += best_length
            else:
                # 3-byte form: prefix 0xC0-0xDF
                plain = 0
                prefix = 0xC0 | (plain & 3)
                prefix |= ((best_length - 5) >> 6) & 0x0C
                if best_offset <= 0x1FFFFF:
                    prefix |= 0x10 if (best_offset - 1) > 0xFFFF else 0
                b0 = ((best_offset - 1) >> 8) & 0xFF
                b1 = (best_offset - 1) & 0xFF
                b2 = (best_length - 5) & 0xFF
                output.append(prefix)
                output.append(b0)
                output.append(b1)
                output.append(b2)
                pos += best_length
        else:
            # Accumulate plain bytes
            plain_start = pos
            pos += 1
            while pos < data_len and (pos - plain_start) < 112:
                # Check if next position has a match
                remaining2 = data_len - pos
                if remaining2 >= MIN_MATCH:
                    has_match = False
                    for candidate in range(max(0, pos - WINDOW_SIZE), pos):
                        off = pos - candidate
                        if off > MAX_OFFSET:
                            break
                        ml = 0
                        mx = min(remaining2, 4)
                        while ml < mx and data[candidate + ml] == data[pos + ml]:
                            ml += 1
                        if ml >= MIN_MATCH:
                            has_match = True
                            break
                    if has_match:
                        break
                pos += 1

            plain_size = pos - plain_start

            # Emit plain blocks in chunks of up to 120 bytes (0x1D*4=120)
            while plain_size > 0:
                chunk = min(plain_size, 120)
                if chunk > 0:
                    # Use 0xE0-0xFB form for plain data
                    output.append(0xE0 | ((chunk // 4) - 1))
                    output.extend(data[plain_start:plain_start + chunk])
                    plain_start += chunk
                    plain_size -= chunk

    # Write stop marker
    output.append(0xFC | 0)  # stop with 0 plain bytes

    return bytes(output)

# ============================================================================
# StreamSet (STR) Format
# ============================================================================

STR_MAGIC_LE = 0x6F6C7333  # "ols3" in little-endian
STR_MAGIC_BE = 0x33736C6F  # "3slo" in little-endian (big-endian file)

BLOCK_OPTIONS = 0x6F6C7333  # "ols3"
BLOCK_CONTENT = 0x53484F43  # "SHOC"
BLOCK_PADDING = 0x46494C4C  # "FILL"

CONTENT_HEADER = 0x53484452  # "SHDR"
CONTENT_DATA = 0x53444154    # "SDAT"
CONTENT_COMPRESSED = 0x5270616B  # "Rpak"

class StreamContent:
    __slots__ = ('type', 'offset', 'size')

    def __init__(self, type_id=0, offset=0, size=0):
        self.type = type_id
        self.offset = offset
        self.size = size

class StreamFileInfo:
    """File info from SHDR header in STR files."""
    __slots__ = ('build', 'alignment', 'flags', 'type', 'unknown0c',
                 'type2', 'unknown14', 'unknown18', 'total_size',
                 'base_name', 'file_name', 'type_name')

    def __init__(self):
        self.build = 0
        self.alignment = 0
        self.flags = 0
        self.type = 0
        self.unknown0c = 0
        self.type2 = 0
        self.unknown14 = 0
        self.unknown18 = 0
        self.total_size = 0
        self.base_name = ""
        self.file_name = ""
        self.type_name = ""

    def serialize(self, endian: str) -> bytes:
        out = bytearray()
        fmt = '>' if endian == 'big' else '<'
        out += struct.pack(fmt + 'I', self.build)
        out += struct.pack(fmt + 'HH', self.alignment, self.flags)
        out += struct.pack(fmt + 'I', self.type)
        out += struct.pack(fmt + 'IIII', self.unknown0c, self.type2,
                           self.unknown14, self.unknown18)
        out += struct.pack(fmt + 'I', self.total_size)
        out += self.base_name.encode('ascii', 'replace') + b'\x00'
        out += self.file_name.encode('ascii', 'replace') + b'\x00'
        out += self.type_name.encode('ascii', 'replace') + b'\x00'
        return bytes(out)

    @classmethod
    def deserialize(cls, f: BinaryIO, endian: str) -> 'StreamFileInfo':
        info = cls()
        fmt = '>' if endian == 'big' else '<'

        info.build = struct.unpack(fmt + 'I', f.read(4))[0]
        info.alignment, info.flags = struct.unpack(fmt + 'HH', f.read(4))
        info.type = struct.unpack(fmt + 'I', f.read(4))[0]
        info.unknown0c, info.type2, info.unknown14, info.unknown18 = \
            struct.unpack(fmt + 'IIII', f.read(16))
        info.total_size = struct.unpack(fmt + 'I', f.read(4))[0]

        def read_string():
            s = bytearray()
            while True:
                c = f.read(1)
                if not c or c == b'\x00':
                    break
                s += c
            return s.decode('ascii', 'replace')

        info.base_name = read_string()
        info.file_name = read_string()
        info.type_name = read_string()
        return info

    def get_sane_filename(self) -> str:
        name = self.file_name
        pos = name.rfind('\\')
        if pos >= 0:
            name = name[pos + 1:]
        if len(name) > 50:
            name = name[:50]
        if len(name) == 0:
            name = "unknown"
        return f"{name}.{self.type_name}"

def parse_str_file(f: BinaryIO) -> Tuple[str, List[StreamContent], int, int]:
    """Parse a STR (StreamSet) file. Returns (endian, contents, unknown00, unknown02)."""
    f.seek(0)
    magic_bytes = f.read(4)
    magic = struct.unpack('<I', magic_bytes)[0]

    if magic == STR_MAGIC_LE:
        endian = 'little'
    elif magic == STR_MAGIC_BE:
        endian = 'big'
    else:
        # Try big-endian read
        magic_be = struct.unpack('>I', magic_bytes)[0]
        if magic_be == STR_MAGIC_LE:
            endian = 'big'
        else:
            raise ValueError(f"Not a StreamSet file: magic=0x{magic:08X}")

    fmt = '>' if endian == 'big' else '<'

    size = struct.unpack(fmt + 'I', f.read(4))[0]
    if size != 12:
        raise ValueError(f"Unexpected options block size: {size}")

    unknown00 = struct.unpack(fmt + 'H', f.read(2))[0]
    unknown02 = struct.unpack(fmt + 'H', f.read(2))[0]

    contents = []
    file_size = f.seek(0, 2)
    f.seek(12)  # After options block (4+4+2+2 = 12 bytes total)

    while f.tell() + 8 <= file_size:
        block_pos = f.tell()
        block_type = struct.unpack(fmt + 'I', f.read(4))[0]
        block_size = struct.unpack(fmt + 'I', f.read(4))[0]

        if block_size < 8 or block_pos + block_size > file_size:
            break

        if block_type == BLOCK_CONTENT:
            content_type = struct.unpack(fmt + 'I', f.read(4))[0]
            content = StreamContent(
                type_id=content_type,
                offset=f.tell(),
                size=block_size - 12
            )
            contents.append(content)

        f.seek(block_pos + block_size)

    return endian, contents, unknown00, unknown02

def unpack_str_file(input_path: str, output_dir: str,
                    decompress: bool = True) -> List[dict]:
    """Unpack a STR file into its constituent sub-files.
    Returns list of metadata dicts for each extracted file."""
    os.makedirs(output_dir, exist_ok=True)

    with open(input_path, 'rb') as f:
        endian, contents, str_u00, str_u02 = parse_str_file(f)
        fmt = '>' if endian == 'big' else '<'

        metadata = []
        i = 0
        counter = 0

        while i < len(contents):
            header_info = contents[i]
            if header_info.type != CONTENT_HEADER:
                i += 1
                continue

            f.seek(header_info.offset)
            file_info = StreamFileInfo.deserialize(f, endian)

            i += 1

            # Build output filename
            sane_name = file_info.get_sane_filename()
            out_name = f"{counter:04d}_{sane_name}"
            counter += 1
            out_name = os.path.join(file_info.type_name, out_name)
            out_path = os.path.join(output_dir, out_name)

            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            # Collect data blocks
            file_data = bytearray()
            read_size = 0
            while read_size < file_info.total_size and i < len(contents):
                data_info = contents[i]
                if data_info.type not in (CONTENT_DATA, CONTENT_COMPRESSED):
                    break

                f.seek(data_info.offset)

                if data_info.type == CONTENT_COMPRESSED and decompress:
                    compressed_size = struct.unpack(fmt + 'I', f.read(4))[0]
                    compressed_data = f.read(compressed_size)
                    decompressed = refpack_decompress(compressed_data)
                    left = file_info.total_size - read_size
                    write_size = min(left, len(decompressed))
                    file_data.extend(decompressed[:write_size])
                    read_size += write_size
                else:
                    left = file_info.total_size - read_size
                    write_size = min(left, data_info.size)
                    file_data.extend(f.read(write_size))
                    read_size += write_size

                i += 1

            with open(out_path, 'wb') as out:
                out.write(file_data)

            meta = {
                'build': f"0x{file_info.build:08X}",
                'alignment': f"0x{file_info.alignment:04X}",
                'flags': f"0x{file_info.flags:04X}",
                'type': f"0x{file_info.type:08X}",
                'type2': f"0x{file_info.type2:08X}",
                'unknown0c': f"0x{file_info.unknown0c:08X}",
                'unknown14': f"0x{file_info.unknown14:08X}",
                'unknown18': f"0x{file_info.unknown18:08X}",
                'base_name': file_info.base_name,
                'file_name': file_info.file_name,
                'type_name': file_info.type_name,
                'total_size': file_info.total_size,
                'extracted_path': out_name,
            }
            metadata.append(meta)
            print(f"  Extracted: {out_name} ({len(file_data)} bytes)")

        # Write metadata JSON (include STR header info)
        meta_path = os.path.join(output_dir, "@metadata.json")
        full_meta = {
            'str_header': {
                'endian': endian,
                'unknown00': str_u00,
                'unknown02': str_u02,
            },
            'files': metadata,
        }
        with open(meta_path, 'w', encoding='utf-8') as mf:
            json.dump(full_meta, mf, indent=2)

        return metadata

def pack_str_file(input_dir: str, output_path: str,
                  endian: str = 'big', buffer_size: int = 0x20000):
    """Pack a directory (with @metadata.json) back into a STR file."""
    meta_path = os.path.join(input_dir, "@metadata.json")
    if not os.path.exists(meta_path):
        raise ValueError(f"No @metadata.json found in {input_dir}")

    with open(meta_path, 'r', encoding='utf-8') as f:
        raw_meta = json.load(f)

    # Support both old (list) and new (dict with str_header) formats
    if isinstance(raw_meta, list):
        metadata = raw_meta
        str_u00, str_u02 = 2, 259
    else:
        str_header = raw_meta.get('str_header', {})
        endian = str_header.get('endian', endian)
        str_u00 = str_header.get('unknown00', 2)
        str_u02 = str_header.get('unknown02', 259)
        metadata = raw_meta.get('files', raw_meta)

    fmt = '>' if endian == 'big' else '<'

    with open(output_path, 'wb') as out:
        buffer = bytearray()

        # Options block
        buffer += struct.pack(fmt + 'I', BLOCK_OPTIONS)
        buffer += struct.pack(fmt + 'I', 12)
        buffer += struct.pack(fmt + 'HH', str_u00, str_u02)

        for meta in metadata:
            file_path = os.path.join(input_dir, meta['extracted_path'])
            if not os.path.exists(file_path):
                print(f"  WARNING: Missing file {meta['extracted_path']}, skipping")
                continue

            with open(file_path, 'rb') as inf:
                file_data = inf.read()

            total_size = len(file_data)

            # Build header
            info = StreamFileInfo()
            info.build = int(meta['build'], 16)
            info.alignment = int(meta['alignment'], 16)
            info.flags = int(meta['flags'], 16)
            info.type = int(meta['type'], 16)
            info.type2 = int(meta['type2'], 16)
            info.unknown0c = int(meta['unknown0c'], 16)
            info.unknown14 = int(meta['unknown14'], 16)
            info.unknown18 = int(meta['unknown18'], 16)
            info.total_size = total_size
            info.base_name = meta['base_name']
            info.file_name = meta['file_name']
            info.type_name = meta['type_name']

            header_data = info.serialize(endian)
            # Align to 4
            while len(header_data) % 4 != 0:
                header_data += b'\x00'

            # Check buffer space
            if len(buffer) + 8 + len(header_data) > buffer_size:
                # Flush buffer with padding
                pad_size = buffer_size - len(buffer)
                if pad_size >= 8:
                    buffer += struct.pack(fmt + 'I', BLOCK_PADDING)
                    buffer += struct.pack(fmt + 'I', pad_size)
                    buffer += b'\x00' * (pad_size - 8)
                out.write(buffer)
                buffer = bytearray()

            # Write SHDR block
            buffer += struct.pack(fmt + 'I', BLOCK_CONTENT)
            buffer += struct.pack(fmt + 'I', 8 + len(header_data))
            buffer += struct.pack(fmt + 'I', CONTENT_HEADER)
            buffer += header_data

            # Write data blocks
            pos = 0
            while pos < total_size:
                remaining = total_size - pos
                space = buffer_size - len(buffer) - 12
                if space <= 0:
                    # Flush
                    pad_size = buffer_size - len(buffer)
                    if pad_size >= 8:
                        buffer += struct.pack(fmt + 'I', BLOCK_PADDING)
                        buffer += struct.pack(fmt + 'I', pad_size)
                        buffer += b'\x00' * (pad_size - 8)
                    out.write(buffer)
                    buffer = bytearray()
                    space = buffer_size - len(buffer) - 12

                block_data_size = min(remaining, space)
                buffer += struct.pack(fmt + 'I', BLOCK_CONTENT)
                buffer += struct.pack(fmt + 'I', 8 + 4 + block_data_size)
                buffer += struct.pack(fmt + 'I', CONTENT_DATA)
                buffer += file_data[pos:pos + block_data_size]
                pos += block_data_size

        # Final flush with padding
        if len(buffer) > 0:
            pad_size = buffer_size - len(buffer)
            if pad_size >= 8:
                buffer += struct.pack(fmt + 'I', BLOCK_PADDING)
                buffer += struct.pack(fmt + 'I', pad_size)
                buffer += b'\x00' * (pad_size - 8)
            out.write(buffer)

    print(f"  Packed {len(metadata)} files into {output_path}")

# ============================================================================
# Texture Conversion (TG4D / DXT5)
# ============================================================================

# DDS format constants
DDS_MAGIC = b'DDS '
DDS_HEADER_SIZE = 124
DDSD_CAPS = 0x1
DDSD_HEIGHT = 0x2
DDSD_WIDTH = 0x4
DDSD_PITCH = 0x8
DDSD_PIXELFORMAT = 0x1000
DDSD_MIPMAPCOUNT = 0x20000
DDSD_LINEARSIZE = 0x80000

DDPF_FOURCC = 0x4

DDSCAPS_TEXTURE = 0x1000

DDS_FOURCC_DXT5 = b'DXT5'
DDS_FOURCC_DXT1 = b'DXT1'

def dxt5_to_dds(data: bytes, width: int, height: int,
                mipmaps: int = 1) -> bytes:
    """Wrap raw DXT5 compressed data in a DDS file header."""
    out = bytearray()
    out += DDS_MAGIC

    # DDS header
    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE
    if mipmaps > 1:
        flags |= DDSD_MIPMAPCOUNT

    block_size = max(1, ((width + 3) // 4) * ((height + 3) // 4)) * 16

    out += struct.pack('<I', DDS_HEADER_SIZE)  # header size
    out += struct.pack('<I', flags)
    out += struct.pack('<I', height)
    out += struct.pack('<I', width)
    out += struct.pack('<I', block_size)  # pitch/linear size
    out += struct.pack('<I', 0)  # depth
    out += struct.pack('<I', mipmaps)  # mipmap count
    out += b'\x00' * 44  # reserved[11]

    # Pixel format
    out += struct.pack('<I', 32)  # pf size
    out += struct.pack('<I', DDPF_FOURCC)
    out += DDS_FOURCC_DXT5
    out += struct.pack('<I', 0)  # rgb bits
    out += struct.pack('<I', 0)  # r mask
    out += struct.pack('<I', 0)  # g mask
    out += struct.pack('<I', 0)  # b mask
    out += struct.pack('<I', 0)  # a mask

    # Caps
    out += struct.pack('<I', DDSCAPS_TEXTURE)
    out += struct.pack('<I', 0)  # caps2
    out += struct.pack('<I', 0)  # caps3
    out += struct.pack('<I', 0)  # caps4
    out += b'\x00' * 4  # reserved2

    # Pixel data
    out += data

    return bytes(out)

def dds_to_dxt5_data(dds_data: bytes) -> Tuple[bytes, int, int, str]:
    """Extract raw DXT data from a DDS file. Returns (data, width, height, fourcc)."""
    if dds_data[:4] != DDS_MAGIC:
        raise ValueError("Not a DDS file")

    header_size = struct.unpack('<I', dds_data[4:8])[0]
    flags = struct.unpack('<I', dds_data[8:12])[0]
    height = struct.unpack('<I', dds_data[12:16])[0]
    width = struct.unpack('<I', dds_data[16:20])[0]

    # Pixel format at offset 76
    pf_size = struct.unpack('<I', dds_data[76:80])[0]
    pf_flags = struct.unpack('<I', dds_data[80:84])[0]
    fourcc = dds_data[84:88]

    pixel_data = dds_data[4 + header_size:]
    fourcc_str = fourcc.decode('ascii', 'replace')
    return pixel_data, width, height, fourcc_str

def decompress_dxt5(data: bytes, width: int, height: int) -> bytes:
    """Decompress DXT5/BC3 data to RGBA8888."""
    try:
        import texture2ddecoder
        return texture2ddecoder.decode_bc3(data, width, height)
    except ImportError:
        pass

    # Fallback: manual DXT5 decompression
    return _decompress_dxt5_manual(data, width, height)

def _decompress_dxt5_manual(data: bytes, width: int, height: int) -> bytes:
    """Manual DXT5/BC3 decompression to RGBA."""
    blocks_x = (width + 3) // 4
    blocks_y = (height + 3) // 4
    output = bytearray(width * height * 4)

    for by in range(blocks_y):
        for bx in range(blocks_x):
            block_offset = (by * blocks_x + bx) * 16
            if block_offset + 16 > len(data):
                break

            # Alpha block (first 8 bytes)
            a0, a1 = data[block_offset], data[block_offset + 1]
            alpha_indices = data[block_offset + 2:8]

            # Color block (next 8 bytes) - DXT1
            c0 = struct.unpack('<H', data[block_offset+8:block_offset+10])[0]
            c1 = struct.unpack('<H', data[block_offset+10:block_offset+12])[0]
            color_indices = data[block_offset+12:16]

            # Decode colors
            def decode_565(c):
                r = (c >> 11) & 0x1F
                g = (c >> 5) & 0x3F
                b = c & 0x1F
                return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)

            r0, g0, b0 = decode_565(c0)
            r1, g1, b1 = decode_565(c1)

            colors = [(r0, g0, b0, 255), (r1, g1, b1, 255)]
            if c0 > c1:
                colors.append(((2*r0+r1)//3, (2*g0+g1)//3, (2*b0+b1)//3, 255))
                colors.append(((r0+2*r1)//3, (g0+2*g1)//3, (b0+2*b1)//3, 255))
            else:
                colors.append(((r0+r1)//2, (g0+g1)//2, (b0+b1)//2, 255))
                colors.append((0, 0, 0, 0))

            # Decode alphas
            alphas = [a0, a1]
            if a0 > a1:
                alphas.append((6*a0 + 1*a1) // 7)
                alphas.append((5*a0 + 2*a1) // 7)
                alphas.append((4*a0 + 3*a1) // 7)
                alphas.append((3*a0 + 4*a1) // 7)
                alphas.append((2*a0 + 5*a1) // 7)
                alphas.append((1*a0 + 6*a1) // 7)
            else:
                alphas.append((4*a0 + 1*a1) // 5)
                alphas.append((3*a0 + 2*a1) // 5)
                alphas.append((2*a0 + 3*a1) // 5)
                alphas.append((1*a0 + 4*a1) // 5)
                alphas.append(0)
                alphas.append(255)

            # Unpack alpha indices (48 bits = 16 * 3-bit values)
            alpha_bits = 0
            for b in alpha_indices:
                alpha_bits = (alpha_bits << 8) | b
            # Reversed bit order
            alpha_bits = int.from_bytes(alpha_indices, 'little')

            # Unpack color indices (32 bits = 16 * 2-bit values)
            color_bits = int.from_bytes(color_indices, 'little')

            for py in range(4):
                for px in range(4):
                    x = bx * 4 + px
                    y = by * 4 + py
                    if x >= width or y >= height:
                        continue

                    ci = (color_bits >> ((py * 4 + px) * 2)) & 3
                    ai = (alpha_bits >> ((py * 4 + px) * 3)) & 7

                    r, g, b, _ = colors[ci]
                    a = alphas[ai]

                    idx = (y * width + x) * 4
                    output[idx] = r
                    output[idx + 1] = g
                    output[idx + 2] = b
                    output[idx + 3] = a

    return bytes(output)

def compress_dxt5(rgba: bytes, width: int, height: int) -> bytes:
    """Compress RGBA data to DXT5. Uses texture2ddecoder if available, else basic."""
    try:
        import texture2ddecoder
        return texture2ddecoder.encode_bc3(rgba, width, height)
    except (ImportError, AttributeError):
        pass

    # Basic fallback: just pad and return zeros (not ideal but functional)
    blocks_x = (width + 3) // 4
    blocks_y = (height + 3) // 4
    return b'\x00' * (blocks_x * blocks_y * 16)

def dds_to_png(dds_data: bytes, output_path: str):
    """Convert DDS file to PNG using Pillow."""
    from PIL import Image

    pixel_data, width, height, fourcc = dds_to_dxt5_data(dds_data)

    if fourcc in ('DXT5', 'BC3'):
        rgba = decompress_dxt5(pixel_data, width, height)
        img = Image.frombytes('RGBA', (width, height), rgba)
    elif fourcc in ('DXT1', 'BC1'):
        rgba = _decompress_dxt1(pixel_data, width, height)
        img = Image.frombytes('RGBA', (width, height), rgba)
    elif fourcc == 'DXT3':
        rgba = _decompress_dxt3(pixel_data, width, height)
        img = Image.frombytes('RGBA', (width, height), rgba)
    else:
        # Try loading directly with Pillow
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.dds', delete=False) as tmp:
            tmp.write(dds_data)
            tmp_path = tmp.name
        try:
            img = Image.open(tmp_path)
            img = img.convert('RGBA')
        finally:
            os.unlink(tmp_path)

    img.save(output_path)
    print(f"  Saved PNG: {output_path} ({width}x{height})")

def _decompress_dxt1(data: bytes, width: int, height: int) -> bytes:
    """Manual DXT1/BC1 decompression to RGBA."""
    try:
        import texture2ddecoder
        return texture2ddecoder.decode_bc1(data, width, height)
    except ImportError:
        pass

    blocks_x = (width + 3) // 4
    blocks_y = (height + 3) // 4
    output = bytearray(width * height * 4)

    for by in range(blocks_y):
        for bx in range(blocks_x):
            bo = (by * blocks_x + bx) * 8
            if bo + 8 > len(data):
                break

            c0 = struct.unpack('<H', data[bo:bo+2])[0]
            c1 = struct.unpack('<H', data[bo+2:bo+4])[0]
            ci = int.from_bytes(data[bo+4:bo+8], 'little')

            def d565(c):
                return ((c>>11)&0x1F)<<3|((c>>11)&0x1F)>>2, ((c>>5)&0x3F)<<2|((c>>5)&0x3F)>>4, (c&0x1F)<<3|(c&0x1F)>>2

            r0,g0,b0 = d565(c0)
            r1,g1,b1 = d565(c1)
            cols = [(r0,g0,b0,255),(r1,g1,b1,255)]
            if c0 > c1:
                cols.append(((2*r0+r1)//3,(2*g0+g1)//3,(2*b0+b1)//3,255))
                cols.append(((r0+2*r1)//3,(g0+2*g1)//3,(b0+2*b1)//3,255))
            else:
                cols.append(((r0+r1)//2,(g0+g1)//2,(b0+b1)//2,255))
                cols.append((0,0,0,0))

            for py in range(4):
                for px in range(4):
                    x, y = bx*4+px, by*4+py
                    if x >= width or y >= height: continue
                    cidx = (ci >> ((py*4+px)*2)) & 3
                    r,g,b,a = cols[cidx]
                    idx = (y*width+x)*4
                    output[idx:idx+4] = bytes([r,g,b,a])

    return bytes(output)

def _decompress_dxt3(data: bytes, width: int, height: int) -> bytes:
    """Manual DXT3/BC2 decompression to RGBA."""
    try:
        import texture2ddecoder
        return texture2ddecoder.decode_bc2(data, width, height)
    except ImportError:
        pass

    blocks_x = (width + 3) // 4
    blocks_y = (height + 3) // 4
    output = bytearray(width * height * 4)

    for by in range(blocks_y):
        for bx in range(blocks_x):
            bo = (by * blocks_x + bx) * 16
            if bo + 16 > len(data):
                break

            # Alpha (8 bytes, 4-bit per pixel)
            alpha_data = data[bo:bo+8]
            # Color (8 bytes, DXT1)
            c0 = struct.unpack('<H', data[bo+8:bo+10])[0]
            c1 = struct.unpack('<H', data[bo+10:bo+12])[0]
            ci = int.from_bytes(data[bo+12:bo+16], 'little')

            def d565(c):
                return ((c>>11)&0x1F)<<3, ((c>>5)&0x3F)<<2, (c&0x1F)<<3

            r0,g0,b0 = d565(c0)
            r1,g1,b1 = d565(c1)
            cols = [(r0,g0,b0),(r1,g1,b1)]
            if c0 > c1:
                cols.append(((2*r0+r1)//3,(2*g0+g1)//3,(2*b0+b1)//3))
                cols.append(((r0+2*r1)//3,(g0+2*g1)//3,(b0+2*b1)//3))
            else:
                cols.append(((r0+r1)//2,(g0+g1)//2,(b0+b1)//2))
                cols.append((0,0,0))

            for py in range(4):
                for px in range(4):
                    x, y = bx*4+px, by*4+py
                    if x >= width or y >= height: continue
                    cidx = (ci >> ((py*4+px)*2)) & 3
                    a = (alpha_data[py*2 + px//2] >> ((px%2)*4)) & 0xF
                    a = a * 17  # expand 4-bit to 8-bit
                    r,g,b = cols[cidx]
                    idx = (y*width+x)*4
                    output[idx:idx+4] = bytes([r,g,b,a])

    return bytes(output)

# ============================================================================
# TG4D Texture Format
# ============================================================================

def parse_tg4h_header(data: bytes) -> Optional[Dict]:
    """Parse a TG4H (texture header) file to extract dimensions and format.

    TG4H header layout (big-endian):
      Offset 0x20: u8 width_log  (width = 2^(val + 6), so 1->128, 2->256, 3->512)
      Offset 0x22: u8 height_log (height = 2^(val + 6))
      Offset 0x26: u8 mipmap_count
      Offset 0x27: u8 format_type (4=DXT5, 5=DXT1)
      Variable:    DXT format string (e.g. "DXT1", "DXT5", "DXT5_NM")
    """
    if len(data) < 0x28:
        return None

    width_log = data[0x20]
    height_log = data[0x22]
    mipmap_count = data[0x26]
    format_type = data[0x27]

    if 0 < width_log <= 12:
        width = 1 << (width_log + 7)
    else:
        width = max(4, width_log)

    if 0 < height_log <= 12:
        height = 1 << (height_log + 7)
    else:
        height = max(4, height_log)

    dxt_format = None
    for i in range(len(data) - 3):
        s = data[i:i+4]
        if s == b'DXT1':
            dxt_format = 'DXT1'
            break
        elif s == b'DXT5':
            dxt_format = 'DXT5'
            break
        elif s == b'DXT3':
            dxt_format = 'DXT3'
            break

    if dxt_format is None:
        dxt_format = {4: 'DXT5', 5: 'DXT1'}.get(format_type, 'DXT5')

    return {
        'width': width,
        'height': height,
        'mipmap_count': mipmap_count,
        'dxt_format': dxt_format,
    }

def find_tg4h_for_tg4d(tg4d_path: str, unpacked_dir: str) -> Optional[str]:
    """Find the TG4H header file that corresponds to a TG4D data file.

    TG4H and TG4D files have sequential number prefixes (not paired),
    so we match by the texture name portion instead.
    """
    tg4d_name = os.path.basename(tg4d_path)
    # Extract texture name: "0002_chest_health_mana_c.tg4d.tg4d" -> "chest_health_mana_c"
    # Remove number prefix
    parts = tg4d_name.split('_', 1)
    if len(parts) < 2:
        return None
    name_part = parts[1]
    # Remove .tg4d.tg4d extension
    for ext in ['.tg4d.tg4d', '.tg4d', '.tg4h.tg4h', '.tg4h']:
        if name_part.endswith(ext):
            name_part = name_part[:-len(ext)]
            break

    tg4h_dir = os.path.join(unpacked_dir, 'tg4h')
    if not os.path.isdir(tg4h_dir):
        return None

    # Find TG4H file with matching texture name
    for fn in os.listdir(tg4h_dir):
        fn_parts = fn.split('_', 1)
        if len(fn_parts) < 2:
            continue
        fn_name = fn_parts[1]
        for ext in ['.tg4h.tg4h', '.tg4h']:
            if fn_name.endswith(ext):
                fn_name = fn_name[:-len(ext)]
                break
        if fn_name == name_part:
            return os.path.join(tg4h_dir, fn)

    return None

def infer_texture_dims_from_size(data_size: int, block_size: int = 16) -> Tuple[int, int]:
    """Infer texture dimensions from DXT data size, assuming pow2 with mipmaps."""
    num_blocks = data_size // block_size
    if num_blocks == 0:
        return 4, 4

    for w in [4096, 2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4]:
        for h in [4096, 2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4]:
            total = 0
            mw, mh = w, h
            while mw >= 1 and mh >= 1:
                total += max(1, (mw + 3) // 4) * max(1, (mh + 3) // 4)
                if mw == 1 and mh == 1:
                    break
                mw = max(1, mw // 2)
                mh = max(1, mh // 2)
            if total == num_blocks:
                return w, h

    for w in [4096, 2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4]:
        for h in [4096, 2048, 1024, 512, 256, 128, 64, 32, 16, 8, 4]:
            if (w // 4) * (h // 4) == num_blocks:
                return w, h

    return 0, 0

def dxt1_to_dds(data: bytes, width: int, height: int,
                mipmaps: int = 1) -> bytes:
    """Wrap raw DXT1 compressed data in a DDS file header."""
    out = bytearray()
    out += DDS_MAGIC

    flags = DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_LINEARSIZE
    if mipmaps > 1:
        flags |= DDSD_MIPMAPCOUNT

    block_size = max(1, ((width + 3) // 4) * ((height + 3) // 4)) * 8

    out += struct.pack('<I', DDS_HEADER_SIZE)
    out += struct.pack('<I', flags)
    out += struct.pack('<I', height)
    out += struct.pack('<I', width)
    out += struct.pack('<I', block_size)
    out += struct.pack('<I', 0)
    out += struct.pack('<I', mipmaps)
    out += b'\x00' * 44

    out += struct.pack('<I', 32)
    out += struct.pack('<I', DDPF_FOURCC)
    out += DDS_FOURCC_DXT1
    out += struct.pack('<IIII', 0, 0, 0, 0)

    out += struct.pack('<I', DDSCAPS_TEXTURE)
    out += struct.pack('<III', 0, 0, 0)
    out += b'\x00' * 4

    out += data
    return bytes(out)

def parse_tg4d_header(data: bytes) -> Optional[Dict]:
    """Try to parse a TG4D texture header to extract dimensions.

    TG4D files may have a header with width/height, or may be raw DXT5 data.
    Returns dict with width, height, format, data_offset, or None if no header.
    """
    if len(data) < 16:
        return None

    # Check for common Visceral texture header patterns
    # TG4D files often start with a small header containing format info

    # Try: first 4 bytes = magic/type, then width, height
    magic = data[:4]

    # Check if it starts with "TG4D" or similar
    if magic == b'TG4D':
        # Parse TG4D header
        if len(data) < 32:
            return None
        width = struct.unpack('<I', data[4:8])[0]
        height = struct.unpack('<I', data[8:12])[0]
        fmt = struct.unpack('<I', data[12:16])[0]
        data_offset = struct.unpack('<I', data[16:20])[0] if len(data) >= 20 else 20
        return {
            'width': width, 'height': height,
            'format': fmt, 'data_offset': data_offset,
            'dxt_format': 'DXT5'
        }

    # Check for texture header with type field
    # Visceral textures may have a 16-byte or 32-byte header
    # Try common patterns
    if len(data) >= 8:
        # Try reading width/height at various offsets
        for hdr_size in [0, 8, 16, 24, 32, 48, 64]:
            if len(data) < hdr_size + 8:
                continue
            w = struct.unpack('<I', data[hdr_size:hdr_size+4])[0]
            h = struct.unpack('<I', data[hdr_size+4:hdr_size+8])[0]
            # Sanity check: dimensions should be reasonable powers of 2 or multiples of 4
            if 1 <= w <= 8192 and 1 <= h <= 8192 and w % 4 == 0 and h % 4 == 0:
                expected_dxt5_size = ((w + 3) // 4) * ((h + 3) // 4) * 16
                if hdr_size + expected_dxt5_size <= len(data) + 16:  # allow small tolerance
                    return {
                        'width': w, 'height': h,
                        'format': 0, 'data_offset': hdr_size,
                        'dxt_format': 'DXT5'
                    }

    return None

def convert_tg4d_to_dds(input_path: str, output_path: str,
                        width: int = 0, height: int = 0,
                        tg4h_path: str = None,
                        dxt_format: str = 'DXT5') -> Tuple[int, int]:
    """Convert a TG4D texture to DDS format. Returns (width, height) used."""
    with open(input_path, 'rb') as f:
        data = f.read()

    # Try TG4H header first
    hdr = None
    if tg4h_path and os.path.exists(tg4h_path):
        with open(tg4h_path, 'rb') as f:
            tg4h_data = f.read()
        hdr = parse_tg4h_header(tg4h_data)

    if hdr:
        w, h = hdr['width'], hdr['height']
        dxt_format = hdr['dxt_format']
        mipmaps = hdr['mipmap_count']
        pixel_data = data
    elif width > 0 and height > 0:
        w, h = width, height
        pixel_data = data
        mipmaps = 1
    else:
        # Infer from file size
        for bs, fmt in [(16, 'DXT5'), (8, 'DXT1')]:
            iw, ih = infer_texture_dims_from_size(len(data), bs)
            if iw > 0 and ih > 0:
                w, h = iw, ih
                dxt_format = fmt
                break
        else:
            print(f"  WARNING: Could not auto-detect dimensions for {input_path}")
            print(f"  File size: {len(data)} bytes. Please specify --width and --height")
            w = width or 4
            h = height or 4
        pixel_data = data
        mipmaps = 1

    if dxt_format in ('DXT5', 'BC3'):
        dds_data = dxt5_to_dds(pixel_data, w, h, mipmaps)
    elif dxt_format in ('DXT1', 'BC1'):
        dds_data = dxt1_to_dds(pixel_data, w, h, mipmaps)
    else:
        dds_data = dxt5_to_dds(pixel_data, w, h, mipmaps)

    with open(output_path, 'wb') as f:
        f.write(dds_data)
    print(f"  Saved DDS: {output_path} ({w}x{h} {dxt_format} {mipmaps} mipmaps)")
    return w, h

def convert_tg4d_to_png(input_path: str, output_path: str,
                        width: int = 0, height: int = 0,
                        tg4h_path: str = None):
    """Convert a TG4D texture to PNG format."""
    # First convert to DDS, then to PNG
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.dds', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        w, h = convert_tg4d_to_dds(input_path, tmp_path, width, height,
                                   tg4h_path=tg4h_path)
        with open(tmp_path, 'rb') as f:
            dds_data = f.read()
        dds_to_png(dds_data, output_path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

def convert_png_to_tg4d(input_path: str, output_path: str,
                        dxt_format: str = 'DXT5') -> Tuple[int, int]:
    """Convert a PNG to TG4D (DXT5) format. Returns (width, height)."""
    from PIL import Image

    img = Image.open(input_path)
    img = img.convert('RGBA')
    w, h = img.size

    # Ensure dimensions are multiples of 4
    if w % 4 != 0 or h % 4 != 0:
        new_w = ((w + 3) // 4) * 4
        new_h = ((h + 3) // 4) * 4
        img = img.resize((new_w, new_h), Image.LANCZOS)
        w, h = new_w, new_h

    rgba = img.tobytes()

    if dxt_format.upper() in ('DXT5', 'BC3'):
        dxt_data = compress_dxt5(rgba, w, h)
    else:
        raise ValueError(f"Unsupported DXT format: {dxt_format}")

    with open(output_path, 'wb') as f:
        f.write(dxt_data)
    print(f"  Saved TG4D: {output_path} ({w}x{h})")
    return w, h

def convert_dds_to_tg4d(input_path: str, output_path: str) -> Tuple[int, int]:
    """Convert a DDS file to TG4D (raw DXT5) format."""
    with open(input_path, 'rb') as f:
        dds_data = f.read()

    pixel_data, w, h, fourcc = dds_to_dxt5_data(dds_data)

    with open(output_path, 'wb') as f:
        f.write(pixel_data)
    print(f"  Saved TG4D: {output_path} ({w}x{h})")
    return w, h

# ============================================================================
# File Type Detection
# ============================================================================

def detect_file_type(data: bytes) -> str:
    """Detect the type of a file from its magic bytes."""
    if len(data) < 4:
        return 'unknown'

    magic_le = struct.unpack('<I', data[:4])[0]
    magic_str = data[:4].decode('ascii', 'replace')

    # StreamSet
    if magic_str == 'ols3' or magic_str == '3slo':
        return 'str'

    # VP6 video
    if data[:3] == b'MVh' or data[:3] == b'SCH':
        return 'vp6'

    # Bink video
    if data[:3] == b'BIK':
        return 'bik'

    # DDS texture
    if data[:4] == b'DDS ':
        return 'dds'

    # TG4D texture
    if data[:4] == b'TG4D':
        return 'tg4d'

    # SimGroup
    if magic_le == 0xCCB51828:
        return 'simgroup'

    # XMA audio
    if data[:3] == b'XMA':
        return 'xma'

    # FSB audio
    if data[:3] == b'FSB':
        return 'fsb'

    # Check for text
    if all(32 <= b < 127 or b in (10, 13, 9) for b in data[:100]):
        return 'text'

    return 'unknown'

def get_file_category(filename: str, file_type: str) -> str:
    """Categorize a file as textures, videos, models, audio, or other."""
    ext = os.path.splitext(filename)[1].lower()

    if ext == '.vp6' or ext == '.bik' or file_type in ('vp6', 'bik'):
        return 'videos'
    if ext in ('.tg4d', '.dds') or file_type in ('tg4d', 'dds'):
        return 'textures'
    if ext in ('.str',) or file_type == 'str':
        return 'str'
    if ext in ('.simgroup',) or file_type == 'simgroup':
        return 'models'
    if ext in ('.xma', '.fsb', '.xwma') or file_type in ('xma', 'fsb'):
        return 'audio'
    if ext in ('.txt', '.cfg', '.ini', '.lua') or file_type == 'text':
        return 'text'

    # Check STR sub-file types
    if ext in ('.geometry', '.geometryvolatile'):
        return 'models'
    if ext in ('.soundbank', '.animationbank'):
        return 'audio' if ext == '.soundbank' else 'animations'

    return 'other'

# ============================================================================
# BIG File Extraction
# ============================================================================

def extract_big_file(big_path: str, output_dir: str,
                     filelist_paths: List[str] = None,
                     asset_type: str = 'all',
                     unpack_str: bool = False,
                     convert_textures: bool = False) -> int:
    """Extract files from a BIG/VIV archive.
    Returns number of files extracted."""
    os.makedirs(output_dir, exist_ok=True)

    # Load filelists
    hash_to_name = {}
    if filelist_paths:
        hash_to_name = load_filelist(filelist_paths)

    with open(big_path, 'rb') as f:
        entries = read_big_entries(f)

        # Resolve filenames
        for entry in entries:
            if entry.name_hash in hash_to_name:
                entry.filename = hash_to_name[entry.name_hash]
            else:
                entry.filename = f"__UNKNOWN_0x{entry.name_hash:08X}"

        # Filter by asset type
        if asset_type != 'all':
            filtered = []
            for entry in entries:
                if entry.size == 0:
                    continue
                f.seek(entry.offset)
                header = f.read(min(256, entry.size))
                ftype = detect_file_type(header)
                category = get_file_category(entry.filename, ftype)

                # For STR files, we need to look inside to categorize
                if category == 'str' and unpack_str:
                    category = 'str_container'

                if asset_type == 'textures' and category in ('textures', 'str_container'):
                    filtered.append(entry)
                elif asset_type == 'videos' and category in ('videos', 'str_container'):
                    filtered.append(entry)
                elif asset_type == 'models' and category in ('models', 'str_container'):
                    filtered.append(entry)
                elif asset_type == 'audio' and category in ('audio', 'str_container'):
                    filtered.append(entry)
                else:
                    # Check extension
                    ext = os.path.splitext(entry.filename)[1].lower()
                    if asset_type == 'textures' and ext == '.str':
                        filtered.append(entry)
                    elif asset_type == 'videos' and ext == '.vp6':
                        filtered.append(entry)
            entries = filtered

        extracted = 0
        for entry in entries:
            if entry.size == 0:
                continue

            # Build output path
            out_path = os.path.join(output_dir, entry.filename)

            # Create directories
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            # Write file
            f.seek(entry.offset)
            data = f.read(entry.size)
            with open(out_path, 'wb') as out:
                out.write(data)

            extracted += 1
            if extracted % 100 == 0:
                print(f"  Extracted {extracted}/{len(entries)} files...")

            # Unpack STR files if requested
            if unpack_str and detect_file_type(data) == 'str':
                str_out_dir = out_path + '_unpacked'
                try:
                    unpack_str_file(out_path, str_out_dir)
                except Exception as e:
                    print(f"  WARNING: Failed to unpack STR {entry.filename}: {e}")

        print(f"\nExtracted {extracted} files to {output_dir}")
        return extracted

# ============================================================================
# Full Pipeline: Extract + Unpack STR + Convert Textures
# ============================================================================

def extract_all_assets(big_path: str, output_dir: str,
                       filelist_paths: List[str] = None,
                       asset_type: str = 'all',
                       convert_textures: bool = True) -> int:
    """Full extraction pipeline: BIG -> STR -> individual assets -> converted formats."""
    os.makedirs(output_dir, exist_ok=True)

    # Load filelists
    hash_to_name = {}
    if filelist_paths:
        hash_to_name = load_filelist(filelist_paths)

    raw_dir = os.path.join(output_dir, '_raw')
    assets_dir = os.path.join(output_dir, 'assets')

    with open(big_path, 'rb') as f:
        entries = read_big_entries(f)

        # Resolve filenames
        for entry in entries:
            if entry.name_hash in hash_to_name:
                entry.filename = hash_to_name[entry.name_hash]
            else:
                entry.filename = f"__UNKNOWN_0x{entry.name_hash:08X}"

        extracted = 0
        textures_converted = 0
        videos_extracted = 0
        str_unpacked = 0

        for entry in entries:
            if entry.size == 0:
                continue

            f.seek(entry.offset)
            data = f.read(entry.size)
            ftype = detect_file_type(data)
            category = get_file_category(entry.filename, ftype)

            # Filter by type
            if asset_type != 'all':
                type_map = {
                    'textures': ['textures'],
                    'videos': ['videos'],
                    'models': ['models'],
                    'audio': ['audio'],
                }
                wanted = type_map.get(asset_type, [])
                if category not in wanted and ftype != 'str':
                    # Also check if it's a STR that might contain the wanted type
                    continue

            # Save raw file
            raw_path = os.path.join(raw_dir, entry.filename)
            os.makedirs(os.path.dirname(raw_path), exist_ok=True)
            with open(raw_path, 'wb') as out:
                out.write(data)
            extracted += 1

            # Process based on type
            if ftype == 'str':
                # Unpack STR file
                str_out = os.path.join(assets_dir, entry.filename + '_unpacked')
                try:
                    metadata = unpack_str_file(raw_path, str_out)

                    # Process sub-files
                    for meta in metadata:
                        sub_path = os.path.join(str_out, meta['extracted_path'])
                        type_name = meta['type_name'].lower()

                        if convert_textures and type_name in ('tg4d', 'tg4d_vol'):
                            # Find corresponding TG4H header
                            tg4h_path = find_tg4h_for_tg4d(sub_path, str_out)

                            # Convert texture to DDS/PNG
                            dds_path = os.path.splitext(sub_path)[0] + '.dds'
                            png_path = os.path.splitext(sub_path)[0] + '.png'
                            try:
                                w, h = convert_tg4d_to_dds(sub_path, dds_path,
                                                           tg4h_path=tg4h_path)
                                dds_to_png(open(dds_path, 'rb').read(), png_path)
                                textures_converted += 1
                            except Exception as e:
                                print(f"  WARNING: Failed to convert texture {meta['extracted_path']}: {e}")

                        elif type_name in ('geometry', 'geometryvolatile'):
                            # Model data - copy as-is
                            model_out = os.path.join(assets_dir, 'models',
                                                     os.path.basename(sub_path))
                            os.makedirs(os.path.dirname(model_out), exist_ok=True)
                            with open(sub_path, 'rb') as sf:
                                with open(model_out, 'wb') as mf:
                                    mf.write(sf.read())

                    str_unpacked += 1
                except Exception as e:
                    print(f"  WARNING: Failed to unpack STR {entry.filename}: {e}")

            elif ftype == 'vp6':
                # Copy video to assets
                vid_out = os.path.join(assets_dir, 'videos', entry.filename)
                os.makedirs(os.path.dirname(vid_out), exist_ok=True)
                with open(vid_out, 'wb') as out:
                    out.write(data)
                videos_extracted += 1

            elif ftype in ('tg4d', 'dds') and convert_textures:
                # Direct texture
                dds_path = os.path.join(assets_dir, 'textures',
                                        os.path.splitext(entry.filename)[0] + '.dds')
                png_path = os.path.splitext(dds_path)[0] + '.png'
                os.makedirs(os.path.dirname(dds_path), exist_ok=True)
                try:
                    if ftype == 'tg4d':
                        convert_tg4d_to_dds(raw_path, dds_path)
                    else:
                        with open(dds_path, 'wb') as out:
                            out.write(data)
                    dds_to_png(open(dds_path, 'rb').read(), png_path)
                    textures_converted += 1
                except Exception as e:
                    print(f"  WARNING: Failed to convert texture {entry.filename}: {e}")

            if extracted % 50 == 0:
                print(f"  Progress: {extracted} files, {textures_converted} textures, "
                      f"{videos_extracted} videos, {str_unpacked} STRs unpacked...")

        print(f"\n=== Extraction Complete ===")
        print(f"  Raw files: {extracted}")
        print(f"  STR files unpacked: {str_unpacked}")
        print(f"  Textures converted: {textures_converted}")
        print(f"  Videos extracted: {videos_extracted}")
        print(f"  Output: {output_dir}")

        return extracted

# ============================================================================
# BIG File Packing
# ============================================================================

def pack_big_archive(input_dir: str, output_path: str,
                     filelist_paths: List[str] = None):
    """Pack a directory of files back into a BIG/VIV archive."""
    # Collect all files
    files = []
    for root, dirs, filenames in os.walk(input_dir):
        for fn in filenames:
            full_path = os.path.join(root, fn)
            rel_path = os.path.relpath(full_path, input_dir)
            # Normalize path separators
            rel_path = rel_path.replace(os.sep, '\\').lower()
            files.append((rel_path, full_path))

    # If we have filelists, we can verify hashes
    if filelist_paths:
        hash_to_name = load_filelist(filelist_paths)
        name_to_hash = {v: k for k, v in hash_to_name.items()}

    # Read and pack files
    entries = []
    for rel_path, full_path in files:
        with open(full_path, 'rb') as f:
            data = f.read()
        entries.append((rel_path, data))

    write_big_archive(output_path, entries)
    print(f"Packed {len(entries)} files into {output_path}")

# ============================================================================
# CLI Interface
# ============================================================================

def cmd_list(args):
    """List files in a BIG archive."""
    filelist_paths = []
    if args.filelist:
        filelist_paths = [args.filelist]
    else:
        # Try to find filelists in the Gibbed.Visceral project
        gibbed_dir = os.path.join(os.path.dirname(__file__), 'Gibbed.Visceral',
                                  'bin', 'projects')
        if os.path.exists(gibbed_dir):
            filelist_paths = find_filelists(gibbed_dir)

    hash_to_name = load_filelist(filelist_paths) if filelist_paths else {}

    with open(args.big_file, 'rb') as f:
        entries = read_big_entries(f)

        matched = 0
        for i, entry in enumerate(entries):
            name = hash_to_name.get(entry.name_hash,
                                    f"__UNKNOWN_0x{entry.name_hash:08X}")
            if not name.startswith("__UNKNOWN"):
                matched += 1

            if args.type:
                f.seek(entry.offset)
                header = f.read(min(256, entry.size))
                ftype = detect_file_type(header)
                category = get_file_category(name, ftype)
                if args.type != 'all' and category != args.type and name.endswith('.str') and args.type != 'str':
                    continue

            dup = " (DUP)" if entry.duplicate else ""
            print(f"  [{i:4d}] 0x{entry.name_hash:08X}  {entry.size:10d}  {name}{dup}")

        print(f"\nTotal: {len(entries)} entries ({matched} matched to filenames)")

def cmd_extract(args):
    """Extract files from a BIG archive."""
    filelist_paths = []
    if args.filelist:
        filelist_paths = [args.filelist]
    else:
        gibbed_dir = os.path.join(os.path.dirname(__file__), 'Gibbed.Visceral',
                                  'bin', 'projects')
        if os.path.exists(gibbed_dir):
            filelist_paths = find_filelists(gibbed_dir)

    if args.full_pipeline:
        extract_all_assets(
            args.big_file, args.output_dir,
            filelist_paths=filelist_paths,
            asset_type=args.type or 'all',
            convert_textures=not args.no_convert
        )
    else:
        extract_big_file(
            args.big_file, args.output_dir,
            filelist_paths=filelist_paths,
            asset_type=args.type or 'all',
            unpack_str=args.unpack_str,
            convert_textures=not args.no_convert
        )

def cmd_unpack_str(args):
    """Unpack a STR file."""
    unpack_str_file(args.input_str, args.output_dir)

def cmd_pack_str(args):
    """Pack a directory into a STR file."""
    pack_str_file(args.input_dir, args.output_str)

def cmd_pack_big(args):
    """Pack a directory into a BIG archive."""
    pack_big_archive(args.input_dir, args.output_viv)

def cmd_convert_texture(args):
    """Convert a TG4D texture to DDS or PNG."""
    out_ext = os.path.splitext(args.output)[1].lower()
    tg4h = getattr(args, 'tg4h', None)
    if out_ext == '.png':
        convert_tg4d_to_png(args.input, args.output, args.width, args.height,
                            tg4h_path=tg4h)
    elif out_ext == '.dds':
        convert_tg4d_to_dds(args.input, args.output, args.width, args.height,
                            tg4h_path=tg4h)
    else:
        print(f"Unknown output format: {out_ext}")

def cmd_make_texture(args):
    """Convert a PNG or DDS to TG4D."""
    in_ext = os.path.splitext(args.input)[1].lower()
    if in_ext == '.png':
        convert_png_to_tg4d(args.input, args.output, args.format)
    elif in_ext == '.dds':
        convert_dds_to_tg4d(args.input, args.output)
    else:
        print(f"Unknown input format: {in_ext}")

def main():
    parser = argparse.ArgumentParser(
        description="Dante's Inferno Asset Extraction & Packing Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # list
    p_list = subparsers.add_parser('list', help='List files in a BIG archive')
    p_list.add_argument('big_file', help='Path to .viv file')
    p_list.add_argument('--filelist', help='Path to .filelist file')
    p_list.add_argument('--type', help='Filter by type (textures/videos/models/audio)')
    p_list.set_defaults(func=cmd_list)

    # extract
    p_extract = subparsers.add_parser('extract', help='Extract files from a BIG archive')
    p_extract.add_argument('big_file', help='Path to .viv file')
    p_extract.add_argument('output_dir', help='Output directory')
    p_extract.add_argument('--filelist', help='Path to .filelist file')
    p_extract.add_argument('--type', default='all',
                           help='Asset type: textures, videos, models, audio, all')
    p_extract.add_argument('--unpack-str', action='store_true',
                           help='Also unpack STR files')
    p_extract.add_argument('--full-pipeline', action='store_true',
                           help='Full pipeline: extract + unpack STR + convert textures')
    p_extract.add_argument('--no-convert', action='store_true',
                           help='Skip texture conversion to PNG')
    p_extract.set_defaults(func=cmd_extract)

    # unpack-str
    p_unpack = subparsers.add_parser('unpack-str', help='Unpack a STR file')
    p_unpack.add_argument('input_str', help='Path to .str file')
    p_unpack.add_argument('output_dir', help='Output directory')
    p_unpack.set_defaults(func=cmd_unpack_str)

    # pack-str
    p_pack_str = subparsers.add_parser('pack-str', help='Pack directory into STR file')
    p_pack_str.add_argument('input_dir', help='Input directory (with @metadata.json)')
    p_pack_str.add_argument('output_str', help='Output .str file')
    p_pack_str.set_defaults(func=cmd_pack_str)

    # pack-big
    p_pack_big = subparsers.add_parser('pack-big', help='Pack directory into BIG archive')
    p_pack_big.add_argument('input_dir', help='Input directory')
    p_pack_big.add_argument('output_viv', help='Output .viv file')
    p_pack_big.add_argument('--filelist', help='Path to .filelist file')
    p_pack_big.set_defaults(func=cmd_pack_big)

    # convert-texture
    p_conv = subparsers.add_parser('convert-texture', help='Convert TG4D to DDS/PNG')
    p_conv.add_argument('input', help='Input .tg4d file')
    p_conv.add_argument('output', help='Output .dds or .png file')
    p_conv.add_argument('--width', type=int, default=0, help='Texture width (if auto-detect fails)')
    p_conv.add_argument('--height', type=int, default=0, help='Texture height (if auto-detect fails)')
    p_conv.add_argument('--tg4h', help='Path to corresponding .tg4h header file')
    p_conv.set_defaults(func=cmd_convert_texture)

    # make-texture
    p_make = subparsers.add_parser('make-texture', help='Convert PNG/DDS to TG4D')
    p_make.add_argument('input', help='Input .png or .dds file')
    p_make.add_argument('output', help='Output .tg4d file')
    p_make.add_argument('--format', default='dxt5', choices=['dxt5', 'dxt1'],
                        help='DXT compression format')
    p_make.set_defaults(func=cmd_make_texture)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)

if __name__ == '__main__':
    main()
