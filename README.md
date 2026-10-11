# RecompiledForzaHorizon

A native PC port of **Forza Horizon (Xbox 360)** built by statically recompiling the
original PowerPC executable to C++ with the [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk),
following the approach of [RecompiledHaloReach](https://github.com/Dyotson/RecompiledHaloReach).

> **Status: early work in progress.** On Linux the game boots through the intro videos,
> title screen and main menu into the opening drive, free roam, festival events and
> races, at 30 fps (60 with `frame_rate = 60`) with sound, DLC and saves (including saves
> from Xenia). Only tested for short sessions so far.

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
| Xbox LIVE | Emulated by a Forza Live server (`server/`): signed in, Gold; Turn 10's title services for sign-in, playlists and online XP; two players find each other with Find Game and race, the race awards XP and credits; parties (Invite Friends), Create Custom Game, online free roam; a shared world: the Horizon World playlist places everyone into the same free roam automatically. Storefront, auctions, gifting and scoreboards answer empty |
| Windows | Cross-compiled from Linux (`tools/build_windows.sh`), tested under Proton; not yet on Windows itself |

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
# 3. The patched Xenos GPU plugin and codegen tool (clones the SDK to ~/rexglue-sdk-src-forza,
#    applies patches/rexglue-sdk/ and installs an overlay at ~/rexglue-sdk-patched-forza;
#    the stock rexglue's dot products overflow to infinity, Xenon's to QNaN, and free roam
#    crashes without it)
tools/build_rexglue_sdk.sh
# 4. Configure (the first configure runs codegen with the overlay's rexglue, about a
#    minute) and build
cmake -S forza-recomp -B forza-recomp/out/build/linux -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER=clang++ -DCMAKE_PREFIX_PATH=$HOME/rexglue-sdk-nightly/0.10.0.24/linux-amd64
ninja -C forza-recomp/out/build/linux
```

## Windows

The Windows version is cross-compiled from Linux with clang/clang-cl and lld-link, after the
Linux build above (its codegen output in `forza-recomp/generated/` is reused, and step 3
checks out the SDK source). `tools/build_windows.sh` builds the ReXGlue SDK for Windows
from `~/rexglue-sdk-src-forza` with this project's patches and the Vulkan backend into
`~/rexglue-sdk-patched-forza/0.10.0.24/win-amd64`, then the game, and packages it in
`forza-recomp/out/dist/windows` (`--sdk-only` and `--game-only` split the long build):

```sh
brew install llvm lld                                  # clang, clang-cl, lld-link
xwin --accept-license splat --output ~/.local/opt/xwin/sdk   # MSVC CRT + Windows SDK (Microsoft's license)
tools/build_windows.sh
tools/package_linux.sh                                 # the Linux package, forza-recomp/out/dist/linux
```

On Windows, extract the package, install the Microsoft Visual C++ 2015-2022 x64
redistributable, extract your game files with `python xcontent_extract.py` and run
`play.bat C:\path\to\extracted\game` (`--offline` for no Xbox LIVE; it starts a local
Forza Live server when Python is installed, or uses `FORZA_SERVER` / `live_server` in
`forza.toml`). Saves, the online identity and the log go to `Documents\forza`.

## Playing

```sh
tools/play.sh                 # play with your own profile (~/.local/share/forza)
tools/play.sh --xenia         # continue your Xenia Canary save (a copy; see below)
tools/play.sh --offline       # without Xbox LIVE
tools/run_forza.sh 120        # a two-minute test run; logs in ${XDG_RUNTIME_DIR:-/tmp}/forza_run
```

- **Profile and controllers:** the game runs signed in to one local profile on player 1,
  and every connected controller drives player 1, so START on any pad gets you past the
  title screen (with Steam Input or Sunshine virtual pads around, your pad is often not
  the first one, and the game used to ask that pad to sign in).
  `FORZA_PAD_PER_USER=1` gives each pad its own player again.
- **Keyboard:** the SDK's keyboard emulation of a pad is available with `--mnk_mode=true`
  (bindings: the SDK's `keybind_*` settings; not tested yet).
- **Xbox LIVE:** the game signs in to an emulated Xbox LIVE, as a Gold member, through a
  Forza Live server (`server/forza_live_server.py`, Python 3 standard library only).
  `play.sh` starts one on this machine for the session (UDP 21200, HTTP 21201, data in
  `~/.local/share/forza/live_server/`), or uses the one already running there. To play
  with others, run the server where everyone can reach it
  (`python3 server/forza_live_server.py --http-port 21201`) and start the game with
  `FORZA_SERVER=host[:port]` (or `live_server = "host:port"` in `forza.toml` next to the
  binary). Your online identity (XUID, gamertag: your login name unless
  `FORZA_GAMERTAG` is set) is kept in `~/.local/share/forza/4D5309C9/live_identity.txt`.
  Everyone in the server's room is your friend.
  **The shared world:** Multiplayer, Find Game, **Horizon World** (the first playlist).
  The server puts you into the fullest open world (8 players each) or you open a new one,
  and everyone who picks it after you is placed with you. A player who arrives while the
  world's free roam is running waits in its lobby until the round ends (rounds last 10
  minutes; `--world-round-minutes` on the server, 0 for endless) and then drives with
  everyone. When the world's host leaves, the others keep driving and the next players are
  placed with them. To drop into a running free roam at once: Find Custom Game, the FREE
  ROAM tab, a world, JUMP IN (someone has to have started a public custom Free Roam).
  Details: [`docs/online_vision.md`](docs/online_vision.md).
  To play together in a party: everyone opens
  Multiplayer; one player picks Invite Friends in the party lobby (there is no Guide, so
  this invites everyone in the room) and the others join that party on their own
  (`live_accept_invites`). The party leader then picks Create Custom Game, sets the game
  type under Setup Game (Free Roam, races, ...), saves the setup (YES) and starts once
  the others are ready. Or, without a party: Find Game, then the Races playlist; the
  first player hosts the playlist's lobby and the next ones join it, and the race starts
  after the intermission once two players are in. The server also stands in for Turn 10's
  title services ("the Horizon server", `docs/title_services.md`): the playlists, the
  rounds' tracks, and online XP, which it keeps per player (`players/` in its data
  directory) and gives back at every sign-in; credits stay in your save.
- **Frame rate:** `frame_rate = 60` in `forza.toml` (or `tools/play.sh --frame_rate=60`)
  runs the game at 60 fps instead of the console's 30. The game times its physics and
  clocks in real time, so they keep their speed. Free roam runs 59 fps; a race with 7 AI
  cars about 42 fps for now, bound by the GPU emulation
  ([`docs/framerate.md`](docs/framerate.md)).
- **DLC:** install your DLC packages (the `4D5309C9/00000002/` folder of your content)
  once with `python3 tools/install_dlc.py /path/to/4D5309C9/00000002`.
- **Saves** live in `~/.local/share/forza/B13EBABEBABEBABE/4D5309C9/`.
- **Your Xenia save:** `tools/play.sh --xenia` copies your Xenia Canary profile's Forza
  Horizon save (`~/xenia_canary_windows/content/<XUID>/4D5309C9`, or
  `$FORZA_XENIA_CONTENT/<XUID>/4D5309C9`) into `~/.local/share/forza/xenia-<XUID>/` and
  plays it signed in with that XUID: Forza ties its save to the profile's XUID, and
  refuses (freezes on the title screen) a save made under another one. The copy is made
  once, so progress made here stays in it; `--xenia-refresh` copies the Xenia save again.
  The Xenia original is never modified. With several Xenia profiles, name one:
  `tools/play.sh --xenia E030000004B490FA`. (Equivalent by hand: copy the save under the
  runtime's profile folder and start with `--profile_xuid=<XUID>`.)

## Legal

Forza Horizon is © Microsoft. This project is not affiliated with Microsoft, Playground
Games or Turn 10 Studios. It contains no game code or assets; you must own the game.
