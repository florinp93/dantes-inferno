# ReXGlue Reference Notes

Condensed reference for the ReXGlue SDK (v0.10.0) as used by this port.
Source: https://github.com/rexglue/rexglue-sdk and its wiki
(https://mintlify.wiki/rexglue/rexglue-sdk). Full doc index:
https://mintlify.com/rexglue/rexglue-sdk/llms.txt

## What ReXGlue is

A **static recompilation toolkit** for Xbox 360 executables. Instead of
interpreting/JIT-compiling PowerPC at runtime (like Xenia), it generates C++
source code **ahead of time** that compiles with standard toolchains (Clang 18+)
and runs natively. Inspired by XenonRecomp and rexdex's recompiler. Built on
Xenia's foundations.

Supported platforms:
| Platform | Arch    | Graphics | Status |
|----------|---------|----------|--------|
| Windows  | x64     | D3D12    | Supported (this port) |
| Linux    | x64     | Vulkan   | Supported |
| macOS    | ARM64/x64 | Metal  | Not supported |

## Workflow (4 phases)

1. **Init**    - `rexglue init` scaffolds the project (requires the XEX present)
2. **Configure** - edit the manifest TOML (function hints, hooks, modules)
3. **Codegen** - `rexglue codegen <manifest>` analyzes XEX -> C++ in `generated/`
4. **Build**   - CMake + Clang compiles generated C++ + runtime -> native EXE

Codegen also runs automatically as a CMake build dependency
(`dantes_inferno_codegen` target), re-running only when inputs change.

## CLI commands

```
rexglue init        Initialize a new project (requires --project_name, --xex_path)
rexglue codegen <manifest.toml>   Analyze XEX and generate C++
rexglue migrate     Update SDK-managed files to current SDK version
rexglue init module             Add a guest DLL module to the manifest
rexglue init achievements       Extract XDBF achievements + icons from a XEX
rexglue recompile-tests         Generate Catch2 tests from PPC assembly
```

### rexglue init (v0.10.0 - manifest-first flow)

```
rexglue init --project_name <name> --project_root <dir> --xex_path <xex> [--game_root <dir>]
             [--scan_dlls] [--template_dir <dir>] [--force]
```

- `--xex_path` is REQUIRED and must exist on disk (the entrypoint XEX).
- `--game_root` defaults to the XEX's parent dir; must contain the XEX.
- `--scan_dlls` walks `game_root` for `.dll` files and adds them as `[[modules]]`.
- `--force` overwrites `RequiresForce` files (CMakeLists.txt, manifest, presets).

Generated files (v0.10.0):
| File | Policy | Notes |
|------|--------|-------|
| `CMakeLists.txt` | RequiresForce | overwritten only with --force |
| `CMakePresets.json` | RequiresForce | overwritten only with --force |
| `<name>_manifest.toml` | RequiresForce | overwritten only with --force |
| `generated/rexglue.cmake` | AlwaysRegenerate | SDK boilerplate, DO NOT EDIT |
| `src/main.cpp` | FirstInitOnly | preserved after first init |
| `src/<name>_app.h` | FirstInitOnly | preserved (user-owned customization point) |

### rexglue codegen

```
rexglue codegen <manifest.toml> [--force] [--enable_exception_handlers]
               [--log_level=trace|debug|info|warn|error] [--log_file=<path>]
```

Output in `generated/<xex_stem>/`:
- `<name>_config.h` - constants (PPC_CODE_BASE, PPC_CODE_SIZE, etc.)
- `<name>_init.h` / `<name>_init.cpp` - function table / mappings
- `sources.cmake` - list of generated sources for CMake
- `sub_<addr>.cpp` - one file per discovered function
- `codegen.d` / `codegen.build.stamp` - depfile + stamp for incremental builds
- `dll_targets.cmake` - (if modules) shared-lib targets for guest DLLs

## Manifest TOML (v0.10.0 format)

```toml
[project]
name = "dantes_inferno"
sdk_version = "0.10.0"
game_root = "game"            # maps to guest path "game:\"

[entrypoint]
file_path = "game/default.xex"
out_directory_path = "generated/default"
includes = []                 # extra include dirs for generated code

[[modules]]                   # optional guest DLL modules
guest_path = "game:\\game\\foo.dll"
file_path = "game/foo.dll"
out_directory_path = "generated/foo"
includes = []

# Manual function overrides (optional)
[[functions]]
address = 0x82000100
name = "GameMain"             # optional, defaults to sub_<addr>
size = 0x500                  # use size OR end, not both
# end = 0x82000600           # exclusive end address
# parent = 0x82000000        # for discontinuous chunks

# Jump table hints for switch statements (optional)
[[switch_tables]]
address = 0x82001000
targets = [0x82001020, 0x82001040]

# Mid-assembly hooks - inject custom C++ at a PPC address (advanced)
[[mid_asm_hooks]]
address = 0x82002000
name = "OnPlayerSpawn"
registers = ["r3", "r4"]
ret = true
```

### Codegen options (in manifest or older config TOML)

- `skip_lr` - skip link register tracking (default false)
- `skip_msr` - skip machine state register (default false)
- `ctr_as_local_variable` - promote CTR to local (default false)
- `xer_as_local_variable` - promote XER to local (default false)
- `cr_registers_as_local_variables` - promote CR fields (default false)
- `non_volatile_registers_as_local_variables` - promote saved regs (default false)
- `generate_exception_handlers` - wrap functions in SEH (Windows, default false)
- `max_jump_extension` - bytes to extend function for jump targets (default 65536)
- `data_region_threshold` - invalid instrs to mark data (default 16)
- `large_function_threshold` - warn size (default 1048576)

## Runtime architecture

- **Processor** (`rex::runtime::Processor`) - execution state, module loading
- **KernelState** (`rex::system::KernelState`) - threads, sync primitives, VFS,
  object table, module loading/symbol resolution
- **Memory** (`rex::memory::Memory`) - 512MB at fixed base `0x100000000` (x64),
  big-endian, page tables, MMIO. (ASan incompatible; UBSan OK.)
- **Graphics** - D3D12 (Windows) / Vulkan (Linux); command list + shader translation
- **Platform** - Win32/GTK windowing, XInput/evdev input, XAudio2/PulseAudio audio

## ReXApp customization (user-owned `src/dantes_inferno_app.h`)

Override these virtual hooks:
- `OnPostInitLogging()`
- `OnPreSetup(rex::RuntimeConfig& config)`
- `OnLoadXexImage(std::string& xex_image)`
- `OnPostLoadXexImage()`
- `OnPostSetup()`
- `OnCreateDialogs(rex::ui::ImGuiDrawer* drawer)`
- `CreateAchievementsOverlay() -> std::unique_ptr<rex::ui::ImGuiDialog>`
- `CreateAchievementNotificationDialog()`
- `OnShutdown()`
- `OnConfigurePaths(rex::PathConfig& paths)`

`REX_DEFINE_APP(name, CreateFn)` provides the platform entry point
(WinMain on Windows, main on Linux).

## CMake integration

Two ways to consume the SDK:
1. **Subdirectory** (this project): `set(REXSDK_DIR ...)` then
   `add_subdirectory(${REXSDK_DIR})` (done inside `generated/rexglue.cmake`).
2. **Installed package**: `find_package(rexglue CONFIG)`.

`rexglue_setup_target(<target>)` (in `generated/rexglue.cmake`) wires up:
- the `<target>_recomp` OBJECT library of generated sources
- the `dantes_inferno_codegen` custom target/command (runs `rexglue codegen`)
- `rex::runtime` linking, PCH, SEH/async-exception flags, metadata embedding

Configure with a preset + SDK path:
```
cmake --preset win-amd64-release -DREXSDK_DIR=thirdparty/rexglue-sdk
cmake --build out/build/win-amd64-release
```

## Runtime flags

```
dantes_inferno --log_level=trace --log_file=run.log --gpu_backend=d3d12
```

## Troubleshooting

- **codegen 'file not found'**: check `file_path` in manifest resolves to a real XEX.
- **'GENERATED_SOURCES not found'**: run codegen first (or just build - it's a dep).
- **Runtime crash**: `--log_level=trace --log_file=crash.log`; check missing assets,
  bad function boundaries, insufficient virtual address space.
- **Graphics wrong**: try the other backend, enable RenderDoc, report with screenshots.
- **CMake 'Clang required'**: SDK enforces Clang 18+; set
  `-DCMAKE_CXX_COMPILER=clang++` explicitly.

## Reference projects

- demo-iruka: https://github.com/rexglue/demo-iruka (simple demo)
- reblue: https://github.com/rexglue/reblue (full game recompilation)
