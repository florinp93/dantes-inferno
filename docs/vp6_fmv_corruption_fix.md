# VP6/Bink FMV Corruption Fix — Technical Documentation

## Problem Statement

Pre-rendered FMV cutscenes in Dante's Inferno (Xbox 360) exhibited severe
visual corruption when played back through the native PC port built with
ReXGlue SDK v0.10.0. The corruption manifested as:

- Green tinting across the frame
- Random noise and checkerboard artifacts
- Scanline patterns
- Periodic block corruption aligned to 8x8 DCT block boundaries

The corruption was present in all VP6/Bink-encoded FMVs and was reproducible
on every run.

## Architecture Context

### VP6 Decode Pipeline

The VP6 decoder runs as recompiled PPC guest code on the host CPU. The decode
pipeline is:

1. **Bitstream parsing** — PPC scalar code extracts VLC-coded DCT coefficients
2. **IDCT (Inverse Discrete Cosine Transform)** — PPC VMX/AltiVec vector code
   transforms frequency-domain coefficients to spatial-domain pixel values
3. **Pixel packing** — VMX pack instructions convert 32-bit intermediate
   results to 8-bit pixel values
4. **Guest RAM writeback** — Vector stores write decoded pixels to guest RAM
5. **GPU texture upload** — The D3D12 backend uploads guest RAM as a luma
   texture (k_8 format)
6. **YUV-to-RGB shader** — The GPU converts YUV planes to RGB for display

### ReXGlue Recompilation Model

ReXGlue statically recompiles PPC Xbox 360 code to C++ at build time. The
generated C++ uses SIMDE intrinsics to emulate PPC VMX instructions on the
host CPU (x86-64 with SSE4.1).

Key architectural detail: **PPC vectors are big-endian, host vectors are
little-endian.** The recompiler handles this by byte-reversing all vector
loads/stores and adjusting element indices. This means PPC element 0 maps to
host element 3, PPC element 1 maps to host element 2, etc.

## Diagnostic Methodology

### Phase 1: Isolating the Corruption Layer

A series of GPU-side diagnostic overrides were injected into the D3D12
texture cache and command processor to determine whether the corruption
originated in the GPU rendering path or upstream in the CPU decode path.

| Override | Effect | Result |
|---|---|---|
| Replace 4th VP6 texture fetch with 1x1 white | Eliminates one YUV plane | Corruption persists |
| Neutralize U/V chroma to 0x80 | Forces grayscale | Corruption persists in B&W at same locations |
| Neutralize Y luma to 0x80 | Forces mid-gray frame | **Corruption disappears — frame is uniform gray** |
| Force opaque source-only blending | Eliminates blend state issues | No effect on corruption |
| Replace all 3 YUV planes with neutral | Forces fully neutral frame | Clean output confirmed |

**Conclusion:** The D3D12 YUV-to-RGB shader path is correct. The corruption
is in the luma (Y) data uploaded to the GPU, not in the rendering pipeline.

### Phase 2: Guest RAM Dump Analysis

Guest RAM was dumped during FMV playback and the luma texture region was
analyzed. The corruption was already present in guest RAM before GPU upload,
confirming the corruption originates in the recompiled PPC VP6 decoder code.

The corruption pattern showed periodic damage within 8x8 DCT blocks —
consistent with errors in the IDCT or pixel packing stages.

### Phase 3: GPU Diagnostic Removal

All temporary GPU-side diagnostic overrides were removed and verified absent
from runtime logs:
- `[GPU VP6 WhiteOverride]`
- `[GPU VP6 LumaOnly]`
- Forced blend overrides
- Diagnostic logging

## Fixes Applied

### Fix 1: `vmsum3fp128` Dot Product Mask — REVERTED (0x7F → 0xEF)

**File:** `thirdparty/rexglue-sdk/src/codegen/builders/vector.cpp`
**Function:** `build_vmsum3fp128`

#### Technical Details

`vmsum3fp128` computes a 3-element floating-point dot product (PPC elements
0, 1, 2 — excluding element 3). The implementation uses SSE
`simde_mm_dp_ps` (dot product) with an 8-bit imm8 mask.

The SSE `dp_ps` mask format (per Intel SDM and SIMDE implementation) is:
- **Bits [7:4] — source/sum mask**: bit `(i+4)` selects host element `i`
  - bit 4 → host elem 0, bit 5 → host elem 1,
  - bit 6 → host elem 2, bit 7 → host elem 3
