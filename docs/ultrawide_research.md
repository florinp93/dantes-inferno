# Ultrawide Support Research (21:9 / 32:9)

## Executive Summary

**You are right: ReXGlue alone cannot do proper ultrawide.** It can force the
viewport to render at any resolution, but the game's projection matrix still
uses a 16:9 aspect ratio, so the 3D scene is horizontally stretched. True
ultrawide requires patching the game's projection matrix builder to use the
host display's aspect ratio instead of the hardcoded 16:9.

The good news: through Ghidra RE, we've identified the exact function and
instruction to patch. The fix is a single `midasm_hook` that replaces the
aspect ratio float register after the division instruction.

---

## 1. The Core Problem

Three independent things must change for correct ultrawide:

| Layer | What happens | Who controls it |
|-------|-------------|-----------------|
| **Projection matrix** | `m[5] = aspect * cot(fov)` — determines horizontal FOV | Game code (PPC) |
| **Render target size** | Internal draw buffer dimensions | ReXGlue cvars |
| **Presentation scaling** | How the guest output fills the host window | ReXGlue presenter |

ReXGlue handles layers 2 and 3. Layer 1 — the projection matrix — is computed
by the game's own code and is opaque to ReXGlue. Without patching it, you get
one of two bad outcomes:

- **`present_letterbox = true`** (default): correct geometry but pillarboxed
  (black bars on left/right of 16:9 image centered on ultrawide screen)
- **`present_letterbox = false`**: fills the screen but stretches the 16:9
  image horizontally — characters look fat, circles become ellipses

The solution is **Hor+ anamorphic render**: patch the projection to use the
host aspect ratio, keep the render buffer at 16:9, then stretch the anamorphic
image to fill the ultrawide display. Because the projection was built for the
wider aspect, the final image is geometrically correct.

---

## 2. RE Findings (Ghidra)

### 2.1 Projection Matrix Builder: `FUN_826d5c58` @ `0x826D5C58`

This is the game's perspective projection matrix builder. Decompiled from
Ghidra (`C:\ghidra_scripts\decomp_matrix_builders.txt`):

```c
float * FUN_826d5c58(double width, double height, double near_plane,
                     float *out_matrix, float *fov_ptr)
{
    float cotFov = 1.0f / tanf(*fov_ptr);   // vertical FOV
    out_matrix[0]  = cotFov;                 // m[0]  = cot(fovY)
    out_matrix[5]  = (width/height) * cotFov;// m[5]  = aspect * cot(fovY)
    out_matrix[10] = -1.0f;                  // m[10] = -1 (reversed Z)
    out_matrix[11] = 1.0f;                   // m[11] = 1
    out_matrix[14] = near_plane * far_scale; // depth
    // all other elements = 0
    return out_matrix;
}
```

**Key instruction** — the aspect ratio division:

```asm
826d5c74  fmr f31,f1          ; f31 = width  (param_1)
826d5c80  fmr f30,f2          ; f30 = height (param_2)
826d5c88  bl  0x8294dfb0      ; call tanf(*fov_ptr)
826d5c90  frsp f10,f1         ; f10 = tanf result (to float)
>>> 826d5c94  fdivs f9,f31,f30    ; f9 = width/height = ASPECT RATIO
826d5cc0  fdivs f10,f13,f10  ; f10 = 1.0 / tan(fov) = cot(fov)
>>> 826d5cec  fmuls f13,f9,f10   ; f13 = aspect * cot(fov) = m[5]
826d5d00  stfs f13,0x14(r31) ; store m[5] into output matrix
```

**Hook target**: `0x826D5C94` — after this instruction, `f9` contains the
aspect ratio. Replace it with the host aspect ratio.

### 2.2 Caller: `FUN_825d5578` @ `0x825D5578`

This is the camera setup function that calls the projection builder. It reads
width/height from a camera/rendering struct:

```c
void FUN_825d5578(long camera_struct)
{
    // ... view matrix setup ...
    FUN_826d5c58(
        (double)(long)*(int*)(camera_struct + 0x360),   // width  (int)
        (double)(long)*(int*)(camera_struct + 0x364),   // height (int)
        (double)*(float*)(camera_struct + 0x354),        // near plane
        output_matrix,
        &fov                                             // FOV pointer
    );
}
```

