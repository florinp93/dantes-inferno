#include "game_config.h"

#include <QDir>
#include <QStandardPaths>

namespace dantes::launcher {
namespace {

QString booleanArgument(const char* name, bool value) {
  return QStringLiteral("--%1=%2")
      .arg(QString::fromLatin1(name), value ? QStringLiteral("true")
                                            : QStringLiteral("false"));
}

QString valueArgument(const char* name, const QString& value) {
  return QStringLiteral("--%1=%2").arg(QString::fromLatin1(name), value);
}

}  // namespace

QString GameConfig::globalConfigPath() {
  const QString directory =
      QStandardPaths::writableLocation(QStandardPaths::AppConfigLocation);
  QDir().mkpath(directory);
  return QDir(directory).filePath(QStringLiteral("launcher.ini"));
}

QString GameConfig::dataRootConfigPath(const QString& dataRoot) {
  return QDir(dataRoot).filePath(QStringLiteral("config/launcher.ini"));
}

QString GameConfig::selectedDataRoot() {
  QSettings settings(globalConfigPath(), QSettings::IniFormat);
  return QDir::cleanPath(
      settings.value(QStringLiteral("paths/data_root")).toString());
}

void GameConfig::setSelectedDataRoot(const QString& root) {
  QSettings settings(globalConfigPath(), QSettings::IniFormat);
  settings.setValue(QStringLiteral("paths/data_root"),
                    QDir::cleanPath(QDir(root).absolutePath()));
  settings.sync();
}

QString GameConfig::selectedGameRoot() {
  QSettings settings(globalConfigPath(), QSettings::IniFormat);
  return QDir::cleanPath(
      settings.value(QStringLiteral("paths/game_root")).toString());
}

void GameConfig::setSelectedGameRoot(const QString& root) {
  QSettings settings(globalConfigPath(), QSettings::IniFormat);
  settings.setValue(QStringLiteral("paths/game_root"),
                    QDir::cleanPath(QDir(root).absolutePath()));
  settings.sync();
}

GameSettings GameConfig::read(QSettings& in) {
  GameSettings result;
  result.resolutionScale =
      in.value(QStringLiteral("graphics/resolution_scale"), 1).toInt();
  result.antiAliasing =
      in.value(QStringLiteral("graphics/swap_post_effect"), QStringLiteral("none"))
          .toString();
  result.anisotropic =
      in.value(QStringLiteral("graphics/anisotropic_override"), 16).toInt();
  result.fullscreen =
      in.value(QStringLiteral("graphics/fullscreen"), true).toBool();
  result.vsync = in.value(QStringLiteral("graphics/vsync"), true).toBool();
  result.native2xMsaa =
      in.value(QStringLiteral("graphics/native_2x_msaa"), false).toBool();
  result.asyncShaders =
      in.value(QStringLiteral("graphics/async_shader_compilation"), true).toBool();
  result.pipelineThreads =
      in.value(QStringLiteral("graphics/vulkan_pipeline_creation_threads"), -1)
          .toInt();

  result.forceStereo =
      in.value(QStringLiteral("audio/force_stereo"), true).toBool();
  result.audioQueuedFrames =
      in.value(QStringLiteral("audio/max_queued_frames"), 16).toInt();
  result.xmaWorker =
      in.value(QStringLiteral("audio/xma_worker"), false).toBool();
  result.frontOnly =
      in.value(QStringLiteral("audio/front_only"), true).toBool();
  result.outputGain =
      in.value(QStringLiteral("audio/output_gain"), 0.5).toDouble();
  result.highpassHz =
      in.value(QStringLiteral("audio/highpass_hz"), 100).toInt();

  result.languageId =
      in.value(QStringLiteral("locale/language_id"), 1).toInt();
  result.countryId = in.value(QStringLiteral("locale/country_id"), 103).toInt();
  result.logging = in.value(QStringLiteral("general/logging"), true).toBool();
  return result;
}

void GameConfig::write(QSettings& out, const GameSettings& value) {
  out.setValue(QStringLiteral("graphics/resolution_scale"),
               value.resolutionScale);
  out.setValue(QStringLiteral("graphics/swap_post_effect"),
               value.antiAliasing);
  out.setValue(QStringLiteral("graphics/anisotropic_override"),
               value.anisotropic);
  out.setValue(QStringLiteral("graphics/fullscreen"), value.fullscreen);
  out.setValue(QStringLiteral("graphics/vsync"), value.vsync);
  out.setValue(QStringLiteral("graphics/native_2x_msaa"), value.native2xMsaa);
  out.setValue(QStringLiteral("graphics/async_shader_compilation"),
               value.asyncShaders);
  out.setValue(QStringLiteral("graphics/vulkan_pipeline_creation_threads"),
               value.pipelineThreads);

  out.setValue(QStringLiteral("audio/force_stereo"), value.forceStereo);
  out.setValue(QStringLiteral("audio/max_queued_frames"),
               value.audioQueuedFrames);
  out.setValue(QStringLiteral("audio/xma_worker"), value.xmaWorker);
  out.setValue(QStringLiteral("audio/front_only"), value.frontOnly);
  out.setValue(QStringLiteral("audio/output_gain"), value.outputGain);
  out.setValue(QStringLiteral("audio/highpass_hz"), value.highpassHz);

  out.setValue(QStringLiteral("locale/language_id"), value.languageId);
  out.setValue(QStringLiteral("locale/country_id"), value.countryId);
  out.setValue(QStringLiteral("general/logging"), value.logging);
}

GameSettings GameConfig::load(const QString& dataRoot) {
  QSettings settings(dataRootConfigPath(dataRoot), QSettings::IniFormat);
  return read(settings);
}

bool GameConfig::save(const QString& dataRoot, const GameSettings& value,
                      QString* error) {
  const QString configDirectory =
      QDir(dataRoot).filePath(QStringLiteral("config"));
  if (!QDir().mkpath(configDirectory)) {
    if (error) {
      *error = QStringLiteral("Could not create %1").arg(configDirectory);
    }
    return false;
  }

  QSettings settings(dataRootConfigPath(dataRoot), QSettings::IniFormat);
  write(settings, value);
  settings.sync();
  if (settings.status() != QSettings::NoError) {
    if (error) {
      *error = QStringLiteral("Could not save settings.");
    }
    return false;
  }
  return true;
}

QStringList GameConfig::commandLine(const QString& dataRoot,
                                    const QString& gameRoot,
                                    const GameSettings& value) {
  QStringList result{
      valueArgument("game_data_root", QDir(gameRoot).absolutePath()),
      valueArgument("user_data_root", QDir(dataRoot).absolutePath()),
      valueArgument("resolution_scale",
                    QString::number(value.resolutionScale)),
      valueArgument("swap_post_effect", value.antiAliasing),
      valueArgument("anisotropic_override",
                    QString::number(value.anisotropic)),
      booleanArgument("fullscreen", value.fullscreen),
      booleanArgument("vsync", value.vsync),
      booleanArgument("native_2x_msaa", value.native2xMsaa),
      booleanArgument("async_shader_compilation", value.asyncShaders),
      valueArgument("vulkan_pipeline_creation_threads",
                    QString::number(value.pipelineThreads)),
      valueArgument("render_target_path_vulkan", QStringLiteral("fbo")),
      booleanArgument("vulkan_sparse_shared_memory", false),
      booleanArgument("audio_force_stereo", value.forceStereo),
      valueArgument("audio_maxqframes",
                    QString::number(value.audioQueuedFrames)),
      booleanArgument("xma_worker", value.xmaWorker),
      booleanArgument("audio_front_only", value.frontOnly),
      valueArgument("audio_output_gain",
                    QString::number(value.outputGain, 'f', 2)),
      valueArgument("audio_highpass_hz", QString::number(value.highpassHz)),
      valueArgument("user_language", QString::number(value.languageId)),
      valueArgument("user_country", QString::number(value.countryId)),
      valueArgument("log_level",
                    value.logging ? QStringLiteral("info")
                                  : QStringLiteral("off")),
      valueArgument("log_file",
                    QDir(dataRoot).filePath(QStringLiteral("logs/dantes_inferno.log"))),
      valueArgument("storage_root", QDir(dataRoot).absolutePath()),
  };
  return result;
}

}  // namespace dantes::launcher
