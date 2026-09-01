# Dante's Inferno PC Port - Improvement Plan

Research findings for the three planned enhancement areas, plus game-specific
technical details. Compiled from ReXGlue SDK v0.10.0 source analysis and web
research. All implementation requires `game/default.xex` to be extracted and
codegen to have run first.

---

## 0. Game Technical Profile

| Property | Value | Source |
|----------|-------|--------|
| Engine | Visceral Engine (custom, same as Dead Space) | Polygon, MobyGames |
| Middleware | Havok (physics), Bink Video (cutscenes) | MobyGames credits |
| Resolution | 1280x720 (720p) | Digital Foundry |
| Anti-aliasing | None | Digital Foundry |
| Frame rate | 60 FPS target (30 FPS for cinematics) | Digital Foundry |
| V-sync | Yes | Digital Foundry |
| Title ID | 454108CF | abgx360, verified |
| Assets | EA BIG/VIV archives (BIGFILE0.VIV, etc.) | ZenHAX/Xentax |
| Camera | Automatic/scripted (no manual control) | Official manual |
| Official PC release | Never | - |
| Existing RE tools | Gibbed.Visceral (source-only, incomplete) | GitHub |
| ReXGlue status | v0.10.0: boots, VMX bugs fixed (PR #426) | GitHub |

### Known blocker: VMX/Altivec instructions — RESOLVED
~~ReXGlue issue #75 reports Dante's Inferno crashes at startup due to unimplemented
PPC instructions: `vcmpgtuw`, `vminsw`, `vadduhs`, `lbzux`, `lhaux`, `stbux`,
`stdux`, `stfsux`. These must be resolved (either in the SDK or via patches)
before the recompiled build boots. Check if v0.10.0 has addressed these since
the issue was filed against v0.1.1.~~

**Status:** Resolved. v0.10.0 has full VMX/AltiVec support. The game boots and
runs. Three VMX instruction builder bugs were found and fixed that caused
VP6/Bink FMV corruption — see `docs/vp6_fmv_corruption_fix.md` and upstream
PR [rexglue/rexglue-sdk#426](https://github.com/rexglue/rexglue-sdk/pull/426).

### DLC (Title ID 454108CF)
- Dark Forest (prequel level)
- Trials of St. Lucia (major expansion: co-op, 40 trials, level editor)
- Various costume packs (Isaac Clarke, Florentine Dante, Animated Film Dante)
- Soul packs (free/small/medium/large)
- Devil Pack, Godlike Pack, Relics Triple Pack

### Xbox 360 control scheme
| Input | Action |
|-------|--------|
| Left Stick | Move Dante |
| Right Stick | Dodge/evade (flick direction) |
| A | Jump (double-tap for double-jump) |
| B | Holy Cross (ranged holy attack) |
| X | Light Attack (scythe) |
| Y | Heavy Attack (scythe) |
| LT | Block / combo modifier |
| RT | Grab |
| LB | Magic modifier (hold + face button = cast spell) |
| RB | Interact / context action |
| LB+RB | Redemption Mode (when meter full) |
| Back | Options |
| Start | Systems Menu |
| D-Pad | Not mapped in normal play |

---

## 1. Input: Multi-Controller + Mouse/Keyboard + Glyph Hooking

### 1.1 What ReXGlue already provides

The SDK ships a complete input stack with three driver backends:

- **SDL3** (`src/input/sdl/sdl_input_driver.cpp`) — primary cross-platform backend.
  Supports multiple simultaneous pads, rumble, and SDL's logical gamepad mapping.
  DualShock/DualSense map automatically: Cross→A, Circle→B, Square→X, Triangle→Y.
  Pinned to SDL3 `release-3.4.x` branch.
- **Windows XInput** (`src/input/xinput/xinput_input_driver.cpp`) — loads
  `xinput1_4.dll`, supports 4 slots, Guide button via ordinal 100.
- **Mouse & Keyboard** (`src/input/mnk/mnk_input_driver.cpp`) — maps keyboard/mouse
  to an Xbox 360 controller. Mouse deltas convert to right-stick input. Has
  configurable keybinds via cvars.

The `InputSystem` (`src/input/input_system.cpp`) owns all drivers, assigns
devices to up to 4 guest users via `SlotAssignment` (preserves slots on
disconnect) or `SharedAssignment` (all devices feed user 0). State merging
combines inputs from multiple devices. `ActiveDeviceTracker` records which
device is currently in use.

Guest input routing is through XAM exports (`XamInputGetState`,
`XamInputSetState`, etc.) in `src/kernel/xam/xam_input.cpp`.

### 1.2 What we need to do

**Controller support — mostly configuration, minimal code:**
- Keep `input_backend = "sdl"` as default (covers Xbox, DualShock, DualSense)
- For DualShock 3 on Windows: set `SDL_HINT_JOYSTICK_HIDAPI_PS3_SIXAXIS_DRIVER`
  in `OnPreSetup` (requires DsHidMini or sixaxis.sys driver)
- Supply a `gamecontrollerdb.txt` for nonstandard pads via `hid_mappings_file` cvar
- Multi-controller already works (up to 4 players, stable slot assignment)

**Mouse & Keyboard — configure defaults in `OnPreSetup`:**
The built-in MnK driver has cvars for every keybind. Defaults are unusual for
a PC action game, so we override them. Recommended mapping for Dante's Inferno:

| Action | Xbox | Proposed MnK |
|--------|------|-------------|
| Move | Left stick | WASD |
| Dodge | Right stick flick | Mouse movement |
| Light attack | X | Left mouse |
| Heavy attack | Y | Right mouse |
| Holy Cross | B | R |
| Grab | RT | F |
| Jump | A | Space |
| Block | LT | Left Shift (hold) |
| Magic modifier | LB | Left Ctrl (hold) |
| Interact | RB | E |
| Magic spells | LB+A/B/X/Y | Ctrl+1/2/3/4 |
| D-pad menus | D-pad | Arrow keys |
| Back/Options | Back | Tab |
| Start/Systems | Start | Esc |

Set via cvars in `OnPreSetup`:
```cpp
rex::cvar::SetFlagByName("input_backend", "sdl");
rex::cvar::SetFlagByName("mnk_mode", "true");
rex::cvar::SetFlagByName("mnk_mouse", "true");
rex::cvar::SetFlagByName("keybind_x", "Mouse1");     // light attack
rex::cvar::SetFlagByName("keybind_y", "Mouse2");     // heavy attack
// ... etc
```

Note: Dante's Inferno has a fixed/scripted camera, so mouse = dodge direction
(right stick), NOT camera control. The `mnk_sensitivity` cvar controls the
right-stick conversion scale.

**DualSense adaptive triggers — de-scoped for now:**
SDL3 only exposes these via raw `SDL_SendGamepadEffect`, which conflicts with
rumble. Treat as optional future enhancement.

### 1.3 Button glyph replacement (the hard part)

**Problem:** The game renders Xbox 360 button prompts (A/B/X/Y icons) as
textures. We want to show PlayStation glyphs (Square/Circle/Triangle/Cross) or
keyboard keys when the user is playing with those input methods. We must NOT
ship original game files.

**No built-in texture replacement API exists** in ReXGlue v0.10.0. Four
strategies, ordered by feasibility:

| Strategy | Effort | Notes |
|----------|--------|-------|
| A. `update:` overlay | Low | Put replacement textures in `update_data_root`. Only works if game reads from `update:` paths. |
| B. Custom VFS overlay device | Medium | Implement a `rex::filesystem::Device` that checks `metadata/glyphs/` first, falls back to `game:` device. Register before main `HostPathDevice`. |
| C. Host-side UI overlay | Medium | Use `rex::ui::ImmediateDrawer` to draw replacement glyphs on top. Requires knowing screen positions of prompts. |
| D. `midasm_hook` on glyph function | Hard, most correct | RE the game's glyph-selection function, hook it to redirect to our textures or host renderer. |

**Active device detection — needs small SDK patch:**
`InputSystem` tracks the active device internally (`ActiveDeviceTracker`) but
doesn't expose it publicly. We need either:
- A small SDK patch adding `GetActiveDeviceInfo(user_index)` to `InputSystem`, OR
- A user-facing `glyph_family` cvar (`xbox`/`playstation`/`mnk`/`auto`)

**Glyph art storage:** Replacement PNGs go in `metadata/glyphs/{xbox,playstation,mnk}/`.
Use `rexglue_embed_metadata` to bundle them. Never put them under `game/`.

**Workflow to identify glyph textures:**
1. Extract the game, build, run with `--log_level=trace`
2. Use RenderDoc or the debug overlay to capture which textures are button glyphs
3. Search `.VIV` archives for UI texture names (Gibbed.Visceral may help)
4. Choose strategy B or D based on how the game loads them

---

## 2. Graphics: Resolution Scaling, AA, Texture Filtering

### 2.1 Three independent resolution concepts

ReXGlue distinguishes three resolutions that must not be conflated:

1. **Guest video mode** (`video_mode_width/height` or `resolution` cvar):
   Changes what `VdQueryVideoMode()` returns and the startup window size.
   Does NOT change internal rendering. Accepts presets like `1080p`, `1440p`,
   `4k`, or explicit `WIDTHxHEIGHT`.

2. **Internal draw resolution** (`resolution_scale` or `draw_resolution_scale_x/y`):
   Scales the emulated Xenos render targets, EDRAM, viewport/scissor. Opaque to
   the game (it still thinks it's rendering at 720p). Integer-only (1-7, clamped
   by device capabilities). Requires restart.

3. **Presentation output size**: Determined by the host swapchain/window. The
   presenter upscales the guest output to fill the window using bilinear, CAS,
   FSR, or (experimentally) FSR2/3.

### 2.2 Resolution scaling — implementation

**Cvars** (defined in `src/graphics/pipeline/texture/cache.cpp:66-78`):
```cpp
resolution_scale          // shared X+Y scale, range 1-8, requires restart
draw_resolution_scale_x   // per-axis, range 1-8, requires restart
draw_resolution_scale_y   // per-axis, range 1-8, requires restart
```

Clamped to `kMaxDrawResolutionScaleAlongAxis` (7). The D3D12 backend further
clamps based on device tiled-resource/virtual-address limits
(`D3D12TextureCache::ClampDrawResolutionScaleToMaxSupported`).

The scale propagates through: render target cache, EDRAM tile geometry, viewport
(`draw_util::GetHostViewportInfo` multiplies by scale), scissor, texture
coordinate shader compensation (`draw_resolution_scaled_texture_offsets` cvar).

**Set in `OnPreSetup`:**
```cpp
REXCVAR_SET(resolution_scale, 2);  // 2x internal = 2560x1440 from 1280x720
```

**Artifact mitigation cvars** (if scaling causes issues):
- `half_pixel_offset` (default true)
- `resolve_resolution_scale_fill_half_pixel_offset` (default true)
- `draw_resolution_scaled_texture_offsets` (default true)

### 2.3 Anti-aliasing — FXAA is available, MSAA is not forceable

**FXAA (available now):**
```cpp
REXCVAR_SET(swap_post_effect, "fxaa");  // or "fxaa_extreme"
```
Compute-based post-process in `D3D12CommandProcessor::IssueSwap`. Applies gamma
ramp → FXAA → output to guest-output texture. Requires restart.

**MSAA — cannot force higher than the game uses:**
The Xenos GPU exposes 1x/2x/4x MSAA. ReXGlue preserves this. Forcing 8x would
require changes across EDRAM layout, pipeline cache keys, shader sample
patterns, resolve shaders, and depth/stencil transfer — high risk, not
recommended. Dante's Inferno uses **no MSAA** on Xbox 360, so the game itself
requests 1x.

**TAA/FSR2/FSR3 — experimental:**
The presenter exposes `fsr2`/`fsr3` but they're documented as experimental
("limited temporal inputs in the presenter path"). The presenter has no
authoritative depth or motion vectors. Not production-ready without significant
backend work.

### 2.4 Texture filtering — anisotropic override

**Cvar** (defined in `src/graphics/pipeline/texture/cache.cpp:52-64`):
```cpp
anisotropic_override  // -1=no override, 0=off, 1=1x, 2=2x, 3=4x, 4=8x, 5=16x
```
Default is 3 (4x). Hot-reloadable (no restart needed).

**Eligibility** (D3D12 sampler creation, `texture_cache.cpp:969-987`):
Only applies to textures that have mipmaps, use linear min/mag filtering, and
use bilinear/trilinear mip filtering. Point-sampled UI textures and
non-mipmapped textures are NOT affected (protects guest semantics).

**Set in `OnPreSetup`:**
```cpp
REXCVAR_SET(anisotropic_override, 5);  // 16x anisotropic
```

### 2.5 Output upscaling (FidelityFX CAS/FSR)

Enable at build time: `-DREXGLUE_ENABLE_FIDELITYFX=ON`

Then use:
```cpp
REXCVAR_SET(present_effect, "fsr");  // or "cas"
```
The presenter applies the effect chain when painting the guest output to the
swapchain. FSR EASU/RCAS for upscaling + sharpening. Multi-pass for >2x.
`present_cas_additional_sharpness` and `present_fsr_sharpness_reduction` tune
the effect. The FidelityFX DLL is auto-staged next to the exe at build time.

### 2.6 Recommended quality configuration

**Safe tier (no rebuild):**
```toml
resolution_scale = 2
anisotropic_override = 5
swap_post_effect = "fxaa"
```

**High-quality tier (FidelityFX build):**
```toml
resolution_scale = 2
anisotropic_override = 5
swap_post_effect = "fxaa"
present_effect = "fsr"
present_fsr_sharpness_reduction = 0.5
present_dither = true
```

All set in `OnPreSetup` (before GPU backend initialization) or via
`dantes_inferno.toml` config file next to the exe.

### 2.7 Where to set cvars

`OnPreSetup(rex::RuntimeConfig&)` is the correct hook — it runs before the GPU
plugin loads and before D3D12 command processor construction. `OnPostSetup` is
too late (caches already built). `OnConfigurePaths` is for data paths only.

---

## 3. Ultrawide Support (21:9 / 32:9)

### 3.1 The core problem

Simply changing the swapchain/window size stretches a 16:9 image. Correct
ultrawide requires TWO changes:
1. **Projection matrix**: widen horizontal FOV (Hor+ approach)
2. **Presentation**: fill the ultrawide display without pillarboxing

### 3.2 What ReXGlue provides

- D3D12 viewport is derived from Xenos register state (`PA_CL_VPORT_*`,
  `PA_SC_WINDOW_*`), not hardcoded 1280x720. Any change to guest viewport
  registers is picked up automatically.
- Swapchain size is independent from guest output size.
- The presenter already does aspect-preserving letterboxing/stretching via
  `present_letterbox` cvar (default true).
- `video_mode_width`/`video_mode_height` / `resolution` cvars set the guest
  display aspect that `VdQueryVideoMode()` reports.
- `midasm_hook` support for per-instruction C++ injection.

### 3.3 Recommended strategy: Hor+ anamorphic render

1. **Patch the projection matrix** to use the host aspect ratio instead of 16:9
   (via `midasm_hook` at the game's projection-setup function)
2. **Leave the guest render buffer at 16:9** (e.g. 1280x720, or scaled with
   `resolution_scale`)
3. **Set `video_mode_width/height`** to the host resolution (e.g. 3440x1440)
4. **Set `present_letterbox = false`** so the presenter stretches the anamorphic
   16:9 image to fill the host surface
5. Because the projection was built for the host aspect, the final image is
   geometrically correct — more horizontal content is visible, no stretching

This mirrors how Xenia Canary widescreen patches work.

### 3.4 Projection math

For a perspective matrix (`D3DXMatrixPerspectiveFovLH`):
```
m00 = cot(fovY/2) / aspect
m11 = cot(fovY/2)
```

Hor+ (keep vertical FOV, expand horizontally):
```
m00_new = m00_old * (a0 / a1)
```
where `a0 = 16/9` (original), `a1 = host_width / host_height` (runtime).

Or if the game stores an aspect-ratio float, replace it with `a1`.

| Target | Aspect | FOV multiplier |
|--------|--------|----------------|
| 16:9 | 1.778 | 1.0 (baseline) |
| 21:9 | 2.333 | 1.3125 |
| 32:9 | 3.556 | 2.0 |
| 2560x1080 | 2.370 | use runtime w/h |
| 3440x1440 | 2.389 | use runtime w/h |

### 3.5 Implementation via midasm_hook

**Manifest syntax** (note: v0.10.0 uses `[[midasm_hook]]`, NOT `[[mid_asm_hooks]]`):
```toml
# config/ultrawide_hooks.toml (user-owned, survives rexglue init --force)
[[midasm_hook]]
address = 0x82000000   # placeholder — must be found via RE
name = "DantesInfernoProjectionHook"
registers = ["r3", "f1"]
after_instruction = true
```

Include via the manifest:
```toml
[entrypoint]
includes = ["config/ultrawide_hooks.toml"]
```

**Hook function** (in `src/ultrawide_hooks.h`):
```cpp
#pragma once
#include <rex/ppc/context.h>

inline void DantesInfernoProjectionHook(PPCRegister& r3, PPCRegister& f1) {
  constexpr float target_aspect = 3440.0f / 1440.0f;
  f1.f32 = target_aspect;  // replace aspect float
}
```

**Force-include the header** for generated code (in `CMakeLists.txt`):
```cmake
rexglue_setup_target(dantes_inferno)
target_compile_options(dantes_inferno_recomp PRIVATE
    "-include${CMAKE_CURRENT_SOURCE_DIR}/src/ultrawide_hooks.h"
)
```

### 3.6 HUD/UI handling

Ultrawide breaks 2D HUD elements (stretching, edge drift). Recommendations:
- **First pass**: patch projection only for gameplay 3D camera, leave menus/
  cutscenes at 16:9 (requires identifying which projection function is
  gameplay-only)
- **Second pass**: if the engine has a separate UI projection matrix, patch the
  world matrix but leave UI at 16:9, or render UI into a centered 16:9 viewport
- Lock cutscenes to 16:9 by default (like Sonic Unleashed Recompiled does)
- Dante's Inferno has a scripted camera, so no right-stick camera to break, but
  widened FOV may reveal popping geometry, missing effects, or off-screen spawns

### 3.7 RE workflow (requires game files)

After codegen, search `generated/default/*.cpp` for:
- Float constants near `1.777777` or `16.0f/9.0f`
- Integers `1280` / `720`
- `D3DXMatrixPerspectiveFovLH` or engine equivalents
- VMX `vmsum*` / `vmadd*` blocks assembling 4x4 matrices
- Code writing `PA_CL_VPORT_*` or calling D3D9 `SetViewport`

No public Xenia Canary widescreen patch exists for Dante's Inferno, so we must
find the addresses ourselves.

### 3.8 Recommended code structure

```
src/
  ultrawide_config.h        # runtime aspect policy, modes
  ultrawide_math.h          # aspect / FOV / matrix helpers
  ultrawide_hooks.h/.cpp    # hook functions called from generated code
  ultrawide_runtime.h/.cpp  # current host window size, mode toggles
config/
  ultrawide_hooks.toml      # [[midasm_hook]] entries
```

---

## 4. Implementation Priority & Dependencies

```
Phase 0: Get the game booting — COMPLETE
  ✓ Extract ISO → game/default.xex
  ✓ Run setup.ps1 (init SDK submodules)
  ✓ Build rexglue CLI
  ✓ rexglue init --force
  ✓ Build & run — VMX/Altivec issue #75 resolved in v0.10.0
  ✓ VP6 FMV corruption fixed (vpkuwus aliasing, vmsum3fp128 mask, pack unpackhi)
  ✓ SDK patches submitted upstream as PR #426

Phase 1: Graphics quality (lowest effort, highest impact) — NEXT
  └─ Set resolution_scale, anisotropic_override, swap_post_effect in OnPreSetup
  └─ Optionally build with FidelityFX for FSR output upscaling
  └─ No RE required — pure cvar configuration

Phase 2: Input configuration
  └─ Set MnK keybind defaults in OnPreSetup
  └─ Configure SDL backend, gamecontrollerdb.txt
  └─ Test DualShock/DualSense/Xbox controllers
  └─ No RE required — pure cvar configuration

Phase 3: DLC auto-install
  └─ Add OnPostSetup hook to scan dlc/ folder
  └─ Call ContentManager::InstallContent() on each STFS package
  └─ No RE required — uses existing SDK API

Phase 4: Ultrawide support (requires RE)
  └─ Search generated code for projection matrix setup
  └─ Identify PPC address and register usage
  └─ Create midasm_hook with aspect-ratio patch
  └─ Handle HUD/UI separately (gameplay vs cutscenes)
  └─ Test 21:9 and 32:9

Phase 5: Button glyph replacement (requires RE)
  └─ Identify how game loads/displays button glyph textures
  └─ Choose strategy: VFS overlay, host overlay, or midasm_hook
  └─ Create replacement glyph art in metadata/glyphs/
  └─ Patch InputSystem to expose active device (or use glyph_family cvar)
  └─ Test with all input methods

Phase 6: Installer (final distribution)
  └─ Build installer that asks for ISO + DLC folder
  └─ Extract XISO to game/ folder
  └─ Copy DLC STFS files to dlc/ folder
  └─ No STFS logic in installer — game exe handles DLC install at startup
```

---

## 5. Key ReXGlue files referenced

| Area | File | Purpose |
|------|------|---------|
| Input drivers | `src/input/sdl/sdl_input_driver.cpp` | SDL3 gamepad backend |
| | `src/input/xinput/xinput_input_driver.cpp` | Windows XInput backend |
| | `src/input/mnk/mnk_input_driver.cpp` | Mouse & keyboard backend |
| Input system | `src/input/input_system.cpp` | Driver management, device assignment |
| Input routing | `src/kernel/xam/xam_input.cpp` | Guest-facing XAM input exports |
| Resolution scale | `src/graphics/pipeline/texture/cache.cpp:66-78` | Cvar definitions |
| | `src/graphics/d3d12/command_processor.cpp:912-942` | D3D12 cache construction |
| Viewport | `src/graphics/util/draw.cpp:164-498` | Xenos→D3D12 viewport translation |
| | `src/graphics/d3d12/command_processor.cpp:2428-2452` | Viewport cache + application |
| AA (FXAA) | `src/graphics/graphics_system.cpp:34-36` | swap_post_effect cvar |
| | `src/graphics/d3d12/command_processor.cpp:1995-2237` | FXAA compute pass |
| Texture filtering | `src/graphics/pipeline/texture/cache.cpp:52-64` | anisotropic_override cvar |
| | `src/graphics/d3d12/texture_cache.cpp:969-987` | D3D12 sampler creation |
| Presenter | `src/ui/presenter.cpp:43-78` | present_effect cvars |
| | `src/ui/d3d12/d3d12_presenter.cpp` | D3D12 presenter implementation |
| FidelityFX | `cmake/rexglue_fidelityfx.cmake` | FSR/CAS build integration |
| DLC/Content | `src/system/xam/content_manager.cpp:572-644` | InstallContent (STFS extraction) |
| | `include/rex/system/xam/content_manager.h:183` | InstallContent declaration |
| VFS | `src/system/runtime.cpp:294-358` | SetupVfs (game:/d:/update: mounts) |
| App hooks | `include/rex/rex_app.h` | ReXApp virtual hooks |
| | `src/ui/rex_app.cpp:86-103` | App lifecycle order |
| midasm hooks | `src/codegen/config.cpp:310-369` | Manifest parser (uses [[midasm_hook]]) |
| | `src/codegen/builders/context.cpp:347-420` | Hook call emission |
| STFS | `include/rex/filesystem/devices/stfs_xbox.h` | STFS header structures |
| | `src/filesystem/devices/stfs_container_device.cpp` | STFS container device |
