import datetime
import shutil
import threading
from pathlib import Path
from tkinter import messagebox
import customtkinter as ctk
from core.theme import C
from core.backup import format_size


class BackupPage:
    def __init__(self, parent, app):
        self.app = app
        self.f = app.fonts
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    def _build(self):
        f = self.f
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(self.frame, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(bar, text="历史备份", font=f["h1"],
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(bar, text="🔄   刷新", width=100, height=40, corner_radius=10,
                      font=f["body"], fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"], text_color=C["text_dim"],
                      command=self.refresh).grid(row=0, column=1, padx=(0, 10))
        ctk.CTkButton(bar, text="💾   立即备份", width=140, height=40, corner_radius=10,
                      font=f["h2"], fg_color=C["purple"], hover_color=C["purple_hover"],
                      command=self.app.do_backup).grid(row=0, column=2)

        self.list = ctk.CTkScrollableFrame(
            self.frame, fg_color=C["card"], corner_radius=16,
            border_width=1, border_color=C["border"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        self.list.grid(row=1, column=0, sticky="nsew")
        self.list.grid_columnconfigure(0, weight=1)

    # ---------- 钩子 ----------
    def on_show(self):
        self.refresh()

    def refresh(self):
        for w in self.list.winfo_children():
            w.destroy()

        root = self.app.server_path.parent / "backups"
        if not root.exists():
            self._empty("备份目录不存在")
            return
        backups = sorted(root.glob("backup_*"), key=lambda p: p.name, reverse=True)
        if not backups:
            self._empty("还没有任何备份")
            return
        for bp in backups:
            self._item(bp)

    def _empty(self, text):
        ctk.CTkLabel(self.list, text=text, font=self.f["body"],
                     text_color=C["text_faint"]).pack(pady=40)

    def _item(self, path):
        f = self.f
        item = ctk.CTkFrame(self.list, fg_color="transparent", corner_radius=10)
        item.pack(fill="x", padx=6, pady=4)
        item.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(item, text="📦", font=ctk.CTkFont(size=20),
                     text_color=C["purple"]).grid(row=0, column=0, rowspan=2,
                                                   padx=(14, 14), pady=10)

        ctk.CTkLabel(item, text=path.name, font=f["h2"], text_color=C["text"],
                     anchor="w").grid(row=0, column=1, sticky="w")

        time_str = "-"
        try:
            ts = path.name.replace("backup_", "")
            dt = datetime.datetime.strptime(ts, "%Y%m%d_%H%M%S")
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

        info = ctk.CTkLabel(item, text=f"{time_str}   ·   计算中…",
                            font=f["small"], text_color=C["text_dim"], anchor="w")
        info.grid(row=1, column=1, sticky="w", pady=(0, 2))

        ctk.CTkButton(
            item, text="🗑", width=40, height=34, corner_radius=8,
            font=ctk.CTkFont(size=14), fg_color="transparent",
            hover_color="#3b1f24", text_color=C["text_dim"],
            command=lambda p=path: self._delete(p),
        ).grid(row=0, column=2, rowspan=2, padx=(12, 14))

        threading.Thread(target=self._size_worker, args=(path, info, time_str),
                         daemon=True).start()

    def _size_worker(self, path, label, time_str):
        total = 0
        try:
            for p in path.rglob("*"):
                if p.is_file():
                    try:
                        total += p.stat().st_size
                    except OSError:
                        pass
        except OSError:
            pass
        self.app.ui(label.configure, text=f"{time_str}   ·   {format_size(total)}")

    def _delete(self, path: Path):
        if not messagebox.askyesno("删除备份",
                                    f"确定要永久删除吗？\n\n{path.name}"):
            return
        try:
            shutil.rmtree(path)
            self.app.log_to_console(f"已删除备份：{path.name}", "ok")
            self.refresh()
        except Exception as e:
            self.app.log_to_console(f"删除失败：{e}", "error")