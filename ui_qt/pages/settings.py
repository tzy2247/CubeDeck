"""设置页。"""
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QComboBox, QFileDialog, QScrollArea, QWidget,
    QMessageBox,
)

from ui_qt.theme import theme, THEMES
from ui_qt.pages.base import BasePage
from ui_qt.widgets.card import Card


LABEL_WIDTH = 130


class SettingsPage(BasePage):
    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self._build()
        self._reload()

    # ========================================================
    #  构建
    # ========================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ---- 顶部按钮栏 ----
        top = Card()
        tl = top.body()
        tl.setContentsMargins(20, 12, 20, 12)
        tr = QHBoxLayout()
        tr.setSpacing(10)

        save_btn = QPushButton("保存配置")
        save_btn.setObjectName("Accent")
        save_btn.setFixedHeight(36)
        save_btn.clicked.connect(self._save)
        tr.addWidget(save_btn)

        reload_btn = QPushButton("重新加载")
        reload_btn.setObjectName("Ghost")
        reload_btn.setFixedHeight(36)
        reload_btn.clicked.connect(self._reload)
        tr.addWidget(reload_btn)

        tr.addStretch()

        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px; "
            f"background: transparent;")
        tr.addWidget(self._status)

        tl.addLayout(tr)
        root.addWidget(top)

        # ---- 滚动区 ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 8, 0)
        bl.setSpacing(12)

        # ====================================================
        #  服务器
        # ====================================================
        c1 = Card(title="服务器")
        b1 = c1.body()
        self.e_server = self._path_row(b1, "服务器目录", "dir", openable=True)
        self.e_java = self._path_row(b1, "Java 路径", "file")
        self.e_xmx = self._entry_row(b1, "最大内存 (-Xmx)",
                                     placeholder="如 4G")
        self.e_xms = self._entry_row(b1, "初始内存 (-Xms)",
                                     placeholder="如 2G")
        self.e_extra = self._entry_row(
            b1, "JVM 额外参数", placeholder="-XX:+UseG1GC")
        bl.addWidget(c1)

        # ====================================================
        #  RCON
        # ====================================================
        c2 = Card(title="RCON")
        b2 = c2.body()
        self.e_port = self._entry_row(b2, "端口")
        self.e_pwd = self._entry_row(b2, "密码", password=True)
        bl.addWidget(c2)

        # ====================================================
        #  自动备份
        # ====================================================
        c3 = Card(title="自动备份 & 恢复")
        b3 = c3.body()
        self.cb_auto_backup = self._check_row(b3, "启用自动备份")
        self.e_interval = self._entry_row(b3, "备份间隔（分钟）")
        self.e_keep = self._entry_row(b3, "保留备份份数")
        self.cb_auto_restart = self._check_row(b3, "崩溃自动重启")
        bl.addWidget(c3)

        # ====================================================
        #  掉落物清理
        # ====================================================
        c4 = Card(title="掉落物清理")
        b4 = c4.body()
        self.cb_global_clean = self._check_row(b4, "启用全局清理")
        self.e_drop_interval = self._entry_row(b4, "清理间隔（分钟）")
        bl.addWidget(c4)

        # ====================================================
        #  外观
        # ====================================================
        c5 = Card(title="外观")
        b5 = c5.body()

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._make_label("主题"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(list(THEMES.keys()))
        self.theme_combo.setFixedHeight(34)
        self.theme_combo.setFixedWidth(200)
        row.addWidget(self.theme_combo)
        row.addStretch()
        b5.addLayout(row)

        hint = QLabel("切换后立即生效")
        hint.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        b5.addWidget(hint)
        bl.addWidget(c5)

        # ====================================================
        #  网络 / 代理
        # ====================================================
        c6 = Card(title="网络 / 代理")
        b6 = c6.body()

        self.e_proxy = self._entry_row(
            b6, "HTTP 代理",
            placeholder="如 http://127.0.0.1:7890")
        self.e_modrinth_api = self._entry_row(
            b6, "Modrinth API",
            placeholder="留空使用内置镜像")

        proxy_hint = QLabel(
            "用于访问插件商店。国内用户若连接超时，\n"
            "填一个本地代理地址即可（Clash: 7890，V2Ray: 10809）。\n"
            "留空则直连。")
        proxy_hint.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        proxy_hint.setWordWrap(True)
        b6.addWidget(proxy_hint)

        row_test = QHBoxLayout()
        row_test.setSpacing(10)
        test_btn = QPushButton("测试 Modrinth 连接")
        test_btn.setObjectName("Ghost")
        test_btn.setFixedHeight(34)
        test_btn.clicked.connect(self._test_modrinth)
        row_test.addWidget(test_btn)
        row_test.addStretch()
        b6.addLayout(row_test)

        self._modrinth_status = QLabel("")
        self._modrinth_status.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px; "
            f"background: transparent;")
        self._modrinth_status.setWordWrap(True)
        b6.addWidget(self._modrinth_status)

        bl.addWidget(c6)

        # ====================================================
        #  CurseForge
        # ====================================================
        c7 = Card(title="CurseForge")
        b7 = c7.body()

        self.e_cf_key = self._entry_row(
            b7, "API Key",
            placeholder="从 console.curseforge.com 获取")

        cf_hint = QLabel(
            "CurseForge 商店需要 API Key。\n"
            "1. 访问 https://console.curseforge.com\n"
            "2. 用 Google 账号登录\n"
            "3. 创建组织后自动生成 API Key\n"
            "4. 复制粘贴到上方输入框")
        cf_hint.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        cf_hint.setWordWrap(True)
        b7.addWidget(cf_hint)

        row_cf = QHBoxLayout()
        row_cf.setSpacing(10)
        cf_test_btn = QPushButton("测试 CurseForge 连接")
        cf_test_btn.setObjectName("Ghost")
        cf_test_btn.setFixedHeight(34)
        cf_test_btn.clicked.connect(self._test_curseforge)
        row_cf.addWidget(cf_test_btn)
        row_cf.addStretch()
        b7.addLayout(row_cf)

        self._cf_status = QLabel("")
        self._cf_status.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px; "
            f"background: transparent;")
        self._cf_status.setWordWrap(True)
        b7.addWidget(self._cf_status)

        bl.addWidget(c7)

        bl.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    # ========================================================
    #  表单组件
    # ========================================================
    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setFixedWidth(LABEL_WIDTH)
        lbl.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 13px; "
            f"background: transparent;")
        return lbl

    def _entry_row(self, parent, label, placeholder="", password=False):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._make_label(label))

        e = QLineEdit()
        e.setPlaceholderText(placeholder)
        e.setFixedHeight(34)
        if password:
            e.setEchoMode(QLineEdit.Password)
        row.addWidget(e, 1)
        parent.addLayout(row)
        return e

    def _path_row(self, parent, label, kind, openable=False):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._make_label(label))

        e = QLineEdit()
        e.setFixedHeight(34)
        row.addWidget(e, 1)

        if openable and kind == "dir":
            open_btn = QPushButton("打开")
            open_btn.setObjectName("Ghost")
            open_btn.setFixedSize(56, 34)
            open_btn.clicked.connect(lambda: self._open_path(e.text()))
            row.addWidget(open_btn)

        browse_btn = QPushButton("浏览")
        browse_btn.setObjectName("Ghost")
        browse_btn.setFixedSize(56, 34)
        browse_btn.clicked.connect(lambda: self._browse(e, kind))
        row.addWidget(browse_btn)

        parent.addLayout(row)
        return e

    def _check_row(self, parent, label):
        cb = QCheckBox(label)
        cb.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 13px; "
            f"background: transparent;")
        parent.addWidget(cb)
        return cb

    def _browse(self, entry, kind):
        if kind == "dir":
            path = QFileDialog.getExistingDirectory(
                self, "选择目录", entry.text() or "")
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择文件", entry.text() or "",
                "Java 可执行文件 (*.exe);;所有文件 (*)")
        if path:
            entry.setText(path)

    def _open_path(self, path):
        if not path:
            return
        p = Path(path)
        if not p.exists():
            QMessageBox.warning(self, "提示", f"路径不存在：\n{path}")
            return
        try:
            os.startfile(str(p))
        except Exception as e:
            QMessageBox.warning(self, "错误", str(e))

    # ========================================================
    #  读写
    # ========================================================
    def _reload(self):
        cfg = self.state.config_data
        self.e_server.setText(cfg.get("server_path", ""))
        self.e_java.setText(cfg.get("java_path", ""))
        self.e_xmx.setText(cfg.get("memory_xmx", "4G"))
        self.e_xms.setText(cfg.get("memory_xms", "2G"))
        self.e_extra.setText(cfg.get("jvm_args", ""))
        self.e_port.setText(str(cfg.get("rcon_port", 25575)))
        self.e_pwd.setText(cfg.get("rcon_password", ""))
        self.e_interval.setText(
            str(cfg.get("auto_backup_interval_min", 60)))
        self.e_keep.setText(str(cfg.get("auto_backup_keep", 10)))
        self.e_drop_interval.setText(
            str(cfg.get("auto_drop_clean_interval_min", 30)))

        self.cb_auto_backup.setChecked(
            bool(cfg.get("auto_backup_enabled")))
        self.cb_auto_restart.setChecked(bool(cfg.get("auto_restart")))
        self.cb_global_clean.setChecked(
            bool(cfg.get("global_clean_enabled")))

        cur_theme = cfg.get("theme", "深蓝")
        idx = self.theme_combo.findText(cur_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)

        self.e_proxy.setText(cfg.get("modrinth_proxy", ""))
        self.e_modrinth_api.setText(cfg.get("modrinth_api_base", ""))
        self.e_cf_key.setText(cfg.get("curseforge_api_key", ""))

        self._status.setText("")

    def _save(self):
        cfg = self.state.config_data
        try:
            port = int(self.e_port.text().strip())
            if not (1 <= port <= 65535):
                raise ValueError
            interval = int(self.e_interval.text().strip() or "60")
            keep = int(self.e_keep.text().strip() or "10")
            drop_interval = int(self.e_drop_interval.text().strip() or "30")
        except ValueError:
            QMessageBox.critical(self, "参数错误", "数字字段格式错误")
            return

        cfg["server_path"] = self.e_server.text().strip()
        cfg["java_path"] = self.e_java.text().strip()
        cfg["memory_xmx"] = self.e_xmx.text().strip() or "4G"
        cfg["memory_xms"] = self.e_xms.text().strip() or "2G"
        cfg["jvm_args"] = self.e_extra.text().strip()
        cfg["rcon_port"] = port
        cfg["rcon_password"] = self.e_pwd.text()
        cfg["auto_backup_enabled"] = self.cb_auto_backup.isChecked()
        cfg["auto_backup_interval_min"] = interval
        cfg["auto_backup_keep"] = keep
        cfg["auto_restart"] = self.cb_auto_restart.isChecked()
        cfg["global_clean_enabled"] = self.cb_global_clean.isChecked()
        cfg["auto_drop_clean_interval_min"] = drop_interval
        cfg["theme"] = self.theme_combo.currentText()
        cfg["modrinth_proxy"] = self.e_proxy.text().strip()
        cfg["modrinth_api_base"] = self.e_modrinth_api.text().strip()
        cfg["curseforge_api_key"] = self.e_cf_key.text().strip()

        if self.state.save_config():
            self.state.server_path = Path(cfg["server_path"])
            self.state.log("配置已保存", "ok")

            # 主题即时生效
            from ui_qt.theme import theme as _t
            if _t.set(cfg["theme"]):
                from PySide6.QtWidgets import QApplication
                QApplication.instance().setStyleSheet(_t.qss())
                self.state.theme_changed.emit(cfg["theme"])

            self._status.setText("已保存")
            self._status.setStyleSheet(
                f"color: {theme.c('green')}; font-size: 11px; "
                f"background: transparent;")
            QMessageBox.information(self, "成功", "配置已保存")

    def on_show(self):
        self._reload()

    # ========================================================
    #  测试连接
    # ========================================================
    def _test_modrinth(self):
        import threading
        from core.modrinth import ModrinthClient

        self._modrinth_status.setText("测试中…")

        proxy = self.e_proxy.text().strip() or None
        api_base = self.e_modrinth_api.text().strip() or None

        def worker():
            client = ModrinthClient(
                timeout=15, proxy=proxy, api_base=api_base,
                verify_ssl=False)
            ok, msg = client.test_connection()

            from PySide6.QtCore import QTimer
            if ok:
                QTimer.singleShot(0, lambda: self._modrinth_status.setText(
                    f"✔ {msg}"))
                QTimer.singleShot(0, lambda: self._modrinth_status.setStyleSheet(
                    f"color: {theme.c('green')}; font-size: 11px; "
                    f"background: transparent;"))
            else:
                short = msg.split("\n")[0][:100]
                QTimer.singleShot(0, lambda: self._modrinth_status.setText(
                    f"✖ {short}"))
                QTimer.singleShot(0, lambda: self._modrinth_status.setStyleSheet(
                    f"color: {theme.c('red')}; font-size: 11px; "
                    f"background: transparent;"))

        threading.Thread(target=worker, daemon=True).start()

    def _test_curseforge(self):
        import threading
        from core.store_curseforge import CurseForgeProvider

        self._cf_status.setText("测试中…")

        key = self.e_cf_key.text().strip()
        proxy = self.e_proxy.text().strip() or None

        def worker():
            p = CurseForgeProvider(
                api_key=key, timeout=15, proxy=proxy, verify_ssl=False)
            ok, msg = p.test_connection()

            from PySide6.QtCore import QTimer
            if ok:
                QTimer.singleShot(0, lambda: self._cf_status.setText(
                    f"✔ {msg}"))
                QTimer.singleShot(0, lambda: self._cf_status.setStyleSheet(
                    f"color: {theme.c('green')}; font-size: 11px; "
                    f"background: transparent;"))
            else:
                short = msg.split("\n")[0][:100]
                QTimer.singleShot(0, lambda: self._cf_status.setText(
                    f"✖ {short}"))
                QTimer.singleShot(0, lambda: self._cf_status.setStyleSheet(
                    f"color: {theme.c('red')}; font-size: 11px; "
                    f"background: transparent;"))

        threading.Thread(target=worker, daemon=True).start()