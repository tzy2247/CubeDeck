import customtkinter as ctk
from core.theme import C


class DashboardPage:
    def __init__(self, parent, app):
        self.app = app
        self.f = app.fonts
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    def _build(self):
        f = self.f
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(3, weight=1)

        # 状态横幅
        banner = ctk.CTkFrame(self.frame, fg_color=C["card"], corner_radius=16,
                              border_width=1, border_color=C["border"])
        banner.grid(row=0, column=0, sticky="ew")
        banner.grid_columnconfigure(1, weight=1)

        self.status_dot = ctk.CTkLabel(banner, text="●",
                                       font=ctk.CTkFont(size=32),
                                       text_color=C["text_faint"])
        self.status_dot.grid(row=0, column=0, rowspan=2, padx=(26, 14), pady=22)

        self.status_text = ctk.CTkLabel(banner, text="服务器未运行", font=f["h1"],
                                        text_color=C["text"], anchor="w")
        self.status_text.grid(row=0, column=1, sticky="w", pady=(22, 0))

        self.status_sub = ctk.CTkLabel(banner, text="点击右侧按钮启动服务器",
                                       font=f["small"], text_color=C["text_dim"],
                                       anchor="w")
        self.status_sub.grid(row=1, column=1, sticky="w", pady=(2, 22))

        self.toggle_btn = ctk.CTkButton(
            banner, text="启动服务器", width=150, height=46, corner_radius=12,
            font=f["h2"], fg_color=C["green"], hover_color=C["green_hover"],
            command=self.app.toggle_server,
        )
        self.toggle_btn.grid(row=0, column=2, rowspan=2, padx=(12, 26), pady=22)

        # 数据卡片
        stats = ctk.CTkFrame(self.frame, fg_color="transparent")
        stats.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        for i in range(4):
            stats.grid_columnconfigure(i, weight=1, uniform="stat")

        self.stat_tps     = self._card(stats, 0, "⚡", "TPS",      "--",       C["accent"])
        self.stat_players = self._card(stats, 1, "👥", "在线玩家", "0 / 0",    C["green"])
        self.stat_mem     = self._card(stats, 2, "🧠", "内存占用", "-- MB",    C["purple"])
        self.stat_uptime  = self._card(stats, 3, "⏱", "运行时长", "--:--:--", C["orange"])

        # 快捷操作
        acts = ctk.CTkFrame(self.frame, fg_color="transparent")
        acts.grid(row=2, column=0, sticky="ew", pady=(20, 0))

        ctk.CTkButton(acts, text="🧹   清理掉落物", height=44, width=160, corner_radius=12,
                      font=f["h2"], fg_color=C["orange"], hover_color=C["orange_hover"],
                      command=self.app.clear_drops).pack(side="left")
        ctk.CTkButton(acts, text="💾   立即备份", height=44, width=160, corner_radius=12,
                      font=f["h2"], fg_color=C["purple"], hover_color=C["purple_hover"],
                      command=self.app.do_backup).pack(side="left", padx=(12, 0))
        ctk.CTkButton(acts, text="🔁   重连 RCON", height=44, width=160, corner_radius=12,
                      font=f["h2"], fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"], text_color=C["text_dim"],
                      command=self.app.manual_reconnect_rcon).pack(side="left", padx=(12, 0))

    def _card(self, parent, col, icon, title, value, color):
        f = self.f
        card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=14,
                            border_width=1, border_color=C["border"])
        padx = (0, 12) if col < 3 else (0, 0)
        card.grid(row=0, column=col, sticky="nsew", padx=padx)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(14, 0))
        ctk.CTkLabel(head, text=icon, font=ctk.CTkFont(size=15),
                     text_color=color).pack(side="left")
        ctk.CTkLabel(head, text=title, font=f["small"],
                     text_color=C["text_dim"]).pack(side="left", padx=(7, 0))

        val = ctk.CTkLabel(card, text=value, font=f["stat"],
                           text_color=C["text"], anchor="w")
        val.pack(fill="x", padx=16, pady=(6, 16))
        return val

    # ---------- 对外 API ----------
    def set_toggle_button(self, state, text, color):
        hover_map = {
            C["green"]:      C["green_hover"],
            C["red"]:        C["red_hover"],
            C["text_faint"]: C["text_faint"],
        }
        self.toggle_btn.configure(state=state, text=text,
                                  fg_color=color,
                                  hover_color=hover_map.get(color, C["accent_hover"]))

    def set_running(self):
        self.set_toggle_button("normal", "停止服务器", C["red"])
        self.status_dot.configure(text_color=C["green"])
        self.status_text.configure(text="服务器运行中")
        self.status_sub.configure(text="进程已启动，正在监听日志…")

    def set_stopping(self):
        self.set_toggle_button("disabled", "停止中…", C["text_faint"])
        self.status_dot.configure(text_color=C["orange"])
        self.status_text.configure(text="服务器正在停止…")
        self.status_sub.configure(text="正在保存世界并关闭进程…")

    def set_stopped(self):
        self.set_toggle_button("normal", "启动服务器", C["green"])
        self.status_dot.configure(text_color=C["text_faint"])
        self.status_text.configure(text="服务器未运行")
        self.status_sub.configure(text="点击右侧按钮启动服务器")
        self.stat_tps.configure(text="--")
        self.stat_players.configure(text="0 / 0")
        self.stat_mem.configure(text="-- MB")
        self.stat_uptime.configure(text="--:--:--")

    def set_tps(self, text):     self.stat_tps.configure(text=text)
    def set_players(self, text): self.stat_players.configure(text=text)
    def set_mem(self, text):     self.stat_mem.configure(text=text)
    def set_uptime(self, text):  self.stat_uptime.configure(text=text)