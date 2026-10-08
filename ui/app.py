"""主窗口 + 服务器进程生命周期 + 权限审计 + AI 接入。"""
import json as _json
import os
import re
import sys
import threading
import time
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from core.theme import C, make_fonts, load_theme_from_config
from core.rcon import SimpleRCON
from core.config import load_config, save_config
from core.backup import perform_backup, rotate_backups
from core.server_info import ServerInfo
from core.permissions import load_permissions, PermissionManager
from core.log_watcher import LogWatcher
from core import process_manager as pm
from core.ai_client import AIClient
from core.server_context import ServerContextProvider
from core.ai_history import AIHistory

from ui.pages.dashboard import DashboardPage
from ui.pages.console_page import ConsolePage
from ui.pages.players import PlayersPage
from ui.pages.permissions import PermissionsPage
from ui.pages.roster import RosterPage
from ui.pages.backup_page import BackupPage
from ui.pages.properties import PropertiesPage
from ui.pages.settings import SettingsPage
from ui.pages.zones import ZonesPage
from ui.pages.ai_page import AIPage

from core.zones import (
    load_zones, save_zones, build_clean_command,
    DIMENSION_KEYS, DIMENSION_CN,
)
from core.clean_zones import (
    load_clean_zones, save_clean_zones, build_clean_zone_command,
)


NAV_ITEMS = [
    ("📊", "仪表盘"),
    ("💻", "控制台"),
    ("👥", "玩家管理"),
    ("⚖", "权限管理"),
    ("🗺", "区域管理"),
    ("📋", "名单管理"),
    ("💾", "备份管理"),
    ("🧩", "服务器属性"),
    ("🤖", "AI 助手"),
    ("⚙", "设置"),
]

PERM_PAGE_INDEX = 3
ZONES_PAGE_INDEX = 4
AI_PAGE_INDEX = 8


