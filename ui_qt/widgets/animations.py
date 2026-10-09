"""动画工具：淡入、滑入、数字滚动、脉冲、列表错开。"""
from PySide6.QtCore import (
    Qt, QObject, QPropertyAnimation, QEasingCurve, QPoint, QTimer,
    Property, QParallelAnimationGroup, Signal,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect, QWidget, QLabel, QScrollArea,
)


# ============================================================
#  1. 淡入
# ============================================================
def fade_in(widget, duration=180, delay=0):
    """让 widget 从透明到不透明。"""
    def start():
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", widget)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        # 动画结束后移除 effect，避免影响后续渲染
        def cleanup():
            try:
                widget.setGraphicsEffect(None)
            except Exception:
                pass

        anim.finished.connect(cleanup)
        widget._fade_anim = anim
        anim.start()

    if delay > 0:
        QTimer.singleShot(delay, start)
    else:
        start()


# ============================================================
#  2. 滑入（从下方或右侧）
# ============================================================
def slide_in(widget, direction="up", distance=24, duration=240, delay=0):
    """
    让 widget 从偏移位置滑到原位。
    direction: up / down / left / right
    """
    def start():
        final_pos = widget.pos()
        if direction == "up":
            start_pos = final_pos + QPoint(0, distance)
        elif direction == "down":
            start_pos = final_pos - QPoint(0, distance)
        elif direction == "left":
            start_pos = final_pos + QPoint(distance, 0)
        else:  # right
            start_pos = final_pos - QPoint(distance, 0)

        widget.move(start_pos)

        anim = QPropertyAnimation(widget, b"pos", widget)
        anim.setDuration(duration)
        anim.setStartValue(start_pos)
        anim.setEndValue(final_pos)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        widget._slide_anim = anim
        anim.start()

    if delay > 0:
        QTimer.singleShot(delay, start)
    else:
        start()


# ============================================================
#  3. 组合：淡入 + 滑入
# ============================================================
def appear(widget, direction="up", distance=20,
           duration=280, delay=0):
    """淡入 + 滑入，一起执行。"""
    fade_in(widget, duration=duration, delay=delay)
    slide_in(widget, direction=direction, distance=distance,
             duration=duration, delay=delay)


# ============================================================
#  4. 错开：多个 widget 依次出现
# ============================================================
def stagger_appear(widgets, direction="up", distance=20,
                   duration=260, step=60, initial_delay=0):
    """让一组 widget 依次出现（每个延迟 step ms）。"""
    for i, w in enumerate(widgets):
        appear(w, direction=direction, distance=distance,
               duration=duration, delay=initial_delay + i * step)


# ============================================================
#  5. 数字滚动
# ============================================================
class NumberCounter(QObject):
    """
    让 QLabel 显示的数字平滑变化到目标值。
    支持整数和小数，自动保留格式。
    """
    finished = Signal()

    def __init__(self, label: QLabel, duration=400):
        super().__init__(label)
        self.label = label
        self.duration = duration
        self._anim = None

    def animate_to(self, target: float, fmt="{:.0f}", suffix=""):
        # 停止旧动画
        if self._anim:
            try:
                self._anim.stop()
            except Exception:
                pass

        try:
            text = self.label.text()
            import re
            m = re.search(r"[-+]?\d+\.?\d*", text)
            start_val = float(m.group()) if m else 0.0
        except Exception:
            start_val = 0.0

        anim = QPropertyAnimation(self, b"value", self)
        anim.setDuration(self.duration)
        anim.setStartValue(start_val)
        anim.setEndValue(float(target))
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def on_change():
            try:
                v = anim.currentValue()
                self.label.setText(fmt.format(v) + suffix)
            except Exception:
                pass

        anim.valueChanged.connect(on_change)

        def on_end():
            try:
                self.label.setText(fmt.format(target) + suffix)
            except Exception:
                pass
            self.finished.emit()

        anim.finished.connect(on_end)
        self._anim = anim
        anim.start()

    # 供 QPropertyAnimation 使用
    def _get_value(self):
        return getattr(self, "_value", 0.0)

    def _set_value(self, v):
        self._value = v

    value = Property(float, _get_value, _set_value)


# ============================================================
#  6. 脉冲（状态点闪烁）
# ============================================================
def pulse(widget, color_start, color_end, duration=1200):
    """让 widget 的颜色在两个值之间循环。"""
    def start():
        anim = QPropertyAnimation(widget, b"windowOpacity", widget)
        anim.setDuration(duration)
        anim.setStartValue(1.0)
        anim.setKeyValueAt(0.5, 0.4)
        anim.setEndValue(1.0)
        anim.setLoopCount(-1)   # 无限循环
        anim.setEasingCurve(QEasingCurve.InOutSine)
        widget._pulse_anim = anim
        anim.start()

    start()


def stop_pulse(widget):
    try:
        if hasattr(widget, "_pulse_anim"):
            widget._pulse_anim.stop()
    except Exception:
        pass


# ============================================================
#  7. 按钮按压缩放
# ============================================================
def install_press_effect(button, scale=0.97):
    """给按钮加按压缩放反馈。"""
    from PySide6.QtWidgets import QGraphicsScale
    # QGraphicsScale 在这里不好用，改用 QGraphicsOpacityEffect
    # 简化实现：按下时轻微变暗
    def on_press():
        try:
            eff = QGraphicsOpacityEffect(button)
            eff.setOpacity(0.75)
            button.setGraphicsEffect(eff)
        except Exception:
            pass

    def on_release():
        try:
            eff = QGraphicsOpacityEffect(button)
            eff.setOpacity(1.0)
            button.setGraphicsEffect(eff)
            QTimer.singleShot(120, lambda: button.setGraphicsEffect(None))
        except Exception:
            pass

    button.pressed.connect(on_press)
    button.released.connect(on_release)


# ============================================================
#  8. 高度动画（折叠/展开）
# ============================================================
def animate_height(widget, target_height, duration=220):
    """平滑改变 widget 的高度。"""
    start = widget.height()
    if start == target_height:
        return

    anim = QPropertyAnimation(widget, b"maximumHeight", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(target_height)
    anim.setEasingCurve(QEasingCurve.OutCubic)

    def on_end():
        try:
            if target_height <= 0:
                widget.setVisible(False)
        except Exception:
            pass

    anim.finished.connect(on_end)
    widget._height_anim = anim
    if target_height > 0:
        widget.setVisible(True)
    anim.start()