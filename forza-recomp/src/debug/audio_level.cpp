// forza - audio level meter for unattended runs.
//
// FORZA_AUDIOLOG=1 logs the peak and RMS of the samples the game submits to the audio
// driver (XAudioSubmitRenderDriverFrame) every 5 seconds, so a scripted run can tell
// whether the game produces sound without anyone listening. A frame is 256 samples for
// each of 6 channels, big-endian floats, one channel after the other.

#include "../platform/guest_memory.h"
#include "../platform/sdk_import.h"

#include <rex/logging.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>

namespace {

using GuestFunc = void (*)(PPCContext&, uint8_t*);

constexpr int kChannels = 6;
constexpr int kSamplesPerChannel = 256;

bool Enabled() {
  static const bool on = [] {
    const char* v = std::getenv("FORZA_AUDIOLOG");
    return v && *v && *v != '0';
  }();
  return on;
}

struct Window {
  std::chrono::steady_clock::time_point start = std::chrono::steady_clock::now();
  std::chrono::steady_clock::time_point first = start;
  double sum_squares = 0;
  float peak = 0;
  uint64_t samples = 0;
  uint32_t frames = 0;
};

void Measure(uint8_t* base, uint32_t samples_addr) {
  static Window w;
  const uint8_t* p = forza::GuestPtr(base, samples_addr);
  for (int i = 0; i < kChannels * kSamplesPerChannel; ++i) {
    uint32_t raw;
    std::memcpy(&raw, p + 4 * i, 4);
    raw = __builtin_bswap32(raw);
    float v;
    std::memcpy(&v, &raw, 4);
    if (!std::isfinite(v)) continue;
    w.peak = std::max(w.peak, std::fabs(v));
    w.sum_squares += double(v) * v;
  }
  w.samples += kChannels * kSamplesPerChannel;
  ++w.frames;
  const auto now = std::chrono::steady_clock::now();
  if (now - w.start < std::chrono::seconds(5)) return;
  const double t = std::chrono::duration<double>(now - w.first).count();
  REXLOG_INFO("FORZA_AUDIOLOG: t={:.0f}s frames={} peak={:.4f} rms={:.5f}", t, w.frames, w.peak,
              std::sqrt(w.sum_squares / double(w.samples ? w.samples : 1)));
  const auto first = w.first;
  w = Window{};
  w.first = first;
}

}  // namespace

// DWORD XAudioSubmitRenderDriverFrame(void* driver, float* samples)
extern "C" REX_FUNC(__imp__XAudioSubmitRenderDriverFrame) {
  static GuestFunc sdk = forza::SdkImport("__imp__XAudioSubmitRenderDriverFrame");
  if (Enabled() && ctx.r4.u32) Measure(base, ctx.r4.u32);
  if (sdk) sdk(ctx, base);
}
