// forza - frame-time statistics (RECOMP_PERF=1), with the same definitions as
// RecompiledHaloReach so the two projects compare.
//
// Every 10 s window, when the scene changes and at exit, one line per frame source:
//
//   PERF: scene=<name> src=<guest|present> t=<s> fps= p50= p95= p99= max= low1= stutters=
//         hitches= ontarget= pipelines=
//
// - src=guest: the game's frames (VdSwap calls); src=present: frames the host presented
//   (counted by the patched GPU plugin, patches/rexglue-sdk/0024, when it has the hook;
//   the SDK skips presenting frames that drew with a placeholder shader).
// - p50/p95/p99/max: frame time in ms; low1 = 1000 / mean of the slowest 1% of frame
//   times; stutters = frames longer than 2x the window's p50; hitches = frames longer
//   than 100 ms; ontarget = % of frames within +-20% of 33.3 ms (the game's 30 fps);
//   pipelines = graphics pipelines the GPU plugin created in the window (its "Creating
//   graphics pipeline state" log lines, placeholders included).
//
// RECOMP_PERF_SCENE=<name> labels the first scene ("boot" otherwise); "SCENE:<name>" on
// the input FIFO (FORZA_AUTOPRESS_FIFO) starts a new one. RECOMP_PERF_CSV=<path> also
// writes every frame: src,scene,t_s,frame_ms.

#include "frame_stats.h"

#include <rex/logging.h>
#include <rex/logging/api.h>

#include <spdlog/sinks/base_sink.h>

#ifndef _WIN32
#include <dlfcn.h>
#endif

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>

