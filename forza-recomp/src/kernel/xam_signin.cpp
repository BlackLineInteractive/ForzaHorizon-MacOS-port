// forza - the signed-in profile: XUIDs, gamertag, Xbox LIVE sign-in and Gold.
//
// The runtime signs in one profile on user 0 (offline XUID 0xB13EBABEBABEBABE, "User"),
// denies every privilege and reports it signed in locally only. Here (adapted from
// RecompiledHaloReach's xam_signin.cpp):
//
// - Every player is an Xbox LIVE Gold member, always: XamUserCheckPrivilege grants
//   everything (multiplayer, communications, user content, purchases, presence, friends,
//   profile viewing) and the membership tier is Gold for any XUID. Forza refused
//   Multiplayer with "You must have an Xbox LIVE Gold Membership to use multiplayer".
// - With a Forza Live server (identity.h: LiveSignin) user 0 is signed in to LIVE: sign-in
//   state 2, the Live-enabled flag and an online XUID (0009...). Without one the profile
//   stays signed in locally (there is no LIVE to talk to).
// - Two XUIDs, as on the console: the offline one belongs to the profile and Forza ties
//   its save to it (the runtime's, or profile_xuid / FORZA_XUID for a copied Xenia save);
//   the online one (identity.cpp) answers requests for the online XUID. The game asks for
//   type 1 (offline) in its XAPI wrappers and type 2 (online) in its Live code.
// - The gamertag (gamertag / FORZA_GAMERTAG, or the Live identity's) replaces "User".

#include "../platform/guest_memory.h"
#include "../platform/sdk_import.h"
#include "identity.h"

#include <rex/logging.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xam/user_profile.h>

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <string>

using forza::GuestPtr;

namespace {

using GuestFunc = void (*)(PPCContext&, uint8_t*);

constexpr uint32_t kSuccess = 0;
constexpr uint32_t kErrorNoSuchUser = 0x00000525;  // X_ERROR_NO_SUCH_USER
constexpr uint32_t kENoSuchUser = 0x80070525;      // X_E_NO_SUCH_USER
constexpr uint32_t kEInvalidArg = 0x80070057;      // X_E_INVALIDARG
constexpr uint32_t kSigninStateSignedInToLive = 2;
constexpr uint32_t kMembershipGold = 6;
// XamUserGetSigninInfo flags: online XUID only / offline XUID only.
constexpr uint32_t kInfoOnlineXuidOnly = 1, kInfoOfflineXuidOnly = 2;
// XamUserGetXUID type mask bit for the offline XUID.
constexpr uint32_t kXuidOffline = 1;

GuestFunc Sdk(const char* name) { return forza::SdkImport(name); }

uint64_t RuntimeXuid() {
  const auto* kernel = rex::system::kernel_state();
  return kernel && kernel->user_profile() ? kernel->user_profile()->xuid() : 0;
}

uint64_t OfflineXuid() {
  const uint64_t x = forza::ProfileXuid();
  return x ? x : RuntimeXuid();
}

// The online XUID while signed in to LIVE, else 0.
uint64_t OnlineXuid() { return forza::LiveSignin() ? forza::IdentityXuid() : 0; }

bool IsOurs(uint64_t xuid) {
  return xuid && (xuid == OfflineXuid() || xuid == RuntimeXuid() || xuid == OnlineXuid());
}

const char* GamertagOverride() {
  const std::string& name = forza::IdentityGamertag();
  return name.empty() ? nullptr : name.c_str();
}

void StoreXuid(uint8_t* p, uint64_t xuid) {
  for (int i = 0; i < 8; ++i) p[i] = uint8_t(xuid >> (56 - 8 * i));
}

void Store32(uint8_t* p, uint32_t v) {
  p[0] = uint8_t(v >> 24);
  p[1] = uint8_t(v >> 16);
  p[2] = uint8_t(v >> 8);
  p[3] = uint8_t(v);
}

void StoreName(uint8_t* p, uint32_t size, const char* name) {
  if (!size) return;
  uint32_t n = std::min<uint32_t>(uint32_t(std::strlen(name)), size - 1);
  std::memcpy(p, name, n);
  p[n] = 0;
}

bool IsUser0(uint32_t user_index) { return user_index == 0 || (user_index & 0xFF) == 0xFF; }

}  // namespace

// DWORD XamUserGetSigninState(DWORD user_index)
extern "C" REX_FUNC(__imp__XamUserGetSigninState) {
  const uint32_t user_index = ctx.r3.u32;
  static GuestFunc sdk = Sdk("__imp__XamUserGetSigninState");
  if (sdk) sdk(ctx, base);
  if (user_index == 0 && ctx.r3.u32 != 0 && forza::LiveSignin()) {
    ctx.r3.u64 = kSigninStateSignedInToLive;
  }
}

