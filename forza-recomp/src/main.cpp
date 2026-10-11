// forza - ReXGlue Recompiled Project

#include "generated/default/forza_init.h"

#include "forza_app.h"

#include <rex/cvar.h>
#include <rex/logging.h>

#include <string_view>

REX_DEFINE_APP(forza, ForzaApp::Create)

REXCVAR_DEFINE_STRING(gpu_backend, "vulkan", "GPU",
                      "GPU backend on Windows: vulkan (with this project's fixes) or d3d12")
    .lifecycle(rex::cvar::Lifecycle::kInitOnly);

std::string ForzaGpuBackend() { return REXCVAR_GET(gpu_backend); }

// The game's vblank callback wakes its main loop every second guest vblank, and the main
// loop takes its frame time from the kernel's millisecond tick count (snapped to 1/59.94 s
// when a frame took 16-17 ms), so the frame rate follows the guest vblank rate and the
// simulation stays at real-time speed (docs/framerate.md).
REXCVAR_DEFINE_INT32(frame_rate, 30, "Display",
                     "Frame rate: 30 (the console's) or 60. 60 runs the guest vblank at 120 Hz; "
                     "the game times its simulation in real time (docs/framerate.md)")
    .validator([](std::string_view v) { return v == "30" || v == "60"; })
    .lifecycle(rex::cvar::Lifecycle::kRequiresRestart);

namespace {

// Gives an SDK cvar this game's default. A value from forza.toml, the environment
// (REX_<NAME>) or the command line stays; the settings UI and SaveConfig treat the new
// value as the default. (From RecompiledHaloReach.)
void SetSdkCvarDefault(std::string_view name, std::string_view value) {
  for (rex::cvar::FlagEntry& entry : rex::cvar::GetRegistry()) {
    if (entry.name != name) continue;
    if (entry.source == rex::cvar::Source::kDefault) entry.setter(value);
    entry.default_value = value;
    return;
  }
  REXLOG_WARN("SDK setting {} not found", name);
}

}  // namespace

void ApplyForzaCvarDefaults() {
  // Present with FIFO (vsync) only. The SDK prefers IMMEDIATE (tearing), and its UI thread
  // repaints nonstop on Linux: without a vsync wait that is thousands of presents a second,
  // GPU time taken from the emulated GPU (measured in RecompiledHaloReach, and here in
  // docs/perf.md). forza.toml or the command line can allow the other modes again.
  SetSdkCvarDefault("vulkan_allow_present_mode_immediate", "false");
  SetSdkCvarDefault("vulkan_allow_present_mode_mailbox", "false");
  SetSdkCvarDefault("vulkan_allow_present_mode_fifo_relaxed", "false");
  // frame_rate = 60: twice the console's vblank rate, so the main loop's wake-up every
  // second vblank comes at 60 Hz. A video_mode_refresh_rate set in forza.toml or on the
  // command line wins.
  if (REXCVAR_GET(frame_rate) == 60) SetSdkCvarDefault("video_mode_refresh_rate", "120");
}
