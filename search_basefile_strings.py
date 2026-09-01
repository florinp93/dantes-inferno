import re

patterns = [b"bink", b".bih", b".vp6", b"BINK", b"BIH", b"VP6", b"video", b"fmv", b"movie",
            b"cinematic", b"chroma", b"luma", b"YUV", b"YUV420", b"bink2", b"Electronic", b"EA",
            b"BIGFILE", b"BIGFILE2", b"BIGFILE3", b"BIGFILE4", b"BIGFILE5", b"BIGFILE6",
            b"BIGFILE7", b"BIGFILE8", b"BIGFILE9", b"BIGFILE10", b"BIGFILE11"]

base = 0x82000000

with open("default_basefile.bin", "rb") as f:
    data = f.read()

print(f"Basefile size: {len(data)} bytes")

for p in patterns:
    found = [m.start() for m in re.finditer(re.escape(p), data)]
    if found:
        print(f"\nPattern '{p.decode()}' found {len(found)} times")
        for off in found[:10]:
            addr = base + off
            start = max(0, off - 32)
            end = min(len(data), off + len(p) + 32)
            ctx = data[start:end]
            ctx_str = "".join(chr(b) if 32 <= b < 127 else "." for b in ctx)
            print(f"  0x{addr:08X}: {ctx_str}")
