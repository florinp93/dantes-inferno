#pragma once

#include <QString>

#include <functional>

namespace dantes::launcher {

struct ImportResult {
  bool success = false;
  bool cancelled = false;
  QString error;
};

using ProgressCallback =
    std::function<bool(qint64 completed, qint64 total, const QString& detail)>;

class ImportService {
 public:
  static bool hasValidGame(const QString& gameRoot);
  static QString defaultXexPath(const QString& gameRoot);

  static ImportResult copyExtracted(const QString& source,
                                    const QString& gameRoot,
                                    const ProgressCallback& progress);
  static ImportResult extractIso(const QString& isoPath,
                                 const QString& gameRoot,
                                 const QString& extractor,
                                 const ProgressCallback& progress);
  static QString findExtractor();

 private:
  static QString temporaryPath(const QString& gameRoot);
  static ImportResult commit(const QString& temporary,
                             const QString& gameRoot);
};

}  // namespace dantes::launcher
