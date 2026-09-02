<p align="center">
  <img src="assets/banner.png" alt="Dante's Inferno - PC Recomp Project" width="100%" />
</p>

<p align="center">
  <a href="https://ko-fi.com/zerkiller">
    <img src="https://img.shields.io/badge/Ko--Fi-Buy%20me%20a%20coffee-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Ko-fi" />
  </a>
  <a href="https://github.com/florinp93">
    <img src="https://img.shields.io/badge/Other-Projects-0AB4F5?style=for-the-badge&logo=github&logoColor=white" alt="Other Projects" />
  </a>
</p>

# Dante's Inferno - Xbox 360 to PC Port (ReXGlue)

A static recompilation port of **Dante's Inferno** (Xbox 360) to native PC,
built with the [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk).

ReXGlue converts Xbox 360 PowerPC XEX executables into portable C++ that runs
natively on Windows (D3D12) and Linux (Vulkan) - no emulation, no JIT at
runtime. This project contains the port configuration, custom hooks, and build
scaffolding; the ReXGlue SDK itself lives under `thirdparty/`.

## Project layout

```
.
├── CMakeLists.txt                 # Build config (SDK-managed, regenerate w/ rexglue init --force)
├── CMakePresets.json              # Platform build presets (SDK-managed)
├── dantes_inferno_manifest.toml   # ReXGlue project manifest (SDK-managed)
├── generated/
│   ├── rexglue.cmake              # SDK boilerplate (auto-generated, DO NOT EDIT)
│   └── default/                   # codegen output (gitignored, built on demand)
├── src/
│   ├── main.cpp                   # App entry point (SDK-managed)
│   └── dantes_inferno_app.h       # App class - override hooks here (user-owned)
├── game/                          # Extracted Xbox 360 game files (gitignored)
│   └── default.xex                #   <- entrypoint XEX goes here
├── metadata/                      # Achievement icons / embedded metadata
├── thirdparty/
│   └── rexglue-sdk/               # ReXGlue SDK (cloned via setup script, gitignored)
├── docs/
│   └── rexglue_notes.md           # ReXGlue workflow & command reference
├── setup.ps1 / setup.sh           # Clone SDK + init submodules
└── .gitignore
```

## Prerequisites

- **Windows 10/11 x64** (this project targets Windows/D3D12)
- **Clang 18+** (LLVM/Clang)
- **CMake 3.25+**
- **Ninja** build system
- **Visual Studio 2022** (for the Windows SDK / D3D12 headers)

## Getting started

### 1. Set up the SDK

```powershell
.\setup.ps1
```

This clones the ReXGlue SDK (pinned to `v0.10.0`) into `thirdparty/rexglue-sdk`
and initializes its submodules.

### 2. Provide the game files

Extract your ripped Xbox 360 ISO into `game/`. The entrypoint executable must be
at `game/default.xex` (the path set in `dantes_inferno_manifest.toml`). Keep the
original directory layout for all other assets.

> **Do not commit anything under `game/`** - it contains copyrighted assets used
> locally for recompilation only.

### 3. Build the SDK CLI (one time)

```powershell
cmake --preset win-amd64-release -DREXSDK_DIR=thirdparty\rexglue-sdk
cmake --build out\build\win-amd64-release --target rexglue
```

Add the built `rexglue.exe` to your PATH (it lives under
`thirdparty\rexglue-sdk\out\win-amd64\Release\`).

### 4. Regenerate SDK-managed files

Once `game/default.xex` exists, regenerate the SDK-managed scaffolding so it
carries the exact version/build stamp:

```powershell
rexglue init --force --project_name dantes_inferno --project_root . --xex_path game\default.xex --game_root game
```

### 5. Configure & build the port

```powershell
cmake --preset win-amd64-release -DREXSDK_DIR=thirdparty\rexglue-sdk
cmake --build out\build\win-amd64-release
```

The build automatically runs `rexglue codegen` (translating the XEX to C++) the
first time and whenever inputs change. Output: `out\win-amd64\Release\dantes_inferno.exe`.

### 6. Run

```powershell
.\out\win-amd64\Release\dantes_inferno.exe
# Useful flags:
#   --log_level=trace     verbose logging
#   --log_file=run.log    write logs to file
```

## Customizing the port

Override virtual hooks in `src/dantes_inferno_app.h` (e.g. `OnPostSetup`,
`OnCreateDialogs`, `OnConfigurePaths`). That file is **user-owned** and
preserved across `rexglue init` / `rexglue migrate`. See
`docs/rexglue_notes.md` for the full hook list and workflow reference.

## License

This repository contains only port scaffolding and configuration. The ReXGlue
SDK is licensed under the BSD 3-Clause License (see `thirdparty/rexglue-sdk/`).
Dante's Inferno and all game assets are property of their respective rights
holders; nothing under `game/` is distributed here.
