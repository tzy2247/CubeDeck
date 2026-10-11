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

        self.setWindowTitle("下载服务端加载器")
        self.resize(680, 600)
        self._build()

        self.versions_loaded.connect(self._on_versions_loaded)
        self.install_done.connect(self._on_install_done)
        self.progress_updated.connect(self._on_progress)

        # 初始加载 MC 版本
        self._load_mc_versions()

    # ========================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        # 标题
        title = QLabel("下载服务端加载器")
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 18px; font-weight: bold; background: transparent;")
        root.addWidget(title)

        hint = QLabel(
            "选择加载器、MC 版本和具体构建，自动下载到目标目录并命名为 server.jar。")
        hint.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px; "
            f"background: transparent;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # 加载器
        root.addWidget(self._make_label("加载器"))
        self._loader_combo = QComboBox()
        for key, name, desc in LOADERS:
            self._loader_combo.addItem(f"{name}  ·  {desc}", key)
        self._loader_combo.setFixedHeight(38)
        self._loader_combo.currentIndexChanged.connect(self._on_loader_changed)
        root.addWidget(self._loader_combo)

        # MC 版本
        root.addWidget(self._make_label("Minecraft 版本"))
        self._mc_combo = QComboBox()
        self._mc_combo.setFixedHeight(38)
        self._mc_combo.addItem("加载中…")
        self._mc_combo.currentIndexChanged.connect(self._on_mc_changed)
        root.addWidget(self._mc_combo)

        # 加载器版本
        root.addWidget(self._make_label("加载器版本 / 构建"))
        self._build_combo = QComboBox()
        self._build_combo.setFixedHeight(38)
        self._build_combo.addItem("请先选择 MC 版本")
        root.addWidget(self._build_combo)

        # 目标目录
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

        # 状态
        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px; "
            f"background: transparent;")
        self._status.setWordWrap(True)
        self._status.setMinimumHeight(60)
        self._status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self._status)

        # 进度条
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

        # 按钮
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
        # ★ 先清空旧数据，避免残留
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

        proxy = self.state.config_data.get(
            "modrinth_proxy", "").strip() or None

        def worker():
            try:
                versions = list_mc_versions(loader, proxy=proxy)
                self.versions_loaded.emit({
                    "type": "mc_versions",
                    "loader": loader,
                    "versions": versions,
                    "error": "",
                })
            except LoaderDownloadError as e:
                import traceback
                traceback.print_exc()
                self.versions_loaded.emit({
                    "type": "mc_versions",
                    "loader": loader,
                    "versions": [],
                    "error": str(e),
                })
            except Exception as e:
                self.versions_loaded.emit({
                    "type": "mc_versions",
                    "loader": loader,
                    "versions": [],
                    "error": str(e),
                })

        threading.Thread(target=worker, daemon=True).start()

    # ========================================================
    #  MC 版本切换
    # ========================================================
    def _on_mc_changed(self, idx):
        mc_version = self._mc_combo.currentData()
        if not mc_version or mc_version in ("加载中…", "加载失败"):
            return

        # ★ 清空旧构建
        self._build_combo.clear()
        self._build_combo.addItem("加载中…")
        self._load_loader_versions(mc_version)

    def _load_loader_versions(self, mc_version):
        loader = self._loader_combo.currentData()
        if not loader:
            return

        proxy = self.state.config_data.get(
            "modrinth_proxy", "").strip() or None

        def worker():
            try:
                versions = list_loader_versions(
                    loader, mc_version, proxy=proxy)
                self.versions_loaded.emit({
                    "type": "loader_versions",
                    "loader": loader,
                    "mc_version": mc_version,
                    "builds": versions,
                    "error": "",
                })
            except LoaderDownloadError as e:
                import traceback
                traceback.print_exc()
                self.versions_loaded.emit({
                    "type": "loader_versions",
                    "loader": loader,
                    "mc_version": mc_version,
                    "builds": [],
                    "error": str(e),
                })
            except Exception as e:
                self.versions_loaded.emit({
                    "type": "loader_versions",
                    "loader": loader,
                    "mc_version": mc_version,
                    "builds": [],
                    "error": str(e),
                })

        threading.Thread(target=worker, daemon=True).start()

    # ========================================================
    #  信号处理
    # ========================================================
    @Slot(dict)
    def _on_versions_loaded(self, payload):
        ptype = payload.get("type", "")

        if ptype == "mc_versions":
            self._apply_mc_versions(payload)
        elif ptype == "loader_versions":
            self._apply_loader_versions(payload)

    def _apply_mc_versions(self, payload):
        # 检查是不是当前加载器的返回（防止竞态）
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
            self._status.setText("该加载器没有可用的 MC 版本")
            return

        for v in versions:
            self._mc_combo.addItem(v, v)
        self._mc_combo.blockSignals(False)
        self._status.setText(f"共 {len(versions)} 个 MC 版本可用")

        # 手动触发一次 MC 版本变化
        self._on_mc_changed(self._mc_combo.currentIndex())

    def _apply_loader_versions(self, payload):
        # 检查当前上下文是否匹配（防止切换加载器后旧数据回调）
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
            self._status.setText("该加载器没有适用于此 MC 版本的构建")
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
            QMessageBox.warning(self, "提示", "请选择加载器")
            return
        if not mc_version or mc_version in ("加载中…", "加载失败", "没有可用版本"):
            QMessageBox.warning(self, "提示", "请选择有效的 MC 版本")
            return
        if not isinstance(build, object) or build is None:
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

        # 覆盖确认
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

        proxy = self.state.config_data.get(
            "modrinth_proxy", "").strip() or None
        java_path = (self.state.config_data.get("java_path", "").strip()
                     or None)

        def log_cb(msg, tag="info"):
            self.state.log(msg, tag)

        def progress_cb(current, total, name):
            self.progress_updated.emit(current, total, name)

        def worker():
            ok, msg = download_loader(
                loader, mc_version, build.loader_version,
                target, java_path=java_path, proxy=proxy,
                log=log_cb, progress=progress_cb)
            self.install_done.emit(ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    @Slot(int, int, str)
    def _on_progress(self, current, total, name):
        self._status.setText(f"{name}（{current}/{total}）")
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(current)
        else:
            self._progress.setRange(0, 0)

    @Slot(bool, str)
    def _on_install_done(self, ok, msg):
        self._installing = False
        self._install_btn.setEnabled(True)
        self._install_btn.setText("下载并安装")
        self._progress.setVisible(False)

        if ok:
            self._status.setText("✔ 安装完成")
            self._status.setToolTip("")
            QMessageBox.information(self, "安装完成", msg)
            self.accept()
        else:
            self._status.setText(f"✖ 安装失败：\n{msg}")
            self._status.setToolTip(msg)
            QMessageBox.critical(self, "安装失败", msg)