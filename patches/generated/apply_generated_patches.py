#!/usr/bin/env python3
"""
apply_generated_patches.py

Applies manual fiber/setjmp/longjmp edits to generated code after codegen.
These edits are lost every time codegen is regenerated and must be re-applied.

The ZeroFiberSwitchCallback() injection in sub_82701240 is automatic via
the [[midasm_hook]] in the manifest and does NOT need manual re-application.

Edits applied:
  1. dantes_inferno_recomp.70.cpp - sub_82701240: add FiberSetjmp before li r3,0
  2. dantes_inferno_recomp.24.cpp - sub_8267ACC8: add setjmp after sub_82701240 call
  3. dantes_inferno_recomp.45.cpp - sub_82700CE0: replace blr with FiberLongjmp
  4. dantes_inferno_recomp.38.cpp - sub_82678D78: add return after sub_82700CE0 call
"""

import os
import re
import sys

def apply_patch(filepath, check_pattern, find_regex, replacement, description):
    if not os.path.exists(filepath):
        print(f"  WARNING: File not found, skipping: {description}")
        return
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    if re.search(check_pattern, content):
        print(f"  Already applied: {description}")
        return
    match = re.search(find_regex, content, re.DOTALL)
    if match:
        content = re.sub(find_regex, replacement, content, flags=re.DOTALL)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Applied: {description}")
    else:
        print(f"  WARNING: Pattern not found: {description}")

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    gen_dir = os.path.join(project_root, 'generated', 'default')

    if not os.path.isdir(gen_dir):
        print(f"ERROR: Generated directory not found: {gen_dir}", file=sys.stderr)
        sys.exit(1)

    # 1. sub_82701240 in .70 - add FiberSetjmp before li r3,0
    file70 = os.path.join(gen_dir, 'dantes_inferno_recomp.70.cpp')
    apply_patch(file70,
        r'FiberSetjmp',
        r'(REX_STORE_U32\(ctx\.r3\.u32 \+ 312, ctx\.r0\.u32\);\n)\s*// li r3,0',
        r'''\g<1>	{
		int fiber_ret = FiberSetjmp(ctx.r3.u32);
		if (fiber_ret != 0) {
			FiberRestoreContext(ctx, base);
			return;
		}
	}
	// li r3,0''',
        "sub_82701240: FiberSetjmp before return")

    # 2. sub_8267ACC8 in .24 - add setjmp after sub_82701240 call
    file24 = os.path.join(gen_dir, 'dantes_inferno_recomp.24.cpp')
    apply_patch(file24,
        r'g_setjmp_ctx_addr',
        r'(ctx\.lr = 0x8267AD1C;\n)\s*sub_82701240\(ctx, base\);\n(\s*// cmpwi r3,0)',
        r'''\g<1>	g_setjmp_ctx_addr = ctx.r3.u32;
	sub_82701240(ctx, base);
	{
		int fiber_ret = setjmp(g_fiber_jmp_buf);
		if (fiber_ret != 0) {
			FiberRestoreContext(ctx, base);
		}
	}
\g<2>''',
        "sub_8267ACC8: setjmp after sub_82701240")

    # 3. sub_82700CE0 in .45 - replace blr with FiberLongjmp
    file45 = os.path.join(gen_dir, 'dantes_inferno_recomp.45.cpp')
    apply_patch(file45,
        r'FiberLongjmp',
        r'(ctx\.r3\.u64 = ctx\.r6\.u64;\n)\s*// blr \n\s*return;\n(loc_82700FCC:)',
        r'''\g<1>	FiberLongjmp(ctx.r6.u32);
	return;
\g<2>''',
        "sub_82700CE0: FiberLongjmp instead of blr")

    # 4. sub_82678D78 in .38 - add return after sub_82700CE0 call
    file38 = os.path.join(gen_dir, 'dantes_inferno_recomp.38.cpp')
    apply_patch(file38,
        r'sub_82700CE0\(ctx, base\);\n\s*return;\n\}',
        r'(sub_82700CE0\(ctx, base\);)\n\}',
        r'''\g<1>
	return;
}''',
        "sub_82678D78: return after sub_82700CE0")

    print("Generated code patches applied.")

if __name__ == '__main__':
    main()
