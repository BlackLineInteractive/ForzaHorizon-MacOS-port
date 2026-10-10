// forza - the GJK distance query's first termination test needs Xenon's dot-product
// overflow result (QNaN), not the IEEE infinity the recompiled vmsum3fp128 gives.
//
// The collision GJK (sub_82D43290) starts each new pair with the simplex solver's
// closest-point estimate v = (-FLT_MAX, -FLT_MAX, -FLT_MAX) (sub_82D12178) and the
// previous squared distance (FLT_MAX, -FLT_MAX, 0, 0) (sub_82D41210). Its termination test
// (sub_82D420F0) computes |v|^2 with vmsum3fp128 at 0x82D42120 and stops when
// FLT_EPSILON * previous >= previous - |v|^2 holds in every lane. The 3 * FLT_MAX^2 overflows:
// Xenon's VMX128 dot products return QNaN on overflow (Xenia emulates this, see its
// use_fast_dot_product option), so on the console the comparison is false and the first
// support point is added. The codegen uses SSE dpps, which gives +infinity: previous -
// infinity is -infinity, the test passes, and GJK stops before the simplex has a single
// vertex. The closest points are then computed from an empty simplex and their w lanes
// (the item indices, sub_82D41608 -> sub_82D0F6E0) come from simplex vertex 0, which was
// never written: stack garbage. sub_82D44B90 hands those indices to the physics definition
// loader sub_82D3DB00, which overran its 8-entry stack array with a garbage record and
// faulted while free roam loaded (docs/PROJECT.md). Whether it faulted depended on what an
// earlier call had left on that stack, hence about half the runs.
//
// The hook below sits right after that vmsum3fp128 and turns an overflow of finite inputs
// into QNaN, as Xenon does. FORZA_GJK_DOT_INF=1 keeps the infinity (the old behavior).
// (The proper fix is the codegen's vmsum3fp128/vmsum4fp128 in the SDK; this game only
// needed this one.)

#include <rex/logging.h>
#include <rex/ppc/context.h>

#include <atomic>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>

static_assert(offsetof(PPCContext, r3) == 0, "hooks recover ctx from &ctx.r3");

namespace {
std::atomic<uint64_t> overflows{0};
}  // namespace

// v61 = vmsum3fp128(v63, v63): the guest's x, y, z lanes are host lanes 1-3, the result is
// in all four.
void ForzaGjkDotOverflow_82D42124(PPCRegister& r3) {
  static const bool keep_inf = [] {
    const char* v = std::getenv("FORZA_GJK_DOT_INF");
    return v && *v && *v != '0';
  }();
  PPCContext& ctx = *reinterpret_cast<PPCContext*>(&r3);
  if (keep_inf || !std::isinf(ctx.v61.f32[0])) return;
  for (int i = 1; i < 4; ++i) {
    if (!std::isfinite(ctx.v63.f32[i])) return;  // infinity in, infinity out
  }
  for (int i = 0; i < 4; ++i) ctx.v61.u32[i] = 0x7FC00000;
  if (overflows.fetch_add(1, std::memory_order_relaxed) == 0) {
    REXLOG_INFO("GJK: |v|^2 overflowed in sub_82D420F0, QNaN as on Xenon (logged once)");
  }
}
