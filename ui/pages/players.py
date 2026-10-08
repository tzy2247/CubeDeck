import threading
import customtkinter as ctk
from core.theme import C
from ui.pages.player_detail import PlayerDetailWindow


class PlayersPage:
    def __init__(self, parent, app):
        self.app = app
        self.f = app.fonts
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    def _build(self):
        f = self.f
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)

        # 顶部栏
        bar = ctk.CTkFrame(self.frame, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        bar.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(bar, text="在线玩家", font=f["h1"],
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        self.count_label = ctk.CTkLabel(bar, text="", font=f["small"],
                                        text_color=C["text_dim"])
        self.count_label.grid(row=0, column=1, padx=(0, 12))

        ctk.CTkButton(bar, text="🔄  刷新", width=100, height=38, corner_radius=10,
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"], text_color=C["text_dim"],
                      font=f["body"], command=self.refresh).grid(row=0, column=2)

        # 玩家列表
        self.list_frame = ctk.CTkScrollableFrame(
            self.frame, fg_color=C["card"], corner_radius=16,
            border_width=1, border_color=C["border"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        self.list_frame.grid(row=1, column=0, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)
        self._empty("点击「刷新」加载在线玩家")

    # ---------- 生命周期 ----------
    def on_show(self):
        self.refresh()

    def on_rcon_connected(self):
        self.refresh()

    def on_server_stopped(self):
        self._empty("服务器未运行")

    # ---------- 列表 ----------
    def _empty(self, text):
        for w in self.list_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.list_frame, text=text, font=self.f["body"],
                     text_color=C["text_faint"]).pack(pady=30)
        self.count_label.configure(text="")

    def refresh(self):
        if not (self.app.rcon_client and self.app.rcon_client.connected):
            self._empty("RCON 未连接")
            return
        self.count_label.configure(text="读取中…", text_color=C["text_dim"])
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        try:
            resp = self.app.rcon_client.command("list") or ""
            names = []
            if ":" in resp:
                tail = resp.split(":", 1)[1].strip()
                if tail:
                    names = [n.strip() for n in tail.split(",") if n.strip()]
            self.app.ui(self._render, names)
        except Exception as e:
            self.app.log_to_console(f"获取玩家列表失败：{e}", "error")
            self.app.ui(self._render, [])

    def _render(self, names):
        for w in self.list_frame.winfo_children():
            w.destroy()

        if not names:
            self._empty("当前没有在线玩家")
            return

        self.count_label.configure(text=f"共 {len(names)} 人",
                                   text_color=C["green"])
        for name in names:
            self._row(name)

    def _row(self, name):
        f = self.f
        row = ctk.CTkFrame(self.list_frame, fg_color=C["card_hover"],
                           corner_radius=10, height=52)
        row.pack(fill="x", padx=6, pady=4)
        row.pack_propagate(False)  # ★ 让行高固定，子控件不撑开

        # ---- 左侧：图标 + 名字 + 详情 ----
        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=(14, 8), pady=8)

        ctk.CTkLabel(left, text="🎮", font=ctk.CTkFont(size=18),
                     text_color=C["accent"]).pack(side="left")
        ctk.CTkLabel(left, text=name, font=f["h2"], text_color=C["text"],
                     anchor="w").pack(side="left", padx=(10, 0))

        ctk.CTkButton(
            left, text="🔧  详情", width=90, height=30, corner_radius=8,
            font=f["small"], fg_color=C["accent"],
            hover_color=C["accent_hover"],
            command=lambda n_=name: self._open_detail(n_),
        ).pack(side="left", padx=(14, 0))

        # ---- 右侧：按钮组用 place 绝对定位，绝不被压缩 ----
        btn_bar = ctk.CTkFrame(row, fg_color="transparent", width=290, height=52)
        btn_bar.place(relx=1.0, rely=0.5, anchor="e", x=-12)

        quick = [
            ("击杀", f"kill {name}", C["red"]),
            ("踢出", f"kick {name}", C["orange"]),
            ("封禁", f"ban {name}", "#b91c1c"),
            ("OP", f"op {name}", C["green"]),
        ]
        for i, (label, cmd, color) in enumerate(quick):
            ctk.CTkButton(
                btn_bar, text=label, width=60, height=30, corner_radius=8,
                font=f["small"], fg_color="transparent", hover_color=color,
                text_color=C["text_dim"], border_width=1,
                border_color=C["border"],
                command=lambda c_=cmd: self.app.quick_rcon(c_),
            ).place(x=i * 68, y=11)

    def _open_detail(self, name):
        PlayerDetailWindow(self.app, name)