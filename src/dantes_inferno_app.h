#pragma once

#include <rex/rex_app.h>
#include <rex/cvar.h>
#include <rex/chrono/clock.h>
#include <rex/filesystem.h>
#include <rex/input/flags.h>
#include <rex/ui/keybinds.h>
#include <rex/ui/imgui_dialog.h>
#include <rex/graphics/command_processor.h>
#include <rex/graphics/graphics_system.h>
#include <rex/logging/macros.h>

#include <array>
#include <chrono>
#include <cstring>
#include <cstdlib>

REXCVAR_DEFINE_DOUBLE(time_scalar, 1.0, "Gameplay",
                      "Guest time scaling factor (1.0 = normal, 50.0 = fast-forward)");

REXCVAR_DEFINE_BOOL(show_fps_overlay, false, "UI",
                    "Show FPS and frametime overlay (top-left corner)");

REXCVAR_DEFINE_STRING(glyph_family, "auto", "UI",
                      "Button glyph family: auto, xbox, or playstation");

REXCVAR_DEFINE_DOUBLE(ultrawide_target_aspect, 0.0, "Graphics",
                      "Target aspect ratio for ultrawide (0=disabled, 1.7778=16:9, "
                      "2.3889=21:9, 3.5556=32:9)");

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

    frame_history_[history_idx_] = static_cast<float>(guest_ft_ms);
    history_idx_ = (history_idx_ + 1) % kHistorySize;

    if (smoothed_fps_ == 0.0) {
      smoothed_fps_ = guest_fps;
      smoothed_ft_ = guest_ft_ms;
    } else {
      smoothed_fps_ = smoothed_fps_ * 0.85 + guest_fps * 0.15;
      smoothed_ft_ = smoothed_ft_ * 0.85 + guest_ft_ms * 0.15;
    }

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
      ImGui::SetWindowFontScale(2.0f);
      ImU32 fps_color = smoothed_fps_ >= 55.0f ? IM_COL32(80, 255, 80, 255) :
                       smoothed_fps_ >= 30.0f ? IM_COL32(255, 220, 60, 255) :
                                                IM_COL32(255, 80, 80, 255);
      ImGui::PushStyleColor(ImGuiCol_Text, fps_color);
      ImGui::Text("%.0f FPS", smoothed_fps_);
      ImGui::PopStyleColor();
      ImGui::SetWindowFontScale(1.0f);

      ImGui::SetWindowFontScale(1.3f);
      ImGui::Text("%.1f ms", smoothed_ft_);
      ImGui::SetWindowFontScale(1.0f);

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

  void OnConfigurePaths(rex::PathConfig& paths) override {
    if (!paths.game_data_root.empty())
      return;

    const std::filesystem::path candidates[] = {
        rex::filesystem::GetExecutableFolder() / "game",
        std::filesystem::current_path() / "game",
    };
    for (const auto& candidate : candidates) {
      std::error_code ec;
      if (std::filesystem::is_directory(candidate, ec)) {
        paths.game_data_root = candidate;
        return;
      }
    }
  }

  void OnPreSetup(rex::RuntimeConfig& config) override {
    config.gpu_plugin = "xenos";

    REXCVAR_SET(input_backend, std::string("sdl"));

    rex::cvar::SetFlagByName("mnk_mode", "true");
    rex::cvar::SetFlagByName("mnk_mouse", "true");
    rex::cvar::SetFlagByName("mnk_sensitivity", "1.5");

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

    double target_aspect = REXCVAR_GET(ultrawide_target_aspect);
    if (target_aspect > 0.0) {
      g_ultrawide_target_aspect = static_cast<float>(target_aspect);
      if (target_aspect >= 1.7778) {
        rex::cvar::SetFlagByName("present_letterbox", "false");
        REXLOG_INFO("ULTRAWIDE: target_aspect={:.4f}, present_letterbox disabled",
                    target_aspect);
      } else {
        rex::cvar::SetFlagByName("present_letterbox", "true");
        REXLOG_INFO("ULTRAWIDE: target_aspect={:.4f}, present_letterbox enabled",
                    target_aspect);
      }
    } else {
      REXLOG_INFO("ULTRAWIDE: disabled (target_aspect={:.4f})", target_aspect);
    }
  }

  void OnPreLaunchModule() override {
    uint8_t* membase = runtime()->memory()->virtual_membase();

    auto* ptr = reinterpret_cast<uint32_t*>(membase + 0x82B101E4);
    *ptr = 0u;
  }

  void OnPostSetup() override {
    rex::chrono::Clock::set_guest_time_scalar(REXCVAR_GET(time_scalar));

    rex::cvar::RegisterChangeCallback("time_scalar",
        [](std::string_view, std::string_view new_value) {
          double scalar = std::stod(std::string(new_value));
          if (scalar < 0.0) scalar = 0.0;
          rex::chrono::Clock::set_guest_time_scalar(scalar);
        });

    rex::cvar::RegisterChangeCallback("ultrawide_target_aspect",
        [](std::string_view, std::string_view new_value) {
          double aspect = std::stod(std::string(new_value));
          g_ultrawide_target_aspect = static_cast<float>(aspect);
          if (aspect >= 1.7778) {
            rex::cvar::SetFlagByName("present_letterbox", "false");
          } else {
            rex::cvar::SetFlagByName("present_letterbox", "true");
          }
        });

    rex::ui::RegisterBind("bind_exit_game", "Alt+F4",
                          "Exit game to desktop", [this] {
      app_context().RequestDeferredQuit();
    });

    if (REXCVAR_GET(show_fps_overlay) && imgui_drawer()) {
      auto* gfx_sys = runtime() ? runtime()->graphics_system() : nullptr;
      auto* command_processor = gfx_sys
          ? static_cast<rex::graphics::GraphicsSystem*>(gfx_sys)->command_processor()
          : nullptr;
      fps_overlay_ = std::make_unique<FpsOverlayDialog>(imgui_drawer(), command_processor);
    }

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

    rex::ui::RegisterBind("bind_fast_forward", "F2",
                          "Toggle 50x fast-forward", [this] {
      double current = REXCVAR_GET(time_scalar);
      bool fast = current > 1.0;
      double target = fast ? 1.0 : 50.0;
      rex::cvar::SetFlagByName("time_scalar", std::to_string(target));
      rex::chrono::Clock::set_guest_time_scalar(target);
      rex::cvar::SetFlagByName("vsync", fast ? "true" : "false");
    });
  }

  void OnShutdown() override {
    rex::ui::UnregisterBind("bind_fast_forward");
    rex::ui::UnregisterBind("bind_fps_overlay");
    rex::ui::UnregisterBind("bind_exit_game");
    rex::cvar::UnregisterChangeCallbacks("time_scalar");
    rex::cvar::UnregisterChangeCallbacks("ultrawide_target_aspect");
    fps_overlay_.reset();
    rex::chrono::Clock::set_guest_time_scalar(1.0);
    rex::cvar::SetFlagByName("vsync", "true");
  }

 private:
  std::unique_ptr<FpsOverlayDialog> fps_overlay_;
};
