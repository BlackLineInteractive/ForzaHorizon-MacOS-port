#!/usr/bin/env bash
# Press inputs in a game started by tools/live_session.sh, wait, and take a screenshot.
#
# Usage: tools/live_step.sh DIR WAIT [INPUT...]
#   Sends each INPUT 0.8 s apart, waits WAIT seconds and saves DIR/shot.png
#   (tools/live_shot.sh). Prints its path, or "no shot".
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$1"; WAIT="$2"; shift 2
for input in "$@"; do echo "$input" > "$DIR/in.fifo"; sleep 0.8; done
sleep "$WAIT"
"$ROOT/tools/live_shot.sh" "$DIR"
