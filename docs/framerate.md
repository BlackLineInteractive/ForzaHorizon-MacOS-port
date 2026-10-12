# Frame rate above 30 fps

Status: `frame_rate` in `forza.toml` (or `--frame_rate=N`) runs the game at 30 (the
console's, the default) or any rate from 60 to 240: 60, 120 and 144 are tested. The game
times its simulation in real time, so physics, the race clock and the videos keep their
speed at every rate; above 30 its frame time comes from the guest tick clock instead of
the kernel's millisecond tick (`src/hooks/frame_time.cpp`), so motion stays even above 60.
Addresses are in `default.xex` (base version); `docs/perf.md` explains the measurements.

## How Forza paces itself

**Frame limiter: the vblank callback.** The game registers `sub_8257E888` as D3D's vertical
blank callback (`sub_829EF650`, called at `0x8259CB9C`). On every vblank it stores the time
and the vblank data and tail-calls `sub_8247C678`, which counts vblanks (`0x832E126C`) and
sets the main loop's event (handle at `0x832E1260`), clearing the count, when:

- the developer option `mainthread30fps` (options object `0x832E29A0` +0x95B, the static
  object `sub_82479E88` returns; on by default) is set: the count has reached 2;
- it is off: every vblank, unless `frontend30fps` (+0x95A, off by default) is set and the
  flag `0x832E1269` is clear (then every second vblank).

The main loop (`sub_823ED888`) waits on that event once per frame. At the console's 60 Hz
that is 30 fps. Forza Motorsport 4, whose engine this is, ran with `mainthread30fps` off at
60 fps.

**Rendering is decoupled.** The main loop runs the simulation and hands the frame to a
render thread; when the render thread (bound by the GPU emulation) is still busy, the main
loop does not wait for it. In a race at a 144 fps target the main loop ran 144 times a
second while the render thread swapped about 70 frames a second (below). So the frame rate the
player sees is the render thread's, and the simulation keeps its own rate.

**Frame time: the kernel's millisecond tick.** After the wait the main loop reads a clock
(the object at `0x832ADD20`: `KeTimeStampBundle->TickCount` plus an offset, `sub_82CEBC40`)
and takes the milliseconds since the last frame (`r30`, 16 if more than 4 s passed):

```
dt = ms * 0.001                                     (f31)
if sub_8247C168() or the clock's +0x50 method:      dt as it is, leftover = 0
else if the frame took 16 or 17 ms:                 dt = 1/59.94, the difference goes into a
                                                    leftover (f30) paid back once it exceeds 1 ms
else:                                               dt = max(ms * 0.001 + leftover, 0.0001), leftover = 0
lockupdatetimeto60fps (+0x956):                     dt = 1/59.94
```

The result is stored at `game+0x1C0` (`stfs f31` at `0x823EDB84`) and handed to the
per-frame updates in `f31`. The 16/17 ms case is the engine's 60 fps path.

**Physics step.** The physics world step (`sub_82D4E2E0`) clamps the dt it is given to
0.2 s and runs `n = min(ceil(dt * CarPhysicsUpdateHz), 2)` substeps of `min(dt / n, 1/30)`
(`CarPhysicsUpdateHz` is 359 in `media/physics.zip:PhysicsSettings.ini`, the physics
settings object `0x834AA248` +0x178; the developer option `forcecarphysicsupdatehz`
overrides it). So every frame longer than 2.8 ms gets two substeps: 16.7 ms each at 30 fps,
8.3 ms at 60, 3.5 ms at 144. The car simulation is variable-step; there is no fixed-rate
accumulator to keep in step with the frame rate.

**Debug options.** A table of developer options (names in `default.xex`, parsed by
`sub_824F8150`, defaults set in `sub_824F7898`) shows the design: `unlockframerate` (+0x1048)
and `framesperrender` (+0x964; the main loop skips the vblank wait when `unlockframerate` is
set or `framesperrender` is not 1), `frontend30fps`, `mainthread30fps`,
`lockupdatetimeto60fps`, `forcephysicsminupdatehz`, `forcecarphysicsupdatehz`, `syncwait`
(present interval 1 instead of immediate), `showframerate`. Retail builds have no command
line to set them.

## What changes above 60 fps, and the fix

**Frame time.** Above 60 fps the millisecond tick makes each frame's dt whole milliseconds.
The frames start on emulated vblanks that the SDK's VSync thread fires at its next 1 ms
check, so at 144 fps the game measured 5 to 9 ms for frames that are 6.94 ms apart (sd
0.9 ms, 13% of the frame), and now and then 0 ms (a 0.1 ms frame). The sum stays real time,
but each frame's motion is off: the car's displacement from one frame to the next varied
with an sd of 16.5% of its local mean at 144 fps (a race, `FORZA_FRAME_TIME=game`), against
2.6-2.8% with the fix.

`src/hooks/frame_time.cpp` (above 30 fps) answers the main loop's call of `sub_8247C168`
(return address `0x823EDB08`, right after `f31 = ms * 0.001`) with true and `f31` set from
the guest tick clock, so the loop stores and passes on that dt (and clears its leftover).
Each frame gets a timestamp: the nominal time of the vblank that released it if the frame
started within 2 ms of that vblank's callback, else the time it started (a late frame). The
nominal vblank times are kept from the callbacks (`sub_8247C678` is overridden too): the
VSync thread fires vblank j at the first 1 ms check after start + j * interval, so a
callback is never early and the schedule is the earliest one consistent with every
callback. dt is the difference of two timestamps, so frames that keep up get exactly the
frame period, late frames their real length, and the sum is real time. The game's rules
stay: more than 4 s still counts as one 60 Hz frame, and dt is at least 0.1 ms. At 144 fps
99-100% of the frames get exactly 6.944 ms (`FORZA_FRAMETIME_LOG=1` logs the statistics).

**Pacing.** The divider of two stays above 30 and the guest vblank runs at twice the frame
rate (60 -> 120 Hz, 120 -> 240 Hz, 144 -> 288 Hz). A fast vblank matters when the GPU
emulation is the bound: the emulated GPU's swap waits end on a vblank (SDK patch 0030), so
the render thread's frames come in whole vblanks. The SDK capped the guest refresh rate at
240 Hz (`GetConfiguredVideoModeRefreshRate`, and the setting's range); SDK patch 0037
(`docs/sdk_patches.md`) raises it to 480 Hz. Without that patch the game falls back on a
divider of one for rates whose double does not fit (the hook clears `mainthread30fps`
before each vblank's check; `frame_time.cpp` reads the setting's range to know): 144 fps
then runs a 144 Hz vblank, and every render frame that misses 6.9 ms takes 13.9: free roam
rendered 71.9 fps instead of 111.5, and a race 65.2 instead of 70.1 (clean runs below).

**What else reads the frame.** The main loop hands this dt to its per-frame updates (14
calls, among them the world update `sub_823E40D8`, which steps the physics). Replays and Rivals
ghosts are recorded on time and error thresholds, not per frame
(`GameTunableSettings.ini`: `ReplayRecordKeyframeFrequency 20`, position, orientation and
velocity buffers, playback springs). AI traffic's path prediction updates every N frames
(`AI/Traffic/PathPrediction/UpdateIntervalFrames`), which only makes it more frequent at
higher rates. The pre-race camera sequence and the 3-2-1 countdown take the same time at 60
and 144 (start pressed to GO: 17.1 s and 16.9 s, read from the race clock in screenshots).

## Online with mixed frame rates

No gate is needed: a 144 fps player and a 60 fps player race together normally. Test (two
instances on one machine, private Forza Live server on 21600/21601, the Horizon World with
a world event, `--world-events 4 --world-event-laps 1`, both cars driven by
`tools/autodrive.py`, CPU drivers on both consoles; scratch harness derived from the
`docs/online_vision.md` tests): A (host) at 144, B at 60, then both at 60 as the baseline.
Both raced the event to the end and went back to the world (the harness's checks), each
seeing the other's car. `tools/carlog.py` sampled both games at once (same host clock) and
`tools/net_sync_report.py` compared each player's own car with its copy on the other
console (the first 144 run used a 144 Hz vblank, the second SDK patch 0037's 288 Hz):

| Pair | A's car as B sees it: mean / p95 distance | B's car as A sees it | Datagrams a second (both ways, per console) |
| --- | --- | --- | --- |
| A 60, B 60 | 0.06 / 0.12 m | 0.05 / 0.13 m | about 194 |
| A 144 (144 Hz), B 60 | 0.31 / 0.76 m (0.16 / 0.54 m shifted by 20 ms) | 0.06 / 0.14 m | about 266 (A sends about 150 a second, B about 100) |
| A 144 (288 Hz), B 60 | 0.42 / 0.83 m (0.04 / 0.12 m shifted by 20 ms) | 0.05 / 0.12 m | about 300 (A sends about 200 a second, B about 100) |

At about 25 m/s that is a few centimetres to a few tens of centimetres: the 144 fps car's copy
on the 60 fps console runs about 20 ms ahead (shifted by 20 ms it is as close as at 60
against 60), well below the network delay of a real connection. The traffic grows with the
frame rate (about 65 datagrams a second each way at 30 fps in an earlier free-roam test,
about 100 at 60, 150-200 at 144, more when the render thread keeps up): a 144 fps player
sends up to twice the traffic of a 60 fps one (about 50 KB/s to each peer at about 250
bytes a datagram). Through the server's relay (64 KB/s per player, `--rate-limit`,
`docs/hosting.md`) that budget runs out sooner with several peers; direct peer-to-peer
paths are not limited. Seen in both
runs and unrelated to the frame rate: the host's race clock started about 12 s before the
peer's (A 00:15.150, B 00:03.100 at the same moment, 60 against 60).

**Rivals ghosts.** A ghost recorded at 30 fps (DriverA's 1:47.228 lap, ghost 4 of the test
server's data) raced in X RIVALS at 144 and at 60 fps (the user's Xenia save, private
server, `tools/autodrive.py` on the saved line): the ghost car (kind 2 in the car list)
reached each point of the lap at the same time after its start in both runs: the
difference was constant within 16 ms from 100 m to 3.3 km (a 0.72 s constant from the
start detection). A Rivals lap driven at 144 fps (1:55.546, against a board whose best
was 200 s so that the game submits it) was uploaded as a 17,992-byte ghost (header
`0000028D 000043B3 00000285 00000ABC`), the size of the 30 fps ghosts of similar laps
(17,332 bytes for 1:55.13, header `000002A0 0000410C 00000298 00000ABC`): the game records
ghosts on its thresholds, not per frame. That ghost, raced at 60 fps as the rival,
followed the lap the player drove at 144 with a constant delay (2.758 s from the start
detection, sd 15 ms over 58 points matched by position along the lap; 13 ms apart between
the first and the last ten). (In these runs the game submitted a Rivals lap only when it
beat the board's best from `GetBestScores`, at 60 and 144 alike.)

## The frame_rate setting

`frame_rate` (`src/main.cpp`; 30 by default; 60 to 240 allowed; it needs a restart) sets the
guest vblank (`video_mode_refresh_rate`, which `VdQueryVideoMode` reports and the SDK's
VSync thread follows) to twice the frame rate, or to the frame rate when twice is past the
SDK's limit (480 Hz with patch 0037, 240 without), unless `video_mode_refresh_rate` is set
explicitly (then the frame rate is that rate divided by the same divider). The frame
stats' `ontarget` uses the same target. Test switches: `FORZA_FRAME_TIME=game` (the millisecond frame time),
`FORZA_VBLANK_DIVIDER=1|2`, `FORZA_FRAMETIME_LOG=1`, `FORZA_FRAMETIME_CSV=<path>` (per frame:
time, dt, the game's ms, on target, the player's car position).

## Measurements

Clean runs: one reserved window, one game at a time (`docs/perf.md`, 2026-10-12 rows). Race:
the GoPro Millennia Masters festival race (sign-up at the spawn point of the user's Xenia
save; Clear Springs Circuit, 7 AI cars), full throttle for 26 s from the countdown. Free
roam: the same save, full throttle for 50 s. "Guest" frames are the render thread's swaps;
the main loop ran at the target rate in every run.

| frame_rate (guest vblank) | Race: guest fps, p50 / p95 / p99 ms, stutters | Free roam: guest fps, p50 / p95 / p99 ms, stutters | Main loop dt: mean, sd (game's ms sd) |
| --- | --- | --- | --- |
| 60 before the hook (120 Hz) | 59.6, 16.8 / 18.1 / 21.6, 0 | 59.9, 16.7 / 18.1 / 19.7, 0 | (1/59.94 snaps) |
| 60 (120 Hz) | 59.6, 16.8 / 18.0 / 21.9, 0 | 59.9, 16.7 / 17.8 / 19.3, 0 | 16.667, 0.08 ms (0.81) |
| 120 (240 Hz) | 75.7, 13.0 / 17.6 / 18.6, 0 | 115.2, 8.4 / 11.5 / 13.1, 15 | 8.333, 0.08 ms (0.74) |
| 144 (288 Hz, SDK patch 0037) | 70.1, 14.2 / 18.0 / 19.0, 0 | 111.5, 9.2 / 11.2 / 12.5, 10 | 6.944, 0.18 ms (0.83) |
| 144 without patch 0037 (144 Hz, divider 1) | 65.2, 14.3 / 20.8 / 21.8, 1 | 71.9, 13.8 / 15.3 / 16.4, 1 | 6.944, 0.19 ms (0.85) |

- **Races are bound by the GPU emulation** above 60: the render thread makes 76 fps at a
  120 fps target and 70 at 144, its frames whole vblanks (above); free roam makes 115 at
  120 and 112 at 144. At 60 nothing changed with the hook (same fps and tail). With patch
  0037 the audio the game submits kept its rate at 144 (940 frames of 256 samples every
  5 s, `FORZA_AUDIOLOG`, as at 60), and the 1 ms polling of the SDK's VSync thread shows no
  worse tail at 288 Hz than at 240 Hz (p99 12.5 ms at 144 against 13.1 ms at 120).
- **Simulation speed.** The race clock against real time between two screenshots 18.3 s
  apart: 18.367 / 18.315 s (60 before), 18.367 / 18.315 (60), 18.284 / 18.315 (120),
  18.458 / 18.360 (144); the differences are the screenshot latency (up to 0.1 s). The
  car's distance from the launch (sampled from guest memory, `tools/carlog.py`) at 1 / 2 /
  3 s: 9.1 / 28.5 / 55.2 m (60 before), 9.0 / 28.3 / 55.9 (60), 9.0 / 28.2 / 56.1 (120),
  9.0 / 28.4 / 56.8 (144); 0-100 km/h in 2.38-2.48 s at every rate (2.67 s in the 60-before
  run, a slower launch). Past 5 s the AI cars and the first corner make the runs differ.
- **The same lap at every rate.** `tools/autodrive.py` driving the saved racing line
  (`AD_PATH_LOAD`) from the grid back to the start point, contended runs: 114.58 s at 60,
  114.56 s at 120, 115.13 s at 144 (the driver's own spread is about a second); 0-100 km/h
  2.40 / 2.43 / 2.39 s.
- **Even motion.** The player's car moved by the same distance every frame within 2.8% at
  144 (sd of each frame's displacement over the mean of its neighbours; 1.1% at 60, 1.2% at
  120), following dt within 0.5%. With the game's millisecond frame time at 144
  (`FORZA_FRAME_TIME=game`, contended) the same measure was 16.5%.
- Menus run at the target (144.0 fps, p99 8.0 ms at 144). No rendering fault in the
  screenshots at any rate. The race-clock, acceleration and lap checks at 144 ran before
  patch 0037 (144 Hz vblank); the Rivals runs and the second online
  run used it.

Earlier results (2026-10-10, before the GPU patches; 30 and 60 fps):

| Guest vblank | Main menu | Free roam | Race | Race clock / real time | Speed at race time ~0.7 / ~2.8 / ~5 s |
| --- | --- | --- | --- | --- | --- |
| 60 Hz (default) | 30.0 fps | 29.9 fps, p50 33.4 ms | 30.0 fps, p50 33.4 ms | 23.332 s / 23.339 s | 33 / 101 / 148 km/h |
| 120 Hz (`frame_rate = 60`) | 60.0 fps | 58.9 fps, p50 16.8, p95 19.5 | 41.6 fps, p50 24.8, p95 30.2 | 22.384 s / 22.351 s | 29 / 98 / 147 km/h |

The intro videos play at their speed at a 120 Hz vblank (they present every vblank and show
the same frames at the same times as at 60 Hz). The SDK's 10 ms sleep in
XMPGetPlaybackController (`FORZA_XMP_NOSLEEP`, docs/perf.md) does not limit the frame rate.

**Tools.** `tools/perf_scenario.sh race DIR warm --user_data_root=<copy of the Xenia save>
--frame_rate=N` (with `FORZA_XUID`) runs the race scenario: free roam, the sign-up at the
spawn (inputs X, A, A, X, then A at the race menu), the throttle held from the countdown,
screenshots for the race clock and the car positions. `tools/carlog.py PID SECS OUT`
samples every car's position from a running game at 250 Hz; `tools/frametime_report.py DIR`
reads `FORZA_FRAMETIME_CSV` (per-frame displacement against dt) and the car log (distance
from the launch, 0-100 km/h, the time back at the launch point);
`tools/net_sync_report.py A B` compares two consoles' car logs. The lap runs used
`tools/autodrive.py` with `AD_PATH_LOAD` (a saved Clear Springs racing line, written by
`AD_PATH_SAVE`). Rivals from the spawn: X (the ticket), X (RIVALS), A (the rival), A (the car), X (race
anyway), A (START RIVALS).

## Leftovers

- **Races above 60 are bound by the GPU emulation** (the render thread waits in
  `BlockOnFence`): 76 fps at 120, 70 at 144 with the SDK as it was. SDK patches 0036, 0038 and
  0039 (docs/perf.md > "GPU emulation at high refresh rates") raised the race at 144 to 97 fps
  (p99 15 ms), at 120 to 90 fps and free roam at 144 to 141; the command processor is still
  the bound.
- **Patch 0037 for RecompiledHaloReach**: the patch is written for both (Reach's own
  frame-rate scheme has the same 240 Hz cap); not ported yet.
- `tools/build_rexglue_sdk.sh` stopped at patch 0018 on a clone that already had the whole
  series (0035 changed 0018's context, so neither the forward nor the reverse check passed).
  Fixed: the series is applied to a temporary index and only files that differ are rewritten.
- Not measured: rates other than 60, 120 and 144 (165 and 240 run 330 and 480 Hz vblanks),
  more than two players online at mixed rates, the relay path (the test peers talked
  directly), the opening drive and the festival intro video above 60, Windows.
- Seen at every rate, not from this work: in a world event the peer's race clock started
  about 12 s after the host's (the cars raced together); at 60 fps in the race the frames
  handed to the presenter have a p99 of 32 ms (14-15 stutters in 26 s, before and after
  the hook) while the guest frames are steady.
- The developer options `framesperrender` and `unlockframerate` were not tried (they would
  run the main loop without the vblank wait).
