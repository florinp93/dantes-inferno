# AGENTS.md - Project guide for AI agents

## Project

Static recompilation port of **Dante's Inferno** (Xbox 360) to native PC using
the ReXGlue SDK (v0.10.0). ReXGlue translates PowerPC XEX -> C++ ahead of time.

## Key paths

- `dantes_inferno_manifest.toml` - ReXGlue project manifest (SDK-managed; regen with `rexglue init --force`)
- `generated/rexglue.cmake` - SDK build boilerplate (auto-generated, DO NOT EDIT)
- `generated/default/` - codegen output (gitignored, produced during build)
- `src/dantes_inferno_app.h` - **user-owned** app class; override ReXApp hooks here
- `src/main.cpp` - entry point (SDK-managed, preserved on first init only)
- `game/` - extracted Xbox 360 game files (gitignored, copyrighted - never commit)
- `thirdparty/rexglue-sdk/` - SDK clone (gitignored, via setup.ps1)
- `docs/rexglue_notes.md` - ReXGlue workflow & command reference

## Build commands (Windows)

```powershell
# One-time: build the rexglue CLI from the SDK
cmake --preset win-amd64-release -DREXSDK_DIR=thirdparty\rexglue-sdk
cmake --build out\build\win-amd64-release --target rexglue

# Regenerate SDK-managed files (requires game/default.xex present)
rexglue init --force --project_name dantes_inferno --project_root . --xex_path game\default.xex --game_root game

# Build the port (codegen runs automatically as a build dependency)
cmake --preset win-amd64-release -DREXSDK_DIR=thirdparty\rexglue-sdk
cmake --build out\build\win-amd64-release
```

Run: `out\win-amd64\Release\dantes_inferno.exe`

## Toolchain

- Clang 18+ required (NOT MSVC/GCC). Detected: Clang 22 at `C:\Program Files\LLVM\bin\clang.exe`
- CMake 3.25+, Ninja, Visual Studio 2022 (Windows SDK for D3D12)
- C++23, D3D12 graphics backend on Windows

## Conventions

- `src/dantes_inferno_app.h` is the ONLY place for custom app behavior. Do not
  edit `main.cpp` or `generated/rexglue.cmake` - they are SDK-managed and get
  overwritten by `rexglue init`/`rexglue migrate`.
- For per-instruction custom C++ injection, use `[[mid_asm_hooks]]` in the
  manifest (see docs/rexglue_notes.md).
- Game assets under `game/` are copyrighted and gitignored. Never commit them.
- The SDK under `thirdparty/rexglue-sdk/` is gitignored; re-clone via `setup.ps1`.

## Naming

Project name `dantes_inferno` -> snake_case `dantes_inferno`, PascalCase
`DantesInferno`, UPPER `DANTESINFERNO`. CMake target: `dantes_inferno`.

## Improvement plan

See `docs/improvements_plan.md` for full research findings. Summary:

1. **Graphics quality** (Phase 1, no RE): resolution_scale, anisotropic_override,
   swap_post_effect=fxaa cvars in OnPreSetup. Optionally FidelityFX FSR build.
2. **Input config** (Phase 2, no RE): SDL backend + MnK keybind defaults in
   OnPreSetup. DualShock/DualSense/Xbox all supported via SDL3.
3. **DLC auto-install** (Phase 3, no RE): OnPostSetup hook scans dlc/ folder,
   calls ContentManager::InstallContent() on each STFS package.
4. **Ultrawide** (Phase 4, requires RE): midasm_hook on projection matrix to
   patch aspect ratio. Hor+ anamorphic render strategy.
5. **Button glyphs** (Phase 5, requires RE): replace game's button prompt
   textures based on active input device. Needs SDK patch for device detection
   or glyph_family cvar. Glyph art in metadata/glyphs/.
6. **Installer** (Phase 6): asks user for ISO + DLC folder, extracts to game/
   and dlc/. No STFS logic in installer.

~~Known blocker: ReXGlue issue #75 — Dante's Inferno crashes at startup due to
unimplemented VMX/Altivec PPC instructions (v0.1.1).~~ **Resolved in v0.10.0.**
Game boots and runs. VMX builder bugs causing FMV corruption were found and
fixed (see `docs/vp6_fmv_corruption_fix.md`).

## SDK patches

The SDK under `thirdparty/rexglue-sdk/` has local patches to
`src/codegen/builders/vector.cpp` that fix three VMX instruction builder bugs.
These fixes are submitted upstream as
[rexglue/rexglue-sdk#426](https://github.com/rexglue/rexglue-sdk/pull/426).
Full technical documentation: `docs/vp6_fmv_corruption_fix.md`.

If the SDK is re-cloned, these patches must be re-applied. The fixes are:

1. **`vpkuwus` / `vpkuhus` in-place aliasing** (root cause of FMV corruption):
   Element-by-element packing loops aliased the destination's narrowed array
   with the source's wider array. Replaced with SSE intrinsics.
2. **`vmsum3fp128` dot product mask** (`0xEF` → `0x7F`): Wrong broadcast
   pattern in the SSE `dp_ps` imm8 mask.
3. **Pack builder `unpackhi_epi64` removal**: Pack builders discarded half
   the packed elements via `unpackhi_epi64`. Removed and operand-swapped for
   byte reversal.

## Build & run notes

- The executable loads `rexgpu-xenos.dll` from its own directory, not from
  the SDK output. After rebuilding the SDK, copy:
  `thirdparty\rexglue-sdk\out\win-amd64\rexgpu-xenos.dll` →
  `out\build\win-amd64-release\rexgpu-xenos.dll`
- Always launch with `--game_data_root=game` from the project root.
- Runtime logs are in `out\build\win-amd64-release\logs\`.
- After changing SDK codegen builders, delete the stale generated files to
  force regeneration:
  `Remove-Item generated\default\dantes_inferno_recomp.{7,95,23,94}.cpp -Force`

## Current status

- [x] SDK cloned at v0.10.0
- [x] Project scaffolding created from ReXGlue v0.10.0 init templates
- [x] GitHub repo created: https://github.com/florinp93/dantes-inferno (private)
- [x] Game ISO + DLC file placed in disc/ (ISO 7.8GB, DLC is STFS LIVE package)
- [x] Improvement research completed (docs/improvements_plan.md)
- [x] SDK submodules initialized & CLI built
- [x] Game ISO extracted into `game/` with `default.xex` entrypoint
- [x] `rexglue init --force` run to stamp SDK-managed files
- [x] First successful codegen + build
- [x] VMX/AltiVec issue #75 resolved (v0.10.0 has full VMX support)
- [x] VP6/Bink FMV corruption diagnosed and fixed (docs/vp6_fmv_corruption_fix.md)
- [x] SDK patches submitted upstream (PR #426)
- [ ] Graphics quality cvars configured in OnPreSetup
- [ ] MnK keybind defaults configured in OnPreSetup
- [ ] DLC auto-install hook in OnPostSetup
- [ ] Ultrawide projection hook (requires RE of generated code)
- [ ] Button glyph replacement (requires RE of generated code)
