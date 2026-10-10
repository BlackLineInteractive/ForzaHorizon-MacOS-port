// forza - frame-time statistics (RECOMP_PERF=1); see frame_stats.cpp.

#pragma once

#include <string>

namespace forza::perf {

void OnGuestFrame();                     // every VdSwap
void SetScene(const std::string& name);  // closes the current window
void Flush();                            // logs the current window (at exit)

}  // namespace forza::perf
