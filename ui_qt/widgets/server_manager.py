"""设置页的服务器管理卡片。"""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QMessageBox, QDialog, QFileDialog,
)

from ui_qt.theme import theme
from core import server_registry as registry


# ============================================================
#  对话框
# ============================================================
class _RenameDialog(QDialog):
    """重命名服务器。"""

    def __init__(self, parent, current_name):
        super().__init__(parent)
        self.setWindowTitle("重命名服务器")
        self.resize(380, 150)
        self._new_name = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        layout.addWidget(QLabel("新名称"))
        self._entry = QLineEdit(current_name)
        self._entry.setFixedHeight(36)
        self._entry.selectAll()
        layout.addWidget(self._entry)

        btns = QHBoxLayout()
        btns.addStretch()

        cancel = QPushButton("取消")
        cancel.setObjectName("Ghost")
        cancel.setFixedHeight(36)
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)

        ok = QPushButton("确定")
        ok.setObjectName("Accent")
        ok.setFixedHeight(36)
        ok.clicked.connect(self._on_ok)
        btns.addWidget(ok)

        layout.addLayout(btns)
        self._entry.returnPressed.connect(self._on_ok)

    def _on_ok(self):
        name = self._entry.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "名称不能为空")
            return
        self._new_name = name
        self.accept()

    def new_name(self):
        return self._new_name


class _NewServerDialog(QDialog):
    """新建服务器：名称 + 服务器目录。"""

    def __init__(self, parent, default_dir=""):
        super().__init__(parent)
        self.setWindowTitle("新建服务器")
        self.resize(560, 260)
        self._name = ""
        self._server_path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        # 名称
        layout.addWidget(self._label("服务器名称"))
        self._name_entry = QLineEdit("新服务器")
        self._name_entry.setFixedHeight(38)
        self._name_entry.selectAll()
        layout.addWidget(self._name_entry)

        # 服务器目录
        layout.addWidget(self._label("服务器目录"))
        path_row = QHBoxLayout()
        path_row.setSpacing(8)

        self._path_entry = QLineEdit(default_dir)
        self._path_entry.setFixedHeight(38)
        self._path_entry.setPlaceholderText(
            "指向含有 server.jar 的目录")
        path_row.addWidget(self._path_entry, 1)

        browse_btn = QPushButton("浏览…")
        browse_btn.setObjectName("Ghost")
        browse_btn.setFixedSize(80, 38)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)

        layout.addLayout(path_row)

        # 提示
        hint = QLabel(
            "如果选择空目录，后续可以用「下载服务端加载器」装进这个目录。\n"
            "如果目录已有服务端，直接指向它即可。")
        hint.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addStretch()

        # 按钮
        btns = QHBoxLayout()
        btns.addStretch()

        cancel = QPushButton("取消")
        cancel.setObjectName("Ghost")
        cancel.setFixedHeight(38)
        cancel.setFixedWidth(90)
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)

        ok = QPushButton("创建")
        ok.setObjectName("Accent")
        ok.setFixedHeight(38)
        ok.setFixedWidth(100)
        ok.clicked.connect(self._on_ok)
        btns.addWidget(ok)

        layout.addLayout(btns)

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 12px; "
            f"background: transparent;")
        return lbl

    def _browse(self):
        start = self._path_entry.text().strip() or "."
        path = QFileDialog.getExistingDirectory(
            self, "选择服务器目录", start)
        if path:
            self._path_entry.setText(path)

    def _on_ok(self):
        name = self._name_entry.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写服务器名称")
            return

        server_path = self._path_entry.text().strip()

        # 目录存在性检查（可选）
        if server_path:
            p = Path(server_path)
            if not p.exists():
                reply = QMessageBox.question(
                    self, "目录不存在",
                    f"{server_path}\n\n"
                    f"目录不存在，是否创建？\n"
                    f"（之后可以往里面下载服务端）",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes)
                if reply != QMessageBox.Yes:
                    return
                try:
                    p.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    QMessageBox.critical(
                        self, "创建目录失败", str(e))
                    return

            # 已有服务端？给个提示
            if (p / "server.jar").exists():
                reply = QMessageBox.question(
                    self, "检测到服务端",
                    f"该目录已包含 server.jar。\n\n"
                    f"要现在启动服务器吗？\n"
                    f"（选「否」只创建配置，不启动）",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No)

        self._name = name
        self._server_path = server_path
        self.accept()

    def result_values(self):
        return self._name, self._server_path


