"""权限管理页：策略配置、玩家授权、实时违规显示、监控诊断。"""
import time
import customtkinter as ctk
from tkinter import messagebox
from core.theme import C
from core.commands import get_commands_for_version
from core.permissions import save_permissions


MODE_OPTIONS = [
    ("关闭审计", "off"),
    ("仅记录", "log"),
    ("警告玩家", "warn"),
    ("警告+踢出", "kick"),
    ("警告+封禁", "ban"),
]
MODE_LABEL = {key: label for label, key in MODE_OPTIONS}
MODE_KEY = {label: key for label, key in MODE_OPTIONS}


class PermissionsPage:
    def __init__(self, parent, app):
        self.app = app
        self.f = app.fonts
        self._selected_player = None
        self._check_vars = {}
        self._player_rows = {}
        self._monitor_tick_after = None

        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    # ========================================================
    #  构建
    # ========================================================
    def _build(self):
        f = self.f
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(2, weight=1)

        # ---- 顶部：全局策略 ----
        top = ctk.CTkFrame(self.frame, fg_color=C["card"], corner_radius=14,
                           border_width=1, border_color=C["border"])
        top.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        ctk.CTkLabel(top, text="⚖️   权限审计策略", font=f["h1"],
                     text_color=C["text"]).pack(anchor="w", padx=18, pady=(14, 8))

        row1 = ctk.CTkFrame(top, fg_color="transparent")
        row1.pack(fill="x", padx=18, pady=(0, 10))

        ctk.CTkLabel(row1, text="执法模式", font=f["body"],
                     text_color=C["text"], width=90, anchor="w").pack(side="left")
        self.mode_var = ctk.StringVar(value="仅记录")
        ctk.CTkOptionMenu(
            row1, values=[label for label, _ in MODE_OPTIONS],
            variable=self.mode_var, width=180,
            fg_color=C["console_bg"], button_color=C["accent"],
            button_hover_color=C["accent_hover"],
        ).pack(side="left", padx=(10, 30))

        ctk.CTkLabel(row1, text="窗口(秒)", font=f["body"],
                     text_color=C["text"], width=70, anchor="w").pack(side="left")
        self.window_entry = ctk.CTkEntry(row1, height=34, width=80,
                                         corner_radius=8, font=f["body"],
                                         fg_color=C["console_bg"],
                                         border_color=C["border"], border_width=1)
        self.window_entry.pack(side="left", padx=(10, 30))
        self.window_entry.insert(0, "300")

        ctk.CTkLabel(row1, text="踢出阈值", font=f["body"],
                     text_color=C["text"], width=80, anchor="w").pack(side="left")
        self.kick_entry = ctk.CTkEntry(row1, height=34, width=60,
                                       corner_radius=8, font=f["body"],
                                       fg_color=C["console_bg"],
                                       border_color=C["border"], border_width=1)
        self.kick_entry.pack(side="left", padx=(10, 20))
        self.kick_entry.insert(0, "3")

        ctk.CTkLabel(row1, text="封禁阈值", font=f["body"],
                     text_color=C["text"], width=80, anchor="w").pack(side="left")
        self.ban_entry = ctk.CTkEntry(row1, height=34, width=60,
                                      corner_radius=8, font=f["body"],
                                      fg_color=C["console_bg"],
                                      border_color=C["border"], border_width=1)
        self.ban_entry.pack(side="left", padx=(10, 0))
        self.ban_entry.insert(0, "10")

        # 保存按钮行
        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.pack(fill="x", padx=18, pady=(0, 6))
        ctk.CTkButton(btns, text="💾  保存策略", width=130, height=38,
                      corner_radius=10, font=f["h2"],
                      fg_color=C["accent"], hover_color=C["accent_hover"],
                      command=self.save_policy).pack(side="left")
        ctk.CTkButton(btns, text="🔄  刷新玩家", width=120, height=38,
                      corner_radius=10, font=f["body"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=self.refresh_players).pack(side="left", padx=(10, 0))
        ctk.CTkButton(btns, text="🗑  清空违规记录", width=140, height=38,
                      corner_radius=10, font=f["body"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=self.clear_violations).pack(side="left", padx=(10, 0))
        self.status = ctk.CTkLabel(btns, text="", font=f["small"],
                                   text_color=C["text_dim"])
        self.status.pack(side="left", padx=(12, 0))

        # ---- 监控状态条 ----
        mon = ctk.CTkFrame(top, fg_color=C["console_bg"], corner_radius=8)
        mon.pack(fill="x", padx=18, pady=(0, 14))

        self.monitor_label = ctk.CTkLabel(
            mon, text="监控状态：未启动", font=f["small"],
            text_color=C["text_dim"], anchor="w", justify="left",
        )
        self.monitor_label.pack(side="left", fill="x", expand=True,
                                padx=12, pady=8)

        ctk.CTkButton(mon, text="🔄 刷新", width=70, height=26, corner_radius=6,
                      font=f["small"], fg_color="transparent",
                      hover_color=C["card_hover"], border_width=1,
                      border_color=C["border"], text_color=C["text_dim"],
                      command=self._refresh_monitor_status
                      ).pack(side="right", padx=8, pady=6)

        # ---- 中部：玩家 + 命令 ----
        mid = ctk.CTkFrame(self.frame, fg_color="transparent")
        mid.grid(row=2, column=0, sticky="nsew")
        mid.grid_columnconfigure(0, weight=1, minsize=200)
        mid.grid_columnconfigure(1, weight=2)
        mid.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(mid, fg_color=C["card"], corner_radius=14,
                            border_width=1, border_color=C["border"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(left, text="玩家", font=f["h2"],
                     text_color=C["text"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 6))

        self.player_list = ctk.CTkScrollableFrame(
            left, fg_color=C["console_bg"], corner_radius=10,
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        self.player_list.grid(row=1, column=0, sticky="nsew",
                              padx=10, pady=(0, 12))

        right = ctk.CTkFrame(mid, fg_color=C["card"], corner_radius=14,
                             border_width=1, border_color=C["border"])
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        self.cmd_header = ctk.CTkLabel(right, text="允许的命令",
                                       font=f["h2"], text_color=C["text"])
        self.cmd_header.grid(row=0, column=0, sticky="w",
                             padx=16, pady=(14, 6))

        self.cmd_scroll = ctk.CTkScrollableFrame(
            right, fg_color=C["console_bg"], corner_radius=10,
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        self.cmd_scroll.grid(row=1, column=0, sticky="nsew",
                             padx=10, pady=(0, 12))

        # ---- 底部：违规记录 ----
        bottom = ctk.CTkFrame(self.frame, fg_color=C["card"],
                              corner_radius=14, height=160,
                              border_width=1, border_color=C["border"])
        bottom.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        bottom.grid_columnconfigure(0, weight=1)
        bottom.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(bottom, text="实时违规记录", font=f["h2"],
                     text_color=C["text"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4))

        self.violation_box = ctk.CTkTextbox(
            bottom, fg_color=C["console_bg"], border_width=0,
            corner_radius=10, font=f["mono"],
            text_color="#f0a8a8", wrap="word", height=110,
        )
        self.violation_box.grid(row=1, column=0, sticky="nsew",
                                padx=12, pady=(0, 12))

    # ========================================================
    #  生命周期
    # ========================================================
    def on_show(self):
        self.load_policy()
        self.refresh_players()
        self._refresh_monitor_status()

    def on_rcon_connected(self):
        self.refresh_players()
        self._refresh_monitor_status()

    # ========================================================
    #  监控诊断
    # ========================================================
    def _refresh_monitor_status(self):
        watcher = getattr(self.app, "_log_watcher", None)

        if watcher is None:
            self.monitor_label.configure(
                text="⚪ 日志监控未启动（服务器未运行）",
                text_color=C["text_faint"])
            return

        if not watcher.is_alive():
            self.monitor_label.configure(
                text="🔴 监控线程已停止",
                text_color=C["red"])
            return

        exists = watcher.log_path.exists()
        exists_str = "存在" if exists else "未生成"

        parts = [
            "🟢 监控运行中",
            f"日志：{exists_str}",
            f"扫描 {watcher.line_count} 行",
            f"精确 {watcher.exact_count}",
            f"反推 {watcher.inferred_count}",
        ]
        if watcher.last_command:
            parts.append(f"最近：{watcher.last_command[:70]}")

        # 如果只有反推、没有精确 → 提示开启 log-player-commands
        if watcher.inferred_count > 0 and watcher.exact_count == 0:
            color = C["orange"]
            parts.append("⚠ 建议开启 log-player-commands 以提高准确度")
        elif watcher.exact_count > 0:
            color = C["green"]
        else:
            color = C["text_dim"]

        self.monitor_label.configure(text="   ".join(parts),
                                     text_color=color)

    # ========================================================
    #  策略读写
    # ========================================================
    def load_policy(self):
        d = self.app.perm_data
        self.mode_var.set(MODE_LABEL.get(d.get("enforcement_mode", "log"),
                                          "仅记录"))
        self.window_entry.delete(0, "end")
        self.window_entry.insert(0, str(d.get("check_window_seconds", 300)))
        self.kick_entry.delete(0, "end")
        self.kick_entry.insert(0, str(d.get("violations_to_kick", 3)))
        self.ban_entry.delete(0, "end")
        self.ban_entry.insert(0, str(d.get("violations_to_ban", 10)))

    def save_policy(self):
        try:
            window = int(self.window_entry.get().strip())
            kick = int(self.kick_entry.get().strip())
            ban = int(self.ban_entry.get().strip())
            if window < 10 or kick < 1 or ban < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("参数错误", "窗口/阈值必须是正整数")
            return

        mode_key = MODE_KEY.get(self.mode_var.get(), "log")
        self.app.perm_data.update({
            "enforcement_mode": mode_key,
            "check_window_seconds": window,
            "violations_to_kick": kick,
            "violations_to_ban": ban,
        })
        if save_permissions(self.app.perm_data):
            self.app.perm_manager.update_data(self.app.perm_data)
            self.app.log_to_console("权限策略已保存", "ok")
            self.status.configure(text="✔ 策略已保存", text_color=C["green"])
        else:
            self.status.configure(text="✖ 保存失败", text_color=C["red"])

    # ========================================================
    #  玩家列表
    # ========================================================
    def refresh_players(self):
        for w in self.player_list.winfo_children():
            w.destroy()
        self._player_rows.clear()

        names = set(self.app.perm_data.get("players", {}).keys())
        try:
            if self.app.rcon_client and self.app.rcon_client.connected:
                resp = self.app.rcon_client.command("list") or ""
                if ":" in resp:
                    tail = resp.split(":", 1)[1].strip()
                    if tail:
                        for n in tail.split(","):
                            n = n.strip()
                            if n:
                                names.add(n)
        except Exception:
            pass

        if not names:
            ctk.CTkLabel(self.player_list, text="没有玩家数据",
                         font=self.f["body"],
                         text_color=C["text_faint"]).pack(pady=20)
            return

        for name in sorted(names):
            self._add_player_row(name)

        if self._selected_player in self._player_rows:
            self._player_rows[self._selected_player].configure(
                fg_color=C["accent"], text_color="#ffffff")

    def _add_player_row(self, name):
        row = ctk.CTkButton(
            self.player_list, text=f"👤  {name}", anchor="w", height=32,
            corner_radius=8, font=self.f["body"],
            fg_color="transparent", hover_color=C["card_hover"],
            text_color=C["text"],
            command=lambda n=name: self._select_player(n),
        )
        row.pack(fill="x", padx=4, pady=1)
        self._player_rows[name] = row

    def _select_player(self, name):
        self._selected_player = name
        for pname, btn in self._player_rows.items():
            if pname == name:
                btn.configure(fg_color=C["accent"], text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent", text_color=C["text"])
        self._render_commands(name)

    # ========================================================
    #  命令勾选（带全选/全不选）
    # ========================================================
    def _render_commands(self, player):
        for w in self.cmd_scroll.winfo_children():
            w.destroy()
        self._check_vars.clear()

        self.cmd_header.configure(text=f"允许 {player} 使用的命令")

        allowed = set(self.app.perm_data.get("players", {}).get(player, []))

        server_ver = self.app.server_info.version
        cmds_by_level = get_commands_for_version(server_ver)

        # 顶部：对当前玩家显示全选/全不选
        top_bar = ctk.CTkFrame(self.cmd_scroll, fg_color="transparent")
        top_bar.pack(fill="x", padx=6, pady=(4, 0))

        def _select_all_global(val):
            for v in self._check_vars.values():
                v.set(val)

        ctk.CTkButton(top_bar, text="☑ 全部选中", width=100, height=28,
                      corner_radius=7, font=self.f["small"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=lambda: _select_all_global(True)
                      ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(top_bar, text="☐ 全部取消", width=100, height=28,
                      corner_radius=7, font=self.f["small"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=lambda: _select_all_global(False)
                      ).pack(side="left")

        for op_level in sorted(cmds_by_level.keys()):
            cmds = cmds_by_level[op_level]

            # 分组标题行 + 该等级的全选/全不选
            head = ctk.CTkFrame(self.cmd_scroll, fg_color="transparent")
            head.pack(fill="x", padx=8, pady=(12, 4))

            ctk.CTkLabel(head, text=f"── 权限等级 {op_level} ──",
                         font=self.f["small"],
                         text_color=C["accent"]).pack(side="left")

            def _level_select(names, val):
                for n, _ in names:
                    var = self._check_vars.get(n)
                    if var is not None:
                        var.set(val)

            ctk.CTkButton(head, text="全选", width=48, height=24,
                          corner_radius=6, font=self.f["small"],
                          fg_color="transparent", hover_color=C["card_hover"],
                          border_width=1, border_color=C["border"],
                          text_color=C["text_dim"],
                          command=lambda ns=cmds: _level_select(ns, True)
                          ).pack(side="right", padx=(4, 0))
            ctk.CTkButton(head, text="全不选", width=58, height=24,
                          corner_radius=6, font=self.f["small"],
                          fg_color="transparent", hover_color=C["card_hover"],
                          border_width=1, border_color=C["border"],
                          text_color=C["text_dim"],
                          command=lambda ns=cmds: _level_select(ns, False)
                          ).pack(side="right")

            grid = ctk.CTkFrame(self.cmd_scroll, fg_color="transparent")
            grid.pack(fill="x", padx=4)
            for i in range(2):
                grid.grid_columnconfigure(i, weight=1, uniform="cmd")

            for i, (cmd_name, desc) in enumerate(cmds):
                var = ctk.BooleanVar(value=cmd_name in allowed)
                self._check_vars[cmd_name] = var

                ctk.CTkCheckBox(
                    grid, text=f"/{cmd_name}  ·  {desc}",
                    variable=var, font=self.f["small"],
                    checkbox_width=18, checkbox_height=18,
                    fg_color=C["accent"], hover_color=C["accent_hover"],
                    text_color=C["text"],
                ).grid(row=i // 2, column=i % 2, sticky="w", padx=6, pady=2)

        if server_ver != (0, 0, 0):
            ver_str = ".".join(map(str, server_ver))
            ctk.CTkLabel(
                self.cmd_scroll,
                text=f"（已根据服务端版本 {ver_str} 过滤命令）",
                font=self.f["small"], text_color=C["text_faint"],
            ).pack(anchor="w", padx=8, pady=(10, 0))

        ctk.CTkButton(
            self.cmd_scroll, text="💾  保存该玩家的授权",
            height=36, corner_radius=10, font=self.f["h2"],
            fg_color=C["green"], hover_color=C["green_hover"],
            command=self.save_player_commands,
        ).pack(fill="x", padx=6, pady=(14, 6))

    def save_player_commands(self):
        if not self._selected_player:
            return
        chosen = [name for name, var in self._check_vars.items() if var.get()]
        self.app.perm_data.setdefault("players", {})[
            self._selected_player] = chosen
        if save_permissions(self.app.perm_data):
            self.app.perm_manager.update_data(self.app.perm_data)
            self.app.log_to_console(
                f"已保存 {self._selected_player} 的授权（{len(chosen)} 条）", "ok")
            self.status.configure(text="✔ 玩家授权已保存", text_color=C["green"])

    # ========================================================
    #  违规显示
    # ========================================================
    def append_violation(self, line: str):
        def do():
            try:
                ts = time.strftime("%H:%M:%S")
                self.violation_box.insert("end", f"[{ts}] {line}\n")
                self.violation_box.see("end")
                total = int(self.violation_box.index("end-1c").split(".")[0])
                if total > 400:
                    self.violation_box.delete("1.0", f"{total - 400}.0")
            except Exception:
                pass
        self.app.ui(do)

    def clear_violations(self):
        self.violation_box.delete("1.0", "end")
        for name in list(getattr(self.app.perm_manager, "_violations", {}).keys()):
            self.app.perm_manager.reset_violation(name)
        self.app.log_to_console("已清空违规记录", "ok")