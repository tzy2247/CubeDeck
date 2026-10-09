"""页面基类。"""
from PySide6.QtWidgets import QWidget


class BasePage(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state

    def on_show(self):
        """切到本页时调用，子类可覆盖。"""
        pass

    def on_server_started(self):
        pass

    def on_server_stopped(self):
        pass

    def on_rcon_connected(self):
        pass