#!/usr/bin/env python3
"""
Scan a default.xex for all potential indirect call targets (function pointers
stored in data sections) and cross-reference against the ReXGlue function table
to find addresses that codegen missed.

Usage:
    python tools/find_missed_targets.py game/default.xex generated/default/dantes_inferno_init.cpp
"""

import struct
import sys
import re
from pathlib import Path


def parse_xex_sections(xex_path):
    """Parse XEX2 header to find code and data section ranges."""
    with open(xex_path, "rb") as f:
        data = f.read()

    # Verify XEX2 magic
    if data[:4] != b"XEX2":
        print(f"ERROR: Not a valid XEX2 file: {xex_path}")
        sys.exit(1)

    # XEX header fields
    # Offset 0x00: magic "XEX2"
    # Offset 0x04: module_flags
    # Offset 0x08: data_size (size of PE data)
    # Offset 0x0C: rsa_signature_offset
    # Offset 0x10: cert_offset
    # ...

    # The XEX contains a PE binary. We need to find the PE header offset.
    # XEX has a header directory. Let's find the PE data.

    # XEX header: at offset 0x08 is the size of the data section (PE file)
    # The PE data starts after the XEX headers.

    # Search for PE\0\0 signature in the file
    pe_offsets = []
    for i in range(len(data) - 4):
        if data[i:i+4] == b"PE\x00\x00":
            # The PE header is at this offset - 4 (the COFF header starts
            # right after the PE signature, and the offset to PE sig is
            # stored at offset 0x3C from the DOS header)
            # But in XEX, the PE is embedded differently.
            pe_offsets.append(i)

    if not pe_offsets:
        print("ERROR: No PE signature found in XEX")
        sys.exit(1)

    # The XEX stores the PE at a known offset. Let's look for the
    # "Portable Executable" more carefully. In XEX files, the PE data
    # is typically compressed/encrypted, but for our extracted default.xex
    # it may be uncompressed.

    # Actually, let's look for the MZ header (DOS stub) which precedes PE
    mz_offsets = []
    for i in range(len(data) - 2):
        if data[i:i+2] == b"MZ":
            mz_offsets.append(i)

    print(f"Found {len(mz_offsets)} MZ headers at offsets: {[hex(x) for x in mz_offsets[:5]]}")
    print(f"Found {len(pe_offsets)} PE signatures at offsets: {[hex(x) for x in pe_offsets[:5]]}")

    # Try each MZ offset
    for mz_off in mz_offsets:
        if mz_off + 0x40 > len(data):
            continue
        e_lfanew = struct.unpack_from("<I", data, mz_off + 0x3C)[0]
        pe_off = mz_off + e_lfanew
        if pe_off + 4 <= len(data) and data[pe_off:pe_off+4] == b"PE\x00\x00":
            print(f"  Valid PE at MZ offset 0x{mz_off:X}, PE at 0x{pe_off:X}")

            # Parse PE headers
            coff_off = pe_off + 4
            machine, num_sections = struct.unpack_from("<HH", data, coff_off)
            print(f"  Machine: 0x{machine:X}, Sections: {num_sections}")

            # Optional header starts at coff_off + 20
            opt_off = coff_off + 20
            magic = struct.unpack_from("<H", data, opt_off)[0]
            print(f"  Optional header magic: 0x{magic:X} ({'PE32' if magic == 0x10b else 'PE32+' if magic == 0x20b else 'unknown'})")

            if magic == 0x10b:  # PE32
                image_base = struct.unpack_from("<I", data, opt_off + 28)[0]
                size_of_image = struct.unpack_from("<I", data, opt_off + 56)[0]
            elif magic == 0x20b:  # PE32+
                image_base = struct.unpack_from("<Q", data, opt_off + 24)[0]
                size_of_image = struct.unpack_from("<I", data, opt_off + 56)[0]
            else:
                continue

            print(f"  Image base: 0x{image_base:X}, Size: 0x{size_of_image:X}")

            # Section table starts after optional header
            opt_size = struct.unpack_from("<H", data, coff_off + 16)[0]
            section_table_off = opt_off + opt_size

            sections = []
            for i in range(num_sections):
                sec_off = section_table_off + i * 40
                name = data[sec_off:sec_off+8].rstrip(b'\x00').decode('ascii', errors='replace')
                vsize = struct.unpack_from("<I", data, sec_off + 8)[0]
                vaddr = struct.unpack_from("<I", data, sec_off + 12)[0]
                raw_size = struct.unpack_from("<I", data, sec_off + 16)[0]
                raw_off = struct.unpack_from("<I", data, sec_off + 20)[0]
                characteristics = struct.unpack_from("<I", data, sec_off + 36)[0]

                is_code = bool(characteristics & 0x20000000)  # IMAGE_SCN_MEM_EXECUTE
                is_data = bool(characteristics & 0x80000000)  # IMAGE_SCN_MEM_READ
                is_writable = bool(characteristics & 0x80000000)  # IMAGE_SCN_MEM_WRITE

                guest_addr = image_base + vaddr
                print(f"  Section {name:8s}: vaddr=0x{vaddr:08X} vsize=0x{vsize:08X} "
                      f"guest=0x{guest_addr:08X}-0x{guest_addr+vsize:08X} "
                      f"raw=0x{raw_off:08X} rawsz=0x{raw_size:08X} "
                      f"{'CODE' if is_code else 'DATA'}{'W' if is_writable else ''}")

                sections.append({
                    'name': name,
                    'vaddr': vaddr,
                    'vsize': vsize,
                    'guest_addr': guest_addr,
                    'guest_end': guest_addr + vsize,
                    'raw_off': raw_off,
                    'raw_size': raw_size,
                    'is_code': is_code,
                    'characteristics': characteristics,
                })

            return data, mz_off, sections, image_base

    print("ERROR: Could not find valid PE in XEX")
    sys.exit(1)


