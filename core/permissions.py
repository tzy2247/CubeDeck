"""权限数据模型、违规检查、执法动作。"""
import json
import time
from pathlib import Path

from core.commands import all_known_commands


# 数据目录由 app 注入
_data_dir = Path(".")


def set_data_dir(d):
    global _data_dir
    _data_dir = Path(d)


def _perm_file():
    return _data_dir / "permissions.json"


DEFAULT_PERM = {
    "enforcement_mode": "log",
    "check_window_seconds": 300,
    "violations_to_kick": 3,
    "violations_to_ban": 10,
    "players": {},
    "groups": {},
    "player_groups": {},
    "forbidden": ["stop", "op", "deop", "ban", "ban-ip",
                  "whitelist", "save-all", "save-off", "save-on", "reload"],
    "whitelist_players": [],
}


def load_permissions():
    path = _perm_file()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in DEFAULT_PERM.items():
                data.setdefault(k, v)
            return data
        except Exception:
            return dict(DEFAULT_PERM)
    save_permissions(DEFAULT_PERM)
    return dict(DEFAULT_PERM)


def save_permissions(data):
    try:
        path = _perm_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False
    

class PermissionManager:
    """权限检查与执法。"""

    def __init__(self, data, server_version=(0, 0, 0), log=None, action=None):
        self.data = data
        self.server_version = server_version
        self.log = log or (lambda m, t="info": None)
        self.action = action or (lambda m, t="info": None)
        self._violations = {}     # {name: [(ts, cmd, raw), ...]}

    # ---------- 外部更新 ----------
    def update_data(self, data):
        self.data = data

    def update_server_version(self, version):
        self.server_version = version

    # ---------- 查询 ----------
    def allowed_commands(self, player: str) -> set:
        allowed = set(self.data.get("players", {}).get(player, []))
        for gname in self.data.get("player_groups", {}).get(player, []):
            allowed.update(self.data.get("groups", {}).get(gname, []))
        valid = all_known_commands(self.server_version)
        return allowed & valid

    def is_whitelisted(self, player: str) -> bool:
        return player in self.data.get("whitelist_players", [])

    def check(self, player: str, cmd_name: str):
        """返回 (ok, reason)。"""
        if self.is_whitelisted(player):
            return True, "白名单玩家"

        mode = self.data.get("enforcement_mode", "log")
        if mode == "off":
            return True, "审计关闭"

        if cmd_name in set(self.data.get("forbidden", [])):
            return False, "该命令被全局禁止"

        if cmd_name in self.allowed_commands(player):
            return True, "已授权"

        return False, f"未授权使用 /{cmd_name}"

    # ---------- 违规处理 ----------
    def on_violation(self, player: str, cmd_name: str, raw_cmd: str):
        now = time.time()
        window = self.data.get("check_window_seconds", 300)
        history = self._violations.setdefault(player, [])
        history.append((now, cmd_name, raw_cmd))
        self._violations[player] = [
            v for v in history if now - v[0] <= window
        ]
        count = len(self._violations[player])

        self.log(f"⚠ {player} 越权执行：{raw_cmd}", "warn")

        mode = self.data.get("enforcement_mode", "log")
        if mode == "log":
            return

        if mode == "warn":
            msg = (f"§c[权限] §f你执行了未授权命令 §e{cmd_name}§f。"
                   f"本次已记录，请遵守服务器规则。")
            payload = json.dumps({"text": msg}, ensure_ascii=False)
            self.action(f"tellraw {player} {payload}")
            return

        if mode == "kick":
            threshold = int(self.data.get("violations_to_kick", 3))
            if count >= threshold:
                self.action(f"kick {player} 越权使用命令：{cmd_name}")
                self.log(f"👉 已踢出 {player}（{count}/{threshold}）", "warn")
            else:
                self.log(f"   违规 {count}/{threshold}，暂不踢出", "info")
            return

        if mode == "ban":
            threshold = int(self.data.get("violations_to_ban", 10))
            if count >= threshold:
                self.action(
                    f"ban {player} 多次越权使用命令：{cmd_name}")
                self.log(f"👉 已封禁 {player}（{count}/{threshold}）", "warn")
            else:
                self.log(f"   违规 {count}/{threshold}，暂不封禁", "info")

    def reset_violation(self, player: str):
        self._violations.pop(player, None)

    def get_violations(self, player: str):
        return list(self._violations.get(player, []))