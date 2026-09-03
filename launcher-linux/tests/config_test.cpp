#include "game_config.h"
#include "import_service.h"

#include <QFile>
#include <QTemporaryDir>
#include <QtTest>

using dantes::launcher::GameConfig;
using dantes::launcher::GameSettings;
using dantes::launcher::ImportService;

class LauncherConfigTest final : public QObject {
  Q_OBJECT

 private slots:
  void savesAndLoadsSettings();
  void buildsQuotedSafeArguments();
  void copiesExtractedGame();
  void rejectsFolderWithoutXex();
};

void LauncherConfigTest::savesAndLoadsSettings() {
  QTemporaryDir root;
  QVERIFY(root.isValid());
  GameSettings expected;
  expected.languageId = 5;
  expected.countryId = 31;
  expected.outputGain = 0.65;
  expected.resolutionScale = 2;

  QString error;
  QVERIFY2(GameConfig::save(root.path(), expected, &error),
           qPrintable(error));
  const GameSettings actual = GameConfig::load(root.path());
  QCOMPARE(actual.languageId, 5);
  QCOMPARE(actual.countryId, 31);
  QCOMPARE(actual.outputGain, 0.65);
  QCOMPARE(actual.resolutionScale, 2);
}

void LauncherConfigTest::buildsQuotedSafeArguments() {
  GameSettings settings;
  settings.languageId = 5;
  const QString dataRoot = QStringLiteral("/tmp/Dante's Inferno Data");
  const QString gameRoot = QStringLiteral("/tmp/Dante's Inferno Game");
  const QStringList arguments =
      GameConfig::commandLine(dataRoot, gameRoot, settings);
  QVERIFY(arguments.contains(
      QStringLiteral("--game_data_root=/tmp/Dante's Inferno Game")));
  QVERIFY(arguments.contains(
      QStringLiteral("--user_data_root=/tmp/Dante's Inferno Data")));
  QVERIFY(arguments.contains(QStringLiteral("--user_language=5")));
  for (const QString& argument : arguments) {
    QVERIFY(!argument.contains(QLatin1Char('"')));
  }
}

void LauncherConfigTest::copiesExtractedGame() {
  QTemporaryDir source;
  QTemporaryDir root;
  QVERIFY(source.isValid());
  QVERIFY(root.isValid());

  QFile xex(source.filePath(QStringLiteral("default.xex")));
  QVERIFY(xex.open(QIODevice::WriteOnly));
  xex.write("XEX2");
  xex.close();
  QFile asset(source.filePath(QStringLiteral("bigfile0.viv")));
  QVERIFY(asset.open(QIODevice::WriteOnly));
  asset.write("asset");
  asset.close();

  const auto result = ImportService::copyExtracted(
      source.path(), root.path(),
      [](qint64, qint64, const QString&) { return true; });
  QVERIFY2(result.success, qPrintable(result.error));
  QVERIFY(ImportService::hasValidGame(root.path()));
  QVERIFY(QFileInfo::exists(root.filePath(QStringLiteral("bigfile0.viv"))));
}

void LauncherConfigTest::rejectsFolderWithoutXex() {
  QTemporaryDir source;
  QTemporaryDir root;
  const auto result = ImportService::copyExtracted(
      source.path(), root.path(),
      [](qint64, qint64, const QString&) { return true; });
  QVERIFY(!result.success);
}

QTEST_MAIN(LauncherConfigTest)
#include "config_test.moc"