namespace forza::perf {

namespace {

using Clock = std::chrono::steady_clock;
constexpr double kWindowSeconds = 10.0;
constexpr double kTargetMs = 1000.0 / 30.0;

bool Enabled() {
  static const bool on = [] {
    const char* v = std::getenv("RECOMP_PERF");
    return v && *v && *v != '0';
  }();
  return on;
}

std::atomic<uint64_t> pipelines_created{0};

// Counts pipeline creations from the GPU plugin's log lines.
class PipelineCountSink : public spdlog::sinks::base_sink<std::mutex> {
 protected:
  void sink_it_(const spdlog::details::log_msg& msg) override {
    static constexpr char kNeedle[] = "Creating graphics pipeline state";
    const auto& text = msg.payload;
    if (text.size() >= sizeof(kNeedle) - 1 &&
        std::memcmp(text.data(), kNeedle, sizeof(kNeedle) - 1) == 0) {
      ++pipelines_created;
    }
  }
  void flush_() override {}
};

struct Source {
  const char* name;
  bool seen = false;
  Clock::time_point last{};
  std::vector<double> frame_ms;  // frame times in the current window
};

struct State {
  std::mutex mutex;
  std::string scene;
  Clock::time_point start = Clock::now();
  Clock::time_point window_start = start;
  uint64_t window_pipelines = 0;
  Source guest{"guest"}, present{"present"};
  FILE* csv = nullptr;
};

State& Get() {
  static State* state = [] {
    auto* s = new State;
    const char* scene = std::getenv("RECOMP_PERF_SCENE");
    s->scene = scene && *scene ? scene : "boot";
    if (const char* path = std::getenv("RECOMP_PERF_CSV"); path && *path) {
      s->csv = std::fopen(path, "w");
      if (s->csv) std::fprintf(s->csv, "src,scene,t_s,frame_ms\n");
    }
    rex::AddSink(std::make_shared<PipelineCountSink>());
    return s;
  }();
  return *state;
}

double Percentile(const std::vector<double>& sorted, double p) {
  if (sorted.empty()) return 0;
  const size_t i = std::min(sorted.size() - 1, size_t(p * double(sorted.size() - 1) + 0.5));
  return sorted[i];
}

void LogSource(State& s, Source& src, double window_s, uint64_t pipelines) {
  if (!src.seen) return;
  std::vector<double> v = src.frame_ms;
  std::sort(v.begin(), v.end());
  const size_t n = v.size();
  const double p50 = Percentile(v, 0.50);
  size_t stutters = 0, hitches = 0, on_target = 0;
  for (double ms : v) {
    if (ms > 2 * p50) ++stutters;
    if (ms > 100) ++hitches;
    if (ms >= kTargetMs * 0.8 && ms <= kTargetMs * 1.2) ++on_target;
  }
  const size_t slow = std::max<size_t>(1, n / 100);
  double slow_sum = 0;
  for (size_t i = 0; i < slow && i < n; ++i) slow_sum += v[n - 1 - i];
  const double low1 = n ? 1000.0 / (slow_sum / double(std::min(slow, n))) : 0;
  const double t = std::chrono::duration<double>(Clock::now() - s.start).count();
  REXLOG_INFO(
      "PERF: scene={} src={} t={:.0f} fps={:.1f} p50={:.1f} p95={:.1f} p99={:.1f} max={:.1f} "
      "low1={:.1f} stutters={} hitches={} ontarget={:.0f} pipelines={}",
      s.scene, src.name, t, window_s > 0 ? double(n) / window_s : 0.0, p50, Percentile(v, 0.95),
      Percentile(v, 0.99), n ? v.back() : 0.0, low1, stutters, hitches,
      n ? 100.0 * double(on_target) / double(n) : 0.0, pipelines);
}

// Logs and resets the current window. Caller holds the mutex.
void CloseWindow(State& s, Clock::time_point now) {
  const double window_s = std::chrono::duration<double>(now - s.window_start).count();
  const uint64_t total_pipelines = pipelines_created.load();
  const uint64_t pipelines = total_pipelines - s.window_pipelines;
  if (window_s > 0.5) {
    LogSource(s, s.guest, window_s, pipelines);
    LogSource(s, s.present, window_s, pipelines);
  }
  s.guest.frame_ms.clear();
  s.present.frame_ms.clear();
  s.window_start = now;
  s.window_pipelines = total_pipelines;
  if (s.csv) std::fflush(s.csv);
}

void OnFrame(Source State::*which) {
  if (!Enabled()) return;
  State& s = Get();
  const auto now = Clock::now();
  std::lock_guard<std::mutex> lock(s.mutex);
  Source& src = s.*which;
  if (src.seen) {
    const double ms = std::chrono::duration<double, std::milli>(now - src.last).count();
    src.frame_ms.push_back(ms);
    if (s.csv) {
      std::fprintf(s.csv, "%s,%s,%.3f,%.3f\n", src.name, s.scene.c_str(),
                   std::chrono::duration<double>(now - s.start).count(), ms);
    }
  }
  src.seen = true;
  src.last = now;
  if (std::chrono::duration<double>(now - s.window_start).count() >= kWindowSeconds) {
    CloseWindow(s, now);
  }
}

void PresentCallback() { OnFrame(&State::present); }

}  // namespace

void OnGuestFrame() {
  static std::once_flag hook_once;
  if (!Enabled()) return;
  std::call_once(hook_once, [] {
#ifndef _WIN32
    // The patched plugin (0024) calls this back on every host present.
    using SetHook = void (*)(void (*)());
    void* plugin = dlopen("librexgpu-xenos.so", RTLD_NOW | RTLD_NOLOAD);
    auto set = plugin ? reinterpret_cast<SetHook>(dlsym(plugin, "rexgpu_set_present_hook"))
                      : nullptr;
    if (set) {
      set(PresentCallback);
    } else {
      REXLOG_INFO("PERF: the GPU plugin has no present hook; only guest frames are measured");
    }
#endif
  });
  OnFrame(&State::guest);
}

void SetScene(const std::string& scene) {
  if (!Enabled()) return;
  State& s = Get();
  std::lock_guard<std::mutex> lock(s.mutex);
  CloseWindow(s, Clock::now());
  s.scene = scene;
  REXLOG_INFO("PERF: scene={}", scene);
}

void Flush() {
  if (!Enabled()) return;
  State& s = Get();
  std::lock_guard<std::mutex> lock(s.mutex);
  CloseWindow(s, Clock::now());
}

}  // namespace forza::perf
