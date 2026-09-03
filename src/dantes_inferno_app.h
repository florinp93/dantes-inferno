// dantes_inferno - ReXGlue Recompiled Project
//
// Customize your app by overriding virtual hooks from rex::ReXApp.

#pragma once

#include <rex/rex_app.h>
#include <rex/cvar.h>
#include <rex/chrono/clock.h>
#include <rex/input/flags.h>
#include <rex/ui/keybinds.h>
#include <rex/ui/imgui_dialog.h>
#include <rex/graphics/command_processor.h>
#include <rex/graphics/graphics_system.h>
#include <rex/logging/macros.h>

#include <array>
#include <chrono>
#include <cstring>

// Time scalar cvar: 1.0 = normal speed, 50.0 = 50x fast-forward for FMVs.
// Can be set from the console (backtick key) or toggled with F2.
REXCVAR_DEFINE_DOUBLE(time_scalar, 1.0, "Gameplay",
                      "Guest time scaling factor (1.0 = normal, 50.0 = fast-forward)");

// Toggle for the FPS overlay.
REXCVAR_DEFINE_BOOL(show_fps_overlay, false, "UI",
                    "Show FPS and frametime overlay (top-left corner)");

REXCVAR_DEFINE_STRING(glyph_family, "auto", "UI",
                      "Button glyph family: auto, xbox, or playstation");

// Simple FPS + frametime overlay dialog, always visible in top-left corner.
// Measures actual guest frame rate (game frames), not host present rate.
//
// The guest frame boundary is CommandProcessor::counter_, incremented once
// per PM4_XE_SWAP packet the recompiled game submits (see VdSwap_entry in
// xboxkrnl_video.cpp and CommandProcessor::ExecutePacketType3_XE_SWAP) -
// i.e. once per real guest-side present, not once per host D3D12 present.
class FpsOverlayDialog : public rex::ui::ImGuiDialog {
 public:
  explicit FpsOverlayDialog(rex::ui::ImGuiDrawer* drawer,
                            rex::graphics::CommandProcessor* command_processor)
      : rex::ui::ImGuiDialog(drawer),
        command_processor_(command_processor),
        last_time_(std::chrono::steady_clock::now()),
        last_guest_frame_count_(command_processor ? command_processor->counter() : 0) {}