The width/height at offsets `+0x360`/`+0x364` are integers (likely 1280/720).
The function is called **indirectly** (via function pointer/vtable) — no
direct `bl` references found in the binary.

### 2.3 16:9 Aspect Ratio Constant

A hardcoded `1.7777778f` (16/9) constant exists at `0x821113C8`, referenced
from `0x8227FD24`:

```asm
8227fd1c  lfs f0,0x50a0(r10)    ; load runtime aspect value
8227fd24  lfs f13,0x4d8(r9)     ; load 1.7777 constant (16:9)
8227fd28  fcmpu cr6,f0,f13      ; compare runtime vs 16:9
8227fd2c  bne cr6,0x8227fd34    ; if not 16:9, take alternate path
8227fd30  li r11,0x1            ; flag = is_16_9
```

This is the game's **display aspect ratio detection** — it checks whether the
output is 16:9 or 4:3 and adjusts UI/layout accordingly. This is separate
from the projection matrix and would need its own patch if we want the game's
UI to treat ultrawide as 16:9 (to avoid UI elements drifting to screen edges).

### 2.4 Other Matrix Builders

40 matrix-building functions were identified by instruction pattern analysis
(`C:\ghidra_scripts\matrix_builders.txt`). The projection builder
`FUN_826d5c58` is the only one with the `tanf` + `fdivs` pattern
characteristic of a perspective matrix. Other notable ones:

- `FUN_826d5e80` (9 stfs, 9 fmuls) — likely an orthographic matrix builder
  (no `tanf` call, no division). Used for UI/HUD rendering.
- `FUN_82667b98` (15 stfs, 15 fmuls, 3 fdivs) — a view matrix or
  look-at builder (uses `1/x` divisions, no `tanf`).

### 2.5 FOV Consumers

200+ functions access FOV-related struct offsets (`0x84`, `0x88`, `0x8c`)
via `stfs`/`lfs` instructions (`C:\ghidra_scripts\fov_consumers.txt`). These
are spread across rendering, camera, and gameplay code. The FOV value flows
through many systems, so we should **not** try to patch FOV — only the aspect
ratio.

---

## 3. Codegen Status

### 3.1 Is the projection function generated?

The projection builder at `0x826D5C58` is **not listed as a separate
function** in `codegen.partition.json`. However, the nearest generated
function starts at `0x826D5B08` (partition 60), and the next function starts
at `0x826D5DF0` (partition 34). Since there are no other function boundaries
between `0x826D5B08` and `0x826D5DF0`, the codegen likely merged the code at
`0x826D5C58` into the function starting at `0x826D5B08`.

The `midasm_hook` mechanism is keyed by **instruction address**, not function
address. As long as the instruction at `0x826D5C94` is part of any generated
function, the hook will be injected. Given the function boundary analysis
above, this should work.

### 3.2 Math library functions

The `tanf` function at `0x8294DFB0` is NOT in the generated code (the entire
`0x8294xxxx` range is absent from `codegen.partition.json`). ReXGlue replaces
PPC math library functions with host-side implementations — the codegen emits
calls to the host's `tanf()` rather than recompiling the PPC version.

### 3.3 Fallback: force function generation

If the hook doesn't fire (because the instruction isn't in any generated
function), add the projection builder to the manifest:

```toml
[entrypoint.functions.0x826D5C58]
name = "projection_matrix_builder"
```

Then regenerate codegen and rebuild. This forces codegen to generate a
function stub at that address, which will include the hook.

---

## 4. Implementation Plan

### 4.1 The Hook

**Manifest** (`config/ultrawide_hooks.toml`):
```toml
[[midasm_hook]]
address = 0x826D5C94
name = "UltrawideAspectHook"
registers = ["f9"]
after_instruction = true
```

