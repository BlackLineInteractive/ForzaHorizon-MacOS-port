// forza - the ReXGlue app: runtime setup for Forza Horizon.
//
// Customize by overriding virtual hooks from rex::ReXApp.

#pragma once

#include <rex/logging.h>
#include <rex/rex_app.h>
#include <rex/runtime.h>

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

  // Override virtual hooks for customization:
  // void OnPostInitLogging() override {}
  // void OnLoadXexImage(std::string& xex_image) override {}
  // void OnPostLoadXexImage() override {}
  // void OnPreLaunchModule() override {}
  // void OnPostSetup() override {}
  // void OnShutdown() override {}
  // void OnConfigurePaths(rex::PathConfig& paths) override {}
};
