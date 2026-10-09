"""插件 / 模组 / 整合包商店，支持 Modrinth 和 CurseForge 双源。"""
import threading
import zipfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QScrollArea, QFrame, QMessageBox,
)

from ui_qt.theme import theme
from ui_qt.pages.base import BasePage
from ui_qt.widgets.card import Card
from core.store_manager import StoreManager


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

# (显示名, 内部类型, 安装目标)
PROJECT_TYPES = [
    ("插件（服务端）", "plugin", "plugins"),
    ("模组（服务端）", "mod", "mods"),
    ("整合包", "modpack", "__modpack__"),
    ("数据包", "datapack", "world/datapacks"),
    ("资源包", "resourcepack", "resourcepacks"),
]

DEFAULT_INDEX = "downloads"
DEFAULT_LIMIT = 20


class PluginStorePage(BasePage):
    search_done = Signal(dict)
    install_done = Signal(str, str)
    install_failed = Signal(str)

    def __init__(self, state, parent=None):
        super().__init__(state, parent)

        self.store = StoreManager(
            state.config_data, log_callback=state.log)
        self.store.set_source(
            state.config_data.get("store_source", "modrinth"))

        self._results = []
        self._current_offset = 0
        self._page_size = DEFAULT_LIMIT
        self._total_hits = 0
        self._installing = False
        self._loaded_once = False

        self._build()

        self.search_done.connect(self._on_search_result)
        self.install_done.connect(self._on_install_finished)
        self.install_failed.connect(self._on_install_failed)

    # ========================================================
    #  构建
    # ========================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ---- 搜索栏 ----
        search_card = Card()
        sl = search_card.body()
        sl.setContentsMargins(20, 14, 20, 14)
        sl.setSpacing(10)

        # 第 0 行：来源切换
        row0 = QHBoxLayout()
        row0.setSpacing(10)

        row0.addWidget(self._make_label("来源"))
        self._source_combo = QComboBox()
        for key, label in self.store.list_sources():
            self._source_combo.addItem(label, key)
        self._source_combo.setFixedHeight(34)
        self._source_combo.setFixedWidth(160)
        # 设置到上次使用的源
        saved_source = self.state.config_data.get("store_source", "modrinth")
        idx = self._source_combo.findData(saved_source)
        if idx >= 0:
            self._source_combo.setCurrentIndex(idx)
        self._source_combo.currentIndexChanged.connect(
            self._on_source_changed)
        row0.addWidget(self._source_combo)

        row0.addStretch()

        self._cf_status = QLabel("")
        self._cf_status.setStyleSheet(
            f"color: {theme.c('orange')};"
            f"font-size: 11px; background: transparent;")
        row0.addWidget(self._cf_status)

        sl.addLayout(row0)

        # 第 1 行：搜索框
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

        # 第 2 行：过滤
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        row2.addWidget(self._make_label("类型"))
        self._type_combo = QComboBox()
        for label, key, _ in PROJECT_TYPES:
            self._type_combo.addItem(label, key)
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

        # ---- 结果列表 ----
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

        # ---- 分页 ----
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

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 12px; "
            f"background: transparent;")
        return lbl

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

        # CurseForge 未配置 API Key 时提示
        if source == "curseforge":
            key = self.state.config_data.get(
                "curseforge_api_key", "").strip()
            if not key:
                self._cf_status.setText("未配置 API Key")
                self._show_placeholder(
                    "CurseForge 需要 API Key\n\n"
                    "请到 设置 → CurseForge 填写。\n"
                    "申请地址：https://console.curseforge.com/#/api-keys")
                return
            else:
                self._cf_status.setText("")
        else:
            self._cf_status.setText("")

        # 重新搜索
        self._do_search(reset=True)

    # ========================================================
    #  搜索
    # ========================================================
    def _do_search(self, reset=True):
        if not hasattr(self, "_search_entry"):
            return

        # 检查 CurseForge 是否已配置
        if self.store.get_source() == "curseforge":
            key = self.state.config_data.get(
                "curseforge_api_key", "").strip()
            if not key:
                return

        query = self._search_entry.text().strip()
        if reset:
            self._current_offset = 0

        project_type = self._type_combo.currentData()
        loader = self._loader_combo.currentData()
        game_version = self._version_entry.text().strip() or None

        # CurseForge 没有 plugin / shader 类型，做映射
        if self.store.get_source() == "curseforge":
            if project_type == "plugin":
                project_type = "mod"
            elif project_type == "shader":
                project_type = "resourcepack"
            elif project_type == "datapack":
                # CurseForge 数据包不在 mods 里，用 mod 兜底
                project_type = "mod"

        index = DEFAULT_INDEX if not query else "relevance"

        self._status_label.setText("搜索中…")

        def worker():
            try:
                result = self.store.search(
                    query=query,
                    project_type=project_type,
                    game_version=game_version,
                    loader=loader,
                    index=index,
                    offset=self._current_offset,
                    limit=self._page_size,
                )
            except Exception as e:
                result = {"error": str(e)}
            self.search_done.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    @Slot(dict)
    def _on_search_result(self, result):
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
            self._status_label.setText(
                f"热门内容 · 第 {page} 页")

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
        # CurseForge 不返回准确 total_hits，用"当前页满"近似判断
        has_next = (len(self._results) >= self._page_size)
        self._next_btn.setEnabled(has_next)

    def _prev_page(self):
        if self._current_offset > 0:
            self._current_offset -= self._page_size
            self._do_search(reset=False)

    def _next_page(self):
        self._current_offset += self._page_size
        self._do_search(reset=False)

    # ========================================================
    #  列表项
    # ========================================================
    def _make_result_item(self, hit):
        item = QFrame()
        item.setObjectName("Card")
        il = QHBoxLayout(item)
        il.setContentsMargins(20, 14, 20, 14)
        il.setSpacing(14)

        info = QVBoxLayout()
        info.setSpacing(4)

        # 名称行
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

        # 服务端 / 客户端标签
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

        # 描述
        desc = QLabel((hit.description or "")[:200])
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px; "
            f"background: transparent;")
        info.addWidget(desc)

        # 统计
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

    # ========================================================
    #  安装
    # ========================================================
    def _get_project_meta(self):
        idx = self._type_combo.currentIndex()
        if 0 <= idx < len(PROJECT_TYPES):
            _, key, target = PROJECT_TYPES[idx]
            return key, target
        return "plugin", "plugins"

    def _install(self, hit):
        if self._installing:
            QMessageBox.information(self, "提示", "已有安装任务进行中")
            return

        project_type, target_subdir = self._get_project_meta()

        warn_text = ""
        if project_type == "mod":
            warn_text = ("\n\n⚠ 服务端只能安装标注「服务端」的模组。\n"
                         "   会自动安装 required 依赖。")
        elif project_type == "modpack":
            warn_text = ("\n\n⚠ 整合包通常以客户端为主。\n"
                         "   安装后请手动挑选服务端模组。")

        reply = QMessageBox.question(
            self, "安装",
            f"确定要安装「{hit.title}」吗？{warn_text}",
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        loader = self._loader_combo.currentData()
        game_version = self._version_entry.text().strip() or None

        # 决定目标目录
        if target_subdir == "__modpack__":
            target_dir = self.state.server_path / "modpacks" / hit.title
        else:
            target_dir = self.state.server_path / target_subdir

        self._installing = True
        self.state.log(f"正在解析「{hit.title}」的依赖…", "info")

        def on_progress(current, total, title):
            self._status_label.setText(
                f"安装中 {current}/{total}：{title}")

        def worker():
            try:
                ok, fail, skip, plan = self.store.installer.install_with_dependencies(
                    project_id=hit.project_id,
                    title=hit.title,
                    target_dir=target_dir,
                    game_version=game_version,
                    loader=loader,
                    progress_callback=on_progress,
                )
                summary = (
                    f"安装完成：成功 {ok}，失败 {fail}，跳过 {skip}\n"
                    f"目标目录：{target_dir}")
                self.install_done.emit(hit.title, summary)
            except Exception as e:
                self.install_failed.emit(str(e))

        threading.Thread(target=worker, daemon=True).start()

    @Slot(str, str)
    def _on_install_finished(self, title, summary):
        self._installing = False
        self._status_label.setText("")
        self.state.log(f"「{title}」安装完成", "ok")
        QMessageBox.information(
            self, "安装完成",
            f"「{title}」安装完成。\n\n{summary}\n\n"
            f"⚠ 需要重启服务器才能生效。")

    def _extract_modpack(self, zip_path, dest_dir):
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(dest_dir)
        finally:
            try:
                zip_path.unlink()
            except Exception:
                pass

    @Slot(str, str)
    def _on_install_finished(self, title, filename):
        self._installing = False
        project_type, _ = self._get_project_meta()

        if project_type == "modpack":
            extra = ("\n\n整合包已解压到 modpacks/ 目录。\n"
                     "请手动挑选用得到的模组复制到 mods/。")
        else:
            extra = "\n\n⚠ 需要重启服务器才能生效。"

        self.state.log(f"「{title}」安装完成：{filename}", "ok")
        QMessageBox.information(
            self, "安装完成",
            f"「{title}」已安装。\n\n文件：{filename}{extra}")

    @Slot(str)
    def _on_install_failed(self, error):
        self._installing = False
        self.state.log(f"安装失败：{error}", "error")
        QMessageBox.critical(self, "安装失败", error)

    # ========================================================
    #  生命周期
    # ========================================================
    def on_show(self):
        # 每次进入都重新读配置（代理、API Key 可能刚改）
        self.store.reload()

        if self._loaded_once:
            return
        self._loaded_once = True
        self._do_search(reset=True)