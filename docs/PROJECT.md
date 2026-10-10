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

- 2026-10-10 (afternoon, later): **free roam, events and races; DLC; Xenia saves.**
  - DLC: `tools/install_dlc.py` extracts the 23 LIVE packages into the runtime's content
    layout (`<user data>/0000000000000000/4D5309C9/00000002/<package>/` plus a
    `Headers/00000002/<package>.header`), byte-identical to what the user's Xenia
    installed. The game mounts them as `DLCRoot0:`..`DLCRoot22:` after START.
  - Saves are tied to the profile: the user's Xenia save (profile `E030000004B490FA`)
    copied under the runtime's profile folder froze the title screen after START. The
    game checks its save with a keyed hash (`sub_82C66308`, key decoded from an
    obfuscated table at `0x82518CF8`, failure callback `sub_824F31F8`), and the failure
    path calls the fatal-error handler `sub_82C09F00` (records four values at
    `0x83442EBC`, sets `0x83442ED1`, spins in `b .` at `0x82C09FA8`). With
    `profile_xuid=E030000004B490FA` (`src/kernel/profile_identity.cpp`; also
    `FORZA_XUID`, `profile_gamertag`/`FORZA_GAMERTAG`) the save loads: free roam in the
    user's Aventador with traffic, a festival event ticket, car select, the pre-race
    menu and a 4-lap circuit race against 7 AI drivers at 30 fps.
  - `src/kernel/xekeys.cpp`: `XeKeysGetConsoleID`, `XeKeysConsolePrivateKeySign`,
    `XeKeysConsoleSignatureVerification` and `XamUserGetIndexFromXUID` answer as in
    Xenia (the SDK's stubs wrote nothing, or returned FALSE).
  - `src/debug/fault_guard.cpp`: a fault nothing handles now logs a host stack
    (module+offset) and aborts, instead of re-running the faulting instruction forever.
    One run with the copied save hit a null read (`read of guest 0x00000000` on one
    thread, logged 1.6 million times: 260 MB in a minute) 30 s after entering single
    player; the next identical run did not.
  - That fault, chased with a repeat script (copy the Xenia save, START, Single Player,
    watch for 110 s): it hits in roughly half the runs, always while free roam loads
    around the saved position, never in the prologue. Two forms: a read of guest
    `0x0000000F` and a write of guest `0x701F0120`, both under `sub_82D3DB00` (called
    from `sub_82D44B90` <- `sub_82D42638` <- `sub_82D43818` <- `sub_82D4D9D0`/
    `sub_82D4DCC8`), the loader of world physics/collision definitions (strings
    `PhysicsDefinition`, `ConvexHull`, `BreakSpeedMph`...). `sub_82D3DB00` keeps an
    array of at most 8 records of 544 bytes in its 4544-byte frame and fills one per
    entry of a 12-byte record chosen by its index argument (`*(r3+84) + index*12`,
    count byte at +9, list pointer at +4). The bad runs read a count above 8 or a
    pointer of 0xF there: the record is garbage, and the loop writes past the frame,
    through the thread's PCR (`r13` = `0x701EE890`) up to the end of the stack at
    `0x701F0000`. So the input is not ready or not what the game expects when it is
    read; the timing dependence points at synchronization (a race the console's timing
    hides, or an emulated primitive that misbehaves). Ruled out: the critical-section
    replacement (it faults with `FORZA_SDK_CRITICAL_SECTIONS=1` too) and fiber
    migration between threads (`FORZA_FIBERTRACE=1`: the game switches fibers once).
    Open.

- 2026-10-10 (evening): **any controller gets past the title screen; Xenia saves from
  `play.sh`; perf tooling from Reach.**
  - The user was stuck at the title screen: the runtime signs in one profile, on user 0,
    and gives every SDL pad its own user slot in connection order. With Steam Input and
    Sunshine virtual pads present, the user's pad was not slot 0, so START came from an
    unsigned user and the game waited for a sign-in nobody could give (reproduced with
    `FORZA_PAD_PER_USER=1` and a scripted press on slot 1: `PAD1:START` on the input FIFO).
    `src/kernel/input_autopress.cpp` now merges every pad into user 0 (buttons combined,
    strongest stick/trigger wins, vibration to all) and reports users 1-3 as without a
    controller: START on a slot-1 or slot-2 pad reaches the first-run screen and the main
    menu from a fresh data folder.
  - `tools/play.sh --xenia [XUID]` plays a copy of the user's Xenia save signed in with
    its XUID (`~/.local/share/forza/xenia-<XUID>/`, DLC and shader cache shared).
  - Frame statistics, Vulkan hooks (present-mode log, present and pipeline counts), the
    FIFO present-mode default and the on-demand achievement toast (the SDK's toast kept
    the UI thread repainting nonstop) ported from RecompiledHaloReach. SDK patch 0024
    (a presenter hook) is gone again: the Vulkan hooks do it without an SDK change.
  - Diagnostics for the physics fault: the item index that overruns `sub_82D3DB00`'s
    array is the low byte of the w lane of a 16-byte closest-point result
    (`sub_82D44B90` r1+384/+400, written whole by `sub_82D41F28` from GJK vertices with
    `vmaddfp`/`vsel`); in failing runs that lane holds pointers or 0xBEBEBEBE fill, i.e.
    the vertex data's w lanes carry garbage. Next: who writes the vertex records
    (r3+0x1AA0 + id*32 in the solver workspace).
- 2026-10-10 (night): **Xbox LIVE through a Forza Live server; Gold; the party
  lobby.** The user saw "You must have an Xbox LIVE Gold Membership" and "no connection
  to Xbox LIVE" under Multiplayer.
  - RecompiledHaloReach's Reach Live client is ported (`src/kernel/identity.cpp`,
    `xam_signin.cpp`, `net.cpp`, `live_xmsg.cpp`, `live_tcp.cpp`, `live_lsp.cpp`,
    `src/platform/socket.*`) with its server (`server/forza_live_server.py`, UDP 21200 and
    HTTP 21201; Reach Live keeps 21100/21101, and an instance of each game can run side by
    side). `tools/play.sh` starts a local server unless `FORZA_SERVER` or `live_server`
    names one (`--offline`: none). The game signs in to LIVE as user 0 with an online XUID
    (`0009...`, kept in `<data>/forza/4D5309C9/live_identity.txt`) while the save stays
    tied to the offline XUID.
  - Gold, always (`xam_signin.cpp`): `XamUserCheckPrivilege` grants everything,
    `XamUserGetMembershipTier[FromXUID]` is Gold, sign-in state 2 with the LIVE flag.
  - Entering Multiplayer then crashed (read of guest `0xC` in `sub_82CA41C8`). Two causes:
    - `XUserReadStats` (XGI `0xB0021`): the SDK answers success and leaves the results
      empty; the game reads its TrueSkill row (column 0 as an int64, two doubles: mu and
      sigma) through the empty view list right after creating the party session.
      `live_xmsg.cpp` now writes a row per player and view with a new player's defaults
      (skill 1, mu 3.0, sigma 1.0, other columns null).
    - The session socket: Forza's session networking (`0x8313xxxx`-`0x8315xxxx`) opens a
      VDP socket, binds it, reads its port with `getsockname` (an SDK stub), and keeps an
      overlapped `WSARecvFrom` posted on it (`sub_83143C40`; `WSA_IO_PENDING` hands the
      OVERLAPPED to an I/O object that waits on its event, `sub_831425C8` collects it
      with `WSAGetOverlappedResult`). The SDK's `WSARecvFrom` always fails, so the socket
      was closed again at once. `net.cpp` now does overlapped receives on the virtual
      sockets (pending receives complete when a datagram arrives: buffers, sender,
      OVERLAPPED status and byte count, then its event), `WSAGetOverlappedResult`,
      `WSACancelOverlappedIO`, `WSAEventSelect`, `WSASendTo`/`WSASend` (gathered,
      completed at once), `getsockname`, `getsockopt` (it probes `SO_RCVBUF` first),
      `getpeername`. The game's Winsock wrappers are at `0x82A628C8`-`0x82A62B88`.
  - Multiplayer now opens the PARTY LOBBY (Find Game, Find Custom Game, Create Custom
    Game, Difficulty, Invite Friends) with the player listed and a hosted party session
    (flags `0x823`: host, presence, peer network, friends join via presence).
  - "The Horizon server is currently unavailable, you will not be awarded XP for online
    multiplayer games": Turn 10's title services. The game enumerates title servers
    every 30 s and keeps one whose description matches the service name it wants
    (wildcards `*`/`?`, `sub_83153D48` called from `sub_83155238`); it talks "Xls Client"
    HTTP/1.1 to it (`POST /Services/o.xtsw`, `Content-Type: bin/xtsw`, `X-TitleId`,
    `X-ClassName`, `X-Method`, `X-UserId`, `X-TransactionId` headers). Our title server
    is now described as `*`, so every service resolves to the Forza Live server, whose
    `forza_live_lsp.py` logs the requests.
  - MISSING CONTENT: not reproduced in the user's flow (main menu, Multiplayer) with all
    23 DLC packages installed. The license path was checked: each DLC's license mask
    comes from `XContentCreateEx` (`sub_825166xx`, the package header written by
    `tools/install_dlc.py`: all bits) and feeds `UPDATE ContentOffers SET IsInstalled=1,
    IsPurchased=(LicenseMask & %u)=LicenseMask` (`sub_825162D0`); the only
    `XamContentGetLicenseMask` caller (`sub_82C01748`) ignores the mask, so the SDK's
    `license_mask` setting does not matter here. The messages are chosen in
    `sub_826B4200` (lobby: DLC / Disc 2 / unknown) and by a content check
    (`sub_825A56E0` returning 4) before `0x8275C238`.