**Hook function** (`src/ultrawide_hooks.h`):
```cpp
#pragma once
#include <rex/ppc/context.h>

// Called after `fdivs f9,f31,f30` which computes width/height.
// Replace f9 (the aspect ratio) with the host display's aspect ratio.
inline void UltrawideAspectHook(float& f9) {
    // TODO: Read actual host window dimensions at runtime.
    // For now, hardcode 21:9 (3440x1440).
    // The game computed width/height (e.g. 1280/720 = 1.777).
    // We replace it with the host aspect (e.g. 3440/1440 = 2.389).
    constexpr float host_aspect = 3440.0f / 1440.0f;
    f9 = host_aspect;
}
```

**Include in manifest**:
```toml
[entrypoint]
includes = ["config/ultrawide_hooks.toml"]
```

**Force-include the header** (in `CMakeLists.txt` or via the app header):
```cmake
target_compile_options(dantes_inferno_recomp PRIVATE
    "-include${CMAKE_CURRENT_SOURCE_DIR}/src/ultrawide_hooks.h"
)
```

### 4.2 Presenter Configuration

In `OnPreSetup` (`src/dantes_inferno_app.h`):
```cpp
// Tell the game the display is ultrawide
REXCVAR_SET(video_mode_width, 3440);
REXCVAR_SET(video_mode_height, 1440);

// Disable letterboxing — stretch the anamorphic 16:9 render to fill
REXCVAR_SET(present_letterbox, false);
```

The guest render target stays at 1280x720 (or scaled with `resolution_scale`).
The projection matrix now uses 3440/1440 aspect, so the 3D scene renders with
wider horizontal FOV. The presenter stretches the 16:9 image to fill the
3440x1440 window, and because the projection was built for 2.389:1, the
result is geometrically correct.

### 4.3 Runtime Aspect Detection (Future)

Instead of hardcoding the aspect ratio, read the actual host window size:

```cpp
inline void UltrawideAspectHook(float& f9) {
    extern float g_host_aspect_ratio;  // updated by OnPostSetup or window resize
    f9 = g_host_aspect_ratio;
}
```

The host aspect can be set from `OnPostSetup` by querying the swapchain
dimensions, or from a cvar like `ultrawide_target_aspect`.

### 4.4 UI/HUD Handling

The game's 2D UI (HUD, menus, subtitles) uses a separate orthographic
projection (`FUN_826d5e80`, no `tanf` call). Since we only hook the
perspective builder, the UI will render at 16:9 and be stretched by the
presenter. This means:

- **HUD elements**: will be stretched horizontally (text wider, icons oval)
- **Menus**: same stretching
- **Cutscenes**: pre-rendered VP6 video is 16:9 — will be stretched

**Mitigation options** (in priority order):
1. **Accept stretched UI** — simplest, many ultrawide games do this
2. **Hook the orthographic builder too** — scale UI x-coordinates to
   compensate (would need RE of `FUN_826d5e80`)
3. **Render UI to a 16:9 sub-viewport** — center the UI in a 16:9 region of
   the ultrawide screen (requires presenter changes)
4. **Patch the 16:9 detection constant** at `0x8227FD24` to always report
   16:9, so the game's own UI layout code doesn't drift to screen edges

### 4.5 Cutscene Handling

Pre-rendered cutscenes (VP6/Bink video) are inherently 16:9. Options:
- **Stretch** (default with `present_letterbox = false`) — fills screen but
  distorts video
- **Letterbox cutscenes only** — detect cutscene state and re-enable
  letterboxing during FMVs (requires a cutscene-detection hook)
- **Crop** — zoom the 16:9 video to fill 21:9 (loses top/bottom content)

Most ultrawide patches for games with pre-rendered cutscenes just stretch or
letterbox them. Recommending stretch for now (simplest).

---

## 5. Potential Issues

### 5.1 Geometry Popping / Off-Screen Spawns

Widening the FOV may reveal geometry that was outside the original 16:9
frustum: missing walls, low-LOD models, popping, or enemies spawning in
visible areas. Dante's Inferno has a scripted camera, so this is less
severe than in games with free camera control, but it will happen.

### 5.2 Shadow / Post-Effect Mismatches

If the game renders shadows or post-processing effects (depth of field,
motion blur) using a separate projection matrix or screen-space coordinates
based on 16:9, those effects may be misaligned at ultrawide aspect ratios.

### 5.3 Function Not Generated

