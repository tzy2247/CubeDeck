"""自绘折线图（零依赖，跟随主题）。"""
from collections import deque

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath, QFont
from PySide6.QtWidgets import QWidget

from ui_qt.theme import theme


class LineChart(QWidget):
    def __init__(self, max_points=60, y_max=20, color_key="accent",
                 y_suffix="", parent=None):
        super().__init__(parent)
        self.setMinimumHeight(160)

        self.max_points = max_points
        self.y_max = float(y_max)
        self.color_key = color_key
        self.y_suffix = y_suffix
        self.data = deque([0.0] * max_points, maxlen=max_points)

    def push(self, value):
        try:
            v = float(value)
        except Exception:
            v = 0.0
        self.data.append(v)
        self.update()

    def clear(self):
        self.data = deque([0.0] * self.max_points,
                          maxlen=self.max_points)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        pad_left = 44
        pad_right = 12
        pad_top = 14
        pad_bottom = 24
        plot_w = w - pad_left - pad_right
        plot_h = h - pad_top - pad_bottom
        if plot_w <= 10 or plot_h <= 10:
            return

        border_c = QColor(theme.c("border"))
        faint_c = QColor(theme.c("text_faint"))
        dim_c = QColor(theme.c("text_dim"))
        text_c = QColor(theme.c("text"))
        line_c = QColor(theme.c(self.color_key))

        # ---- 网格 + Y 轴刻度 ----
        grid = 4
        painter.setFont(QFont("Consolas", 8))
        for i in range(grid + 1):
            y = pad_top + plot_h * i / grid
            pen = QPen(border_c, 1, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(pad_left, int(y),
                             pad_left + plot_w, int(y))

            val = self.y_max * (1 - i / grid)
            if self.y_suffix.strip() == "MB":
                label = f"{val:.0f}"
            else:
                label = f"{val:.1f}"
            painter.setPen(faint_c)
            painter.drawText(0, int(y - 6), pad_left - 6, 12,
                             Qt.AlignRight | Qt.AlignVCenter, label)

        # ---- 数据折线 ----
        pts = list(self.data)
        if len(pts) >= 2:
            path = QPainterPath()
            for i, v in enumerate(pts):
                x = pad_left + plot_w * i / (self.max_points - 1)
                ratio = 0.0
                if self.y_max > 0:
                    ratio = min(max(v / self.y_max, 0.0), 1.0)
                y = pad_top + plot_h * (1 - ratio)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)

            painter.setPen(QPen(line_c, 2, Qt.SolidLine,
                                Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)

        # ---- X 轴底部线 ----
        painter.setPen(QPen(border_c, 1))
        painter.drawLine(pad_left, pad_top + plot_h,
                         pad_left + plot_w, pad_top + plot_h)

        # ---- X 轴标签 ----
        painter.setPen(faint_c)
        painter.drawText(pad_left, pad_top + plot_h + 4,
                         100, 18, Qt.AlignLeft | Qt.AlignVCenter,
                         "2 分钟前")
        painter.drawText(pad_left + plot_w - 100, pad_top + plot_h + 4,
                         100, 18, Qt.AlignRight | Qt.AlignVCenter,
                         "现在")

        # ---- 最新值 ----
        if pts:
            last = pts[-1]
            if self.y_suffix.strip() == "MB":
                text = f"{last:.0f}{self.y_suffix}"
            else:
                text = f"{last:.1f}{self.y_suffix}"
            painter.setFont(QFont("Consolas", 11, QFont.Bold))
            painter.setPen(line_c)
            painter.drawText(pad_left + plot_w - 120, pad_top,
                             120, 20, Qt.AlignRight | Qt.AlignTop,
                             text)

        painter.end()