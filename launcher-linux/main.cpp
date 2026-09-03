#include "main_window.h"

#include <QApplication>
#include <QCoreApplication>

int main(int argc, char** argv) {
  QApplication application(argc, argv);
  QCoreApplication::setOrganizationName(QStringLiteral("HellsGateRecomp"));
  QCoreApplication::setApplicationName(QStringLiteral("DantesInfernoLauncher"));
  QCoreApplication::setApplicationVersion(
      QStringLiteral(DANTES_LAUNCHER_VERSION));

  dantes::launcher::MainWindow window;
  window.show();
  return application.exec();
}
