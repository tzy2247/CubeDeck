"""备份管理：列表 + 打开文件夹 + 恢复 + 删除。"""
import datetime
import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QScrollArea,
    QWidget, QMessageBox, QFrame,
)

from ui_qt.theme import theme
from ui_qt.pages.base import BasePage
from core.backup import format_size, open_folder, restore_backup


class SizeWorker(QThread):
    done = Signal(str, str)   # (name, size_str)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        total = 0
        try:
            for p in self.path.rglob("*"):
                if p.is_file():
                    try:
                        total += p.stat().st_size
                    except OSError:
                        pass
        except Exception:
            pass
        self.done.emit(self.path.name, format_size(total))


class BackupPage(BasePage):
    def __init__(self, state, parent=None):
        super().__init__(state, parent)
        self._size_workers = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # 工具栏
        bar = QHBoxLayout()
        title = QLabel("历史备份")
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 16px; font-weight: bold;")
        bar.addWidget(title)
        bar.addStretch()

        open_folder_btn = QPushButton("打开备份文件夹")
        open_folder_btn.setObjectName("Ghost")
        open_folder_btn.setFixedHeight(38)
        open_folder_btn.clicked.connect(self._open_root_folder)
        bar.addWidget(open_folder_btn)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("Ghost")
        refresh_btn.setFixedHeight(38)
        refresh_btn.clicked.connect(self.refresh)
        bar.addWidget(refresh_btn)

        backup_btn = QPushButton("立即备份")
        backup_btn.setObjectName("Purple")
        backup_btn.setFixedHeight(38)
        backup_btn.clicked.connect(lambda: self.state.do_backup())
        bar.addWidget(backup_btn)
        root.addLayout(bar)

        # 列表
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, 1)

        self._show_empty("还没有任何备份")

    def _clear_list(self):
        for w in self._size_workers:
            w.quit()
        self._size_workers.clear()
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_empty(self, text):
        self._clear_list()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            f"color: {theme.c('text_faint')}; "
            f"font-size: 13px; padding: 40px;")
        self._list_layout.addWidget(lbl)
        self._list_layout.addStretch()

    def refresh(self):
        self._clear_list()

        root = self.state.server_path.parent / "backups"
        if not root.exists():
            self._show_empty("备份目录不存在")
            return
        backups = sorted(root.glob("backup_*"),
                         key=lambda p: p.name, reverse=True)
        if not backups:
            self._show_empty("还没有任何备份")
            return

        # ★ 关键：创建时就设为透明，避免在最终位置闪一帧
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        items = []
        for bp in backups:
            item = self._make_item(bp)
            eff = QGraphicsOpacityEffect(item)
            eff.setOpacity(0.0)
            item.setGraphicsEffect(eff)
            self._list_layout.addWidget(item)
            items.append(item)

        self._list_layout.addStretch()

        # 错开淡入
        self._fade_in_items(items)

    def _fade_in_items(self, items):
        """
        QVBoxLayout 里无法做真正的位置动画（layout 会强制归位），
        改用纯透明度淡入 + 错开节奏，视觉上干净且不会闪烁。
        """
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        # 只对前 10 项做动画，超过则立即显示
        visible = items[:10]
        rest = items[10:]

        # 超过 10 项的立即显示
        for w in rest:
            try:
                w.setGraphicsEffect(None)
            except Exception:
                pass

        def animate_one(widget, idx):
            eff = widget.graphicsEffect()
            if eff is None:
                eff = QGraphicsOpacityEffect(widget)
                widget.setGraphicsEffect(eff)
                eff.setOpacity(0.0)

            anim = QPropertyAnimation(eff, b"opacity", widget)
            anim.setDuration(260)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)

            def cleanup():
                try:
                    widget.setGraphicsEffect(None)
                except Exception:
                    pass

            anim.finished.connect(cleanup)
            widget._fade_anim = anim
            anim.start()

        for i in range(len(visible)):
            QTimer.singleShot(i * 40 + 20,
                              lambda idx=i: animate_one(visible[idx], idx))

    def _make_item(self, path):
        item = QFrame()
        item.setObjectName("Card")
        il = QHBoxLayout(item)
        il.setContentsMargins(20, 14, 20, 14)
        il.setSpacing(16)

        info = QVBoxLayout()
        info.setSpacing(2)

        name = QLabel(path.name)
        name.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 13px; font-weight: bold; background: transparent;")
        info.addWidget(name)

        time_str = "-"
        try:
            ts = path.name.replace("backup_", "")
            dt = datetime.datetime.strptime(ts, "%Y%m%d_%H%M%S")
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

        info_lbl = QLabel(f"{time_str}   ·   计算中…")
        info_lbl.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        info.addWidget(info_lbl)

        il.addLayout(info, 1)

        # 异步计算大小
        worker = SizeWorker(path)
        worker.done.connect(
            lambda _, s, l=info_lbl, t=time_str:
            l.setText(f"{t}   ·   {s}"))
        worker.start()
        self._size_workers.append(worker)

        # 按钮组（右对齐）
        open_btn = QPushButton("打开")
        open_btn.setObjectName("Ghost")
        open_btn.setFixedSize(60, 32)
        open_btn.clicked.connect(lambda: open_folder(path))
        il.addWidget(open_btn)

        restore_btn = QPushButton("恢复")
        restore_btn.setObjectName("Orange")
        restore_btn.setFixedSize(70, 32)
        restore_btn.clicked.connect(lambda: self._restore(path))
        il.addWidget(restore_btn)

        del_btn = QPushButton("删除")
        del_btn.setObjectName("Danger")
        del_btn.setFixedSize(60, 32)
        del_btn.clicked.connect(lambda: self._delete(path))
        il.addWidget(del_btn)

        return item

    def _open_root_folder(self):
        root = self.state.server_path.parent / "backups"
        if not root.exists():
            QMessageBox.information(self, "提示", "备份目录还不存在")
            return
        open_folder(root)

    def _delete(self, path):
        reply = QMessageBox.question(
            self, "删除备份",
            f"确定要永久删除吗？\n\n{path.name}\n\n此操作不可撤销。")
        if reply != QMessageBox.Yes:
            return
        try:
            shutil.rmtree(path)
            self.state.log(f"已删除备份：{path.name}", "ok")
            self.refresh()
        except Exception as e:
            self.state.log(f"删除失败：{e}", "error")

    def _restore(self, path):
        if self.state.is_running:
            reply = QMessageBox.question(
                self, "恢复备份",
                f"恢复前需要先停止服务器。\n\n备份：{path.name}\n\n"
                f"⚠ 当前世界数据将被替换。继续吗？")
            if reply != QMessageBox.Yes:
                return
            self.state.stop_server()
            from PySide6.QtCore import QTimer
            QTimer.singleShot(3000, lambda: self._do_restore(path))
        else:
            reply = QMessageBox.question(
                self, "恢复备份",
                f"确定要从备份恢复吗？\n\n{path.name}\n\n"
                f"⚠ 当前世界数据将被替换。")
            if reply != QMessageBox.Yes:
                return
            self._do_restore(path)

    def _do_restore(self, backup_path):
        self.state.log(
            f"━━━ 开始恢复备份：{backup_path.name} ━━━", "info")
        ok, result = restore_backup(
            self.state.server_path, backup_path, log=self.state.log)
        if ok:
            self.state.log("恢复完成", "ok")
            QMessageBox.information(
                self, "恢复完成",
                f"备份已恢复。\n\n恢复前的世界保存在：\n{result}")
        else:
            self.state.log(f"✖ 恢复失败：{result}", "error")
            QMessageBox.critical(self, "恢复失败", str(result))

    def on_show(self):
        self.refresh()