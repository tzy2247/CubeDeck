"""CubeDeck 启动入口（PySide6 版本）。"""
import sys

from PySide6.QtWidgets import QApplication

from ui_qt.main_window import MainWindow
from core import paths


def run():
    paths.ensure_userdata_root()

    app = QApplication(sys.argv)
    app.setApplicationName("CubeDeck")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()