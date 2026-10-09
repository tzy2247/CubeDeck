"""物品编辑对话框。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox,
)

from ui_qt.theme import theme


COMMON_ITEMS = [
    ("钻石", "minecraft:diamond"),
    ("下界合金锭", "minecraft:netherite_ingot"),
    ("金苹果", "minecraft:golden_apple"),
    ("附魔金苹果", "minecraft:enchanted_golden_apple"),
    ("鞘翅", "minecraft:elytra"),
    ("不死图腾", "minecraft:totem_of_undying"),
    ("末影珍珠", "minecraft:ender_pearl"),
    ("三叉戟", "minecraft:trident"),
]


class ItemEditDialog(QDialog):
    def __init__(self, parent, slot_label, current_id, current_count):
        super().__init__(parent)
        self.setWindowTitle(f"编辑 · {slot_label}")
        self.resize(480, 420)
        self._item_id = current_id or ""
        self._count = int(current_count or 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        title = QLabel(slot_label)
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 17px; font-weight: bold;")
        layout.addWidget(title)

        # 物品 ID
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("物品 ID"))
        self._id_entry = QLineEdit(current_id or "")
        self._id_entry.setPlaceholderText("minecraft:diamond_sword")
        row1.addWidget(self._id_entry, 1)
        layout.addLayout(row1)

        # 数量
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("数量"))
        self._count_entry = QLineEdit(str(current_count or 1))
        row2.addWidget(self._count_entry, 1)
        layout.addLayout(row2)

        # 常用
        layout.addWidget(QLabel("常用物品"))
        self._common_list = QListWidget()
        for cn, iid in COMMON_ITEMS:
            item = QListWidgetItem(f"{cn}  ({iid})")
            item.setData(Qt.UserRole, iid)
            self._common_list.addItem(item)
        self._common_list.itemDoubleClicked.connect(self._pick_common)
        layout.addWidget(self._common_list, 1)

        # 按钮
        btns = QHBoxLayout()
        clear_btn = QPushButton("🗑  清空")
        clear_btn.setObjectName("Danger")
        clear_btn.setFixedHeight(40)
        clear_btn.clicked.connect(self._do_clear)
        btns.addWidget(clear_btn)
        btns.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("Ghost")
        cancel_btn.setFixedHeight(40)
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setObjectName("Accent")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save)
        btns.addWidget(save_btn)
        layout.addLayout(btns)

    def _pick_common(self, item):
        iid = item.data(Qt.UserRole)
        self._id_entry.setText(iid)

    def _do_clear(self):
        self._item_id = ""
        self._count = 0
        self.accept()

    def _save(self):
        iid = self._id_entry.text().strip()
        if not iid:
            QMessageBox.warning(self, "提示", "请填写物品 ID")
            return
        if ":" not in iid:
            iid = f"minecraft:{iid}"
        try:
            cnt = int(self._count_entry.text())
            if cnt < 1 or cnt > 6400:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "提示", "数量必须为 1-6400 的整数")
            return
        self._item_id = iid
        self._count = cnt
        self.accept()

    def result_item(self):
        return self._item_id, self._count