If the hook doesn't fire after building, the instruction at `0x826D5C94`
may not be in any generated function. Fix: add `0x826D5C58` to
`[entrypoint.functions]` in the manifest (see section 3.3).

### 5.4 Register Clobbering

The hook replaces `f9` after the `fdivs` instruction. The subsequent
`fmuls f13,f9,f10` at `0x826D5CEC` will use our value. No other instruction
between `0x826D5C94` and `0x826D5CEC` reads or writes `f9`, so this is safe.

---

## 6. Verification Steps

1. Build with the hook and presenter config
2. Launch at 3440x1440 (or windowed 2560x1080 for testing)
3. Check: 3D scene should show more horizontal content (not stretched)
4. Check: characters should look proportionally correct (not fat)
5. Check: HUD elements may be stretched (expected, see 4.4)
6. Test at 32:9 (3840x1080) — more aggressive, more likely to show popping
7. If hook doesn't fire, check runtime logs for "midasm_hook" messages
8. If function not generated, add to manifest and rebuild

---

## 7. File Inventory

### Ghidra project
- `D:\ghidra_dantes_inferno\` — Ghidra project with analyzed `default_basefile.bin`
- `C:\ghidra_scripts\decomp_matrix_builders.txt` — decompiled projection builder + disassembly
- `C:\ghidra_scripts\proj_matrix_callers.txt` — decompiled caller (camera setup)
- `C:\ghidra_scripts\ultrawide_analysis.txt` — alternate projection, stores, constants
- `C:\ghidra_scripts\ultrawide_analysis2.txt` — raw disasm, 1.7777 constant refs
- `C:\ghidra_scripts\matrix_builders.txt` — all 40 matrix builder functions
- `C:\ghidra_scripts\fov_consumers.txt` — all FOV-related register accesses
- `C:\ghidra_scripts\proj_path_analysis.txt` — tanf/cosf/sinf callers

### Key addresses

| Address | What | Significance |
|---------|------|-------------|
| `0x826D5C58` | `FUN_826d5c58` | Perspective projection matrix builder |
| `0x826D5C94` | `fdivs f9,f31,f30` | **Hook point**: aspect ratio = width/height |
| `0x826D5CEC` | `fmuls f13,f9,f10` | m[5] = aspect * cot(fov) |
| `0x825D5578` | `FUN_825d5578` | Camera setup (calls projection builder) |
| `0x821113C8` | `1.7777778f` | Hardcoded 16:9 aspect constant |
| `0x8227FD24` | `lfs f13,0x4d8(r9)` | 16:9 detection (compares runtime vs 1.777) |
| `0x826D5E80` | `FUN_826d5e80` | Orthographic matrix builder (UI/HUD) |
| `0x8294DFB0` | `tanf` | Math library (not recompiled, host-side) |

### ReXGlue SDK references

| File | Purpose |
|------|---------|
| `src/ui/presenter.cpp:549-650` | `RefreshGuestOutput` — sets display aspect ratio |
| `src/ui/presenter.cpp:860-975` | Letterbox/stretch calculation |
| `src/ui/presenter.cpp:32-33` | `present_letterbox` cvar definition |
| `src/codegen/config.cpp:310-369` | `[[midasm_hook]]` parsing |
| `src/codegen/builders/context.cpp:347-400` | `emit_mid_asm_hook` — hook injection |
| `src/codegen/function_graph.cpp:584-598` | Hook before/after instruction dispatch |

---

## 8. Summary

| Question | Answer |
|----------|--------|
| Can ReXGlue do proper ultrawide alone? | **No** — it can set the viewport size but not the projection matrix |
| Where is the aspect ratio computed? | `FUN_826d5c58` @ `0x826D5C58`, instruction `fdivs f9,f31,f30` @ `0x826D5C94` |
| What needs to change? | Replace `f9` (aspect ratio) with host aspect via `midasm_hook` |
| Is the function in generated code? | Likely yes (merged into function at `0x826D5B08`); fallback: add to manifest |
| What about UI/HUD? | Will be stretched; needs separate orthographic hook or sub-viewport |
| What about cutscenes? | Pre-rendered 16:9 video; will be stretched (acceptable) |
| Estimated effort | **Medium** — one hook + presenter config + testing + UI mitigation |
