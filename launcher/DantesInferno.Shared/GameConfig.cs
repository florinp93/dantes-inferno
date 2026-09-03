using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

namespace DantesInferno
{
    public class GameConfig
    {
        private readonly Dictionary<string, string> _values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private readonly string _path;

        public GameConfig(string path)
        {
            _path = path ?? string.Empty;
        }

        public static GameConfig Load(string path)
        {
            var cfg = new GameConfig(path);
            if (File.Exists(path))
            {
                foreach (var line in File.ReadAllLines(path))
                {
                    var trimmed = line.Trim();
                    if (string.IsNullOrEmpty(trimmed) || trimmed.StartsWith("#"))
                        continue;

                    int eq = trimmed.IndexOf('=');
                    if (eq <= 0) continue;

                    string key = trimmed.Substring(0, eq).Trim();
                    string raw = trimmed.Substring(eq + 1).Trim();
                    string value = Unquote(raw);
                    cfg._values[key] = value;
                }
            }
            return cfg;
        }

        public void Save()
        {
            var sb = new StringBuilder();

            var keys = _values.Keys.OrderBy(k => k, StringComparer.OrdinalIgnoreCase).ToList();
            foreach (var key in keys)
            {
                string value = _values[key];
                if (value == null) continue;

                if (IsNumber(value) || IsBool(value))
                    sb.AppendLine($"{key} = {value}");
                else
                    sb.AppendLine($"{key} = \"{Escape(value)}\"");
            }

            Directory.CreateDirectory(Path.GetDirectoryName(_path) ?? ".");
            File.WriteAllText(_path, sb.ToString(), Encoding.UTF8);
        }

        public string this[string key]
        {
            get { return _values.TryGetValue(key, out var v) ? v : null; }
            set { _values[key] = value ?? string.Empty; }
        }

        public T Get<T>(string key, T defaultValue) where T : IConvertible
        {
            if (!_values.TryGetValue(key, out var raw) || raw == null)
                return defaultValue;
            try
            {
                return (T)Convert.ChangeType(raw, typeof(T), CultureInfo.InvariantCulture);
            }
            catch
            {
                return defaultValue;
            }
        }

        public void Set<T>(string key, T value) where T : IConvertible
        {
            _values[key] = value?.ToString() ?? string.Empty;
        }

        private static string Unquote(string raw)
        {
            if (raw.Length >= 2 && raw.StartsWith("\"") && raw.EndsWith("\""))
            {
                var inner = raw.Substring(1, raw.Length - 2);
                return inner.Replace("\\\"", "\"").Replace("\\\\", "\\");
            }
            return raw;
        }

        private static string Escape(string value)
        {
            return value.Replace("\\", "\\\\").Replace("\"", "\\\"");
        }

        private static bool IsNumber(string value)
        {
            if (string.IsNullOrEmpty(value)) return false;
            return double.TryParse(value, NumberStyles.Any, CultureInfo.InvariantCulture, out _);
        }

        private static bool IsBool(string value)
        {
            return value.Equals("true", StringComparison.OrdinalIgnoreCase) ||
                   value.Equals("false", StringComparison.OrdinalIgnoreCase);
        }

        public string GameDataRoot
        {
            get { return this["game_data_root"]; }
            set { this["game_data_root"] = value; }
        }

        public string Resolution
        {
            get { return this["resolution"] ?? "1080p"; }
            set { this["resolution"] = value; }
        }

        public int ResolutionScale
        {
            get { return Get("resolution_scale", 1); }
            set { Set("resolution_scale", Math.Max(1, Math.Min(8, value))); }
        }

        public int AnisotropicOverride
        {
            get { return Get("anisotropic_override", -1); }
            set { Set("anisotropic_override", Math.Max(-1, Math.Min(16, value))); }
        }

        public string SwapPostEffect
        {
            get { return this["swap_post_effect"] ?? "none"; }
            set { this["swap_post_effect"] = value; }
        }

        public string PresentEffect
        {
            get { return this["present_effect"] ?? "bilinear"; }
            set { this["present_effect"] = value; }
        }

        public bool VSync
        {
            get { return Get("vsync", true); }
            set { Set("vsync", value); }
        }

        public bool Fullscreen
        {
            get { return Get("fullscreen", true); }
            set { Set("fullscreen", value); }
        }

        public string RenderTargetPath
        {
            get { return this["render_target_path_d3d12"] ?? "rov"; }
            set { this["render_target_path_d3d12"] = value; }
        }

        public string InputBackend
        {
            get { return this["input_backend"] ?? "sdl"; }
            set { this["input_backend"] = value; }
        }

        public bool MnkMode
        {
            get { return Get("mnk_mode", true); }
            set { Set("mnk_mode", value); }
        }

        public bool MnkMouse
        {
            get { return Get("mnk_mouse", true); }
            set { Set("mnk_mouse", value); }
        }

        public double MnkSensitivity
        {
            get { return Get("mnk_sensitivity", 1.5); }
            set { Set("mnk_sensitivity", value); }
        }

        public string LogLevel
        {
            get { return this["log_level"] ?? "off"; }
            set { this["log_level"] = value; }
        }

        public bool PlayStationGlyphs
        {
            get { return Get("playstation_glyphs", false); }
            set { Set("playstation_glyphs", value); }
        }
    }
}
