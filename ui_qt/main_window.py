"""主窗口：侧边栏 + 页面栈。"""
from PySide6.QtCore import Qt, QSize, QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget, QFrame, QMessageBox,
    QDialog,
)

from ui_qt.theme import theme
from ui_qt.app_state import AppState

# 页面
from ui_qt.pages.dashboard import DashboardPage
from ui_qt.pages.console import ConsolePage
from ui_qt.pages.players import PlayersPage
from ui_qt.pages.permissions import PermissionsPage
from ui_qt.pages.zones import ZonesPage
from ui_qt.pages.roster import RosterPage
from ui_qt.pages.backup import BackupPage
from ui_qt.pages.properties import PropertiesPage
from ui_qt.pages.ai import AIPage
from ui_qt.pages.settings import SettingsPage
from ui_qt.pages.plugin_store import PluginStorePage

# 新手引导
from ui_qt.dialogs.onboarding import OnboardingDialog

NAV_ITEMS = [
    "仪表盘",
    "控制台",
    "玩家管理",
    "权限管理",
    "区域管理",
    "名单管理",
    "备份管理",
    "服务器属性",
    "AI 助手",
    "插件商店",
    "设置",
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.state = AppState()

        self.setWindowTitle("CubeDeck")
        self.resize(1220, 800)
        self.setMinimumSize(1000, 640)

        self.setStyleSheet(theme.qss())

        self._page_anim = None

        self._connect_signals()
        self._build()

        self._nav.setCurrentRow(0)
        self._switch_to(0, animate=False)

        # 无服务器时弹出引导
        if not self.state.has_server():
            QTimer.singleShot(300, self._show_onboarding)

    # ========================================================
    def _connect_signals(self):
        s = self.state
        s.server_starting.connect(self._on_server_starting)
        s.server_started.connect(self._on_server_started)
        s.server_stopping.connect(self._on_server_stopping)
        s.server_stopped.connect(self._on_server_stopped)
        s.rcon_connected.connect(self._on_rcon_connected)
        s.rcon_disconnected.connect(self._on_rcon_disconnected)
        s.theme_changed.connect(self._on_theme_changed)
        s.eula_required.connect(self._on_eula_required)
        s.port_conflict.connect(self._on_port_conflict)
        s.server_switched.connect(self._on_server_switched)

    # ========================================================
    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main(), 1)

    # --------------------------------------------------------
    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)

        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)

        logo = QWidget()
        ll = QVBoxLayout(logo)
        ll.setContentsMargins(24, 24, 24, 22)
        ll.setSpacing(2)

        # ★ 不再写内联样式，用 objectName 交给 QSS 处理
        t1 = QLabel("CubeDeck")
        t1.setObjectName("LogoTitle")
        ll.addWidget(t1)

        t2 = QLabel("Minecraft 服务器控制台")
        t2.setObjectName("LogoSub")
        ll.addWidget(t2)

        sl.addWidget(logo)

        from ui_qt.widgets.server_selector import ServerSelector

        selector_wrap = QWidget()
        sel_layout = QVBoxLayout(selector_wrap)
        sel_layout.setContentsMargins(20, 0, 20, 14)
        sel_layout.setSpacing(0)

        self._server_selector = ServerSelector(self.state)
        self._server_selector.server_changed.connect(self._on_server_switch)
        sel_layout.addWidget(self._server_selector)

        sl.addWidget(selector_wrap)

        self._nav = QListWidget()
        self._nav.setObjectName("NavList")
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._nav.setFocusPolicy(Qt.NoFocus)

        for label in NAV_ITEMS:
            item = QListWidgetItem(label)
            item.setSizeHint(QSize(0, 40))
            self._nav.addItem(item)

        self._nav.currentRowChanged.connect(self._on_nav_changed)
        sl.addWidget(self._nav, 1)

        footer = QWidget()
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(28, 12, 24, 22)
        fl.setSpacing(6)

        self._rcon_dot = QLabel("●")
        self._rcon_dot.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 10px; "
            f"background: transparent;")
        fl.addWidget(self._rcon_dot)

        self._rcon_label = QLabel("RCON 未连接")
        self._rcon_label.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        fl.addWidget(self._rcon_label)
        fl.addStretch()

        sl.addWidget(footer)

        return sidebar

    # --------------------------------------------------------
    def _build_main(self):
        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(28, 24, 28, 24)
        ml.setSpacing(16)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(12)

        self._page_title = QLabel("仪表盘")
        self._page_title.setObjectName("PageTitle")
        self._page_title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 22px; font-weight: bold; background: transparent;")
        header.addWidget(self._page_title)
        header.addStretch()

        self._header_status = QLabel("离线")
        self._header_status.setObjectName("StatusChip")
        self._refresh_status_chip("text_dim", "离线")
        header.addWidget(self._header_status)

        ml.addLayout(header)

        self._stack = QStackedWidget()
        ml.addWidget(self._stack, 1)

        self._pages = [
            DashboardPage(self.state),
            ConsolePage(self.state),
            PlayersPage(self.state),
            PermissionsPage(self.state),
            ZonesPage(self.state),
            RosterPage(self.state),
            BackupPage(self.state),
            PropertiesPage(self.state),
            AIPage(self.state),
            PluginStorePage(self.state),
            SettingsPage(self.state),
        ]
        for p in self._pages:
            self._stack.addWidget(p)

        return main

    def _refresh_status_chip(self, color_key, text):
        self._header_status.setText(f"●  {text}")
        self._header_status.setStyleSheet(
            f"color: {theme.c(color_key)}; "
            f"background-color: {theme.c('card')}; "
            f"border: 1px solid {theme.c('border')}; "
            f"border-radius: 12px; "
            f"padding: 4px 14px; font-size: 12px;")

    # ========================================================
    def _on_nav_changed(self, row):
        self._switch_to(row, animate=True)

    def _switch_to(self, index, animate=True):
        if index < 0 or index >= len(self._pages):
            return

        self._stack.setCurrentIndex(index)
        self._page_title.setText(NAV_ITEMS[index])

        page = self._pages[index]
        if hasattr(page, "on_show"):
            try:
                page.on_show()
            except Exception as e:
                self.state.log(
                    f"[UI] {type(page).__name__} on_show 失败：{e}", "error")

        if animate:
            self._animate_page_in(page)
            self._animate_title()

    def _animate_page_in(self, widget):
        from ui_qt.widgets.animations import appear
        try:
            appear(widget, direction="right", distance=24,
                   duration=260, delay=0)
        except Exception:
            pass

    def _animate_title(self):
        from ui_qt.widgets.animations import appear
        try:
            appear(self._page_title, direction="down",
                   distance=8, duration=220, delay=30)
        except Exception:
            pass

    # ========================================================
    #  服务器切换
    # ========================================================
    def _on_server_switch(self, server_id):
        before_id = self.state.server_id
        self.state.request_switch_server(server_id)

        if self.state.server_id == before_id:
            if hasattr(self, "_server_selector"):
                try:
                    self._server_selector.reload()
                except Exception:
                    pass

    def _on_server_switched(self, server_id):
        if hasattr(self, "_server_selector"):
            try:
                self._server_selector.reload()
            except Exception:
                pass

        for p in self._pages:
            if hasattr(p, "on_show"):
                try:
                    p.on_show()
                except Exception as e:
                    self.state.log(
                        f"[UI] {type(p).__name__} 刷新失败：{e}", "warn")

        self._refresh_status_chip("text_dim", "离线")

        self._rcon_dot.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 10px; "
            f"background: transparent;")
        self._rcon_label.setText("RCON 未连接")
        self._rcon_label.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")

    def _on_server_starting(self):
        self._refresh_status_chip("orange", "启动中")

    def _on_server_started(self):
        self._refresh_status_chip("green", "运行中")
        for p in self._pages:
            if hasattr(p, "on_server_started"):
                try:
                    p.on_server_started()
                except Exception:
                    pass

    def _on_server_stopping(self):
        self._refresh_status_chip("orange", "停止中")

    def _on_server_stopped(self):
        self._refresh_status_chip("text_dim", "离线")

        self._rcon_dot.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 10px; "
            f"background: transparent;")
        self._rcon_label.setText("RCON 未连接")
        self._rcon_label.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")

        for p in self._pages:
            if hasattr(p, "on_server_stopped"):
                try:
                    p.on_server_stopped()
                except Exception:
                    pass

    def _on_rcon_connected(self):
        self._rcon_dot.setStyleSheet(
            f"color: {theme.c('green')}; font-size: 10px; "
            f"background: transparent;")
        self._rcon_label.setText("RCON 已连接")
        self._rcon_label.setStyleSheet(
            f"color: {theme.c('green')}; font-size: 11px; "
            f"background: transparent;")

        for p in self._pages:
            if hasattr(p, "on_rcon_connected"):
                try:
                    p.on_rcon_connected()
                except Exception:
                    pass

    def _on_rcon_disconnected(self):
        self._rcon_dot.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 10px; "
            f"background: transparent;")
        self._rcon_label.setText("RCON 未连接")
        self._rcon_label.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")

    # ========================================================
    def _on_theme_changed(self, name):
        # 1. 刷新全局 QSS
        self.setStyleSheet(theme.qss())

        # 2. 重建所有页面（让内联样式也应用新主题）
        self._reload_all_pages()

        # 3. 更新主窗口内的内联样式控件
        self._page_title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 22px; font-weight: bold; background: transparent;")

        if self.state.is_running:
            self._refresh_status_chip("green", "运行中")
        else:
            self._refresh_status_chip("text_dim", "离线")

        if self._rcon_label.text() == "RCON 已连接":
            self._rcon_dot.setStyleSheet(
                f"color: {theme.c('green')}; font-size: 10px; "
                f"background: transparent;")
            self._rcon_label.setStyleSheet(
                f"color: {theme.c('green')}; font-size: 11px; "
                f"background: transparent;")
        else:
            self._rcon_dot.setStyleSheet(
                f"color: {theme.c('text_faint')}; font-size: 10px; "
                f"background: transparent;")
            self._rcon_label.setStyleSheet(
                f"color: {theme.c('text_faint')}; font-size: 11px; "
                f"background: transparent;")

    def _reload_all_pages(self):
        """
        销毁并重建所有页面。
        主题切换时调用，让所有内联样式用新主题重新生成。
        """
        # 记住当前页
        current_idx = self._stack.currentIndex()

        # 从栈里移除旧页面 + 标记删除
        for p in self._pages:
            try:
                self._stack.removeWidget(p)
            except Exception:
                pass
            try:
                p.setParent(None)
                p.deleteLater()
            except Exception:
                pass

        self._pages = []

        # 重新创建
        try:
            self._pages = [
                DashboardPage(self.state),
                ConsolePage(self.state),
                PlayersPage(self.state),
                PermissionsPage(self.state),
                ZonesPage(self.state),
                RosterPage(self.state),
                BackupPage(self.state),
                PropertiesPage(self.state),
                AIPage(self.state),
                PluginStorePage(self.state),
                SettingsPage(self.state),
            ]
        except Exception as e:
            self.state.log(f"[UI] 重建页面失败：{e}", "error")
            return

        for p in self._pages:
            self._stack.addWidget(p)

        # 恢复当前页
        if 0 <= current_idx < len(self._pages):
            self._stack.setCurrentIndex(current_idx)
            page = self._pages[current_idx]
            if hasattr(page, "on_show"):
                try:
                    page.on_show()
                except Exception:
                    pass
        else:
            self._stack.setCurrentIndex(0)
            self._page_title.setText(NAV_ITEMS[0])

    # ========================================================
    #  新手引导
    # ========================================================
    def _show_onboarding(self):
        dlg = OnboardingDialog(self)
        accepted = dlg.exec() == QDialog.Accepted
        action, name, path = dlg.get_result()

        try:
            dlg.setParent(None)
            dlg.deleteLater()
        except Exception:
            pass

        if not accepted:
            return

        if action == "download":
            QTimer.singleShot(300, self._goto_server_setup)
        elif action == "import":
            self._do_import_server(name, path)

    def _goto_server_setup(self):
        settings_idx = NAV_ITEMS.index("设置")
        self._nav.setCurrentRow(settings_idx)

        page = self._pages[settings_idx]
        QTimer.singleShot(500, page._open_server_setup)

    def _do_import_server(self, name, path):
        ok = self.state.activate_server(name, path)
        if not ok:
            QMessageBox.warning(
                self, "导入失败",
                "服务器导入失败，请检查目录或重试。")
            return

        for p in self._pages:
            if hasattr(p, "on_show"):
                try:
                    p.on_show()
                except Exception:
                    pass

        if hasattr(self, "_server_selector"):
            self._server_selector.reload()

        QMessageBox.information(
            self, "导入成功",
            f"服务器「{name}」已导入。\n\n"
            f"目录：{path}\n\n"
            f"可以在「设置」中调整 Java 路径和内存配置。")

    def _goto_settings_for_java(self):
        try:
            settings_idx = NAV_ITEMS.index("设置")
        except ValueError:
            return

        self._nav.setCurrentRow(settings_idx)

        page = self._pages[settings_idx]
        try:
            if hasattr(page, "_reload"):
                page._reload()
        except Exception:
            pass

        try:
            if hasattr(page, "e_java"):
                page.e_java.setFocus()
                page.e_java.selectAll()
        except Exception:
            pass

    # ========================================================
    #  EULA / 端口冲突
    # ========================================================
    def _on_eula_required(self):
        reply = QMessageBox.question(
            self, "Minecraft EULA",
            "启动服务器需要先同意 Minecraft 最终用户许可协议 (EULA)。\n\n"
            "协议全文：https://aka.ms/MinecraftEULA\n\n"
            "是否同意并继续启动？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            eula_path = self.state.server_path / "eula.txt"
            eula_path.write_text(
                "# By changing the setting below to TRUE you are "
                "indicating your agreement to our EULA\n"
                "# (https://aka.ms/MinecraftEULA).\n"
                "eula=true\n",
                encoding="utf-8",
            )
            self.state.log("已同意 EULA，正在启动…", "ok")
        except Exception as e:
            QMessageBox.critical(self, "写入 eula.txt 失败", str(e))
            return

        self.state.start_server()

    def _on_port_conflict(self, port, who):
        box = QMessageBox(self)
        box.setWindowTitle("端口冲突")
        box.setIcon(QMessageBox.Warning)
        box.setText(f"端口 {port} 已被占用")
        box.setInformativeText(
            f"占用者：{who}\n\n"
            f"你可以选择：\n"
            f"· 换用其他端口 —— 自动修改 server.properties 中的 server-port\n"
            f"· 清理占用进程 —— 终止占用该端口的进程（适合残留的僵尸进程）\n"
            f"· 取消 —— 不做任何操作")

        switch_btn = box.addButton("换用其他端口", QMessageBox.AcceptRole)
        kill_btn = box.addButton("清理占用进程", QMessageBox.DestructiveRole)
        cancel_btn = box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(switch_btn)

        box.exec()

        clicked = box.clickedButton()
        if clicked is switch_btn:
            self.state.resolve_port_conflict("switch")
        elif clicked is kill_btn:
            self.state.resolve_port_conflict("kill")
        else:
            self.state.resolve_port_conflict("cancel")

    # ========================================================
    def closeEvent(self, event):
        keep = self.state.config_data.get("keep_server_on_exit", True)

        if self.state.is_running:
            if keep:
                reply = QMessageBox.question(
                    self, "退出确认",
                    "服务器仍在后台运行。\n\n"
                    "是：保留服务器并退出（下次自动接管）\n"
                    "否：停止服务器并退出\n"
                    "取消：留在软件内",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.Cancel:
                    event.ignore()
                    return
                if reply == QMessageBox.No:
                    self._graceful_stop_and_wait()
            else:
                reply = QMessageBox.question(
                    self, "退出确认",
                    "服务器正在运行，确定要退出并停止服务器吗？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply != QMessageBox.Yes:
                    event.ignore()
                    return
                self._graceful_stop_and_wait()

        try:
            if self.state._log_watcher:
                self.state._log_watcher.stop()
        except Exception:
            pass

        event.accept()

    def _graceful_stop_and_wait(self):
        try:
            self.state.stop_server()
        except Exception:
            pass
        from PySide6.QtCore import QEventLoop
        loop = QEventLoop()
        QTimer.singleShot(3000, loop.quit)
        loop.exec()