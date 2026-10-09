"""主窗口：侧边栏 + 页面栈。"""
from PySide6.QtCore import Qt, QSize, QEasingCurve, QPropertyAnimation, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QStackedWidget, QFrame, QMessageBox,
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

        # ---- Logo ----
        logo = QWidget()
        ll = QVBoxLayout(logo)
        ll.setContentsMargins(24, 24, 24, 22)
        ll.setSpacing(2)

        t1 = QLabel("CubeDeck")
        t1.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 18px; font-weight: bold; letter-spacing: 0.5px;")
        ll.addWidget(t1)

        t2 = QLabel("Minecraft 服务器控制台")
        t2.setStyleSheet(
            f"color: {theme.c('text_faint')}; "
            f"font-size: 11px; letter-spacing: 0.3px;")
        ll.addWidget(t2)

        sl.addWidget(logo)

        # ---- 分隔线 ----
        line = QFrame()
        line.setObjectName("HLine")
        line.setFixedHeight(1)
        sl.addWidget(line)

        # ---- 导航 ----
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

        # ---- 底部状态 ----
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

        # ---- 页头 ----
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

        # ---- 页面栈 ----
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
        """页面淡入 + 从右侧滑入。"""
        from ui_qt.widgets.animations import appear
        try:
            appear(widget, direction="right", distance=24,
                   duration=260, delay=0)
        except Exception:
            pass

    def _animate_title(self):
        """页头标题轻微滑入。"""
        from ui_qt.widgets.animations import appear
        try:
            appear(self._page_title, direction="down",
                   distance=8, duration=220, delay=30)
        except Exception:
            pass

    # ========================================================
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
        self.setStyleSheet(theme.qss())

        # 主窗口自有元素需重刷
        self._page_title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 22px; font-weight: bold; background: transparent;")
        if self.state.is_running:
            self._refresh_status_chip("green", "运行中")
        else:
            self._refresh_status_chip("text_dim", "离线")

        for p in self._pages:
            fn = getattr(p, "on_theme_changed", None) or getattr(p, "on_show", None)
            if fn:
                try:
                    fn()
                except Exception:
                    pass

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