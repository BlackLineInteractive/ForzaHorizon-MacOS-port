// forza - Kinect (NUI) and XAM queries answered the way Xenia answers them.
//
// Forza Horizon supports Kinect (voice commands through SpeechFacade, head tracking)
// and asks for it all the time. Xenia, where the game runs, is the reference:
//
// - XamNuiGetDeviceStatus: Xenia zeroes the status and returns 0xC0050006 (no Kinect).
//   The SDK zeroes it but returns nothing, so r3 keeps the status pointer, a positive
//   value the game may read as success.
// - XamXStudioRequest(0x1003, &out) is polled every 30 ms (Xenia: 314,000 calls in a
//   session). Neither Xenia nor the SDK implements it, and both leave r3 as it was
//   (the request code, positive). Same here, without the SDK's warning per call.
// - XAM app 0xFE message 0x2B003: Xenia's XamApp answers success for this title
//   ("Games used in: 4D5309C9", buffer of three u64s, unknown). The SDK fails it.

#include "../platform/sdk_import.h"

#include <rex/logging.h>
#include <rex/ppc/context.h>
#include <rex/ppc/func.h>
#include <rex/system/kernel_state.h>
#include <rex/system/xthread.h>

#include <cstdint>
#include <mutex>

namespace {

using GuestFunc = void (*)(PPCContext&, uint8_t*);

constexpr uint32_t kXamApp = 0xFE;
constexpr uint32_t kMsgUnknown2B003 = 0x0002B003;
constexpr uint32_t kNuiNotConnected = 0xC0050006;
constexpr uint32_t kSuccess = 0;
constexpr uint32_t kIoPending = 997;  // ERROR_IO_PENDING

bool IsXenia2B003(uint32_t app, uint32_t message) {
  return app == kXamApp && message == kMsgUnknown2B003;
}

}  // namespace

// DWORD XamNuiGetDeviceStatus(X_NUI_DEVICE_STATUS* status)
extern "C" REX_FUNC(__imp__XamNuiGetDeviceStatus) {
  static GuestFunc sdk = forza::SdkImport("__imp__XamNuiGetDeviceStatus");
  if (sdk) sdk(ctx, base);  // zeroes the status (not connected)
  ctx.r3.u64 = kNuiNotConnected;
}

// DWORD XamXStudioRequest(DWORD request, void* out)
extern "C" REX_FUNC(__imp__XamXStudioRequest) {
  (void)base;
  static std::once_flag once;
  std::call_once(once, [&ctx] {
    REXLOG_INFO("XamXStudioRequest({:#x}) polled; left unanswered as in Xenia", ctx.r3.u32);
  });
}

// DWORD XMsgInProcessCall(DWORD app, DWORD message, void* arg1, void* arg2)
extern "C" REX_FUNC(__imp__XMsgInProcessCall) {
  static GuestFunc sdk = forza::SdkImport("__imp__XMsgInProcessCall");
  if (IsXenia2B003(ctx.r3.u32, ctx.r4.u32)) {
    ctx.r3.u64 = kSuccess;
    return;
  }
  if (sdk) sdk(ctx, base);
}

namespace {
// XMsgStartIORequest[Ex](app, message, XOVERLAPPED*, buffer, buffer size[, unknown]):
// answered at once, completing the XOVERLAPPED as the SDK does.
void StartIORequest(GuestFunc sdk, PPCContext& ctx, uint8_t* base) {
  if (!IsXenia2B003(ctx.r3.u32, ctx.r4.u32)) {
    if (sdk) sdk(ctx, base);
    return;
  }
  const uint32_t overlapped = ctx.r5.u32;
  if (overlapped) {
    REX_KERNEL_STATE()->CompleteOverlappedImmediate(overlapped, kSuccess);
    ctx.r3.u64 = kIoPending;
  } else {
    ctx.r3.u64 = kSuccess;
  }
  rex::system::XThread::SetLastError(0);
}
}  // namespace

extern "C" REX_FUNC(__imp__XMsgStartIORequest) {
  static GuestFunc sdk = forza::SdkImport("__imp__XMsgStartIORequest");
  StartIORequest(sdk, ctx, base);
}

extern "C" REX_FUNC(__imp__XMsgStartIORequestEx) {
  static GuestFunc sdk = forza::SdkImport("__imp__XMsgStartIORequestEx");
  StartIORequest(sdk, ctx, base);
}

// DWORD XMsgSystemProcessCall(DWORD app, DWORD message, void* buffer, DWORD size)
extern "C" REX_FUNC(__imp__XMsgSystemProcessCall) {
  static GuestFunc sdk = forza::SdkImport("__imp__XMsgSystemProcessCall");
  if (IsXenia2B003(ctx.r3.u32, ctx.r4.u32)) {
    ctx.r3.u64 = kSuccess;
    return;
  }
  if (sdk) sdk(ctx, base);
}
