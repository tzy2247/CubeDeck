"""保护区和清理区编辑对话框。"""
import re
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QMessageBox, QScrollArea, QWidget,
)

from ui_qt.theme import theme
from core.zones import (normalize_zone, DIMENSION_CN, DIMENSION_KEYS)
from core.clean_zones import normalize_clean_zone


class ZoneEditDialog(QDialog):
    def __init__(self, state, zone=None, parent=None):
        super().__init__(parent)
        self.state = state
        self._zone = dict(zone) if zone else {}
        self._is_new = zone is None

        self.setWindowTitle("编辑保护区" if not self._is_new else "新建保护区")
        self.resize(560, 580)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # 名称
        row = QHBoxLayout()
        row.addWidget(QLabel("名称"))
        self._name = QLineEdit(self._zone.get("name", "新保护区"))
        row.addWidget(self._name, 1)
        layout.addLayout(row)

        # 维度
        row = QHBoxLayout()
        row.addWidget(QLabel("维度"))
        self._dim = QComboBox()
        for key in DIMENSION_KEYS:
            self._dim.addItem(DIMENSION_CN.get(key, key), key)
        self._dim.addItem("全部维度", "*")
        cur_dim = self._zone.get("dimension", "minecraft:overworld")
        idx = self._dim.findData(cur_dim)
        if idx >= 0:
            self._dim.setCurrentIndex(idx)
        row.addWidget(self._dim, 1)
        layout.addLayout(row)

        # 启用
        self._enabled = QCheckBox("启用")
        self._enabled.setChecked(self._zone.get("enabled", True))
        layout.addWidget(self._enabled)

        # 角1
        layout.addWidget(QLabel("角 1（包含）"))
        self._entries = {}
        for key_label, key_name, default in (
            ("X", "x1", self._zone.get("x1", 0)),
            ("Y", "y1", self._zone.get("y1", 0)),
            ("Z", "z1", self._zone.get("z1", 0)),
        ):
            r = QHBoxLayout()
            r.addWidget(QLabel(key_label))
            e = QLineEdit(str(default))
            e.setFixedWidth(120)
            r.addWidget(e)
            self._entries[key_name] = e
            r.addStretch()
            layout.addLayout(r)

        # 角2
        layout.addWidget(QLabel("角 2（包含）"))
        for key_label, key_name, default in (
            ("X", "x2", self._zone.get("x2", 0)),
            ("Y", "y2", self._zone.get("y2", 0)),
            ("Z", "z2", self._zone.get("z2", 0)),
        ):
            r = QHBoxLayout()
            r.addWidget(QLabel(key_label))
            e = QLineEdit(str(default))
            e.setFixedWidth(120)
            r.addWidget(e)
            self._entries[key_name] = e
            r.addStretch()
            layout.addLayout(r)

        # 按钮
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("Ghost")
        cancel.setFixedHeight(40)
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)

        save = QPushButton("✓ 保存")
        save.setObjectName("Green")
        save.setFixedHeight(40)
        save.clicked.connect(self._save)
        btns.addWidget(save)
        layout.addLayout(btns)

    def _save(self):
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写名称")
            return

        try:
            coords = {k: float(e.text().strip())
                      for k, e in self._entries.items()}
        except ValueError:
            QMessageBox.warning(self, "提示", "坐标必须是数字")
            return

        zone = {
            "name": name,
            "dimension": self._dim.currentData(),
            "enabled": self._enabled.isChecked(),
            **coords,
        }

        x1, y1, z1, x2, y2, z2 = normalize_zone(zone)
        zone.update({"x1": x1, "y1": y1, "z1": z1,
                     "x2": x2, "y2": y2, "z2": z2})

        zones = self.state.zones_data.setdefault("zones", [])
        if self._is_new:
            if any(z.get("name") == zone["name"] for z in zones):
                QMessageBox.warning(self, "提示", f"已存在：{zone['name']}")
                return
            zones.append(zone)
        else:
            old = self._zone.get("name")
            for i, z in enumerate(zones):
                if z.get("name") == old:
                    zones[i] = zone
                    break
        from core.zones import save_zones
        save_zones(self.state.zones_data)
        self.accept()


