# RecompiledForzaHorizon: native static recompilation of Forza Horizon (Xbox 360)

Goal: run Forza Horizon (Xbox 360, Title ID `4D5309C9`, base version, no title update)
natively on x86-64 Linux (later Windows) by statically recompiling `default.xex` and its
facade DLLs (PowerPC Xenon) to C++ with the ReXGlue SDK. The approach, tooling and many
runtime fixes come from [RecompiledHaloReach](https://github.com/Dyotson/RecompiledHaloReach)
(same SDK, same author); files taken from it say so.

## The game files

| | |
| --- | --- |
| Container | Games on Demand (content type `0x7000`), SVOD: a header file `4D5309C9/00007000/589C7B8B0AE2A7A0CBE0` plus 46 fragments in `589C7B8B0AE2A7A0CBE0.data/` (7.6 GB), no XSF header, XDVDFS magic at `0x12000` of `Data0000` |
| `default.xex` | Base version (Xenia module hash `D48ABF1704CE5C4A`, matching `patches/4D5309C9 - Forza Horizon.patch.toml`; TU4 would be `336A44DC03EC8782`). Version 0.0.0.7, built 2012-09-04, Media ID `2B7A1346` (Europe/Asia disc), 20.9 MB, load address `0x82000000`, image size `0x1620000`, entry point `0x82A6FBC0`, AES-encrypted with basic (zero-run) compression |
| DLLs | `XMediaFacade_default.xex` (loads at `0x88000000`) and `SpeechFacade_default.xex` (`0x89000000`), loaded at run time with `XexLoadImage` |
| Data | `media/` (cars, tracks, audio, shaders, UI zips, string tables...), `nuisp*` Kinect speech models, `$SystemUpdate/` (dashboard update, not used) |
| DLC | `4D5309C9/00000002/`: 23 LIVE (STFS, read-only format) marketplace packages, content type 2: car packs, VIP, Season Pass, Rally Expansion (1 GB), 1000 Club Expansion. Each holds `Media/<id>.puboffer` and `Media/DLCZips/<id>_pri_65[.zip]` (the expansions also `spa.bin`). Not used yet |

`tools/xcontent_extract.py` (standard library only, read-only) lists and extracts both
container kinds; it is a port of the SDK's `StfsContainerDevice` (from Xenia):

```sh
G=~/forza-horizon-.../4D5309C9
python3 tools/xcontent_extract.py $G/00007000/589C7B8B0AE2A7A0CBE0 info
python3 tools/xcontent_extract.py $G/00007000/589C7B8B0AE2A7A0CBE0 extract extracted/game
python3 tools/xcontent_extract.py $G/00000002/<package> list
```

The extraction was checked against the SVOD level-0 hash tables (SHA-1 of every 4 KB
data pair in all 46 fragments: no mismatch). SVOD block mapping: each 0xA290000-byte
fragment is one level-1 hash block, then 0xCB groups of (level-0 hash block + 0x198
data sectors of 0x800 bytes).

`tools/xex_image.py XEX OUT --elf` writes the decrypted, decompressed image as a PowerPC
ELF (via `openssl enc` for AES), and `tools/ppcdis.sh ADDR [+LEN]` disassembles it with
`llvm-objdump` (VMX128 shows as `<unknown>`). Quicker than Ghidra for looking at a few
instructions; both read `extracted/analysis/`.

## Layout

| Path | What |
| --- | --- |
| `extracted/game/` | Extracted game (gitignored, never committed) |
| `extracted/analysis/` | Decoded xex images for disassembly (gitignored) |
| `forza-recomp/forza_manifest.toml` | Codegen manifest (`default.xex` + 2 DLL modules) |
| `forza-recomp/hints/` | Function boundaries, rexcrt mappings, per-module hints |
| `forza-recomp/src/` | Runtime code: app class, kernel/XAM overrides, debug tools |
| `forza-recomp/generated/` | Codegen output; only `rexglue.cmake` is tracked here, the rest goes to the private `RecompiledForzaHorizon-generated` repo (`tools/sync_generated_repo.sh`) |
| `patches/rexglue-sdk/` | SDK patches (started as Reach's 19 GPU patches) |
| `ghidra_projects/ForzaHorizon` | Ghidra project with `default.xex` (gitignored) |

## Tooling

- ReXGlue SDK nightly 0.10.0.24 (`nightly-20261002-bd833a2a`) at
  `~/rexglue-sdk-nightly/0.10.0.24/linux-amd64`.
- Patched Xenos GPU plugin: `tools/build_rexglue_sdk.sh` builds it into this project's own
  overlay `~/rexglue-sdk-patched-forza/0.10.0.24/linux-amd64` from its own clone
  `~/rexglue-sdk-src-forza` (never Reach's `~/rexglue-sdk-src`/`~/rexglue-sdk-patched`).
  Until Forza needs a patch of its own, CMake and the run scripts fall back to Reach's
  overlay, which has the same patch set.
- Clang 23, CMake, Ninja from Homebrew (`/home/linuxbrew/.linuxbrew/bin`).
- Ghidra 12.1.4 + XEXLoaderWV: `ghidra_projects/ForzaHorizon` was made with
  `analyzeHeadless ... -import extracted/game/default.xex` (about 25 minutes with 6 GB heap).

Build (always through the same path, `/var/home/...`; `/home` is a symlink and a
different spelling makes CMake rebuild everything):

```sh
export PATH=/home/linuxbrew/.linuxbrew/bin:$PATH
cmake -S forza-recomp -B forza-recomp/out/build/linux -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_PREFIX_PATH=$HOME/rexglue-sdk-nightly/0.10.0.24/linux-amd64
nice -n 15 ninja -C forza-recomp/out/build/linux -j4
```

## Hard rules

- Never modify, move or delete anything in the game folder, the zip next to it, Xenia
  (`~/xenia_canary_windows`) or the Reach project and its SDK checkout/overlay.
- No game code or data in this repository: `extracted/`, `*.xex`, generated C++ and
  Ghidra projects are gitignored. The generated C++ goes only to the private repo.
- Game runs: under `timeout`, with every SDL pad ignored, after checking `free -g`
  (the run scripts refuse with less than 10 GB available); kill by PID.

## Status log

- 2026-10-10: project started. Game extracted from the GOD container (base version, see
  above). Codegen of `default.xex` + both facade DLLs succeeds: 76,788 functions in
  `default.xex`, 248 MB of C++. Hints needed so far:
  - 20 tail-call-only entry points (accessors, forwarders, this-adjusting thunks placed
    right after an unconditional branch) that failed validation with "target not in any
    function" (`hints/tail_targets.toml`, `hints/xmediafacade.toml`,
    `hints/speechfacade.toml`), found by iterating codegen on its error list.
  - The statically linked XAPI fiber routines (same code as in Reach) mapped to the SDK's
    native fibers (`hints/rexcrt.toml`); without the mapping codegen could not even
    resolve SwitchToFiber's tail call into its context save at `0x830ED910`.
  - Known benign warnings: `bdz` at `0x82AD8138/813C` branch to `0x82AD836C`, the zero
    word just past the function (MSVC's marker for unreachable switch cases); function
    `0x8241A370` is 2.5 MB (one huge initializer).

- 2026-10-10 (later): **boots to gameplay.** The game plays the Microsoft Studios intro
  video, shows the title screen ("PRESS START"), the first-run video calibration screen,
  the main menu (Single Player / Multiplayer), the live-action festival intro video, and
  then the in-engine prologue: the SRT Viper cinematic on the road and the drive to the
  festival with HUD (minimap, speedometer), steerable with scripted pad input. Rendering
  looks right with the patched GPU plugin (Reach's 19 patches). Screenshots in
  `screenshots/` (gitignored). What it took:
  - 220 indirectly referenced entry points (vtables, callback tables, CRT initializers)
    and 357 orphan functions in `default.xex`, plus 37/22 and 89/19 in the two DLLs,
    found with Reach's tools ported to read the XEX image instead of Ghidra
    (`tools/find_missing_entries.py`, `tools/find_orphan_functions.py`). The first boot
    died in `XMediaFacade`'s CRT initializers ("Call to invalid or unregistered function
    at 0x882435D8", a `__xc_a` entry). Six hints that split functions were pruned
    (`tools/prune_split_hints.py` plus two by hand: a jump-table case after a call at
    `0x829CBE14`, an EH funclet at `0x82ABAF38`), and 20 that landed on import thunks
    (codegen: "outranked by import") were dropped: they left undefined `sub_831EDxxx`
    symbols, and in a DLL an undefined symbol only shows up when `dlopen` fails at run
    time ("Failed to load shared library for module").
  - `cache:` mounted on a host folder (`<cache_root>/cache`) in `ForzaApp::OnPreLaunchModule`,
    as Xenia does with `mount_cache`: the game keeps ghost and replay streams there.
  - Codegen rewrites the DLL sources during the build, but only `default.xex`'s sources
    are declared codegen outputs, so ninja picks up DLL changes on its next run:
    `tools/build.sh` runs ninja twice.
  - Open: `Resolve region is empty` + `PM4_DRAW_INDX_2(3, 8, 2): Failed in backend`
    logged ~180 times a second (Xenia later made empty resolves a silent no-op,
    "log spam in Forza Horizon 1/2"); `XamXStudioRequest` stub logged 33 times a second
    (Xenia also gets it, 314k calls in the user's log); audio not verified.

- 2026-10-10 (afternoon): **the opening drive plays at 30 fps with sound.**
  - Own SDK clone and overlay (`~/rexglue-sdk-src-forza`, `~/rexglue-sdk-patched-forza`)
    with patch 0023: an empty resolve region is a no-op, as in Xenia, which changed it
    for Forza Horizon. It was logged twice per resolve, about 180 lines a second
    (`Resolve region is empty` + `PM4_DRAW_INDX_2(3, 8, 2): Failed in backend`).
  - `src/kernel/xam_nui.cpp`: Kinect and XAM answers as in Xenia:
    `XamNuiGetDeviceStatus` returns 0xC0050006 (no Kinect; the SDK returned nothing),
    `XamXStudioRequest` (polled every 30 ms) is left unanswered without a warning per
    call, XAM app 0xFE message 0x2B003 succeeds.
  - Title screen and the drive run at a steady 29.5-30 fps (`FORZA_FPSLOG=1`); the
    drive was held at full throttle for two minutes (89 mph on the road, then into the
    woods) without errors. Audio frames carry sound (`FORZA_AUDIOLOG=1`: RMS 0.01-0.04
    during the intro and menus). Saves: the profile (`ForzaProfile`) is written under
    `~/.local/share/forza/<xuid>/4D5309C9/00000001/`; the second run skips the first-run
    screen.
  - Online vision (design only, for later): `docs/online_vision.md`.

## Debugging recipes

- Find a codegen hint's target: `tools/ppcdis.sh 0x82F76188 +0x80`.
- Runs: `tools/run_forza.sh SECS [flags]` (logs in `$FORZA_RUN_DIR`), or
  `tools/live_session.sh DIR` + `tools/live_step.sh DIR WAIT INPUT...` (input FIFO,
  screenshot `DIR/shot.png` through `FORZA_SCREENSHOT_TRIGGER`). Headless frame dumps come
  out all zero (seen in Reach); check rendering with screenshots from a windowed run.
- `FORZA_FPSLOG=1` logs the frame rate every 5 s; `FORZA_AUDIOLOG=1` the peak/RMS of the
  audio the game submits (non-zero means it makes sound).
- `tools/xrefs.py ADDR` lists branches, lis/addi pairs and data words pointing at an
  address (a quick stand-in for Ghidra's xrefs).
- Kernel imports can be overridden from `src/` by defining `extern "C" REX_FUNC(__imp__Name)`;
  `forza::SdkImport("__imp__Name")` finds the SDK's original. Guest pointers in hand-written
  code: always `forza::GuestPtr(base, addr)` (Windows maps 0xE0000000+ 4 KB further on).
- Guest address X is host `0x100000000 + X` on Linux: `gdb -p PID`, `rwatch *(int*)0x1XXXXXXXX`,
  `bt` shows the `sub_XXXXXXXX` frames.
