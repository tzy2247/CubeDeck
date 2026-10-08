"""采集服务器实时状态，作为 AI 的上下文。"""
import re
import threading
import time


class ServerContextProvider:
    """
    周期性采样服务器状态，缓存给 AI 使用。
    采样触发时机：每次 AI 调用前，若缓存过期则刷新。
    """

    def __init__(self, app, cache_ttl=30.0):
        self.app = app
        self._cache_ttl = cache_ttl
        self._cache = {}
        self._cache_time = 0.0
        self._lock = threading.Lock()

    # ========================================================
    #  对外接口
    # ========================================================
    def get_summary(self) -> str:
        """返回服务器状态汇总文本，用于塞进 AI 的 prompt。"""
        with self._lock:
            now = time.time()
            if now - self._cache_time > self._cache_ttl:
                self._refresh_locked()
            return self._format_summary_locked()

    def get_player_detail(self, player: str) -> str:
        """
        按需查询指定玩家的详细数据（不缓存，实时查）。
        玩家不在线或 RCON 断开时返回空字符串。
        """
        client = self.app.rcon_client
        if not (client and client.connected):
            return ""
        if not player:
            return ""

        lines = []
        for field, label in (
            ("Pos",        "坐标"),
            ("Health",     "血量"),
            ("XpLevel",    "经验等级"),
            ("foodLevel",  "饱食度"),
            ("Dimension",  "所在维度"),
        ):
            try:
                resp = client.command(f"data get entity {player} {field}") or ""
                value = self._extract_value(resp)
                if value:
                    lines.append(f"- {label}: {value}")
            except Exception:
                pass

        if not lines:
            return ""
        return f"【{player} 的实时数据】\n" + "\n".join(lines)

    def invalidate(self):
        """手动失效缓存，下次调用会立即刷新。"""
        with self._lock:
            self._cache_time = 0.0

    # ========================================================
    #  内部实现
    # ========================================================
    def _refresh_locked(self):
        client = self.app.rcon_client
        self._cache = {}
        self._cache_time = time.time()

        if not (client and client.connected):
            return

        info = self.app.server_info

        # ---- 版本 ----
        try:
            self._cache["version"] = info.summary()
        except Exception:
            pass

        # ---- 在线玩家 ----
        try:
            resp = client.command("list") or ""
            m = re.search(r"There are (\d+) of a max of (\d+)", resp)
            if m:
                self._cache["online"] = f"{m.group(1)} / {m.group(2)}"
                names_part = resp.split(":", 1)[-1].strip()
                if names_part:
                    self._cache["players"] = names_part
        except Exception:
            pass

        # ---- 游戏内时间 ----
        try:
            resp = client.command("time query daytime") or ""
            m = re.search(r"(\d+)", resp)
            if m:
                ticks = int(m.group(1)) % 24000
                hour = (ticks // 1000 + 6) % 24
                minute = int((ticks % 1000) * 60 / 1000)
                if 0 <= ticks < 12000:
                    period = "白天"
                elif 12000 <= ticks < 13800:
                    period = "日落"
                elif 13800 <= ticks < 22200:
                    period = "夜晚"
                else:
                    period = "日出"
                self._cache["daytime"] = (
                    f"{hour:02d}:{minute:02d} ({period})")
        except Exception:
            pass

        # ---- 世界天数 ----
        try:
            resp = client.command("time query gametime") or ""
            m = re.search(r"(\d+)", resp)
            if m:
                total_ticks = int(m.group(1))
                day = total_ticks // 24000
                self._cache["day"] = str(day)
        except Exception:
            pass

        # ---- TPS ----
        try:
            cmd = info.cmd_tps()
            if cmd:
                resp = client.command(cmd) or ""
                m = re.search(r"(\d+\.\d+)", resp)
                if m:
                    self._cache["tps"] = m.group(1)
        except Exception:
            pass

    def _format_summary_locked(self):
        if not self._cache:
            return "【服务器状态】\nRCON 未连接，暂无实时数据。"

        lines = ["【当前服务器状态】"]
        if "version" in self._cache:
            lines.append(f"- 服务端: {self._cache['version']}")
        if "online" in self._cache:
            lines.append(f"- 在线人数: {self._cache['online']}")
        if "players" in self._cache:
            lines.append(f"- 玩家列表: {self._cache['players']}")
        if "day" in self._cache:
            lines.append(f"- 世界天数: 第 {self._cache['day']} 天")
        if "daytime" in self._cache:
            lines.append(f"- 游戏内时间: {self._cache['daytime']}")
        if "tps" in self._cache:
            lines.append(f"- 服务器 TPS: {self._cache['tps']}")
        return "\n".join(lines)

    @staticmethod
    def _extract_value(resp: str) -> str:
        """从 data get 响应里提取值。
        例: 'Steve has the following entity data: 12.5d' → '12.5d'
            'No entity was found' → ''
        """
        if not resp:
            return ""
        if "No entity was found" in resp:
            return ""
        if ":" in resp:
            return resp.split(":", 1)[1].strip()
        return resp.strip()