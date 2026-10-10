// forza - the ReXGlue app: runtime setup for Forza Horizon.
//
// Customize by overriding virtual hooks from rex::ReXApp.

#pragma once

#include <rex/filesystem/devices/host_path_device.h>
#include <rex/filesystem/vfs.h>
#include <rex/logging.h>
#include <rex/rex_app.h>
#include <rex/runtime.h>

#include <filesystem>
#include <string>

namespace forza {
void InstallFaultGuard();  // src/debug/fault_guard.cpp
namespace perf {
void Flush();  // src/debug/frame_stats.cpp
}  // namespace perf
}  // namespace forza

class ForzaApp : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<ForzaApp>(new ForzaApp(ctx, "forza",
        PPCImageConfig));
  }

  void OnPreSetup(rex::RuntimeConfig& config) override {
    if (!config.graphics && config.gpu_plugin.empty()) {
      config.gpu_plugin = "xenos";
    }
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

  void OnShutdown() override { forza::perf::Flush(); }

  // Override virtual hooks for customization:
  // void OnPostInitLogging() override {}
  // void OnLoadXexImage(std::string& xex_image) override {}
  // void OnPostLoadXexImage() override {}
  // void OnPostSetup() override {}
  // void OnConfigurePaths(rex::PathConfig& paths) override {}
};
