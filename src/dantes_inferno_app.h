// dantes_inferno - ReXGlue Recompiled Project
//
// Customize your app by overriding virtual hooks from rex::ReXApp.

#pragma once

#include <rex/rex_app.h>
#include <rex/cvar.h>
#include <rex/chrono/clock.h>
#include <rex/input/flags.h>
#include <rex/ui/keybinds.h>
#include <rex/logging/macros.h>

// Time scalar cvar: 1.0 = normal speed, 50.0 = 50x fast-forward for FMVs.
// Can be set from the console (backtick key) or toggled with F2.
REXCVAR_DEFINE_DOUBLE(time_scalar, 1.0, "Gameplay",
                      "Guest time scaling factor (1.0 = normal, 50.0 = fast-forward)");

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
    //
    // NOTE: GPU cvars (render_target_path_d3d12, resolution_scale, etc.) are
    // defined inside rexgpu-xenos.dll, which isn't loaded until after
    // OnPreSetup returns. SetFlagByName here returns false because the cvars
    // aren't registered yet. These must be passed as command-line arguments
    // (--render_target_path_d3d12=rov, --resolution_scale=2, etc.) which are
    // parsed after all cvars are registered. See launch.ps1.

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

  void OnPostLoadXexImage() override {
    // Patch: zero out the fiber-switch callback at guest 0x82B101E4.
    //
    // sub_82701240 is a setjmp-like context-save used by the save system.
    // It loads a function pointer from 0x82B101E4; if non-zero it calls that
    // function and returns immediately WITHOUT saving the context. The XEX
    // ships a no-op blr stub (sub_821EA208) at that address, so the "save"
    // returns with r3 still holding the non-zero buffer address. The caller
    // (sub_8267ACC8) interprets the non-zero return as an error and aborts,
    // leaving the save object null and eventually crashing.
    //
    // Zeroing the pointer makes sub_82701240 fall through to the normal
    // context-save path, which sets r3=0 (success) and returns.
    //
    // NOTE: OnPostLoadXexImage is called before relocations are applied,
    // so the value is still 0 here. The actual write of 0x821EA208 happens
    // during module launch. We patch it in OnPreLaunchModule instead.
  }

  void OnPreLaunchModule() override {
    // By now the module is launched, relocations are applied, and the
    // fiber-switch callback at 0x82B101E4 has been set to 0x821EA208
    // (a no-op blr stub). Zero it out so sub_82701240 does the normal
    // context save and returns success.
    uint8_t* membase = runtime()->memory()->virtual_membase();
    auto* ptr = reinterpret_cast<uint32_t*>(membase + 0x82B101E4);
    REXLOG_INFO("OnPreLaunchModule: ptr={:p}, old value=0x{:08X}",
                (void*)ptr, *ptr);
    *ptr = 0u;
    REXLOG_INFO("OnPreLaunchModule: patched 0x82B101E4 to 0, new value=0x{:08X}", *ptr);
  }

  void OnPostSetup() override {
    // Apply the initial time_scalar value (may have been set on command line).
    rex::chrono::Clock::set_guest_time_scalar(REXCVAR_GET(time_scalar));

    // React to console changes: "time_scalar 50" in the console (backtick key).
    rex::cvar::RegisterChangeCallback("time_scalar",
        [](std::string_view, std::string_view new_value) {
          double scalar = std::stod(std::string(new_value));
          if (scalar < 0.0) scalar = 0.0;
          rex::chrono::Clock::set_guest_time_scalar(scalar);
        });

    // F2 toggles between 1.0x and 50.0x for quick FMV fast-forward.
    // FMV players are typically frame-based (one video frame per game loop
    // iteration), not time-based, so time scaling alone doesn't speed them up.
    // We also disable vsync to uncap the host frame rate, letting the game
    // loop run as fast as the CPU/GPU can process frames.
    rex::ui::RegisterBind("bind_fast_forward", "F2",
                          "Toggle 50x fast-forward (FMV skip)", [this] {
      double current = REXCVAR_GET(time_scalar);
      bool fast = current > 1.0;
      double target = fast ? 1.0 : 50.0;
      rex::cvar::SetFlagByName("time_scalar", std::to_string(target));
      rex::chrono::Clock::set_guest_time_scalar(target);
      // Disable vsync to uncap frame rate while fast-forwarding.
      rex::cvar::SetFlagByName("vsync", fast ? "true" : "false");
    });
  }

  void OnShutdown() override {
    rex::ui::UnregisterBind("bind_fast_forward");
    rex::cvar::UnregisterChangeCallbacks("time_scalar");
    // Restore normal speed and vsync on exit.
    rex::chrono::Clock::set_guest_time_scalar(1.0);
    rex::cvar::SetFlagByName("vsync", "true");
  }
};
