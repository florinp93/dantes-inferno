// dantes_inferno - ReXGlue Recompiled Project
//
// Customize your app by overriding virtual hooks from rex::ReXApp.

#pragma once

#include <rex/rex_app.h>
#include <rex/cvar.h>
#include <rex/input/flags.h>

class DantesInfernoApp : public rex::ReXApp {
 public:
  using rex::ReXApp::ReXApp;

  static std::unique_ptr<rex::ui::WindowedApp> Create(
      rex::ui::WindowedAppContext& ctx) {
    return std::unique_ptr<DantesInfernoApp>(new DantesInfernoApp(ctx, "dantes_inferno",
        PPCImageConfig));
  }

  void OnPreSetup(rex::RuntimeConfig& config) override {
    // --- GPU plugin ---
    // Load the Xenos GPU emulation plugin (built as rexgpu-xenos.dll).
    // Without this, all Vd* graphics calls are no-ops and the game can't
    // render anything.
    config.gpu_plugin = "xenos";

    // --- Render target path ---
    // Use pixel-shader interlock (rasterizer-ordered views) instead of host
    // render targets. The host-RT (RTV/DSV) path corrupts pre-rendered VP6 FMV
    // video because the EDRAM resolve + frontbuffer dump doesn't correctly
    // handle the video render target's format and lifecycle (the RT gets
    // evicted from the host RT cache after ~20 frames, and the _AS_16_16_16_16
    // format is loaded with the wrong stride). The ROV path writes directly to
    // the EDRAM buffer, matching the working Vulkan fragment-shader-interlock
    // path. This is the same issue documented in TheSimpsonsGameRecomp #15.
    rex::cvar::SetFlagByName("render_target_path_d3d12", "rov");

    // --- Input configuration ---
    //
    // ReXGlue v0.10.0 ships three input drivers that coexist:
    //   1. SDL3 gamepad driver  (DualShock 3/4, DualSense, Xbox 360/One, ...)
    //   2. Windows XInput driver (Xbox pads only, selected via --input_backend xinput)
    //   3. MnK driver            (keyboard + mouse -> virtual Xbox 360 controller)
    //
    // SDL3 is the default and handles every major controller family through its
    // built-in HIDAPI backends. The MnK driver is always loaded but only feeds
    // input when mnk_mode is true, so a plugged-in gamepad and keyboard/mouse
    // can be used at the same time.

    // Explicit SDL backend (also the default) so a future cvar change can't
    // silently break gamepad support.
    REXCVAR_SET(input_backend, std::string("sdl"));

    // Enable keyboard/mouse as a virtual controller and use the mouse for the
    // right stick (dodge/camera in Dante's Inferno).
    rex::cvar::SetFlagByName("mnk_mode", "true");
    rex::cvar::SetFlagByName("mnk_mouse", "true");
    rex::cvar::SetFlagByName("mnk_sensitivity", "1.5");

    // Dante's Inferno MnK keybinds (action-oriented layout).
    // Game Xbox 360 layout:
    //   A = Jump / Interact / Confirm
    //   B = Heavy attack / Cancel
    //   X = Light attack
    //   Y = Grab / Context action
    //   LB = Block / Parry / Target lock
    //   RB = Magic / Projectile
    //   LT = Block / Modifier
    //   RT = Magic / Projectile
    //   Right stick = Dodge / Evade (flick direction)
    //   Back = Pause / Menu
    //   Start = Pause / Journal
    rex::cvar::SetFlagByName("keybind_a", "Space");
    rex::cvar::SetFlagByName("keybind_b", "F");
    rex::cvar::SetFlagByName("keybind_x", "MouseLeft");
    rex::cvar::SetFlagByName("keybind_y", "E");
    rex::cvar::SetFlagByName("keybind_left_shoulder", "Q");
    rex::cvar::SetFlagByName("keybind_right_shoulder", "MouseRight");
    rex::cvar::SetFlagByName("keybind_left_trigger", "Shift");
    rex::cvar::SetFlagByName("keybind_right_trigger", "Ctrl");
    rex::cvar::SetFlagByName("keybind_lstick_up", "W");
    rex::cvar::SetFlagByName("keybind_lstick_down", "S");
    rex::cvar::SetFlagByName("keybind_lstick_left", "A");
    rex::cvar::SetFlagByName("keybind_lstick_right", "D");
    rex::cvar::SetFlagByName("keybind_lstick_press", "X");
    // Right stick is driven by the mouse (mnk_mouse=true); arrow keys are a
    // fallback for dodge flicks.
    rex::cvar::SetFlagByName("keybind_rstick_up", "Up");
    rex::cvar::SetFlagByName("keybind_rstick_down", "Down");
    rex::cvar::SetFlagByName("keybind_rstick_left", "Left");
    rex::cvar::SetFlagByName("keybind_rstick_right", "Right");
    rex::cvar::SetFlagByName("keybind_rstick_press", "R");
    rex::cvar::SetFlagByName("keybind_dpad_up", "Shift+Up");
    rex::cvar::SetFlagByName("keybind_dpad_down", "Shift+Down");
    rex::cvar::SetFlagByName("keybind_dpad_left", "Shift+Left");
    rex::cvar::SetFlagByName("keybind_dpad_right", "Shift+Right");
    rex::cvar::SetFlagByName("keybind_back", "Tab");
    rex::cvar::SetFlagByName("keybind_start", "Escape");
  }
};
