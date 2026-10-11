// forza - the facade DLLs stay loaded once loaded.
//
// Forza Horizon loads XMediaFacade_default.xex and SpeechFacade_default.xex with
// XexLoadImage and unloads and reloads them around online races. Reloading a recompiled
// DLL fails in the SDK: XexUnloadImage looks the module's recompiled library up by the
// module's resolved path, which does not match the manifest's guest path, so the library
// stays registered, and the next XexLoadImage refuses it ("Recompiled module ... already
// loaded; refusing duplicate load") and returns no module; the game then faults reading
// through it (seen when two players left an online race). Here the last XexUnloadImage of
// a facade DLL keeps it loaded (no DLL_PROCESS_DETACH), so the reload finds it and gets
// the same module back, as if it had never been unloaded.

#include "../platform/guest_memory.h"
#include "../platform/sdk_import.h"

#include <rex/logging.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xmodule.h>

#include <cstdint>
#include <string>

using forza::GuestPtr;

namespace {
using GuestFunc = void (*)(PPCContext&, uint8_t*);

bool IsFacade(const std::string& name) {
  std::string lower;
  for (char c : name) lower += char(c >= 'A' && c <= 'Z' ? c + 32 : c);
  return lower.find("facade_default") != std::string::npos;
}
}  // namespace

// DWORD XexUnloadImage(HANDLE hmodule)
extern "C" REX_FUNC(__imp__XexUnloadImage) {
  static GuestFunc sdk = forza::SdkImport("__imp__XexUnloadImage");
  const uint32_t hmodule = ctx.r3.u32;
  if (hmodule) {
    auto module = rex::system::XModule::GetFromHModule(rex::system::kernel_state(),
                                                       GuestPtr(base, hmodule));
    if (module && module->module_type() == rex::system::XModule::ModuleType::kUserModule &&
        IsFacade(module->name())) {
      auto* ldr = reinterpret_cast<rex::system::X_LDR_DATA_TABLE_ENTRY*>(GuestPtr(base, hmodule));
      if (ldr->load_count <= 1) {
        REXLOG_INFO("FORZA: XexUnloadImage({}): kept loaded", module->name());
        ctx.r3.u64 = 0;
        return;
      }
    }
  }
  if (sdk) sdk(ctx, base);
}
