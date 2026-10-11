"""CubeDeck 启动入口（PySide6 版本）。"""
import sys
import os
import io
import gc

# 预导入 netrc，规避 Python 3.12 + requests 惰性导入 netrc 的 GC abort
import netrc  # noqa: F401

from pathlib import Path


# ============================================================
#  ★ 兜底 stdout / stderr
#  无控制台模式（pythonw / PyInstaller console=False）下
#  sys.stdout 和 sys.stderr 会是 None，导致任何 print 或
#  faulthandler.enable() 崩溃。
# ============================================================
def _ensure_std_streams():
    if sys.stdout is None:
        sys.stdout = io.TextIOWrapper(
            io.BytesIO(), encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = io.TextIOWrapper(
            io.BytesIO(), encoding="utf-8", errors="replace")


_ensure_std_streams()


from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import QTimer

from ui_qt.main_window import MainWindow
from core import paths


def run():
    # faulthandler 需要 stderr，放在 _ensure_std_streams 之后
    import faulthandler
    try:
        faulthandler.enable()
    except Exception:
        pass

    paths.ensure_userdata_root()

    app = QApplication(sys.argv)
    app.setApplicationName("CubeDeck")

    # ★ 完全禁用 Python GC（Python 3.12 + PySide6 会有 access violation）
    gc.disable()

    # 图标
    try:
        icon_path = Path("icon.ico")
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
    except Exception:
        pass

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()