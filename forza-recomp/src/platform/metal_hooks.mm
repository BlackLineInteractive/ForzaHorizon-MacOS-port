// forza - hooks in Apple Metal for macOS; see metal_hooks.h.
//
// Hooks host presents and pipeline creation for macOS Metal backend, reporting to frame_stats.
#import "metal_hooks.h"
#import "../debug/frame_stats.h"

#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#import <objc/runtime.h>

#include <rex/logging.h>
#include <rex/system/interfaces/graphics.h>

#include <mutex>
#include <string>

namespace forza {

static bool g_metal_hooks_installed = false;

// Original function pointers for swizzled methods
static void (*orig_present)(id, SEL) = nullptr;
static void (*orig_presentDrawable)(id, SEL, id<MTLDrawable>) = nullptr;

static void Swizzled_present(id self, SEL _cmd) {
  perf::OnHostPresent();
  if (orig_present) {
    orig_present(self, _cmd);
  }
}

static void Swizzled_presentDrawable(id self, SEL _cmd, id<MTLDrawable> drawable) {
  perf::OnHostPresent();
  if (orig_presentDrawable) {
    orig_presentDrawable(self, _cmd, drawable);
  }
}

static void SwizzleMethod(Class cls, SEL origSel, IMP newImp, IMP* origImpOut) {
  if (!cls) return;
  Method m = class_getInstanceMethod(cls, origSel);
  if (!m) return;
  *origImpOut = method_getImplementation(m);
  method_setImplementation(m, newImp);
}

bool InstallMetalHooks(rex::system::IGraphicsSystem* graphics) {
  static std::mutex mutex;
  std::lock_guard<std::mutex> lock(mutex);
  if (g_metal_hooks_installed) return true;

  id<MTLDevice> defaultDevice = MTLCreateSystemDefaultDevice();
  if (!defaultDevice) {
    REXLOG_WARN("Metal: No default MTLDevice found on this macOS system");
    return false;
  }

  REXLOG_INFO("Metal backend initialized: GPU '{}' (low-power: {}, headless: {})",
              [[defaultDevice name] UTF8String],
              [defaultDevice isLowPower] ? "yes" : "no",
              [defaultDevice isHeadless] ? "yes" : "no");

  if (perf::Enabled()) {
    // 1. Swizzle [CAMetalDrawable present]
    Class drawableClass = NSClassFromString(@"CAMetalDrawable");
    if (drawableClass) {
      SwizzleMethod(drawableClass, @selector(present), (IMP)Swizzled_present, (IMP*)&orig_present);
    }

    // 2. Swizzle [id<MTLCommandBuffer> presentDrawable:]
    id<MTLCommandQueue> queue = [defaultDevice newCommandQueue];
    if (queue) {
      id<MTLCommandBuffer> cb = [queue commandBuffer];
      if (cb) {
        Class cbClass = [cb class];
        SwizzleMethod(cbClass, @selector(presentDrawable:), (IMP)Swizzled_presentDrawable,
                      (IMP*)&orig_presentDrawable);
      }
    }
  }

  g_metal_hooks_installed = true;
  return true;
}

}  // namespace forza
