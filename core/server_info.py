"""服务端类型与版本探测 + 能力矩阵 + 跨版本命令适配。"""
import re
from pathlib import Path


SERVER_PATTERNS = [
    ("purpur",    r"running Purpur"),
    ("paper",     r"running Paper"),
    ("spigot",    r"running (?:CraftBukkit|Spigot)"),
    ("neoforge",  r"(?:Powered by|running) NeoForge"),
    ("forge",     r"(?:Powered by|running) Forge"),
    ("fabric",    r"Loading Minecraft .+ with Fabric"),
]


class ServerInfo:
    def __init__(self):
        self.type = "vanilla"
        self.version = (0, 0, 0)

    # ---------- 探测 ----------
    def detect_from_log(self, server_path: Path):
        log = server_path / "logs" / "latest.log"
        if not log.exists():
            return
        try:
            head = log.read_text(encoding="utf-8", errors="replace")[:8000]
        except Exception:
            return

        for name, pat in SERVER_PATTERNS:
            if re.search(pat, head, re.IGNORECASE):
                self.type = name
                break

        m = re.search(r"MC:\s*(\d+)\.(\d+)(?:\.(\d+))?", head)
        if m:
            self.version = tuple(int(x) for x in m.groups() if x)
            return
        m = re.search(
            r"Minecraft server version\s+(\d+)\.(\d+)(?:\.(\d+))?", head)
        if m:
            self.version = tuple(int(x) for x in m.groups() if x)

    def detect_from_rcon(self, rcon):
        if not (rcon and getattr(rcon, "connected", False)):
            return
        try:
            resp = rcon.command("version") or ""
        except Exception:
            return

        low = resp.lower()
        if "purpur" in low:
            self.type = "purpur"
        elif "paper" in low:
            self.type = "paper"
        elif "spigot" in low or "craftbukkit" in low:
            self.type = "spigot"
        elif "neoforge" in low:
            self.type = "neoforge"
        elif "forge" in low:
            self.type = "forge"
        elif "fabric" in low:
            self.type = "fabric"

        m = re.search(r"MC:\s*(\d+)\.(\d+)(?:\.(\d+))?", resp)
        if not m:
            m = re.search(r"version\s+(\d+)\.(\d+)(?:\.(\d+))?", resp)
        if m:
            self.version = tuple(int(x) for x in m.groups() if x)

    # ---------- 能力查询 ----------
    def has(self, cap: str) -> bool:
        v = self.version

        if cap == "item_replace":    return v >= (1, 17)
        if cap == "replaceitem":     return (1, 16) <= v < (1, 17)
        if cap == "equipment_field": return v >= (1, 20, 5)
        if cap == "data_command":    return v >= (1, 13)
        if cap == "execute_in":      return v >= (1, 13)
        if cap == "effect_give":     return v >= (1, 13)
        if cap == "save_flush":      return v >= (1, 13)
        if cap == "tps":
            return self.type in ("paper", "spigot", "purpur",
                                 "forge", "neoforge")
        if cap == "luckperms":
            return self.type in ("paper", "spigot", "purpur")
        return False

    # ---------- 命令适配 ----------
    def cmd_set_item(self, player, slot, item_id, count):
        if self.has("item_replace"):
            return f"item replace entity {player} {slot} with {item_id} {count}"
        return f"replaceitem entity {player} {slot} {item_id} {count}"

    def cmd_clear_slot(self, player, slot):
        if self.has("item_replace"):
            return f"item replace entity {player} {slot} with air 1"
        return f"replaceitem entity {player} {slot} air 1"

    def cmd_tps(self):
        if self.type in ("paper", "spigot", "purpur"):
            return "tps"
        if self.type == "neoforge":
            return "neoforge tps"
        if self.type == "forge":
            return "forge tps"
        return None

    def summary(self) -> str:
        v = (".".join(map(str, self.version))
             if self.version != (0, 0, 0) else "未知")
        return f"{self.type} {v}"