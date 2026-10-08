"""内嵌式搜索下拉列表（挂在容器 Frame 上，用 place 定位）。"""
import customtkinter as ctk
from core.theme import C, FONT_FAMILY


class SearchDropdown(ctk.CTkFrame):
    """
    挂在对话框内部某个 Frame 上的下拉列表。
    parent 必须是一个 Frame（不是 Toplevel），其 rooty 不含标题栏偏移。
    """

    def __init__(self, parent, anchor_widget, command,
                 width=400, height=240):
        super().__init__(parent, fg_color=C["border"], corner_radius=8,
                         width=width, height=height)
        self._parent = parent           # ← 内部的 frame
        self._anchor = anchor_widget
        self._command = command
        self._values = []
        self._visible = False
        self._width = width
        self._height = height

        self.frame = ctk.CTkScrollableFrame(
            self, fg_color=C["card"], corner_radius=6,
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        self.frame.pack(fill="both", expand=True, padx=1, pady=1)

    # ---------- 显示 / 隐藏 ----------
    def show(self, values):
        self.update_values(values)
        if not self._values:
            self.hide()
            return

        try:
            self._parent.update_idletasks()
        except Exception:
            pass

        try:
            ax = self._anchor.winfo_rootx()
            ay = self._anchor.winfo_rooty()
            aw = self._anchor.winfo_width()
            ah = self._anchor.winfo_height()

            # 参考基准：内部 frame（无标题栏偏移）
            px = self._parent.winfo_rootx()
            py = self._parent.winfo_rooty()

            x = ax - px - 60
            y = ay - py + ah + 2 - 60
            w = max(self._width, aw)
        except Exception:
            x, y, w = 20, 60, self._width

        # CTk 不允许 place 传宽高
        try:
            self.configure(width=w, height=self._height)
        except Exception:
            pass

        self.place(x=x, y=y)
        self.lift()
        self._visible = True

    def hide(self):
        if self._visible:
            self.place_forget()
            self._visible = False

    def is_visible(self):
        return self._visible

    # ---------- 内容 ----------
    def update_values(self, values):
        values = list(values)
        if values == self._values:
            return
        self._values = values

        for w in self.frame.winfo_children():
            w.destroy()

        for v in values:
            ctk.CTkButton(
                self.frame, text=v, anchor="w", height=30, corner_radius=6,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                fg_color="transparent",
                hover_color=C["card_hover"],
                text_color=C["text"],
                command=lambda val=v: self._pick(val),
            ).pack(fill="x", padx=4, pady=1)

    def _pick(self, value):
        self.hide()
        if self._command:
            try:
                self._command(value)
            except Exception:
                pass