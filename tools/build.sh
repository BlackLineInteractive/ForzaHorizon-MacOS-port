#!/usr/bin/env bash
# Build the Linux binary (and run codegen first if the manifest or hints changed).
# Usage: tools/build.sh [ninja args...]   e.g. tools/build.sh -j8
#
# Runs ninja twice: codegen rewrites the DLL modules' sources during the build, but
# generated/rexglue.cmake declares only default.xex's sources as codegen outputs, so
# ninja sees the DLL changes only on its next run. FORZA_BUILD picks the build dir
# (default linux), FORZA_JOBS the parallelism (default 4); runs at nice 15. Refuses to
# start while another agent holds the benchmark lock (tools/bench_lock.sh).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/forza-recomp/out/build/${FORZA_BUILD:-linux}"
. "$ROOT/tools/bench_lock.sh"
bench_lock_check || exit 3
export PATH="/home/linuxbrew/.linuxbrew/bin:$PATH"
nice -n 15 ninja -C "$BUILD" -j"${FORZA_JOBS:-4}" "$@"
nice -n 15 ninja -C "$BUILD" -j"${FORZA_JOBS:-4}" "$@"
