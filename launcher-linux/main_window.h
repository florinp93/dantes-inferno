#pragma once

#include "game_config.h"

#include <QMainWindow>

class QCheckBox;
class QComboBox;
class QLabel;
class QPushButton;
class QSlider;
class QSpinBox;

namespace dantes::launcher {

class MainWindow final : public QMainWindow {
  Q_OBJECT

 public:
  explicit MainWindow(QWidget* parent = nullptr);

 private slots:
  void chooseDataRoot();
  void chooseGameRoot();
  void importIso();
  void saveSettings();
  void resetSettings();
  void play();
  void openLogs();

 private:
  QWidget* createPlayPage();
  QWidget* createSettingsPage();
  QWidget* createGraphicsPage();
  QWidget* createAudioPage();
  QWidget* createLocalePage();
  bool runFirstSetup();
  bool performImport(const QString& isoPath);
  bool confirmReplaceGame();
  QString gameExecutable() const;
  void loadSettings();
  GameSettings collectSettings() const;
  void applySettings(const GameSettings& settings);
  void updateStatus();
  bool setDataRoot(const QString& root);
  void setGameRoot(const QString& root);

  QString dataRoot_;
  QString gameRoot_;
  QLabel* dataRootLabel_ = nullptr;
  QLabel* gameRootLabel_ = nullptr;
  QLabel* statusLabel_ = nullptr;
  QPushButton* playButton_ = nullptr;
  QPushButton* importIsoButton_ = nullptr;

  QComboBox* resolutionScale_ = nullptr;
  QComboBox* antiAliasing_ = nullptr;
  QComboBox* anisotropic_ = nullptr;
  QCheckBox* fullscreen_ = nullptr;
  QCheckBox* vsync_ = nullptr;
  QCheckBox* nativeMsaa_ = nullptr;
  QCheckBox* asyncShaders_ = nullptr;
  QSpinBox* pipelineThreads_ = nullptr;

  QCheckBox* forceStereo_ = nullptr;
  QSpinBox* queuedFrames_ = nullptr;
  QCheckBox* xmaWorker_ = nullptr;
  QCheckBox* frontOnly_ = nullptr;
  QSlider* outputGain_ = nullptr;
  QLabel* outputGainLabel_ = nullptr;
  QSpinBox* highpassHz_ = nullptr;

  QComboBox* language_ = nullptr;
  QSpinBox* country_ = nullptr;
  QCheckBox* logging_ = nullptr;
};

}  // namespace dantes::launcher
