#include "import_service.h"

#include <QCoreApplication>
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QProcess>
#include <QStandardPaths>
#include <QStorageInfo>
#include <QUuid>

namespace dantes::launcher {
namespace {

ImportResult failure(const QString& error, bool cancelled = false) {
  return {.success = false, .cancelled = cancelled, .error = error};
}

qint64 treeSize(const QString& path) {
  qint64 size = 0;
  QDirIterator iterator(path, QDir::Files | QDir::NoSymLinks,
                        QDirIterator::Subdirectories);
  while (iterator.hasNext()) {
    iterator.next();
    size += iterator.fileInfo().size();
  }
  return size;
}

bool copyTree(const QString& source, const QString& destination, qint64 total,
              const ProgressCallback& progress, QString* error) {
  const QDir sourceDirectory(source);
  if (!QDir().mkpath(destination)) {
    *error = QStringLiteral("Could not create %1").arg(destination);
    return false;
  }

  qint64 copied = 0;
  QDirIterator iterator(source, QDir::Dirs | QDir::Files | QDir::NoDotAndDotDot |
                                    QDir::NoSymLinks,
                        QDirIterator::Subdirectories);
  while (iterator.hasNext()) {
    const QString sourcePath = iterator.next();
    const QFileInfo info(sourcePath);
    const QString relative = sourceDirectory.relativeFilePath(sourcePath);
    const QString destinationPath = QDir(destination).filePath(relative);

    if (info.isDir()) {
      if (!QDir().mkpath(destinationPath)) {
        *error = QStringLiteral("Could not create %1").arg(destinationPath);
        return false;
      }
      continue;
    }

    QDir().mkpath(QFileInfo(destinationPath).absolutePath());
    QFile::remove(destinationPath);
    if (!QFile::copy(sourcePath, destinationPath)) {
      *error = QStringLiteral("Could not copy %1").arg(relative);
      return false;
    }
    copied += info.size();
    if (progress && !progress(copied, total, relative)) {
      *error = QStringLiteral("Import cancelled.");
      return false;
    }
  }
  return true;
}

}  // namespace

QString ImportService::defaultXexPath(const QString& gameRoot) {
  return QDir(gameRoot).filePath(QStringLiteral("default.xex"));
}

bool ImportService::hasValidGame(const QString& gameRoot) {
  const QFileInfo xex(defaultXexPath(gameRoot));
  return xex.isFile() && xex.size() > 0;
}

QString ImportService::temporaryPath(const QString& gameRoot) {
  const QString parent =
      QFileInfo(QDir(gameRoot).absolutePath()).absolutePath();
  return QDir(parent).filePath(
      QStringLiteral(".game-import-%1")
          .arg(QUuid::createUuid().toString(QUuid::WithoutBraces)));
}

ImportResult ImportService::commit(const QString& temporary,
                                   const QString& gameRoot) {
  const QString xex = QDir(temporary).filePath(QStringLiteral("default.xex"));
  if (!QFileInfo::exists(xex)) {
    QDir(temporary).removeRecursively();
    return failure(
        QStringLiteral("The import does not contain a default.xex file."));
  }

  const QString destination = QDir(gameRoot).absolutePath();
  QString backup;
  if (QFileInfo::exists(destination)) {
    backup = QDir(QFileInfo(destination).absolutePath()).filePath(
        QStringLiteral(".game-backup-%1")
            .arg(QUuid::createUuid().toString(QUuid::WithoutBraces)));
    if (!QDir().rename(destination, backup)) {
      return failure(
          QStringLiteral("Could not prepare the existing game folder."));
    }
  }
  if (!QDir().rename(temporary, destination)) {
    if (!backup.isEmpty()) {
      QDir().rename(backup, destination);
    }
    return failure(QStringLiteral("Could not finish the import."));
  }
  if (!backup.isEmpty()) {
    QDir(backup).removeRecursively();
  }
  return {.success = true};
}

ImportResult ImportService::copyExtracted(
    const QString& source, const QString& gameRoot,
    const ProgressCallback& progress) {
  const QFileInfo sourceXex(QDir(source).filePath(QStringLiteral("default.xex")));
  if (!sourceXex.isFile()) {
    return failure(QStringLiteral(
        "The selected folder does not contain default.xex in its root."));
  }

  const QString parent = QFileInfo(QDir(gameRoot).absolutePath()).absolutePath();
  if (!QDir().mkpath(parent)) {
    return failure(QStringLiteral("Could not create the selected folder."));
  }

  const qint64 total = treeSize(source);
  const QStorageInfo storage(parent);
  if (storage.isValid() && storage.bytesAvailable() < total) {
    return failure(QStringLiteral("There is not enough free space."));
  }

  const QString temporary = temporaryPath(gameRoot);
  QString error;
  if (!copyTree(source, temporary, total, progress, &error)) {
    QDir(temporary).removeRecursively();
    return failure(error, error == QStringLiteral("Import cancelled."));
  }
  return commit(temporary, gameRoot);
}

QString ImportService::findExtractor() {
  const QDir app(QCoreApplication::applicationDirPath());
  const QStringList candidates{
      qEnvironmentVariable("DANTES_EXTRACT_XISO"),
      app.filePath(QStringLiteral("extract-xiso")),
      app.filePath(QStringLiteral("../libexec/extract-xiso")),
      QStandardPaths::findExecutable(QStringLiteral("extract-xiso")),
  };
  for (const QString& candidate : candidates) {
    const QFileInfo info(candidate);
    if (!candidate.isEmpty() && info.isFile() && info.isExecutable()) {
      return info.absoluteFilePath();
    }
  }
  return {};
}

ImportResult ImportService::extractIso(const QString& isoPath,
                                       const QString& gameRoot,
                                       const QString& extractor,
                                       const ProgressCallback& progress) {
  const QFileInfo iso(isoPath);
  if (!iso.isFile()) {
    return failure(QStringLiteral("The selected ISO was not found."));
  }
  if (extractor.isEmpty()) {
    return failure(QStringLiteral(
        "extract-xiso was not found for Linux ARM64."));
  }
  const QString parent = QFileInfo(QDir(gameRoot).absolutePath()).absolutePath();
  if (!QDir().mkpath(parent)) {
    return failure(QStringLiteral("Could not create the selected folder."));
  }

  const QStorageInfo storage(parent);
  if (storage.isValid() && storage.bytesAvailable() < iso.size()) {
    return failure(QStringLiteral("There is not enough free space."));
  }

  const QString temporary = temporaryPath(gameRoot);
  QDir().mkpath(temporary);

  QProcess process;
  process.setProcessChannelMode(QProcess::MergedChannels);
  process.start(extractor,
                {QStringLiteral("-x"), QStringLiteral("-d"), temporary,
                 QStringLiteral("-s"), iso.absoluteFilePath()});
  if (!process.waitForStarted()) {
    QDir(temporary).removeRecursively();
    return failure(QStringLiteral("Could not start extract-xiso: %1")
                       .arg(process.errorString()));
  }

  while (process.state() != QProcess::NotRunning) {
    process.waitForReadyRead(100);
    const QString output =
        QString::fromLocal8Bit(process.readAll()).trimmed();
    if (progress && !progress(0, 0, output)) {
      process.kill();
      process.waitForFinished();
      QDir(temporary).removeRecursively();
      return failure(QStringLiteral("Extraction cancelled."), true);
    }
    QCoreApplication::processEvents();
  }

  const QString finalOutput =
      QString::fromLocal8Bit(process.readAll()).trimmed();
  if (process.exitStatus() != QProcess::NormalExit ||
      process.exitCode() != 0) {
    QDir(temporary).removeRecursively();
    return failure(
        QStringLiteral("extract-xiso failed with error (%1).\n%2")
            .arg(process.exitCode())
            .arg(finalOutput));
  }
  return commit(temporary, gameRoot);
}

}  // namespace dantes::launcher
