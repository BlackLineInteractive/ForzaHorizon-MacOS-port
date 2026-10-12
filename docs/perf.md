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
  100 ms; `ontarget` = % of frames within +-20% of the target frame time (33.3 ms, or
  16.7 ms with `frame_rate = 60`; two guest vblanks); `pipelines` = graphics pipelines
  created in the window (the plugin's "Creating graphics pipeline state" log lines,
  placeholders included).
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
RADV) was shared with other game instances and builds, each game
using 1.5-2.5 cores. Rules:

- Numbers for this file and for before/after comparisons come from a clean window: take
  the lock file `BENCH_LOCK` (`owner expiry-epoch purpose`, see `tools/bench_lock.sh`) for at most
  15 minutes and pause other load. Delete it when done.
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
| 2026-10-10 | frame_rate 30 | freeroam (Xenia save) | warm | 4.0-5.8, no other game (reserved) | main menu | guest | 30.0 | 33.5 | 34.1 | 34.2 | 34.4 | 29.1 | 0 | 0 | 100 |
| 2026-10-10 | frame_rate 60 | freeroam (Xenia save) | warm | 4.0-5.8, no other game (reserved) | main menu | guest | 60.0 | 16.8 | 17.3 | 17.4 | 17.8 | 56.9 | 0 | 0 | 100 |
| 2026-10-10 | frame_rate 30 | freeroam (Xenia save) | warm | 4.0-5.8, no other game (reserved) | free roam | guest | 29.9 | 33.4 | 35.5 | 38.9 | 90.4 | 18.7 | 2 | 0 | 98.7 |
| 2026-10-10 | frame_rate 30 | freeroam (Xenia save) | warm | 4.0-5.8, no other game (reserved) | free roam | present | 29.9 | 33.4 | 34.4 | 34.9 | 84.8 | 20.1 | 2 | 0 | 99.3 |
| 2026-10-10 | frame_rate 60 | freeroam (Xenia save) | warm | 4.0-5.8, no other game (reserved) | free roam | guest | 58.9 | 16.8 | 19.5 | 24.8 | 46.8 | 32.4 | 8 | 0 | 94.8 |
| 2026-10-10 | frame_rate 60 | freeroam (Xenia save) | warm | 4.0-5.8, no other game (reserved) | free roam | present | 58.8 | 16.8 | 18.0 | 25.5 | 46.7 | 31.1 | 10 | 0 | 96.6 |
| 2026-10-10 | frame_rate 30 | race (festival race, 7 AI cars) | warm | 4.0-5.8, no other game (reserved) | race | guest | 30.0 | 33.4 | 35.8 | 37.1 | 58.0 | 24.1 | 0 | 0 | 99.4 |
| 2026-10-10 | frame_rate 60 | race (festival race, 7 AI cars) | warm | 4.0-5.8, no other game (reserved) | race | guest | 41.6 | 24.8 | 30.2 | 34.1 | 44.8 | 26.4 | 0 | 0 | 18.4 |
| 2026-10-10 | frame_rate 60 | race (festival race, 7 AI cars) | warm | 4.0-5.8, no other game (reserved) | race | present | 41.6 | 24.9 | 32.4 | 34.0 | 50.3 | 26.5 | 1 | 0 | 18.6 |
| 2026-10-11 | GPU A/B: SDK as shipped (nightly runtime) | race (festival race, 7 AI cars) | warm | under 2 at start, no other game (reserved) | race | guest | 41.4 / 42.4 | 24.8 / 24.7 | 29.4 / 30.5 | 32.8 / 33.6 | 50.1 / 53.7 | 26.6 / 26.8 | 1 / 1 | 0 | 15.8 / 23.8 |
| 2026-10-11 | GPU A/B: runtime with Reach SDK patch 0028 only | race (festival race, 7 AI cars) | warm | under 2 at start, no other game (reserved) | race | guest | 49.3 | 17.8 | 25.9 | 26.8 | 32.4 | 35.8 | 0 | 0 | 56.7 |
| 2026-10-11 | GPU A/B: plugin with Reach SDK patches 0029-0032 only | race (festival race, 7 AI cars) | warm | under 2 at start, no other game (reserved) | race | guest | 50.3 | 18.4 | 26.2 | 27.8 | 42.1 | 32.7 | 1 | 0 | 60.2 |
| 2026-10-11 | GPU A/B: Reach SDK patches 0028-0032 | race (festival race, 7 AI cars) | warm | under 2 at start, no other game (reserved) | race | guest | 59.7 / 59.7 | 16.8 / 16.8 | 17.9 / 17.9 | 20.9 / 20.7 | 33.6 / 35.7 | 42.6 / 43.2 | 1 / 1 | 0 | 98.6 / 98.6 |
| 2026-10-12 | frame_rate 60, before the frame time hook | race (festival race, 7 AI cars), 26 s | warm | 1.5, no other game (reserved) | race | guest | 59.6 | 16.8 | 18.1 | 21.6 | 28.7 | 41.5 | 0 | 0 | 97.9 |
| 2026-10-12 | frame_rate 60, before the frame time hook | race (festival race, 7 AI cars), 26 s | warm | 1.5, no other game (reserved) | race | present | 59.0 | 16.8 | 17.4 | 32.1 | 43.9 | 25.4 | 14 | 0 | 97.8 |
| 2026-10-12 | frame_rate 60 (frame time hook) | race (festival race, 7 AI cars), 26 s | warm | 3.5, no other game (reserved) | race | guest | 59.6 | 16.8 | 18.0 | 21.9 | 29.1 | 42.5 | 0 | 0 | 98.0 |
| 2026-10-12 | frame_rate 60 (frame time hook) | race (festival race, 7 AI cars), 26 s | warm | 3.5, no other game (reserved) | race | present | 58.7 | 16.8 | 17.7 | 32.7 | 44.2 | 25.4 | 15 | 0 | 96.7 |
| 2026-10-12 | frame_rate 120 (240 Hz vblank) | race (festival race, 7 AI cars), 26 s | warm | 2.7, no other game (reserved) | race | guest | 75.7 | 13.0 | 17.6 | 18.6 | 23.9 | 50.8 | 0 | 0 | 25.8 |
| 2026-10-12 | frame_rate 120 (240 Hz vblank) | race (festival race, 7 AI cars), 26 s | warm | 2.7, no other game (reserved) | race | present | 73.0 | 13.1 | 17.2 | 18.2 | 30.3 | 49.5 | 1 | 0 | 19.9 |
| 2026-10-12 | frame_rate 144 (144 Hz vblank) | race (festival race, 7 AI cars), 26 s | warm | 5.1, no other game (reserved) | race | guest | 65.2 | 14.3 | 20.8 | 21.8 | 31.8 | 42.8 | 1 | 0 | 0.0 |
| 2026-10-12 | frame_rate 144 (144 Hz vblank) | race (festival race, 7 AI cars), 26 s | warm | 5.1, no other game (reserved) | race | present | 65.3 | 14.1 | 21.0 | 21.5 | 28.2 | 44.2 | 1 | 0 | 0.1 |
| 2026-10-12 | frame_rate 60, before the frame time hook | freeroam (Xenia save), 50 s | warm | 4.6, no other game (reserved) | free roam | guest | 59.9 | 16.7 | 18.1 | 19.7 | 30.5 | 42.4 | 0 | 0 | 98.3 |
| 2026-10-12 | frame_rate 60, before the frame time hook | freeroam (Xenia save), 50 s | warm | 4.6, no other game (reserved) | free roam | present | 59.9 | 16.8 | 17.5 | 18.8 | 32.9 | 47.4 | 0 | 0 | 99.5 |
| 2026-10-12 | frame_rate 60 (frame time hook) | freeroam (Xenia save), 50 s | warm | 3.6, no other game (reserved) | free roam | guest | 59.9 | 16.7 | 17.8 | 19.3 | 31.3 | 44.7 | 0 | 0 | 99.0 |
| 2026-10-12 | frame_rate 60 (frame time hook) | freeroam (Xenia save), 50 s | warm | 3.6, no other game (reserved) | free roam | present | 59.9 | 16.8 | 17.2 | 18.0 | 32.9 | 48.7 | 0 | 0 | 99.6 |
| 2026-10-12 | frame_rate 120 (240 Hz vblank) | freeroam (Xenia save), 50 s | warm | 3.7, no other game (reserved) | free roam | guest | 115.2 | 8.4 | 11.5 | 13.1 | 27.6 | 63.7 | 15 | 0 | 91.0 |
| 2026-10-12 | frame_rate 120 (240 Hz vblank) | freeroam (Xenia save), 50 s | warm | 3.7, no other game (reserved) | free roam | present | 113.1 | 8.5 | 12.5 | 16.3 | 26.7 | 55.0 | 42 | 0 | 89.0 |
| 2026-10-12 | frame_rate 144 (144 Hz vblank) | freeroam (Xenia save), 50 s | warm | 4.6, no other game (reserved) | free roam | guest | 71.9 | 13.8 | 15.3 | 16.4 | 27.7 | 52.1 | 1 | 0 | 0.1 |
| 2026-10-12 | frame_rate 144 (144 Hz vblank) | freeroam (Xenia save), 50 s | warm | 4.6, no other game (reserved) | free roam | present | 71.9 | 13.8 | 14.8 | 15.7 | 21.8 | 57.6 | 0 | 0 | 0.0 |
| 2026-10-12 | frame_rate 144, SDK patch 0037 (288 Hz vblank) | race (festival race, 7 AI cars), 26 s | warm | 1.3, no other game (reserved) | race | guest | 70.1 | 14.2 | 18.0 | 19.0 | 23.2 | 49.8 | 0 | 0 | 2.3 |
| 2026-10-12 | frame_rate 144, SDK patch 0037 (288 Hz vblank) | race (festival race, 7 AI cars), 26 s | warm | 1.3, no other game (reserved) | race | present | 70.1 | 13.9 | 18.0 | 18.4 | 23.7 | 50.5 | 0 | 0 | 2.6 |
| 2026-10-12 | frame_rate 144, SDK patch 0037 (288 Hz vblank) | freeroam (Xenia save), 50 s | warm | 4.3, no other game (reserved) | free roam | guest | 111.5 | 9.2 | 11.2 | 12.5 | 23.1 | 67.3 | 10 | 0 | 41.4 |
| 2026-10-12 | frame_rate 144, SDK patch 0037 (288 Hz vblank) | freeroam (Xenia save), 50 s | warm | 4.3, no other game (reserved) | free roam | present | 110.6 | 9.5 | 10.8 | 13.3 | 23.7 | 65.0 | 6 | 0 | 40.8 |

