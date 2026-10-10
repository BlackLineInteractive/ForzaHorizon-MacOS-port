#!/usr/bin/env bash
# Disassemble guest code from the decoded default.xex image (tools/xex_image.py --elf).
# Usage: tools/ppcdis.sh START [END|+BYTES] [IMAGE.elf]
#   tools/ppcdis.sh 0x82F76188 +0x80
# VMX128 instructions (Xenon extensions) show as <unknown>.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
start=$1; end=${2:-+0x40}; elf=${3:-$ROOT/extracted/analysis/default.elf}
case "$end" in +*) end=$(printf '0x%X' $((start + ${end#+}))) ;; esac
[ -f "$elf" ] || python3 -I "$ROOT/tools/xex_image.py" "$ROOT/extracted/game/default.xex" "$elf" --elf >&2
OBJDUMP=$(command -v llvm-objdump || echo /home/linuxbrew/.linuxbrew/bin/llvm-objdump)
"$OBJDUMP" -d --no-show-raw-insn --start-address="$start" --stop-address="$end" "$elf" | tail -n +7 \
    | sed -E 's/ <\.text\+0x[0-9a-f]+>//'
