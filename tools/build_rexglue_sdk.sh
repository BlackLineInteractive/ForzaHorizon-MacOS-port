#!/usr/bin/env bash
# Build the ReXGlue Xenos GPU plugin (librexgpu-xenos.so) from source with the
# fixes in patches/rexglue-sdk/, and install it into an overlay of the nightly
# SDK so the forza build and tools/run_forza.sh pick it up. Adapted from
# RecompiledHaloReach; the patch set started as Reach's.
#
# Usage: tools/build_rexglue_sdk.sh [--source-only]
#   --source-only  only check out and patch the SDK source (all tools/build_windows.sh needs)
#
# Why: the SDK's Xenos emulation lacks many Xenia fixes; the first one found
# (in Halo: Reach) was the SPIR-V translator reading the texture-fetch exponent
# bias from fetch-constant word 4 instead of word 3, which darkens textures 256x.
# Upstream closed the report (rexglue/rexglue-sdk#456) without taking GPU
# changes, so we carry the patches (docs/sdk_patches.md).
#
# Environment:
#   REXSDK_NIGHTLY  installed nightly SDK the overlay is based on
#                   (default ~/rexglue-sdk-nightly/0.10.0.24/linux-amd64)
#   REXSDK_SRC      source checkout (default ~/rexglue-sdk-src-forza/sdk)
#   REXSDK_JOBS     parallel compile jobs (default 4; the build runs at nice 15)
#   REXSDK_PATCHED  overlay prefix to create
#                   (default ~/rexglue-sdk-patched-forza/0.10.0.24/linux-amd64)
#
# The defaults are this project's own clone and overlay: RecompiledHaloReach uses
# ~/rexglue-sdk-src and ~/rexglue-sdk-patched, and the two patch sets may differ.
#
# Only the plugin is taken from this build; every other SDK file in the overlay
# is a symlink into the nightly, so the plugin must be built from the nightly's
# exact commit to stay ABI-compatible with its librexruntime.so.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SDK_COMMIT=bd833a2ab69d305f99ddf57418fc38ffec8af93d  # nightly 0.10.0.24 (nightly-20261002-bd833a2a)
NIGHTLY="${REXSDK_NIGHTLY:-$HOME/rexglue-sdk-nightly/0.10.0.24/linux-amd64}"
SRC="${REXSDK_SRC:-$HOME/rexglue-sdk-src-forza/sdk}"
OVERLAY="${REXSDK_PATCHED:-$HOME/rexglue-sdk-patched-forza/0.10.0.24/linux-amd64}"
BREW=/home/linuxbrew/.linuxbrew

SOURCE_ONLY=0
[ "${1:-}" = --source-only ] && SOURCE_ONLY=1
[ "$SOURCE_ONLY" = 1 ] || [ -d "$NIGHTLY/lib" ] || { echo "nightly SDK not found at $NIGHTLY" >&2; exit 1; }

if [ ! -d "$SRC/.git" ]; then
    git clone https://github.com/rexglue/rexglue-sdk "$SRC"
fi
git -C "$SRC" fetch --quiet origin "$SDK_COMMIT" 2>/dev/null || true
git -C "$SRC" checkout --quiet "$SDK_COMMIT"
git -C "$SRC" submodule update --init --recursive --depth 1 --quiet

for patch in "$ROOT"/patches/rexglue-sdk/*.patch; do
    if git -C "$SRC" apply --reverse --check "$patch" 2>/dev/null; then
        echo "already applied: $(basename "$patch")"
    else
        git -C "$SRC" apply "$patch"
        echo "applied: $(basename "$patch")"
    fi
done
[ "$SOURCE_ONLY" = 0 ] || exit 0

# Building the SDK needs X11/XCB and Wayland headers (its UI module and SDL3
# require them). Hosts without them (immutable Fedora) can use Homebrew's:
#   brew install libx11 libxcb libxext libxfixes libxcursor libxi libxrandr \
#                libxscrnsaver libxrender libxtst xorgproto wayland
cmake_args=()
if [ -d "$BREW/opt/xorgproto/include" ]; then
    xp="$BREW/opt/xorgproto"
    inc=""
    for pkg in xorgproto wayland libxcb libx11 libxau libxdmcp; do
        inc+=" -I$BREW/opt/$pkg/include"
    done
    export PKG_CONFIG_PATH="$BREW/lib/pkgconfig:$BREW/share/pkgconfig:$xp/share/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
    # The -L only serves this build's own librexruntime.so, which the plugin
    # links against but which is never shipped (the nightly's is used).
    cmake_args+=(-DCMAKE_PREFIX_PATH="$BREW" -DX11_X11_INCLUDE_PATH="$BREW/include"
                 "-DCMAKE_C_FLAGS=-march=x86-64-v2 $inc"
                 "-DCMAKE_CXX_FLAGS=-march=x86-64-v2 $inc"
                 "-DCMAKE_SHARED_LINKER_FLAGS=-L$BREW/lib")
fi
( cd "$SRC" && cmake --preset linux-amd64 "${cmake_args[@]}" > /dev/null )
nice -n 15 cmake --build "$SRC/out/build/linux-amd64" --config Release --target rexgpu-xenos \
    --parallel "${REXSDK_JOBS:-4}"

built="$SRC/out/linux-amd64/Release/librexgpu-xenos.so"
[ -n "$built" ] || { echo "librexgpu-xenos.so not found in the build tree" >&2; exit 1; }

# Overlay: symlink everything from the nightly, then replace the plugin.
mkdir -p "$OVERLAY/lib"
for entry in "$NIGHTLY"/*; do
    [ "$(basename "$entry")" = lib ] || ln -sfn "$entry" "$OVERLAY/$(basename "$entry")"
done
for entry in "$NIGHTLY"/lib/*; do
    ln -sfn "$entry" "$OVERLAY/lib/$(basename "$entry")"
done
rm -f "$OVERLAY/lib/librexgpu-xenos.so"
cp "$built" "$OVERLAY/lib/librexgpu-xenos.so"
echo "patched plugin: $OVERLAY/lib/librexgpu-xenos.so"

# Stage it next to existing builds of the same SDK right away (the forza
# POST_BUILD step only re-copies it when forza relinks). Builds against other
# SDK versions keep their own plugin: it must match their librexruntime.so.
for build in "$ROOT"/forza-recomp/out/build/*/; do
    [ -f "$build/librexgpu-xenos.so" ] || continue
    sdk_dir="$(sed -n 's/^rexglue_DIR:PATH=//p' "$build/CMakeCache.txt" 2>/dev/null)"
    case "$sdk_dir" in
        "$NIGHTLY"/*|"$OVERLAY"/*)
            # rm first: running instances may have the old file mapped.
            rm -f "$build/librexgpu-xenos.so"
            cp "$OVERLAY/lib/librexgpu-xenos.so" "$build/librexgpu-xenos.so"
            echo "staged into $build" ;;
    esac
done
