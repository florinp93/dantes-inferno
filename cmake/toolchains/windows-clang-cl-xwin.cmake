# windows-clang-cl-xwin.cmake
#
# Cross-compile toolchain: build the Windows (x64/D3D12) target of this
# project natively on Linux, using clang-cl targeting x86_64-pc-windows-msvc
# against a Windows SDK + MSVC CRT snapshot fetched by `xwin`
# (https://github.com/Jake-Shadle/xwin). No Wine/Proton/VM involved in the
# build itself - Proton only comes in afterwards, to *run* the resulting .exe.
#
# Setup (one-time):
#   cargo install xwin --locked
#   XWIN_ACCEPT_LICENSE=1 xwin --accept-license --cache-dir ~/.local/opt/xwin-cache \
#       splat --output ~/.local/opt/xwin-sdk
#
# Usage:
#   cmake -S . -B out/build/win-cross -G Ninja \
#       -DCMAKE_TOOLCHAIN_FILE=cmake/toolchains/windows-clang-cl-xwin.cmake \
#       -DXWIN_SDK_PATH=$HOME/.local/opt/xwin-sdk \
#       -DREXSDK_DIR=thirdparty/rexglue-sdk \
#       -DCMAKE_BUILD_TYPE=Release
#   cmake --build out/build/win-cross
#
# XWIN_SDK_PATH may also be supplied via the XWIN_SDK_PATH environment
# variable instead of a -D cache variable.

set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR AMD64)

if(NOT XWIN_SDK_PATH)
    if(DEFINED ENV{XWIN_SDK_PATH})
        set(XWIN_SDK_PATH "$ENV{XWIN_SDK_PATH}")
    else()
        set(XWIN_SDK_PATH "$ENV{HOME}/.local/opt/xwin-sdk")
    endif()
endif()

if(NOT EXISTS "${XWIN_SDK_PATH}/sdk/include/um")
    message(FATAL_ERROR
        "XWIN_SDK_PATH (${XWIN_SDK_PATH}) doesn't look like an xwin splat output "
        "(missing sdk/include/um). Run `xwin splat --output ${XWIN_SDK_PATH}` "
        "or pass -DXWIN_SDK_PATH=<path>.")
endif()

set(CMAKE_C_COMPILER clang-cl)
set(CMAKE_CXX_COMPILER clang-cl)
set(CMAKE_C_COMPILER_TARGET x86_64-pc-windows-msvc)
set(CMAKE_CXX_COMPILER_TARGET x86_64-pc-windows-msvc)
set(CMAKE_LINKER lld-link)
set(CMAKE_AR llvm-lib)

# Resource compiler for src/dantes_inferno.rc.
find_program(CMAKE_RC_COMPILER
    NAMES llvm-rc llvm-rc-22 llvm-rc-18
    HINTS "$ENV{HOME}/.local/opt/llvm-mingw/bin" /usr/lib64/llvm22/bin /usr/bin
)

# No working mt.exe/llvm-mt is available here (the ROCm-bundled llvm-mt was
# built without libxml2 and can't merge manifests). CMake only invokes MT
# to embed the UAC/DPI manifest under incremental linking; disabling both
# sidesteps that step entirely rather than requiring a manifest tool.
#
# Library search paths: real per-target link steps call lld-link directly
# (CMake's Windows-Clang(MSVC) platform module, via `cmake -E vs_link_exe`),
# so these flags reach lld-link verbatim - no need for a "-link" separator
# there. The dash-prefixed `-libpath:` spelling (vs. `/libpath:`) matters
# because these same _INIT flags are also echoed into CMake's one-shot
# ABI-detection try_compile, where clang-cl itself is the link driver: a
# slash-prefixed unrecognized flag with an embedded quoted path there gets
# parsed as an input filename and hard-fails, while the dash-prefixed form
# is safely warned-and-ignored (dash flags forward to the linker without a
# `-link` separator only in the two-step target-build path, but that's fine
# since lld-link accepts both `/` and `-` prefixes identically anyway).
set(_xwin_libpath_flags
    "-libpath:\"${XWIN_SDK_PATH}/crt/lib/x86_64\" -libpath:\"${XWIN_SDK_PATH}/sdk/lib/um/x86_64\" -libpath:\"${XWIN_SDK_PATH}/sdk/lib/ucrt/x86_64\""
)
set(CMAKE_EXE_LINKER_FLAGS_INIT "/MANIFEST:NO /INCREMENTAL:NO ${_xwin_libpath_flags}")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "/MANIFEST:NO /INCREMENTAL:NO ${_xwin_libpath_flags}")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "/MANIFEST:NO /INCREMENTAL:NO ${_xwin_libpath_flags}")

set(_xwin_includes
    "${XWIN_SDK_PATH}/crt/include"
    "${XWIN_SDK_PATH}/sdk/include/ucrt"
    "${XWIN_SDK_PATH}/sdk/include/um"
    "${XWIN_SDK_PATH}/sdk/include/shared"
    "${XWIN_SDK_PATH}/sdk/include/winrt"
    "${XWIN_SDK_PATH}/sdk/include/cppwinrt"
)
set(_xwin_flags "")
foreach(_inc ${_xwin_includes})
    string(APPEND _xwin_flags " -imsvc \"${_inc}\"")
endforeach()

# Matches the SDK's own windows-base preset (CMakePresets.json), which we
# can't use directly here since it's gated to hostSystemName == Windows.
set(CMAKE_C_FLAGS_INIT "-march=x86-64-v2${_xwin_flags}")
# The SDK's own build passes -fno-char8_t (GNU/clang++ driver spelling,
# since the official presets build with plain clang++, not clang-cl) so a
# few source files rely on u8"..." literals implicitly decaying to
# std::string_view/const char*. clang-cl doesn't recognize that spelling
# (silently ignores it) - /Zc:char8_t- is the cl-style equivalent.
set(CMAKE_CXX_FLAGS_INIT "-march=x86-64-v2 /Zc:char8_t-${_xwin_flags}")

# lld-link (and real link.exe) resolve libraries via the LIB environment
# variable, same as cl.exe resolves headers via INCLUDE - this is far more
# reliable across CMake's try_compile/ABI-detection steps than hand-rolling
# /libpath: flags on the top-level clang-cl driver line, which only forwards
# raw linker syntax when it follows a literal "-link" argument.
set(ENV{LIB} "${XWIN_SDK_PATH}/crt/lib/x86_64;${XWIN_SDK_PATH}/sdk/lib/um/x86_64;${XWIN_SDK_PATH}/sdk/lib/ucrt/x86_64")

# clang-cl (binary literally named clang-cl) is auto-detected by CMake as an
# MSVC-frontend Clang; no need to force CMAKE_*_COMPILER_ID/FRONTEND_VARIANT
# by hand - doing so skips CMake's normal detection and breaks the
# Windows-Clang(MSVC) platform module selection.

set(CMAKE_FIND_ROOT_PATH "${XWIN_SDK_PATH}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
