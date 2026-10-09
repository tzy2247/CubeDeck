"""主题系统：配色方案 + QSS 样式表。"""

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
    },
    "深青绿": {
        "bg": "#0a1415", "sidebar": "#0f1c1d", "card": "#142424",
        "card_hover": "#1c2e2e", "console_bg": "#071011",
        "border": "#1d3334",
        "accent": "#0d9488", "accent_hover": "#0f766e",
        "green": "#22c55e", "green_hover": "#16a34a",
        "red": "#e74c3c", "red_hover": "#c0392b",
        "orange": "#f39c12", "orange_hover": "#d68910",
        "purple": "#8b5cf6", "purple_hover": "#7c3aed",
        "text": "#dcefed", "text_dim": "#86a5a2", "text_faint": "#5d7674",
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
    },
    "暗橙": {
        "bg": "#15100a", "sidebar": "#1e1610", "card": "#261c12",
        "card_hover": "#33251a", "console_bg": "#0f0b07",
        "border": "#3a2a1c",
        "accent": "#ea580c", "accent_hover": "#c2410c",
        "green": "#16a34a", "green_hover": "#15803d",
        "red": "#dc2626", "red_hover": "#b91c1c",
        "orange": "#f59e0b", "orange_hover": "#d97706",
        "purple": "#8b5cf6", "purple_hover": "#7c3aed",
        "text": "#f5ede2", "text_dim": "#b9a896", "text_faint": "#8a7861",
    },
    "玫瑰红": {
        "bg": "#160a0f", "sidebar": "#1f0e16", "card": "#26121c",
        "card_hover": "#321926", "console_bg": "#10070a",
        "border": "#3a1c29",
        "accent": "#e11d48", "accent_hover": "#be123c",
        "green": "#16a34a", "green_hover": "#15803d",
        "red": "#dc2626", "red_hover": "#b91c1c",
        "orange": "#ea580c", "orange_hover": "#c2410c",
        "purple": "#a855f7", "purple_hover": "#9333ea",
        "text": "#f7e6ea", "text_dim": "#bf95a1", "text_faint": "#8a6570",
    },
}

DEFAULT_THEME = "深蓝"


class Theme:
    def __init__(self):
        self.current = DEFAULT_THEME
        self.colors = dict(THEMES[DEFAULT_THEME])

    def set(self, name):
        if name not in THEMES:
            return False
        self.current = name
        self.colors = dict(THEMES[name])
        return True

    def c(self, key):
        return self.colors.get(key, "#ffffff")

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
           输入
           ============================================================ */
        QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox,
        QComboBox {{
            background-color: {c['console_bg']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            padding: 6px 10px;
            selection-background-color: {c['accent']};
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
        QSpinBox:focus, QComboBox:focus {{
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
            background-color: {c['console_bg']};
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
           状态条（页头右上角小徽章）
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