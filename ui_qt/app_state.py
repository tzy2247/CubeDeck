"""全局应用状态：封装 core 模块 + Qt 信号槽。"""
import json as _json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread

from core.config import load_config, save_config
from core.rcon import SimpleRCON
from core.server_info import ServerInfo
from core.permissions import (
    load_permissions, PermissionManager, set_data_dir as set_perm_dir,
)
from core.log_watcher import LogWatcher
from core import process_manager as pm
from core.process_manager import set_state_dir as set_pm_dir
from core import server_registry as registry
from core import paths
from core.ai_client import AIClient
from core.server_context import ServerContextProvider
from core.ai_history import AIHistory, set_data_dir as set_hist_dir
from core.backup import perform_backup, rotate_backups
from core.zones import (
    load_zones, save_zones, build_clean_command,
    DIMENSION_KEYS, DIMENSION_CN,
    set_data_dir as set_zones_dir,
)
from core.clean_zones import (
    load_clean_zones, save_clean_zones, build_clean_zone_command,
    set_data_dir as set_clean_dir,
)


# ============================================================
#  异步 RCON 执行器
# ============================================================
class RconWorker(QThread):
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, rcon_client, cmd):
        super().__init__()
        self.rcon_client = rcon_client
        self.cmd = cmd

    def run(self):
        try:
            client = self.rcon_client
            if not (client and client.connected):
                self.error.emit("RCON 未连接")
                return
            resp = client.command(self.cmd)
            self.finished.emit(resp or "")
        except Exception as e:
            self.error.emit(str(e))


