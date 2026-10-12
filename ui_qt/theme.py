"""主题系统：配色方案 + QSS 样式表。"""
import threading

THEMES = {
    "深蓝": {
        "bg": "#0f1117", "sidebar": "#151a24", "card": "#1a1f2b",
        "card_hover": "#222836", "console_bg": "#0d1017",
        "border": "#262d3d",
        "accent": "#4f8cff", "accent_hover": "#3d78e8",
        "green": "#2ecc71", "green_hover": "#27ae60",
        "red": "#e74c3c", "red_hover": "#c0392b",
        "orange": "#f39c12", "orange_hover": "#d68910",
        "purple": "#9b59b6", "purple_hover": "#8e44ad",
        "text": "#e6e9f0", "text_dim": "#8b93a7", "text_faint": "#5d6577",
        # ★ 新增
        "input_bg": "#0d1017", "input_text": "#e6e9f0",
        "is_light": False,
    },
    "深紫": {
        "bg": "#0e0a1a", "sidebar": "#161028", "card": "#1d1633",
        "card_hover": "#261f42", "console_bg": "#0a0714",
        "border": "#2c2349",
        "accent": "#8b5cf6", "accent_hover": "#7c3aed",
        "green": "#22c55e", "green_hover": "#16a34a",
        "red": "#e74c3c", "red_hover": "#c0392b",
        "orange": "#f39c12", "orange_hover": "#d68910",
        "purple": "#c084fc", "purple_hover": "#a855f7",
        "text": "#e9e6f5", "text_dim": "#9a92b0", "text_faint": "#6b6484",
        "input_bg": "#0a0714", "input_text": "#e9e6f5",
        "is_light": False,
    },

    "午夜黑": {
        "bg": "#000000", "sidebar": "#0a0a0a", "card": "#131313",
        "card_hover": "#1c1c1c", "console_bg": "#050505",
        "border": "#222222",
        "accent": "#5b7cfa", "accent_hover": "#4a68d8",
        "green": "#22c55e", "green_hover": "#16a34a",
        "red": "#dc2626", "red_hover": "#b91c1c",
        "orange": "#d97706", "orange_hover": "#b45309",
        "purple": "#8b5cf6", "purple_hover": "#7c3aed",
        "text": "#f5f5f5", "text_dim": "#9ca3af", "text_faint": "#6b7280",
        "input_bg": "#050505", "input_text": "#f5f5f5",
        "is_light": False,
    },

    "晨白": {
        "bg": "#f0f0f3", "sidebar": "#e6e6ea", "card": "#f7f7f9",
        "card_hover": "#e4e4e8", "console_bg": "#1a1a1a",
        "border": "#d8d8dd",
        "accent": "#4f7cf5", "accent_hover": "#3b66d8",
        "green": "#16a34a", "green_hover": "#15803d",
        "red": "#dc2626", "red_hover": "#b91c1c",
        "orange": "#d97706", "orange_hover": "#b45309",
        "purple": "#7c3aed", "purple_hover": "#6d28d9",
        "text": "#18181b", "text_dim": "#71717a", "text_faint": "#a1a1aa",
        "input_bg": "#ffffff", "input_text": "#18181b",
        "is_light": True,
    },

    "淡绿": {
        "bg": "#e3efe8", "sidebar": "#d6e7de", "card": "#f2f9f5",
        "card_hover": "#e7f1eb", "console_bg": "#0d1a14",
        "border": "#bdd9c9",
        "accent": "#10b981", "accent_hover": "#059669",
        "green": "#16a34a", "green_hover": "#15803d",
        "red": "#dc2626", "red_hover": "#b91c1c",
        "orange": "#ea580c", "orange_hover": "#c2410c",
        "purple": "#8b5cf6", "purple_hover": "#7c3aed",
        "text": "#1a3a2c", "text_dim": "#5a7a6a", "text_faint": "#93b0a2",
        "input_bg": "#ffffff", "input_text": "#1a3a2c",
        "is_light": True,
    },

    "浅橙": {
        "bg": "#f4eae0", "sidebar": "#f0dfcc", "card": "#faf4ea",
        "card_hover": "#efe5d6", "console_bg": "#1a1410",
        "border": "#e5c9aa",
        "accent": "#f97316", "accent_hover": "#ea580c",
        "green": "#16a34a", "green_hover": "#15803d",
        "red": "#dc2626", "red_hover": "#b91c1c",
        "orange": "#f59e0b", "orange_hover": "#d97706",
        "purple": "#8b5cf6", "purple_hover": "#7c3aed",
        "text": "#3a2418", "text_dim": "#7a5e48", "text_faint": "#b8a08c",
        "input_bg": "#ffffff", "input_text": "#3a2418",
        "is_light": True,
    },

    "浅粉": {
        "bg": "#f5e5eb", "sidebar": "#f0d8e0", "card": "#faf1f5",
        "card_hover": "#f0e0e8", "console_bg": "#1a1116",
        "border": "#e0c0cc",
        "accent": "#e91e63", "accent_hover": "#d4145a",
        "green": "#16a34a", "green_hover": "#15803d",
        "red": "#dc2626", "red_hover": "#b91c1c",
        "orange": "#ea580c", "orange_hover": "#c2410c",
        "purple": "#a855f7", "purple_hover": "#9333ea",
        "text": "#3a1f2a", "text_dim": "#8a6b76", "text_faint": "#c0a4ae",
        "input_bg": "#ffffff", "input_text": "#3a1f2a",
        "is_light": True,
    },
}

