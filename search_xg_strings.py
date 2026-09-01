import re

with open("default_basefile.bin", "rb") as f:
    data = f.read()

base = 0x82000000
patterns = [b"XGSetTextureHeader", b"XGSetLinearTextureHeader", b"XGCalcTextureAddress",
            b"XGSetTexture", b"XGSetLinear", b"XGCalc", b"XGTEXTURE", b"xgraphics"]

for s in patterns:
    found = [m.start() for m in re.finditer(re.escape(s), data)]
    if found:
        print(f"'{s.decode()}' found {len(found)} times")
        for off in found[:5]:
            print(f"  0x{base+off:08X}")
    else:
        print(f"'{s.decode()}' not found")
