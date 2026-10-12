"""插件 / 模组 / 整合包商店，支持 Modrinth 和 CurseForge 双源。

包含两个视图（QStackedWidget 切换）：
  0 = 搜索结果
  1 = 版本选择
另支持导入 .mrpack 整合包。
"""
import hashlib
import threading
import zipfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QScrollArea, QFrame, QMessageBox,
    QStackedWidget, QFileDialog, QProgressDialog,
)

import requests

from ui_qt.theme import theme
from ui_qt.pages.base import BasePage
from ui_qt.widgets.card import Card
from core.store_manager import StoreManager
from core.modrinth import USER_AGENT
from core.mrpack_installer import (
    install_mrpack, count_server_files, MrpackError,
)
from core.downloader import Downloader
from core import paths


LOADERS = [
    ("全部", None),
    ("Paper", "paper"),
    ("Spigot", "spigot"),
    ("Bukkit", "bukkit"),
    ("Purpur", "purpur"),
    ("Fabric", "fabric"),
    ("Forge", "forge"),
    ("NeoForge", "neoforge"),
    ("Quilt", "quilt"),
]

PROJECT_TYPES = [
    ("插件（服务端）", "plugin", "plugins"),
    ("模组", "mod", "mods"),
    ("整合包", "modpack", "__modpack__"),
    ("数据包", "datapack", "world/datapacks"),
    ("资源包", "resourcepack", "resourcepacks"),
]

CF_PROJECT_TYPES = [
    ("模组", "mod", "mods"),
    ("整合包", "modpack", "__modpack__"),
    ("资源包", "resourcepack", "resourcepacks"),
]

DEFAULT_INDEX = "downloads"
DEFAULT_LIMIT = 20
ICON_SIZE = 48


# ============================================================
#  图标缓存
# ============================================================
def _icon_cache_dir():
    d = paths.USERDATA_ROOT / "cache" / "icons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _icon_cache_path(url):
    if not url:
        return None
    h = hashlib.md5(url.encode()).hexdigest()
    return _icon_cache_dir() / f"{h}.img"


def _load_icon_bytes(url, proxy=None):
    if not url:
        return None

    cache_path = _icon_cache_path(url)
    if cache_path and cache_path.exists():
        try:
            return cache_path.read_bytes()
        except Exception:
            pass

    try:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        session.verify = False
        if proxy:
            session.proxies = {"http": proxy, "https": proxy}
        try:
            import urllib3
            urllib3.disable_warnings()
        except Exception:
            pass

        resp = session.get(url, timeout=15)
        if resp.ok and resp.content:
            data = resp.content
            if cache_path:
                try:
                    cache_path.write_bytes(data)
                except Exception:
                    pass
            return data
    except Exception:
        pass
    return None


def _fmt_size(n):
    if not n:
        return "未知"
    f = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if f < 1024:
            return f"{f:.1f} {unit}"
        f /= 1024
    return f"{f:.1f} TB"


# ============================================================
#  安装进度对话框
# ============================================================
class InstallProgressDialog(QProgressDialog):
    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(f"安装 · {title}")
        self.setLabelText("准备中…")
        self.setCancelButtonText("后台运行")
        self.setRange(0, 0)
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumWidth(440)
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)
        self.canceled.connect(self.hide)