def find_code_range(sections):
    """Find the overall code address range from sections marked as executable."""
    code_sections = [s for s in sections if s['is_code']]
    if not code_sections:
        # Fallback: use all sections
        code_sections = sections

    min_addr = min(s['guest_addr'] for s in code_sections)
    max_addr = max(s['guest_end'] for s in code_sections)
    return min_addr, max_addr


def scan_data_for_code_refs(data, pe_offset, sections, code_min, code_max):
    """Scan all non-code sections for 4-byte values that fall in the code range."""
    code_refs = set()

    for sec in sections:
        if sec['is_code']:
            # Still scan code sections for internal references (jump tables in code)
            pass

        # Scan the raw data of this section
        raw_off = sec['raw_off']
        raw_size = sec['raw_size']
        if raw_off == 0 or raw_size == 0:
            continue

        sec_data = data[pe_offset + raw_off: pe_offset + raw_off + raw_size]

        # Scan for 4-byte aligned values in code range
        for i in range(0, len(sec_data) - 3, 4):
            val = struct.unpack_from("<I", sec_data, i)[0]
            if code_min <= val < code_max:
                # Check alignment - PPC instructions are 4-byte aligned
                if val % 4 == 0:
                    code_refs.add(val)

        # Also scan unaligned (some data tables may not be aligned)
        for i in range(0, len(sec_data) - 3, 1):
            val = struct.unpack_from("<I", sec_data, i)[0]
            if code_min <= val < code_max and val % 4 == 0:
                code_refs.add(val)

    return code_refs


def extract_registered_functions(init_cpp_path):
    """Extract all registered function addresses from dantes_inferno_init.cpp."""
    registered = set()
    pattern = re.compile(r'\{\s*0x([0-9A-Fa-f]+)\s*,\s*(\w+)\s*\}')

    with open(init_cpp_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            m = pattern.search(line)
            if m:
                addr = int(m.group(1), 16)
                name = m.group(2)
                registered.add((addr, name))

    return registered


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <default.xex> <dantes_inferno_init.cpp>")
        sys.exit(1)

    xex_path = sys.argv[1]
    init_cpp_path = sys.argv[2]

    print(f"=== Parsing XEX: {xex_path} ===")
    data, pe_offset, sections, image_base = parse_xex_sections(xex_path)

    code_min, code_max = find_code_range(sections)
    print(f"\nCode range: 0x{code_min:08X} - 0x{code_max:08X}")

    print(f"\n=== Scanning data sections for code references ===")
    code_refs = scan_data_for_code_refs(data, pe_offset, sections, code_min, code_max)
    print(f"Found {len(code_refs)} potential code addresses in data sections")

    print(f"\n=== Loading registered functions from: {init_cpp_path} ===")
    registered = extract_registered_functions(init_cpp_path)
    registered_addrs = {addr for addr, _ in registered}
    print(f"Found {len(registered_addrs)} registered functions")

    print(f"\n=== Finding missed targets ===")
    missed = sorted(code_refs - registered_addrs)

    if not missed:
        print("All code references are registered! No missed targets.")
        return

    print(f"Found {len(missed)} MISSED indirect call targets:\n")
    print("Copy these into dantes_inferno_manifest.toml under [entrypoint.functions.*]:\n")

    for addr in missed:
        name = f"unresolved_branch_target_{addr:08X}"
        print(f"[entrypoint.functions.0x{addr:08X}]")
        print(f'name = "{name}"')
        print()

    # Also write to a file for easy reference
    out_path = Path("tools/missed_targets.txt")
    with open(out_path, 'w') as f:
        f.write(f"# {len(missed)} missed indirect call targets\n")
        f.write(f"# Add these to dantes_inferno_manifest.toml\n\n")
        for addr in missed:
            name = f"unresolved_branch_target_{addr:08X}"
            f.write(f"[entrypoint.functions.0x{addr:08X}]\n")
            f.write(f'name = "{name}"\n\n')
    print(f"\nAlso written to: {out_path}")


if __name__ == "__main__":
    main()
