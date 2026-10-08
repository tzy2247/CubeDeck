import datetime
import customtkinter as ctk
from core.theme import C


class ConsolePage:
    def __init__(self, parent, app):
        self.app = app
        self.f = app.fonts
        self._history = []
        self._history_idx = -1
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    def _build(self):
        f = self.f
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(0, weight=1)

        card = ctk.CTkFrame(self.frame, fg_color=C["card"], corner_radius=16,
                            border_width=1, border_color=C["border"])
        card.grid(row=0, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)

        self.text = ctk.CTkTextbox(
            card, fg_color=C["console_bg"], border_width=0, corner_radius=12,
            font=f["mono"], wrap="word", text_color="#c8d0e0",
        )
        self.text.grid(row=0, column=0, sticky="nsew", padx=14, pady=(14, 8))

        tw = getattr(self.text, "_textbox", None) or self.text
        for name, color in (
            ("time",   C["text_faint"]),
            ("info",   "#c8d0e0"),
            ("cmd",    "#7dd3fc"),
            ("error",  "#f87171"),
            ("warn",   "#fbbf24"),
            ("ok",     "#4ade80"),
            ("server", "#9aa4bb"),
        ):
            try:
                tw.tag_config(name, foreground=color)
            except Exception:
                pass

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))
        row.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            row, placeholder_text="输入服务器指令，按 Enter 发送（↑/↓ 翻历史）",
            height=42, corner_radius=10, font=f["body"],
            fg_color=C["console_bg"], border_color=C["border"], border_width=1,
        )
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", lambda e: self.send())
        self.entry.bind("<Up>", self._hist_up)
        self.entry.bind("<Down>", self._hist_down)

        ctk.CTkButton(row, text="发送", width=90, height=42, corner_radius=10,
                      font=f["h2"], fg_color=C["accent"], hover_color=C["accent_hover"],
                      command=self.send).grid(row=0, column=1, padx=(10, 0))
        ctk.CTkButton(row, text="清空", width=72, height=42, corner_radius=10,
                      font=f["body"], fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"], text_color=C["text_dim"],
                      command=lambda: self.text.delete("1.0", "end")
                      ).grid(row=0, column=2, padx=(8, 0))

    def append(self, message, tag="info"):
        def do():
            try:
                self.text.insert("end", f"[{datetime.datetime.now():%H:%M:%S}] ", "time")
                self.text.insert("end", f"{message}\n", tag)
                self.text.see("end")
                total = int(self.text.index("end-1c").split(".")[0])
                if total > 2000:
                    self.text.delete("1.0", f"{total - 2000}.0")
            except Exception:
                pass
        self.app.ui(do)

    def send(self):
        cmd = self.entry.get().strip()
        if not cmd:
            return
        self.entry.delete(0, "end")

        if not self._history or self._history[-1] != cmd:
            self._history.append(cmd)
            if len(self._history) > 100:
                self._history.pop(0)
        self._history_idx = -1

        if cmd.lower().lstrip("/").strip() == "stop":
            if self.app.is_running:
                self.app.log_to_console(f"> {cmd}", "cmd")
                self.app.stop_server()
            else:
                self.app.log_to_console("服务器未运行", "warn")
            return

        self.app.quick_rcon(cmd)

    def _hist_up(self, event):
        if not self._history:
            return "break"
        if self._history_idx == -1:
            self._history_idx = len(self._history) - 1
        elif self._history_idx > 0:
            self._history_idx -= 1
        self.entry.delete(0, "end")
        self.entry.insert(0, self._history[self._history_idx])
        return "break"

    def _hist_down(self, event):
        if not self._history or self._history_idx == -1:
            return "break"
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self.entry.delete(0, "end")
            self.entry.insert(0, self._history[self._history_idx])
        else:
            self._history_idx = -1
            self.entry.delete(0, "end")
        return "break"