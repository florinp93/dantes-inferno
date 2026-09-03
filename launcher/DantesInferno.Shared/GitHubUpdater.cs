using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace DantesInferno
{
    public class ReleaseAsset
    {
        public string Name { get; set; }
        public string BrowserDownloadUrl { get; set; }
    }

    public class ReleaseInfo
    {
        public string TagName { get; set; }
        public string Name { get; set; }
        public string Body { get; set; }
        public string HtmlUrl { get; set; }
        public bool Prerelease { get; set; }
        public List<ReleaseAsset> Assets { get; set; } = new List<ReleaseAsset>();

        public SemanticVersion Version
        {
            get { return SemanticVersion.Parse(TagName); }
        }
    }

    public class SemanticVersion : IComparable<SemanticVersion>
    {
        public int Major { get; set; }
        public int Minor { get; set; }
        public int Build { get; set; }
        public int Revision { get; set; }
        public string Prerelease { get; set; }
        public string BuildMetadata { get; set; }

        public static SemanticVersion Parse(string input)
        {
            var result = new SemanticVersion();
            if (string.IsNullOrWhiteSpace(input))
                return result;

            string text = input.Trim().ToLowerInvariant();
            text = Regex.Replace(text, "^v", string.Empty, RegexOptions.IgnoreCase);

            if (text.Contains("+"))
            {
                int plus = text.IndexOf("+");
                result.BuildMetadata = text.Substring(plus + 1);
                text = text.Substring(0, plus);
            }

            if (text.Contains("-"))
            {
                int dash = text.IndexOf("-");
                result.Prerelease = text.Substring(dash + 1);
                text = text.Substring(0, dash);
            }

            var parts = text.Split('.');
            int major = 0, minor = 0, build = 0, revision = 0;
            if (parts.Length > 0) int.TryParse(parts[0], out major);
            if (parts.Length > 1) int.TryParse(parts[1], out minor);
            if (parts.Length > 2) int.TryParse(parts[2], out build);
            if (parts.Length > 3) int.TryParse(parts[3], out revision);

            result.Major = major;
            result.Minor = minor;
            result.Build = build;
            result.Revision = revision;
            return result;
        }

        public int CompareTo(SemanticVersion other)
        {
            if (other == null) return 1;

            int result = Major.CompareTo(other.Major);
            if (result != 0) return result;

            result = Minor.CompareTo(other.Minor);
            if (result != 0) return result;

            result = Build.CompareTo(other.Build);
            if (result != 0) return result;

            result = Revision.CompareTo(other.Revision);
            if (result != 0) return result;

            if (string.IsNullOrEmpty(Prerelease) && string.IsNullOrEmpty(other.Prerelease))
                return 0;
            if (string.IsNullOrEmpty(Prerelease))
                return 1;
            if (string.IsNullOrEmpty(other.Prerelease))
                return -1;

            var a = Prerelease.Split('.');
            var b = other.Prerelease.Split('.');
            int len = Math.Max(a.Length, b.Length);
            for (int i = 0; i < len; i++)
            {
                if (i >= a.Length) return -1;
                if (i >= b.Length) return 1;

                bool aNum = int.TryParse(a[i], out int av);
                bool bNum = int.TryParse(b[i], out int bv);

                if (aNum && bNum)
                {
                    result = av.CompareTo(bv);
                    if (result != 0) return result;
                }
                else
                {
                    result = string.Compare(a[i], b[i], StringComparison.Ordinal);
                    if (result != 0) return result;
                }
            }

            return 0;
        }

        public override string ToString()
        {
            string v;
            if (Revision > 0)
                v = Major + "." + Minor + "." + Build + "." + Revision;
            else if (Build > 0)
                v = Major + "." + Minor + "." + Build;
            else
                v = Major + "." + Minor;
            if (!string.IsNullOrEmpty(Prerelease))
                v += "-" + Prerelease;
            if (!string.IsNullOrEmpty(BuildMetadata))
                v += "+" + BuildMetadata;
            return v;
        }

        public static bool operator >(SemanticVersion a, SemanticVersion b) { return a.CompareTo(b) > 0; }
        public static bool operator <(SemanticVersion a, SemanticVersion b) { return a.CompareTo(b) < 0; }
        public static bool operator >=(SemanticVersion a, SemanticVersion b) { return a.CompareTo(b) >= 0; }
        public static bool operator <=(SemanticVersion a, SemanticVersion b) { return a.CompareTo(b) <= 0; }
    }

    public static class GitHubUpdater
    {
        private const string ApiUrl = "https://api.github.com/repos/florinp93/dantes-inferno/releases";

        static GitHubUpdater()
        {
            try
            {
                ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072;
            }
            catch { }
        }

        public static ReleaseInfo CheckLatest(string token = null)
        {
            using (var client = new WebClient())
            {
                client.Headers["User-Agent"] = "DantesInfernoLauncher/1.0";
                if (!string.IsNullOrWhiteSpace(token))
                    client.Headers["Authorization"] = "token " + token;

                string json = client.DownloadString(ApiUrl);
                var serializer = new JavaScriptSerializer();
                var releases = serializer.Deserialize<List<object>>(json);
                if (releases == null || releases.Count == 0)
                    throw new InvalidOperationException("No releases found.");

                var first = releases[0] as Dictionary<string, object>;
                if (first == null)
                    throw new InvalidOperationException("Unexpected release list format.");

                return MapRelease(first);
            }
        }

        public static SemanticVersion GetLocalVersion(string installDirectory)
        {
            string versionPath = PathHelper.GetVersionPath(installDirectory);
            if (File.Exists(versionPath))
            {
                string text = File.ReadAllText(versionPath).Trim();
                return SemanticVersion.Parse(text);
            }
            return new SemanticVersion();
        }

        public static void SetLocalVersion(string installDirectory, SemanticVersion version)
        {
            string versionPath = PathHelper.GetVersionPath(installDirectory);
            Directory.CreateDirectory(Path.GetDirectoryName(versionPath) ?? installDirectory);
            File.WriteAllText(versionPath, version.ToString());
        }

        private static ReleaseInfo MapRelease(Dictionary<string, object> raw)
        {
            var info = new ReleaseInfo
            {
                TagName = raw.GetValueOrDefault("tag_name") as string,
                Name = raw.GetValueOrDefault("name") as string,
                Body = raw.GetValueOrDefault("body") as string,
                HtmlUrl = raw.GetValueOrDefault("html_url") as string,
            };

            if (raw.TryGetValue("prerelease", out var pre) && pre is bool b)
                info.Prerelease = b;

            if (raw.TryGetValue("assets", out var aObj) && aObj is IEnumerable assets)
            {
                foreach (var a in assets)
                {
                    if (a is Dictionary<string, object> asset)
                    {
                        info.Assets.Add(new ReleaseAsset
                        {
                            Name = asset.GetValueOrDefault("name") as string,
                            BrowserDownloadUrl = asset.GetValueOrDefault("browser_download_url") as string
                        });
                    }
                }
            }

            return info;
        }

        private static string GetValueOrDefault(this Dictionary<string, object> dict, string key)
        {
            return dict.TryGetValue(key, out var value) ? value as string : null;
        }
    }
}
