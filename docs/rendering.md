# Rendering issues

## Open: hard-edged rectangle in the speed blur

**Symptom.** At speed the game blurs the edges of the screen. A rectangle around the
player's car is never blurred, and its edge is sharp; on the console the blur fades in
smoothly toward the car.

**State (2026-10-12).** Not fixed. Two RenderDoc captures were taken in the Millennia
Masters race at full throttle (frame_rate 30, about 12 s and 18 s after GO; 7,106 draws
in the second) with `FORZA_RDCAPTURE_TRIGGER` under `renderdoccmd capture` (layer setup
as in RecompiledHaloReach `docs/menu_black_screen.md`). The draw list was made, but the
blur pass was not analysed yet. The captures were deleted to free disk space, so take new
ones. Screenshots (`FORZA_SCREENSHOT_TRIGGER`) come out empty under RenderDoc.

**What the code shows.**
- `sub_82461108` draws the technique `PPMotionBlurDepthHorizonVel` (a velocity pass from
  depth): a full-screen quad given as normalized shorts (-32767..32767).
- `sub_82402678` uses `BloomTonemap_MotionBlur_Vignette`, probably the final combine that
  applies the blur.
- The camera definitions set a `MotionBlurAmount` per shot (`media/camera.zip`, for
  example `321Cams.xml`).

**Next steps.**
1. Capture again at speed. List the draws (RecompiledHaloReach `tools/renderdoc/draws.py`)
   and find the combine draw that samples the velocity target.
2. Save its inputs (`savetex.py`), and read the blend state, scissor, stencil and viewport
   of the blur draws. Look for what cuts the rectangle: a mask texture, a scissor or
   stencil rectangle, a resolve region, a sampler (point instead of linear filtering), a
   format, or the 4th vertex of a rectangle-list primitive.
3. Compare with Xenia. Its input must stay inside a nested display: never a global
   uinput pad, which Steam could map onto the desktop.
4. Fix it in a game hook, or as SDK patch 0040 or later, in both projects'
   `patches/rexglue-sdk/`.