# ============================================================
#  AppState
# ============================================================
class AppState(QObject):
    # ---- 信号 ----
    log_message = Signal(str, str)
    server_starting = Signal()
    server_started = Signal()
    server_stopping = Signal()
    server_stopped = Signal()
    rcon_connected = Signal()
    rcon_disconnected = Signal()
    theme_changed = Signal(str)
    stats_updated = Signal(dict)
    server_switched = Signal(str)
    backup_finished = Signal()
    eula_required = Signal()
    port_conflict = Signal(int, str)

    def __init__(self):
        super().__init__()

        paths.ensure_userdata_root()

        self.registry = registry.load_registry()
        self.current_server = registry.get_active()

        # ====================================================
        #  公共状态（无论有无服务器都需要）
        # ====================================================
        self.is_running = False
        self.rcon_client = None
        self.start_time = None
        self._server_pid = None
        self._server_create_time = None
        self._is_external = False
        self._user_stopping = False
        self._backup_running = False
        self._last_auto_backup = time.time()
        self._last_drop_clean = time.time()
        self._last_reconnect = 0.0
        self._log_watcher = None
        self._workers = []
        self._scheduler_stop = threading.Event()
        self._session_token = 0
        self._switching = False
        self._port_conflict_handling = False
        self._stdout_file = None
        self.process = None
        self._last_ai_call_time = 0.0
        self._last_ai_call_per_player = {}
        self.server_info = ServerInfo()

        # ====================================================
        #  无服务器：进入空状态
        # ====================================================
        if self.current_server is None:
            from core.config import DEFAULT_CONFIG
            self.server_id = ""
            self.config_data = dict(DEFAULT_CONFIG)
            self.server_path = Path(".")
            self.data_dir = paths.USERDATA_ROOT
            self.perm_data = {}
            self.perm_manager = PermissionManager(
                self.perm_data,
                server_version=self.server_info.version,
                log=self.log,
                action=lambda *a, **kw: None,
            )
            self.zones_data = {"zones": []}
            self.clean_zones_data = {"zones": []}
            self.ai_history = AIHistory()
            self.server_context = ServerContextProvider(self)
            return

        # ====================================================
        #  有服务器：完整初始化
        # ====================================================
        self.server_id = self.current_server["id"]
        self.config_data = dict(self.current_server["config"])
        self.server_path = Path(self.config_data.get("server_path", "."))

        self.data_dir = registry.get_data_dir(self.server_id)
        set_perm_dir(self.data_dir)
        set_zones_dir(self.data_dir)
        set_clean_dir(self.data_dir)
        set_hist_dir(self.data_dir)
        set_pm_dir(self.data_dir)

        self.perm_data = load_permissions()
        self.perm_manager = PermissionManager(
            self.perm_data,
            server_version=self.server_info.version,
            log=self.log,
            action=self._perm_action,
        )
        self.zones_data = load_zones()
        self.clean_zones_data = load_clean_zones()
        self.ai_history = AIHistory()
        self.server_context = ServerContextProvider(self)

        threading.Thread(target=self._status_loop, daemon=True).start()
        threading.Thread(target=self._scheduler_loop, daemon=True).start()
        threading.Thread(target=self._detect_running_server,
                         daemon=True).start()

    # ========================================================
    #  日志
    # ========================================================
    def log(self, message, tag="info"):
        self.log_message.emit(str(message), tag)

    # ========================================================
    #  服务器状态
    # ========================================================
    def has_server(self) -> bool:
        return bool(self.server_id)

    def activate_server(self, name: str, server_path) -> bool:
        """从空状态创建并激活一个服务器。"""
        if self.has_server():
            return False

        from core.config import DEFAULT_CONFIG
        cfg = dict(DEFAULT_CONFIG)
        cfg["server_path"] = str(server_path)

        sid = registry.add_server(name, cfg)
        registry.set_active(sid)

        server = registry.get_server(sid)
        if server is None:
            return False

        self.server_id = sid
        self.current_server = server
        self.config_data = dict(server["config"])
        self.server_path = Path(self.config_data.get("server_path", "."))

        self.data_dir = registry.get_data_dir(sid)
        set_perm_dir(self.data_dir)
        set_zones_dir(self.data_dir)
        set_clean_dir(self.data_dir)
        set_hist_dir(self.data_dir)
        set_pm_dir(self.data_dir)

        self.perm_data = load_permissions()
        self.perm_manager = PermissionManager(
            self.perm_data,
            server_version=self.server_info.version,
            log=self.log,
            action=self._perm_action,
        )
        self.zones_data = load_zones()
        self.clean_zones_data = load_clean_zones()
        self.ai_history = AIHistory()
        self.server_context = ServerContextProvider(self)

        threading.Thread(target=self._status_loop, daemon=True).start()
        threading.Thread(target=self._scheduler_loop, daemon=True).start()
        threading.Thread(target=self._detect_running_server,
                         daemon=True).start()

        self.log(f"已激活服务器：{name}", "ok")
        self.server_switched.emit(sid)
        return True

    # ========================================================
    #  RCON 快捷执行
    # ========================================================
    def quick_rcon(self, cmd, on_done=None, silent=False):
        if not (self.rcon_client and self.rcon_client.connected):
            self.log("RCON 未连接，无法执行", "warn")
            return
        if not silent:
            self.log(f"> {cmd}", "cmd")

        worker = RconWorker(self.rcon_client, cmd)
        self._workers.append(worker)

        def _on_finished(resp):
            if resp and not silent:
                for line in resp.splitlines():
                    line = line.strip()
                    if line:
                        self.log(line, "rcon")
            if on_done:
                try:
                    on_done(resp)
                except Exception:
                    pass

        def _on_error(err):
            self.log(f"指令失败：{err}", "error")

        worker.finished.connect(_on_finished)
        worker.error.connect(_on_error)
        worker.finished.connect(lambda: self._drop_worker(worker))
        worker.error.connect(lambda: self._drop_worker(worker))
        worker.start()

    def _drop_worker(self, w):
        try:
            self._workers.remove(w)
        except ValueError:
            pass

    def _perm_action(self, cmd, tag="info"):
        if self.rcon_client and self.rcon_client.connected:
            self.quick_rcon(cmd)

    # ========================================================
    #  服务器启动
    # ========================================================
    def start_server(self):
        if not self.has_server():
            self.log("尚未选择服务器", "warn")
            return
        if self.is_running:
            return
        self.server_starting.emit()
        threading.Thread(target=self._start_server_worker,
                         daemon=True).start()

    def _start_server_worker(self):
        try:
            self._do_start_server()
        except Exception as e:
            import traceback
            self.log(f"启动服务器出错：{e}", "error")
            try:
                tb = traceback.format_exc()
                for line in tb.splitlines()[-8:]:
                    self.log(f"  {line}", "error")
            except Exception:
                pass
            self.server_stopped.emit()

    def _do_start_server(self):
        """实际启动逻辑（支持 jar / run.bat / run.sh 三种方式）。"""
        # ---- 1. 已有实例？接管 ----
        existing = (pm.find_running_server(self.server_path)
                    or pm.find_running_java_by_cwd(self.server_path))
        if existing:
            self.log(
                f"检测到已在运行的服务端（PID {existing['pid']}），正在接管…",
                "info")
            self._take_over(existing)
            return

        # ---- 1.5. EULA 检查 ----
        eula_path = self.server_path / "eula.txt"
        eula_ok = False
        if eula_path.exists():
            try:
                txt = eula_path.read_text(
                    encoding="utf-8", errors="ignore")
                normalized = txt.replace(" ", "").lower()
                if "eula=true" in normalized:
                    eula_ok = True
            except Exception:
                pass

        if not eula_ok:
            self.log("⚠ 需要先同意 Minecraft EULA 才能启动服务器", "warn")
            try:
                eula_path.write_text(
                    "# By changing the setting below to TRUE you are "
                    "indicating your agreement to our EULA\n"
                    "# (https://aka.ms/MinecraftEULA).\n"
                    "eula=false\n",
                    encoding="utf-8")
            except Exception:
                pass
            self.eula_required.emit()
            self.server_stopped.emit()
            return

        # ---- 2. 校验 Java ----
        java_path = Path(self.config_data.get("java_path", ""))
        if not java_path.exists():
            self.log(f"找不到 Java：{java_path}", "error")
            self.server_stopped.emit()
            return

        if not self.server_path.exists():
            self.log(f"服务器目录不存在：{self.server_path}", "error")
            self.server_stopped.emit()
            return

        # ---- 2.5. 端口占用检查 ----
        mc_port = 25565
        props = self.server_path / "server.properties"
        if props.exists():
            try:
                for line in props.read_text(
                        encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line.startswith("server-port="):
                        try:
                            mc_port = int(line.split("=", 1)[1].strip())
                        except ValueError:
                            pass
                        break
            except Exception:
                pass

        port_ok, who = self._check_port_usage(mc_port)
        if not port_ok:
            self.log(f"⚠ 端口 {mc_port} 已被占用：{who}", "warn")
            if not self._port_conflict_handling:
                self._port_conflict_handling = True
                self.port_conflict.emit(mc_port, who)
            return

        # ---- 3. 检测启动方式 ----
        startup = pm.detect_startup_method(self.server_path)
        if startup is None:
            self.log(
                "找不到启动文件。\n"
                "  支持的启动方式：\n"
                "    · run.bat / run.sh（Forge 1.17+ / NeoForge）\n"
                "    · *.jar（Paper / Purpur / Fabric / 原版）",
                "error")
            self.server_stopped.emit()
            return

        method_type, target = startup

        xmx = self.config_data.get("memory_xmx", "4G")
        xms = self.config_data.get("memory_xms", "2G")
        extra = self.config_data.get("jvm_args", "").strip()

        # ---- 4. 组装命令 ----
        env = os.environ.copy()
        java_dir = str(java_path.parent)
        env["PATH"] = java_dir + os.pathsep + env.get("PATH", "")

        if method_type == "bat":
            self.log(f"使用启动脚本：{target.name}", "info")
            cmd = ["cmd", "/c", str(target), "nogui"]
            uses_script = True
        elif method_type == "sh":
            self.log(f"使用启动脚本：{target.name}", "info")
            cmd = ["bash", str(target), "nogui"]
            uses_script = True
        else:
            self.log(f"使用 JAR 启动：{target.name}", "info")
            cmd = [str(java_path), f"-Xmx{xmx}", f"-Xms{xms}"]
            if extra:
                cmd += extra.split()
            cmd += ["-jar", str(target), "nogui"]
            uses_script = False

        # ---- 5. 启动进程（stdout 重定向到文件，避免 PIPE 死锁）----
        try:
            if sys.platform == "win32":
                flags = (
                        subprocess.CREATE_NEW_PROCESS_GROUP
                        | 0x08000000  # CREATE_NO_WINDOW
                )
            else:
                flags = 0

            log_dir = self.server_path / "logs"
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            stdout_log_path = log_dir / "stdout.log"

            try:
                self._stdout_file = open(
                    stdout_log_path, "ab", buffering=0)
            except Exception:
                self._stdout_file = subprocess.DEVNULL

            self.process = subprocess.Popen(
                cmd,
                cwd=str(self.server_path),
                env=env,
                stdin=subprocess.PIPE,
                stdout=self._stdout_file,
                stderr=subprocess.STDOUT,
                bufsize=0,
                creationflags=flags,
            )
        except Exception as e:
            self.log(f"启动失败：{e}", "error")
            self.server_stopped.emit()
            return

        # ---- 6. 记录状态 ----
        time.sleep(0.3)
        ct = pm.get_create_time(self.process.pid) or time.time()
        self._server_pid = self.process.pid
        self._server_create_time = ct
        self.is_running = True
        self.start_time = time.time()
        self._user_stopping = False

        pm.save_state({
            "pid": self.process.pid,
            "create_time": ct,
            "start_time": self.start_time,
        })

        self.server_started.emit()

        # ---- 7. 脚本启动时，后台扫描真正的 java 进程 ----
        if uses_script:
            token = self._session_token

            def _find_java_async():
                for _ in range(15):
                    time.sleep(1)
                    if (not self.is_running
                            or token != self._session_token):
                        return
                    running = pm.find_running_java_by_cwd(
                        self.server_path)
                    if running:
                        self._server_pid = running["pid"]
                        self._server_create_time = (
                                running.get("create_time") or 0.0)
                        pm.save_state({
                            "pid": self._server_pid,
                            "create_time": self._server_create_time,
                            "start_time": self.start_time,
                        })
                        self.log(
                            f"已捕获服务端 Java 进程 "
                            f"PID={self._server_pid}", "info")
                        return
                self.log("未捕获到 Java 子进程（可能仍在启动中）", "warn")

            threading.Thread(target=_find_java_async, daemon=True).start()

        # ---- 8. 日志、进程监控、RCON ----
        try:
            self._start_log_watcher()
        except Exception as e:
            self.log(f"日志监控启动失败：{e}", "warn")

        token = self._session_token
        try:
            threading.Thread(target=self._watch_process,
                             args=(token,), daemon=True).start()
        except Exception:
            pass

        try:
            threading.Thread(target=self._connect_rcon_delayed,
                             daemon=True).start()
        except Exception:
            pass

    def _connect_rcon_delayed(self):
        try:
            self._wait_rcon_ready(timeout=90)
        except Exception:
            pass
        try:
            self._connect_rcon()
        except Exception as e:
            self.log(f"RCON 连接线程出错：{e}", "warn")

    def _take_over(self, existing, token=None):
        """接管已有服务端进程。"""
        if token is None:
            token = self._session_token
        if token != self._session_token:
            return

        self._server_pid = existing["pid"]
        self._server_create_time = existing.get("create_time") or 0.0
        self._is_external = True
        self.is_running = True
        if not self.start_time:
            self.start_time = time.time()

        try:
            pm.save_state({
                "pid": self._server_pid,
                "create_time": self._server_create_time,
                "start_time": self.start_time,
            })
        except Exception:
            pass

        self.server_started.emit()

        try:
            self._start_log_watcher()
        except Exception as e:
            self.log(f"日志监控启动失败：{e}", "warn")

        try:
            threading.Thread(target=self._connect_rcon,
                             daemon=True).start()
        except Exception:
            pass

        try:
            threading.Thread(target=self._watch_process,
                             args=(token,), daemon=True).start()
        except Exception:
            pass

    def _detect_running_server(self, token=None):
        """优先读状态文件，兜底进程扫描。"""
        if not self.has_server():
            return
        if token is None:
            token = self._session_token
        if token != self._session_token:
            return

        state = pm.load_state()
        pid = state.get("pid")
        create_time = state.get("create_time")
        saved_start = state.get("start_time")

        if pid and pm.is_process_alive(pid, create_time):
            running = (pm.find_running_java_by_cwd(self.server_path)
                       or pm.find_running_server(self.server_path))
            if running and running["pid"] == pid:
                self.log(
                    f"检测到服务器已在运行"
                    f"（PID {pid}，来自状态文件），正在接管…", "info")
                if saved_start:
                    self.start_time = saved_start
                self._take_over({
                    "pid": pid,
                    "create_time": create_time,
                }, token=token)
                return

        try:
            pm.clear_state()
        except Exception:
            pass

        running = (pm.find_running_java_by_cwd(self.server_path)
                   or pm.find_running_server(self.server_path))
        if not running:
            return

        self.log(
            f"检测到服务器已在运行"
            f"（PID {running['pid']}，来自进程扫描），正在接管…", "info")
        self._take_over(running, token=token)

    # ========================================================
    #  服务器停止
    # ========================================================
    def stop_server(self):
        if not self.has_server():
            return
        if not self.is_running:
            return
        self._user_stopping = True
        self.server_stopping.emit()
        self.log("正在停止服务器…", "warn")
        threading.Thread(target=self._stop_server_worker,
                         daemon=True).start()

    def _stop_server_worker(self):
        try:
            self._do_stop_server()
        except Exception as e:
            self.log(f"停止服务器出错：{e}", "error")
            self._on_server_exited()

    def _do_stop_server(self):
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
                self.log("优雅停止超时，强制终止…", "warn")
                pm.kill_process(pid, ct, timeout=5)

        self._on_server_exited()

    def _watch_process(self, token=None):
        """监控服务端存活。首次检查提前到 3 秒。"""
        if token is None:
            token = self._session_token

        time.sleep(3)

        # 首次检查：如果进程已死，直接读日志给出失败原因
        if not pm.find_running_java_by_cwd(self.server_path):
            if token == self._session_token:
                self._log_start_failure()
                self._on_server_exited(token)
            return

        while self.is_running and token == self._session_token:
            running = pm.find_running_java_by_cwd(self.server_path)
            if running:
                self._server_pid = running["pid"]
                self._server_create_time = (
                        running.get("create_time") or 0.0)
                time.sleep(2)
                continue

            time.sleep(3)
            if token != self._session_token:
                return
            if pm.find_running_java_by_cwd(self.server_path):
                time.sleep(2)
                continue

            if token == self._session_token:
                self._on_server_exited(token)
            return

    def _log_start_failure(self):
        """读取日志末尾，猜测启动失败原因。"""
        log_path = self.server_path / "logs" / "latest.log"
        if not log_path.exists():
            self.log(
                "启动失败：未生成日志文件（服务端可能从未成功运行）",
                "error")
            return
        try:
            text = log_path.read_text(
                encoding="utf-8", errors="replace")
            lines = [ln for ln in text.splitlines() if ln.strip()]
            tail = lines[-20:] if len(lines) > 20 else lines

            self.log("━━━ 服务端启动失败，日志末尾： ━━━", "error")
            for ln in tail:
                self.log(f"  {ln}", "error")

            joined = "\n".join(tail)
            if ("Address already in use" in joined
                    or "FAILED TO BIND TO PORT" in joined):
                self.log(
                    "  ✖ 原因：端口已被占用。可能有僵尸 Java 进程残留。",
                    "error")
            elif "UnsupportedClassVersionError" in joined:
                self.log(
                    "  ✖ 原因：Java 版本过低。MC 1.21+ 需要 Java 21+。",
                    "error")
            elif "Unable to access jarfile" in joined:
                self.log("  ✖ 原因：server.jar 路径错误或文件损坏。",
                         "error")
            elif "Could not reserve enough space" in joined:
                self.log("  ✖ 原因：内存参数过大，超出物理内存。",
                         "error")
        except Exception as e:
            self.log(f"读取日志失败：{e}", "warn")

    def _on_server_exited(self, token=None):
        if token is None:
            token = self._session_token
        if token != self._session_token:
            return

        if (not self.is_running and self._server_pid is None
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

        # 关闭 stdout 文件句柄
        if getattr(self, "_stdout_file", None):
            try:
                self._stdout_file.close()
            except Exception:
                pass
            self._stdout_file = None

        if getattr(self, "process", None):
            try:
                self.process = None
            except Exception:
                pass

        if self.rcon_client:
            try:
                self.rcon_client.disconnect()
            except Exception:
                pass
            self.rcon_client = None

        try:
            pm.clear_state()
        except Exception:
            pass

        if self._log_watcher:
            try:
                self._log_watcher.stop()
            except Exception:
                pass
            self._log_watcher = None

        try:
            self.server_context.invalidate()
        except Exception:
            pass

        self.log("服务器已停止", "ok")
        self.server_stopped.emit()

        if (not user_stopped and was_running
                and self.config_data.get("auto_restart", False)):
            self.log("异常退出，5 秒后自动重启…", "warn")

            def _restart():
                time.sleep(5)
                if not self.is_running and token == self._session_token:
                    self.start_server()
            threading.Thread(target=_restart, daemon=True).start()

    # ========================================================
    #  端口冲突处理
    # ========================================================
    def _check_port_usage(self, port: int):
        """检查端口是否被占用。返回 (ok, 占用描述)。"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.bind(("0.0.0.0", port))
                return True, ""
        except OSError:
            pass

        try:
            import psutil
            for conn in psutil.net_connections(kind="inet"):
                if (conn.laddr
                        and getattr(conn.laddr, "port", None) == port):
                    pid = conn.pid
                    if pid:
                        try:
                            p = psutil.Process(pid)
                            return False, f"{p.name()} (PID {pid})"
                        except Exception:
                            return False, f"PID {pid}"
            return False, "未知进程"
        except Exception as e:
            return False, f"未知（{e}）"

    def _find_free_port(self, start=25565, end=25665):
        """从 start 开始找到一个可用端口，找不到返回 None。"""
        for port in range(start, end):
            try:
                with socket.socket(socket.AF_INET,
                                   socket.SOCK_STREAM) as s:
                    s.settimeout(0.3)
                    s.bind(("0.0.0.0", port))
                    return port
            except OSError:
                continue
        return None

    def _set_server_property(self, key, value):
        """修改 server.properties 中某个字段（不存在则添加）。"""
        props = self.server_path / "server.properties"
        lines = []
        if props.exists():
            try:
                lines = props.read_text(
                    encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                lines = []

        new_lines = []
        found = False
        for line in lines:
            stripped = line.strip()
            if (stripped.startswith(f"{key}=")
                    and not stripped.startswith("#")):
                new_lines.append(f"{key}={value}")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f"{key}={value}")

        try:
            props.write_text(
                "\n".join(new_lines) + "\n", encoding="utf-8")
            return True
        except Exception as e:
            self.log(f"修改 server.properties 失败：{e}", "error")
            return False

    def _kill_port_owner(self, port):
        """终止占用指定端口的所有进程。返回 [(pid, name), ...]。"""
        import psutil
        killed = []
        try:
            conns = psutil.net_connections(kind="inet")
        except Exception as e:
            self.log(f"枚举端口失败：{e}", "warn")
            return killed

        for conn in conns:
            try:
                if (conn.laddr
                        and getattr(conn.laddr, "port", None) == port
                        and conn.pid):
                    p = psutil.Process(conn.pid)
                    name = p.name()
                    p.kill()
                    killed.append((conn.pid, name))
                    self.log(
                        f"已终止占用进程：{name} (PID {conn.pid})", "ok")
            except Exception as e:
                try:
                    self.log(
                        f"无法终止 PID {conn.pid}：{e}", "warn")
                except Exception:
                    pass

        return killed

    def resolve_port_conflict(self, action: str):
        """
        用户在端口冲突对话框里做出选择。
        action: "switch" | "kill" | "cancel"
        """
        self._port_conflict_handling = False

        if action == "cancel":
            self.log("已取消启动（端口冲突未解决）", "warn")
            self.server_stopped.emit()
            return

        # 读取当前端口
        old_port = 25565
        props = self.server_path / "server.properties"
        if props.exists():
            try:
                for line in props.read_text(
                        encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if line.startswith("server-port="):
                        try:
                            old_port = int(line.split("=", 1)[1].strip())
                        except ValueError:
                            pass
                        break
            except Exception:
                pass

        if action == "switch":
            new_port = self._find_free_port(start=old_port + 1)
            if new_port is None:
                new_port = self._find_free_port(start=25565, end=25665)

            if new_port is None:
                self.log("找不到可用端口，无法切换", "error")
                self.server_stopped.emit()
                return

            if self._set_server_property("server-port", new_port):
                self.log(
                    f"已将 server-port 从 {old_port} 改为 {new_port}",
                    "ok")
            else:
                self.server_stopped.emit()
                return

            self.start_server()
            return

        if action == "kill":
            killed = self._kill_port_owner(old_port)
            if not killed:
                self.log(
                    f"未能终止任何进程（端口 {old_port} 占用者可能无权限）",
                    "warn")
                self.server_stopped.emit()
                return

            time.sleep(1.0)
            self.start_server()
            return

    # ========================================================
    #  RCON 连接
    # ========================================================
    def _wait_rcon_ready(self, timeout=60):
        log_path = self.server_path / "logs" / "latest.log"
        start = time.time()
        while time.time() - start < timeout:
            if not self.is_running:
                return
            try:
                if log_path.exists():
                    tail = log_path.read_text(
                        encoding="utf-8", errors="replace")[-4000:]
                    if ("RCON running on" in tail
                            or "RCON Listener started" in tail):
                        time.sleep(0.5)
                        return
            except Exception:
                pass
            time.sleep(0.5)

    def _connect_rcon(self):
        port = int(self.config_data.get("rcon_port", 25575))
        pwd = str(self.config_data.get("rcon_password", "")).replace(
            "\ufeff", "").strip()
        self.log(f"正在连接 RCON（127.0.0.1:{port}）…", "info")

        for attempt in range(1, 11):
            if not self.is_running:
                return
            client = SimpleRCON("127.0.0.1", port, pwd)
            try:
                if client.connect():
                    self.rcon_client = client
                    self.log("RCON 连接成功", "ok")
                    self._on_rcon_connected()
                    return
                client.disconnect()
                self.log(f"RCON 认证失败（第 {attempt} 次）", "warn")
            except Exception as e:
                client.disconnect()
                self.log(f"RCON 连接失败（第 {attempt} 次）：{e}", "warn")
            time.sleep(3)

        self.log("RCON 连接失败，指令不可用", "error")

    def _on_rcon_connected(self):
        try:
            self.server_info.detect_from_log(self.server_path)
        except Exception:
            pass

        def _detect():
            try:
                self.server_info.detect_from_rcon(self.rcon_client)
            except Exception:
                pass
            try:
                self.perm_manager.update_server_version(
                    self.server_info.version)
            except Exception:
                pass
            self.log(f"服务端：{self.server_info.summary()}", "ok")

        try:
            threading.Thread(target=_detect, daemon=True).start()
        except Exception:
            pass

        try:
            self.server_context.invalidate()
        except Exception:
            pass

        self.rcon_connected.emit()

    def manual_reconnect_rcon(self):
        if not self.is_running:
            self.log("服务器未运行", "warn")
            return
        if self.rcon_client:
            try:
                self.rcon_client.disconnect()
            except Exception:
                pass
            self.rcon_client = None
        threading.Thread(target=self._connect_rcon, daemon=True).start()

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

    def _on_server_log_line(self, line):
        msg = re.sub(r"^\[\d{2}:\d{2}:\d{2}\]\s+", "", line)
        low = msg.lower()

        if re.search(r"<[^>]+>\s+\S", msg):
            tag = "player"
        elif re.search(r"System chat:\s*\[([^\]:]+):\s*(.+?)\]", msg):
            tag = "player_cmd"
        elif "error" in low or "exception" in low or "caused by" in low:
            tag = "error"
        elif "warn" in low:
            tag = "warn"
        else:
            tag = "server"

        self.log(msg, tag)

    def _on_player_command(self, player, cmd_name, raw_cmd, source="exact"):
        try:
            self.log(f"{player} 执行：{raw_cmd}", "player_cmd")
        except Exception:
            pass

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
            cooldowns.append(
                int(self.config_data.get("ai_chat_cooldown", 5)))
        if should_moderate:
            cooldowns.append(
                int(self.config_data.get("ai_moderation_cooldown", 3)))

        required_gap = max(cooldowns) if cooldowns else 5

        now = time.time()
        global_gap = float(
            self.config_data.get("ai_global_cooldown", 1.0))
        if global_gap > 0 and now - self._last_ai_call_time < global_gap:
            return

        last_per = self._last_ai_call_per_player.get(player, 0)
        if now - last_per < required_gap:
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
                + "\n\n你可以参考下方实时数据回答玩家：\n\n"
                + "\n\n".join(context_blocks))
        else:
            full_system = base_prompt

        messages = [{"role": "system", "content": full_system}]
        ctx_n = int(self.config_data.get("ai_context_lines", 10))

        for entry in self.ai_history.recent(ctx_n):
            messages.append({
                "role": "user",
                "content": f"<{entry['player']}> {entry['message']}",
            })
            if entry.get("reply"):
                messages.append({
                    "role": "assistant",
                    "content": entry["reply"],
                })

        note_parts = []
        if should_reply:
            note_parts.append("回复这位玩家")
        if should_moderate:
            note_parts.append("审核这条消息是否违规")
        note = "；".join(note_parts)

        messages.append({
            "role": "user",
            "content": f"<{player}> {clean_message}\n\n[{note}]",
        })

        reply_text, err = client.chat(
            messages, temperature=0.7, max_tokens=400)
        if err:
            self.log(f"AI 请求失败：{err}", "error")
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
        self.log(f"AI 处理：<{player}> {raw_message}", "info")

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
        self.quick_rcon(f"tellraw @a {payload}", silent=True)

    def _execute_moderation(self, player, action, reason):
        reason_str = reason or "违反服务器规则"

        if action == "warn":
            safe = reason_str.replace('"', '\\"')
            payload = _json.dumps({
                "text": f"[审核] {player}：{safe}", "color": "yellow"
            }, ensure_ascii=False)
            self.quick_rcon(f"tellraw @a {payload}", silent=True)
        elif action == "kick":
            self.quick_rcon(f"kick {player} {reason_str}", silent=True)
        elif action == "ban":
            self.quick_rcon(f"ban {player} {reason_str}", silent=True)

        self.log(f"AI 审核：{player} → {action}  ({reason_str})", "warn")

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
        stats = {}

        if self._server_pid:
            try:
                import psutil
                p = psutil.Process(self._server_pid)
                mem = p.memory_info().rss / 1024 / 1024
                stats["mem"] = mem
            except Exception:
                pass

        if self.start_time:
            stats["uptime"] = int(time.time() - self.start_time)

        client = self.rcon_client
        if client and client.connected:
            try:
                cmd = self.server_info.cmd_tps()
                if cmd:
                    resp = client.command(cmd) or ""

                    # ★ 优先：找冒号后面的第一个浮点数（标准 TPS 响应格式）
                    m = re.search(
                        r":\s*[^\d]*(\d+(?:\.\d+)?)",
                        resp)
                    if not m:
                        # 兜底1：找所有浮点数里的最大值（过滤版本号等）
                        candidates = re.findall(
                            r"(\d+\.\d+)", resp)
                        floats = []
                        for c in candidates:
                            try:
                                v = float(c)
                                if 0.0 <= v <= 100.0:
                                    floats.append(v)
                            except ValueError:
                                pass
                        if floats:
                            stats["tps"] = max(floats)
                            if "tps" not in stats:
                                pass
                        else:
                            self.log(
                                f"[调试] TPS 解析失败，原始响应："
                                f"{resp[:200]!r}", "warn")
                    else:
                        try:
                            tps_val = float(m.group(1))
                            if 0.0 <= tps_val <= 100.0:
                                stats["tps"] = tps_val
                        except ValueError:
                            pass
            except Exception:
                pass

        self.stats_updated.emit(stats)

    # ========================================================
    #  调度
    # ========================================================
    def _scheduler_loop(self):
        while not self._scheduler_stop.is_set():
            try:
                if (self.config_data.get("auto_backup_enabled")
                        and self.is_running
                        and self.rcon_client
                        and self.rcon_client.connected):
                    interval = int(self.config_data.get(
                        "auto_backup_interval_min", 60)) * 60
                    if time.time() - self._last_auto_backup >= interval:
                        self._last_auto_backup = time.time()
                        self.log("触发自动备份", "info")
                        self.do_backup(wait=True)
                        rotate_backups(
                            self.server_path,
                            int(self.config_data.get(
                                "auto_backup_keep", 10)),
                            self.log,
                            backup_dir=self.data_dir / "backups",
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
                self.log(f"清理区「{zone.get('name')}」自动清理", "info")
                zone["last_clean"] = now
                changed = True
            except Exception as e:
                self.log(
                    f"清理区「{zone.get('name')}」清理失败：{e}", "warn")

        if changed:
            save_clean_zones(self.clean_zones_data)

    def _trigger_drop_clean(self):
        try:
            resp = self.rcon_client.command("list") or ""
            m = re.search(r"There are (\d+) of a max", resp)
            if m and int(m.group(1)) == 0:
                self.log("定时清理触发，当前无玩家在线，跳过", "info")
                return
        except Exception:
            pass

        zones = self.zones_data.get("zones", [])
        active = [z for z in zones if z.get("enabled", True)]

        if not active:
            self.log("触发定时清理（无保护区，全清）", "info")
        else:
            self.log(f"触发定时清理（{len(active)} 个保护区）", "info")

        def _run():
            try:
                self.rcon_client.command(
                    "say §e[系统] §f5 秒后清理地面掉落物，请及时捡取。")
            except Exception:
                pass

            time.sleep(5)

            if not active:
                try:
                    self.rcon_client.command("kill @e[type=item]")
                    self.log("已全清掉落物", "ok")
                except Exception as e:
                    self.log(f"清理失败：{e}", "error")
                return

            dims = set()
            for z in active:
                zd = z.get("dimension", "")
                if zd == "*":
                    dims = set(DIMENSION_KEYS)
                    break
                if zd in DIMENSION_KEYS:
                    dims.add(zd)

            sent = 0
            for dim in DIMENSION_KEYS:
                if dim not in dims:
                    continue
                cmd = build_clean_command(zones, dim)
                if not cmd:
                    continue
                sent += 1
                self.log(f"> {cmd}", "cmd")
                try:
                    self.rcon_client.command(cmd)
                except Exception as e:
                    self.log(f"清理失败：{e}", "warn")

            if sent:
                self.log(f"已按保护区过滤清理（{sent} 个维度）", "ok")

        threading.Thread(target=_run, daemon=True).start()

    # ========================================================
    #  备份
    # ========================================================
    def do_backup(self, wait=False):
        if not self.has_server():
            return
        if self._backup_running:
            self.log("已有备份正在进行", "warn")
            return

        backup_dir = self.data_dir / "backups"

        if wait:
            self._backup_worker(backup_dir)
        else:
            threading.Thread(target=self._backup_worker,
                             args=(backup_dir,), daemon=True).start()

    def _backup_worker(self, backup_dir):
        if self._backup_running:
            return
        self._backup_running = True
        try:
            perform_backup(
                self.server_path, self.rcon_client, self.log,
                backup_dir=backup_dir)
        finally:
            self._backup_running = False
            self.backup_finished.emit()

    # ========================================================
    #  手动清理
    # ========================================================
    def clear_drops(self):
        if not self.has_server():
            return
        zones = self.zones_data.get("zones", [])
        active = [z for z in zones if z.get("enabled", True)]

        if not active:
            self.quick_rcon("kill @e[type=item]")
            self.log("已发送全清掉落物指令", "ok")
            return

        dims = set()
        for z in active:
            zd = z.get("dimension", "")
            if zd == "*":
                dims = set(DIMENSION_KEYS)
                break
            if zd in DIMENSION_KEYS:
                dims.add(zd)

        sent = 0
        for dim in DIMENSION_KEYS:
            if dim not in dims:
                continue
            cmd = build_clean_command(zones, dim)
            if not cmd:
                continue
            sent += 1
            self.quick_rcon(cmd)

        self.log(
            f"已按保护区过滤清理（{len(active)} 个保护区）", "ok")

    # ========================================================
    #  配置保存
    # ========================================================
    def save_config(self):
        if not self.has_server():
            return False
        if registry.update_server(
                self.server_id,
                name=self.current_server.get("name"),
                config=self.config_data):
            self.server_path = Path(
                self.config_data.get("server_path", "."))
            return True
        return False

    # ========================================================
    #  主题
    # ========================================================
    def apply_theme(self, name):
        from ui_qt.theme import theme
        if theme.set(name):
            self.config_data["theme"] = name
            self.save_config()
            self.theme_changed.emit(name)
            return True
        return False

    # ========================================================
    #  多服务器切换
    # ========================================================
    def switch_server(self, server_id):
        """
        切换到指定服务器。

        与之前不同：允许从空状态（无服务器）切换到第一个服务器。
        切换完成后 emit server_switched，由 UI 层刷新所有页面。
        """
        if server_id == self.server_id:
            return False
        if self._switching:
            return False

        server = registry.get_server(server_id)
        if server is None:
            return False

        self._switching = True
        try:
            had_server = self.has_server()

            # =============================================
            #  1. 保存当前服务器配置（如果有）
            # =============================================
            if had_server:
                try:
                    registry.update_server(
                        self.server_id,
                        name=self.current_server.get("name"),
                        config=self.config_data,
                    )
                except Exception:
                    pass

            # =============================================
            #  2. 保存运行状态文件（如果服务器在跑）
            # =============================================
            if had_server and self.is_running and self._server_pid:
                try:
                    pm.save_state({
                        "pid": self._server_pid,
                        "create_time": self._server_create_time,
                        "start_time": self.start_time,
                    })
                    self.log(
                        f"已保存服务器运行状态"
                        f"（PID {self._server_pid}）", "info")
                except Exception as e:
                    self.log(f"保存状态失败：{e}", "warn")

            # =============================================
            #  3. 会话失效（让旧线程停止）
            # =============================================
            self._session_token += 1

            if self.rcon_client:
                try:
                    self.rcon_client.disconnect()
                except Exception:
                    pass
                self.rcon_client = None

            if self._log_watcher:
                try:
                    self._log_watcher.stop()
                except Exception:
                    pass
                self._log_watcher = None

            self.is_running = False
            self.start_time = None
            self._server_pid = None
            self._server_create_time = None
            self._is_external = False
            self._user_stopping = False

            try:
                self.server_context.invalidate()
            except Exception:
                pass

            # =============================================
            #  4. 切换注册表 active
            # =============================================
            try:
                registry.set_active(server_id)
            except Exception:
                pass

            # =============================================
            #  5. 应用新服务器
            # =============================================
            self.server_id = server_id
            self.current_server = server
            self.config_data = dict(server["config"])
            self.server_path = Path(
                self.config_data.get("server_path", "."))

            # 切换数据目录
            try:
                self.data_dir = registry.get_data_dir(server_id)
                set_perm_dir(self.data_dir)
                set_zones_dir(self.data_dir)
                set_clean_dir(self.data_dir)
                set_hist_dir(self.data_dir)
                set_pm_dir(self.data_dir)
            except Exception:
                pass

            # 重新加载数据
            try:
                self.perm_data = load_permissions()
                self.perm_manager.update_data(self.perm_data)
                try:
                    self.perm_manager._violations.clear()
                except Exception:
                    pass
                self.zones_data = load_zones()
                self.clean_zones_data = load_clean_zones()
                self.ai_history = AIHistory()
            except Exception as e:
                self.log(f"加载新服务器数据失败：{e}", "warn")

            self._last_ai_call_time = 0.0
            self._last_ai_call_per_player = {}

            # =============================================
            #  6. 通知 UI
            # =============================================
            self.server_stopped.emit()
            self.server_switched.emit(server_id)

            # =============================================
            #  7. 后台检测新服务器目录下是否有在跑的实例
            # =============================================
            token = self._session_token

            def _detect_async():
                time.sleep(0.3)
                try:
                    self._detect_running_server(token=token)
                except Exception as e:
                    self.log(f"检测新服务器失败：{e}", "warn")

            threading.Thread(target=_detect_async, daemon=True).start()

            self.log(
                f"已切换到服务器："
                f"{self.current_server.get('name', server_id)}", "ok")
            return True
        finally:
            self._switching = False

    # ========================================================
    #  多服务器管理扩展
    # ========================================================
    def add_new_server(self, name, server_path="", java_path=""):
        """创建一个新服务器。返回新 server_id 或 None。"""
        try:
            from core.config import DEFAULT_CONFIG
            cfg = dict(DEFAULT_CONFIG)
            if server_path:
                cfg["server_path"] = server_path
            if java_path:
                cfg["java_path"] = java_path

            sid = registry.add_server(name, cfg)
            self.log(f"已创建服务器：{name}", "ok")
            return sid
        except Exception as e:
            self.log(f"创建服务器失败：{e}", "error")
            return None

    def request_switch_server(self, server_id):
        """UI 触发的切换请求：会先弹确认框（如果服务端在运行）。"""
        if server_id == self.server_id:
            return

        if self.is_running:
            from PySide6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                None, "切换服务器",
                "当前服务器正在运行。\n\n"
                "切换后管理器会与它断开连接（服务端进程不受影响），\n"
                "你可以稍后切回来继续管理。\n\n"
                "继续吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes)
            if reply != QMessageBox.Yes:
                return

        self.switch_server(server_id)