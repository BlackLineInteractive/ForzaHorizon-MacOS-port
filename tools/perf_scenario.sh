#!/usr/bin/env bash
# Scripted performance scenarios with frame statistics (RECOMP_PERF, docs/perf.md).
#
# Usage: tools/perf_scenario.sh SCENARIO DIR [cold|warm] [extra forza flags...]
#   menu      boot, title screen, START, main menu (about 2 minutes)
#   drive     a profile that has not finished the prologue: main menu, Single Player,
#             the intro video, then the opening drive at full throttle (about 4 minutes)
#   freeroam  a profile in free roam: main menu, Single Player, 90 s of free roam
#             driving (use FORZA_XUID and --user_data_root for a copied save)
#   cold      runs with an empty shader cache (--cache_root=DIR/cache_cold); warm (default)
#             uses the normal one.
# Prints the PERF lines (one per 10 s window and source) and leaves the log in DIR.
# Uses tools/live_session.sh, so the memory check and pad isolation apply.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCENARIO="$1"; DIR="$2"; CACHE="${3:-warm}"
shift 3 2>/dev/null || shift $#
mkdir -p "$DIR"
extra=()
if [ "$CACHE" = cold ]; then
    rm -rf "$DIR/cache_cold"; mkdir -p "$DIR/cache_cold"
    extra+=(--cache_root="$DIR/cache_cold")
fi
export RECOMP_PERF=1 RECOMP_PERF_SCENE=boot RECOMP_PERF_CSV="$DIR/frames.csv"
"$ROOT/tools/live_session.sh" "$DIR" 600 "${extra[@]}" "$@" > /dev/null || exit 1
fifo="$DIR/in.fifo"
say() { echo "$1" > "$fifo"; }
alive() { kill -0 "$(cat "$DIR/pid")" 2>/dev/null; }
wait_s() { local end=$((SECONDS + $1)); while [ $SECONDS -lt $end ] && alive; do sleep 1; done; }

wait_s 45; say SCENE:title; wait_s 10
say START; wait_s 8; say SCENE:main_menu; wait_s 30
case "$SCENARIO" in
    menu) ;;
    drive)
        say A; say SCENE:intro_video; wait_s 100
        say SCENE:drive
        for _ in $(seq 1 12); do say RT:5; wait_s 5; done ;;
    freeroam)
        say A; say SCENE:loading; wait_s 40
        say SCENE:freeroam
        for _ in $(seq 1 18); do say RT:5; wait_s 5; done ;;
    *) echo "unknown scenario $SCENARIO" >&2 ;;
esac
say SCENE:end; wait_s 2
kill -INT "$(cat "$DIR/pid")" 2>/dev/null
wait_s 15
grep -h "PERF: scene=" "$DIR/forza.log" | sed 's/^.*PERF: /PERF: /'
for shm in /dev/shm/xenia_memory_*; do
    [ -O "$shm" ] || continue
    grep -qs "$(basename "$shm")" /proc/[0-9]*/maps || rm -f -- "$shm"
done
