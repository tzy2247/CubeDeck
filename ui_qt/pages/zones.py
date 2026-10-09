"""区域管理：保护区 + 清理区。"""
import time
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QScrollArea,
    QWidget, QMessageBox, QFrame, QTabWidget, QCheckBox,
)

from ui_qt.theme import theme
from ui_qt.pages.base import BasePage
from ui_qt.dialogs.zone_edit import ZoneEditDialog, CleanZoneEditDialog
from core.zones import normalize_zone, build_visualize_command, DIMENSION_CN
from core.clean_zones import normalize_clean_zone, build_clean_zone_command


class ZonesPage(BasePage):
    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()

        # 保护区
        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(12, 12, 12, 12)
        pl.setSpacing(10)

        pbar = QHBoxLayout()
        pbar.addStretch()
        add_p = QPushButton("新建保护区")
        add_p.setObjectName("Accent")
        add_p.setFixedHeight(38)
        add_p.clicked.connect(self._add_zone)
        pbar.addWidget(add_p)
        pl.addLayout(pbar)

        self._prot_scroll = self._make_scroll()
        pl.addWidget(self._prot_scroll, 1)

        tabs.addTab(pw, "保护区")

        # 清理区
        cw = QWidget()
        cl = QVBoxLayout(cw)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(10)

        cbar = QHBoxLayout()
        cbar.addStretch()
        add_c = QPushButton("新建清理区")
        add_c.setObjectName("Accent")
        add_c.setFixedHeight(38)
        add_c.clicked.connect(self._add_clean_zone)
        cbar.addWidget(add_c)
        cl.addLayout(cbar)

        self._clean_scroll = self._make_scroll()
        cl.addWidget(self._clean_scroll, 1)

        tabs.addTab(cw, "清理区")

        root.addWidget(tabs)

    def _make_scroll(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(6)
        bl.addStretch()

        scroll.setWidget(body)
        scroll._body_layout = bl
        scroll._body = body
        return scroll

    # ========================================================
    #  保护区
    # ========================================================
    def _clear_scroll(self, scroll):
        layout = scroll._body_layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def refresh(self):
        self._refresh_protected()
        self._refresh_clean()

    def _refresh_protected(self):
        scroll = self._prot_scroll
        self._clear_scroll(scroll)

        zones = self.state.zones_data.get("zones", [])
        if not zones:
            lbl = QLabel("还没有任何保护区")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {theme.c('text_faint')}; "
                f"font-size: 13px; padding: 40px;")
            scroll._body_layout.addWidget(lbl)
            scroll._body_layout.addStretch()
            return

        for zone in zones:
            scroll._body_layout.addWidget(self._make_zone_row(zone))
        scroll._body_layout.addStretch()

    def _make_zone_row(self, zone):
        row = QFrame()
        row.setObjectName("Card")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 10, 14, 10)
        rl.setSpacing(10)

        enabled = zone.get("enabled", True)
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {theme.c('green') if enabled else theme.c('text_faint')}; "
            f"font-size: 14px;")
        rl.addWidget(dot)

        info = QVBoxLayout()
        info.setSpacing(2)

        name = QLabel(zone.get("name", "未命名"))
        name.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 14px; font-weight: bold;")
        info.addWidget(name)

        dim_cn = DIMENSION_CN.get(zone.get("dimension", ""), "?")
        try:
            x1, y1, z1, x2, y2, z2 = normalize_zone(zone)
            w = x2 - x1; h = y2 - y1; d = z2 - z1
            info_text = (f"{dim_cn}  ({x1:g},{y1:g},{z1:g}) → "
                         f"({x2:g},{y2:g},{z2:g})  [{w:g}×{h:g}×{d:g}]")
        except Exception:
            info_text = f"{dim_cn}  坐标无效"
        info_lbl = QLabel(info_text)
        info_lbl.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px;")
        info.addWidget(info_lbl)
        rl.addLayout(info, 1)

        # 启用开关
        cb = QCheckBox()
        cb.setChecked(enabled)
        cb.stateChanged.connect(
            lambda s, z=zone: self._toggle_zone(z, s))
        rl.addWidget(cb)

        # 可视化
        vis_btn = QPushButton("👁")
        vis_btn.setObjectName("Ghost")
        vis_btn.setFixedSize(38, 30)
        vis_btn.clicked.connect(lambda: self._visualize(zone))
        rl.addWidget(vis_btn)

        # 编辑
        edit_btn = QPushButton("✏")
        edit_btn.setObjectName("Ghost")
        edit_btn.setFixedSize(38, 30)
        edit_btn.clicked.connect(lambda: self._edit_zone(zone))
        rl.addWidget(edit_btn)

        # 删除
        del_btn = QPushButton("🗑")
        del_btn.setObjectName("Danger")
        del_btn.setFixedSize(38, 30)
        del_btn.clicked.connect(lambda: self._delete_zone(zone))
        rl.addWidget(del_btn)

        return row

    def _toggle_zone(self, zone, state_int):
        zone["enabled"] = bool(state_int)
        from core.zones import save_zones
        save_zones(self.state.zones_data)
        self._refresh_protected()

    def _add_zone(self):
        dlg = ZoneEditDialog(self.state, None, self)
        if dlg.exec():
            self._refresh_protected()

    def _edit_zone(self, zone):
        dlg = ZoneEditDialog(self.state, zone, self)
        if dlg.exec():
            self._refresh_protected()

    def _delete_zone(self, zone):
        reply = QMessageBox.question(
            self, "删除保护区",
            f"确定要删除「{zone.get('name')}」吗？")
        if reply != QMessageBox.Yes:
            return
        zones = self.state.zones_data.get("zones", [])
        self.state.zones_data["zones"] = [
            z for z in zones if z.get("name") != zone.get("name")]
        from core.zones import save_zones
        save_zones(self.state.zones_data)
        self._refresh_protected()

    def _visualize(self, zone):
        cmd = build_visualize_command(zone)
        if not cmd:
            return
        for line in cmd.splitlines():
            if line.strip():
                self.state.quick_rcon(line)

    # ========================================================
    #  清理区
    # ========================================================
    def _refresh_clean(self):
        scroll = self._clean_scroll
        self._clear_scroll(scroll)

        zones = self.state.clean_zones_data.get("zones", [])
        if not zones:
            lbl = QLabel("还没有任何清理区")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(
                f"color: {theme.c('text_faint')}; "
                f"font-size: 13px; padding: 40px;")
            scroll._body_layout.addWidget(lbl)
            scroll._body_layout.addStretch()
            return

        for zone in zones:
            scroll._body_layout.addWidget(self._make_clean_row(zone))
        scroll._body_layout.addStretch()

    def _make_clean_row(self, zone):
        row = QFrame()
        row.setObjectName("Card")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(14, 10, 14, 10)
        rl.setSpacing(10)

        enabled = zone.get("enabled", True)
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {theme.c('orange') if enabled else theme.c('text_faint')}; "
            f"font-size: 14px;")
        rl.addWidget(dot)

        info = QVBoxLayout()
        info.setSpacing(2)
        name = QLabel(zone.get("name", "未命名"))
        name.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 14px; font-weight: bold;")
        info.addWidget(name)

        dim_cn = DIMENSION_CN.get(zone.get("dimension", ""), "?")
        interval = zone.get("interval_min", 15)
        try:
            x1, y1, z1, x2, y2, z2 = normalize_clean_zone(zone)
            info_text = (f"{dim_cn}  ({x1:g},{y1:g},{z1:g}) → "
                         f"({x2:g},{y2:g},{z2:g})   ·   每 {interval} 分钟")
        except Exception:
            info_text = f"{dim_cn}  坐标无效   ·   每 {interval} 分钟"
        info_lbl = QLabel(info_text)
        info_lbl.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px;")
        info.addWidget(info_lbl)
        rl.addLayout(info, 1)

        cb = QCheckBox()
        cb.setChecked(enabled)
        cb.stateChanged.connect(
            lambda s, z=zone: self._toggle_clean_zone(z, s))
        rl.addWidget(cb)

        clean_btn = QPushButton("清理")
        clean_btn.setObjectName("Ghost")
        clean_btn.setFixedSize(38, 30)
        clean_btn.clicked.connect(lambda: self._clean_now(zone))
        rl.addWidget(clean_btn)

        edit_btn = QPushButton("✏")
        edit_btn.setObjectName("Ghost")
        edit_btn.setFixedSize(38, 30)
        edit_btn.clicked.connect(lambda: self._edit_clean_zone(zone))
        rl.addWidget(edit_btn)

        del_btn = QPushButton("🗑")
        del_btn.setObjectName("Danger")
        del_btn.setFixedSize(38, 30)
        del_btn.clicked.connect(lambda: self._delete_clean_zone(zone))
        rl.addWidget(del_btn)

        return row

    def _toggle_clean_zone(self, zone, state_int):
        zone["enabled"] = bool(state_int)
        from core.clean_zones import save_clean_zones
        save_clean_zones(self.state.clean_zones_data)
        self._refresh_clean()

    def _add_clean_zone(self):
        dlg = CleanZoneEditDialog(self.state, None, self)
        if dlg.exec():
            self._refresh_clean()

    def _edit_clean_zone(self, zone):
        dlg = CleanZoneEditDialog(self.state, zone, self)
        if dlg.exec():
            self._refresh_clean()

    def _delete_clean_zone(self, zone):
        reply = QMessageBox.question(
            self, "删除清理区",
            f"确定要删除「{zone.get('name')}」吗？")
        if reply != QMessageBox.Yes:
            return
        zones = self.state.clean_zones_data.get("zones", [])
        self.state.clean_zones_data["zones"] = [
            z for z in zones if z.get("name") != zone.get("name")]
        from core.clean_zones import save_clean_zones
        save_clean_zones(self.state.clean_zones_data)
        self._refresh_clean()

    def _clean_now(self, zone):
        cmd = build_clean_zone_command(zone)
        if not cmd:
            return
        self.state.quick_rcon(cmd)
        zone["last_clean"] = time.time()
        from core.clean_zones import save_clean_zones
        save_clean_zones(self.state.clean_zones_data)
        self.state.log(f"已手动清理「{zone.get('name')}」", "ok")

    def on_show(self):
        self.refresh()