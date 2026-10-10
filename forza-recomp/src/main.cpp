// forza - ReXGlue Recompiled Project

#include "generated/default/forza_init.h"

#include "forza_app.h"

#include <rex/cvar.h>
#include <rex/logging.h>

#include <string_view>

REX_DEFINE_APP(forza, ForzaApp::Create)

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
}
