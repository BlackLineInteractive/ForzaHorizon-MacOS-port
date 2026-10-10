# RecompiledForzaHorizon

A native PC port of **Forza Horizon (Xbox 360)** built by statically recompiling the
original PowerPC executable to C++ with the [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk),
following the approach of [RecompiledHaloReach](https://github.com/Dyotson/RecompiledHaloReach).

> **Status: early work in progress.** On Linux the game boots through the intro videos,
> title screen and main menu into the opening drive, free roam, festival events and
> races, at 30 fps with sound, DLC and saves (including saves from Xenia). Only tested
> for short sessions so far.

This repository contains **no game code and no game data**. You need your own copy of the
game (the Games on Demand / SVOD package of the base version, Title ID `4D5309C9`). The
recompiled C++ is generated from your copy on your machine and never committed here.

## How it works

- `default.xex` (base version, Xenia module hash `D48ABF1704CE5C4A`) and the two facade
  DLLs it loads (`XMediaFacade_default.xex`, `SpeechFacade_default.xex`) are translated
  function by function into C++ by `rexglue codegen`, driven by
  `forza-recomp/forza_manifest.toml`.
- The ReXGlue runtime (derived from [Xenia](https://github.com/xenia-canary/xenia-canary))
  provides the Xbox 360 kernel/XAM emulation, the Xenos GPU on Vulkan, audio and the
  virtual file system.
- This repository supplies what the generic toolchain can't work out on its own:
  - `forza-recomp/hints/`: function boundaries codegen missed, and statically linked XAPI
    routines mapped to native SDK versions (fibers).
  - `forza-recomp/src/`: the app class and native overrides of kernel/XAM exports (runtime
    fixes, RSA public-key crypto, scripted input and screenshots for automated tests).
  - `patches/rexglue-sdk/`: fixes to the SDK's Xenos GPU emulation.
  - `tools/`: a Games on Demand / STFS package extractor, an XEX image decoder for
    disassembly, build and run scripts.
  - `docs/PROJECT.md`: status log, findings and debugging recipes.

## Status

| Area | State |
| --- | --- |
| Extraction (GOD/SVOD, STFS DLC) | Done (`tools/xcontent_extract.py`) |
| Codegen of `default.xex` + 2 DLLs | Done (76,788 functions, 248 MB of C++) |
| Linux build (Clang) | Builds and links |
| Boot, intro video, title screen, main menu | Work, render correctly with the patched GPU plugin |
| Opening drive (in-engine) | Renders and drives with a pad at 30 fps |
| Free roam, events, races | Work in short tests (a circuit race against 7 AI drivers) |
| Audio | The game produces sound (measured, not listened to yet) |
| Saves | Saved and loaded; Xenia saves load with `profile_xuid` set to the Xenia profile's XUID |
| DLC | All 23 packages install with `tools/install_dlc.py` and are mounted by the game |
| Windows | Not yet |

## Requirements

- Linux x86-64 with a Vulkan 1.3 GPU, about 10 GB of free RAM and 20 GB of disk
  (7.6 GB of extracted game files plus the build).
- Your own Forza Horizon Games on Demand package (`4D5309C9/00007000/<name>` plus
  `<name>.data/`), base version.
- Clang (tested with 23), CMake >= 3.25, Ninja, Python 3, Git, OpenSSL (for
  `tools/xex_image.py` only).
- [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk) 0.10.0.24 nightly
  (`nightly-20261002-bd833a2a`).

## Building (Linux)

```sh
# 1. The ReXGlue SDK nightly, unpacked to ~/rexglue-sdk-nightly/0.10.0.24/linux-amd64
# 2. The game files, extracted from your Games on Demand package (only read)
python3 tools/xcontent_extract.py /path/to/4D5309C9/00007000/<name> extract extracted/game
# 3. The patched Xenos GPU plugin (clones the SDK to ~/rexglue-sdk-src-forza, applies
#    patches/rexglue-sdk/ and installs an overlay at ~/rexglue-sdk-patched-forza)
tools/build_rexglue_sdk.sh
# 4. Configure (the first configure runs codegen, about a minute) and build
cmake -S forza-recomp -B forza-recomp/out/build/linux -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_PREFIX_PATH=$HOME/rexglue-sdk-nightly/0.10.0.24/linux-amd64
ninja -C forza-recomp/out/build/linux
```

## Playing

```sh
tools/play.sh              # play (log: ~/.local/share/forza/forza.log)
tools/run_forza.sh 120     # a two-minute test run; logs in ${XDG_RUNTIME_DIR:-/tmp}/forza_run
```

- **Controller:** any SDL-supported pad. Keyboard emulation of a pad is available with
  `--mnk_mode=true` (bindings: the SDK's `keybind_*` settings; not tested yet).
- **DLC:** install your DLC packages (the `4D5309C9/00000002/` folder of your content)
  once with `python3 tools/install_dlc.py /path/to/4D5309C9/00000002`.
- **Saves** live in `~/.local/share/forza/B13EBABEBABEBABE/4D5309C9/`. Forza ties its save
  to the profile's XUID: to continue a save from Xenia, copy Xenia's
  `content/<XUID>/4D5309C9` folder there and start with `--profile_xuid=<XUID>` (or put
  `profile_xuid = "<XUID>"` in `forza.toml` next to the executable).

## Legal

Forza Horizon is © Microsoft. This project is not affiliated with Microsoft, Playground
Games or Turn 10 Studios. It contains no game code or assets; you must own the game.
