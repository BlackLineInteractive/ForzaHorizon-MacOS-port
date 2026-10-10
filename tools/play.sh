#!/usr/bin/env bash
# Play the game: no time limit and no scripted input (tools/run_forza.sh is the test
# runner). Extra arguments are passed to the game, e.g. --resolution_scale=2.
#
# Environment: FORZA_BUILD (build dir under forza-recomp/out/build, default linux),
# REXSDK (SDK prefix; default the patched overlay that tools/build_rexglue_sdk.sh makes),
# FORZA_DATA (game files, default extracted/game). The log is ~/.local/share/forza/forza.log.
# Adapted from RecompiledHaloReach's tools/play.sh.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/forza-recomp/out/build/${FORZA_BUILD:-linux}"
DATA="${FORZA_DATA:-$ROOT/extracted/game}"
[ -x "$BUILD/forza" ] || { echo "no build at $BUILD (see README: Building)" >&2; exit 1; }
[ -f "$DATA/default.xex" ] || { echo "no game files at $DATA (see README: Building, step 2)" >&2; exit 1; }
SDK="${REXSDK:-$HOME/rexglue-sdk-patched-forza/0.10.0.24/linux-amd64}"
if [ ! -d "$SDK/lib" ]; then
    echo "patched SDK overlay not found at $SDK; using the plain nightly" >&2
    SDK="$HOME/rexglue-sdk-nightly/0.10.0.24/linux-amd64"
fi
LOG_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/forza"
mkdir -p "$LOG_DIR"
cd "$BUILD"
LD_LIBRARY_PATH="$SDK/lib:$BUILD" ./forza --game_data_root="$DATA" \
    --log_file="$LOG_DIR/forza.log" "$@"
status=$?
# Guest memory (/dev/shm/xenia_memory_*, 5 GB) is not unlinked when the game is killed.
for shm in /dev/shm/xenia_memory_*; do
    [ -O "$shm" ] || continue
    grep -qs "$(basename "$shm")" /proc/[0-9]*/maps || rm -f -- "$shm"
done
exit $status
