"""AI 助手：配置 + 对话记录。"""
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QCheckBox, QTabWidget, QWidget, QTextEdit, QComboBox,
    QMessageBox, QFrame,
)

from ui_qt.theme import theme
from ui_qt.pages.base import BasePage


class AIPage(BasePage):
    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self._build()
        state.log_message.connect(self._on_log)

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # 顶部
        top = QFrame()
        top.setObjectName("Card")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(16, 12, 16, 12)

        title = QLabel("AI 助手")
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 16px; font-weight: bold;")
        tl.addWidget(title)

        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px;")
        tl.addWidget(self._status)
        tl.addStretch()

        self._enable_cb = QCheckBox("启用 AI")
        self._enable_cb.setChecked(
            bool(self.state.config_data.get("ai_enabled")))
        self._enable_cb.stateChanged.connect(self._toggle_enable)
        tl.addWidget(self._enable_cb)
        root.addWidget(top)

        # Tab
        tabs = QTabWidget()
        tabs.addTab(self._build_config_tab(), "API 配置")
        tabs.addTab(self._build_chat_tab(), "对话设置")
        tabs.addTab(self._build_mod_tab(), "行为审核")
        tabs.addTab(self._build_prompt_tab(), "人设")
        tabs.addTab(self._build_log_tab(), "对话记录")
        root.addWidget(tabs, 1)

    def _build_config_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self._base_url = self._row(layout, "API 网址",
                                    self.state.config_data.get(
                                        "ai_base_url", ""))
        self._api_key = self._row(layout, "API Key",
                                   self.state.config_data.get(
                                       "ai_api_key", ""), password=True)
        self._model = self._row(layout, "模型",
                                 self.state.config_data.get("ai_model", ""))

        row = QHBoxLayout()
        row.addWidget(QLabel("快速填充"))
        for name, url, model in (
            ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
            ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
            ("通义千问",
             "https://dashscope.aliyuncs.com/compatible-mode/v1",
             "qwen-plus"),
        ):
            btn = QPushButton(name)
            btn.setObjectName("Ghost")
            btn.setFixedHeight(32)
            btn.clicked.connect(
                lambda _=False, u=url, m=model: self._preset(u, m))
            row.addWidget(btn)
        row.addStretch()
        layout.addLayout(row)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("保存配置")
        save_btn.setObjectName("Accent")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save_config)
        btn_row.addWidget(save_btn)

        test_btn = QPushButton("测试连接")
        test_btn.setObjectName("Green")
        test_btn.setFixedHeight(40)
        test_btn.clicked.connect(self._test_connection)
        btn_row.addWidget(test_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._test_result = QLabel("")
        self._test_result.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px;")
        layout.addWidget(self._test_result)

        layout.addStretch()
        return w

    def _row(self, parent, label, value, password=False):
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFixedWidth(100)
        row.addWidget(lbl)
        e = QLineEdit(str(value))
        e.setFixedHeight(36)
        if password:
            e.setEchoMode(QLineEdit.Password)
        row.addWidget(e, 1)
        parent.addLayout(row)
        return e

    def _preset(self, url, model):
        self._base_url.setText(url)
        self._model.setText(model)

    def _build_chat_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self._chat_enabled = QCheckBox("允许 AI 回复玩家聊天")
        self._chat_enabled.setChecked(
            bool(self.state.config_data.get("ai_chat_enabled", True)))
        layout.addWidget(self._chat_enabled)

        self._chat_trigger = self._row(
            layout, "触发前缀",
            self.state.config_data.get("ai_chat_trigger", "!"))
        self._chat_cooldown = self._row(
            layout, "冷却(秒)",
            self.state.config_data.get("ai_chat_cooldown", 5))
        self._context_lines = self._row(
            layout, "上下文条数",
            self.state.config_data.get("ai_context_lines", 10))

        save_btn = QPushButton("保存")
        save_btn.setObjectName("Accent")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save_config)
        layout.addWidget(save_btn)

        layout.addStretch()
        return w

    def _build_mod_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self._mod_enabled = QCheckBox("启用玩家行为审核")
        self._mod_enabled.setChecked(
            bool(self.state.config_data.get("ai_moderation_enabled")))
        layout.addWidget(self._mod_enabled)

        self._mod_broadcast = QCheckBox("违规时广播处理结果")
        self._mod_broadcast.setChecked(
            bool(self.state.config_data.get("ai_moderation_broadcast", True)))
        layout.addWidget(self._mod_broadcast)

        self._mod_cooldown = self._row(
            layout, "审核冷却",
            self.state.config_data.get("ai_moderation_cooldown", 3))
        self._global_cooldown = self._row(
            layout, "全局冷却",
            self.state.config_data.get("ai_global_cooldown", 1.0))

        save_btn = QPushButton("保存")
        save_btn.setObjectName("Accent")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save_config)
        layout.addWidget(save_btn)

        layout.addStretch()
        return w

    def _build_prompt_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        layout.addWidget(QLabel(
            "系统提示词（必须要求 AI 返回 JSON："
            "reply / violation / reason）"))

        self._prompt = QTextEdit()
        self._prompt.setPlainText(
            self.state.config_data.get("ai_system_prompt", ""))
        layout.addWidget(self._prompt, 1)

        save_btn = QPushButton("保存人设")
        save_btn.setObjectName("Accent")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save_config)
        layout.addWidget(save_btn)
        return w

    def _build_log_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        layout.addWidget(self._log_text, 1)

        btn_row = QHBoxLayout()
        reload_btn = QPushButton("加载最近 200 条")
        reload_btn.setObjectName("Ghost")
        reload_btn.setFixedHeight(34)
        reload_btn.clicked.connect(self._reload_history)
        btn_row.addWidget(reload_btn)
        btn_row.addStretch()

        clear_btn = QPushButton("清空记录")
        clear_btn.setObjectName("Danger")
        clear_btn.setFixedHeight(34)
        clear_btn.clicked.connect(self._clear_history)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

        self._reload_history()
        return w

    # ========================================================
    #  操作
    # ========================================================
    def _toggle_enable(self, s):
        self.state.config_data["ai_enabled"] = bool(s)
        self.state.save_config()

    def _save_config(self):
        cfg = self.state.config_data
        cfg["ai_base_url"] = self._base_url.text().strip()
        cfg["ai_api_key"] = self._api_key.text().strip()
        cfg["ai_model"] = self._model.text().strip()
        cfg["ai_chat_enabled"] = self._chat_enabled.isChecked()
        cfg["ai_chat_trigger"] = self._chat_trigger.text().strip()
        try:
            cfg["ai_chat_cooldown"] = int(self._chat_cooldown.text() or 5)
            cfg["ai_context_lines"] = int(self._context_lines.text() or 10)
            cfg["ai_moderation_cooldown"] = int(self._mod_cooldown.text() or 3)
            cfg["ai_global_cooldown"] = float(self._global_cooldown.text() or 1)
        except ValueError:
            QMessageBox.critical(self, "参数错误", "冷却/上下文必须是数字")
            return
        cfg["ai_moderation_enabled"] = self._mod_enabled.isChecked()
        cfg["ai_moderation_broadcast"] = self._mod_broadcast.isChecked()
        cfg["ai_system_prompt"] = self._prompt.toPlainText()
        cfg["ai_enabled"] = self._enable_cb.isChecked()
        if self.state.save_config():
            self.state.log("AI 配置已保存", "ok")
            self._test_result.setText("✔ 已保存")

    def _test_connection(self):
        from core.ai_client import AIClient
        self._test_result.setText("测试中…")
        client = AIClient(
            self._base_url.text().strip(),
            self._api_key.text().strip(),
            self._model.text().strip(),
            timeout=15,
        )

        def worker():
            ok, msg = client.test_connection()
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._test_result.setText(msg))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _reload_history(self):
        entries = self.state.ai_history.recent(200)
        self._log_text.clear()
        if not entries:
            self._log_text.setPlainText("（暂无历史记录）")
            return
        lines = []
        for e in entries:
            ts = time.strftime("%m-%d %H:%M:%S",
                               time.localtime(e.get("time", 0)))
            lines.append(f"[{ts}] <{e.get('player')}> {e.get('message')}")
            if e.get("reply"):
                lines.append(f"{e['reply']}")
            if e.get("action", "none") != "none":
                lines.append(f"{e['action']}  ({e.get('reason','')})")
        self._log_text.setPlainText("\n".join(lines))

    def _clear_history(self):
        reply = QMessageBox.question(
            self, "清空记录", "确定要清空所有对话记录吗？")
        if reply != QMessageBox.Yes:
            return
        self.state.ai_history.clear()
        self._reload_history()

    def _on_log(self, msg, tag):
        pass

    def on_show(self):
        enabled = self.state.config_data.get("ai_enabled")
        self._status.setText("已启用" if enabled else "未启用")