- 2026-10-12 rows (docs/framerate.md): one reserved window, one game at a time, back to back
  (the load average is the previous run's game), the race driven at full throttle for 26 s
  from the countdown. "Before" is the binary before `src/hooks/frame_time.cpp`. Above 60 fps
  the guest frames are the render thread's (free roam: 50 s at full throttle): the main loop
  runs at the target rate whatever the render thread makes (`FORZA_FRAMETIME_LOG`), and render frames come in whole guest
  vblanks (12.5 or 16.7 ms at 120, 13.9 or 20.8 ms at 144 with a 144 Hz vblank, multiples
  of 3.5 ms with SDK patch 0037's 288 Hz), so `ontarget` (8.3 / 6.9 ms) is low when the GPU
  emulation is the bound. The 144 Hz-vblank rows are the build before patch 0037 (frame_rate
  144 falls back on a divider of one without it).
- `frame_rate = 60` (docs/framerate.md), one reserved window, one game at a time; the load
  average is the game's own (it keeps 3-4 cores busy). Free roam: 90 s at full throttle
  from the user's Xenia save; race: GoPro Millennia Masters (signed up at that save's spawn
  point), 25 s at full throttle from the start. `ontarget` counts against 16.7 ms at 60.
  Races are bound by the GPU emulation (the render thread waits in D3D's `BlockOnFence`).
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
  or more load on the machine at that moment (other games and builds).
- Free roam: one guest frame in ten takes 47-55 ms (p95), and the slowest 1% 70-120 ms.
  That is the stutter to explain first.
- Main menu presents: frames reach the presenter every 33 ms on average but p95 is 48 ms
  (the present cadence alternates around the guest's regular 33 ms frames): pacing to
  look at.

## GPU emulation speed (2026-10-11)

Races at `frame_rate = 60` were bound by the emulated GPU's command processor. Profiled with
user-space `perf_event_open` sampling (frame-pointer call chains; samply refuses at
`perf_event_paranoid = 2`, this works) and a wall-clock sampler of the command processor
thread; the details are in RecompiledHaloReach `docs/perf.md` > "GPU emulation speed", where
the fixes live as SDK patches 0028-0032:

- **0028 (runtime, `librexruntime.so`):** every write-watch fault (the game writing vertex
  data the GPU had uploaded, thousands a second) rechecked the page's protection by reading
  and parsing all of `/proc/self/maps` (~1,800 lines) while holding the global critical
  region. The command processor needs that lock for its shared-memory uploads and waited on
  it ~17% of the time. Now one `PROCMAP_QUERY` ioctl (Linux 6.11+).
- **0029-0032 (GPU plugin):** register writes as ranges (they were 30% of the command
  processor: 40 M a second, each with a register-table switch only for a debug log),
  `WAIT_REG_MEM` wakes on the guest vblank interrupt instead of 1 ms sleeps, shared-memory
  requests without the lock when the pages are valid, and unchanged fetch constants keep
  their texture bindings.

Results are the four "GPU A/B" rows above (one reserved window, same game binary, two runs
where two values are given): the race goes from 41-42 fps (p99 33 ms) to 59.7 fps (p50
16.8, p99 20.8 ms, 98.6% of frames on target). Either half alone reaches about 50 fps:
frames snap to the 120 Hz guest vblank, so the command processor had to fit both. This
project's SDK overlay ships the nightly `librexruntime.so`, so 0028 needs the overlay to
carry a patched runtime as Reach's does. Screenshots of the race menu and the race match the
unpatched build.
