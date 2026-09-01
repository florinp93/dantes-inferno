# Headless Stress Test Report

Generated: 2026-09-02T00:17:53
Harness log: `D:\Zerk Cloud\Dante's Inferno\test\headless_test_run.log`

## Summary

- Runs: **2**
- Crashes: **1**
- True hangs (no log progress at timeout): **0**
- Running normally at timeout (game loop, not a bug): **1**
- Clean / non-zero exits: **0**

## Runtime configuration

The recompiled `dantes_inferno.exe` was launched with these cvars (every ReXGlue cvar is auto-exposed as a `--cvar=value` CLI flag):

| Flag | Purpose |
|------|---------|
| `--headless` | Skips XAM UI dialogs so automation never blocks on a guest MessageBox. |
| `--audio_mute` | Disables audio output. |
| `--no-vsync` | Unlocks the guest vblank worker to ~1000 Hz guest tick (closest available to a 'turbo' mode; the SDK has no `--turbo`/`--framerate 0`/`--no-render` flag). |
| `--window_width=320 --window_height=180` | Smallest viable window. A window is always created on Windows (SDL3); the SDK has no display-less mode. |
| `--log_level=trace --log_file=...` | Full trace logging for post-crash analysis. |
| `--game_data_root=game` | Resolves the guest `game:\` VFS to `./game`. |

Input coverage (Option A — monkey testing): a background thread posted semi-randomized `WM_KEYDOWN`/`WM_MOUSEMOVE` events to the game window via `PostMessageW`. The app's MnK driver (enabled in `src/dantes_inferno_app.h`) translates these into a virtual Xbox 360 controller, exercising real gameplay/input paths. Scene/level warp iteration (Option B) was **not** used because it requires reverse engineering of the generated game code (per `AGENTS.md`, RE work is still pending).

Crash interception: the harness attached as a Win32 debugger (`DEBUG_PROCESS`) and called `MiniDumpWriteDump` at the first fatal exception, recording the NT status code, faulting address, and (via the `minidump` package) the faulting module.

## Per-run results

| Run | Outcome | Exit code | Duration | Exc. code | Exc. address | Faulting module | Monkey actions |
|-----|---------|-----------|----------|-----------|--------------|-----------------|----------------|
| 0 | running_at_timeout | 0x00000000 | 45.8s | 0xC0000005 | 0x00007FF794DB2DC4 | - | 115 |
| 1 | crash | 0xFFFFFFFF | 4.7s | 0xC0000005 | 0x00007FF794DB2DC4 | - | 11 |

## Bugs found

### Bug 1: Crash — run 1

- **Reproduction:** run `python tools/headless_stress_test.py --runs 1 --duration 34`; the failure surfaced after ~5s of monkey input.
- **Exit code:** `crash: NT status 0xFFFFFFFF`
- **Exception:** ACCESS_VIOLATION (`0xC0000005`) at address `0x00007FF794DB2DC4`
- **Thread count at crash:** 57
- **Minidump:** `D:\Zerk Cloud\Dante's Inferno\test\minidumps\run_1.dmp` (open with WinDbx/cdb: `cdb -z D:\Zerk Cloud\Dante's Inferno\test\minidumps\run_1.dmp`)
- **Run log:** `D:\Zerk Cloud\Dante's Inferno\test\run_1.log`
- **Last 60 log lines before termination:**
  ```
  [2026-09-02 00:17:50.998] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:50.998] [debug] [krnl] [t24456] XAudioSubmitRenderDriverFrame: driver=41550000 samples=7006E730
  [2026-09-02 00:17:50.998] [debug] [apu] [t24456] AudioSystem::SubmitFrame called: index=0 samples_ptr=7006E730
  [2026-09-02 00:17:50.998] [debug] [apu] [t24456] SDLAudioDriver::SubmitFrame: frame_ptr=7006E730 queued_count=7
  [2026-09-02 00:17:50.998] [debug] [apu] [t24456] AudioWorker: callback returned for client 0
  [2026-09-02 00:17:50.998] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000002
  [2026-09-02 00:17:50.998] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:51.001] [debug] [gpu] [t21700] Created a 320x2048 4xMSAA depth render target with guest format 0 at EDRAM base 1624
  [2026-09-02 00:17:51.005] [debug] [gpu] [t21700] Created a 640x4096 1xMSAA color render target with guest format 0 at EDRAM base 1440
  [2026-09-02 00:17:51.008] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000002
  [2026-09-02 00:17:51.008] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:51.008] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000002
  [2026-09-02 00:17:51.008] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:51.008] [debug] [gpu] [t21700] Created a 320x2048 4xMSAA depth render target with guest format 0 at EDRAM base 1440
  [2026-09-02 00:17:51.013] [trace] [gpu] [t21700] Resolve: 0,0 <= x,y < 640,360, kD24S8 -> k_24_8 at 0x0A733000 (potentially modified memory range 0x0A733000 to 0x0A8FF000)
  [2026-09-02 00:17:51.018] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000002
  [2026-09-02 00:17:51.018] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:51.018] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000002
  [2026-09-02 00:17:51.018] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:51.028] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000002
  [2026-09-02 00:17:51.028] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:51.028] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000002
  [2026-09-02 00:17:51.029] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:51.030] [trace] [gpu] [t21700] Make 0A733000 -> 0A914000 (1970176b) coherent, action = VC | TC
  [2026-09-02 00:17:51.032] [trace] [gpu] [t21700] Make 1F690000 -> 1FC90000 (6291456b) coherent, action = VC
  [2026-09-02 00:17:51.032] [trace] [gpu] [t21700] Resolve: 0,0 <= x,y < 640,360, k_8_8_8_8 -> k_8_8_8_8 at 0x0AE77000 (potentially modified memory range 0x0AE77000 to 0x0B043000)
  [2026-09-02 00:17:51.032] [trace] [gpu] [t21700] Make 0AE77000 -> 0B058000 (1970176b) coherent, action = VC | TC
  [2026-09-02 00:17:51.033] [trace] [gpu] [t21700] Make 1F690000 -> 1FC90000 (6291456b) coherent, action = VC
  [2026-09-02 00:17:51.033] [trace] [gpu] [t21700] Resolve: 0,0 <= x,y < 1280,720, kD24S8 -> k_24_8 at 0x0A733000 (potentially modified memory range 0x0A733000 to 0x0AACB000)
  [2026-09-02 00:17:51.033] [trace] [gpu] [t21700] Make 0A733000 -> 0AACC000 (3772416b) coherent, action = VC | TC
  [2026-09-02 00:17:51.033] [trace] [gpu] [t21700] Make 1F690000 -> 1FC90000 (6291456b) coherent, action = VC
  [2026-09-02 00:17:51.034] [debug] [gpu] [t21700] Created a 480x1368 4xMSAA depth render target with guest format 0 at EDRAM base 720
  [2026-09-02 00:17:51.034] [trace] [gpu] [t21700] Resolve: 0,0 <= x,y < 960,960, kD24S8 -> k_24_8 at 0x0B78A000 (potentially modified memory range 0x0B78A000 to 0x0BE74000)
  [2026-09-02 00:17:51.038] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000002
  [2026-09-02 00:17:51.038] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:51.038] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000002
  [2026-09-02 00:17:51.038] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:51.039] [trace] [gpu] [t21700] Make 0B78A000 -> 0BE93000 (7376896b) coherent, action = VC | TC
  [2026-09-02 00:17:51.039] [trace] [gpu] [t21700] Make 1F690000 -> 1FC90000 (6291456b) coherent, action = VC
  [2026-09-02 00:17:51.039] [debug] [gpu] [t21700] Created a 80x8192 1xMSAA color render target with guest format 14 at EDRAM base 1440
  [2026-09-02 00:17:51.041] [trace] [gpu] [t21700] Resolve: 0,0 <= x,y < 64,8, k_32_FLOAT -> k_32_FLOAT at 0x0B46C000 (potentially modified memory range 0x0B46C000 to 0x0B46E000)
  [2026-09-02 00:17:51.046] [trace] [gpu] [t21700] Make 0B46C000 -> 0B46F000 (12288b) coherent, action = VC | TC
  [2026-09-02 00:17:51.046] [trace] [gpu] [t21700] Make 1F690000 -> 1FC90000 (6291456b) coherent, action = VC
  [2026-09-02 00:17:51.046] [trace] [gpu] [t21700] Make 00001000 -> 00001000 (0b) coherent, action = N/A
  [2026-09-02 00:17:51.047] [debug] [gpu] [t21700] Created a 1280x2048 1xMSAA depth render target with guest format 0 at EDRAM base 0
  [2026-09-02 00:17:51.047] [trace] [gpu] [t21700] Created tiled 640x360x1 2D k_8_8_8_8 texture with 1 unpacked mip level, base at 0x0AE77000 (pitch 1280, size 0x001CC000), mips at 0x00000000 (size 0x00000000)
  [2026-09-02 00:17:51.047] [trace] [gpu] [t21700] Loaded tiled 640x360x1 2D k_8_8_8_8 texture with 1 unpacked mip level, base at 0x0AE77000 (pitch 1280, size 0x001CC000), mips at 0x00000000 (size 0x00000000)
  [2026-09-02 00:17:51.047] [info] [gpu] [t21700] [GPU VP6 SamplerDesc] fc=0: U=2 V=2 W=3 Border=[0.00,0.00,0.00,0.00] Filter=20 MinLOD=0 MaxLOD=0.25
  [2026-09-02 00:17:51.048] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000002
  [2026-09-02 00:17:51.048] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:51.048] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000002
  [2026-09-02 00:17:51.048] [debug] [apu] [t18984] XMA: Write to unknown register (0601): 00000003
  [2026-09-02 00:17:51.048] [trace] [gpu] [t21700] Resolve: 0,0 <= x,y < 1280,720, k_8_8_8_8 -> k_8_8_8_8 at 0x0AE77000 (potentially modified memory range 0x0AE77000 to 0x0B20F000)
  [2026-09-02 00:17:51.049] [trace] [gpu] [t21700] Make 0AE77000 -> 0B210000 (3772416b) coherent, action = VC | TC
  [2026-09-02 00:17:51.049] [trace] [gpu] [t21700] Loaded tiled 1280x720x1 2D k_8_8_8_8 texture with 1 unpacked mip level, base at 0x0AE77000 (pitch 1280, size 0x00398000), mips at 0x00000000 (size 0x00000000)
  [2026-09-02 00:17:51.049] [trace] [gpu] [t21700] Resolve: 0,0 <= x,y < 1280,720, k_8_8_8_8 -> k_8_8_8_8 at 0x0A39A000 (potentially modified memory range 0x0A39A000 to 0x0A732000)
  [2026-09-02 00:17:51.049] [trace] [gpu] [t21700] Make 0A39A000 -> 0A733000 (3772416b) coherent, action = VC | TC
  [2026-09-02 00:17:51.049] [trace] [gpu] [t21700] Make 1F690000 -> 1FC90000 (6291456b) coherent, action = VC
  [2026-09-02 00:17:51.050] [trace] [gpu] [t21700] Loaded tiled 1280x720x1 2D k_8_8_8_8 texture with 1 unpacked mip level, base at 0x0A39A000 (pitch 1280, size 0x00398000), mips at 0x00000000 (size 0x00000000)
  [2026-09-02 00:17:51.050] [info] [gpu] [t21700] [GPU VP6 Swap] frontbuffer_ptr=0xA39A000 format=6 dim=1280x720 swap_resource=0x2143f513b10 swap_desc_dim=1280x720
  ```

