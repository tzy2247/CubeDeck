"""新手引导对话框：下载或导入服务器。

设计原则：
- 不使用自定义信号，避免与主窗口模态嵌套
- 不使用 lambda 直接绑定 mousePressEvent（PySide6 不安全）
- 通过 get_result() 让调用方在 exec() 返回后处理
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QFrame,
)

from ui_qt.theme import theme


class _ClickableCard(QFrame):
    """可点击的卡片。正确覆写 mousePressEvent，不用 lambda。"""

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback
        self.setObjectName("Card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(160)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            try:
                self._callback()
            except Exception:
                pass
        super().mousePressEvent(event)


class OnboardingDialog(QDialog):
    """
    新手引导。

    调用方用法：
        dlg = OnboardingDialog(parent)
        if dlg.exec() == QDialog.Accepted:
            action, name, path = dlg.get_result()
            # action: "download" | "import"
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("欢迎使用 CubeDeck")
        self.setModal(True)
        self.resize(520, 380)
        self.setStyleSheet(theme.qss())

        self._action = None          # "download" / "import"
        self._import_name = ""
        self._import_path = ""

        self._build()

    # ========================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 36, 36, 28)
        root.setSpacing(18)

        title = QLabel("还没有服务端吗？")
        title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 22px; font-weight: bold; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        subtitle = QLabel("下载或导入你的服务器，开始使用 CubeDeck")
        subtitle.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 13px; "
            f"background: transparent;")
        subtitle.setAlignment(Qt.AlignCenter)
        root.addWidget(subtitle)

        root.addSpacing(12)

        cards = QHBoxLayout()
        cards.setSpacing(14)
        cards.addWidget(self._make_card(
            icon="⬇",
            title="下载服务端",
            desc="从官方或镜像下载\nPaper、Fabric、原版等",
            color_key="accent",
            on_click=self._on_download,
        ))
        cards.addWidget(self._make_card(
            icon="📁",
            title="导入本地服务器",
            desc="选择已有服务器目录\n直接接管管理",
            color_key="green",
            on_click=self._on_import,
        ))
        root.addLayout(cards)
        root.addStretch()

        btns = QHBoxLayout()
        btns.addStretch()
        skip_btn = QPushButton("稍后再说")
        skip_btn.setObjectName("Ghost")
        skip_btn.setFixedSize(100, 36)
        skip_btn.clicked.connect(self.reject)
        btns.addWidget(skip_btn)
        root.addLayout(btns)

    def _make_card(self, icon, title, desc, color_key, on_click):
        card = _ClickableCard(on_click)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 24, 20, 20)
        layout.setSpacing(8)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(
            f"color: {theme.c(color_key)}; font-size: 36px; "
            f"background: transparent;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 15px; font-weight: bold; background: transparent;")
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(desc)
        desc_lbl.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent;")
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(desc_lbl)

        return card

    # ========================================================
    def get_result(self):
        """返回 (action, name, path)。action 为空表示用户取消。"""
        return self._action, self._import_name, self._import_path

    # ========================================================
    def _on_download(self):
        self._action = "download"
        self.accept()

    def _on_import(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择服务器目录", str(Path.home()))
        if not path:
            return

        p = Path(path)
        if not p.exists() or not p.is_dir():
            QMessageBox.warning(self, "提示", "目录不存在")
            return

        has_jar = (p / "server.jar").exists()
        has_props = (p / "server.properties").exists()
        has_eula = (p / "eula.txt").exists()

        if not (has_jar or has_props or has_eula):
            reply = QMessageBox.question(
                self, "目录检查",
                f"该目录看起来不像 Minecraft 服务端目录：\n{p}\n\n"
                f"（未找到 server.jar / server.properties / eula.txt）\n\n"
                f"仍然要导入吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self._action = "import"
        self._import_name = p.name or "我的服务器"
        self._import_path = str(p)
        self.accept()