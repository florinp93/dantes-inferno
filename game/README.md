# Place extracted Xbox 360 game files here.
#
# This directory is the `game_root` referenced by dantes_inferno_manifest.toml.
# ReXGlue maps it to the guest path "game:\" at runtime.
#
# After ripping your disc to an ISO:
#   1. Extract the ISO contents into this directory (e.g. with extract-xiso,
#      Xbox Image Browser, or 7-Zip for XISO-format images).
#   2. Ensure the entrypoint executable is at:  game/default.xex
#      (the path set in dantes_inferno_manifest.toml -> [entrypoint].file_path).
#   3. Keep all other game assets (textures, audio, .dll modules, etc.) in
#      their original relative layout under this folder.
#
# NOTHING in this directory should be committed to git (see .gitignore).
# These are copyrighted game assets used locally for the recompilation only.