# ============================================================
#  主页面
# ============================================================
class PluginStorePage(BasePage):
    search_done = Signal(dict)
    files_loaded = Signal(dict)
    install_done = Signal(str, str)
    install_failed = Signal(str)
    icon_loaded = Signal(str, bytes)
    progress_bytes = Signal(int, int, str)
    progress_step = Signal(int, int, str)

    def __init__(self, state, parent=None):
        super().__init__(state, parent)

        self.store = StoreManager(state.config_data)
        self.store.set_source(
            state.config_data.get("store_source", "modrinth"))

        self._results = []
        self._current_offset = 0
        self._page_size = DEFAULT_LIMIT
        self._total_hits = 0
        self._installing = False
        self._loaded_once = False

        self._icon_labels = {}
        self._current_hit = None
        self._current_files = []
        self._progress_dlg = None

        self._build()

        self.search_done.connect(self._on_search_result)
        self.files_loaded.connect(self._on_files_loaded)
        self.install_done.connect(self._on_install_finished)
        self.install_failed.connect(self._on_install_failed)
        self.icon_loaded.connect(self._on_icon_loaded)
        self.progress_bytes.connect(self._on_progress_bytes)
        self.progress_step.connect(self._on_progress_step)

    # ========================================================
    #  ★ 安全 emit 辅助
    # ========================================================
    def _safe_emit(self, signal, *args):
        """在 worker 线程里安全 emit，页面已销毁或已取消时静默返回。"""
        if self._cancelled:
            return
        try:
            signal.emit(*args)
        except (RuntimeError, AttributeError):
            pass

    # ========================================================
    #  构建
    # ========================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        root.addWidget(self._stack)

        self._search_view = self._build_search_view()
        self._stack.addWidget(self._search_view)

        self._versions_view = self._build_versions_view()
        self._stack.addWidget(self._versions_view)

        self._stack.setCurrentIndex(0)

    # --------------------------------------------------------
    #  搜索视图
    # --------------------------------------------------------
    def _build_search_view(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        search_card = Card()
        sl = search_card.body()
        sl.setContentsMargins(20, 14, 20, 14)
        sl.setSpacing(10)

        row0 = QHBoxLayout()
        row0.setSpacing(10)
        row0.addWidget(self._make_label("来源"))
        self._source_combo = QComboBox()
        for key, label in self.store.list_sources():
            self._source_combo.addItem(label, key)
        self._source_combo.setFixedHeight(34)
        self._source_combo.setFixedWidth(160)
        saved_source = self.state.config_data.get("store_source", "modrinth")
        idx = self._source_combo.findData(saved_source)
        if idx >= 0:
            self._source_combo.setCurrentIndex(idx)
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)
        row0.addWidget(self._source_combo)

        import_btn = QPushButton("导入 .mrpack")
        import_btn.setObjectName("Ghost")
        import_btn.setFixedHeight(34)
        import_btn.setFixedWidth(140)
        import_btn.clicked.connect(self._import_mrpack)
        row0.addWidget(import_btn)

        row0.addStretch()

        self._cf_status = QLabel("")
        self._cf_status.setStyleSheet(
            f"color: {theme.c('orange')}; font-size: 11px; "
            f"background: transparent;")
        row0.addWidget(self._cf_status)
        sl.addLayout(row0)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self._search_entry = QLineEdit()
        self._search_entry.setPlaceholderText(
            "搜索…（如 LuckPerms、Sodium、Fabulously Optimized）")
        self._search_entry.setFixedHeight(38)
        self._search_entry.returnPressed.connect(self._do_search)
        row1.addWidget(self._search_entry, 1)

        search_btn = QPushButton("搜索")
        search_btn.setObjectName("Accent")
        search_btn.setFixedHeight(38)
        search_btn.setFixedWidth(80)
        search_btn.clicked.connect(self._do_search)
        row1.addWidget(search_btn)
        sl.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        row2.addWidget(self._make_label("类型"))
        self._type_combo = QComboBox()
        self._rebuild_type_combo(saved_source)
        self._type_combo.setFixedHeight(34)
        self._type_combo.setFixedWidth(180)
        self._type_combo.currentIndexChanged.connect(self._do_search)
        row2.addWidget(self._type_combo)

        row2.addWidget(self._make_label("加载器"))
        self._loader_combo = QComboBox()
        for label, key in LOADERS:
            self._loader_combo.addItem(label, key)
        self._loader_combo.setFixedHeight(34)
        self._loader_combo.setFixedWidth(160)
        self._loader_combo.currentIndexChanged.connect(self._do_search)
        row2.addWidget(self._loader_combo)

        row2.addWidget(self._make_label("游戏版本"))
        self._version_entry = QLineEdit()
        self._version_entry.setPlaceholderText("如 1.21.4")
        self._version_entry.setFixedHeight(34)
        self._version_entry.setFixedWidth(100)
        self._version_entry.returnPressed.connect(self._do_search)
        row2.addWidget(self._version_entry)

        row2.addStretch()
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px; "
            f"background: transparent;")
        row2.addWidget(self._status_label)
        sl.addLayout(row2)
        root.addWidget(search_card)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 8, 0)
        self._list_layout.setSpacing(8)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        self._prev_btn = QPushButton("上一页")
        self._prev_btn.setObjectName("Ghost")
        self._prev_btn.setFixedHeight(34)
        self._prev_btn.clicked.connect(self._prev_page)
        self._prev_btn.setEnabled(False)
        bottom.addWidget(self._prev_btn)

        self._page_label = QLabel("第 1 页")
        self._page_label.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px; "
            f"background: transparent;")
        bottom.addWidget(self._page_label)

        self._next_btn = QPushButton("下一页")
        self._next_btn.setObjectName("Ghost")
        self._next_btn.setFixedHeight(34)
        self._next_btn.clicked.connect(self._next_page)
        bottom.addWidget(self._next_btn)
        bottom.addStretch()
        root.addLayout(bottom)

        self._show_placeholder("正在加载热门内容…")
        return w

    # --------------------------------------------------------
    #  版本视图
    # --------------------------------------------------------
    def _build_versions_view(self):
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        top_card = Card()
        tl = top_card.body()
        tl.setContentsMargins(20, 14, 20, 14)
        tr = QHBoxLayout()
        tr.setSpacing(12)

        back_btn = QPushButton("← 返回")
        back_btn.setObjectName("Ghost")
        back_btn.setFixedHeight(36)
        back_btn.setFixedWidth(90)
        back_btn.clicked.connect(self._back_to_search)
        tr.addWidget(back_btn)

        self._versions_title = QLabel("选择版本")
        self._versions_title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 15px; font-weight: bold; background: transparent;")
        tr.addWidget(self._versions_title)
        tr.addStretch()

        self._versions_status = QLabel("")
        self._versions_status.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px; "
            f"background: transparent;")
        tr.addWidget(self._versions_status)

        tl.addLayout(tr)
        root.addWidget(top_card)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._versions_widget = QWidget()
        self._versions_layout = QVBoxLayout(self._versions_widget)
        self._versions_layout.setContentsMargins(0, 0, 8, 0)
        self._versions_layout.setSpacing(8)
        self._versions_layout.addStretch()
        scroll.setWidget(self._versions_widget)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        self._auto_install_btn = QPushButton("自动安装最新版（含依赖）")
        self._auto_install_btn.setObjectName("Accent")
        self._auto_install_btn.setFixedHeight(38)
        self._auto_install_btn.clicked.connect(self._auto_install)
        self._auto_install_btn.setEnabled(False)
        bottom.addWidget(self._auto_install_btn)

        bottom.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("Ghost")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setFixedWidth(90)
        cancel_btn.clicked.connect(self._back_to_search)
        bottom.addWidget(cancel_btn)

        root.addLayout(bottom)
        return w

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 12px; "
            f"background: transparent;")
        return lbl

    # ========================================================
    #  类型下拉框
    # ========================================================
    def _get_project_types_for_source(self, source):
        if source == "curseforge":
            return CF_PROJECT_TYPES
        return PROJECT_TYPES

    def _rebuild_type_combo(self, source):
        types = self._get_project_types_for_source(source)

        if self._type_combo.count() > 0:
            old_data = self._type_combo.currentData()
        else:
            old_data = None

        self._type_combo.blockSignals(True)
        self._type_combo.clear()
        for label, key, _ in types:
            self._type_combo.addItem(label, key)

        idx = self._type_combo.findData(old_data)
        self._type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._type_combo.blockSignals(False)

    def _cf_needs_key(self):
        api_base = self.state.config_data.get(
            "curseforge_api_base", "").strip()
        if not api_base:
            return False
        if "api.curseforge.com" in api_base:
            return True
        return False

    # ========================================================
    #  视图切换
    # ========================================================
    def _back_to_search(self):
        self._stack.setCurrentIndex(0)

    def _show_versions_view(self, hit):
        self._current_hit = hit
        self._current_files = []
        self._versions_title.setText(f"选择版本 · {hit.title}")

        self._clear_versions_layout()
        loading = QLabel("正在加载版本列表…")
        loading.setAlignment(Qt.AlignCenter)
        loading.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 14px; "
            f"padding: 60px; background: transparent;")
        self._versions_layout.addWidget(loading)
        self._versions_layout.addStretch()

        self._versions_status.setText("加载中…")
        self._auto_install_btn.setEnabled(False)
        self._stack.setCurrentIndex(1)

    # ========================================================
    #  源切换
    # ========================================================
    def _on_source_changed(self, idx):
        source = self._source_combo.currentData()
        if not source:
            return
        self.store.set_source(source)
        self.state.config_data["store_source"] = source
        self.state.save_config()

        self._rebuild_type_combo(source)

        if source == "curseforge":
            if self._cf_needs_key():
                key = self.state.config_data.get(
                    "curseforge_api_key", "").strip()
                if not key:
                    self._cf_status.setText("使用官方 API 需配置 Key")
                    self._show_placeholder(
                        "当前配置为 CurseForge 官方 API\n\n"
                        "请到 设置 → CurseForge 填写 API Key，\n"
                        "或清空 API 地址以使用内置 MCIM 镜像。")
                    return
            else:
                self._cf_status.setText("使用 MCIM 镜像")
        else:
            self._cf_status.setText("")

        self._do_search(reset=True)

    # ========================================================
    #  搜索
    # ========================================================
    def _do_search(self, reset=True):
        if not hasattr(self, "_search_entry"):
            return

        if self.store.get_source() == "curseforge":
            if self._cf_needs_key():
                key = self.state.config_data.get(
                    "curseforge_api_key", "").strip()
                if not key:
                    return

        # ★ 每次发起新搜索，重置取消标志
        self._cancelled = False

        query = self._search_entry.text().strip()
        if reset:
            self._current_offset = 0

        project_type = self._type_combo.currentData()
        loader = self._loader_combo.currentData()
        game_version = self._version_entry.text().strip() or None

        if self.store.get_source() == "curseforge":
            if project_type == "plugin":
                project_type = "mod"
            elif project_type == "datapack":
                project_type = "mod"

        index = DEFAULT_INDEX if not query else "relevance"
        self._status_label.setText("搜索中…")

        offset = self._current_offset
        page_size = self._page_size

        def worker():
            try:
                result = self.store.search(
                    query=query,
                    project_type=project_type,
                    game_version=game_version,
                    loader=loader,
                    index=index,
                    offset=offset,
                    limit=page_size,
                )
            except Exception as e:
                result = {"error": str(e)}

            # ★ 页面已销毁/已取消 → 不 emit
            if self._cancelled:
                return
            try:
                self.search_done.emit(result)
            except (RuntimeError, AttributeError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    @Slot(dict)
    def _on_search_result(self, result):
        if self._cancelled:
            return

        if "error" in result:
            self._status_label.setText("搜索失败")
            self._show_placeholder(
                f"搜索失败：{result['error']}\n\n"
                f"可尝试切换来源、配置代理或稍后重试。")
            return

        hits = result.get("hits", [])
        total = result.get("total_hits", 0)

        self._results = hits
        self._total_hits = total

        page = self._current_offset // self._page_size + 1
        if self._search_entry.text().strip():
            self._status_label.setText(
                f"找到 {total} 个结果 · 第 {page} 页")
        else:
            self._status_label.setText(f"热门内容 · 第 {page} 页")

        self._clear_list()
        if not hits:
            self._show_placeholder(
                "没有找到匹配的项目\n\n"
                "试试换关键词，或清空加载器/版本过滤。")
            self._update_pagination()
            return

        for hit in hits:
            self._list_layout.addWidget(self._make_result_item(hit))

        self._list_layout.addStretch()
        self._update_pagination()

    def _update_pagination(self):
        page = self._current_offset // self._page_size + 1
        self._page_label.setText(f"第 {page} 页")
        self._prev_btn.setEnabled(self._current_offset > 0)
        has_next = len(self._results) >= self._page_size
        self._next_btn.setEnabled(has_next)

    def _prev_page(self):
        if self._current_offset > 0:
            self._current_offset -= self._page_size
            self._do_search(reset=False)

    def _next_page(self):
        self._current_offset += self._page_size
        self._do_search(reset=False)

    # ========================================================
    #  搜索结果项
    # ========================================================
    def _make_result_item(self, hit):
        item = QFrame()
        item.setObjectName("Card")
        il = QHBoxLayout(item)
        il.setContentsMargins(16, 12, 16, 12)
        il.setSpacing(14)

        icon_label = QLabel("·")
        icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(
            f"background-color: {theme.c('card_hover')}; "
            f"border-radius: 8px; "
            f"color: {theme.c('text_faint')}; font-size: 18px;")
        il.addWidget(icon_label)

        self._icon_labels[hit.project_id] = icon_label
        if hit.icon_url:
            self._load_icon_async(hit.project_id, hit.icon_url)

        info = QVBoxLayout()
        info.setSpacing(4)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)

        title = QLabel(hit.title or "未知")
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 14px; font-weight: bold; background: transparent;")
        name_row.addWidget(title)

        if hit.author:
            author = QLabel(f"by {hit.author}")
            author.setStyleSheet(
                f"color: {theme.c('text_faint')}; font-size: 11px; "
                f"background: transparent;")
            name_row.addWidget(author)

        tags = []
        if hit.server_side in ("required", "optional"):
            tags.append("服务端")
        if hit.client_side in ("required", "optional"):
            tags.append("客户端")
        if tags:
            tag_lbl = QLabel(" · ".join(tags))
            tag_lbl.setStyleSheet(
                f"color: {theme.c('accent')}; font-size: 10px; "
                f"background: transparent; padding-left: 8px;")
            name_row.addWidget(tag_lbl)

        name_row.addStretch()
        info.addLayout(name_row)

        desc = QLabel((hit.description or "")[:200])
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px; "
            f"background: transparent;")
        info.addWidget(desc)

        stats_parts = []
        if hit.downloads:
            stats_parts.append(f"下载 {hit.downloads:,}")
        if hit.follows:
            stats_parts.append(f"关注 {hit.follows:,}")
        stats_parts.append(f"来源 {hit.source}")
        stats = QLabel("  ·  ".join(stats_parts))
        stats.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        info.addWidget(stats)

        il.addLayout(info, 1)

        install_btn = QPushButton("安装")
        install_btn.setObjectName("Green")
        install_btn.setFixedSize(80, 36)
        install_btn.clicked.connect(
            lambda _=False, h=hit: self._install(h))
        il.addWidget(install_btn)

        return item

    def _load_icon_async(self, project_id, icon_url):
        proxy = self.state.config_data.get(
            "modrinth_proxy", "").strip() or None

        def worker():
            data = _load_icon_bytes(icon_url, proxy=proxy)
            if not data:
                return
            if self._cancelled:
                return
            try:
                self.icon_loaded.emit(project_id, data)
            except (RuntimeError, AttributeError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    @Slot(str, bytes)
    def _on_icon_loaded(self, project_id, data):
        if self._cancelled:
            return
        label = self._icon_labels.get(project_id)
        if label is None:
            return

        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        pixmap = pixmap.scaled(
            ICON_SIZE - 8, ICON_SIZE - 8,
            Qt.KeepAspectRatio, Qt.SmoothTransformation)
        try:
            label.setText("")
            label.setPixmap(pixmap)
        except Exception:
            pass

    def _show_placeholder(self, text):
        self._clear_list()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 14px; "
            f"padding: 60px; background: transparent;")
        self._list_layout.addWidget(lbl)
        self._list_layout.addStretch()

    def _clear_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._icon_labels.clear()

    # ========================================================
    #  打开版本列表
    # ========================================================
    def _install(self, hit):
        if self._installing:
            QMessageBox.information(self, "提示", "已有安装任务进行中")
            return

        self._cancelled = False  # ★ 新操作，重置取消标志

        self._show_versions_view(hit)

        loader = self._loader_combo.currentData()
        game_version = self._version_entry.text().strip() or None

        def worker():
            try:
                files = self.store.get_files(
                    hit.project_id,
                    game_version=game_version,
                    loader=loader,
                )
                payload = {
                    "hit": hit,
                    "files": files,
                    "error": "",
                }
            except Exception as e:
                payload = {
                    "hit": hit,
                    "files": [],
                    "error": str(e),
                }

            if self._cancelled:
                return
            try:
                self.files_loaded.emit(payload)
            except (RuntimeError, AttributeError):
                pass

        threading.Thread(target=worker, daemon=True).start()

    @Slot(dict)
    def _on_files_loaded(self, payload):
        if self._cancelled:
            return

        hit = payload.get("hit")
        files = payload.get("files", [])
        err = payload.get("error", "")

        if self._current_hit is not hit:
            return

        self._current_files = files

        if err:
            self._clear_versions_layout()
            lbl = QLabel(f"加载失败：\n\n{err}")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"color: {theme.c('red')}; font-size: 13px; "
                f"padding: 60px; background: transparent;")
            self._versions_layout.addWidget(lbl)
            self._versions_layout.addStretch()
            self._versions_status.setText("失败")
            self._auto_install_btn.setEnabled(False)
            return

        if not files:
            self._clear_versions_layout()
            loader_cn = self._loader_combo.currentText()
            gv = self._version_entry.text().strip() or "任意"
            lbl = QLabel(
                f"没有找到兼容的版本。\n\n"
                f"当前过滤：\n"
                f"  加载器 = {loader_cn}\n"
                f"  游戏版本 = {gv}\n\n"
                f"试试把过滤条件改成「全部」和空版本。")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                f"color: {theme.c('text_faint')}; font-size: 13px; "
                f"padding: 60px; background: transparent;")
            self._versions_layout.addWidget(lbl)
            self._versions_layout.addStretch()
            self._versions_status.setText("0 个版本")
            self._auto_install_btn.setEnabled(False)
            return

        self._clear_versions_layout()
        for f in files[:300]:
            self._versions_layout.addWidget(self._make_version_row(f))
        self._versions_layout.addStretch()

        self._versions_status.setText(f"共 {len(files)} 个版本")
        self._auto_install_btn.setEnabled(True)

    def _make_version_row(self, file):
        row = QFrame()
        row.setObjectName("Card")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(16, 10, 16, 10)
        rl.setSpacing(12)

        info = QVBoxLayout()
        info.setSpacing(3)

        name = QLabel(file.filename)
        name.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 13px; "
            f"background: transparent;")
        name.setWordWrap(True)
        info.addWidget(name)

        gv_list = file.game_versions or []
        gv = ", ".join(gv_list[:5])
        if len(gv_list) > 5:
            gv += "…"
        gv = gv or "—"

        ld = ", ".join(file.loaders) if file.loaders else "—"
        rt_cn = {
            "release": "正式",
            "beta": "测试",
            "alpha": "开发",
        }.get(file.release_type, file.release_type)

        meta = QLabel(
            f"MC {gv}   ·   {ld}   ·   {rt_cn}   ·   {_fmt_size(file.size)}")
        meta.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        meta.setWordWrap(True)
        info.addWidget(meta)

        rl.addLayout(info, 1)

        btn = QPushButton("下载")
        btn.setObjectName("Green")
        btn.setFixedSize(80, 32)
        btn.clicked.connect(lambda _=False, f=file: self._download_one(f))
        rl.addWidget(btn)

        return row

    def _clear_versions_layout(self):
        while self._versions_layout.count():
            item = self._versions_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ========================================================
    #  目录选择
    # ========================================================
    def _get_project_meta(self):
        key = self._type_combo.currentData() or "mod"
        for _label, ptype, target in PROJECT_TYPES:
            if ptype == key:
                return ptype, target
        return "mod", "mods"

    def _default_target_dir(self, hit):
        project_type, target_subdir = self._get_project_meta()
        if target_subdir == "__modpack__":
            return self.state.server_path / "modpacks" / hit.title
        return self.state.server_path / target_subdir

    def _choose_target_dir(self, hit):
        default = self._default_target_dir(hit)
        try:
            default.mkdir(parents=True, exist_ok=True)
            start_dir = str(default)
        except Exception:
            start_dir = str(self.state.server_path)

        path = QFileDialog.getExistingDirectory(
            self,
            f"选择「{hit.title}」的下载位置",
            start_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not path:
            return None
        return Path(path)

    # ========================================================
    #  下载
    # ========================================================
    def _download_one(self, file):
        if self._installing:
            QMessageBox.information(self, "提示", "已有安装任务进行中")
            return
        hit = self._current_hit
        if hit is None:
            return

        target_dir = self._choose_target_dir(hit)
        if target_dir is None:
            return

        self._do_install(hit, file, target_dir, with_deps=False)

    def _auto_install(self):
        if self._installing:
            QMessageBox.information(self, "提示", "已有安装任务进行中")
            return
        hit = self._current_hit
        if hit is None:
            return

        target_dir = self._choose_target_dir(hit)
        if target_dir is None:
            return

        self._do_install(hit, None, target_dir, with_deps=True)

    def _do_install(self, hit, file, target_dir, with_deps=False):
        self._installing = True
        self._cancelled = False  # ★ 新任务，重置
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        if with_deps:
            self.state.log(f"开始安装「{hit.title}」（含依赖）", "info")
        else:
            self.state.log(
                f"开始安装「{hit.title}」（{file.filename}）", "info")

        self._progress_dlg = InstallProgressDialog(self, hit.title)
        self._progress_dlg.setLabelText("准备中…")
        self._progress_dlg.show()

        # 预先取参数（避免 worker 里访问 GUI）
        loader = self._loader_combo.currentData()
        game_version = self._version_entry.text().strip() or None

        def worker():
            try:
                if with_deps:
                    def step_cb(current, total, title):
                        if self._cancelled:
                            return
                        try:
                            self.progress_step.emit(current, total, title)
                        except (RuntimeError, AttributeError):
                            pass

                    ok, fail, skip, plan = (
                        self.store.installer.install_with_dependencies(
                            project_id=hit.project_id,
                            title=hit.title,
                            target_dir=target_dir,
                            game_version=game_version,
                            loader=loader,
                            progress_callback=step_cb,
                        ))
                    summary = (
                        f"成功 {ok}，失败 {fail}，跳过 {skip}\n"
                        f"目标目录：{target_dir}")
                else:
                    dest = target_dir / file.filename
                    urls = file.fallback_urls or [file.download_url]

                    def byte_cb(downloaded, total):
                        if self._cancelled:
                            return
                        try:
                            self.progress_bytes.emit(
                                downloaded, total, file.filename)
                        except (RuntimeError, AttributeError):
                            pass

                    self.store.download(urls, dest,
                                        progress_callback=byte_cb)
                    summary = (
                        f"文件：{file.filename}\n"
                        f"目标目录：{target_dir}")

                if self._cancelled:
                    return
                try:
                    self.install_done.emit(hit.title, summary)
                except (RuntimeError, AttributeError):
                    pass
            except Exception as e:
                import traceback
                traceback.print_exc()
                if self._cancelled:
                    return
                try:
                    self.install_failed.emit(str(e))
                except (RuntimeError, AttributeError):
                    pass

        threading.Thread(target=worker, daemon=True).start()

    # ========================================================
    #  进度更新
    # ========================================================
    @Slot(int, int, str)
    def _on_progress_bytes(self, downloaded, total, filename):
        if self._cancelled:
            return
        if not self._progress_dlg:
            return
        try:
            if total > 0:
                self._progress_dlg.setRange(0, 100)
                self._progress_dlg.setValue(
                    int(downloaded * 100 / total))
                self._progress_dlg.setLabelText(
                    f"下载中：{filename}\n"
                    f"{_fmt_size(downloaded)} / {_fmt_size(total)}")
            else:
                self._progress_dlg.setRange(0, 0)
                self._progress_dlg.setLabelText(
                    f"下载中：{filename}\n"
                    f"已下载 {_fmt_size(downloaded)}")
        except Exception:
            pass

    @Slot(int, int, str)
    def _on_progress_step(self, current, total, title):
        if self._cancelled:
            return
        if not self._progress_dlg:
            return
        try:
            self._progress_dlg.setRange(0, total)
            self._progress_dlg.setValue(current)
            self._progress_dlg.setLabelText(
                f"安装中（{current}/{total}）：{title}")
        except Exception:
            pass

    # ========================================================
    #  安装完成/失败
    # ========================================================
    @Slot(str, str)
    def _on_install_finished(self, title, summary):
        if self._cancelled:
            return
        self._installing = False

        if self._progress_dlg:
            try:
                self._progress_dlg.close()
                self._progress_dlg.deleteLater()
            except Exception:
                pass
            self._progress_dlg = None

        self.state.log(f"「{title}」安装完成", "ok")
        QMessageBox.information(
            self, "安装完成",
            f"「{title}」已安装。\n\n{summary}\n\n"
            f"⚠ 需要重启服务器才能生效。")
        self._back_to_search()

    @Slot(str)
    def _on_install_failed(self, error):
        if self._cancelled:
            return
        self._installing = False

        if self._progress_dlg:
            try:
                self._progress_dlg.close()
                self._progress_dlg.deleteLater()
            except Exception:
                pass
            self._progress_dlg = None

        self.state.log(f"安装失败：{error}", "error")
        QMessageBox.critical(self, "安装失败", error)

    # ========================================================
    #  导入 .mrpack
    # ========================================================
    def _import_mrpack(self):
        if self._installing:
            QMessageBox.information(self, "提示", "已有安装任务进行中")
            return

        mrpack_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 .mrpack 整合包",
            str(self.state.server_path.parent),
            "Modrinth 整合包 (*.mrpack);;所有文件 (*)",
        )
        if not mrpack_path:
            return

        try:
            n_files, info = count_server_files(mrpack_path)
        except MrpackError as e:
            QMessageBox.critical(self, "解析失败", str(e))
            return

        if n_files == 0:
            QMessageBox.warning(
                self, "提示",
                "该整合包没有适合服务端的文件。\n\n"
                "可能它只在客户端使用。")
            return

        msg = (
            f"整合包：{info.name}\n"
            f"版本：{info.version_id or '(未知)'}\n"
            f"MC 版本：{info.mc_version or '(未知)'}\n"
            f"加载器：{info.loader or '原版'} "
            f"{info.loader_version}\n\n"
            f"服务端需下载 {n_files} 个文件。\n\n"
            f"继续吗？")
        reply = QMessageBox.question(
            self, "导入整合包", msg,
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        default_dir = str(self.state.server_path)
        target_dir = QFileDialog.getExistingDirectory(
            self,
            "选择安装位置（通常直接选服务器根目录）",
            default_dir,
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not target_dir:
            return

        include_optional = False
        opt_count = sum(
            1 for f in info.files if f.server_env == "optional")
        if opt_count > 0:
            reply2 = QMessageBox.question(
                self, "可选文件",
                f"整合包中有 {opt_count} 个服务端标记为「可选」的文件。\n\n"
                f"是否一并下载？\n"
                f"（推荐：否，避免不必要的资源占用）",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)
            include_optional = (reply2 == QMessageBox.Yes)

        self._do_import_mrpack(
            Path(mrpack_path), Path(target_dir), include_optional)

    def _do_import_mrpack(self, mrpack_path, target_dir,
                          include_optional=False):
        self._installing = True
        self._cancelled = False  # ★ 新任务，重置

        self.state.log(
            f"开始导入整合包：{mrpack_path.name} → {target_dir}", "info")

        self._progress_dlg = InstallProgressDialog(
            self, mrpack_path.stem)
        self._progress_dlg.setLabelText("准备中…")
        self._progress_dlg.show()

        proxy = self.state.config_data.get(
            "modrinth_proxy", "").strip() or None
        downloader = Downloader(proxy=proxy, verify_ssl=False)

        def log_cb(msg, tag="info"):
            self.state.log(msg, tag)

        def progress_cb(current, total, name):
            if self._cancelled:
                return
            try:
                self.progress_step.emit(current, total, name)
            except (RuntimeError, AttributeError):
                pass

        def worker():
            try:
                ok, fail, skip, errors = install_mrpack(
                    mrpack_path, target_dir, downloader,
                    log=log_cb, progress=progress_cb,
                    include_optional=include_optional,
                )
                summary = (
                    f"成功 {ok}，失败 {fail}，跳过 {skip}\n"
                    f"安装位置：{target_dir}")
                if errors:
                    summary += f"\n\n部分失败：\n"
                    for path, err in errors[:5]:
                        summary += f"  · {path}: {err[:80]}\n"
                    if len(errors) > 5:
                        summary += f"  ... 还有 {len(errors) - 5} 个"

                if self._cancelled:
                    return
                try:
                    self.install_done.emit(mrpack_path.stem, summary)
                except (RuntimeError, AttributeError):
                    pass
            except Exception as e:
                import traceback
                traceback.print_exc()
                if self._cancelled:
                    return
                try:
                    self.install_failed.emit(str(e))
                except (RuntimeError, AttributeError):
                    pass

        threading.Thread(target=worker, daemon=True).start()

    # ========================================================
    #  生命周期
    # ========================================================
    def on_show(self):
        # ★ 进入页面时清除取消标志
        self._cancelled = False
        self.store.reload()
        if self._loaded_once:
            return
        self._loaded_once = True
        self._do_search(reset=True)