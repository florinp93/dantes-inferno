# dantes_inferno - ReXGlue Recompiled Project
#
# SDK boilerplate lives in generated/rexglue.cmake.

cmake_minimum_required(VERSION 3.25)
project(dantes_inferno LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Ensure SSE4.1 (implies SSSE3) for all targets including SDK libraries
if(NOT MSVC AND CMAKE_SYSTEM_PROCESSOR MATCHES "x86_64|AMD64")
    add_compile_options(-mssse3 -msse4.1)
endif()

include(generated/rexglue.cmake)

# Sources
set(DANTESINFERNO_SOURCES
    src/main.cpp
)

if(WIN32)
    add_executable(dantes_inferno WIN32 ${DANTESINFERNO_SOURCES})
else()
    add_executable(dantes_inferno ${DANTESINFERNO_SOURCES})
endif()

rexglue_setup_target(dantes_inferno)

# rexruntime links rexui/imgui PRIVATE, but rex/rex_app.h includes rex/ui/*
# which requires imgui's include directory. Add it directly.
target_include_directories(dantes_inferno PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/thirdparty/rexglue-sdk/thirdparty/imgui"
)
