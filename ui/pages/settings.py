import os
from pathlib import Path
from tkinter import filedialog, messagebox
import customtkinter as ctk
from core.theme import C
from core.config import save_config


class SettingsPage:
    def __init__(self, parent, app):
        self.app = app
        self.f = app.fonts
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()
        self._reload()

    def _build(self):
        f = self.f
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(
            self.frame, fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        # ---- 服务器 ----
        c1 = self._card(scroll, "🖥   服务器设置", 0)
        self.e_server = self._path_row(c1, "服务器目录", "dir")
        self.e_java = self._path_row(c1, "Java 路径", "file")
        self.e_xmx = self._entry_row(c1, "最大内存 (-Xmx)")
        self.e_xms = self._entry_row(c1, "初始内存 (-Xms)")
        self.e_extra = self._entry_row(c1, "JVM 额外参数",
                                       placeholder="-XX:+UseG1GC -XX:MaxGCPauseMillis=200 …")

        # ---- RCON ----
        c2 = self._card(scroll, "🔐   RCON 设置", 1)
        self.e_port = self._entry_row(c2, "RCON 端口")
        self.e_pwd = self._entry_row(c2, "RCON 密码", show="•")

        # ---- 自动备份 & 恢复 ----
        c3 = self._card(scroll, "🕒   自动备份 & 恢复", 2)

        row = ctk.CTkFrame(c3, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(4, 10))
        ctk.CTkLabel(row, text="启用自动备份", font=f["body"],
                     text_color=C["text"], width=140, anchor="w").pack(side="left")
        self.var_auto = ctk.StringVar(value="false")
        ctk.CTkSwitch(row, text="", variable=self.var_auto,
                      onvalue="true", offvalue="false",
                      progress_color=C["accent"]).pack(side="left")

        self.e_interval = self._entry_row(c3, "备份间隔（分钟）")
        self.e_keep = self._entry_row(c3, "保留备份份数")

        row2 = ctk.CTkFrame(c3, fg_color="transparent")
        row2.pack(fill="x", padx=18, pady=(4, 14))
        ctk.CTkLabel(row2, text="崩溃自动重启", font=f["body"],
                     text_color=C["text"], width=140, anchor="w").pack(side="left")
        self.var_restart = ctk.StringVar(value="false")
        ctk.CTkSwitch(row2, text="", variable=self.var_restart,
                      onvalue="true", offvalue="false",
                      progress_color=C["accent"]).pack(side="left")

        # ---- 自动清理掉落物 ----
        c4 = self._card(scroll, "🧹   全局掉落物清理", 3)

        row3 = ctk.CTkFrame(c4, fg_color="transparent")
        row3.pack(fill="x", padx=18, pady=(4, 10))
        ctk.CTkLabel(row3, text="启用全局清理", font=f["body"],
                     text_color=C["text"], width=140, anchor="w").pack(side="left")
        self.var_drop_clean = ctk.StringVar(value="false")
        ctk.CTkSwitch(row3, text="", variable=self.var_drop_clean,
                      onvalue="true", offvalue="false",
                      progress_color=C["accent"]).pack(side="left")

        self.e_drop_interval = self._entry_row(c4, "全局清理间隔（分钟）")

        ctk.CTkLabel(
            c4,
            text="提示：全局清理开启时，清理区自动清理暂停。关闭后，"
                 "清理区将按各自间隔独立清理。",
            font=f["small"], text_color=C["text_faint"],
            justify="left", wraplength=600,
        ).pack(anchor="w", padx=18, pady=(4, 12))

        # ---- 保存 ----
        bar = ctk.CTkFrame(scroll, fg_color="transparent")
        bar.grid(row=4, column=0, sticky="ew", pady=(10, 20))

        ctk.CTkButton(bar, text="💾   保存配置", height=46, width=180, corner_radius=12,
                      font=f["h2"], fg_color=C["accent"], hover_color=C["accent_hover"],
                      command=self.save).pack(side="left")
        ctk.CTkButton(bar, text="↺   重新加载", height=46, width=140, corner_radius=12,
                      font=f["h2"], fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"], text_color=C["text_dim"],
                      command=self._reload).pack(side="left", padx=(12, 0))

    # ---------- 组件工厂 ----------
    def _card(self, parent, title, row):
        card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=16,
                            border_width=1, border_color=C["border"])
        card.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(card, text=title, font=self.f["h1"], text_color=C["text"],
                     anchor="w").pack(fill="x", padx=18, pady=(16, 8))
        return card

    def _entry_row(self, card, label, show=None, placeholder=None):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(4, 10))
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text=label, font=self.f["body"], text_color=C["text"],
                     width=140, anchor="w").grid(row=0, column=0, sticky="w")
        e = ctk.CTkEntry(row, height=38, corner_radius=10, font=self.f["body"],
                         fg_color=C["console_bg"], border_color=C["border"],
                         border_width=1, show=show,
                         placeholder_text=placeholder or "")
        e.grid(row=0, column=1, sticky="ew")
        return e

    def _path_row(self, card, label, kind):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(4, 10))
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text=label, font=self.f["body"], text_color=C["text"],
                     width=140, anchor="w").grid(row=0, column=0, sticky="w")
        e = ctk.CTkEntry(row, height=38, corner_radius=10, font=self.f["body"],
                         fg_color=C["console_bg"], border_color=C["border"],
                         border_width=1)
        e.grid(row=0, column=1, sticky="ew")

        def browse():
            if kind == "dir":
                p = filedialog.askdirectory(initialdir=e.get() or ".")
            else:
                p = filedialog.askopenfilename(
                    initialdir=os.path.dirname(e.get() or "."),
                    filetypes=[("Java 可执行文件", "java*.exe"), ("所有文件", "*.*")],
                )
            if p:
                e.delete(0, "end")
                e.insert(0, p)

        ctk.CTkButton(row, text="浏览…", width=80, height=38, corner_radius=10,
                      font=self.f["body"], fg_color="transparent",
                      hover_color=C["card_hover"], border_width=1,
                      border_color=C["border"], text_color=C["text_dim"],
                      command=browse).grid(row=0, column=2, padx=(10, 0))
        return e

    # ---------- 读写 ----------
    def _set_entry(self, entry, value):
        entry.delete(0, "end")
        entry.insert(0, str(value))

    def on_show(self):
        self._reload()

    def _reload(self):
        cfg = self.app.config_data
        self._set_entry(self.e_server, cfg.get("server_path", ""))
        self._set_entry(self.e_java, cfg.get("java_path", ""))
        self._set_entry(self.e_xmx, cfg.get("memory_xmx", "4G"))
        self._set_entry(self.e_xms, cfg.get("memory_xms", "2G"))
        self._set_entry(self.e_extra, cfg.get("jvm_args", ""))
        self._set_entry(self.e_port, cfg.get("rcon_port", 25575))
        self._set_entry(self.e_pwd, cfg.get("rcon_password", ""))
        self._set_entry(self.e_interval, cfg.get("auto_backup_interval_min", 60))
        self._set_entry(self.e_keep, cfg.get("auto_backup_keep", 10))
        self.var_auto.set("true" if cfg.get("auto_backup_enabled") else "false")
        self.var_restart.set("true" if cfg.get("auto_restart") else "false")
        self._set_entry(self.e_drop_interval,
                        cfg.get("auto_drop_clean_interval_min", 30))
        self.var_drop_clean.set(
            "true" if cfg.get("global_clean_enabled") else "false")

    def save(self):
        try:
            port = int(self.e_port.get().strip())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showerror("参数错误", "RCON 端口必须是 1-65535 之间的整数")
            return
        try:
            interval = int(self.e_interval.get().strip())
            if interval < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("参数错误", "备份间隔必须是 ≥1 的整数")
            return
        try:
            keep = int(self.e_keep.get().strip())
            if keep < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("参数错误", "保留份数必须是 ≥1 的整数")
            return
        try:
            drop_interval = int(self.e_drop_interval.get().strip())
            if drop_interval < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("参数错误", "清理间隔必须是 ≥1 的整数（分钟）")
            return

        cfg = self.app.config_data
        cfg.update({
            "server_path":              self.e_server.get().strip(),
            "java_path":                self.e_java.get().strip(),
            "memory_xmx":               self.e_xmx.get().strip() or "4G",
            "memory_xms":               self.e_xms.get().strip() or "2G",
            "jvm_args":                 self.e_extra.get().strip(),
            "rcon_port":                port,
            "rcon_password":            self.e_pwd.get(),
            "auto_backup_enabled":      self.var_auto.get() == "true",
            "auto_backup_interval_min": interval,
            "auto_backup_keep":         keep,
            "auto_restart":             self.var_restart.get() == "true",
            "global_clean_enabled":      self.var_drop_clean.get() == "true",
            "auto_drop_clean_interval_min": drop_interval,
        })

        if save_config(cfg):
            self.app.server_path = Path(cfg["server_path"])
            self.app.log_to_console("配置已保存", "ok")
            messagebox.showinfo("保存成功", "配置已写入 server_config.json")
        else:
            messagebox.showerror("保存失败", "无法写入 server_config.json")