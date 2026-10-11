"""语言文件导出对话框：从 mods 目录批量提取汉化/英语。"""
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QProgressBar, QCheckBox, QTextEdit, QMessageBox,
)

from ui_qt.theme import theme
from core.lang_exporter import (
    scan_mods, export_languages, count_entries,
)


# ============================================================
#  后台 worker
# ============================================================
class _ScanWorker(QThread):
    progress = Signal(int, int, str)
    done = Signal(dict)

    def __init__(self, mods_dir, log_cb):
        super().__init__()
        self.mods_dir = mods_dir
        self.log_cb = log_cb

    def run(self):
        try:
            result = scan_mods(
                self.mods_dir,
                log=self.log_cb,
                progress=lambda c, t, n: self.progress.emit(c, t, n),
            )
            self.done.emit(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.done.emit({"mods": [], "total": 0,
                            "with_zh": 0, "with_en": 0,
                            "error": str(e)})


class _ExportWorker(QThread):
    progress = Signal(int, int, str)
    done = Signal(dict)

    def __init__(self, scan_result, output_dir, prefer_zh, log_cb):
        super().__init__()
        self.scan_result = scan_result
        self.output_dir = output_dir
        self.prefer_zh = prefer_zh
        self.log_cb = log_cb

    def run(self):
        try:
            result = export_languages(
                self.scan_result,
                self.output_dir,
                prefer_zh=self.prefer_zh,
                log=self.log_cb,
                progress=lambda c, t, n: self.progress.emit(c, t, n),
            )
            self.done.emit(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.done.emit({"zh": 0, "en": 0, "skipped": 0,
                            "error": str(e)})


# ============================================================
#  对话框
# ============================================================
class LangExporterDialog(QDialog):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._scan_result = None
        self._scan_worker = None
        self._export_worker = None

        self.setWindowTitle("导出模组语言文件")
        self.resize(760, 640)
        self._build()

        # 默认 mods 目录：当前服务器目录下的 mods
        try:
            default_mods = self.state.server_path / "mods"
            if default_mods.exists():
                self._mods_edit.setText(str(default_mods))
        except Exception:
            pass

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("导出模组语言文件")
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 18px; font-weight: bold; background: transparent;")
        root.addWidget(title)

        hint = QLabel(
            "从整合包 mods 目录下的所有 .jar 中提取语言文件。\n"
            "优先提取 zh_cn.json；若没有汉化则导出 en_us.json 作为翻译模板。\n"
            "输出结构：<输出目录>/<modid>/<locale>.json")
        hint.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px; "
            f"background: transparent;")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # ---- mods 目录 ----
        root.addWidget(self._label("mods 目录（含 .jar）"))
        mods_row = QHBoxLayout()
        mods_row.setSpacing(8)
        self._mods_edit = QLineEdit()
        self._mods_edit.setFixedHeight(36)
        self._mods_edit.setPlaceholderText(
            "选择包含 .jar 文件的 mods 目录")
        mods_row.addWidget(self._mods_edit, 1)

        browse_mods = QPushButton("浏览…")
        browse_mods.setObjectName("Ghost")
        browse_mods.setFixedSize(80, 36)
        browse_mods.clicked.connect(self._browse_mods)
        mods_row.addWidget(browse_mods)
        root.addLayout(mods_row)

        # ---- 输出目录 ----
        root.addWidget(self._label("输出目录"))
        out_row = QHBoxLayout()
        out_row.setSpacing(8)
        self._out_edit = QLineEdit()
        self._out_edit.setFixedHeight(36)
        self._out_edit.setPlaceholderText("语言文件导出到的目标目录")
        out_row.addWidget(self._out_edit, 1)

        browse_out = QPushButton("浏览…")
        browse_out.setObjectName("Ghost")
        browse_out.setFixedSize(80, 36)
        browse_out.clicked.connect(self._browse_out)
        out_row.addWidget(browse_out)
        root.addLayout(out_row)

        # ---- 选项 ----
        self._prefer_zh_cb = QCheckBox(
            "优先汉化（有汉化时只导出 zh_cn.json；未勾选则汉化和英语都导出）")
        self._prefer_zh_cb.setChecked(True)
        self._prefer_zh_cb.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 12px; "
            f"background: transparent;")
        root.addWidget(self._prefer_zh_cb)

        # ---- 结果展示 ----
        self._result_box = QTextEdit()
        self._result_box.setReadOnly(True)
        self._result_box.setFixedHeight(180)
        self._result_box.setStyleSheet(
            f"QTextEdit {{ background-color: {theme.c('console_bg')}; "
            f"color: {theme.c('text')}; "
            f"border: 1px solid {theme.c('border')}; "
            f"border-radius: 6px; padding: 8px; font-size: 12px; }}")
        root.addWidget(self._result_box)

        # ---- 进度条 ----
        self._progress = QProgressBar()
        self._progress.setFixedHeight(8)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            f"QProgressBar {{ background-color: {theme.c('card')}; "
            f"border: none; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ "
            f"background-color: {theme.c('accent')}; "
            f"border-radius: 4px; }}")
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        # ---- 状态栏 ----
        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px; "
            f"background: transparent;")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        root.addStretch()

        # ---- 按钮 ----
        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch()

        self._scan_btn = QPushButton("扫描")
        self._scan_btn.setObjectName("Accent")
        self._scan_btn.setFixedHeight(38)
        self._scan_btn.setMinimumWidth(100)
        self._scan_btn.clicked.connect(self._do_scan)
        btns.addWidget(self._scan_btn)

        self._export_btn = QPushButton("导出")
        self._export_btn.setObjectName("Green")
        self._export_btn.setFixedHeight(38)
        self._export_btn.setMinimumWidth(100)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._do_export)
        btns.addWidget(self._export_btn)

        close_btn = QPushButton("关闭")
        close_btn.setObjectName("Ghost")
        close_btn.setFixedHeight(38)
        close_btn.setMinimumWidth(90)
        close_btn.clicked.connect(self.reject)
        btns.addWidget(close_btn)

        root.addLayout(btns)

    def _label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 12px; "
            f"background: transparent;")
        return lbl

    # ========================================================
    def _browse_mods(self):
        start = self._mods_edit.text().strip() or "."
        path = QFileDialog.getExistingDirectory(
            self, "选择 mods 目录", start)
        if path:
            self._mods_edit.setText(path)

    def _browse_out(self):
        start = self._out_edit.text().strip() or "."
        path = QFileDialog.getExistingDirectory(
            self, "选择输出目录", start)
        if path:
            self._out_edit.setText(path)

    # ========================================================
    #  扫描
    # ========================================================
    def _do_scan(self):
        mods_dir = self._mods_edit.text().strip()
        if not mods_dir:
            QMessageBox.warning(self, "提示", "请先选择 mods 目录")
            return

        if not Path(mods_dir).is_dir():
            QMessageBox.warning(self, "提示",
                                f"目录不存在：\n{mods_dir}")
            return

        self._scan_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._result_box.clear()
        self._status.setText("扫描中…")

        def log_cb(msg, tag="info"):
            self._result_box.append(msg)

        self._scan_worker = _ScanWorker(mods_dir, log_cb)
        self._scan_worker.progress.connect(self._on_progress)
        self._scan_worker.done.connect(self._on_scan_done)
        self._scan_worker.start()

    def _on_progress(self, current, total, name):
        if total > 0:
            self._progress.setRange(0, total)
            self._progress.setValue(current)
        self._status.setText(f"处理中：{name}（{current}/{total}）")

    def _on_scan_done(self, result):
        self._scan_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._status.setText("")

        if result.get("error"):
            self._result_box.append(
                f"\n✖ 扫描失败：{result['error']}")
            QMessageBox.critical(self, "扫描失败", result["error"])
            return

        self._scan_result = result

        stats = count_entries(result)
        summary = (
            f"\n━━━━━━━━ 扫描结果 ━━━━━━━━\n"
            f"总模组数：{result['total']}\n"
            f"含语言文件：{len(result['mods'])}\n"
            f"有汉化（zh_cn）：{result['with_zh']}\n"
            f"有英语（en_us）：{result['with_en']}\n"
            f"待翻译模组（有英语无汉化）：{stats['untranslated_mods']}\n"
            f"汉化条目总数：{stats['total_zh']}\n"
            f"英语条目总数：{stats['total_en']}\n"
        )
        self._result_box.append(summary)

        if result["mods"]:
            self._export_btn.setEnabled(True)

    # ========================================================
    #  导出
    # ========================================================
    def _do_export(self):
        if not self._scan_result or not self._scan_result.get("mods"):
            QMessageBox.warning(self, "提示", "请先扫描 mods 目录")
            return

        out_dir = self._out_edit.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "提示", "请先选择输出目录")
            return

        # 若输出目录不存在，询问是否创建
        out_path = Path(out_dir)
        if not out_path.exists():
            reply = QMessageBox.question(
                self, "目录不存在",
                f"{out_dir}\n\n目录不存在，是否创建？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes)
            if reply != QMessageBox.Yes:
                return

        prefer_zh = self._prefer_zh_cb.isChecked()

        self._scan_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._result_box.append(
            f"\n━━━━━━━━ 开始导出 ━━━━━━━━\n"
            f"输出到：{out_dir}\n"
            f"优先汉化：{'是' if prefer_zh else '否'}")

        def log_cb(msg, tag="info"):
            self._result_box.append(msg)

        self._export_worker = _ExportWorker(
            self._scan_result, out_dir, prefer_zh, log_cb)
        self._export_worker.progress.connect(self._on_progress)
        self._export_worker.done.connect(self._on_export_done)
        self._export_worker.start()

    def _on_export_done(self, result):
        self._scan_btn.setEnabled(True)
        self._export_btn.setEnabled(True)
        self._progress.setVisible(False)
        self._status.setText("")

        if result.get("error"):
            self._result_box.append(
                f"\n✖ 导出失败：{result['error']}")
            QMessageBox.critical(self, "导出失败", result["error"])
            return

        summary = (
            f"\n━━━━━━━━ 导出完成 ━━━━━━━━\n"
            f"汉化文件：{result['zh']} 个\n"
            f"英语文件：{result['en']} 个\n"
            f"跳过：{result['skipped']} 个"
        )
        self._result_box.append(summary)

        QMessageBox.information(
            self, "导出完成",
            f"汉化文件：{result['zh']} 个\n"
            f"英语文件：{result['en']} 个\n"
            f"跳过：{result['skipped']} 个\n\n"
            f"输出目录：\n{self._out_edit.text().strip()}")

    # ========================================================
    def closeEvent(self, event):
        # 若 worker 还在跑，先停止
        for w in (self._scan_worker, self._export_worker):
            if w and w.isRunning():
                w.quit()
                w.wait(2000)
        super().closeEvent(event)