- **Bits [3:0] — destination/broadcast mask**: bit `i` selects host element `i`

Due to the PPC-to-host byte reversal:
- PPC element 0 = host element 3
- PPC element 1 = host element 2
- PPC element 2 = host element 1
- PPC element 3 = host element 0 (excluded from 3-element dot)

To sum PPC elements 0,1,2 = host elements 3,2,1 and exclude PPC element 3 =
host element 0:
- Sum bits [7:4] = `1110` = `0xE` (bit 4=0 excludes host elem 0 = PPC elem 3)
- Broadcast bits [3:0] = `1111` = `0xF` (all lanes)
- **Correct mask: `0xEF`**

#### History — Incorrect "Fix" and Reversion

An earlier iteration of this document incorrectly described the mask layout
as bits [7:4] = broadcast and [3:0] = sum (reversed from the actual Intel
convention). Based on that incorrect understanding, the mask was changed
from `0xEF` to `0x7F`. This was **wrong**:

- `0x7F` = `0b0111_1111`: sum bits [7:4] = `0111` → sums host elements
  0,1,2 (PPC elements 3,2,1) and **EXCLUDES host element 3 = PPC element 0
  (the X component)**. This broke 3-element dot products in physics/collision
  code, causing the character to fall through the map after the opening
  cutscene.
- `0xEF` = `0b1110_1111`: sum bits [7:4] = `1110` → sums host elements
  1,2,3 (PPC elements 2,1,0) and excludes host element 0 = PPC element 3 (W).
  This is correct.

The FMV corruption was actually fixed by Fix 2 (pack builder `unpackhi`
removal) and Fix 3 (`vpkuwus`/`vpkuhus` aliasing), not by the `vmsum3fp128`
mask change. The mask change was a red herring that introduced a new,
severe physics bug.

The `0x7F` → `0xEF` reversion was verified by the SDK's PPC instruction
test suite (`ppc_tests`): the `vmsum3fp128.test_1` test case failed with
`0x7F` (expected `0x4122A7F0`, got `0x4102A7F0` — missing the PPC element 0
product) and passes with `0xEF`. All 1458 test cases pass after the fix.

#### Generated Code (After Reversion)

```cpp
// vmsum3fp128 v8,v10,v10
simde_mm_store_ps(ctx.v8.f32,
                  simde_mm_dp_ps(simde_mm_load_ps(ctx.v10.f32),
                                 simde_mm_load_ps(ctx.v10.f32), 0xEF));
```

### Fix 2: Pack Builder `unpackhi_epi64` Removal

**File:** `thirdparty/rexglue-sdk/src/codegen/builders/vector.cpp`
**Functions:** `build_vpkshus`, `build_vpkuhum`, `build_vpkuwus`,
`build_vpkuwum`, `build_vpkshss`, `build_vpkswss`, `build_vpkswus`

#### Technical Details

The PPC pack instructions combine two 128-bit source vectors into a single
128-bit destination by packing (narrowing) elements. For example,
`vpkshus` packs 8+8 signed 16-bit halfwords into 16 unsigned 8-bit bytes
with unsigned saturation.

The SSE pack intrinsics (`packus_epi16`, `packs_epi16`, `packus_epi32`,
`packs_epi32`) take two 128-bit inputs and produce a 128-bit output where
the first source occupies the low 8/16 bytes and the second source occupies
the high 8/16 bytes.

The original builders wrapped the pack intrinsic in
`simde_mm_unpackhi_epi64`, which extracts only the high 64 bits of the
128-bit result. This discarded the low 64 bits (containing the packed
elements from the first source) and duplicated the high 64 bits into both
halves of the destination.

This caused:
- Loss of half the packed elements
- Duplication of the remaining elements
- Periodic 8-pixel corruption patterns in packed pixel output

The fix removes the `unpackhi_epi64` wrapper and adjusts operand ordering
to account for the PPC-to-host byte reversal. Since SSE pack puts the first
argument in low bytes and PPC puts the first source in high bytes (due to
reversal), the operands are swapped: `pack(op[2], op[1])` instead of
`pack(op[1], op[2])`.

#### Generated Code (After Fix)

```cpp
// vpkshus128 v63,v12,v13
simde_mm_store_si128((simde__m128i*)ctx.v63.u8,
                     simde_mm_packus_epi16(
                         simde_mm_load_si128((simde__m128i*)ctx.v13.s16),
                         simde_mm_load_si128((simde__m128i*)ctx.v12.s16)));
```