DEFAULT_THEME = "深蓝"


class Theme:
    def __init__(self):
        self.current = DEFAULT_THEME
        self.colors = dict(THEMES[DEFAULT_THEME])
        self._callbacks = []
        self._lock = threading.RLock()

    def register(self, callback):
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)
        return callback

    def unregister(self, callback):
        with self._lock:
            try:
                self._callbacks.remove(callback)
            except ValueError:
                pass

    def set(self, name):
        if name not in THEMES:
            return False

        with self._lock:
            self.current = name
            self.colors = dict(THEMES[name])
            callbacks = list(self._callbacks)

        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass
        return True

    def c(self, key):
        return self.colors.get(key, "#ffffff")

    def is_light(self) -> bool:
        """当前主题是否为浅色主题。"""
        return bool(self.colors.get("is_light", False))

    def qss(self):
        c = self.colors
        return f"""
        * {{
            font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
            font-size: 13px;
            outline: none;
        }}
        QWidget {{
            background-color: {c['bg']};
            color: {c['text']};
        }}
        QLabel {{
            background: transparent;
        }}
        QMainWindow, QDialog {{
            background-color: {c['bg']};
        }}

        /* ============================================================
           侧边栏 Logo
           ============================================================ */
        QLabel#LogoTitle {{
            color: {c['text']};
            font-size: 18px;
            font-weight: bold;
            letter-spacing: 0.5px;
            background: transparent;
        }}
        QLabel#LogoSub {{
            color: {c['text_faint']};
            font-size: 11px;
            letter-spacing: 0.3px;
            background: transparent;
        }}

        /* ============================================================
           卡片
           ============================================================ */
        QFrame#Card {{
            background-color: {c['card']};
            border: 1px solid {c['border']};
            border-radius: 10px;
        }}
        QFrame#CardFlat {{
            background-color: {c['card']};
            border: none;
            border-radius: 10px;
        }}

        /* ============================================================
           侧边栏
           ============================================================ */
        QFrame#Sidebar {{
            background-color: {c['sidebar']};
            border: none;
        }}
        QListWidget#NavList {{
            background-color: transparent;
            border: none;
            outline: none;
            padding: 4px 0;
        }}
        QListWidget#NavList::item {{
            color: {c['text_dim']};
            padding: 10px 20px 10px 28px;
            margin: 1px 12px;
            border-radius: 6px;
            border-left: 3px solid transparent;
        }}
        QListWidget#NavList::item:hover {{
            background-color: {c['card_hover']};
            color: {c['text']};
        }}
        QListWidget#NavList::item:selected {{
            background-color: {c['card']};
            color: {c['text']};
            border-left: 3px solid {c['accent']};
        }}

        /* ============================================================
           按钮
           ============================================================ */
        QPushButton {{
            background-color: {c['card']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 13px;
            min-height: 20px;
        }}
        QPushButton:hover {{
            background-color: {c['card_hover']};
            border-color: {c['accent']};
        }}
        QPushButton:pressed {{
            background-color: {c['border']};
        }}
        QPushButton:disabled {{
            color: {c['text_faint']};
        }}
        QPushButton#Accent {{
            background-color: {c['accent']};
            color: #ffffff;
            border: none;
        }}
        QPushButton#Accent:hover {{
            background-color: {c['accent_hover']};
        }}
        QPushButton#Green {{
            background-color: {c['green']};
            color: #ffffff;
            border: none;
        }}
        QPushButton#Green:hover {{
            background-color: {c['green_hover']};
        }}
        QPushButton#Red {{
            background-color: {c['red']};
            color: #ffffff;
            border: none;
        }}
        QPushButton#Red:hover {{
            background-color: {c['red_hover']};
        }}
        QPushButton#Purple {{
            background-color: {c['purple']};
            color: #ffffff;
            border: none;
        }}
        QPushButton#Purple:hover {{
            background-color: {c['purple_hover']};
        }}
        QPushButton#Orange {{
            background-color: {c['orange']};
            color: #ffffff;
            border: none;
        }}
        QPushButton#Orange:hover {{
            background-color: {c['orange_hover']};
        }}
        QPushButton#Ghost {{
            background-color: transparent;
            color: {c['text_dim']};
            border: 1px solid {c['border']};
        }}
        QPushButton#Ghost:hover {{
            color: {c['text']};
            background-color: {c['card_hover']};
            border-color: {c['accent']};
        }}
        QPushButton#Danger {{
            background-color: transparent;
            color: {c['red']};
            border: 1px solid {c['border']};
        }}
        QPushButton#Danger:hover {{
            color: #ffffff;
            background-color: {c['red']};
            border-color: {c['red']};
        }}
        QPushButton#Subtle {{
            background-color: transparent;
            color: {c['text_dim']};
            border: none;
            padding: 4px 8px;
        }}
        QPushButton#Subtle:hover {{
            color: {c['text']};
            background-color: {c['card_hover']};
        }}

        /* ============================================================
           ★ 单行输入框（浅色主题下白底黑字）
           ============================================================ */
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
            background-color: {c['input_bg']};
            color: {c['input_text']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            padding: 6px 10px;
            selection-background-color: {c['accent']};
        }}
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QComboBox:focus {{
            border-color: {c['accent']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {c['card']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            selection-background-color: {c['accent']};
            outline: none;
        }}

        /* ============================================================
           ★ 多行文本框（控制台 / 日志，永远深色黑底）
           ============================================================ */
        QPlainTextEdit, QTextEdit {{
            background-color: {c['console_bg']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            padding: 6px 10px;
            selection-background-color: {c['accent']};
        }}
        QPlainTextEdit:focus, QTextEdit:focus {{
            border-color: {c['accent']};
        }}

        /* ============================================================
           复选框
           ============================================================ */
        QCheckBox {{
            spacing: 8px;
            color: {c['text']};
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid {c['border']};
            background-color: {c['input_bg']};
        }}
        QCheckBox::indicator:hover {{
            border-color: {c['accent']};
        }}
        QCheckBox::indicator:checked {{
            background-color: {c['accent']};
            border-color: {c['accent']};
        }}

        /* ============================================================
           滚动条
           ============================================================ */
        QScrollArea {{
            background-color: transparent;
            border: none;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {c['border']};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {c['accent']};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 8px;
            border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: {c['border']};
            border-radius: 4px;
            min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {c['accent']};
        }}

        /* ============================================================
           标签页
           ============================================================ */
        QTabWidget::pane {{
            background-color: {c['card']};
            border: 1px solid {c['border']};
            border-radius: 8px;
            top: -1px;
        }}
        QTabBar {{
            background: transparent;
            qproperty-drawBase: 0;
        }}
        QTabBar::tab {{
            background-color: transparent;
            color: {c['text_dim']};
            padding: 7px 14px;
            margin-right: 2px;
            border: none;
            border-bottom: 2px solid transparent;
        }}
        QTabBar::tab:hover {{
            color: {c['text']};
        }}
        QTabBar::tab:selected {{
            color: {c['accent']};
            border-bottom: 2px solid {c['accent']};
            background-color: transparent;
        }}

        /* ============================================================
           文本样式
           ============================================================ */
        QLabel#PageTitle {{
            font-size: 22px;
            font-weight: bold;
            color: {c['text']};
        }}
        QLabel#CardTitle {{
            font-size: 13px;
            font-weight: bold;
            color: {c['text']};
        }}
        QLabel#SectionTitle {{
            font-size: 12px;
            font-weight: bold;
            color: {c['text_dim']};
            letter-spacing: 0.5px;
        }}
        QLabel#StatValue {{
            font-size: 26px;
            font-weight: bold;
            color: {c['text']};
        }}
        QLabel#Dim {{
            color: {c['text_dim']};
        }}
        QLabel#Faint {{
            color: {c['text_faint']};
        }}
        QLabel#Muted {{
            color: {c['text_dim']};
            font-size: 12px;
        }}

        /* ============================================================
           列表
           ============================================================ */
        QListWidget {{
            background-color: transparent;
            border: none;
            outline: none;
        }}
        QListWidget::item {{
            padding: 8px 12px;
            border-radius: 6px;
            margin: 2px 0;
            color: {c['text']};
        }}
        QListWidget::item:hover {{
            background-color: {c['card_hover']};
        }}
        QListWidget::item:selected {{
            background-color: {c['accent']};
            color: #ffffff;
        }}

        /* ============================================================
           分割线
           ============================================================ */
        QFrame#HLine {{
            background-color: {c['border']};
            max-height: 1px;
            border: none;
        }}
        QFrame#VLine {{
            background-color: {c['border']};
            max-width: 1px;
            border: none;
        }}

        /* ============================================================
           状态条
           ============================================================ */
        QLabel#StatusChip {{
            color: {c['text_dim']};
            background-color: {c['card']};
            border: 1px solid {c['border']};
            border-radius: 12px;
            padding: 4px 12px;
            font-size: 12px;
        }}
        """


theme = Theme()