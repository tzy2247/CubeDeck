"""监控 logs/latest.log：抓取玩家命令、玩家聊天，同时把每一行回调出去。"""
import re
import threading
import time
from pathlib import Path

# 这些行是服务端对 RCON 内部命令的技术回应，不显示给用户
IGNORE_LOG_LINES = (
    "Automatic saving is now disabled",
    "Automatic saving is now enabled",
    "Saving is now disabled",
    "Saving is now enabled",
    "Saved the game",
    "Saving the game",
    "Thread RCON Client",
    "Thread RCON Listener",
    "RCON running on",
)

# ---------- 精确模式（Paper/Spigot log-player-commands） ----------
EXACT_PATTERNS = [
    re.compile(
        r"\[Server thread/INFO\]:\s+(\S+)\s+issued server command:\s*(/.*)$"),
    re.compile(
        r"\[Server thread/INFO\]\s+\[[^\]]+\]:\s+(\S+)\s+issued server command:\s*(/.*)$"),
]

# ---------- 反推模式（原版 System chat 反馈） ----------
SYSTEM_CHAT_PATTERN = re.compile(
    r"System chat:\s*\[([^\]:]+):\s*(.+?)\]\s*$"
)

# ---------- 玩家聊天 ----------
CHAT_PATTERNS = [
    re.compile(r"\[Server thread/INFO\]:\s+\[Not Secure\]\s+<([^>]+)>\s+(.+)$"),
    re.compile(r"\[Server thread/INFO\]:\s+<([^>]+)>\s+(.+)$"),
]

IGNORE_FEEDBACK = ("joined the game", "left the game")

# 反馈 → 命令名
FEEDBACK_RULES = [
    (re.compile(r"^Gave\s+\d+\s+.+?\s+to\s+", re.I),                "give"),
    (re.compile(r"^Teleported\s+", re.I),                           "tp"),
    (re.compile(r"^Set\s+the\s+time\s+to\s+", re.I),                "time"),
    (re.compile(r"^The\s+time\s+is\s+now\s+", re.I),                "time"),
    (re.compile(r"^Set\s+(?:own\s+)?game\s+mode\s+to\s+", re.I),    "gamemode"),
    (re.compile(r"^Set\s+.+?'s\s+game\s+mode\s+to\s+", re.I),       "gamemode"),
    (re.compile(r"^Added\s+tag\s+", re.I),                          "tag"),
    (re.compile(r"^Removed\s+tag\s+", re.I),                        "tag"),
    (re.compile(r"^Applied\s+effect\s+", re.I),                     "effect"),
    (re.compile(r"^Gave\s+.+?\s+effect\s+", re.I),                  "effect"),
    (re.compile(r"^Removed\s+effect\s+", re.I),                     "effect"),
    (re.compile(r"^Summoned\s+", re.I),                             "summon"),
    (re.compile(r"^Spawned\s+", re.I),                              "summon"),
    (re.compile(r"^Changed\s+the\s+block\s+at\s+", re.I),           "setblock"),
    (re.compile(r"^Successfully\s+filled\s+", re.I),                "fill"),
    (re.compile(r"^Killed\s+", re.I),                               "kill"),
    (re.compile(r"^Enchanted\s+", re.I),                            "enchant"),
    (re.compile(r"^Set\s+the\s+weather\s+to\s+", re.I),             "weather"),
    (re.compile(r"^Set\s+spawn\s+point\s+", re.I),                  "spawnpoint"),
    (re.compile(r"^World\s+border\s+", re.I),                       "worldborder"),
    (re.compile(r"^Cleared\s+", re.I),                              "clear"),
    (re.compile(r"^Created\s+\d+\s+block", re.I),                   "clone"),
    (re.compile(r"^The\s+nearest\s+", re.I),                        "locate"),
    (re.compile(r"^Placed\s+", re.I),                               "place"),
    (re.compile(r"^Granted\s+", re.I),                              "advancement"),
    (re.compile(r"^Revoked\s+", re.I),                              "advancement"),
    (re.compile(r"^Set\s+max\s+health\s+", re.I),                   "attribute"),
    (re.compile(r"^Set\s+difficulty\s+to\s+", re.I),                "difficulty"),
    (re.compile(r"^Gave\s+.+?\s+experience", re.I),                 "xp"),
    (re.compile(r"^Added\s+.+?\s+experience", re.I),                "xp"),
    (re.compile(r"^Played\s+sound\s+", re.I),                       "playsound"),
    (re.compile(r"^Stopped\s+sound\s+", re.I),                      "stopsound"),
    (re.compile(r"^Applied\s+\d+(?:\.\d+)?\s+damage", re.I),        "damage"),
    (re.compile(r"^Spread\s+\d+\s+players", re.I),                  "spreadplayers"),
    (re.compile(r"^Added\s+.+?\s+to\s+force-load", re.I),           "forceload"),

    (re.compile(r"^Made\s+.+?\s+a\s+server\s+operator", re.I),      "op"),
    (re.compile(r"^Made\s+.+?\s+no\s+longer\s+a\s+server\s+operator", re.I), "deop"),
    (re.compile(r"^Kicked\s+", re.I),                               "kick"),
    (re.compile(r"^Banned\s+player\s+", re.I),                      "ban"),
    (re.compile(r"^Banned\s+IP\s+", re.I),                          "ban-ip"),
    (re.compile(r"^Unbanned\s+player\s+", re.I),                    "pardon"),
    (re.compile(r"^Unbanned\s+IP\s+", re.I),                        "pardon-ip"),
    (re.compile(r"^Added\s+.+?\s+to\s+the\s+whitelist", re.I),      "whitelist"),
    (re.compile(r"^Removed\s+.+?\s+from\s+the\s+whitelist", re.I),  "whitelist"),
    (re.compile(r"^Turned\s+(?:on|off)\s+the\s+whitelist", re.I),   "whitelist"),
    (re.compile(r"^Stopping\s+the\s+server", re.I),                 "stop"),
    (re.compile(r"^Saved\s+the\s+game", re.I),                      "save-all"),
    (re.compile(r"^Saving\s+is\s+now\s+disabled", re.I),            "save-off"),
    (re.compile(r"^Saving\s+is\s+now\s+enabled", re.I),             "save-on"),
    (re.compile(r"^Reloading", re.I),                               "reload"),
]


