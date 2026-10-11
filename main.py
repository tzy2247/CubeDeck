"""CubeDeck 启动入口（PySide6 版本）。"""
import sys
import os
import gc

# 预导入 netrc，规避 Python 3.12 + requests 惰性导入 netrc 的 GC abort
import netrc  # noqa: F401

from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from ui_qt.main_window import MainWindow
from core import paths


def run():
    import faulthandler
    faulthandler.enable()

    paths.ensure_userdata_root()

    app = QApplication(sys.argv)
    app.setApplicationName("CubeDeck")

    # ★ 完全禁用 Python GC（自动 + 手动都不要）
    #    Python 3.12 + PySide6/shiboken 环境下，GC 遍历对象时会与
    #    其他线程里的 C 扩展状态冲突，触发 access violation。
    #    依赖 Qt parent-child 与 Python 引用计数管理内存。
    gc.disable()

    # 图标
    icon_path = Path("icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()