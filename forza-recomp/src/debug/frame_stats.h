// forza - frame-time statistics (frame rate and stutter), off by default.
//
// RECOMP_PERF=1 times two streams: guest frames (VdSwap) and
// host presents (vkQueuePresentKHR, hooked in src/platform/vulkan_hooks.cpp), and logs one
// line per stream every 10 s and a summary at exit:
//
//   PERF: scene=<name> src=<guest|present> t=<s> fps=<avg> p50=<ms> p95=<ms> p99=<ms>
//         max=<ms> low1=<fps> stutters=<n> hitches=<n> ontarget=<%> pipelines=<n>
//
// The summary line ends with "final=1 from=<s>" (it covers the frames since <s>).
// RECOMP_PERF_SCENE=<name> labels the lines, RECOMP_PERF_CSV=<path> writes every frame time
// (scene,src,t,ms), and RECOMP_PERF_RESET=<path> restarts the summary when that file appears
// (it is deleted again), so a script can measure from the moment a scene is reached.
// "SCENE:<name>" on the input FIFO (src/kernel/input_autopress.cpp) does both at once: it
// logs the summary of the scene so far, renames the scene and restarts the summary.
// Definitions and results: docs/perf.md. Ported from RecompiledHaloReach, so the numbers
// of the two projects compare.

#pragma once

#include <cstdint>
#include <string>

namespace forza::perf {

bool Enabled();

// A guest frame was handed to VdSwap.
void OnGuestFrame();

// The host presenter called vkQueuePresentKHR.
void OnHostPresent();

// The GPU plugin created `count` graphics or compute pipelines (guest shaders and
// render-target helpers; src/platform/vulkan_hooks.cpp).
void OnPipelinesCreated(uint32_t count);

// Ends the current scene (its summary lines) and starts a new one named `name`.
void SetScene(const std::string& name);

// Logs the summary lines and closes the CSV (once; the game exits on a window close).
void Shutdown();

}  // namespace forza::perf
