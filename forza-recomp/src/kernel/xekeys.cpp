// forza - console identity and XUID lookups as Xenia answers them.
//
// Forza Horizon imports XeKeysGetConsoleID, XeKeysConsolePrivateKeySign and
// XeKeysConsoleSignatureVerification (save signing) and XamUserGetIndexFromXUID. In
// the SDK the first and last are stubs that write nothing (the game then reads whatever
// its stack held), PrivateKeySign returns FALSE without a certificate and the
// verification returns FALSE. Xenia, where the user's saves come from, returns a fixed
// console ID and certificate, leaves the verification unimplemented (r3 keeps the hash
// pointer: nonzero, "valid") and maps the signed-in profile's XUID to its user index.
// Matching it keeps saves made in either one loadable in the other.

#include "../platform/guest_memory.h"

#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xam/user_profile.h>

#include <cstdint>
#include <cstring>

using forza::GuestPtr;

uint64_t ForzaProfileXuid();  // profile_identity.cpp: 0 when not overridden

namespace {

// Xenia's XE_CONSOLE_ID: RefurbBits 3, ManufactureMonth 9, ManufactureYear 1,
// MacIndex3..5 0x40 0x66 0x7E, Crc 0, as the bitfields lay out in memory.
constexpr uint8_t kConsoleId[5] = {0x93, 0x01, 0x64, 0xE6, 0x07};
constexpr char kConsoleIdHex[12] = {'2', '4', '5', '1', '4', '9', '1', '0', '0', '0', '0', '0'};
constexpr uint32_t kCertificateSize = 0x1A8;  // XE_CONSOLE_CERTIFICATE
constexpr uint32_t kErrorNoSuchUser = 0x80070525;  // X_E_NO_SUCH_USER
constexpr uint32_t kErrorInvalidArg = 0x80070057;  // X_E_INVALIDARG

}  // namespace

// NTSTATUS XeKeysGetConsoleID(XE_CONSOLE_ID* raw_bytes, char* hex_string)
extern "C" REX_FUNC(__imp__XeKeysGetConsoleID) {
  if (ctx.r3.u32) std::memcpy(GuestPtr(base, ctx.r3.u32), kConsoleId, sizeof(kConsoleId));
  if (ctx.r4.u32) std::memcpy(GuestPtr(base, ctx.r4.u32), kConsoleIdHex, sizeof(kConsoleIdHex));
  ctx.r3.u64 = 0;  // STATUS_SUCCESS
}

// BOOL XeKeysConsolePrivateKeySign(const BYTE hash[20], XE_CONSOLE_SIGNATURE* output)
extern "C" REX_FUNC(__imp__XeKeysConsolePrivateKeySign) {
  const uint32_t hash = ctx.r3.u32, output = ctx.r4.u32;
  if (!hash || !output) {
    ctx.r3.u64 = 0;
    return;
  }
  uint8_t* cert = GuestPtr(base, output);
  std::memset(cert, 0, kCertificateSize);
  std::memcpy(cert + 0x02, kConsoleId, sizeof(kConsoleId));
  cert[0x1B] = 2;  // console_type: retail (big-endian u32 at 0x18)
  const uint8_t manufacture_date[8] = {2, 0, 0, 5, 1, 1, 2, 2};
  std::memcpy(cert + 0x1C, manufacture_date, sizeof(manufacture_date));
  ctx.r3.u64 = 1;
}

// BOOL XeKeysConsoleSignatureVerification(const BYTE hash[20], const XE_CONSOLE_SIGNATURE*
//                                          signature, NTSTATUS* status)
// Unimplemented in Xenia: the call returns with r3 unchanged, the (nonzero) hash pointer.
extern "C" REX_FUNC(__imp__XeKeysConsoleSignatureVerification) {
  (void)base;
  ctx.r3.u64 = ctx.r3.u32 ? 1 : 0;
}

// DWORD XamUserGetIndexFromXUID(XUID xuid, DWORD flags, DWORD* index)
extern "C" REX_FUNC(__imp__XamUserGetIndexFromXUID) {
  const uint64_t xuid = ctx.r3.u64;
  const uint32_t index = ctx.r5.u32;
  if (!index) {
    ctx.r3.u64 = kErrorInvalidArg;
    return;
  }
  // The only signed-in profile is user 0: the runtime's own XUID, or the override.
  const auto* kernel = rex::system::kernel_state();
  const uint64_t own = kernel && kernel->user_profile() ? kernel->user_profile()->xuid() : 0;
  if (xuid == own || (ForzaProfileXuid() && xuid == ForzaProfileXuid())) {
    uint8_t* out = GuestPtr(base, index);
    std::memset(out, 0, 4);
    ctx.r3.u64 = 0;
    return;
  }
  ctx.r3.u64 = kErrorNoSuchUser;
}
