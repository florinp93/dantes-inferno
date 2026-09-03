cmake_minimum_required(VERSION 3.25)
project(dantes_inferno LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT MSVC AND CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
    add_compile_options(-mssse3 -msse4.1)
endif()

include(generated/rexglue.cmake)

if(REXSDK_DIR)
    # The generated depfile only tracks the manifest and XEX. Track the ARM VMX
    # backend too so stale scalar code cannot survive an SDK/codegen update.
    add_custom_command(
        OUTPUT "${CMAKE_CURRENT_SOURCE_DIR}/generated/default/codegen.build.stamp"
        APPEND
        DEPENDS
            "${REXSDK_DIR}/src/codegen/builders/vector.cpp"
            "${REXSDK_DIR}/include/rex/ppc/intrinsics.h"
    )
endif()

set(DANTESINFERNO_SOURCES
    src/main.cpp
)

if(WIN32)
    list(APPEND DANTESINFERNO_SOURCES src/dantes_inferno.rc)
    add_executable(dantes_inferno WIN32 ${DANTESINFERNO_SOURCES})
else()
    add_executable(dantes_inferno ${DANTESINFERNO_SOURCES})
endif()

rexglue_setup_target(dantes_inferno GPU_PLUGINS xenos)

if(NOT MSVC AND CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm64|ARM64")
    # ARMv8.4-A is supported by the target SoC without relying on -mcpu=native,
    # which is unsafe under this device's userspace/toolchain combination.
    target_compile_options(dantes_inferno PRIVATE -march=armv8.4-a)
    if(TARGET dantes_inferno_recomp)
        target_compile_options(dantes_inferno_recomp PRIVATE -march=armv8.4-a)
    endif()

    # Optimize across the many generated recompilation translation units.
    include(CheckIPOSupported)
    check_ipo_supported(RESULT DANTESINFERNO_IPO_SUPPORTED OUTPUT DANTESINFERNO_IPO_ERROR)
    if(DANTESINFERNO_IPO_SUPPORTED)
        set_property(TARGET dantes_inferno PROPERTY INTERPROCEDURAL_OPTIMIZATION_RELEASE TRUE)
        if(TARGET dantes_inferno_recomp)
            set_property(TARGET dantes_inferno_recomp
                PROPERTY INTERPROCEDURAL_OPTIMIZATION_RELEASE TRUE)
        endif()
    else()
        message(WARNING "LTO unavailable for dantes_inferno: ${DANTESINFERNO_IPO_ERROR}")
    endif()
endif()

target_include_directories(dantes_inferno PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/rexglue-sdk/thirdparty/imgui"
)

option(DANTESINFERNO_BUILD_LAUNCHER "Build the native Qt launcher" ON)
option(DANTESINFERNO_LAUNCHER_BUILD_TESTS "Build Qt launcher tests" ON)
if(DANTESINFERNO_BUILD_LAUNCHER AND UNIX AND NOT APPLE)
    find_package(Qt6 6.4 COMPONENTS Core Gui Widgets QUIET)
    if(Qt6_FOUND)
        if(DANTESINFERNO_LAUNCHER_BUILD_TESTS)
            enable_testing()
        endif()
        add_subdirectory(launcher-linux)
    else()
        message(WARNING
            "Qt 6.4+ was not found; dantes_inferno_launcher will not be built")
    endif()
endif()
