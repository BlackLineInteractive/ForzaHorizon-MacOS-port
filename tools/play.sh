#!/usr/bin/env bash
# Play the game: no time limit and no scripted input (tools/run_forza.sh is the test
# runner). Extra arguments are passed to the game, e.g. --resolution_scale=2.
#
#   tools/play.sh                 # your profile and progress in ~/.local/share/forza
#   tools/play.sh --xenia [XUID]  # continue your Xenia save (see below)
#
# Profile: the runtime signs in one local profile (XUID B13EBABEBABEBABE) on player 1, and
# every controller drives player 1, so START on any pad gets past the title screen. Saves
# go to ~/.local/share/forza/B13EBABEBABEBABE/4D5309C9/.
#
# --xenia [XUID]: plays with a COPY of your Xenia Canary profile's Forza Horizon save
# (Xenia's content/<XUID>/4D5309C9; the original is never modified). Forza ties its save
# to the profile's XUID, so the game runs signed in with that XUID. The copy lives in
# ~/.local/share/forza/xenia-<XUID>/ and is made once: progress you make here stays there.
# --xenia-refresh copies the Xenia save again (replacing that copy). XUID defaults to the
# only Xenia profile with a Forza Horizon save; Xenia's content folder is
# $FORZA_XENIA_CONTENT (default ~/xenia_canary_windows/content). Installed DLC
# (tools/install_dlc.py) is shared with the normal profile.
#
# Environment: FORZA_BUILD (build dir under forza-recomp/out/build, default linux), REXSDK
# (SDK prefix; default the patched overlay that tools/build_rexglue_sdk.sh makes),
# FORZA_DATA (game files, default extracted/game). The log is ~/.local/share/forza/forza.log.
# Adapted from RecompiledHaloReach's tools/play.sh.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/forza-recomp/out/build/${FORZA_BUILD:-linux}"
DATA="${FORZA_DATA:-$ROOT/extracted/game}"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/forza"
TITLE=4D5309C9
LOCAL_PROFILE=B13EBABEBABEBABE  # the runtime's own profile folder

xenia=0; refresh=0; xuid=""
args=()
while [ $# -gt 0 ]; do
    case "$1" in
        --xenia|--xenia-refresh)
            xenia=1
            [ "$1" = --xenia-refresh ] && refresh=1
            if [ $# -gt 1 ] && [[ "$2" =~ ^[0-9A-Fa-f]{16}$ ]]; then xuid="${2^^}"; shift; fi ;;
        *) args+=("$1") ;;
    esac
    shift
done

[ -x "$BUILD/forza" ] || { echo "no build at $BUILD (see README: Building)" >&2; exit 1; }
[ -f "$DATA/default.xex" ] || { echo "no game files at $DATA (see README: Building, step 2)" >&2; exit 1; }
SDK="${REXSDK:-$HOME/rexglue-sdk-patched-forza/0.10.0.24/linux-amd64}"
[ -d "$SDK/lib" ] || SDK="$HOME/rexglue-sdk-patched/0.10.0.24/linux-amd64"
if [ ! -d "$SDK/lib" ]; then
    echo "patched SDK overlay not found; using the plain nightly (textures may render dark)" >&2
    SDK="$HOME/rexglue-sdk-nightly/0.10.0.24/linux-amd64"
fi
mkdir -p "$DATA_HOME"

if [ "$xenia" = 1 ]; then
    content="${FORZA_XENIA_CONTENT:-$HOME/xenia_canary_windows/content}"
    if [ -z "$xuid" ]; then
        candidates=()
        for d in "$content"/*/"$TITLE"/00000001; do
            [ -d "$d" ] || continue
            p=$(basename "$(dirname "$(dirname "$d")")")
            [ "$p" = 0000000000000000 ] || candidates+=("$p")
        done
        if [ ${#candidates[@]} -ne 1 ]; then
            echo "found ${#candidates[@]} Xenia profiles with a Forza Horizon save in $content;" \
                 "name one: tools/play.sh --xenia <XUID>" >&2
            exit 1
        fi
        xuid="${candidates[0]}"
    fi
    src="$content/$xuid/$TITLE"
    [ -d "$src" ] || { echo "no Forza Horizon save at $src" >&2; exit 1; }
    root="$DATA_HOME/xenia-$xuid"
    dest="$root/$LOCAL_PROFILE/$TITLE"
    if [ "$refresh" = 1 ] || [ ! -d "$dest" ]; then
        rm -rf "$dest"
        mkdir -p "$(dirname "$dest")"
        cp -r "$src" "$dest" || exit 1
        echo "copied the Xenia save of $xuid to $dest"
    fi
    # Installed DLC lives with the normal profile; share it.
    mkdir -p "$DATA_HOME/0000000000000000"
    [ -e "$root/0000000000000000" ] || ln -s ../0000000000000000 "$root/0000000000000000"
    # The shader cache stays shared with the normal profile.
    args=(--user_data_root="$root" --cache_root="$DATA_HOME/cache" --profile_xuid="$xuid" "${args[@]}")
fi

cd "$BUILD"
LD_LIBRARY_PATH="$SDK/lib:$BUILD" ./forza --game_data_root="$DATA" \
    --log_file="$DATA_HOME/forza.log" "${args[@]}"
status=$?
# Guest memory (/dev/shm/xenia_memory_*, 5 GB) is not unlinked when the game is killed.
for shm in /dev/shm/xenia_memory_*; do
    [ -O "$shm" ] || continue
    grep -qs "$(basename "$shm")" /proc/[0-9]*/maps || rm -f -- "$shm"
done
exit $status
