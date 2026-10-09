"""全局应用状态：封装 core 模块 + Qt 信号槽。"""
import json as _json
import re
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

    def __init__(self):
        super().__init__()

        # ====================================================
        #  1. 注册表 + 当前服务器
        # ====================================================
        paths.ensure_userdata_root()

        self.registry = registry.load_registry()
        self.current_server = registry.get_active()

        if self.current_server is None:
            from core.config import DEFAULT_CONFIG
            sid = registry.add_server("默认服务器", dict(DEFAULT_CONFIG))
            self.current_server = registry.get_server(sid)

        self.server_id = self.current_server["id"]
        self.config_data = dict(self.current_server["config"])
        self.server_path = Path(self.config_data.get("server_path", "."))

        # ====================================================
        #  2. 数据目录（必须在加载数据之前设置）
        # ====================================================
        self.data_dir = registry.get_data_dir(self.server_id)
        set_perm_dir(self.data_dir)
        set_zones_dir(self.data_dir)
        set_clean_dir(self.data_dir)
        set_hist_dir(self.data_dir)

        # ====================================================
        #  3. 运行状态
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

        # ====================================================
        #  4. core 模块
        # ====================================================
        self.server_info = ServerInfo()
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

        # AI 冷却
        self._last_ai_call_time = 0.0
        self._last_ai_call_per_player = {}

        # ====================================================
        #  5. 后台线程
        # ====================================================
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
        if self.is_running:
            return
        self.server_starting.emit()
        threading.Thread(target=self._start_server_worker,
                         daemon=True).start()

    def _start_server_worker(self):
        """外壳：捕获所有异常，保证信号始终发出。"""
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
            # ★ 无论如何要复位 UI
            self.server_stopped.emit()

    def _do_start_server(self):
        """实际启动逻辑。"""
        # ---- 1. 检查是否有已运行的服务端 ----
        existing = pm.find_running_server(self.server_path)
        if existing:
            self.log(
                f"检测到已在运行的服务端（PID {existing['pid']}），正在接管…",
                "info")
            self._take_over(existing)
            return

        # ---- 2. 校验 Java 和 jar ----
        java_path = Path(self.config_data.get("java_path", ""))
        if not java_path.exists():
            self.log(f"找不到 Java：{java_path}", "error")
            self.server_stopped.emit()
            return

        if not self.server_path.exists():
            self.log(f"服务器目录不存在：{self.server_path}", "error")
            self.server_stopped.emit()
            return

        try:
            jars = sorted(self.server_path.glob("*.jar"))
        except Exception as e:
            self.log(f"扫描 jar 失败：{e}", "error")
            self.server_stopped.emit()
            return

        if not jars:
            self.log("未找到 .jar 文件", "error")
            self.server_stopped.emit()
            return

        jar = jars[0]
        xmx = self.config_data.get("memory_xmx", "4G")
        xms = self.config_data.get("memory_xms", "2G")
        extra = self.config_data.get("jvm_args", "").strip()

        cmd = [str(java_path), f"-Xmx{xmx}", f"-Xms{xms}"]
        if extra:
            cmd += extra.split()
        cmd += ["-jar", jar.name, "nogui"]

        self.log(f"启动服务端：{jar.name}  Xmx={xmx} Xms={xms}", "info")

        # ---- 3. 启动进程 ----
        try:
            proc = pm.launch_detached(cmd, self.server_path)
        except Exception as e:
            self.log(f"启动失败：{e}", "error")
            self.server_stopped.emit()
            return

        # ---- 4. 记录状态 ----
        time.sleep(0.3)
        try:
            ct = pm.get_create_time(proc.pid) or time.time()
        except Exception:
            ct = time.time()

        self._server_pid = proc.pid
        self._server_create_time = ct
        self._is_external = False
        self.is_running = True
        self.start_time = time.time()
        self._user_stopping = False

        try:
            pm.save_state({
                "pid": proc.pid,
                "create_time": ct,
                "start_time": self.start_time,
            })
        except Exception:
            pass

        # ---- 5. ★ 立即发信号：UI 马上切"运行中" ----
        self.server_started.emit()

        # ---- 6. 启动日志监控 ----
        try:
            self._start_log_watcher()
        except Exception as e:
            self.log(f"日志监控启动失败：{e}", "warn")

        # ---- 7. 启动进程监控 ----
        try:
            threading.Thread(target=self._watch_process,
                             daemon=True).start()
        except Exception:
            pass

        # ---- 8. RCON 连接放到独立线程，避免阻塞启动流程 ----
        try:
            threading.Thread(target=self._connect_rcon_delayed,
                             daemon=True).start()
        except Exception:
            pass

    def _connect_rcon_delayed(self):
        """等 RCON 就绪后连接（独立线程）。"""
        try:
            self._wait_rcon_ready(timeout=90)
        except Exception:
            pass
        try:
            self._connect_rcon()
        except Exception as e:
            self.log(f"RCON 连接线程出错：{e}", "warn")

    def _take_over(self, existing):
        self._server_pid = existing["pid"]
        self._server_create_time = existing.get("create_time") or 0.0
        self._is_external = True
        self.is_running = True
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
                             daemon=True).start()
        except Exception:
            pass

    def _detect_running_server(self):
        try:
            running = pm.find_running_server(self.server_path)
        except Exception:
            running = None

        if not running:
            try:
                pm.clear_state()
            except Exception:
                pass
            return

        try:
            self.log(
                f"检测到已在运行的服务端（PID {running['pid']}），正在接管…",
                "info")
            self._take_over(running)
        except Exception as e:
            self.log(f"接管失败：{e}", "warn")

    # ========================================================
    #  服务器停止
    # ========================================================
    def stop_server(self):
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
        # 优先用 RCON 优雅停止
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

    def _watch_process(self):
        while self.is_running:
            if not pm.is_process_alive(self._server_pid,
                                        self._server_create_time):
                self._on_server_exited()
                return
            time.sleep(2)

    def _on_server_exited(self):
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
                if not self.is_running:
                    self.start_server()
            threading.Thread(target=_restart, daemon=True).start()

    # ========================================================
    #  RCON 连接
    # ========================================================
    def _wait_rcon_ready(self, timeout=60):
        """轮询服务端日志，等到 RCON 监听器启动再返回。"""
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
                    m = re.search(r"(\d+\.\d+)[,)]", resp)
                    if m:
                        stats["tps"] = float(m.group(1))
            except Exception:
                pass

            try:
                resp = client.command("list") or ""
                m = re.search(r"There are (\d+) of a max of (\d+)", resp)
                if m:
                    stats["players"] = f"{m.group(1)} / {m.group(2)}"
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
        if self._backup_running:
            self.log("已有备份正在进行", "warn")
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
            perform_backup(
                self.server_path, self.rcon_client, self.log)
        finally:
            self._backup_running = False

    # ========================================================
    #  手动清理
    # ========================================================
    def clear_drops(self):
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
        """保存当前服务器配置到注册表。"""
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
        """切换到指定服务器（不影响正在运行的服务端进程）。"""
        if server_id == self.server_id:
            return False

        server = registry.get_server(server_id)
        if server is None:
            return False

        # 保存当前配置
        registry.update_server(
            self.server_id,
            name=self.current_server.get("name"),
            config=self.config_data,
        )

        # 断开 RCON / 日志监控
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

        # 切换数据目录
        registry.set_active(server_id)
        self.server_id = server_id
        self.current_server = server
        self.config_data = dict(server["config"])
        self.server_path = Path(
            self.config_data.get("server_path", "."))

        self.data_dir = registry.get_data_dir(server_id)
        set_perm_dir(self.data_dir)
        set_zones_dir(self.data_dir)
        set_clean_dir(self.data_dir)
        set_hist_dir(self.data_dir)

        # 重新加载数据
        self.perm_data = load_permissions()
        self.perm_manager.update_data(self.perm_data)
        self.zones_data = load_zones()
        self.clean_zones_data = load_clean_zones()
        self.ai_history = AIHistory()

        # 清空运行状态
        self.is_running = False
        self.start_time = None
        self._server_pid = None
        self._server_create_time = None
        self._is_external = False

        try:
            self.server_context.invalidate()
        except Exception:
            pass

        # 检测新服务器是否有在跑的实例
        threading.Thread(target=self._detect_running_server,
                         daemon=True).start()

        self.log(
            f"已切换到服务器："
            f"{self.current_server.get('name', server_id)}",
            "ok")
        return True