 protected:
  void OnDraw(ImGuiIO& io) override {
    auto now = std::chrono::steady_clock::now();
    auto delta = std::chrono::duration<double, std::milli>(now - last_time_);
    last_time_ = now;

    // Read the guest frame counter from the GPU command processor to get
    // the actual game frame rate (not the host present rate).
    uint64_t current_guest_frames =
        command_processor_ ? command_processor_->counter() : 0;
    uint64_t frames_delta = current_guest_frames - last_guest_frame_count_;
    last_guest_frame_count_ = current_guest_frames;

    double interval_ms = delta.count();
    double guest_fps = 0;
    double guest_ft_ms = 0;
    if (frames_delta > 0 && interval_ms > 0) {
      guest_fps = frames_delta * 1000.0 / interval_ms;
      guest_ft_ms = interval_ms / frames_delta;
    }

    // Update frametime history (rolling buffer).
    frame_history_[history_idx_] = static_cast<float>(guest_ft_ms);
    history_idx_ = (history_idx_ + 1) % kHistorySize;

    // Smoothed values (exponential moving average).
    if (smoothed_fps_ == 0.0) {
      smoothed_fps_ = guest_fps;
      smoothed_ft_ = guest_ft_ms;
    } else {
      smoothed_fps_ = smoothed_fps_ * 0.85 + guest_fps * 0.15;
      smoothed_ft_ = smoothed_ft_ * 0.85 + guest_ft_ms * 0.15;
    }

    // Draw window in top-left corner, no title bar, no interaction.
    ImGui::SetNextWindowPos(ImVec2(8, 8), ImGuiCond_Always);
    ImGui::SetNextWindowBgAlpha(0.65f);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(10, 8));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding, 4.0f);

    bool visible = true;
    if (ImGui::Begin("##fps_overlay", &visible,
                     ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoResize |
                         ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoCollapse |
                         ImGuiWindowFlags_NoInputs | ImGuiWindowFlags_NoNav |
                         ImGuiWindowFlags_NoSavedSettings |
                         ImGuiWindowFlags_AlwaysAutoResize |
                         ImGuiWindowFlags_NoFocusOnAppearing)) {
      // FPS text - large, color-coded
      ImGui::SetWindowFontScale(2.0f);
      ImU32 fps_color = smoothed_fps_ >= 55.0f ? IM_COL32(80, 255, 80, 255) :
                       smoothed_fps_ >= 30.0f ? IM_COL32(255, 220, 60, 255) :
                                                IM_COL32(255, 80, 80, 255);
      ImGui::PushStyleColor(ImGuiCol_Text, fps_color);
      ImGui::Text("%.0f FPS", smoothed_fps_);
      ImGui::PopStyleColor();
      ImGui::SetWindowFontScale(1.0f);

      // Frametime text
      ImGui::SetWindowFontScale(1.3f);
      ImGui::Text("%.1f ms", smoothed_ft_);
      ImGui::SetWindowFontScale(1.0f);

      // Frametime graph
      ImGui::Spacing();
      ImGui::PlotLines("##frametime", frame_history_.data(),
                       static_cast<int>(kHistorySize),
                       static_cast<int>(history_idx_), nullptr,
                       0.0f, 50.0f, ImVec2(220, 50));
    }
    ImGui::End();
    ImGui::PopStyleVar(2);
  }

 private:
  static constexpr size_t kHistorySize = 120;
  std::array<float, kHistorySize> frame_history_{};
  size_t history_idx_ = 0;
  rex::graphics::CommandProcessor* command_processor_;
  std::chrono::steady_clock::time_point last_time_;
  uint64_t last_guest_frame_count_;
  double smoothed_fps_ = 0.0;
  double smoothed_ft_ = 0.0;
};

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

  void OnPreLaunchModule() override {
    uint8_t* membase = runtime()->memory()->virtual_membase();
    auto* ptr = reinterpret_cast<uint32_t*>(membase + 0x82B101E4);
    *ptr = 0u;
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

    // Create the FPS overlay if enabled.
    if (REXCVAR_GET(show_fps_overlay) && imgui_drawer()) {
      // IGraphicsSystem (the interface runtime() hands back) only exposes
      // presenter(); command_processor() lives on the concrete backend base
      // (D3D12/Vulkan both derive from it), same downcast the SDK itself
      // uses internally (see d3d12/graphics_system.cpp).
      auto* gfx_sys = runtime() ? runtime()->graphics_system() : nullptr;
      auto* command_processor = gfx_sys
          ? static_cast<rex::graphics::GraphicsSystem*>(gfx_sys)->command_processor()
          : nullptr;
      fps_overlay_ = std::make_unique<FpsOverlayDialog>(imgui_drawer(), command_processor);
    }

    // F1 toggles the FPS overlay on/off.
    rex::ui::RegisterBind("bind_fps_overlay", "F1",
                          "Toggle FPS overlay", [this] {
      if (fps_overlay_) {
        fps_overlay_.reset();
      } else if (imgui_drawer()) {
        auto* gfx_sys = runtime() ? runtime()->graphics_system() : nullptr;
        auto* command_processor = gfx_sys
            ? static_cast<rex::graphics::GraphicsSystem*>(gfx_sys)->command_processor()
            : nullptr;
        fps_overlay_ = std::make_unique<FpsOverlayDialog>(imgui_drawer(), command_processor);
      }
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
    rex::ui::UnregisterBind("bind_fps_overlay");
    rex::cvar::UnregisterChangeCallbacks("time_scalar");
    fps_overlay_.reset();
    // Restore normal speed and vsync on exit.
    rex::chrono::Clock::set_guest_time_scalar(1.0);
    rex::cvar::SetFlagByName("vsync", "true");
  }

 private:
  std::unique_ptr<FpsOverlayDialog> fps_overlay_;
};