// DWORD XamUserGetSigninInfo(DWORD user_index, DWORD flags, X_USER_SIGNIN_INFO* info)
// X_USER_SIGNIN_INFO: u64 xuid; u32 flags (+8); u32 state (+12); u32, u32; char name[16] (+24).
extern "C" REX_FUNC(__imp__XamUserGetSigninInfo) {
  const uint32_t user_index = ctx.r3.u32, flags = ctx.r4.u32, info = ctx.r5.u32;
  static GuestFunc sdk = Sdk("__imp__XamUserGetSigninInfo");
  if (sdk) sdk(ctx, base);
  if (ctx.r3.u32 != kSuccess || user_index != 0 || !info) return;
  uint8_t* p = GuestPtr(base, info);
  const uint64_t online = OnlineXuid();
  uint64_t xuid = OfflineXuid();
  if (online && !(flags & kInfoOfflineXuidOnly)) xuid = online;
  if (!online && (flags & kInfoOnlineXuidOnly)) xuid = 0;
  StoreXuid(p, xuid);
  if (const char* tag = GamertagOverride()) StoreName(p + 24, 16, tag);
  if (forza::LiveSignin()) {
    p[11] |= 1;  // XUSER_INFO_FLAG_LIVE_ENABLED
    Store32(p + 12, kSigninStateSignedInToLive);
  }
}

// DWORD XamUserGetXUID(DWORD user_index, DWORD type_mask, XUID* xuid)
extern "C" REX_FUNC(__imp__XamUserGetXUID) {
  const uint32_t user_index = ctx.r3.u32, type_mask = ctx.r4.u32, xuid = ctx.r5.u32;
  static GuestFunc sdk = Sdk("__imp__XamUserGetXUID");
  if (sdk) sdk(ctx, base);
  if (ctx.r3.u32 != kSuccess || user_index != 0 || !xuid) return;
  const uint64_t online = OnlineXuid();
  // An online XUID when one was asked for and exists; else the profile's offline one.
  StoreXuid(GuestPtr(base, xuid),
            (online && (type_mask & ~kXuidOffline)) ? online : OfflineXuid());
}

// DWORD XamUserGetName(DWORD user_index, char* buffer, DWORD buffer_size)
extern "C" REX_FUNC(__imp__XamUserGetName) {
  const uint32_t user_index = ctx.r3.u32, buffer = ctx.r4.u32, size = ctx.r5.u32;
  static GuestFunc sdk = Sdk("__imp__XamUserGetName");
  if (sdk) sdk(ctx, base);
  if (ctx.r3.u32 == kSuccess && user_index == 0 && buffer) {
    if (const char* tag = GamertagOverride()) StoreName(GuestPtr(base, buffer), size, tag);
  }
}

// DWORD XamUserCheckPrivilege(DWORD user_index, DWORD privilege, BOOL* result)
// Gold, always: every privilege is granted.
extern "C" REX_FUNC(__imp__XamUserCheckPrivilege) {
  const uint32_t user_index = ctx.r3.u32, result = ctx.r5.u32;
  if (!IsUser0(user_index)) {
    if (result) std::memset(GuestPtr(base, result), 0, 4);
    ctx.r3.u64 = user_index < 4 ? kErrorNoSuchUser : 0x57;  // ERROR_INVALID_PARAMETER
    return;
  }
  if (result) Store32(GuestPtr(base, result), 1);
  ctx.r3.u64 = kSuccess;
}

// DWORD XamUserGetMembershipTier(DWORD user_index)
extern "C" REX_FUNC(__imp__XamUserGetMembershipTier) {
  (void)base;
  ctx.r3.u64 = IsUser0(ctx.r3.u32) ? kMembershipGold : kErrorNoSuchUser;
}

// DWORD XamUserGetMembershipTierFromXUID(XUID xuid): the SDK leaves it a stub that returns
// the XUID's low word. Everyone is Gold.
extern "C" REX_FUNC(__imp__XamUserGetMembershipTierFromXUID) {
  (void)base;
  ctx.r3.u64 = kMembershipGold;
}

// DWORD XamUserGetIndexFromXUID(XUID xuid, DWORD flags, DWORD* index): the SDK stub
// writes nothing. Our XUIDs (offline, runtime, online) are user 0, as Xenia maps the
// signed-in profile's XUID to its index.
extern "C" REX_FUNC(__imp__XamUserGetIndexFromXUID) {
  const uint64_t xuid = ctx.r3.u64;
  const uint32_t index = ctx.r5.u32;
  if (!index) {
    ctx.r3.u64 = kEInvalidArg;
    return;
  }
  if (IsOurs(xuid)) {
    std::memset(GuestPtr(base, index), 0, 4);
    ctx.r3.u64 = kSuccess;
    return;
  }
  ctx.r3.u64 = kENoSuchUser;
}