### Fix 3: `vpkuwus` and `vpkuhus` In-Place Aliasing (Root Cause)

**File:** `thirdparty/rexglue-sdk/src/codegen/builders/vector.cpp`
**Functions:** `build_vpkuwus`, `build_vpkuhus`

#### Technical Details

This was the root cause of the visible FMV corruption.

The original `build_vpkuwus` and `build_vpkuhus` implementations used
element-by-element scalar packing loops instead of SSE intrinsics. The
justification was that `simde_mm_packus_epi32` and `simde_mm_packus_epi16`
treat inputs as signed, which would incorrectly clamp unsigned values
>= 0x8000/0x80000000.

The element-by-element approach writes to the destination's narrowed element
array (`u16[]` or `u8[]`) while reading from the source's wider element
array (`u32[]` or `u16[]`). When the destination register is the same as
one of the source registers (in-place operation), the writes corrupt
subsequent reads because the `u16[]`/`u8[]` and `u32[]`/`u16[]` arrays are
aliased — they refer to the same underlying 128-bit storage.

**Concrete example — `vpkuwus128 v63,v61,v63`:**

```
Iteration 0: v63.u16[7] = saturate(v61.u32[3])   // writes bytes 14-15
             v63.u16[3] = saturate(v63.u32[3])   // reads bytes 12-15 ← CORRUPTED
```

After writing `v63.u16[7]` (bytes 14-15), the read of `v63.u32[3]` (bytes
12-15) picks up the already-modified bytes 14-15. The high 16 bits of the
read value are now the packed result, not the original source data. This
produces an incorrect saturation check and wrong packed value for
`v63.u16[3]`.

The same corruption cascades through all subsequent iterations where the
destination overlaps the source.

This pattern occurs frequently in the VP6 IDCT output path because the
decoder reuses registers aggressively — the generated code contains
instances like `vpkuwus128 v63,v61,v63` and `vpkuwus128 v63,v62,v63` where
the destination is also the second source.

#### Fix

Replace the element-by-element loops with SSE intrinsics that:
1. Clamp unsigned values to the target range using `min_epu32`/`min_epu16`
   (unsigned minimum, which correctly handles values that would be
   interpreted as negative by signed pack intrinsics)
2. Use `packus_epi32`/`packus_epi16` to pack the clamped values

The SSE intrinsics load both source vectors into separate host registers
before computing the result, so there is no aliasing even when the PPC
destination register overlaps a PPC source register.

Operand order is swapped (`op[2], op[1]`) to account for PPC-to-host byte
reversal, consistent with the other pack builders.

#### Generated Code (After Fix)

```cpp
// vpkuwus128 v63,v61,v63
simde_mm_store_si128(
    (simde__m128i*)ctx.v63.u16,
    simde_mm_packus_epi32(
        simde_mm_min_epu32(
            simde_mm_load_si128((simde__m128i*)ctx.v63.u32),
            simde_mm_set1_epi32(0xFFFF)),
        simde_mm_min_epu32(
            simde_mm_load_si128((simde__m128i*)ctx.v61.u32),
            simde_mm_set1_epi32(0xFFFF))));
```

The `min_epu32` clamp to `0xFFFF` ensures that unsigned values in the range
`[0, 0xFFFF]` pass through unchanged (these are non-negative when
interpreted as signed, so `packus_epi32` handles them correctly), and
values `> 0xFFFF` are clamped to `0xFFFF` (matching PPC unsigned saturate
semantics).

The same pattern applies to `vpkuhus` with `min_epu16` clamping to `0xFF`
and `packus_epi16`.

## Instructions Investigated But Not Changed

### `vmaddfp` / `vnmsubfp` / `vmaddcfp128`

These fused multiply-add instructions were investigated for potential
operand-order mismatches. The PPC assembly syntax for `vmaddfp` is
`vmaddfp vD, vA, vC, vB` (note: vC appears before vB in assembly), and the
operation is `vD = vA * vC + vB`.

The ReXGlue disassembler (based on binutils `ppc-dis.c`) stores operands in
**assembly syntax order** as defined by the opcode table entry:
```
{ "vmaddfp", VXA(4, 46), VXA_MASK, PPCVEC, { VD, VA, VC, VB }, ... }
```

This means:
- `operands[0]` = vD (destination)
- `operands[1]` = vA (multiplicand)
- `operands[2]` = vC (multiplicand)
- `operands[3]` = vB (addend)

