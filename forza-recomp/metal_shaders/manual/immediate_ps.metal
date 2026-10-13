// Hand-written Metal version of the ReXGlue SDK's src/ui/shaders/vulkan_spirv/immediate_ps.h
// (the ImGui / immediate drawer pixel shader). SPIRV-Cross cannot translate that one with
// argument buffers, so tools/spirv_to_metal.py uses this file instead.
//
// Vulkan: set 0 binding 0 is a combined image sampler; inputs are location 0 (texcoord) and
// location 1 (color) from immediate_vs. Output = color * texture sampled at LOD 0.
#include <metal_stdlib>

using namespace metal;

struct immediate_ps_set0 {
  texture2d<float> texture_ [[id(0)]];
  sampler sampler_ [[id(1)]];
};

struct immediate_ps_in {
  float2 texcoord [[user(locn0)]];
  float4 color [[user(locn1)]];
};

fragment float4 immediate_ps(immediate_ps_in in [[stage_in]],
                             constant immediate_ps_set0& set0 [[buffer(0)]]) {
  return in.color * set0.texture_.sample(set0.sampler_, in.texcoord, level(0.0f));
}
