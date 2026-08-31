import struct

with open("game/default.xex", "rb") as f:
    data = f.read()

print(f"File size: {len(data)} bytes")
print(f"Magic: {data[:4]}")

flags = struct.unpack_from("<I", data, 0x04)[0]
data_size = struct.unpack_from("<I", data, 0x08)[0]
print(f"Module flags: 0x{flags:08X}")
print(f"Data size (PE): 0x{data_size:08X} ({data_size} bytes)")

# XEX header directory
# The XEX2 header has:
# 0x00: magic
# 0x04: module_flags
# 0x08: pe_data_size
# 0x0C: rsa_signature_offset
# 0x10: cert_offset (4 bytes), cert_size (4 bytes)
cert_off = struct.unpack_from("<I", data, 0x10)[0]
cert_size = struct.unpack_from("<I", data, 0x14)[0]
print(f"Cert offset: 0x{cert_off:08X}, size: 0x{cert_size:08X}")

# Bit 0 of flags = compressed
print(f"Compressed: {bool(flags & 0x01)}")
print(f"Encrypted:  {bool(flags & 0x02)}")

# Dump first 0x400 bytes as hex
for i in range(0, min(0x400, len(data)), 16):
    hex_str = " ".join(f"{b:02X}" for b in data[i:i+16])
    ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in data[i:i+16])
    print(f"{i:04X}: {hex_str}  {ascii_str}")
