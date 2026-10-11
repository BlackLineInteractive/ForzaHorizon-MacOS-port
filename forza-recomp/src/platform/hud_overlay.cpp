// forza - the challenge text box over the game; see hud_overlay.h.

#include "hud_overlay.h"

#include <imgui.h>
#include <rex/logging.h>
#include <rex/ui/imgui_dialog.h>
#include <rex/ui/imgui_drawer.h>
#include <rex/ui/windowed_app_context.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>

namespace forza {
namespace {

using Clock = std::chrono::steady_clock;

class HudDialog final : public rex::ui::ImGuiDialog {
 public:
  HudDialog(rex::ui::ImGuiDrawer* drawer, rex::ui::WindowedAppContext& app_context)
      : ImGuiDialog(drawer), drawer_(drawer), app_context_(app_context) {
    drawer_->RemoveDialog(this);  // the constructor registered it; registered while shown
  }

  void Show(const std::string& title, const std::string& body, double seconds) {
    {
      std::lock_guard lock(mutex_);
      title_ = title;
      body_ = body;
      until_ = Clock::now() + std::chrono::milliseconds(int64_t(seconds * 1000));
    }
    if (!registered_.exchange(true)) {
      app_context_.CallInUIThread([this] { drawer_->AddDialog(this); });
    }
  }

  void Clear() {
    std::lock_guard lock(mutex_);
    until_ = Clock::time_point{};
  }

 protected:
  void OnDraw(ImGuiIO& io) override {
    std::string title, body;
    {
      std::lock_guard lock(mutex_);
      if (Clock::now() >= until_) {
        // The drawer detaches from the presenter once its last dialog is gone.
        registered_ = false;
        drawer_->RemoveDialog(this);
        return;
      }
      title = title_;
      body = body_;
    }
    const float scale = std::clamp(io.DisplaySize.y / 720.0f, 1.0f, 2.5f);
    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.06f),
                            ImGuiCond_Always, ImVec2(0.5f, 0.0f));
    ImGui::SetNextWindowBgAlpha(0.72f);
    const ImGuiWindowFlags flags =
        ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoMove |
        ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoInputs |
        ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoFocusOnAppearing;
    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding, 6.0f * scale);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(16.0f * scale, 10.0f * scale));
    if (ImGui::Begin("##forza_hud", nullptr, flags)) {
      ImGui::SetWindowFontScale(1.5f * scale);
      ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1.0f, 0.62f, 0.1f, 1.0f));
      ImGui::TextUnformatted(title.c_str());
      ImGui::PopStyleColor();
      ImGui::SetWindowFontScale(1.25f * scale);
      if (!body.empty()) ImGui::TextUnformatted(body.c_str());
    }
    ImGui::End();
    ImGui::PopStyleVar(2);
  }

 private:
  rex::ui::ImGuiDrawer* drawer_;
  rex::ui::WindowedAppContext& app_context_;
  std::mutex mutex_;
  std::string title_, body_;
  Clock::time_point until_{};
  std::atomic<bool> registered_{false};
};

// Lives for the whole run (the drawer keeps a raw pointer while it is registered).
HudDialog* hud = nullptr;

}  // namespace

void InstallHud(rex::ui::ImGuiDrawer* drawer, rex::ui::WindowedAppContext& app_context) {
  if (!drawer || hud) return;
  hud = new HudDialog(drawer, app_context);
}

void HudShow(const std::string& title, const std::string& body, double seconds, bool log) {
  if (log) REXLOG_INFO("HUD: {} | {}", title, body);
  if (hud) hud->Show(title, body, seconds);
}

void HudClear() {
  if (hud) hud->Clear();
}

}  // namespace forza