**Recommended fix / next step:**

- Access violation. Cross-reference the faulting address with the generated function map in `generated/default/dantes_inferno_init.h` (the `sub_<addr>` table) to identify the guest function. If the address is inside `dantes_inferno.exe`, check the corresponding `generated/default/sub_<addr>.cpp` for a missed branch target or an unimplemented intrinsic; add a `[[mid_asm_hooks]]` entry or a function override in the manifest if needed. If inside `rexgpu-xenos.dll`, inspect the D3D12 command-processor path (see `docs/vp6_fmv_corruption_fix.md` for a prior example of a VMX/EDRAM bug in the same area).

## Tooling notes & limitations

- **No `--turbo` / `--framerate 0` / `--no-render` flag exists** in ReXGlue v0.10.0. `--no-vsync` is the only available frame-rate unlock (it sets the guest vblank worker to a 1 ms interval). A true headless/no-render mode would require an SDK change to skip window creation in `ReXApp::SetupPresentation` and run the graphics system on the offscreen provider path.
- **No PDB is produced** for the release build, so minidump stack frames cannot be symbolicated in-process. The harness records the exception code, faulting address, and faulting module; for full symbolic stacks, rebuild with `-DCMAKE_BUILD_TYPE=RelWithDebInfo` (or enable `generate_exception_handlers` in the manifest) and open the `.dmp` with `cdb -z <dump>`.
- **xvfb is not applicable** on Windows; the SDL3 windowing layer always creates a window. The harness uses a 320x180 window and posts input in the background via `PostMessageW` so the test does not hijack the foreground.
