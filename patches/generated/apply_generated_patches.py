#!/usr/bin/env python3
"""
apply_generated_patches.py

Applies manual fiber/setjmp/longjmp edits to generated code after codegen.
These edits are lost every time codegen is regenerated and must be re-applied.

The ZeroFiberSwitchCallback() injection in sub_82701240 is automatic via
the [[midasm_hook]] in the manifest and does NOT need manual re-application.

Edits applied:
  1. sub_82701240: add FiberSetjmp before li r3,0
  2. sub_8267ACC8: add setjmp after sub_82701240 call
  3. sub_82700CE0: replace blr with FiberLongjmp
  4. sub_82678D78: add return after sub_82700CE0 call

The functions may land in different .cpp files depending on the manifest's
unresolved-function entries, so we search all generated files dynamically.
"""

import os
import re
import sys
import glob

def find_file_containing(gen_dir, pattern):
    """Find the first .cpp file in gen_dir containing the given regex pattern."""
    for filepath in sorted(glob.glob(os.path.join(gen_dir, 'dantes_inferno_recomp.*.cpp'))):
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        if re.search(pattern, content):
            return filepath, content
    return None, None

def apply_patch(filepath, content, check_pattern, find_regex, replacement, description):
    if not filepath:
        print(f"  WARNING: File not found for: {description}")
        return content
    if re.search(check_pattern, content):
        print(f"  Already applied: {description}")
        return content
    match = re.search(find_regex, content, re.DOTALL)
    if match:
        content = re.sub(find_regex, replacement, content, flags=re.DOTALL)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Applied: {description} ({os.path.basename(filepath)})")
    else:
        print(f"  WARNING: Pattern not found: {description} ({os.path.basename(filepath)})")
    return content

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    gen_dir = os.path.join(project_root, 'generated', 'default')

    if not os.path.isdir(gen_dir):
        print(f"ERROR: Generated directory not found: {gen_dir}", file=sys.stderr)
        sys.exit(1)

    # 1. sub_82701240 - add FiberSetjmp before li r3,0
    # This function contains the ZeroFiberSwitchCallback() hook injection.
    filepath, content = find_file_containing(gen_dir, r'DEFINE_REX_FUNC\(sub_82701240\)')
    if filepath:
        content = apply_patch(filepath, content,
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

    # 2. sub_8267ACC8 - add setjmp after sub_82701240 call
    filepath, content = find_file_containing(gen_dir, r'DEFINE_REX_FUNC\(sub_8267ACC8\)')
    if filepath:
        content = apply_patch(filepath, content,
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

    # 3. sub_82700CE0 - replace blr with FiberLongjmp
    filepath, content = find_file_containing(gen_dir, r'DEFINE_REX_FUNC\(sub_82700CE0\)')
    if filepath:
        content = apply_patch(filepath, content,
            r'FiberLongjmp',
            r'(ctx\.r3\.u64 = ctx\.r6\.u64;\n)\s*// blr \n\s*return;\n(loc_82700FCC:)',
            r'''\g<1>	FiberLongjmp(ctx.r6.u32);
	return;
\g<2>''',
            "sub_82700CE0: FiberLongjmp instead of blr")

    # 4. sub_82678D78 - add return after sub_82700CE0 call
    filepath, content = find_file_containing(gen_dir, r'DEFINE_REX_FUNC\(sub_82678D78\)')
    if filepath:
        content = apply_patch(filepath, content,
            r'sub_82700CE0\(ctx, base\);\n\s*return;\n\}',
            r'(sub_82700CE0\(ctx, base\);)\n\}',
            r'''\g<1>
	return;
}''',
            "sub_82678D78: return after sub_82700CE0")

    print("Generated code patches applied.")

if __name__ == '__main__':
    main()
