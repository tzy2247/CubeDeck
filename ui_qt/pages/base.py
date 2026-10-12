"""页面基类。"""
from PySide6.QtWidgets import QWidget


class BasePage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._cancelled = False

    def on_show(self):
        """页面显示时调用。子类可覆盖。"""
        pass

    def cancel(self):
        """
        页面即将被销毁时调用（例如主题切换、程序退出）。
        子类应在异步 worker 里检查 self._cancelled 再 emit。
        """
        self._cancelled = True

    def reset_cancelled(self):
        """重新进入页面时清除取消标志。"""
        self._cancelled = False