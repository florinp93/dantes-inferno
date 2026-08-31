#!/usr/bin/env bash
# setup.sh - Bootstrap the Dante's Inferno ReXGlue port project (Linux/macOS).
#
# Clones the ReXGlue SDK into thirdparty/rexglue-sdk at the pinned version and
# initializes its nested submodules. Safe to re-run.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sdk_dir="$root/thirdparty/rexglue-sdk"
tag="v0.10.0"

echo "== Dante's Inferno - ReXGlue project setup =="

# --- Prerequisite checks -----------------------------------------------------
for tool in git cmake ninja clang; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "MISSING: $tool not found on PATH." >&2
        echo "  ReXGlue requires: Clang 18+, CMake 3.25+, Ninja." >&2
        exit 1
    fi
done
echo "Prerequisites OK."

# --- Clone / update SDK ------------------------------------------------------
if [ -d "$sdk_dir/.git" ]; then
    echo "SDK already cloned at $sdk_dir"
else
    echo "Cloning ReXGlue SDK ($tag) into thirdparty/rexglue-sdk ..."
    git clone --branch "$tag" --depth 1 https://github.com/rexglue/rexglue-sdk.git "$sdk_dir"
fi

echo "Initializing SDK submodules (this can take a while) ..."
git -C "$sdk_dir" submodule update --init --recursive --depth 1

echo ""
echo "Setup complete."
echo "Next steps:"
echo "  1. Extract your Xbox 360 ISO into ./game/ (entrypoint at game/default.xex)"
echo "  2. Build the SDK CLI:  cmake --preset linux-amd64-release -DREXSDK_DIR=thirdparty/rexglue-sdk && cmake --build out/build/linux-amd64-release --target rexglue"
echo "  3. Regenerate SDK-managed files:  rexglue init --force --project_name dantes_inferno --project_root . --xex_path game/default.xex --game_root game"
echo "  4. Configure & build the port:    cmake --preset linux-amd64-release -DREXSDK_DIR=thirdparty/rexglue-sdk && cmake --build out/build/linux-amd64-release"