class LogWatcher(threading.Thread):
    def __init__(self, log_path: Path, on_command,
                 on_line=None, on_chat=None,
                 poll=0.3, read_from_start=False):
        super().__init__(daemon=True)
        self.log_path = Path(log_path)
        self.on_command = on_command
        self.on_line = on_line
        self.on_chat = on_chat
        self.poll = poll
        self.read_from_start = read_from_start
        self._stop = threading.Event()
        self._pos = 0
        self._fp = None

        # 诊断
        self.line_count = 0
        self.exact_count = 0
        self.inferred_count = 0
        self.chat_count = 0
        self.last_line = ""
        self.last_command = ""
        self.last_chat = ""
        self.error = ""

    @property
    def command_count(self):
        return self.exact_count + self.inferred_count

    def stop(self):
        self._stop.set()

    def run(self):
        self._open_log()
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                self.error = str(e)
            time.sleep(self.poll)
        if self._fp:
            try:
                self._fp.close()
            except Exception:
                pass

    # ---------- 内部 ----------
    def _open_log(self):
        try:
            if self.log_path.exists():
                self._fp = open(self.log_path, "r",
                                encoding="utf-8", errors="replace")
                if not self.read_from_start:
                    self._fp.seek(0, 2)
                self._pos = self._fp.tell()
        except Exception as e:
            self._fp = None
            self.error = str(e)

    def _tick(self):
        if not self.log_path.exists():
            if self._fp:
                try:
                    self._fp.close()
                except Exception:
                    pass
                self._fp = None
            return

        try:
            size = self.log_path.stat().st_size
        except Exception:
            return

        if self._fp is None:
            self._open_log()
            return

        if size < self._pos:
            try:
                self._fp.close()
            except Exception:
                pass
            self._fp = open(self.log_path, "r",
                            encoding="utf-8", errors="replace")
            self._pos = 0

        while True:
            line = self._fp.readline()
            if not line:
                break
            self._pos = self._fp.tell()
            self._handle_line(line.rstrip())

    def _handle_line(self, line: str):
        self.line_count += 1
        self.last_line = line[:240]

        self.line_count += 1
        self.last_line = line[:240]

        # ★ 过滤服务端的技术性回应
        for ignore in IGNORE_LOG_LINES:
            if ignore in line:
                # 仍需回调 on_line，让控制台看到完整日志（可选）
                # 若不想让用户看到，直接 return 即可
                return

        # ---- 全行回调（给控制台显示）----
        if self.on_line:
            try:
                self.on_line(line)
            except Exception:
                pass

        # ---- 玩家聊天 ----
        if self.on_chat:
            for pat in CHAT_PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                player = m.group(1).strip()
                message = m.group(2).strip()
                if (player and message
                        and player.lower() not in ("server", "rcon")):
                    self.chat_count += 1
                    self.last_chat = f"{player}: {message}"
                    try:
                        self.on_chat(player, message)
                    except Exception:
                        pass
                break

        # ---- 精确命令模式 ----
        for pat in EXACT_PATTERNS:
            m = pat.search(line)
            if not m:
                continue
            player = m.group(1).strip()
            raw = m.group(2).strip()
            if not raw.startswith("/"):
                continue
            if player.lower() in ("server", "rcon"):
                continue
            body = raw[1:].strip()
            name = body.split()[0].lower() if body else ""
            if ":" in name:
                name = name.split(":", 1)[1]
            if not name:
                continue
            self.exact_count += 1
            self.last_command = f"[exact] {player}: {raw}"
            try:
                self.on_command(player, name, raw, "exact")
            except Exception:
                pass
            return

        # ---- 反推命令模式 ----
        m = SYSTEM_CHAT_PATTERN.search(line)
        if not m:
            return

        player = m.group(1).strip()
        feedback = m.group(2).strip()

        for word in IGNORE_FEEDBACK:
            if word in feedback:
                return
        if player.lower() in ("server", "rcon"):
            return

        cmd_name = self._infer_command(feedback)
        if not cmd_name:
            return

        self.inferred_count += 1
        self.last_command = f"[infer] {player}: {feedback}"
        try:
            self.on_command(player, cmd_name,
                            f"/{cmd_name}  /* {feedback} */",
                            "inferred")
        except Exception:
            pass

    @staticmethod
    def _infer_command(feedback: str):
        for pat, cmd in FEEDBACK_RULES:
            if pat.search(feedback):
                return cmd
        return None