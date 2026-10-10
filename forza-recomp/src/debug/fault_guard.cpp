// forza - stop on a fault nothing handles instead of re-running it forever.
//
// The runtime's signal handler offers a fault to its handlers (MMIO ranges, GPU
// write watches); when none takes it, it returns and the faulting instruction runs
// again. A null read in recompiled code then faults forever, and the runtime logs
// "Unhandled guest access violation" each time: 4 MB of log a second (a 260 MB log in
// one minute when a copied save was loaded). A trap (__builtin_trap, e.g. a switch case
// out of range) loops the same way.
//
// This handler is installed after the runtime's, so it only sees faults nobody took.
// It logs the fault once with the host call stack as module+offset (resolve with
// `addr2line -f -e forza-recomp/out/build/linux/forza 0xOFFSET`; frames in sub_XXXXXXXX
// are the recompiled guest functions) and then aborts (core dump), unless FORZA_FAULT=wait,
// which parks the thread so gdb can attach (gdb -p PID, then `thread apply all bt`).

#include <rex/exception_handler.h>
#include <rex/logging.h>

#ifndef _WIN32
#include <dlfcn.h>
#include <execinfo.h>
#endif

#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <thread>

namespace forza {

namespace {

constexpr uint64_t kGuestVirtualBase = 0x100000000ull;  // Linux: guest X is host base + X

bool Wait() {
  const char* v = std::getenv("FORZA_FAULT");
  return v && std::strcmp(v, "wait") == 0;
}

void LogStack() {
#ifndef _WIN32
  void* frames[48];
  const int n = backtrace(frames, 48);
  for (int i = 0; i < n; ++i) {
    Dl_info info{};
    if (dladdr(frames[i], &info) && info.dli_fname) {
      const char* name = std::strrchr(info.dli_fname, '/');
      REXLOG_ERROR("  #{} {}+0x{:X}{}{}", i, name ? name + 1 : info.dli_fname,
                   reinterpret_cast<uintptr_t>(frames[i]) -
                       reinterpret_cast<uintptr_t>(info.dli_fbase),
                   info.dli_sname ? " " : "", info.dli_sname ? info.dli_sname : "");
    } else {
      REXLOG_ERROR("  #{} {}", i, frames[i]);
    }
  }
#endif
}

bool OnUnhandledFault(rex::arch::Exception* ex, void* /*data*/) {
  using Code = rex::arch::Exception::Code;
  if (ex->code() == Code::kAccessViolation) {
    const uint64_t addr = ex->fault_address();
    const bool guest = addr >= kGuestVirtualBase && addr < kGuestVirtualBase + 0x100000000ull;
    REXLOG_CRITICAL("Unhandled {} fault at host 0x{:X}{} (pc 0x{:X})",
                    ex->access_violation_operation() ==
                            rex::arch::Exception::AccessViolationOperation::kWrite
                        ? "write"
                        : "read",
                    addr, guest ? fmt::format(" = guest 0x{:08X}", uint32_t(addr)) : "",
                    ex->pc());
  } else {
    REXLOG_CRITICAL("Unhandled illegal instruction (trap) at pc 0x{:X}", ex->pc());
  }
  LogStack();
  if (Wait()) {
    REXLOG_CRITICAL("FORZA_FAULT=wait: thread parked for a debugger");
    for (;;) std::this_thread::sleep_for(std::chrono::hours(1));
  }
  std::abort();
}

}  // namespace

void InstallFaultGuard() { rex::arch::ExceptionHandler::Install(OnUnhandledFault, nullptr); }

}  // namespace forza
