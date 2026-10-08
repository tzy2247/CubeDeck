"""全局配色与字体。"""

C = {
    "bg":          "#0f1117",
    "sidebar":     "#151a24",
    "card":        "#1a1f2b",
    "card_hover":  "#222836",
    "console_bg":  "#0d1017",
    "border":      "#262d3d",
    "accent":      "#4f8cff",
    "accent_hover":"#3d78e8",
    "green":       "#2ecc71",
    "green_hover": "#27ae60",
    "red":         "#e74c3c",
    "red_hover":   "#c0392b",
    "orange":      "#f39c12",
    "orange_hover":"#d68910",
    "purple":      "#9b59b6",
    "purple_hover":"#8e44ad",
    "text":        "#e6e9f0",
    "text_dim":    "#8b93a7",
    "text_faint":  "#5d6577",
}

FONT_FAMILY = "Microsoft YaHei UI"
MONO_FAMILY = "Consolas"


def make_fonts():
    """在 CTk 初始化之后调用，避免提前导入 customtkinter。"""
    import customtkinter as ctk
    return {
        "title": ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold"),
        "h1":    ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
        "h2":    ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
        "body":  ctk.CTkFont(family=FONT_FAMILY, size=13),
        "small": ctk.CTkFont(family=FONT_FAMILY, size=11),
        "stat":  ctk.CTkFont(family=FONT_FAMILY, size=24, weight="bold"),
        "mono":  ctk.CTkFont(family=MONO_FAMILY, size=12),
    }