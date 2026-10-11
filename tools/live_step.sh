#!/usr/bin/env bash
# Press inputs in a game started by tools/live_session.sh, wait, and take a screenshot.
#
# Usage: tools/live_step.sh DIR WAIT [INPUT...]
#   Sends each INPUT 0.8 s apart, waits WAIT seconds and saves DIR/shot.png
#   (tools/live_shot.sh). Prints its path, or "no shot".
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$1"; WAIT="$2"; shift 2
# Fail fast when the game is gone: a write to a FIFO with no reader blocks forever.
pid="$(cat "$DIR/pid" 2>/dev/null || true)"
if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    echo "error: the game in $DIR is not running (pid ${pid:-unknown}); start it with tools/live_session.sh" >&2
    exit 3
fi
for input in "$@"; do
    # Bounded write: the game may exit between the check and the write.
    if ! timeout 5 bash -c 'printf "%s\n" "$1" > "$2"' _ "$input" "$DIR/in.fifo"; then
        echo "error: could not write '$input' to $DIR/in.fifo within 5 s (the game stopped reading)" >&2
        exit 3
    fi
    sleep 0.8
done
sleep "$WAIT"
"$ROOT/tools/live_shot.sh" "$DIR"
