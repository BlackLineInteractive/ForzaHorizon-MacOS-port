// forza - the ReXGlue app: runtime setup for Forza Horizon.
//
// Customize by overriding virtual hooks from rex::ReXApp.

#pragma once

#include "debug/frame_stats.h"
#include "platform/achievement_toast.h"
#include "platform/vulkan_hooks.h"

#include <rex/filesystem/devices/host_path_device.h>
#include <rex/filesystem/vfs.h>
#include <rex/logging.h>
#include <rex/rex_app.h>
#include <rex/runtime.h>
#include <rex/system/gpu_plugin.h>
#include <rex/ui/overlay/achievement_notification.h>

#include <filesystem>
#include <string>

namespace forza {
void InstallFaultGuard();  // src/debug/fault_guard.cpp
}  // namespace forza

// SDK settings with this game's defaults (src/main.cpp).
void ApplyForzaCvarDefaults();

class ForzaApp : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<ForzaApp>(new ForzaApp(ctx, "forza",
        PPCImageConfig));
  }

  // Runs after forza.toml and the command line are applied, before the window opens.
  void OnPostInitLogging() override { ApplyForzaCvarDefaults(); }

  void OnPreSetup(rex::RuntimeConfig& config) override {
    if (!config.graphics && config.gpu_plugin.empty()) {
      config.gpu_plugin = "xenos";
    }
    // Loaded here rather than by the SDK so OnCreateDialogs can reach the GPU provider.
    if (!config.graphics && !config.gpu_plugin.empty()) {
      config.graphics = rex::system::LoadGpuPlugin(config.gpu_plugin);
    }
    graphics_ = config.graphics.get();
  }

  // The GPU provider exists now and the window has no swapchain yet: hook the Vulkan
  // calls (swapchain present-mode log, RECOMP_PERF timing; src/platform/vulkan_hooks.h).
  void OnCreateDialogs(rex::ui::ImGuiDrawer*) override { forza::InstallVulkanHooks(graphics_); }

  void OnPostSetup() override { forza::InstallVulkanHooks(runtime()->graphics_system()); }

  // The SDK's achievement toasts, registered with the ImGui drawer only while one shows, so
  // the window is not repainted nonstop (src/platform/achievement_toast.h; from
  // RecompiledHaloReach).
  std::unique_ptr<rex::ui::AchievementNotificationDialog> CreateAchievementNotificationDialog()
      override {
    return forza::MakeOnDemandToast(rex::ReXApp::CreateAchievementNotificationDialog(),
                                    imgui_drawer(), app_context());
  }

  // The SDK hard-exits right after a close request is accepted (SIGINT included), so the
  // frame statistics summary is written here.
  bool OnWindowCloseRequested() override {
    forza::perf::Shutdown();
    return true;
  }

  // The game keeps ghost and replay streams on the console's utility partition
  // (cache:\ghost_stream_N, cache:\replay_stream, as in Xenia's cache folder). Its
  // XAPI XMountUtilityDrive gets no symbolic link from the runtime (the SDK backs the
  // raw Cache0/Cache1 partitions with a null device), so cache:\ fails with "device
  // not found". Mount a host folder there as Xenia does with mount_cache.
  void OnPreLaunchModule() override {
    // After the runtime's own handlers (MMIO, GPU watches), so it only sees faults
    // nothing else takes.
    forza::InstallFaultGuard();
    auto* vfs = runtime()->file_system();
    const std::filesystem::path host = cache_root() / "cache";
    std::error_code ec;
    std::filesystem::create_directories(host, ec);
    auto device = std::make_unique<rex::filesystem::HostPathDevice>("\\CACHE", host, false);
    if (!device->Initialize() || !vfs->RegisterDevice(std::move(device)) ||
        !vfs->RegisterSymbolicLink("cache:", "\\CACHE")) {
      REXLOG_ERROR("Failed to mount cache: at {}", host.string());
    }
  }

  // Override virtual hooks for customization:
  // void OnLoadXexImage(std::string& xex_image) override {}
  // void OnPostLoadXexImage() override {}
  // void OnConfigurePaths(rex::PathConfig& paths) override {}

 private:
  rex::system::IGraphicsSystem* graphics_ = nullptr;
};