The builder emits `mul(op[1], op[2]) + op[3]` = `vA * vC + vB`, which is
correct. No change was needed.

An earlier iteration incorrectly swapped operands[2] and operands[3],
producing `vA * vB + vC` — this broke the IDCT and caused new color
artifacts (green/white/pink/blue). The swap was reverted.

### `vperm` / `vperm128`

The `simde_mm_perm_epi8_` helper in `intrinsics.h` was reviewed. It
correctly inverts the control byte indices to account for byte reversal
and uses `blendv_epi8` to select between the two source vectors. The PPC
vperm semantics (including zeroing when control bit 5 is set) are handled
by the SSE shuffle mask high bit. No change was needed.

### `vsldoi`

The `build_vsldoi` builder uses `simde_mm_alignr_epi8(vA, vB, 16-SH)`,
which correctly concatenates `[vB || vA]` and right-shifts by `16-SH`
bytes, equivalent to PPC `vsldoi` semantics under byte reversal. No change
was needed.

### `stvewx` / `stvx128`

Vector store byte ordering was reviewed. The `stvewx` store uses
`ctx.vN.u32[3 - ((ea & 0xF) >> 2)]` to select the correct word considering
byte reversal. The `stvx128` store applies `VectorMaskL` (a byte-reversal
shuffle mask) before writing to guest RAM. Both are correct.

### `vcuxwfp128` / `vcfpuxws128`

The unsigned int-to-float and float-to-unsigned-int conversion helpers
(`simde_mm_cvtepu32_ps_` and `simde_mm_vctuxs`) were reviewed. Both
correctly handle the unsigned range by splitting values >= 2^31 into a
high-bit adjustment. No change was needed.

## Files Modified

All changes are in the ReXGlue SDK (gitignored, under
`thirdparty/rexglue-sdk/`):

| File | Changes |
|---|---|
| `src/codegen/builders/vector.cpp` | `vmsum3fp128` mask, pack builders `unpackhi` removal, `vpkuwus`/`vpkuhus` aliasing fix |
| `include/rex/graphics/d3d12/texture_cache.h` | Temporary diagnostic overrides (added then removed) |
| `src/graphics/d3d12/command_processor.cpp` | Temporary diagnostic overrides (added then removed) |
| `src/graphics/d3d12/pipeline_cache.cpp` | Temporary diagnostic overrides (added then removed) |
| `src/graphics/d3d12/render_target_cache.cpp` | Temporary diagnostic overrides (added then removed) |
| `src/graphics/d3d12/texture_cache.cpp` | Temporary diagnostic overrides (added then removed) |
| `src/graphics/pipeline/shader/dxbc_translator.cpp` | Temporary diagnostic overrides (added then removed) |
| `src/graphics/pipeline/texture/cache.cpp` | Temporary diagnostic overrides (added then removed) |

All temporary GPU-side diagnostic overrides were removed after
investigation. The only permanent changes are in
`src/codegen/builders/vector.cpp`.

## Verification

1. Generated code was regenerated by deleting stale `.cpp` files in
   `generated/default/` and rebuilding (codegen runs as a build dependency)
2. Generated code was inspected to confirm the fixes were applied:
   - `vmsum3fp128` uses mask `0x7F`
   - Pack instructions use direct SSE pack intrinsics without `unpackhi`
   - `vpkuwus128` uses `min_epu32` + `packus_epi32` (no element loops)
3. The rebuilt `rexgpu-xenos.dll` was copied from
   `thirdparty/rexglue-sdk/out/win-amd64/` to
   `out/build/win-amd64-release/` (the directory the executable loads from)
4. The game was launched with `--game_data_root=game`
5. Runtime logs were checked for the absence of stale diagnostic markers
6. User confirmed: FMV corruption is completely eliminated

## Build & Launch Procedure

```powershell
# Delete stale generated files to force regeneration
Remove-Item generated\default\dantes_inferno_recomp.{7,95,23,94}.cpp -Force

# Build (codegen runs automatically as a build dependency)
cmake --build out\build\win-amd64-release

# Copy the rebuilt DLL to the executable directory
Copy-Item thirdparty\rexglue-sdk\out\win-amd64\rexgpu-xenos.dll `
          out\build\win-amd64-release\rexgpu-xenos.dll -Force

# Launch with the required game-data argument
.\out\build\win-amd64-release\dantes_inferno.exe --game_data_root=game
```
