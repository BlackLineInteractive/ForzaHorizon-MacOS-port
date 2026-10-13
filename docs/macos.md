# macOS port

Status: **experimental**. The game builds natively on an Intel Mac and starts, rendering
through the SDK's Vulkan backend on MoltenVK (which turns Vulkan into Metal). A native Metal
backend is in progress: the SDK's own shaders are already in Metal Shading Language
(below), the backend that would use them is not written yet.

## Tested machine

| | |
| --- | --- |
| Mac | MacBook Pro 16" (2019), Intel Core i9-9880H, 32 GB |
| GPU | AMD Radeon Pro 5500M 8 GB (used) and Intel UHD Graphics 630, both Metal 3 |
| OS | macOS 26 (Darwin 25.6), Xcode with the Metal toolchain |
| SDK | ReXGlue nightly 0.10.0.24 `mac-amd64` (`nightly-20261002-bd833a2a`), which ships `libMoltenVK.dylib`, `libvulkan.1.dylib` and `librexgpu-xenos.dylib` |

Apple Silicon (`mac-arm64` nightly) has not been tried.

## Building

```sh
# 1. The SDK nightly, unpacked to ~/rexglue-sdk-nightly/0.10.0.24/mac-amd64
#    (rexglue-sdk-0.10.0.24-dev.gbd833a2-mac-amd64.zip, about 71 MB: check that the
#    download is complete, a truncated zip has no central directory)
# 2. The game files, as on Linux
python3 tools/xcontent_extract.py /path/to/4D5309C9/00007000/<name> extract extracted/game
# 3. The patched SDK (GPU plugin, runtime, codegen tool) into the overlay
#    ~/rexglue-sdk-patched-forza/0.10.0.24/mac-amd64 (about 780 build steps)
REXSDK_JOBS=12 tools/build_rexglue_sdk.sh
# 4. Configure against the overlay (codegen runs with its rexglue) and build with Apple clang
O=$HOME/rexglue-sdk-patched-forza/0.10.0.24/mac-amd64
cmake -S forza-recomp -B forza-recomp/out/build/macos -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH=$O
ninja -C forza-recomp/out/build/macos
```

The overlay is the nightly with the plugin, `librexruntime.dylib` and `bin/rexglue`
replaced: every other entry is a symlink into the nightly. `build_rexglue_sdk.sh` picks the
SDK preset from the host (`mac-amd64`, `mac-arm64`), gives the copied binaries the
nightly's `@loader_path` rpaths with `install_name_tool` and signs them ad hoc. Configuring
against the overlay matters: the build copies the runtime and plugin next to `forza` from
the prefix it finds, and codegen must run the patched `rexglue` (0025 changes the generated
code). An existing build dir keeps its old `rexglue_DIR` and `FORZA_SKIP_CODEGEN`: pass
`-Drexglue_DIR=$O/lib/cmake/rexglue -DFORZA_SKIP_CODEGEN=OFF` when switching it.

Homebrew provides CMake, Ninja, `vulkan-headers` and `molten-vk` (CMake adds their include
directories when present). `forza-recomp/CMakeLists.txt` names the GPU plugin
`librexgpu-xenos.dylib` on macOS and links Metal, QuartzCore, Cocoa and Foundation.

## Running

`tools/run_forza.sh` and `tools/play.sh` are Linux-only for now (`/proc/meminfo`, `timeout`,
`LD_LIBRARY_PATH`, `/dev/shm`). Start the binary directly:

```sh
cd forza-recomp/out/build/macos
./forza --game_data_root=$PWD/../../../../extracted/game --log_file=forza.log
```

`gpu_backend` defaults to `vulkan` on every platform: the plugin only knows `vulkan` and
`d3d12`, and refuses any other name. `src/platform/metal_hooks.mm` only logs the Metal
device and, with `RECOMP_PERF`, counts presents; the Vulkan hooks
(`src/platform/vulkan_hooks.cpp`) are installed on macOS as everywhere else.

First run (2026-10-13, stock plugin): the game starts, picks the Radeon Pro 5500M through
MoltenVK (Vulkan 1.3), presents with FIFO at 3584x2240 and renders. With the patched
plugin it reaches the title screen ("PRESS START") with correct colours and textures, and
90 seconds of log hold no GPU errors (the stock plugin logged `Resolve region is empty`
and `PM4_DRAW_INDX_2 ... Failed in backend` every frame). Gameplay is not tested yet.

