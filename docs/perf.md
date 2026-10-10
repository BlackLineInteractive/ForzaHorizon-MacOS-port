# Performance

Frame statistics use the same definitions as RecompiledHaloReach so the two projects
compare (`src/debug/frame_stats.cpp`, enabled with `RECOMP_PERF=1`):

```
PERF: scene= src=<guest|present> t= fps= p50= p95= p99= max= low1= stutters= hitches= ontarget= pipelines=
```

- One line per 10 s window, per scene change and at exit, for each source:
  `guest` = the game's frames (VdSwap), `present` = frames the GPU plugin handed to the
  presenter (SDK patch 0024; frames that drew with an async placeholder shader are not
  presented).
- Frame times in ms; `low1` = 1000 / mean of the slowest 1% of frame times;
  `stutters` = frames longer than 2x the window's p50; `hitches` = frames longer than
  100 ms; `ontarget` = % of frames within +-20% of 33.3 ms; `pipelines` = graphics
  pipelines created in the window (the plugin's "Creating graphics pipeline state" log
  lines, placeholders included).
- `RECOMP_PERF_CSV=<file>` writes every frame; `RECOMP_PERF_SCENE` names the first scene;
  `SCENE:<name>` on the input FIFO starts a new one.

## Scenarios

`tools/perf_scenario.sh SCENARIO DIR [cold|warm] [flags]` drives the game through the
input FIFO and prints the PERF lines:

| Scenario | What |
| --- | --- |
| `menu` | boot (intro video), title screen, START, main menu |
| `drive` | Single Player from a profile that has not finished the prologue: intro video, then the opening drive at full throttle |
| `freeroam` | Single Player from a profile in free roam (e.g. the user's Xenia save in a scratch `--user_data_root` with `FORZA_XUID`): loading, then 90 s of driving |

`cold` starts with an empty shader cache (`--cache_root` in the run directory); `warm` uses
the normal one.

**Machine load matters.** The test machine (Ryzen 7 7800X3D, 8 cores; Radeon RX 9060 XT,
RADV) is shared with other agents that run Halo: Reach instances and builds, each game
using 1.5-2.5 cores. Rules:

- Numbers for this file and for before/after comparisons come from a clean window: ask
  the orchestrator for one (purpose, at most 15 minutes); it pauses the other agents and
  creates the lock file `BENCH_LOCK` (`owner expiry-epoch purpose`) in the shared scratch
  directory. Delete it when done.
- The run scripts (`tools/live_session.sh`, `tools/run_forza.sh`, `tools/build.sh`)
  refuse to start while someone else holds an unexpired lock (`tools/bench_lock.sh`).
- `tools/perf_scenario.sh` records other game processes, the load average and free memory
  at the start and end and prints `status=CONTENDED` when another game ran or the
  1-minute load average was above 2. Contended results are not baselines.
- Intro videos are skipped through the input FIFO, and each scene is only labelled once
  it is reached.

## Results

Results marked CONTENDED were taken while other games ran; they are not baselines.

| Date | Commit | Scenario | Cache | Load avg | Scene | Source | fps | p50 | p95 | p99 | max | low1 | stutters | hitches | ontarget |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-10 | 741ccf4 | menu | warm | CONTENDED: ~15-20, 2 Reach instances | intro video | guest | 59.9 | 16.6 | 18.7 | 20.3 | 50.5 | 35.9 | 1 | 0 | n/a (60 fps video) |
| 2026-10-10 | 741ccf4 | menu | warm | CONTENDED: ~15-20, 2 Reach instances | main menu | guest | 30.0 | 33.4 | 35.4 | 36.8 | 39.1 | 26.1 | 0 | 0 | 100 |
| 2026-10-10 | 741ccf4 | menu | warm | CONTENDED: ~15-20, 2 Reach instances | main menu | present | 30.0 | 33.3 | 48.1 | 48.9 | 49.9 | 20.1 | 0 | 0 | 54-69 |
| 2026-10-10 | 741ccf4 | freeroam (Xenia save) | warm | CONTENDED: ~23, 2 Reach instances | free roam (8 windows) | guest | 27.2-29.4 | 33.5-35.7 | 47.5-55.0 | 52.7-74.2 | 54-118 | 10.3-18.5 | 0-9 | 0-1 | 57-71 |
| 2026-10-10 | 741ccf4 | freeroam (Xenia save) | warm | CONTENDED: ~23, 2 Reach instances | free roam (8 windows) | present | 27.0-29.3 | 33.4-33.8 | 40.3-56.6 | 50.9-83.1 | 54-118 | 9.3-18.5 | 0-8 | 0-1 | 81-94 |
| 2026-10-10 | 96c43fd+ | freeroam (Xenia save), SDK XMPGetPlaybackController (10 ms sleep) | warm | 1.9-4.5, no other game (CLEAN) | free roam (10 windows) | guest | 29.9-30.0 | 33.3-33.5 | 35.0-35.7 | 35.9-51.4 | 37-62 | 17.6-27.4 | 0 | 0 | 96-100 |
| 2026-10-10 | 96c43fd+ | freeroam (Xenia save), XMPGetPlaybackController answered without the sleep | warm | 4.4-4.5, no other game (CONTENDED by load) | free roam (10 windows) | guest | 29.6-30.0 | 33.3-33.5 | 35.0-36.4 | 35.9-63.5 | 37-81 | 13.7-27.0 | 0-1 | 0 | 96-100 |
| 2026-10-10 | build before 0025 (GJK hook) | freeroam (Xenia save) | warm | 2.5, no other game | free roam | guest | 29.8 | 33.3 | 36.0 | 47.7 | 75.5 | 17.1 | 5 | 0 | 96.9 |
| 2026-10-10 | build before 0025 (GJK hook) | freeroam (Xenia save) | warm | 2.5, no other game | free roam | present | 29.6 | 33.4 | 34.5 | 65.3 | 100.7 | 14.2 | 15 | 1 | 98.2 |
| 2026-10-10 | patch 0025, no hook | freeroam (Xenia save) | warm | 4.2, no other game | free roam | guest | 29.9 | 33.3 | 35.3 | 37.8 | 66.6 | 20.8 | 0 | 0 | 99.1 |
| 2026-10-10 | patch 0025, no hook | freeroam (Xenia save) | warm | 4.2, no other game | free roam | present | 29.8 | 33.4 | 34.4 | 35.5 | 68.2 | 19.1 | 3 | 0 | 99.3 |

- SDK patch 0025 (dot products give QNaN on overflow) A/B in one reserved window with no
  other game running (the script still says CONTENDED: the load average was above 2). The
  run before compiled 52 pipelines in free roam and the run after 20 (the first run warmed
  the shared cache), which explains the better tail after; the patch itself costs nothing
  measurable.

Reading so far:

- XMPGetPlaybackController (music player app 0xFA, message 0x7001B): RecompiledHaloReach
  found its audio thread asking once per frame and the SDK's 10 ms sleep (on non-main
  threads) holding it to 45 fps. Forza polls it from a loop instead: about 46 calls/s
  with the sleep, about 10,500/s without it (a core spinning), and free roam holds 30 fps
  either way (the two rows above). The SDK's answer stays; `FORZA_XMP_NOSLEEP=1` answers
  at once, for frame-rate experiments above 30 fps.
- (Contended runs.) The game held its 30 fps cap in menus and close to it in free roam
  (27-29 fps) even with two Reach instances running. The 12 fps the user saw has not been
  reproduced in a measured run yet; candidates are a heavier scene, a cold shader cache,
  or more load on the machine at that moment (other agents' games and builds).
- Free roam: one guest frame in ten takes 47-55 ms (p95), and the slowest 1% 70-120 ms.
  That is the stutter to explain first.
- Main menu presents: frames reach the presenter every 33 ms on average but p95 is 48 ms
  (the present cadence alternates around the guest's regular 33 ms frames): pacing to
  look at.