- **Status and open items (end of 2026-10-10):**
  - Xbox LIVE: signed in, Gold, party lobby works. In a two-instance test (DriverA,
    DriverB, one local server) DriverB's "Find Custom Game" found no session, hosted a
    matchmaking session (flags `0x2D`) and started an online race alone (0/3 laps,
    place 1/1, no crash); DriverA's scripted menu path ended back in the lobby. Not
    done yet: both instances in one online free-roam session (next: A "Create Custom
    Game" -> free roam, then B "Find Custom Game", or A "Invite Friends" -> B, which
    auto-accepts with `live_accept_invites`); Turn 10's "Xls" title services (the game
    made no title-server request yet even with the `*` description; next: see why
    `sub_83155238` is not reached or fails); a second server-search path if Forza's
    custom-game search uses properties other than Reach's hopper id.
  - MISSING CONTENT: not reproduced (see above). Next: the user's exact flow with
    `--xenia` and the place it shows; log `sub_825A56E0`'s result and the content id.
  - Free-roam physics crash (`sub_82D3DB00`): open, see above. Next: find the writer of
    the GJK vertex records; the generated C++ carries VMX128 disassembly as comments,
    which objdump cannot decode.
  - Performance: no clean-window numbers yet (docs/perf.md has contended ones only).
  - Frame-rate unlock: xenia-canary/game-patches has no frame-rate patch for this game.
    Cheapest experiment: `--video_mode_refresh_rate=120` (the SDK's guest vblank rate;
    the game presents every second vblank, so 60 fps if it keeps up) and check whether
    the game runs faster than real time (fixed per-frame step) by comparing the speed
    reached after N seconds of throttle at 60 and 120 Hz. `--vsync=false` (1 kHz vblank)
    unlocks completely. Not run yet.

