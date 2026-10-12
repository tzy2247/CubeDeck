"""下载加载器的对话框。"""
import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QFileDialog, QMessageBox, QProgressBar,
)

from ui_qt.theme import theme
from core.loader_downloader import (
    LOADERS, list_mc_versions, list_loader_versions,
    download_loader, LoaderDownloadError,
)


class ServerSetupDialog(QDialog):
    versions_loaded = Signal(dict)
    install_done = Signal(bool, str)
    progress_updated = Signal(int, int, str)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._installing = False
        self._cancelled = False        # 关闭/取消后置为 True

        self.setWindowTitle("下载服务端")
        self.resize(680, 600)
        self._build()

        self.versions_loaded.connect(self._on_versions_loaded)
        self.install_done.connect(self._on_install_done)
        self.progress_updated.connect(self._on_progress)

        self._load_mc_versions()

    # ========================================================
    #  辅助：读取配置
    # ========================================================
    def _get_proxy(self):
        return self.state.config_data.get(
            "modrinth_proxy", "").strip() or None

    def _get_prefer(self):
        """★ 下载源优先级：official / mirror"""
        return self.state.config_data.get(
            "download_prefer", "official")

    # ========================================================
    #  生命周期管理
    # ========================================================
    def closeEvent(self, event):
        """关闭时立标记取消，断开信号，避免 worker 访问已死对象。"""
        self._cancelled = True
        try:
            self.versions_loaded.disconnect()
        except Exception:
            pass
        try:
            self.install_done.disconnect()
        except Exception:
            pass
        try:
            self.progress_updated.disconnect()
        except Exception:
            pass
        super().closeEvent(event)

    def reject(self):
        self._cancelled = True
        super().reject()

    def done(self, code):
        self._cancelled = True
        super().done(code)

    # ========================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("下载服务端")
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 18px; font-weight: bold; background: transparent;")
        root.addWidget(title)

        hint = QLabel(
            "选择服务端类型、MC 版本和具体构建，自动下载到目标目录并命名为 server.jar。")
        hint.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px; "
            f"background: transparent;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        root.addWidget(self._make_label("服务端类型"))
        self._loader_combo = QComboBox()
        for key, name, desc in LOADERS:
            self._loader_combo.addItem(f"{name}  ·  {desc}", key)
        self._loader_combo.setFixedHeight(38)
        self._loader_combo.currentIndexChanged.connect(self._on_loader_changed)
        root.addWidget(self._loader_combo)

        root.addWidget(self._make_label("Minecraft 版本"))
        self._mc_combo = QComboBox()
        self._mc_combo.setFixedHeight(38)
        self._mc_combo.addItem("加载中…")
        self._mc_combo.currentIndexChanged.connect(self._on_mc_changed)
        root.addWidget(self._mc_combo)

        root.addWidget(self._make_label("加载器版本 / 构建"))
        self._build_combo = QComboBox()
        self._build_combo.setFixedHeight(38)
        self._build_combo.addItem("请先选择 MC 版本")
        root.addWidget(self._build_combo)

        root.addWidget(self._make_label("安装目录"))
        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self._dir_entry = QLineEdit()
        self._dir_entry.setFixedHeight(38)
        self._dir_entry.setText(str(self._get_default_dir()))
        dir_row.addWidget(self._dir_entry, 1)

        browse_btn = QPushButton("浏览…")
        browse_btn.setObjectName("Ghost")
        browse_btn.setFixedSize(80, 38)
        browse_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(browse_btn)
        root.addLayout(dir_row)

        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px; "
            f"background: transparent;")
        self._status.setWordWrap(True)
        self._status.setMinimumHeight(60)
        self._status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self._status)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(8)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background-color: {theme.c('card')}; "
            f"border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background-color: {theme.c('accent')}; "
            f"border-radius: 4px; }}")
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        root.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("Ghost")
        cancel_btn.setFixedSize(100, 40)
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)

        self._install_btn = QPushButton("下载并安装")
        self._install_btn.setObjectName("Accent")
        self._install_btn.setFixedSize(140, 40)
        self._install_btn.clicked.connect(self._do_install)
        btns.addWidget(self._install_btn)

        root.addLayout(btns)

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 12px; "
            f"background: transparent;")
        return lbl

    def _get_default_dir(self):
        try:
            return self.state.server_path
        except Exception:
            return Path(".")

    # ========================================================
    #  加载器切换
    # ========================================================
    def _on_loader_changed(self, idx):
        self._mc_combo.blockSignals(True)
        self._mc_combo.clear()
        self._mc_combo.addItem("加载中…")
        self._mc_combo.blockSignals(False)

        self._build_combo.clear()
        self._build_combo.addItem("请先选择 MC 版本")
        self._status.setText("")
        self._status.setToolTip("")
        self._load_mc_versions()

    def _load_mc_versions(self):
        loader = self._loader_combo.currentData()
        if not loader:
            return

        proxy = self._get_proxy()
        prefer = self._get_prefer()   # ★

        def worker():
            versions = []
            err = ""
            try:
                versions = list_mc_versions(
                    loader, proxy=proxy, prefer=prefer)
            except LoaderDownloadError as e:
                import traceback
                traceback.print_exc()
                err = str(e)
            except Exception as e:
                err = str(e)

            if self._cancelled:
                return

            try:
                self.versions_loaded.emit({
                    "type": "mc_versions",
                    "loader": loader,
                    "versions": versions,
                    "error": err,
                })
            except RuntimeError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    # ========================================================
    #  MC 版本切换
    # ========================================================
    def _on_mc_changed(self, idx):
        mc_version = self._mc_combo.currentData()
        if not mc_version or mc_version in ("加载中…", "加载失败"):
            return

        self._build_combo.clear()
        self._build_combo.addItem("加载中…")
        self._load_loader_versions(mc_version)

    def _load_loader_versions(self, mc_version):
        loader = self._loader_combo.currentData()
        if not loader:
            return

        proxy = self._get_proxy()
        prefer = self._get_prefer()   # ★

        def worker():
            versions = []
            err = ""
            try:
                versions = list_loader_versions(
                    loader, mc_version, proxy=proxy, prefer=prefer)
            except LoaderDownloadError as e:
                import traceback
                traceback.print_exc()
                err = str(e)
            except Exception as e:
                err = str(e)

            if self._cancelled:
                return

            try:
                self.versions_loaded.emit({
                    "type": "loader_versions",
                    "loader": loader,
                    "mc_version": mc_version,
                    "builds": versions,
                    "error": err,
                })
            except RuntimeError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    # ========================================================
    #  信号处理
    # ========================================================
    @Slot(dict)
    def _on_versions_loaded(self, payload):
        if self._cancelled:
            return

        ptype = payload.get("type", "")
        if ptype == "mc_versions":
            self._apply_mc_versions(payload)
        elif ptype == "loader_versions":
            self._apply_loader_versions(payload)

    def _apply_mc_versions(self, payload):
        if payload.get("loader") != self._loader_combo.currentData():
            return

        self._mc_combo.blockSignals(True)
        self._mc_combo.clear()

        if payload.get("error"):
            self._mc_combo.addItem("加载失败")
            self._mc_combo.blockSignals(False)
            err = payload["error"]
            self._status.setText(f"加载 MC 版本失败：\n{err}")
            self._status.setToolTip(err)
            return

        versions = payload.get("versions", [])
        if not versions:
            self._mc_combo.addItem("没有可用版本")
            self._mc_combo.blockSignals(False)
            self._status.setText("该服务端类型没有可用的 MC 版本")
            return

        for v in versions:
            self._mc_combo.addItem(v, v)
        self._mc_combo.blockSignals(False)
        self._status.setText(f"共 {len(versions)} 个 MC 版本可用")

        self._on_mc_changed(self._mc_combo.currentIndex())

    def _apply_loader_versions(self, payload):
        if payload.get("loader") != self._loader_combo.currentData():
            return
        if payload.get("mc_version") != self._mc_combo.currentData():
            return

        self._build_combo.clear()

        if payload.get("error"):
            self._build_combo.addItem("加载失败")
            err = payload["error"]
            self._status.setText(f"加载版本失败：\n{err}")
            self._status.setToolTip(err)
            return

        builds = payload.get("builds", [])
        if not builds:
            self._build_combo.addItem("没有可用版本")
            self._status.setText("该服务端类型没有适用于此 MC 版本的构建")
            return

        for v in builds[:200]:
            self._build_combo.addItem(v.display, v)

        self._status.setText(
            f"共 {len(builds)} 个可用版本"
            + ("（显示前 200 个）" if len(builds) > 200 else ""))

    # ========================================================
    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择安装目录", self._dir_entry.text() or ".")
        if path:
            self._dir_entry.setText(path)

    # ========================================================
    #  安装
    # ========================================================
    def _do_install(self):
        if self._installing:
            return

        loader = self._loader_combo.currentData()
        mc_version = self._mc_combo.currentData()
        build = self._build_combo.currentData()
        target_dir = self._dir_entry.text().strip()

        if not loader:
            QMessageBox.warning(self, "提示", "请选择服务端类型")
            return
        if not mc_version or mc_version in ("加载中…", "加载失败", "没有可用版本"):
            QMessageBox.warning(self, "提示", "请选择有效的 MC 版本")
            return
        if build is None:
            QMessageBox.warning(self, "提示", "请选择加载器版本")
            return
        if not target_dir:
            QMessageBox.warning(self, "提示", "请填写安装目录")
            return

        target = Path(target_dir)
        if not target.exists():
            reply = QMessageBox.question(
                self, "目录不存在",
                f"{target}\n\n目录不存在，是否创建？",
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        jar_path = target / "server.jar"
        if jar_path.exists():
            reply = QMessageBox.question(
                self, "覆盖确认",
                f"{jar_path}\n\n已存在，是否覆盖？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        self._installing = True
        self._install_btn.setEnabled(False)
        self._install_btn.setText("安装中…")
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._status.setText("准备中…")

        proxy = self._get_proxy()
        prefer = self._get_prefer()   # ★
        java_path = (self.state.config_data.get("java_path", "").strip()
                     or None)

        def log_cb(msg, tag="info"):
            self.state.log(msg, tag)

        def progress_cb(current, total, name):
            if self._cancelled:
                return
            try:
                self.progress_updated.emit(current, total, name)
            except RuntimeError:
                pass

        def worker():
            ok, msg = download_loader(
                loader, mc_version, build.loader_version,
                target, java_path=java_path, proxy=proxy,
                log=log_cb, progress=progress_cb,
                prefer=prefer)   # ★

            if self._cancelled:
                return

            try:
                self.install_done.emit(ok, msg)
            except RuntimeError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    @Slot(int, int, str)
    def _on_progress(self, current, total, name):
        if self._cancelled:
            return
        self._status.setText(f"{name}（{current}/{total}）")
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(current)
        else:
            self._progress.setRange(0, 0)

    @Slot(bool, str)
    def _on_install_done(self, ok, msg):
        if self._cancelled:
            return

        self._installing = False
        self._install_btn.setEnabled(True)
        self._install_btn.setText("下载并安装")
        self._progress.setVisible(False)

        if not ok:
            self._status.setText(f"✖ 安装失败：\n{msg}")
            self._status.setToolTip(msg)
            QMessageBox.critical(self, "安装失败", msg)
            return

        self._status.setText("✔ 安装完成")
        self._status.setToolTip("")

        # 首次安装：创建并激活服务器
        if not self.state.has_server():
            target_dir = Path(self._dir_entry.text().strip())
            name = target_dir.name or "我的服务器"
            try:
                self.state.activate_server(name, str(target_dir))
            except Exception as e:
                import traceback
                traceback.print_exc()
                QMessageBox.critical(self, "激活服务器失败", f"{e}")

            # 通知主窗口刷新侧边栏
            try:
                parent = self.parent()
                if parent and hasattr(parent, "_server_selector"):
                    parent._server_selector.reload()
                elif parent and hasattr(parent, "window"):
                    w = parent.window()
                    if w and hasattr(w, "_server_selector"):
                        w._server_selector.reload()
            except Exception:
                pass

        QMessageBox.information(self, "安装完成", msg)
        self.accept()