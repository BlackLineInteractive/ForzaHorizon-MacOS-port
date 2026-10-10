// forza - the signed-in profile's XUID and gamertag.
//
// The runtime signs in one default profile, XUID 0xB13EBABEBABEBABE "User". Forza
// Horizon signs its save (ForzaProfile) with a key that depends on the profile: a save
// made under another XUID fails the check (sub_82C66308 with the tamper callback
// sub_824F31F8), and the game stops in its fatal-error handler (sub_82C09F00) with the
// title screen frozen. To keep playing a save from Xenia, set profile_xuid to the XUID
// of the Xenia profile it was made with (the folder name in Xenia's content/, e.g.
// E030000004B490FA) and copy the save folder into
// ~/.local/share/forza/B13EBABEBABEBABE/4D5309C9/ (the runtime keeps its folder name).
//
// Settings go in forza.toml next to the executable or on the command line
// (--profile_xuid=...); FORZA_XUID / FORZA_GAMERTAG override them.

#include "../platform/guest_memory.h"
#include "../platform/sdk_import.h"

#include <rex/cvar.h>
#include <rex/logging.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>

REXCVAR_DEFINE_STRING(profile_xuid, "", "Profile",
                      "XUID of the signed-in profile, 16 hex digits (e.g. that of the Xenia "
                      "profile a copied save was made with). Empty: the runtime's default "
                      "(FORZA_XUID overrides)");
REXCVAR_DEFINE_STRING(profile_gamertag, "", "Profile",
                      "Gamertag of the signed-in profile, up to 15 characters. Empty: the "
                      "runtime's default (FORZA_GAMERTAG overrides)");

using forza::GuestPtr;

namespace {

using GuestFunc = void (*)(PPCContext&, uint8_t*);

struct Identity {
  uint64_t xuid = 0;
  std::string gamertag;
};

const Identity& Get() {
  static Identity id;
  static std::once_flag once;
  std::call_once(once, [] {
    std::string xuid = REXCVAR_GET(profile_xuid);
    if (const char* v = std::getenv("FORZA_XUID"); v && *v) xuid = v;
    if (!xuid.empty()) id.xuid = std::strtoull(xuid.c_str(), nullptr, 16);
    id.gamertag = REXCVAR_GET(profile_gamertag);
    if (const char* v = std::getenv("FORZA_GAMERTAG"); v && *v) id.gamertag = v;
    if (id.gamertag.size() > 15) id.gamertag.resize(15);
    if (id.xuid || !id.gamertag.empty()) {
      REXLOG_INFO("Profile: XUID {:016X}, gamertag '{}'", id.xuid,
                  id.gamertag.empty() ? "(default)" : id.gamertag);
    }
  });
  return id;
}

GuestFunc Sdk(const char* name) { return forza::SdkImport(name); }

void StoreXuid(uint8_t* p, uint64_t xuid) {
  for (int i = 0; i < 8; ++i) p[i] = uint8_t(xuid >> (56 - 8 * i));
}

void StoreName(uint8_t* p, uint32_t size, const std::string& name) {
  if (!size) return;
  const uint32_t n = std::min<uint32_t>(uint32_t(name.size()), size - 1);
  std::memcpy(p, name.data(), n);
  p[n] = 0;
}

}  // namespace

uint64_t ForzaProfileXuid() { return Get().xuid; }

// DWORD XamUserGetSigninInfo(DWORD user_index, DWORD flags, X_USER_SIGNIN_INFO* info)
extern "C" REX_FUNC(__imp__XamUserGetSigninInfo) {
  const uint32_t user_index = ctx.r3.u32, info = ctx.r5.u32;
  static GuestFunc sdk = Sdk("__imp__XamUserGetSigninInfo");
  if (sdk) sdk(ctx, base);
  if (ctx.r3.u32 != 0 || user_index != 0 || !info) return;
  // X_USER_SIGNIN_INFO: xuid at 0, name[16] at 24.
  const Identity& id = Get();
  if (id.xuid) StoreXuid(GuestPtr(base, info), id.xuid);
  if (!id.gamertag.empty()) StoreName(GuestPtr(base, info + 24), 16, id.gamertag);
}

// DWORD XamUserGetXUID(DWORD user_index, DWORD type, XUID* xuid)
extern "C" REX_FUNC(__imp__XamUserGetXUID) {
  const uint32_t user_index = ctx.r3.u32, xuid = ctx.r5.u32;
  static GuestFunc sdk = Sdk("__imp__XamUserGetXUID");
  if (sdk) sdk(ctx, base);
  if (ctx.r3.u32 == 0 && user_index == 0 && xuid && Get().xuid) {
    StoreXuid(GuestPtr(base, xuid), Get().xuid);
  }
}

// DWORD XamUserGetName(DWORD user_index, char* buffer, DWORD buffer_size)
extern "C" REX_FUNC(__imp__XamUserGetName) {
  const uint32_t user_index = ctx.r3.u32, buffer = ctx.r4.u32, size = ctx.r5.u32;
  static GuestFunc sdk = Sdk("__imp__XamUserGetName");
  if (sdk) sdk(ctx, base);
  if (ctx.r3.u32 == 0 && user_index == 0 && buffer && !Get().gamertag.empty()) {
    StoreName(GuestPtr(base, buffer), size, Get().gamertag);
  }
}
