// forza - a text box over the game for the Horizon World's head-to-head challenges
// (src/hooks/world_challenge.cpp): prompts, countdowns, the race's distance and results.
//
// Drawn with the SDK's ImGui drawer at the top centre of the window, without taking input,
// and registered with the drawer only while it shows (as the achievement toasts are,
// achievement_toast.h): the drawer repaints the window nonstop while any dialog is
// registered. It is drawn over the presented frame, so tools/live_shot.sh screenshots
// (the game's output image) don't show it; every text is also logged ("HUD: ...").

#pragma once

#include <string>

namespace rex::ui {
class ImGuiDrawer;
class WindowedAppContext;
}  // namespace rex::ui

namespace forza {

// ForzaApp::OnCreateDialogs.
void InstallHud(rex::ui::ImGuiDrawer* drawer, rex::ui::WindowedAppContext& app_context);

// Shows `title` (first line, highlighted) and `body` for `seconds`, replacing what shows.
// Any thread. `log` false skips the log line (texts that change every frame).
void HudShow(const std::string& title, const std::string& body, double seconds, bool log = true);
void HudClear();

}  // namespace forza
