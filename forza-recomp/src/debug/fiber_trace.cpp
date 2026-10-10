// forza - FORZA_FIBERTRACE=1: report fibers that resume on another host thread.
//
// The SDK's native fibers keep one PPCContext per thread. A fiber whose generated
// frames were entered on thread A keep using A's context after another thread B
// switches to it, while A goes on using the same context: both threads then share
// registers. This wraps rexcrt_SwitchToFiber and logs each migration (the first few in
// detail, then a count every 1000), to tell whether the game's job system moves fibers
// between threads.

#include "../platform/guest_memory.h"

#include <rex/logging.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>

#include <dlfcn.h>
#include <pthread.h>

#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <mutex>
#include <unordered_map>

using forza::GuestPtr;

namespace {

using GuestFunc = void (*)(PPCContext&, uint8_t*);

bool Enabled() {
  static const bool on = [] {
    const char* v = std::getenv("FORZA_FIBERTRACE");
    return v && *v && *v != '0';
  }();
  return on;
}

uint32_t Load32(const uint8_t* p) { return uint32_t(p[0]) << 24 | p[1] << 16 | p[2] << 8 | p[3]; }

// The current fiber: KPCR (r13) +0x100 is the KTHREAD, KTHREAD +0x164 the fiber.
uint32_t CurrentFiber(PPCContext& ctx, uint8_t* base) {
  const uint32_t kthread = Load32(GuestPtr(base, ctx.r13.u32 + 0x100));
  return kthread ? Load32(GuestPtr(base, kthread + 0x164)) : 0;
}

std::mutex table_mutex;
std::unordered_map<uint32_t, uint64_t> last_thread;  // fiber -> host thread it last ran on
std::atomic<uint64_t> switches{0}, migrations{0};

}  // namespace

extern "C" REX_FUNC(rexcrt_SwitchToFiber) {
  static GuestFunc sdk = reinterpret_cast<GuestFunc>(dlsym(RTLD_NEXT, "rexcrt_SwitchToFiber"));
  if (Enabled()) {
    const uint64_t self = uint64_t(pthread_self());
    const uint32_t target = ctx.r3.u32;
    const uint32_t current = CurrentFiber(ctx, base);
    std::lock_guard<std::mutex> lock(table_mutex);
    if (current) last_thread[current] = self;
    const uint64_t total = ++switches;
    if (total == 1 || total % 100000 == 0) {
      REXLOG_INFO("FORZA_FIBERTRACE: {} switches, {} migrations", total, migrations.load());
    }
    auto it = last_thread.find(target);
    if (it != last_thread.end() && it->second != self) {
      const uint64_t n = ++migrations;
      if (n <= 10 || n % 1000 == 0) {
        REXLOG_WARN("FORZA_FIBERTRACE: fiber {:08X} resumed on another thread (migration {} of "
                    "{} switches)",
                    target, n, switches.load());
      }
    }
  }
  if (sdk) sdk(ctx, base);
  // Back on this fiber (possibly on another thread): note where it runs now.
  if (Enabled()) {
    const uint32_t current = CurrentFiber(ctx, base);
    std::lock_guard<std::mutex> lock(table_mutex);
    if (current) last_thread[current] = uint64_t(pthread_self());
  }
}
