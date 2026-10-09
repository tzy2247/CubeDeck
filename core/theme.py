"""全局配色与字体，支持多主题切换。"""

FONT_FAMILY = "Microsoft YaHei UI"
MONO_FAMILY = "Consolas"


# ============================================================
#  主题库
#  设计原则：
#    1. 背景层次用明度区分（bg < sidebar < card < hover）
#    2. 所有语义色（accent / green / red / orange / purple）
#       保持中等偏深明度，白字放上去永远清晰
#    3. 主题之间用「背景色调 + 主色相」区分，不用「浅色」
# ============================================================
THEMES = {
    "深蓝 (默认)": {
        "bg": "#0f1117", "sidebar": "#151a24", "card": "#1a1f2b",
        "card_hover": "#222836", "console_bg": "#0d1017",
        "border": "#262d3d",
        "accent": "#4f8cff", "accent_hover": "#3d78e8",
        "green": "#2ecc71", "green_hover": "#27ae60",
        "red": "#e74c3c", "red_hover": "#c0392b",
        "orange": "#f39c12", "orange_hover": "#d68910",
        "purple": "#9b59b6", "purple_hover": "#8e44ad",
        "text": "#e6e9f0", "text_dim": "#8b93a7", "text_faint": "#7d8496",
    },
    "深紫": {
        "bg": "#0e0a1a", "sidebar": "#161028", "card": "#1d1633",
        "card_hover": "#261f42", "console_bg": "#0a0714",
        "border": "#2c2349",
        "accent": "#8b5cf6", "accent_hover": "#7c3aed",
        "green": "#2ecc71", "green_hover": "#27ae60",
        "red": "#e74c3c", "red_hover": "#c0392b",
        "orange": "#f39c12", "orange_hover": "#d68910",
        "purple": "#c084fc", "purple_hover": "#a855f7",
        "text": "#e9e6f5", "text_dim": "#9a92b0", "text_faint": "#847da0",
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
        "text": "#dcefed", "text_dim": "#86a5a2", "text_faint": "#6e8c89",
    },
    "午夜黑": {
        "bg": "#000000", "sidebar": "#0a0a0a", "card": "#131313",
        "card_hover": "#1c1c1c", "console_bg": "#050505",
        "border": "#222222",
        # 主色改成深蓝，白字可见
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
        # 主色橙稍微调深，配白字清晰
        "accent": "#ea580c", "accent_hover": "#c2410c",
        # 绿色换成中绿，不再红配绿
        "green": "#16a34a", "green_hover": "#15803d",
        "red": "#dc2626", "red_hover": "#b91c1c",
        "orange": "#f59e0b", "orange_hover": "#d97706",
        "purple": "#8b5cf6", "purple_hover": "#7c3aed",
        "text": "#f5ede2", "text_dim": "#b9a896", "text_faint": "#9a8771",
    },
    "玫瑰红": {
        "bg": "#160a0f", "sidebar": "#1f0e16", "card": "#26121c",
        "card_hover": "#321926", "console_bg": "#10070a",
        "border": "#3a1c29",
        "accent": "#e11d48", "accent_hover": "#be123c",
        # 绿改成中绿，和白字、玫红都协调
        "green": "#16a34a", "green_hover": "#15803d",
        "red": "#dc2626", "red_hover": "#b91c1c",
        "orange": "#ea580c", "orange_hover": "#c2410c",
        "purple": "#a855f7", "purple_hover": "#9333ea",
        "text": "#f7e6ea", "text_dim": "#bf95a1", "text_faint": "#a37b86",
    },
}

DEFAULT_THEME = "深蓝 (默认)"

C = dict(THEMES[DEFAULT_THEME])
_current_theme = DEFAULT_THEME


def get_theme_names():
    return list(THEMES.keys())


def get_current_theme():
    return _current_theme


def set_theme(name):
    global _current_theme
    if name not in THEMES:
        return False
    _current_theme = name
    C.clear()
    C.update(THEMES[name])
    return True


def load_theme_from_config(cfg):
    set_theme(cfg.get("theme", DEFAULT_THEME))


# ============================================================
#  字体
# ============================================================
def make_fonts():
    import customtkinter as ctk
    return {
        "title": ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold"),
        "h1":    ctk.CTkFont(family=FONT_FAMILY, size=17, weight="bold"),
        "h2":    ctk.CTkFont(family=FONT_FAMILY, size=14, weight="bold"),
        "body":  ctk.CTkFont(family=FONT_FAMILY, size=13),
        "small": ctk.CTkFont(family=FONT_FAMILY, size=11),
        "stat":  ctk.CTkFont(family=FONT_FAMILY, size=28, weight="bold"),
        "mono":  ctk.CTkFont(family=MONO_FAMILY, size=12),
    }


# ============================================================
#  间距 / 圆角
# ============================================================
SPACING = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24}
RADIUS = {"card": 14, "button": 10, "input": 8, "small": 6}


def pick_text_color(bg_color_name: str) -> str:
    """方案 A 下所有语义色都用白字。"""
    return "#ffffff"


# 为每套主题补齐 *_text 键（供老代码的 C["green_text"] 等引用）
for _name, _t in THEMES.items():
    for _k in ("accent", "green", "red", "orange", "purple"):
        _t.setdefault(f"{_k}_text", "#ffffff")

# 重新同步到全局 C
C.clear()
C.update(THEMES[_current_theme])

# ============================================================
#  按钮样式辅助
# ============================================================
def accent_btn_kwargs():
    """主操作按钮：蓝底白字"""
    return {
        "fg_color": C["accent"],
        "hover_color": C["accent_hover"],
        "text_color": "#ffffff",
    }


def green_btn_kwargs():
    """成功/启动按钮：绿底白字"""
    return {
        "fg_color": C["green"],
        "hover_color": C["green_hover"],
        "text_color": "#ffffff",
    }


def red_btn_kwargs():
    """危险/停止按钮：红底白字"""
    return {
        "fg_color": C["red"],
        "hover_color": C["red_hover"],
        "text_color": "#ffffff",
    }


def orange_btn_kwargs():
    """警告按钮：橙底白字"""
    return {
        "fg_color": C["orange"],
        "hover_color": C["orange_hover"],
        "text_color": "#ffffff",
    }


def purple_btn_kwargs():
    """备份/次要操作按钮：紫底白字"""
    return {
        "fg_color": C["purple"],
        "hover_color": C["purple_hover"],
        "text_color": "#ffffff",
    }


def ghost_btn_kwargs():
    """透明边框按钮：刷新/取消/次要操作"""
    return {
        "fg_color": "transparent",
        "hover_color": C["card_hover"],
        "border_width": 1,
        "border_color": C["border"],
        "text_color": C["text_dim"],
    }


def danger_ghost_btn_kwargs():
    """危险操作的透明按钮：删除/移除"""
    return {
        "fg_color": "transparent",
        "hover_color": "#3b1f24",
        "border_width": 1,
        "border_color": C["border"],
        "text_color": C["text_dim"],
    }