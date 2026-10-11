# Frame rate above 30 fps

Status: `frame_rate = 60` in `forza.toml` (or `--frame_rate=60`) runs the game at 60 fps.
The game times its simulation in real time, so physics, the race clock and the videos keep
their speed. Addresses are in `default.xex` (base version); `docs/perf.md` explains the
measurements.

## How Forza paces itself

**Frame limiter: the vblank callback.** The game registers `sub_8257E888` as D3D's vertical
blank callback (`sub_829EF650`, called at `0x8259CB9C`). On every vblank it stores the time
and the vblank data and calls `sub_8247C678`, which counts vblanks (`0x832E126C`) and, once
the count reaches 2, sets the main loop's event (handle at `0x832E1260`) and clears the count.
The main loop (`sub_823ED888`) waits on that event once per frame. At the console's 60 Hz that is 30 fps.

**Frame time: the kernel's millisecond tick.** After the wait the main loop reads a clock
(the object at `0x832ADD20`: `KeTimeStampBundle->TickCount` plus an offset, `sub_82CEBC40`)
and takes the milliseconds since the last frame (16 if more than 4 s passed):

```
dt = ms * 0.001
if the frame took 16 or 17 ms:   dt = 1/59.94, the difference goes into a leftover
                                 that is paid back once it exceeds 1 ms
otherwise:                       dt = max(ms * 0.001 + leftover, 0.0001), leftover = 0
```

(skipped, dt = ms * 0.001, when `sub_8247C168` or the clock's +0x50 method says so). The
result is stored at `game+0x1C0` and handed to the per-frame updates. The 16/17 ms case is
the engine's 60 fps path: Forza Horizon runs on Forza Motorsport 4's engine, which ran at
60 fps on the console. The physics world step
(`sub_82D4E2E0`) splits the dt it is given (clamped to 0.2 s) into at most two substeps of at
most 1/30 s.

**Debug options.** A table of developer options (names in `default.xex`, parsed by
`sub_824F8150`, defaults set in `sub_824F7898`) shows the design: `unlockframerate` and
`framesperrender` (the main loop skips the vblank wait when `unlockframerate` is set or
`framesperrender` is not 1), `frontend30fps` (on: the vblank divider of 2 above; off: a
wake-up every vblank), `mainthread30fps`, `lockupdatetimeto60fps` (dt = 1/59.94 always),
`forcephysicsminupdatehz`, `forcecarphysicsupdatehz`, `syncwait` (present interval 1 instead
of immediate), `showframerate`. Retail builds have no command line to set them.

So the frame rate is the guest vblank rate divided by 2, and the simulation does not
depend on it: raising the vblank rate is enough.

## Measurements

Free roam: the user's Xenia save, 90 s at full throttle. Race: the GoPro Millennia Masters
festival race (sign-up at the save's spawn point; Clear Springs Circuit, 7 AI cars),
throttle held from the countdown, a screenshot every ~2 s with the race timer and the
speedometer. Clean runs: a reserved window, one game at a time (docs/perf.md). The 240 Hz
row is from a contended run.

| Guest vblank | Main menu | Free roam | Race | Race clock / real time | Speed at race time ~0.7 / ~2.8 / ~5 s |
| --- | --- | --- | --- | --- | --- |
| 60 Hz (default) | 30.0 fps | 29.9 fps, p50 33.4 ms | 30.0 fps, p50 33.4 ms | 23.332 s / 23.339 s | 33 / 101 / 148 km/h |
| 120 Hz (`frame_rate = 60`) | 60.0 fps | 58.9 fps, p50 16.8, p95 19.5 | 41.6 fps, p50 24.8, p95 30.2 | 22.384 s / 22.351 s | 29 / 98 / 147 km/h |
| 240 Hz (contended) | | 57-64 fps, p50 15.9-17.2 | 40-50 fps, p50 19.3-24.7 | 22.491 s / 22.448 s | 30 / 106 / 157 km/h |

The race clock keeps real time (the difference is the screenshot latency, about 0.1 s), and
the car accelerates the same (0-100 km/h in about 2.8 s; the spread is the launch;
contended runs at 120 Hz gave the same). Past 5 s the runs differ because of the AI cars
and the first corner. No texture or rendering fault in any of the runs, and 10 free-roam
loads at 60 fps without a fault (`tools/repro_freeroam.sh` with `REX_FRAME_RATE=60`). The
intro videos play at their speed at 120 Hz (they present
every vblank, 120 fps, and show the same frames at the same times as at 60 Hz).

The SDK's 10 ms sleep in XMPGetPlaybackController (`FORZA_XMP_NOSLEEP`, docs/perf.md) does
not limit the frame rate: free roam holds 60 fps at 120 Hz with it (contended runs, the
same with and without).

## What bounds a frame at 60

Not the limiter. A CPU profile of the race at a 120 Hz vblank (contended, 23 s, 3 cores
busy): the render thread is busy 97% of the time, about 70% of it spinning in D3D's
`BlockOnFence` (`sub_823E91F0`, polling the GPU's fence write-back through `sub_829F04A8`),
that is, waiting for the emulated GPU; the GPU command processor thread uses about 66% of a
core (register writes, packet parsing). So races are bound by the GPU emulation (the command
processor plus the host GPU), free roam only just fits in 16.7 ms, and a 240 Hz vblank
(a 120 fps target) gains little. The SDK's `Audio_Worker` thread spins on a mutex
(`pthread_mutex_trylock`, about 75% of a core): CPU time the other threads lack on a busy
machine.

## What breaks at higher rates

Nothing measured at 60 fps. From the code, above 60 fps the frame time is whole
milliseconds (8 or 9 ms at 120 fps, so each frame's dt is off by up to 8%, though their sum
stays right), and at several hundred fps it is 1-3 ms, or 0.1 ms (slow motion) when two
frames fall in the same millisecond. Xenia's `vsync = false` makes the guest vblank 1 kHz,
and with the divider of 2 the game then runs as fast as it can, which probably explains the
broken physics seen there. The texture problems seen in Xenia were not reproduced here.

## The frame_rate setting

`frame_rate = 60` (`src/main.cpp`; 30 is the default; it needs a restart) makes the guest
vblank 120 Hz (`video_mode_refresh_rate`, which `VdQueryVideoMode` reports and the SDK's
VSync thread follows), unless `video_mode_refresh_rate` is set explicitly. Above 60:
`video_mode_refresh_rate = 240` targets 120 fps (the SDK clamps the rate to 24-240 Hz, so
this is the most this scheme gives), but the port does not reach it yet (above).

Not checked yet: online races at 60 fps (and against a player at 30), the opening drive and
the festival intro video.