class CleanZoneEditDialog(QDialog):
    def __init__(self, state, zone=None, parent=None):
        super().__init__(parent)
        self.state = state
        self._zone = dict(zone) if zone else {}
        self._is_new = zone is None

        self.setWindowTitle("编辑清理区" if not self._is_new else "新建清理区")
        self.resize(560, 620)
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.addWidget(QLabel("名称"))
        self._name = QLineEdit(self._zone.get("name", "新清理区"))
        row.addWidget(self._name, 1)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("维度"))
        self._dim = QComboBox()
        for key in DIMENSION_KEYS:
            self._dim.addItem(DIMENSION_CN.get(key, key), key)
        cur_dim = self._zone.get("dimension", "minecraft:overworld")
        idx = self._dim.findData(cur_dim)
        if idx >= 0:
            self._dim.setCurrentIndex(idx)
        row.addWidget(self._dim, 1)
        layout.addLayout(row)

        self._enabled = QCheckBox("启用")
        self._enabled.setChecked(self._zone.get("enabled", True))
        layout.addWidget(self._enabled)

        row = QHBoxLayout()
        row.addWidget(QLabel("清理间隔（分钟）"))
        self._interval = QLineEdit(str(self._zone.get("interval_min", 15)))
        self._interval.setFixedWidth(80)
        row.addWidget(self._interval)
        row.addStretch()
        layout.addLayout(row)

        layout.addWidget(QLabel("角 1（包含）"))
        self._entries = {}
        for key_label, key_name, default in (
            ("X", "x1", self._zone.get("x1", 0)),
            ("Y", "y1", self._zone.get("y1", 0)),
            ("Z", "z1", self._zone.get("z1", 0)),
        ):
            r = QHBoxLayout()
            r.addWidget(QLabel(key_label))
            e = QLineEdit(str(default))
            e.setFixedWidth(120)
            r.addWidget(e)
            self._entries[key_name] = e
            r.addStretch()
            layout.addLayout(r)

        layout.addWidget(QLabel("角 2（包含）"))
        for key_label, key_name, default in (
            ("X", "x2", self._zone.get("x2", 0)),
            ("Y", "y2", self._zone.get("y2", 0)),
            ("Z", "z2", self._zone.get("z2", 0)),
        ):
            r = QHBoxLayout()
            r.addWidget(QLabel(key_label))
            e = QLineEdit(str(default))
            e.setFixedWidth(120)
            r.addWidget(e)
            self._entries[key_name] = e
            r.addStretch()
            layout.addLayout(r)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("Ghost")
        cancel.setFixedHeight(40)
        cancel.clicked.connect(self.reject)
        btns.addWidget(cancel)

        save = QPushButton("✓ 保存")
        save.setObjectName("Green")
        save.setFixedHeight(40)
        save.clicked.connect(self._save)
        btns.addWidget(save)
        layout.addLayout(btns)

    def _save(self):
        import time
        name = self._name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写名称")
            return

        try:
            coords = {k: float(e.text().strip())
                      for k, e in self._entries.items()}
            interval = int(self._interval.text())
            if interval < 1:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "提示", "坐标/间隔无效")
            return

        zone = {
            "name": name,
            "dimension": self._dim.currentData(),
            "enabled": self._enabled.isChecked(),
            "interval_min": interval,
            "last_clean": self._zone.get("last_clean", time.time()),
            **coords,
        }

        x1, y1, z1, x2, y2, z2 = normalize_clean_zone(zone)
        zone.update({"x1": x1, "y1": y1, "z1": z1,
                     "x2": x2, "y2": y2, "z2": z2})

        zones = self.state.clean_zones_data.setdefault("zones", [])
        if self._is_new:
            if any(z.get("name") == zone["name"] for z in zones):
                QMessageBox.warning(self, "提示", f"已存在：{zone['name']}")
                return
            zones.append(zone)
        else:
            old = self._zone.get("name")
            for i, z in enumerate(zones):
                if z.get("name") == old:
                    zones[i] = zone
                    break
        from core.clean_zones import save_clean_zones
        save_clean_zones(self.state.clean_zones_data)
        self.accept()