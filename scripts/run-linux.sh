#!/usr/bin/env bash
# Standalone Linux/Proton launcher for dantes_inferno.exe. Copy this next to
# the built exe (or set DANTES_HOME below) along with its DLLs and game/.
# See docs/linux-cross-compile.md for the full story behind every choice
# made here.
set -euo pipefail

HERE="${DANTES_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
PROTON="${PROTON:-}"

if [ -z "$PROTON" ]; then
  # Try to find the newest GE-Proton under Steam's compatibilitytools.d.
  compat_dir="$HOME/.local/share/Steam/compatibilitytools.d"
  if [ -d "$compat_dir" ]; then
    PROTON=$(find "$compat_dir" -maxdepth 2 -iname proton -type f 2>/dev/null | sort -V | tail -1)
  fi
fi

if [ -z "$PROTON" ] || [ ! -x "$PROTON" ]; then
  echo "Proton not found. Set PROTON=/path/to/proton (a GE-Proton build works well)."
  exit 1
fi

[ -e "$HERE/dantes_inferno.exe" ] || { echo "dantes_inferno.exe not found in $HERE"; exit 1; }
[ -e "$HERE/game/default.xex" ] || { echo "game/default.xex missing under $HERE/game"; exit 1; }

# The prefix lives next to the game, not in /tmp, so it survives a reboot.
export STEAM_COMPAT_DATA_PATH="$HERE/prefix"
export STEAM_COMPAT_CLIENT_INSTALL_PATH="${STEAM_COMPAT_CLIENT_INSTALL_PATH:-$HOME/.local/share/Steam}"
mkdir -p "$STEAM_COMPAT_DATA_PATH"

# Optional: FPS overlay + a CSV log, with  MANGOHUD=1 ./run-linux.sh
if [ "${MANGOHUD:-0}" = 1 ]; then
  mkdir -p "$HERE/fpslog"
  export MANGOHUD=1
  export MANGOHUD_CONFIG="${MANGOHUD_CONFIG:-output_folder=$HERE/fpslog,autostart_log=1,log_duration=0,log_interval=100}"
fi

# game_data_root MUST be a CLI flag, not dantes_inferno.toml - see
# docs/linux-cross-compile.md §3. Absolute path required.
#
# render_target_path_d3d12 is deliberately left UNSET (the default RTV/DSV
# path). Forcing rov (as the C# launcher and src/dantes_inferno_app.h's own
# comment recommend, to avoid FMV corruption) instead corrupts general
# gameplay rendering on Linux/vkd3d-proton - see docs/linux-cross-compile.md
# §3 for the measured trade-off and the real FMV fix (a vector-instruction
# recompiler bug, docs/vp6_fmv_corruption_fix.md / upstream PR #426).
GAME_ARGS=(
  "--game_data_root=$HERE/game"
  "--draw_resolution_scale_x=2"
  "--draw_resolution_scale_y=2"
  "--anisotropic_override=5"
  "--native_2x_msaa=true"
  "--present_dither=true"
)

# Proton's first invocation only builds the prefix and exits, so run twice.
first_run=0
[ -d "$STEAM_COMPAT_DATA_PATH/pfx" ] || first_run=1

# An ABSOLUTE path is required here - a relative one fails with "Failed to
# create process: 2" and writes no log at all.
"$PROTON" run "$HERE/dantes_inferno.exe" "${GAME_ARGS[@]}" "$@" || true

if [ "$first_run" = 1 ]; then
  echo "Prefix created. Starting the game..."
  exec "$PROTON" run "$HERE/dantes_inferno.exe" "${GAME_ARGS[@]}" "$@"
fi
