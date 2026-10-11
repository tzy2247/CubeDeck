"""物品编辑对话框：ID 输入 + 中文名搜索 + 数量。"""
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QCompleter, QMessageBox,
)

from ui_qt.theme import theme
from core.item_names import get_item_name, is_loaded as _lang_loaded
from core.item_search import get_index


class ItemEditDialog(QDialog):
    """编辑单个槽位的物品。"""

    def __init__(self, parent, slot_label, current_id="", current_count=1):
        super().__init__(parent)
        self._slot_label = slot_label
        self._item_id = current_id or ""
        self._count = max(1, int(current_count or 1))

        self.setWindowTitle(f"编辑物品 · {slot_label}")
        self.resize(560, 360)
        self._build()
        self._load_initial()

    # ========================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        # 槽位提示
        slot_lbl = QLabel(f"槽位：{self._slot_label}")
        slot_lbl.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px; "
            f"background: transparent;")
        root.addWidget(slot_lbl)

        # 语言状态
        self._lang_status = QLabel("")
        self._lang_status.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        root.addWidget(self._lang_status)

        # ---- 搜索框 ----
        root.addWidget(self._label("搜索物品（ID 或中文名）"))
        self._search_edit = QLineEdit()
        self._search_edit.setFixedHeight(38)
        self._search_edit.setPlaceholderText(
            "输入 ID（如 diamond_sword）或中文名（如 钻石剑）")
        self._search_edit.textEdited.connect(self._on_search_edited)
        self._search_edit.returnPressed.connect(self._on_confirm)
        root.addWidget(self._search_edit)

        # ★ QCompleter 自动补全
        self._completer_model = QStandardItemModel(self)
        self._completer = QCompleter(self)
        self._completer.setModel(self._completer_model)
        # UnfilteredPopupCompletion: 我们已过滤好，不要让 Qt 再过滤
        self._completer.setCompletionMode(
            QCompleter.UnfilteredPopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setMaxVisibleItems(15)
        self._completer.activated.connect(self._on_completer_activated)
        self._search_edit.setCompleter(self._completer)

        # ---- 当前选中展示 ----
        info_row = QHBoxLayout()
        info_row.setSpacing(8)

        self._name_lbl = QLabel("—")
        self._name_lbl.setStyleSheet(
            f"color: {theme.c('accent')}; font-size: 14px; "
            f"font-weight: bold; background: transparent;")
        info_row.addWidget(self._name_lbl)
        info_row.addStretch()

        self._id_lbl = QLabel("")
        self._id_lbl.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        info_row.addWidget(self._id_lbl)
        root.addLayout(info_row)

        # ---- 数量 ----
        count_row = QHBoxLayout()
        count_row.setSpacing(8)
        count_row.addWidget(self._label("数量"))
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 6400)
        self._count_spin.setValue(self._count)
        self._count_spin.setFixedHeight(34)
        self._count_spin.setFixedWidth(110)
        count_row.addWidget(self._count_spin)

        count_row.addWidget(self._label("（1~6400，超过 64 会拆成多格）"))
        count_row.addStretch()
        root.addLayout(count_row)

        # ---- 快捷操作 ----
        quick_row = QHBoxLayout()
        quick_row.setSpacing(8)
        for label, value in (("1", 1), ("16", 16), ("32", 32),
                             ("64", 64)):
            btn = QPushButton(label)
            btn.setObjectName("Ghost")
            btn.setFixedSize(48, 30)
            btn.clicked.connect(
                lambda _=False, v=value: self._count_spin.setValue(v))
            quick_row.addWidget(btn)
        quick_row.addStretch()
        root.addLayout(quick_row)

        root.addStretch()

        # ---- 按钮 ----
        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("Ghost")
        cancel_btn.setFixedSize(100, 38)
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)

        clear_btn = QPushButton("清空此槽")
        clear_btn.setObjectName("Danger")
        clear_btn.setFixedSize(100, 38)
        clear_btn.clicked.connect(self._on_clear)
        btns.addWidget(clear_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setObjectName("Accent")
        ok_btn.setFixedSize(100, 38)
        ok_btn.clicked.connect(self._on_confirm)
        btns.addWidget(ok_btn)

        root.addLayout(btns)

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 12px; "
            f"background: transparent;")
        return lbl

    # ========================================================
    def _load_initial(self):
        # 语言文件状态
        try:
            lang_ok = _lang_loaded()
        except Exception:
            lang_ok = False

        if lang_ok:
            try:
                total = get_index().total
                self._lang_status.setText(
                    f"✔ 已加载 {total} 个物品，可搜中文名")
            except Exception:
                self._lang_status.setText("语言文件已加载")
        else:
            self._lang_status.setText(
                "⚠ 未加载语言文件，只能搜 ID（可在设置页配置语言文件目录）")

        # 初始值：显示当前物品
        if self._item_id:
            self._search_edit.setText(self._item_id)
            self._show_current(self._item_id)
        self._count_spin.setValue(self._count)

        QTimer_singleShot = None
        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._search_edit.setFocus)
        except Exception:
            pass

    # ========================================================
    #  搜索
    # ========================================================
    def _on_search_edited(self, text):
        """搜索框内容变化 → 更新补全列表。"""
        try:
            index = get_index()
        except Exception:
            return

        query = text.strip()
        if not query:
            self._completer_model.clear()
            return

        results = index.search(query, limit=100)

        # 重建 completer model
        self._completer_model.clear()
        for full_id, name in results:
            display = f"{name}  ({full_id})" if name else full_id
            item = QStandardItem(display)
            item.setData(full_id, Qt.UserRole)
            self._completer_model.appendRow(item)

        # 弹窗（只有当有结果时）
        if results:
            self._completer.complete()

        # 实时预览第一个结果
        if results:
            self._show_current(results[0][0])

    def _on_completer_activated(self, text):
        """用户从补全列表选中一项。"""
        if not text:
            return

        # 从显示文本解析出完整 ID
        full_id = self._parse_display(text)
        if full_id:
            self._search_edit.setText(full_id)
            self._show_current(full_id)

    @staticmethod
    def _parse_display(text):
        """从 '钻石剑 (minecraft:diamond_sword)' 中提取 ID。"""
        m = re.search(r"\(([^)]+)\)\s*$", text)
        if m:
            return m.group(1).strip()
        # 没有括号，可能是纯 ID
        return text.strip()

    def _show_current(self, full_id):
        """在下方显示当前物品的中文名和 ID。"""
        if not full_id:
            self._name_lbl.setText("—")
            self._id_lbl.setText("")
            return

        try:
            name = get_item_name(full_id)
        except Exception:
            name = ""

        # 判断是否翻译成功
        short_id = full_id.replace("minecraft:", "")
        has_trans = (
            name and name != full_id and name != short_id
            and name != full_id.split(":", 1)[-1]
            and not name.startswith("item.")
            and not name.startswith("block.")
        )

        if has_trans:
            self._name_lbl.setText(name)
        else:
            self._name_lbl.setText(short_id)
        self._id_lbl.setText(full_id)

    # ========================================================
    #  确认 / 清空
    # ========================================================
    def _on_confirm(self):
        text = self._search_edit.text().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请输入物品 ID 或名称")
            return

        # 如果是补全显示的格式，解析
        item_id = self._parse_display(text)
        if not item_id:
            QMessageBox.warning(self, "提示", "无法识别物品 ID")
            return

        # 简单校验：不包含空格
        if " " in item_id:
            item_id = item_id.split()[0]

        # 自动补命名空间
        if ":" not in item_id and not item_id.startswith("#"):
            item_id = f"minecraft:{item_id}"

        self._item_id = item_id
        self._count = self._count_spin.value()
        self.accept()

    def _on_clear(self):
        self._item_id = ""
        self._count = 0
        self.accept()

    # ========================================================
    def result_item(self):
        """返回 (item_id, count)。空字符串代表清空。"""
        return self._item_id, self._count

    # ========================================================
    #  主题变化时刷新（如果对话框还开着）
    # ========================================================
    def changeEvent(self, event):
        super().changeEvent(event)
        # 简单处理：重新应用
        try:
            from PySide6.QtCore import QEvent
            if event.type() == QEvent.PaletteChange:
                self.setStyleSheet("")
        except Exception:
            pass