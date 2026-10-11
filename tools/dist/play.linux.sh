#!/usr/bin/env bash
# Start the game with the files extracted from your own disc (see README.txt):
#   ./play.sh /path/to/extracted/game [options]     e.g. --resolution_scale=2
#   ./play.sh --offline                             no Xbox LIVE (no Forza Live server)
# The path is remembered in game_data_root.txt. FORZA_SERVER=host[:port] names a shared
# Forza Live server (or live_server = "host:port" in forza.toml); otherwise a local one
# (python3 server/forza_live_server.py) runs for the session.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
SAVED="$DIR/game_data_root.txt"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}/forza"
offline=0; DATA="${FORZA_DATA:-}"; args=()
[ -z "$DATA" ] && [ -f "$SAVED" ] && DATA="$(cat "$SAVED")"
first=1
for arg in "$@"; do
    if [ "$arg" = --offline ]; then offline=1
    elif [ "$first" = 1 ] && [ "${arg#-}" = "$arg" ]; then DATA="$arg"
    else args+=("$arg"); fi
    first=0
done
if [ -z "$DATA" ] || ! abs="$(cd "$DATA" 2>/dev/null && pwd)" || [ ! -f "$abs/default.xex" ]; then
    echo "usage: $0 /path/to/extracted/game [options] (README.txt explains the extraction)" >&2
    exit 1
fi
DATA="$abs"
printf '%s\n' "$DATA" > "$SAVED" 2>/dev/null || true
mkdir -p "$DATA_HOME"
server_pid=""
if [ "$offline" = 1 ]; then
    unset FORZA_SERVER
elif [ -z "${FORZA_SERVER:-}" ] && ! grep -qsE '^\s*live_server\s*=\s*"[^"]+' "$DIR/forza.toml"; then
    if command -v python3 > /dev/null; then
        if ! (exec 3<>/dev/tcp/127.0.0.1/21201) 2>/dev/null; then
            mkdir -p "$DATA_HOME/live_server"
            python3 "$DIR/server/forza_live_server.py" --host 127.0.0.1 --port 21200 \
                --http-port 21201 --data-dir "$DATA_HOME/live_server" \
                > "$DATA_HOME/live_server/server.log" 2>&1 &
            server_pid=$!
            sleep 0.5
        fi
        export FORZA_SERVER=127.0.0.1:21200
    else
        echo "python3 not found: starting without a local Forza Live server (--offline)" >&2
    fi
fi
log=(--log_file="$DATA_HOME/forza.log")
for arg in "${args[@]}"; do case "$arg" in --log_file | --log_file=*) log=() ;; esac; done
cd "$DIR"
LD_LIBRARY_PATH="$DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ./forza --game_data_root="$DATA" \
    "${log[@]}" "${args[@]}"
status=$?
[ -n "$server_pid" ] && kill "$server_pid" 2>/dev/null
# Guest memory (/dev/shm/xenia_memory_*, 5 GB) is not unlinked when the game is killed.
for shm in /dev/shm/xenia_memory_*; do
    [ -O "$shm" ] || continue
    grep -qs "$(basename "$shm")" /proc/[0-9]*/maps || rm -f -- "$shm"
done
exit $status
