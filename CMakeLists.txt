# dantes_inferno - ReXGlue Recompiled Project
#
# SDK boilerplate lives in generated/rexglue.cmake.

cmake_minimum_required(VERSION 3.25)
project(dantes_inferno LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

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
