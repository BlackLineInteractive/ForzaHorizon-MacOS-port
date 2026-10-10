#!/usr/bin/env bash
# Load free roam from a fresh copy of a Xenia save N times and report faults.
#
# Usage: tools/repro_freeroam.sh WORKDIR [N] [LABEL]
#   Each run copies $FORZA_XENIA_CONTENT/<XUID>/4D5309C9 (default
#   ~/xenia_canary_windows/content/E030000004B490FA; the original is only read) into
#   WORKDIR/ud/B13EBABEBABEBABE/, starts the game with tools/live_session.sh, presses START
#   at 45 s and A (Single Player) at 57 s, then watches the log for up to 2 minutes for an
#   unhandled fault or a PHYSCHECK line (src/hooks/physics_loader_check.cpp). Prints one
#   line per run; faulting logs are kept as WORKDIR/LABEL_fault_N.log.
#   Environment (FORZA_PHYS_SEED, ...) passes through to the game. Link
#   WORKDIR/ud/0000000000000000 to the installed DLC (<data>/0000000000000000) beforehand
#   if the save needs it. Kills only the processes it started.
# Written for the free-roam physics fault (docs/PROJECT.md).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
W="$(mkdir -p "$1" && cd "$1" && pwd)"
N="${2:-3}"
L="${3:-run}"
XUID="${FORZA_XUID:-E030000004B490FA}"
SRC="${FORZA_XENIA_CONTENT:-$HOME/xenia_canary_windows/content}/$XUID/4D5309C9"
D="$W/session"
UD="$W/ud"
[ -d "$SRC" ] || { echo "no save at $SRC" >&2; exit 1; }
for i in $(seq 1 "$N"); do
    avail=$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)
    [ "$avail" -lt 10 ] && { echo "$L $i: only ${avail} GB available, stopping"; break; }
    rm -rf "$UD/B13EBABEBABEBABE"
    mkdir -p "$UD/B13EBABEBABEBABE"
    cp -r "$SRC" "$UD/B13EBABEBABEBABE/"
    rm -f "$D"/forza*.log
    FORZA_XUID=$XUID FORZA_FPSLOG=1 "$ROOT/tools/live_session.sh" "$D" 200 \
        --user_data_root="$UD" > /dev/null || { echo "$L $i: could not start"; break; }
    T=$(cat "$D/pid")
    sleep 45; echo START > "$D/in.fifo"; sleep 12; echo A > "$D/in.fifo"
    for _ in $(seq 1 24); do
        sleep 5
        grep -q "Unhandled\|PHYSCHECK" "$D/forza.log" 2>/dev/null && { sleep 3; break; }
        kill -0 "$T" 2>/dev/null || break
    done
    G=$(pgrep -P "$T" | head -1)
    fps=$(grep -o "t=[0-9]*s [0-9.]* fps" "$D/forza.log" | tail -1)
    if grep -q "Unhandled\|PHYSCHECK" "$D/forza.log"; then
        echo "$L $i: FAULT (last: $fps)"
        cp "$D/forza.log" "$W/${L}_fault_$i.log"
    else
        echo "$L $i: ok (last: $fps)"
    fi
    kill -INT "$T" 2>/dev/null; sleep 8
    [ -n "$G" ] && kill -0 "$G" 2>/dev/null && kill -9 "$G"
    kill -0 "$T" 2>/dev/null && kill -9 "$T"
    for _ in $(seq 1 20); do  # let it unmap its guest memory before the cleanup below
        { [ -n "$G" ] && kill -0 "$G" 2>/dev/null; } || break
        sleep 0.5
    done
    for shm in /dev/shm/xenia_memory_*; do
        [ -O "$shm" ] || continue
        grep -qs "$(basename "$shm")" /proc/[0-9]*/maps || rm -f -- "$shm"
    done
done
