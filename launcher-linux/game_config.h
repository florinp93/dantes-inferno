#pragma once

#include <QSettings>
#include <QString>
#include <QStringList>

namespace dantes::launcher {

struct GameSettings {
  int resolutionScale = 1;
  QString antiAliasing = QStringLiteral("none");
  int anisotropic = 16;
  bool fullscreen = true;
  bool vsync = true;
  bool native2xMsaa = false;
  bool asyncShaders = true;
  int pipelineThreads = -1;

  bool forceStereo = true;
  int audioQueuedFrames = 16;
  bool xmaWorker = false;
  bool frontOnly = true;
  double outputGain = 0.5;
  int highpassHz = 100;

  int languageId = 1;
  int countryId = 103;
  bool logging = true;
};

class GameConfig {
 public:
  static QString globalConfigPath();
  static QString dataRootConfigPath(const QString& dataRoot);
  static QString selectedDataRoot();
  static void setSelectedDataRoot(const QString& root);
  static QString selectedGameRoot();
  static void setSelectedGameRoot(const QString& root);

  static GameSettings load(const QString& dataRoot);
  static bool save(const QString& dataRoot, const GameSettings& settings,
                   QString* error = nullptr);
  static QStringList commandLine(const QString& dataRoot, const QString& gameRoot,
                                 const GameSettings& settings);

 private:
  static GameSettings read(QSettings& settings);
  static void write(QSettings& out, const GameSettings& settings);
};

}  // namespace dantes::launcher
