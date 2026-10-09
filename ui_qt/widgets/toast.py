"""右下角 Toast 通知，带滑入滑出动画。"""
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint,
)
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout

from ui_qt.theme import theme


class Toast(QWidget):
    _stack = []

    def __init__(self, parent, message, kind="info", duration=3000):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool
                            | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        color_key = {
            "info": "accent", "ok": "green",
            "warn": "orange", "error": "red",
        }.get(kind, "accent")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(message)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: #ffffff; font-size: 13px; "
            f"background-color: {theme.c(color_key)}; "
            f"padding: 12px 18px; border-radius: 8px;")
        layout.addWidget(lbl)

        self.setStyleSheet("background: transparent;")
        self.adjustSize()
        self.setFixedWidth(min(420, self.width()))

        Toast._stack.append(self)

        QTimer.singleShot(0, self._show_animated)

    def _show_animated(self):
        self._reposition()
        self.show()

        # 滑入动画
        final_pos = self.pos()
        start_pos = QPoint(final_pos.x() + 40, final_pos.y())
        self.move(start_pos)

        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(220)
        self._anim.setStartValue(start_pos)
        self._anim.setEndValue(final_pos)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

        QTimer.singleShot(3000, self._close_animated)

    def _reposition(self):
        parent = self.parent()
        if parent is None:
            return
        pr = parent.rect()
        idx = Toast._stack.index(self)
        x = parent.mapToGlobal(pr.topRight()).x() - self.width() - 24
        y = parent.mapToGlobal(pr.topRight()).y() + 80 + idx * 76
        self.move(x, y)

    def _close_animated(self):
        try:
            Toast._stack.remove(self)
        except ValueError:
            pass

        final_pos = self.pos()
        end_pos = QPoint(final_pos.x() + 40, final_pos.y())

        self._close_anim = QPropertyAnimation(self, b"pos", self)
        self._close_anim.setDuration(180)
        self._close_anim.setStartValue(final_pos)
        self._close_anim.setEndValue(end_pos)
        self._close_anim.setEasingCurve(QEasingCurve.InCubic)

        def done():
            # 重排其它 toast
            for i, t in enumerate(Toast._stack):
                try:
                    t._reposition()
                except Exception:
                    pass
            self.close()
            self.deleteLater()

        self._close_anim.finished.connect(done)
        self._close_anim.start()