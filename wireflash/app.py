"""Arranque de la aplicacion Qt."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .controller.mainwindow import MainWindow
from .view.theme import THEMES, saved_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("WireFlash")
    app.setOrganizationName("WireFlash")
    app.setStyleSheet(THEMES[saved_theme()]["qss"])
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