# ============================================================
#  服务器管理卡片
# ============================================================
class ServerManagerWidget(QWidget):
    """服务器列表 + 增删改。"""

    changed = Signal()

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._build()
        self.reload()

        # ★ 订阅 AppState 信号，让切换 / 启停 / 改名时自动重绘
        try:
            self.state.server_switched.connect(self._on_server_switched)
            self.state.server_started.connect(self._on_server_state_changed)
            self.state.server_stopped.connect(self._on_server_state_changed)
        except Exception:
            pass

    def _on_server_switched(self, _server_id=""):
        """切换服务器后重绘列表（标记新的"当前"）。"""
        self.reload()

    def _on_server_state_changed(self):
        """服务器启停后重绘（状态圆点颜色会变）。"""
        self.reload()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.addStretch()

        add_btn = QPushButton("➕ 添加服务器")
        add_btn.setObjectName("Accent")
        add_btn.setFixedHeight(34)
        add_btn.clicked.connect(self._add_server)
        top.addWidget(add_btn)
        layout.addLayout(top)

        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(6)
        layout.addLayout(self._list_layout)

    # ========================================================
    def reload(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        servers = registry.list_servers()
        active_id = self.state.server_id

        for s in servers:
            self._list_layout.addWidget(
                self._make_row(s, is_active=(s["id"] == active_id)))

    def _make_row(self, server, is_active=False):
        row = QFrame()
        row.setObjectName("Card")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 10, 14, 10)
        rl.setSpacing(12)

        # 状态点
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {theme.c('green') if is_active else theme.c('text_faint')}; "
            f"font-size: 12px; background: transparent;")
        rl.addWidget(dot)

        # 名称 + 路径
        info = QVBoxLayout()
        info.setSpacing(2)

        name = QLabel(server.get("name", server["id"]))
        name.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 13px; font-weight: bold; background: transparent;")
        info.addWidget(name)

        cfg = server.get("config", {}) or {}
        path_text = cfg.get("server_path") or "（未配置服务器目录）"
        path = QLabel(path_text)
        path.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        path.setWordWrap(True)
        info.addWidget(path)
        rl.addLayout(info, 1)

        if is_active:
            current_lbl = QLabel("当前")
            current_lbl.setStyleSheet(
                f"color: {theme.c('accent')}; font-size: 11px; "
                f"background: transparent;")
            rl.addWidget(current_lbl)
        else:
            switch_btn = QPushButton("切换")
            switch_btn.setObjectName("Ghost")
            switch_btn.setFixedSize(60, 30)
            switch_btn.clicked.connect(
                lambda _=False, sid=server["id"]: self._switch(sid))
            rl.addWidget(switch_btn)

        rename_btn = QPushButton("改名")
        rename_btn.setObjectName("Ghost")
        rename_btn.setFixedSize(60, 30)
        rename_btn.clicked.connect(
            lambda _=False, s=server: self._rename(s))
        rl.addWidget(rename_btn)

        del_btn = QPushButton("删除")
        del_btn.setObjectName("Danger")
        del_btn.setFixedSize(60, 30)
        del_btn.clicked.connect(
            lambda _=False, sid=server["id"]: self._delete(sid))
        rl.addWidget(del_btn)

        return row

    # ========================================================
    def _add_server(self):
        # 默认目录：当前服务器父目录下的 "new_server"
        default_dir = ""
        try:
            default_dir = str(self.state.server_path.parent / "new_server")
        except Exception:
            pass

        dlg = _NewServerDialog(self, default_dir)
        if dlg.exec() != QDialog.Accepted:
            return

        name, server_path = dlg.result_values()

        new_id = self.state.add_new_server(
            name, server_path=server_path)
        if not new_id:
            QMessageBox.warning(self, "添加失败", "无法添加服务器")
            return

        QMessageBox.information(
            self, "已创建",
            f"「{name}」已创建。\n\n"
            f"目录：{server_path or '（未配置）'}\n\n"
            f"是否立即切换过去并配置 Java 路径？")
        self.reload()
        self.changed.emit()

    def _switch(self, server_id):
        self.state.request_switch_server(server_id)
        self.reload()
        self.changed.emit()

    def _rename(self, server):
        current = server.get("name", "")
        dlg = _RenameDialog(self, current)
        if dlg.exec() != QDialog.Accepted:
            return
        new_name = dlg.new_name()
        if new_name == current:
            return

        registry.update_server(server["id"], name=new_name)
        if server["id"] == self.state.server_id:
            self.state.current_server["name"] = new_name

        self.state.log(f"服务器已重命名：{current} → {new_name}", "ok")
        self.reload()
        self.changed.emit()

    def _delete(self, server_id):
        servers = registry.list_servers()
        if len(servers) <= 1:
            QMessageBox.warning(self, "提示", "至少保留一个服务器")
            return

        target_name = server_id
        for s in servers:
            if s["id"] == server_id:
                target_name = s.get("name", server_id)
                break

        reply = QMessageBox.question(
            self, "删除服务器",
            f"确定要删除「{target_name}」吗？\n\n"
            f"⚠ 数据文件会保留在 CubeDeck/{server_id}/ 目录下，\n"
            f"   可以手动恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        was_active = (server_id == self.state.server_id)

        registry.remove_server(server_id)
        self.state.log(f"已删除服务器：{target_name}", "warn")

        if was_active:
            remaining = registry.list_servers()
            if remaining:
                self.state.request_switch_server(remaining[0]["id"])

        self.reload()
        self.changed.emit()