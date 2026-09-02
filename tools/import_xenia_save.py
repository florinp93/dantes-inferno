#!/usr/bin/env python3
"""Import a Xenia save into ReXGlue's content format."""
import struct
import sys
import os
import shutil

def create_rexglue_header(output_path, file_name, display_name, xuid, title_id,
                          device_id=1, content_type=1):
    """Create a ReXGlue .header file with XCONTENT_AGGREGATE_DATA (0x148 bytes)."""
    # XCONTENT_DATA (0x134 bytes):
    #   device_id: be<uint32_t> (4)
    #   content_type: be<uint32_t> (4)
    #   display_name_raw: uint16_t[128] (256)
    #   file_name_raw: char[42] (42)
    #   padding: uint8_t[2] (2)
    # XCONTENT_AGGREGATE_DATA extends XCONTENT_DATA (+0x14):
    #   xuid: be<uint64_t> (8)
    #   title_id: be<uint32_t> (4)

    data = bytearray(0x148)

    # device_id (big-endian)
    struct.pack_into('>I', data, 0x0, device_id)
    # content_type (big-endian)
    struct.pack_into('>I', data, 0x4, content_type)

    # display_name_raw: UTF-16BE, 128 chars max
    display_name_utf16 = display_name.encode('utf-16-be')
    if len(display_name_utf16) > 256:
        display_name_utf16 = display_name_utf16[:256]
    data[0x8:0x8 + len(display_name_utf16)] = display_name_utf16

    # file_name_raw: ASCII, 42 chars max
    file_name_bytes = file_name.encode('ascii')
    if len(file_name_bytes) > 42:
        file_name_bytes = file_name_bytes[:42]
    data[0x108:0x108 + len(file_name_bytes)] = file_name_bytes

    # padding at 0x132 (2 bytes, already zero)

    # xuid (big-endian)
    struct.pack_into('>Q', data, 0x134, xuid)
    # title_id (big-endian)
    struct.pack_into('>I', data, 0x13C, title_id)

    with open(output_path, 'wb') as f:
        f.write(data)
    print(f"Created header: {output_path} ({len(data)} bytes)")

def main():
    # ReXGlue paths
    rex_content_root = r"C:\Users\Florin\Documents\dantes_inferno"
    xuid = 0xB13EBABEBABEBABE
    title_id = 0x454108CF
    content_type = 1  # kSavedGame
    save_name = "DI1-EN-563334654447146054067553"

    # Build paths
    xuid_str = f"{xuid:016X}"
    title_id_str = f"{title_id:08X}"
    content_type_str = f"{content_type:08X}"

    package_dir = os.path.join(rex_content_root, xuid_str, title_id_str,
                               content_type_str, save_name)
    header_dir = os.path.join(rex_content_root, xuid_str, title_id_str,
                              "Headers", content_type_str)
    header_path = os.path.join(header_dir, f"{save_name}.header")

    # Xenia paths
    xenia_base = r"D:\EMU\Xbox 360\Emulators\Xenia Canary\content"
    xenia_save_dir = os.path.join(xenia_base, "E03000005CDA2D34", "454108CF",
                                  "00000001", save_name)
    xenia_data_file = os.path.join(xenia_save_dir, save_name)

    # Clean up old extraction
    old_extracted = package_dir + "_extracted"
    if os.path.exists(old_extracted):
        shutil.rmtree(old_extracted)

    # Create package directory
    os.makedirs(package_dir, exist_ok=True)
    os.makedirs(header_dir, exist_ok=True)

    # Create header file
    display_name = "Dante's Inferno Save"
    create_rexglue_header(header_path, save_name, display_name, xuid, title_id)

    # Copy data file into package directory
    # The game expects files inside the mounted content directory.
    # Copy with the same name as the save (Xenia's convention)
    dest_data = os.path.join(package_dir, save_name)
    shutil.copy2(xenia_data_file, dest_data)
    print(f"Copied data: {xenia_data_file} -> {dest_data}")

    # Also try copying with common save filenames the game might expect
    # Check the data file for clues about internal structure
    with open(xenia_data_file, 'rb') as f:
        magic = f.read(4)
    print(f"Data file magic: {magic}")

    print(f"\nPackage directory: {package_dir}")
    print(f"Header file: {header_path}")
    print(f"\nContents of package dir:")
    for item in os.listdir(package_dir):
        item_path = os.path.join(package_dir, item)
        print(f"  {item} ({os.path.getsize(item_path)} bytes)")

if __name__ == '__main__':
    main()
