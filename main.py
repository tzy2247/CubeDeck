"""CubeDeck 启动入口（PySide6 版本）。"""
import sys
import os
import io
import gc
from pathlib import Path

# 预导入 netrc，规避 Python 3.12 + requests 惰性导入 netrc 的 GC abort
import netrc  # noqa: F401


# ============================================================
#  兜底 stdout / stderr
# ============================================================
def _ensure_std_streams():
    if sys.stdout is None:
        sys.stdout = io.TextIOWrapper(
            io.BytesIO(), encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = io.TextIOWrapper(
            io.BytesIO(), encoding="utf-8", errors="replace")


_ensure_std_streams()


# ============================================================
#  ★ 资源路径解析（打包 / 开发环境通用）
# ============================================================
def resource_path(relative: str) -> str:
    """
    获取资源的绝对路径。
    - 打包后：从 sys._MEIPASS 取
    - 开发时：从项目根目录取
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        # 未打包：以 main.py 所在目录为根
        base = os.path.dirname(os.path.abspath(__file__))
    return str(Path(base) / relative)


from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from ui_qt.main_window import MainWindow
from core import paths


def run():
    import faulthandler
    try:
        faulthandler.enable()
    except Exception:
        pass

    paths.ensure_userdata_root()

    app = QApplication(sys.argv)
    app.setApplicationName("CubeDeck")

    # ★ 用 resource_path 解析图标路径
    try:
        icon_path = resource_path("icon.ico")
        if Path(icon_path).exists():
            app.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass

    gc.disable()

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()