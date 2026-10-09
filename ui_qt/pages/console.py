"""控制台：多色日志 + 过滤 + 指令输入。"""
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QPlainTextEdit, QButtonGroup, QWidget,
)

from ui_qt.theme import theme
from ui_qt.pages.base import BasePage


FILTER_MODES = {
    "全部": None,
    "玩家": {"player", "player_cmd"},
    "错误": {"error", "warn"},
    "RCON": {"cmd", "rcon"},
    "服务器": {"server"},
    "管理器": {"ok", "info"},
}

TAG_COLORS = {
    "time": "#5d6577",
    "info": "#c8d0e0",
    "cmd": "#7dd3fc",
    "rcon": "#93c5fd",
    "player": "#a78bfa",
    "player_cmd": "#c084fc",
    "error": "#f87171",
    "warn": "#fbbf24",
    "ok": "#4ade80",
    "server": "#9aa4bb",
}


class ConsolePage(BasePage):
    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self._entries = deque(maxlen=3000)
        self._filter = "全部"
        self._history = []
        self._history_idx = -1

        self._build()

        state.log_message.connect(self._on_log)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # ---- 顶部过滤栏 ----
        top = QHBoxLayout()
        top.setSpacing(6)

        self._filter_buttons = {}
        for name in FILTER_MODES:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _=False, n=name: self._set_filter(n))
            self._filter_buttons[name] = btn
            top.addWidget(btn)

        top.addStretch()

        self._count_label = QLabel("0 条")
        self._count_label.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px;")
        top.addWidget(self._count_label)

        clear_btn = QPushButton("清空")
        clear_btn.setObjectName("Danger")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear_all)
        top.addWidget(clear_btn)

        root.addLayout(top)

        self._update_filter_styles()

        # ---- 日志正文 ----
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Consolas", 10))
        self._text.setStyleSheet(
            f"QPlainTextEdit {{ "
            f"background-color: {theme.c('console_bg')}; "
            f"color: {theme.c('text')}; "
            f"border: 1px solid {theme.c('border')}; "
            f"border-radius: 10px; padding: 8px; }}")
        root.addWidget(self._text, 1)

        # ---- 输入行 ----
        row = QHBoxLayout()
        row.setSpacing(8)

        self._entry = QLineEdit()
        self._entry.setPlaceholderText(
            "输入服务器指令，按 Enter 发送（↑/↓ 翻历史）")
        self._entry.setFixedHeight(40)
        self._entry.returnPressed.connect(self._send)
        self._entry.installEventFilter(self)
        row.addWidget(self._entry, 1)

        send_btn = QPushButton("发送")
        send_btn.setObjectName("Accent")
        send_btn.setFixedSize(90, 40)
        send_btn.clicked.connect(self._send)
        row.addWidget(send_btn)

        clear_view_btn = QPushButton("清空")
        clear_view_btn.setObjectName("Ghost")
        clear_view_btn.setFixedSize(72, 40)
        clear_view_btn.clicked.connect(self._text.clear)
        row.addWidget(clear_view_btn)

        root.addLayout(row)

    # ========================================================
    #  事件过滤：上下键翻历史
    # ========================================================
    def eventFilter(self, obj, event):
        if obj is self._entry and event.type() == event.Type.KeyPress:
            key = event.key()
            if key == Qt.Key_Up:
                self._hist_up()
                return True
            if key == Qt.Key_Down:
                self._hist_down()
                return True
        return super().eventFilter(obj, event)

    def _hist_up(self):
        if not self._history:
            return
        if self._history_idx == -1:
            self._history_idx = len(self._history) - 1
        elif self._history_idx > 0:
            self._history_idx -= 1
        self._entry.setText(self._history[self._history_idx])

    def _hist_down(self):
        if not self._history or self._history_idx == -1:
            return
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self._entry.setText(self._history[self._history_idx])
        else:
            self._history_idx = -1
            self._entry.clear()

    # ========================================================
    #  过滤
    # ========================================================
    def _set_filter(self, name):
        if name == self._filter:
            return
        self._filter = name
        self._update_filter_styles()
        self._render()

    def _update_filter_styles(self):
        for name, btn in self._filter_buttons.items():
            active = name == self._filter
            if active:
                btn.setStyleSheet(
                    f"QPushButton {{ "
                    f"background-color: {theme.c('accent')}; "
                    f"color: #ffffff; border: none; "
                    f"border-radius: 6px; padding: 0 12px; }}")
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ "
                    f"background-color: transparent; "
                    f"color: {theme.c('text_dim')}; "
                    f"border: 1px solid {theme.c('border')}; "
                    f"border-radius: 6px; padding: 0 12px; }}"
                    f"QPushButton:hover {{ "
                    f"background-color: {theme.c('card_hover')}; "
                    f"color: {theme.c('text')}; }}")
            btn.setChecked(active)

    def _render(self):
        self._text.clear()
        allowed = FILTER_MODES.get(self._filter)

        shown = 0
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.End)

        for ts, msg, tag in self._entries:
            if allowed is not None and tag not in allowed:
                continue
            self._append_line(cursor, ts, msg, tag)
            shown += 1

        total = len(self._entries)
        if allowed is None:
            self._count_label.setText(f"{total} 条")
        else:
            self._count_label.setText(f"{shown} / {total} 条")

        self._text.verticalScrollBar().setValue(
            self._text.verticalScrollBar().maximum())

    def _append_line(self, cursor, ts, msg, tag):
        # 时间戳
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(TAG_COLORS.get("time", "#5d6577")))
        cursor.insertText(f"[{ts}] ", fmt)

        # 内容
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(TAG_COLORS.get(tag, "#c8d0e0")))
        cursor.insertText(f"{msg}\n", fmt)

    # ========================================================
    #  日志追加
    # ========================================================
    def _on_log(self, msg, tag):
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._entries.append((ts, msg, tag))

        allowed = FILTER_MODES.get(self._filter)
        if allowed is not None and tag not in allowed:
            total = len(self._entries)
            shown = sum(1 for _, _, t in self._entries if t in allowed)
            self._count_label.setText(f"{shown} / {total} 条")
            return

        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._append_line(cursor, ts, msg, tag)
        self._text.setTextCursor(cursor)
        self._text.verticalScrollBar().setValue(
            self._text.verticalScrollBar().maximum())

        # 限制行数
        if self._text.blockCount() > 3000:
            c2 = self._text.textCursor()
            c2.movePosition(QTextCursor.Start)
            c2.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 500)
            c2.removeSelectedText()

        total = len(self._entries)
        if allowed is None:
            self._count_label.setText(f"{total} 条")
        else:
            shown = sum(1 for _, _, t in self._entries if t in allowed)
            self._count_label.setText(f"{shown} / {total} 条")

    def _clear_all(self):
        self._entries.clear()
        self._text.clear()
        self._count_label.setText("0 条")

    # ========================================================
    #  发送
    # ========================================================
    def _send(self):
        cmd = self._entry.text().strip()
        if not cmd:
            return
        self._entry.clear()

        if not self._history or self._history[-1] != cmd:
            self._history.append(cmd)
            if len(self._history) > 100:
                self._history.pop(0)
        self._history_idx = -1

        if cmd.lower().lstrip("/").strip() == "stop":
            if self.state.is_running:
                self.state.log(f"> {cmd}", "cmd")
                self.state.stop_server()
            else:
                self.state.log("服务器未运行", "warn")
            return

        self.state.quick_rcon(cmd)