## Debugging recipes

- Find a codegen hint's target: `tools/ppcdis.sh 0x82F76188 +0x80`.
- Runs: `tools/run_forza.sh SECS [flags]` (logs in `$FORZA_RUN_DIR`), or
  `tools/live_session.sh DIR` + `tools/live_step.sh DIR WAIT INPUT...` (input FIFO,
  screenshot `DIR/shot.png` through `FORZA_SCREENSHOT_TRIGGER`). Headless frame dumps come
  out all zero (seen in Reach); check rendering with screenshots from a windowed run.
- `FORZA_FPSLOG=1` logs the frame rate every 5 s; `FORZA_AUDIOLOG=1` the peak/RMS of the
  audio the game submits (non-zero means it makes sound).
- A fault no handler takes aborts with a host stack in the log (`src/debug/fault_guard.cpp`):
  `addr2line -f -e forza-recomp/out/build/linux/forza 0xOFFSET` names the `sub_XXXXXXXX`
  frames. `FORZA_FAULT=wait` parks the thread instead, for `gdb -p`.
- Never pass two files to `xxd` (`xxd a b` writes the dump into `b`): that clobbered a
  save header once.
- Testing with the user's Xenia save without touching it: copy
  `~/xenia_canary_windows/content/E030000004B490FA/4D5309C9` into a scratch
  `<dir>/B13EBABEBABEBABE/`, symlink `<dir>/0000000000000000` to the installed DLC, run with
  `--user_data_root=<dir>` and `FORZA_XUID=E030000004B490FA`.
- `tools/xrefs.py ADDR` lists branches, lis/addi pairs and data words pointing at an
  address (a quick stand-in for Ghidra's xrefs).
- Kernel imports can be overridden from `src/` by defining `extern "C" REX_FUNC(__imp__Name)`;
  `forza::SdkImport("__imp__Name")` finds the SDK's original. Guest pointers in hand-written
  code: always `forza::GuestPtr(base, addr)` (Windows maps 0xE0000000+ 4 KB further on).
- Guest address X is host `0x100000000 + X` on Linux: `gdb -p PID`, `rwatch *(int*)0x1XXXXXXXX`,
  `bt` shows the `sub_XXXXXXXX` frames.
