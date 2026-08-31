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

Known blocker: ReXGlue issue #75 — Dante's Inferno crashes at startup due to
unimplemented VMX/Altivec PPC instructions (v0.1.1). Check if v0.10.0 resolved.

## Current status

- [x] SDK cloned at v0.10.0 (submodules NOT yet initialized - run `setup.ps1`)
- [x] Project scaffolding created from ReXGlue v0.10.0 init templates
- [x] GitHub repo created: https://github.com/florinp93/dantes-inferno (private)
- [x] Game ISO + DLC file placed in disc/ (ISO 7.8GB, DLC is STFS LIVE package)
- [x] Improvement research completed (docs/improvements_plan.md)
- [ ] SDK submodules initialized & CLI built
- [ ] Game ISO extracted into `game/` with `default.xex` entrypoint
- [ ] `rexglue init --force` run to stamp SDK-managed files
- [ ] First successful codegen + build (may hit VMX/Altivec issue #75)
- [ ] Graphics quality cvars configured in OnPreSetup
- [ ] MnK keybind defaults configured in OnPreSetup
- [ ] DLC auto-install hook in OnPostSetup
- [ ] Ultrawide projection hook (requires RE of generated code)
- [ ] Button glyph replacement (requires RE of generated code)
