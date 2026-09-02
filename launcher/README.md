# Dante's Inferno - Hell's Gate Launcher & Installer

C# WPF (.NET Framework 4.0) launcher and installer for the ReXGlue PC port.

## Projects

- `DantesInferno.Shared` - common config parsing, TOML read/write, GitHub release updater.
- `DantesInfernoLauncher` - settings launcher that writes `dantes_inferno.toml` and starts the game.
- `DantesInfernoInstaller` - wizard that extracts the user's ISO, copies the port files, and creates a desktop shortcut.

## Building

Requires Visual Studio 2022 Community (or Build Tools) with .NET Framework 4.0 reference assemblies.

```powershell
cd launcher
.\package-release.ps1
```

`package-release.ps1` builds the solution and assembles `..\launcher-release\DantesInferno\`.

It expects the C++ ReXGlue game to already be built at `..\out\build\win-amd64-release`:

```powershell
cmake --preset win-amd64-release -DREXSDK_DIR=thirdparty\rexglue-sdk
cmake --build out\build\win-amd64-release
```

## Release layout

```
DantesInferno/
  DantesInfernoInstaller.exe   # installer
  DantesInferno.Shared.dll
  extract-xiso.exe
  dist/
    dantes_inferno.exe
    rexruntime.dll
    rexgpu-xenos.dll
    DantesInfernoLauncher.exe
    DantesInferno.Shared.dll
    icon.ico
    icon.png
    version.txt
```

Distribute the folder or the generated `DantesInferno-Release.zip`.

## Launcher settings

The launcher edits `dantes_inferno.toml` next to `dantes_inferno.exe` and launches the game with `--game_data_root=<install>\game`.

Exposed cvars:

- `resolution` - screen resolution preset
- `video_mode_refresh_rate` + `vsync` - frame cap / VSync
- `anisotropic_override` - 16x anisotropic filtering
- `swap_post_effect` - FXAA / FXAA Extreme
- `native_2x_msaa` - native MSAA
- `fullscreen` - fullscreen toggle
- `render_target_path_d3d12` - set to `rov` for FMV stability
- `input_backend` - SDL for broad gamepad support

`resolution_scale` is present in the UI but currently disabled due to a known ReXGlue bug.

## Auto-updater

The launcher checks `https://api.github.com/repos/florinp93/dantes-inferno/releases/latest` and compares the release `tag_name` to the local `version.txt`. The repository must be public for unauthenticated checks.

## Installer flow

1. Ask for destination folder.
2. Ask for the Dante's Inferno Xbox 360 ISO.
3. Extract the ISO into `<dest>\game` using `extract-xiso.exe`.
4. Copy `dist\*` into `<dest>`.
5. Write a default `dantes_inferno.toml` and `version.txt`.
6. Create a desktop shortcut pointing to `DantesInfernoLauncher.exe`.

The installer must be distributed with a `dist` folder next to it (or run through `package-release.ps1`).
