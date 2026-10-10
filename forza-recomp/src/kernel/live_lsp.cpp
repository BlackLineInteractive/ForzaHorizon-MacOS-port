// forza - title servers ("LSP") on a Forza Live server.
//
// (Adapted from RecompiledHaloReach, where Halo: Reach finds Bungie's title servers with
// XTitleServerCreateEnumerator: XAM enumerator app 0xFC, open message 0x58039, items
// X_TITLE_SERVER {inaServer, dwFlags, szServerInfo[200]}; Reach matches the description's
// comma-separated tokens against its service names, then opens HTTP/1.0 connections.)
//
// Forza Horizon enumerates the title servers every 30 s and picks one whose description
// matches the service it wants: the description holds wildcard patterns (`*`, `?`;
// sub_83153D48, called from sub_83155238). It then talks Turn 10's "Xls Client"
// protocol to it: HTTP/1.1 POST /Services/o.xtsw, Content-Type bin/xtsw, with
// X-TitleId, X-ClassName, X-Method and X-UserId headers. With Live sign-in the
// enumeration returns one title server, the Forza Live server, described as "*" (or
// FORZA_LSP_SERVICES), so every service resolves to it; net.cpp sends TCP connections to
// the server's HTTP port, where server/forza_live_lsp.py logs and answers. Without an
// answer the party lobby says "The Horizon server is currently unavailable" (no XP for
// online games) and play goes on. The marketplace asset enumeration (0x58042) is empty.
// Every other enumerator goes to the SDK.

#include "../platform/guest_memory.h"
#include "../platform/sdk_import.h"
#include "identity.h"
#include "live.h"

#include <rex/logging.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xenumerator.h>
#include <rex/system/xtypes.h>


#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <string>

using forza::GuestPtr;

namespace {

using GuestFunc = void (*)(PPCContext&, uint8_t*);

constexpr uint32_t kXLiveBaseApp = 0xFC;
constexpr uint32_t kTitleServerOpen = 0x58039;     // XTitleServerCreateEnumerator
constexpr uint32_t kMarketplaceAssetOpen = 0x58042;  // XMarketplaceCreateAssetEnumerator
constexpr uint32_t kTitleServerSize = 0xD0;        // X_TITLE_SERVER

void Store32(uint8_t* p, uint32_t v) {
  p[0] = uint8_t(v >> 24);
  p[1] = uint8_t(v >> 16);
  p[2] = uint8_t(v >> 8);
  p[3] = uint8_t(v);
}

// The title server's description: patterns the game matches its service names against.
std::string Services() {
  const char* v = std::getenv("FORZA_LSP_SERVICES");
  return v ? v : "*";
}

}  // namespace

// DWORD XamCreateEnumeratorHandle(DWORD user_index, DWORD app_id, DWORD open_message,
//     DWORD close_message, DWORD extra_size, DWORD item_count, DWORD flags, HANDLE* handle)
extern "C" REX_FUNC(__imp__XamCreateEnumeratorHandle) {
  const uint32_t user_index = ctx.r3.u32, app_id = ctx.r4.u32, open = ctx.r5.u32,
                 close = ctx.r6.u32, extra_size = ctx.r7.u32, item_count = ctx.r8.u32,
                 flags = ctx.r9.u32, out_handle = ctx.r10.u32;
  const bool title_servers = open == kTitleServerOpen;
  if (app_id != kXLiveBaseApp || (!title_servers && open != kMarketplaceAssetOpen) ||
      !forza::LiveSignin()) {
    static GuestFunc sdk =
        forza::SdkImport("__imp__XamCreateEnumeratorHandle");
    if (sdk) sdk(ctx, base);
    return;
  }
  using namespace rex;
  using namespace rex::system;
  const uint32_t item_size = title_servers ? kTitleServerSize : extra_size;
  auto e = object_ref<XStaticUntypedEnumerator>(
      new XStaticUntypedEnumerator(REX_KERNEL_STATE(), item_count ? item_count : 1, item_size));
  X_STATUS status = e->Initialize(user_index, app_id, open, close, flags, extra_size, nullptr);
  if (XFAILED(status)) {
    ctx.r3.u64 = status;
    return;
  }
  uint32_t ip;
  uint16_t port;
  if (title_servers && forza::LiveServerHttp(ip, port)) {
    uint8_t* item = e->AppendItem();
    std::memset(item, 0, kTitleServerSize);
    Store32(item, ip);
    const std::string services = Services();
    std::strncpy(reinterpret_cast<char*>(item + 8), services.c_str(), 199);
    REXLOG_INFO("FORZA_LIVE: title server {}.{}.{}.{} (HTTP port {}) for services \"{}\"",
                ip >> 24, (ip >> 16) & 0xFF, (ip >> 8) & 0xFF, ip & 0xFF, port, services);
  }
  if (out_handle) Store32(GuestPtr(base, out_handle), e->handle());
  ctx.r3.u64 = 0;
}