## Controls

The keyboard is on by default on macOS (`mnk_mode`, set in `src/main.cpp`; a pad works
alongside it, both drive player 1):

| Pad | Keys |
| --- | --- |
| Left stick (steer) | W A S D |
| Right trigger (throttle) / left trigger (brake) | E or O / Q or I |
| A / B / X / Y | Space or ; / Backspace or ' / L / P |
| LB / RB | 1 / 3 |
| Right stick (camera) | arrow keys |
| D-pad | Shift + arrow keys |
| START / BACK | Return or X / Tab or Z |

The SDK's `keybind_*` settings in `forza.toml` remap them; `--mnk_mode=false` turns the
keyboard off.

## Known issues

- Without `tools/build_rexglue_sdk.sh` the build ships the nightly's stock plugin (CMake
  warns that `FORZA_XENOS_PLUGIN` is missing), which lacks every fix in
  `docs/sdk_patches.md`.
- MoltenVK warns `Metal does not support disabling primitive restart`: Metal always
  restarts strips at the 0xFFFF / 0xFFFFFFFF index, so a guest strip draw that relies on
  restart being off could lose triangles. No visible effect seen so far.
- MoltenVK has no Vulkan format for the guest formats `k_1_5_5_5`, `k_6_5_5` and
  `k_DXT3A_AS_1_1_1_1`, and no sparse binding (the 512 MB shared memory buffer is allocated
  in full).
- RenderDoc has no macOS build: `FORZA_RDCAPTURE` only logs a warning
  (`src/debug/frame_dump.cpp`); use Xcode's Metal frame capture.
- The CPU profiler (`src/debug/cpu_profile.cpp`) works, but thread names are `?` (no
  `/proc`); samples still carry the thread id.
- Performance is not measured yet.

## Metal shaders

The SDK ships its own shaders (EDRAM resolves and clears, texture untiling and
decompression, gamma with FXAA luma, host depth store, the presenter's bilinear / CAS / FSR
output filters, ImGui) only as SPIR-V arrays in `src/{graphics,ui}/shaders/vulkan_spirv/*.h`.
`tools/spirv_to_metal.py` rewrites all 109 of them as Metal Shading Language into
`forza-recomp/metal_shaders/` and links them into `rexgpu_builtin.metallib`:

```sh
brew install spirv-cross
tools/build_rexglue_sdk.sh --source-only     # the SDK source in ~/rexglue-sdk-src-forza/sdk
tools/spirv_to_metal.py --metallib forza-recomp/metal_shaders/rexgpu_builtin.metallib
```

- MSL 3.0 (macOS 13+), compiled with `xcrun metal -O3`. Entry points are named after the
  shader (`resolve_full_32bpp_cs`, `immediate_ps`...), so all fit in one library.
- Each Vulkan descriptor set is a Metal argument buffer at `[[buffer(set)]]`, its bindings
  are `[[id(binding)]]`; push constants follow as a plain `[[buffer(n)]]`. A Metal backend
  can fill them in the Vulkan backend's layout.
- `immediate_ps` (ImGui) is hand-written in `metal_shaders/manual/`: SPIRV-Cross throws on
  it with argument buffers.
- Checked: the Metal compiler accepts all 109, and both GPUs of the test machine build a
  pipeline state from every one (compute kernels alone, pixel shaders paired with their
  vertex shader).

These are the SDK's built-in shaders only. The game's own shaders are Xenos microcode that
the SDK translates to SPIR-V while the game runs; a native backend has to translate those
to MSL at run time too.

## Roadmap

1. Mac launch scripts (`tools/play.sh`, `tools/run_forza.sh`), then play past the title
   screen: prologue drive, free roam, a race.
2. Measure MoltenVK (`RECOMP_PERF`, `tools/frametime_report.py`) in free roam and a race,
   and try MoltenVK's own settings (Metal argument buffers, `MVK_CONFIG_*`).
3. Native Metal backend in the SDK fork (`src/graphics/metal/`), in this order: presenter,
   pipelines (game shaders through SPIR-V → MSL), shared memory and textures (the shaders
   above), render targets / EDRAM (raster order groups), resolves. Compare each step with
   MoltenVK screenshots.
4. OpenGL is not planned: macOS stops at OpenGL 4.1, which has no compute shaders, SSBOs
   or image load/store, and the Xenos emulation needs them (texture untiling, resolves).