class MinecraftManagerGUI(ctk.CTk):

    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("CubeDeck - Best Minecraft Server Manager")
        self.geometry("1180x760")
        self.minsize(980, 660)

        # 主题必须在创建任何 widget 之前加载
        self.config_data = load_config()
        load_theme_from_config(self.config_data)

        self.configure(fg_color=C["bg"])

        self.fonts = make_fonts()

        # ---------- 状态 ----------
        self.server_path = Path(self.config_data["server_path"])
        self.is_running = False
        self.rcon_client = None
        self.start_time = None
        self.current_index = 0
        self._user_stopping = False
        self._exit_lock = threading.Lock()
        self._backup_running = False
        self._last_auto_backup = time.time()
        self._last_drop_clean = time.time()
        self._last_reconnect = 0.0
        self._tps_warned = False

        # ---------- 进程管理 ----------
        self._server_pid = None
        self._server_create_time = None
        self._is_external = False

        # ---------- 保护区 / 清理区 ----------
        self.zones_data = load_zones()
        self.clean_zones_data = load_clean_zones()

        # ---------- 服务端探测 ----------
        self.server_info = ServerInfo()

        # ---------- 权限审计 ----------
        self.perm_data = load_permissions()
        self.perm_manager = PermissionManager(
            self.perm_data,
            server_version=self.server_info.version,
            log=self.log_to_console,
            action=self._perm_action,
        )
        self._log_watcher = None

        # ---------- AI 助手 ----------
        self._last_ai_call_time = 0.0
        self._last_ai_call_per_player = {}
        self.ai_history = AIHistory()
        self.server_context = ServerContextProvider(self)

        # ---------- 布局 ----------
        self.grid_columnconfigure(0, weight=0, minsize=240)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()
        self._switch_tab(0)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        threading.Thread(target=self._status_loop, daemon=True).start()
        threading.Thread(target=self._scheduler_loop, daemon=True).start()
        threading.Thread(target=self._detect_running_server,
                         daemon=True).start()

        self.log_to_console("CubeDeck 已就绪", "ok")
        self.log_to_console(f"服务器目录：{self.server_path}", "info")

    # ========================================================
    #  侧边栏
    # ========================================================
    def _build_sidebar(self):
        from core.theme import SPACING, RADIUS
        bar = ctk.CTkFrame(self, width=240, corner_radius=0,
                           fg_color=C["sidebar"])
        bar.grid(row=0, column=0, sticky="nsew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_rowconfigure(len(NAV_ITEMS) + 2, weight=1)

        # ---- Logo 区 ----
        logo = ctk.CTkFrame(bar, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="ew",
                  padx=SPACING["lg"], pady=(24, 28))

        ctk.CTkLabel(logo, text="⛏", width=42, height=42,
                     font=ctk.CTkFont(size=22),
                     fg_color=C["accent"], corner_radius=RADIUS["button"],
                     text_color=C["accent_text"]).pack(side="left")

        tb = ctk.CTkFrame(logo, fg_color="transparent")
        tb.pack(side="left", padx=(12, 0))
        ctk.CTkLabel(tb, text="CubeDeck", font=self.fonts["h1"],
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tb, text="Minecraft 服务器控制台",
                     font=self.fonts["small"],
                     text_color=C["text_faint"]).pack(anchor="w")

        # ---- 导航按钮 ----
        self.nav_buttons = []
        self.nav_indicators = []
        for i, (icon, label) in enumerate(NAV_ITEMS):
            row = ctk.CTkFrame(bar, fg_color="transparent", height=40)
            row.grid(row=1 + i, column=0, sticky="ew",
                     padx=SPACING["md"], pady=2)
            row.grid_columnconfigure(1, weight=1)
            row.grid_propagate(False)

            indicator = ctk.CTkFrame(row, width=3, height=20,
                                     fg_color="transparent",
                                     corner_radius=2)
            indicator.grid(row=0, column=0, padx=(4, 8), pady=10)
            self.nav_indicators.append(indicator)

            btn = ctk.CTkButton(
                row, text=f"{icon}   {label}", anchor="w",
                height=40, corner_radius=RADIUS["button"],
                fg_color="transparent", hover_color=C["card_hover"],
                text_color=C["text_dim"], font=self.fonts["body"],
                command=lambda idx=i: self._switch_tab(idx),
            )
            btn.grid(row=0, column=1, sticky="ew", padx=(0, 4))
            self.nav_buttons.append(btn)

        # ---- 底部 RCON 状态 ----
        footer = ctk.CTkFrame(bar, fg_color="transparent")
        footer.grid(row=len(NAV_ITEMS) + 3, column=0, sticky="ew",
                    padx=SPACING["lg"], pady=SPACING["xl"])

        self.rcon_dot = ctk.CTkLabel(footer, text="⚪",
                                     font=ctk.CTkFont(size=12),
                                     text_color=C["text_faint"])
        self.rcon_dot.pack(side="left")
        self.rcon_label = ctk.CTkLabel(footer, text="RCON 未连接",
                                       font=self.fonts["small"],
                                       text_color=C["text_faint"])
        self.rcon_label.pack(side="left", padx=(6, 0))

    # ========================================================
    #  主区域
    # ========================================================
    def _build_main(self):
        from core.theme import SPACING, RADIUS
        main = ctk.CTkFrame(self, corner_radius=0, fg_color=C["bg"])
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent", height=56)
        header.grid(row=0, column=0, sticky="ew",
                    padx=SPACING["xl"], pady=(SPACING["xl"], 0))
        header.grid_columnconfigure(0, weight=1)

        self.page_title = ctk.CTkLabel(header, text="仪表盘",
                                       font=self.fonts["title"],
                                       text_color=C["text"], anchor="w")
        self.page_title.grid(row=0, column=0, sticky="w")

        self.header_status = ctk.CTkLabel(
            header, text="⚪  离线", font=self.fonts["body"],
            text_color=C["text_dim"], fg_color=C["card"],
            corner_radius=RADIUS["card"], padx=14, pady=6,
        )
        self.header_status.grid(row=0, column=1, sticky="e")

        self.content = ctk.CTkFrame(main, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew",
                          padx=SPACING["xl"],
                          pady=(SPACING["lg"], SPACING["xl"]))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.pages = [
            DashboardPage(self.content, self),
            ConsolePage(self.content, self),
            PlayersPage(self.content, self),
            PermissionsPage(self.content, self),
            ZonesPage(self.content, self),
            RosterPage(self.content, self),
            BackupPage(self.content, self),
            PropertiesPage(self.content, self),
            AIPage(self.content, self),
            SettingsPage(self.content, self),
        ]
        self.page_frames = [p.frame for p in self.pages]

    def _switch_tab(self, index):
        if (index == self.current_index
                and self.page_frames[index].winfo_ismapped()):
            return

        for i, btn in enumerate(self.nav_buttons):
            if i == index:
                btn.configure(fg_color=C["card"], text_color=C["text"])
                try:
                    self.nav_indicators[i].configure(fg_color=C["accent"])
                except Exception:
                    pass
            else:
                btn.configure(fg_color="transparent",
                              text_color=C["text_dim"])
                try:
                    self.nav_indicators[i].configure(fg_color="transparent")
                except Exception:
                    pass

        self.page_frames[self.current_index].grid_forget()
        self.page_frames[index].grid(row=0, column=0, sticky="nsew")
        self.current_index = index
        self.page_title.configure(text=NAV_ITEMS[index][1])

        page = self.pages[index]
        if hasattr(page, "on_show"):
            try:
                page.on_show()
            except Exception:
                pass

    # ========================================================
    #  线程安全 UI 调度 & 日志
    # ========================================================
    def ui(self, func, *args, **kwargs):
        def wrap():
            try:
                func(*args, **kwargs)
            except Exception:
                pass
        try:
            self.after(0, wrap)
        except Exception:
            pass

    def log_to_console(self, message, tag="info"):
        try:
            console_page = self.pages[1]
            console_page.append(str(message), tag)
        except Exception:
            pass

    def _on_server_log_line(self, line):
        msg = re.sub(r"^\[\d{2}:\d{2}:\d{2}\]\s+", "", line)
        low = msg.lower()
        if "error" in low or "exception" in low or "caused by" in low:
            tag = "error"
        elif "warn" in low:
            tag = "warn"
        else:
            tag = "server"
        self.log_to_console(msg, tag)

    # ========================================================
    #  RCON 快捷执行
    # ========================================================
    def quick_rcon(self, cmd, on_done=None):
        self.log_to_console(f"> {cmd}", "cmd")
        if not (self.rcon_client and self.rcon_client.connected):
            self.log_to_console("RCON 未连接，无法执行", "warn")
            return
        threading.Thread(target=self._quick_rcon_worker,
                         args=(cmd, on_done), daemon=True).start()

    def _quick_rcon_worker(self, cmd, on_done):
        try:
            client = self.rcon_client
            if not client:
                return
            resp = client.command(cmd)
            if resp:
                for line in resp.splitlines():
                    if line.strip():
                        self.log_to_console(line.strip(), "server")
        except Exception as e:
            self.log_to_console(f"指令失败：{e}", "error")
            self._auto_reconnect_rcon()
        if on_done:
            try:
                self.ui(on_done)
            except Exception:
                pass

    def rcon_call(self, cmd, callback):
        def worker():
            try:
                if self.rcon_client and self.rcon_client.connected:
                    resp = self.rcon_client.command(cmd)
                else:
                    resp = ""
            except Exception as e:
                resp = ""
                self.log_to_console(
                    f"RCON 连接已断开：{e}，尝试重连…", "warn")
                self._auto_reconnect_rcon()
            try:
                self.ui(callback, resp)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _auto_reconnect_rcon(self):
        now = time.time()
        if now - getattr(self, "_last_reconnect", 0) < 10:
            return
        self._last_reconnect = now
        if self.rcon_client:
            try:
                self.rcon_client.disconnect()
            except Exception:
                pass
            self.rcon_client = None
        threading.Thread(target=self._connect_rcon, daemon=True).start()

    def _perm_action(self, cmd, tag="info"):
        if self.rcon_client and self.rcon_client.connected:
            self.quick_rcon(cmd)

    # ========================================================
    #  保护区 / 清理区辅助
    # ========================================================
    def _active_zones(self):
        return [z for z in self.zones_data.get("zones", [])
                if z.get("enabled", True)]

    def _dims_with_zones(self, zones):
        dims = set()
        for z in zones:
            zdim = z.get("dimension", "")
            if zdim == "*":
                return set(DIMENSION_KEYS)
            if zdim in DIMENSION_KEYS:
                dims.add(zdim)
        return dims

    # ========================================================
    #  启动时检测残留服务端
    # ========================================================
    def _detect_running_server(self):
        try:
            running = pm.find_running_server(self.server_path)
        except Exception:
            running = None

        if not running:
            pm.clear_state()
            return

        pid = running["pid"]
        create_time = running.get("create_time") or 0.0
        self.log_to_console(
            f"检测到已在运行的服务端（PID {pid}），正在接管…", "warn")

        self._server_pid = pid
        self._server_create_time = create_time
        self._is_external = True
        self.is_running = True
        self.start_time = time.time()

        pm.save_state({
            "pid": pid,
            "create_time": create_time,
            "start_time": self.start_time,
        })

        self.ui(self._on_started_ui)
        self._start_log_watcher()
        threading.Thread(target=self._connect_rcon, daemon=True).start()
        threading.Thread(target=self._watch_process, daemon=True).start()

    # ========================================================
    #  服务器生命周期
    # ========================================================
    def toggle_server(self):
        if self.is_running:
            self.stop_server()
        else:
            self.start_server()

    def start_server(self):
        if self.is_running:
            return
        self.pages[0].set_toggle_button("disabled", "启动中…",
                                         C["text_faint"])
        threading.Thread(target=self._start_server_worker,
                         daemon=True).start()

    def _start_server_worker(self):
        existing = pm.find_running_server(self.server_path)
        if existing:
            self.log_to_console(
                f"检测到已在运行的服务端（PID {existing['pid']}），正在接管…",
                "warn")
            self._server_pid = existing["pid"]
            self._server_create_time = existing.get("create_time") or 0.0
            self._is_external = True
            self.is_running = True
            self.start_time = time.time()
            pm.save_state({
                "pid": self._server_pid,
                "create_time": self._server_create_time,
                "start_time": self.start_time,
            })
            self.ui(self._on_started_ui)
            self._start_log_watcher()
            threading.Thread(target=self._connect_rcon, daemon=True).start()
            threading.Thread(target=self._watch_process, daemon=True).start()
            return

        java_path = Path(self.config_data["java_path"])
        if not java_path.exists():
            self.log_to_console(f"找不到 Java：{java_path}", "error")
            self.ui(self._reset_toggle_button)
            return
        if not self.server_path.exists():
            self.log_to_console(
                f"服务器目录不存在：{self.server_path}", "error")
            self.ui(self._reset_toggle_button)
            return

        jars = sorted(self.server_path.glob("*.jar"))
        if not jars:
            self.log_to_console("未找到 .jar 文件", "error")
            self.ui(self._reset_toggle_button)
            return

        jar = jars[0]
        xmx = self.config_data.get("memory_xmx", "4G")
        xms = self.config_data.get("memory_xms", "2G")
        extra = self.config_data.get("jvm_args", "").strip()

        cmd = [str(java_path), f"-Xmx{xmx}", f"-Xms{xms}"]
        if extra:
            cmd += extra.split()
        cmd += ["-jar", jar.name, "nogui"]

        self.log_to_console(
            f"脱离启动服务端：{jar.name}  Xmx={xmx} Xms={xms}", "info")

        try:
            proc = pm.launch_detached(cmd, self.server_path)
        except Exception as e:
            self.log_to_console(f"启动失败：{e}", "error")
            self.ui(self._reset_toggle_button)
            return

        time.sleep(0.3)
        ct = pm.get_create_time(proc.pid) or time.time()
        self._server_pid = proc.pid
        self._server_create_time = ct
        self._is_external = False
        self.is_running = True
        self.start_time = time.time()
        self._user_stopping = False

        pm.save_state({
            "pid": proc.pid,
            "create_time": ct,
            "start_time": self.start_time,
        })

        self.ui(self._on_started_ui)
        self._start_log_watcher()
        threading.Thread(target=self._watch_process, daemon=True).start()

        time.sleep(8)
        self._connect_rcon()

    # ========================================================
    #  重启软件
    # ========================================================
    def restart_app(self):
        """重新启动管理器程序。服务端进程不受影响，下次启动自动接管。"""
        import subprocess

        # 停止日志监控
        if self._log_watcher:
            try:
                self._log_watcher.stop()
            except Exception:
                pass
            self._log_watcher = None

        # 断开 RCON（服务端不受影响）
        if self.rcon_client:
            try:
                self.rcon_client.disconnect()
            except Exception:
                pass
            self.rcon_client = None

        # 保留 server_state.json，让新进程能接管正在运行的服务端

        # 构造启动命令
        if getattr(sys, "frozen", False):
            # PyInstaller 打包后
            args = [sys.executable] + sys.argv[1:]
        else:
            # 开发环境（python main.py）
            args = [sys.executable] + sys.argv

        try:
            subprocess.Popen(args, close_fds=True)
        except Exception as e:
            messagebox.showerror("重启失败", f"无法启动新进程：\n{e}")
            return

        # 立即退出当前进程（跳过清理，避免和 Tk 事件循环纠缠）
        os._exit(0)

    def _reset_toggle_button(self):
        self.pages[0].set_toggle_button("normal", "启动服务器", C["green"])

    def _on_started_ui(self):
        self.pages[0].set_running()
        self.header_status.configure(text="●  运行中", text_color=C["green"])
        for page in self.pages:
            if hasattr(page, "on_server_started"):
                page.on_server_started()

    def _on_stopped_ui(self):
        try:
            self.pages[0].set_stopped()
        except Exception as e:
            self.log_to_console(f"[UI] 仪表盘重置失败：{e}", "error")
        try:
            self.header_status.configure(text="●  离线",
                                         text_color=C["text_dim"])
        except Exception:
            pass
        try:
            self.rcon_dot.configure(text="⚪")
            self.rcon_label.configure(text="RCON 未连接",
                                      text_color=C["text_faint"])
        except Exception:
            pass
        for page in self.pages:
            if hasattr(page, "on_server_stopped"):
                try:
                    page.on_server_stopped()
                except Exception:
                    pass

    def stop_server(self):
        if not self.is_running:
            return
        self._user_stopping = True
        self.pages[0].set_stopping()
        self.header_status.configure(text="●  停止中",
                                     text_color=C["orange"])
        self.log_to_console("正在停止服务器…", "warn")
        threading.Thread(target=self._stop_server_worker,
                         daemon=True).start()

    def _stop_server_worker(self):
        if self.rcon_client and self.rcon_client.connected:
            try:
                self.rcon_client.command("stop")
            except Exception:
                pass

        pid = self._server_pid
        ct = self._server_create_time
        if pid:
            ok = pm.wait_for_exit(pid, ct, timeout=25, interval=0.5)
            if not ok:
                self.log_to_console("优雅停止超时，强制终止…", "warn")
                pm.kill_process(pid, ct, timeout=5)

        self._on_server_exited()

    def _watch_process(self):
        while self.is_running:
            if not pm.is_process_alive(self._server_pid,
                                        self._server_create_time):
                self._on_server_exited()
                return
            time.sleep(2)

    def _on_server_exited(self):
        with self._exit_lock:
            if (not self.is_running
                    and self._server_pid is None
                    and self.start_time is None):
                return
            was_running = self.is_running
            user_stopped = self._user_stopping

            self.is_running = False
            self.start_time = None
            self._server_pid = None
            self._server_create_time = None
            self._is_external = False
            self._user_stopping = False

            if self.rcon_client:
                try:
                    self.rcon_client.disconnect()
                except Exception:
                    pass
                self.rcon_client = None

        pm.clear_state()

        if self._log_watcher:
            try:
                self._log_watcher.stop()
            except Exception:
                pass
            self._log_watcher = None
        if self.server_context:
            self.server_context.invalidate()

        self.log_to_console("服务器已停止", "ok")
        self.ui(self._on_stopped_ui)

        if (not user_stopped and was_running
                and self.config_data.get("auto_restart", False)):
            self.log_to_console("异常退出，5 秒后自动重启…", "warn")

            def _restart():
                time.sleep(5)
                if not self.is_running:
                    self.start_server()
            threading.Thread(target=_restart, daemon=True).start()

    # ========================================================
    #  RCON
    # ========================================================
    def _connect_rcon(self):
        port = int(self.config_data["rcon_port"])
        pwd = str(self.config_data["rcon_password"]).replace(
            "\ufeff", "").strip()
        self.log_to_console(f"正在连接 RCON（127.0.0.1:{port}）…", "info")

        for attempt in range(1, 11):
            if not self.is_running:
                return
            client = SimpleRCON("127.0.0.1", port, pwd)
            try:
                if client.connect():
                    self.rcon_client = client
                    self.log_to_console("RCON 连接成功", "ok")
                    self.ui(self._on_rcon_connected_ui)
                    return
                client.disconnect()
                self.log_to_console(
                    f"RCON 认证失败（第 {attempt} 次）", "warn")
            except Exception as e:
                client.disconnect()
                self.log_to_console(
                    f"RCON 连接失败（第 {attempt} 次）：{e}", "warn")
            time.sleep(3)

        self.log_to_console("RCON 连接失败，指令不可用", "error")

    def _on_rcon_connected_ui(self):
        try:
            self.server_info.detect_from_log(self.server_path)
        except Exception:
            pass

        def _detect():
            try:
                self.server_info.detect_from_rcon(self.rcon_client)
            except Exception:
                pass
            self.perm_manager.update_server_version(self.server_info.version)
            self.log_to_console(
                f"服务端：{self.server_info.summary()}", "ok")

        threading.Thread(target=_detect, daemon=True).start()

        self.rcon_dot.configure(text="🟢")
        self.rcon_label.configure(text="RCON 已连接", text_color=C["green"])
        for page in self.pages:
            if hasattr(page, "on_rcon_connected"):
                page.on_rcon_connected()
        if self.server_context:
            self.server_context.invalidate()

    def manual_reconnect_rcon(self):
        if not self.is_running:
            self.log_to_console("服务器未运行", "warn")
            return
        if self.rcon_client:
            self.rcon_client.disconnect()
            self.rcon_client = None
        threading.Thread(target=self._connect_rcon, daemon=True).start()

    # ========================================================
    #  保护区数据
    # ========================================================
    def save_zones_data(self):
        save_zones(self.zones_data)

    def add_or_update_zone(self, zone, is_new=True, old_name=None):
        zones = self.zones_data.setdefault("zones", [])
        if is_new:
            if any(z.get("name") == zone["name"] for z in zones):
                messagebox.showwarning(
                    "提示", f"已存在同名保护区：{zone['name']}")
                return
            zones.append(zone)
        else:
            for i, z in enumerate(zones):
                if z.get("name") == old_name:
                    zones[i] = zone
                    break
        if save_zones(self.zones_data):
            self.log_to_console(
                f"保护区已{'创建' if is_new else '更新'}：{zone['name']}",
                "ok")
            try:
                self.pages[ZONES_PAGE_INDEX].refresh()
            except Exception:
                pass

    def remove_zone(self, name):
        zones = self.zones_data.get("zones", [])
        self.zones_data["zones"] = [
            z for z in zones if z.get("name") != name]
        if save_zones(self.zones_data):
            self.log_to_console(f"保护区已删除：{name}", "ok")
            try:
                self.pages[ZONES_PAGE_INDEX].refresh()
            except Exception:
                pass

    # ========================================================
    #  清理区数据
    # ========================================================
    def save_clean_zones_data(self):
        save_clean_zones(self.clean_zones_data)

    def add_or_update_clean_zone(self, zone, is_new=True, old_name=None):
        zones = self.clean_zones_data.setdefault("zones", [])
        if is_new:
            if any(z.get("name") == zone["name"] for z in zones):
                messagebox.showwarning(
                    "提示", f"已存在同名清理区：{zone['name']}")
                return
            zones.append(zone)
        else:
            for i, z in enumerate(zones):
                if z.get("name") == old_name:
                    zones[i] = zone
                    break
        if save_clean_zones(self.clean_zones_data):
            self.log_to_console(
                f"清理区已{'创建' if is_new else '更新'}：{zone['name']}",
                "ok")
            try:
                self.pages[ZONES_PAGE_INDEX].refresh()
            except Exception:
                pass

    def remove_clean_zone(self, name):
        zones = self.clean_zones_data.get("zones", [])
        self.clean_zones_data["zones"] = [
            z for z in zones if z.get("name") != name]
        if save_clean_zones(self.clean_zones_data):
            self.log_to_console(f"清理区已删除：{name}", "ok")
            try:
                self.pages[ZONES_PAGE_INDEX].refresh()
            except Exception:
                pass

    # ========================================================
    #  日志监控
    # ========================================================
    def _start_log_watcher(self):
        if self._log_watcher and self._log_watcher.is_alive():
            return
        log_path = self.server_path / "logs" / "latest.log"
        self._log_watcher = LogWatcher(
            log_path,
            on_command=self._on_player_command,
            on_line=self._on_server_log_line,
            on_chat=self._on_player_chat,
        )
        self._log_watcher.start()

    def _on_player_command(self, player, cmd_name, raw_cmd, source="exact"):
        try:
            ok, reason = self.perm_manager.check(player, cmd_name)
        except Exception:
            return
        if ok:
            return

        try:
            self.perm_manager.on_violation(player, cmd_name, raw_cmd)
        except Exception:
            pass

        tag = "" if source == "exact" else "  ⚠️需核对"
        try:
            page = self.pages[PERM_PAGE_INDEX]
            if hasattr(page, "append_violation"):
                page.append_violation(
                    f"{player} 越权：{raw_cmd}  （{reason}）{tag}")
        except Exception:
            pass

    # ========================================================
    #  AI 助手
    # ========================================================
    def _on_player_chat(self, player, message):
        if not self.config_data.get("ai_enabled"):
            return
        if not self.config_data.get("ai_api_key"):
            return

        chat_on = self.config_data.get("ai_chat_enabled", True)
        mod_on = self.config_data.get("ai_moderation_enabled", False)

        should_reply = False
        clean_message = message

        if chat_on:
            trigger = self.config_data.get("ai_chat_trigger", "").strip()
            if not trigger:
                should_reply = True
            elif message.startswith(trigger):
                should_reply = True
                clean_message = message[len(trigger):].strip()

        should_moderate = mod_on

        if not should_reply and not should_moderate:
            return

        cooldowns = []
        if should_reply:
            cooldowns.append(int(self.config_data.get(
                "ai_chat_cooldown", 5)))
        if should_moderate:
            cooldowns.append(int(self.config_data.get(
                "ai_moderation_cooldown", 3)))

        required_gap = max(cooldowns) if cooldowns else 5

        now = time.time()

        global_gap = float(self.config_data.get("ai_global_cooldown", 1.0))
        if global_gap > 0 and now - self._last_ai_call_time < global_gap:
            return

        last_per = self._last_ai_call_per_player.get(player, 0)
        if now - last_per < required_gap:
            remain = required_gap - (now - last_per)
            self.log_to_console(
                f"⏱ {player} 冷却中（还需 {remain:.1f} 秒），跳过 AI 调用",
                "info")
            return

        self._last_ai_call_time = now
        self._last_ai_call_per_player[player] = now

        threading.Thread(
            target=self._process_chat_with_ai,
            args=(player, message, clean_message,
                  should_reply, should_moderate),
            daemon=True,
        ).start()

    def _process_chat_with_ai(self, player, raw_message, clean_message,
                              should_reply, should_moderate):
        client = AIClient(
            self.config_data.get("ai_base_url", ""),
            self.config_data.get("ai_api_key", ""),
            self.config_data.get("ai_model", ""),
            timeout=30,
        )

        base_prompt = self.config_data.get("ai_system_prompt", "")

        context_blocks = []
        if self.config_data.get("ai_context_enabled", True):
            try:
                self.server_context._cache_ttl = float(
                    self.config_data.get("ai_context_ttl", 30))
            except Exception:
                pass

            summary = self.server_context.get_summary()
            if summary:
                context_blocks.append(summary)

            if should_reply:
                detail = self.server_context.get_player_detail(player)
                if detail:
                    context_blocks.append(detail)

        if context_blocks:
            full_system = (
                    base_prompt
                    + "\n\n你可以参考下方实时数据回答玩家，"
                      "但不要照搬原文，只把相关事实融入回复：\n\n"
                    + "\n\n".join(context_blocks)
            )
        else:
            full_system = base_prompt

        messages = [{"role": "system", "content": full_system}]

        ctx_n = int(self.config_data.get("ai_context_lines", 10))
        for entry in self.ai_history.recent(ctx_n):
            messages.append({
                "role": "user",
                "content": f"<{entry['player']}> {entry['message']}"
            })
            if entry.get("reply"):
                messages.append({
                    "role": "assistant",
                    "content": entry["reply"]
                })

        prompt_note = []
        if should_reply:
            prompt_note.append("回复这位玩家")
        if should_moderate:
            prompt_note.append("审核这条消息是否违规")
        note = "；".join(prompt_note) if prompt_note else ""

        messages.append({
            "role": "user",
            "content": f"<{player}> {clean_message}\n\n[{note}]"
        })

        reply_text, err = client.chat(messages, temperature=0.7,
                                      max_tokens=400)

        if err:
            self.log_to_console(f"AI 请求失败：{err}", "error")
            try:
                self.pages[AI_PAGE_INDEX].append_error(f"{player}: {err}")
            except Exception:
                pass
            return

        reply = ""
        action = "none"
        reason = ""
        try:
            clean = (reply_text or "").strip()
            if clean.startswith("```"):
                parts = clean.split("```")
                if len(parts) >= 2:
                    clean = parts[1]
                    if clean.startswith("json"):
                        clean = clean[4:]
            data = _json.loads(clean)
            reply = str(data.get("reply", "")).strip()
            action = str(data.get("violation", "none")).strip().lower()
            reason = str(data.get("reason", "")).strip()
        except Exception:
            reply = (reply_text or "").strip()
            if not should_reply:
                reply = ""

        if action not in ("none", "warn", "kick", "ban"):
            action = "none"

        if reply and should_reply:
            self._ai_say(reply)

        if action != "none" and should_moderate:
            self._execute_moderation(player, action, reason)

        entry = {
            "time": time.time(),
            "player": player,
            "message": raw_message,
            "reply": reply,
            "action": action,
            "reason": reason,
        }
        self.ai_history.append(entry)

        try:
            self.pages[AI_PAGE_INDEX].append_chat(
                player, raw_message, reply, action, reason)
        except Exception:
            pass

    def _ai_say(self, text):
        safe = text.replace('"', '\\"').replace("\n", " ")
        if len(safe) > 200:
            safe = safe[:200] + "…"
        payload = _json.dumps({
            "text": "",
            "extra": [
                {"text": "[AI] ", "color": "light_purple"},
                {"text": safe, "color": "white"},
            ]
        }, ensure_ascii=False)
        self.quick_rcon(f"tellraw @a {payload}")

    def _execute_moderation(self, player, action, reason):
        reason_str = reason or "违反服务器规则"
        broadcast = self.config_data.get("ai_moderation_broadcast", True)

        if action == "warn":
            safe = reason_str.replace('"', '\\"')
            payload = _json.dumps({
                "text": f"[审核] {player}：{safe}", "color": "yellow"
            }, ensure_ascii=False)
            self.quick_rcon(f"tellraw @a {payload}")
        elif action == "kick":
            safe = reason_str.replace('"', '\\"')
            self.quick_rcon(f'kick {player} {safe}')
            if broadcast:
                payload = _json.dumps({
                    "text": f"[审核] {player} 已被踢出：{safe}",
                    "color": "gold"
                }, ensure_ascii=False)
                self.quick_rcon(f"tellraw @a {payload}")
        elif action == "ban":
            safe = reason_str.replace('"', '\\"')
            self.quick_rcon(f'ban {player} {safe}')
            if broadcast:
                payload = _json.dumps({
                    "text": f"[审核] {player} 已被封禁：{safe}",
                    "color": "red"
                }, ensure_ascii=False)
                self.quick_rcon(f"tellraw @a {payload}")

        self.log_to_console(
            f"🛡 AI 审核：{player} → {action}  ({reason_str})", "warn")

    # ========================================================
    #  状态轮询
    # ========================================================
    def _status_loop(self):
        while True:
            try:
                if self.is_running:
                    self._refresh_stats()
            except Exception:
                pass
            time.sleep(2)

    def _refresh_stats(self):
        pid = self._server_pid
        if pid:
            try:
                import psutil
                p = psutil.Process(pid)
                mem = p.memory_info().rss / 1024 / 1024
                self.ui(self.pages[0].set_mem, f"{mem:,.0f} MB")
            except Exception:
                pass

        if self.start_time:
            elapsed = int(time.time() - self.start_time)
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            self.ui(self.pages[0].set_uptime, f"{h:02d}:{m:02d}:{s:02d}")

        client = self.rcon_client
        if not (client and client.connected):
            return

        try:
            cmd = self.server_info.cmd_tps()
            if cmd:
                resp = client.command(cmd) or ""
                m = re.search(r"(\d+\.\d+)[,)]", resp)
                if m:
                    self.ui(self.pages[0].set_tps, m.group(1))
                else:
                    self.ui(self.pages[0].set_tps, "N/A")
            else:
                self.ui(self.pages[0].set_tps, "N/A")
        except Exception:
            pass

        try:
            resp = client.command("list") or ""
            m = re.search(r"There are (\d+) of a max of (\d+)", resp)
            if m:
                self.ui(self.pages[0].set_players,
                        f"{m.group(1)} / {m.group(2)}")
        except Exception:
            pass

    # ========================================================
    #  调度
    # ========================================================
    def _scheduler_loop(self):
        while True:
            try:
                if (self.config_data.get("auto_backup_enabled")
                        and self.is_running
                        and self.rcon_client
                        and self.rcon_client.connected):
                    interval = int(self.config_data.get(
                        "auto_backup_interval_min", 60)) * 60
                    if time.time() - self._last_auto_backup >= interval:
                        self._last_auto_backup = time.time()
                        self.log_to_console("⏰ 触发自动备份", "info")
                        self.do_backup(wait=True)
                        rotate_backups(
                            self.server_path,
                            int(self.config_data.get(
                                "auto_backup_keep", 10)),
                            self.log_to_console,
                        )

                if (self.config_data.get("global_clean_enabled")
                        and self.is_running
                        and self.rcon_client
                        and self.rcon_client.connected):
                    interval = int(self.config_data.get(
                        "auto_drop_clean_interval_min", 30)) * 60
                    if time.time() - self._last_drop_clean >= interval:
                        self._last_drop_clean = time.time()
                        self._trigger_drop_clean()

                if (not self.config_data.get("global_clean_enabled")
                        and self.is_running
                        and self.rcon_client
                        and self.rcon_client.connected):
                    self._tick_clean_zones()
            except Exception:
                pass
            time.sleep(30)

    def _tick_clean_zones(self):
        zones = self.clean_zones_data.get("zones", [])
        now = time.time()
        changed = False

        for zone in zones:
            if not zone.get("enabled", True):
                continue

            interval = int(zone.get("interval_min", 15)) * 60
            last = float(zone.get("last_clean", 0.0) or 0.0)
            if now - last < interval:
                continue

            cmd = build_clean_zone_command(zone)
            if not cmd:
                continue

            try:
                self.rcon_client.command(cmd)
                self.log_to_console(
                    f"🧹 清理区「{zone.get('name')}」自动清理", "info")
                zone["last_clean"] = now
                changed = True
            except Exception as e:
                self.log_to_console(
                    f"清理区「{zone.get('name')}」清理失败：{e}", "warn")

        if changed:
            save_clean_zones(self.clean_zones_data)

    def _trigger_drop_clean(self):
        try:
            resp = self.rcon_client.command("list") or ""
            m = re.search(r"There are (\d+) of a max", resp)
            if m and int(m.group(1)) == 0:
                self.log_to_console(
                    "⏰ 定时清理触发，当前无玩家在线，跳过", "info")
                return
        except Exception:
            pass

        zones = self.zones_data.get("zones", [])
        active = self._active_zones()

        if not active:
            self.log_to_console(
                "⏰ 定时清理触发，但无启用保护区，跳过（避免误清）", "info")
            return

        target_dims = self._dims_with_zones(zones)

        self.log_to_console(
            f"⏰ 触发定时清理（{len(active)} 个保护区，"
            f"覆盖 {len(target_dims)} 个维度）", "info")

        def _run():
            try:
                self.rcon_client.command(
                    "say §e[系统] §f5 秒后清理地面掉落物，请及时捡取。")
            except Exception:
                pass
            time.sleep(5)

            sent = 0
            for dim in DIMENSION_KEYS:
                if dim not in target_dims:
                    continue
                cmd = build_clean_command(zones, dim)
                if not cmd:
                    continue
                sent += 1
                self.log_to_console(f"> {cmd}", "cmd")
                try:
                    self.rcon_client.command(cmd)
                except Exception as e:
                    self.log_to_console(
                        f"清理 {DIMENSION_CN.get(dim, dim)} 失败：{e}",
                        "warn")

            if sent:
                self.log_to_console(
                    f"已按保护区过滤清理（{sent} 个维度）", "ok")
            else:
                self.log_to_console(
                    "没有维度被保护区覆盖，未清理", "warn")

        threading.Thread(target=_run, daemon=True).start()

    def clear_drops(self):
        zones = self.zones_data.get("zones", [])
        active = self._active_zones()

        if not active:
            self.log_to_console(
                "没有启用保护区，请先到「区域管理」创建保护区后再清理",
                "warn")
            return

        target_dims = self._dims_with_zones(zones)

        sent = 0
        for dim in DIMENSION_KEYS:
            if dim not in target_dims:
                continue
            cmd = build_clean_command(zones, dim)
            if not cmd:
                continue
            sent += 1
            self.quick_rcon(cmd)

        if sent == 0:
            self.log_to_console("保护区未覆盖任何维度，未执行清理", "warn")
        else:
            self.log_to_console(
                f"已按保护区过滤清理（{len(active)} 个保护区，"
                f"{sent} 个维度）", "ok")

    # ========================================================
    #  备份
    # ========================================================
    def do_backup(self, wait=False):
        if self._backup_running:
            self.log_to_console("已有备份正在进行", "warn")
            return
        if wait:
            self._backup_worker()
        else:
            threading.Thread(target=self._backup_worker,
                             daemon=True).start()

    def _backup_worker(self):
        if self._backup_running:
            return
        self._backup_running = True
        try:
            perform_backup(self.server_path, self.rcon_client,
                           self.log_to_console)
            self.ui(self.pages[6].refresh)
        finally:
            self._backup_running = False

    # ========================================================
    #  退出
    # ========================================================
    def _on_close(self):
        if self.is_running:
            keep = self.config_data.get("keep_server_on_exit", True)

            if keep:
                if not messagebox.askyesno(
                        "退出确认",
                        "服务器仍在后台运行。\n\n"
                        "• 是：保留服务器并退出（下次可自动接管）\n"
                        "• 否：停止服务器并退出"):
                    self._stop_server_worker()
                    if self._log_watcher:
                        try:
                            self._log_watcher.stop()
                        except Exception:
                            pass
                    self.destroy()
                    return
                if self._log_watcher:
                    try:
                        self._log_watcher.stop()
                    except Exception:
                        pass
                if self.rcon_client:
                    try:
                        self.rcon_client.disconnect()
                    except Exception:
                        pass
                self.destroy()
                return
            else:
                if messagebox.askyesno(
                        "退出确认",
                        "服务器正在运行，确定要退出并停止服务器吗？"):
                    self._stop_server_worker()
                    if self._log_watcher:
                        try:
                            self._log_watcher.stop()
                        except Exception:
                            pass
                    self.destroy()
                return

        if self._log_watcher:
            try:
                self._log_watcher.stop()
            except Exception:
                pass
        self.destroy()


def run():
    app = MinecraftManagerGUI()
    app.mainloop()