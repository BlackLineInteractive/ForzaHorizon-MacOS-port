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

Reading so far:

- (Contended runs.) The game held its 30 fps cap in menus and close to it in free roam
  (27-29 fps) even with two Reach instances running. The 12 fps the user saw has not been
  reproduced in a measured run yet; candidates are a heavier scene, a cold shader cache,
  or more load on the machine at that moment (other agents' games and builds).
- Free roam: one guest frame in ten takes 47-55 ms (p95), and the slowest 1% 70-120 ms.
  That is the stutter to explain first.
- Main menu presents: frames reach the presenter every 33 ms on average but p95 is 48 ms
  (the present cadence alternates around the guest's regular 33 ms frames): pacing to
  look at.
