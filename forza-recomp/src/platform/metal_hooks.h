// forza - hooks in Apple Metal for macOS; see metal_hooks.mm.
#pragma once

namespace rex::system {
class IGraphicsSystem;
}

namespace forza {

// Installs hooks on Metal drawable presentation and pipeline creation;
// returns true when Metal is active.
bool InstallMetalHooks(rex::system::IGraphicsSystem* graphics);

}  // namespace forza
