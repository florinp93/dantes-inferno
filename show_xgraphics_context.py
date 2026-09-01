import re

with open("default_basefile.bin", "rb") as f:
    data = f.read()

base = 0x82000000
for m in re.finditer(re.escape(b"xgraphics"), data):
    off = m.start()
    start = max(0, off - 64)
    end = min(len(data), off + 64)
    ctx = data[start:end]
    s = "".join(chr(b) if 32 <= b < 127 else "." for b in ctx)
    print(f"0x{base+off:08X}: {s}")
