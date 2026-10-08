import re
import shutil
from tkinter import messagebox
import customtkinter as ctk
from core.theme import C
from core.config import save_config


# ============================================================
#  字段定义
#  (分组, key, 中文标签, 类型)
#  类型: str / int / bool / password / enum:选项1,选项2,...
# ============================================================
PROP_FIELDS = [
    # ---------- 基础 ----------
    ("基础", "motd",               "服务器标语 (MOTD)",        "str"),
    ("基础", "server-ip",          "绑定 IP（留空=所有网卡）",   "str"),
    ("基础", "server-port",        "服务器端口",               "int"),
    ("基础", "max-players",        "最大玩家数",               "int"),
    ("基础", "online-mode",        "正版验证",                 "bool"),
    ("基础", "white-list",         "启用白名单",               "bool"),
    ("基础", "enforce-whitelist",  "强制白名单",               "bool"),
    ("基础", "hide-online-players","隐藏在线玩家列表",          "bool"),
    ("基础", "accepts-transfers",  "接受跨服转移",             "bool"),

    # ---------- 游戏玩法 ----------
    ("游戏玩法", "difficulty",               "难度",
        "enum:peaceful,easy,normal,hard"),
    ("游戏玩法", "gamemode",                 "默认游戏模式",
        "enum:survival,creative,adventure,spectator"),
    ("游戏玩法", "force-gamemode",           "强制游戏模式",       "bool"),
    ("游戏玩法", "hardcore",                 "极限模式",           "bool"),
    ("游戏玩法", "pvp",                      "允许 PVP",           "bool"),
    ("游戏玩法", "allow-flight",             "允许飞行",           "bool"),
    ("游戏玩法", "allow-nether",             "允许下界",           "bool"),
    ("游戏玩法", "generate-structures",      "生成结构",           "bool"),
    ("游戏玩法", "spawn-protection",         "出生点保护半径",      "int"),
    ("游戏玩法", "level-name",               "世界名称",           "str"),
    ("游戏玩法", "level-seed",               "世界种子",           "str"),
    ("游戏玩法", "level-type",               "世界类型（如 minecraft:normal）", "str"),
    ("游戏玩法", "max-world-size",           "世界边界最大值",      "int"),
    ("游戏玩法", "player-idle-timeout",      "挂机踢出（分钟，0=禁用）", "int"),
    ("游戏玩法", "pause-when-empty-seconds", "空服暂停（秒，0=禁用）",  "int"),

    # ---------- 性能 ----------
    ("性能", "view-distance",                   "视距（区块）",           "int"),
    ("性能", "simulation-distance",             "模拟距离（区块）",        "int"),
    ("性能", "max-tick-time",                   "最大 tick 时间（ms）",    "int"),
    ("性能", "entity-broadcast-range-percentage","实体广播范围（%）",      "int"),
    ("性能", "max-chained-neighbor-updates",    "链式方块更新上限",        "int"),
    ("性能", "network-compression-threshold",   "网络压缩阈值",           "int"),
    ("性能", "sync-chunk-writes",               "同步区块写入",           "bool"),
    ("性能", "use-native-transport",            "使用原生传输",           "bool"),
    ("性能", "region-file-compression",         "区域文件压缩",
        "enum:deflate,lz4,none"),
    ("性能", "rate-limit",                      "数据包速率限制",          "int"),
    ("性能", "status-heartbeat-interval",       "状态心跳间隔（ms）",      "int"),

    # ---------- 聊天 / 消息 ----------
    ("聊天 / 消息", "broadcast-console-to-ops",        "向 OP 广播控制台指令",  "bool"),
    ("聊天 / 消息", "broadcast-rcon-to-ops",           "向 OP 广播 RCON 指令",  "bool"),
    ("聊天 / 消息", "chat-spam-threshold-seconds",     "聊天刷屏阈值（秒）",    "int"),
    ("聊天 / 消息", "command-spam-threshold-seconds",  "指令刷屏阈值（秒）",    "int"),
    ("聊天 / 消息", "enforce-secure-profile",          "强制安全聊天签名",      "bool"),
    ("聊天 / 消息", "log-ips",                         "记录玩家 IP",          "bool"),
    ("聊天 / 消息", "text-filtering-config",           "文本过滤配置",          "str"),
    ("聊天 / 消息", "text-filtering-version",          "文本过滤版本",          "int"),
    ("聊天 / 消息", "enable-code-of-conduct",          "启用行为准则",          "bool"),

    # ---------- RCON / 查询 ----------
    ("RCON / 查询", "enable-rcon",              "启用 RCON",           "bool"),
    ("RCON / 查询", "rcon.port",                "RCON 端口",           "int"),
    ("RCON / 查询", "rcon.password",            "RCON 密码",           "password"),
    ("RCON / 查询", "enable-query",             "启用 Query",          "bool"),
    ("RCON / 查询", "query.port",               "Query 端口",          "int"),
    ("RCON / 查询", "enable-status",            "响应服务器列表状态",    "bool"),
    ("RCON / 查询", "enable-jmx-monitoring",    "启用 JMX 监控",       "bool"),
    ("RCON / 查询", "prevent-proxy-connections","阻止代理连接",         "bool"),

    # ---------- 权限 ----------
    ("权限", "op-permission-level",       "OP 权限等级（1-4）",     "int"),
    ("权限", "function-permission-level", "函数权限等级（1-4）",     "int"),

    # ---------- 资源包 ----------
    ("资源包", "require-resource-pack", "强制资源包",     "bool"),
    ("资源包", "resource-pack",         "资源包 URL",     "str"),
    ("资源包", "resource-pack-id",      "资源包 ID",      "str"),
    ("资源包", "resource-pack-prompt",  "资源包提示文本",  "str"),
    ("资源包", "resource-pack-sha1",    "资源包 SHA1",    "str"),

    # ---------- 高级 ----------
    ("高级", "initial-enabled-packs",  "初始启用数据包",           "str"),
    ("高级", "initial-disabled-packs", "初始禁用数据包",           "str"),
    ("高级", "generator-settings",     "生成器设置（JSON）",        "str"),
    ("高级", "bug-report-link",        "Bug 报告链接",            "str"),

    ("高级", "management-server-enabled",         "启用管理服务器",           "bool"),
    ("高级", "management-server-host",            "管理服务器主机",           "str"),
    ("高级", "management-server-port",            "管理服务器端口（0=随机）",  "int"),
    ("高级", "management-server-secret",          "管理服务器密钥",           "password"),
    ("高级", "management-server-tls-enabled",     "管理服务器启用 TLS",       "bool"),
    ("高级", "management-server-allowed-origins", "管理服务器允许的来源",      "str"),
]

GROUP_ORDER = ["基础", "游戏玩法", "性能", "聊天 / 消息",
               "RCON / 查询", "权限", "资源包", "高级"]


class PropertiesPage:
    def __init__(self, parent, app):
        self.app = app
        self.f = app.fonts
        self._vars = {}      # key -> (typ, var)
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    @property
    def _props_path(self):
        return self.app.server_path / "server.properties"

    # ========================================================
    #  构建 UI
    # ========================================================
    def _build(self):
        f = self.f
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)

        # ---- 头部 ----
        header = ctk.CTkFrame(self.frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header, text="server.properties", font=f["h1"],
                     text_color=C["text"]).grid(row=0, column=0, sticky="w")

        self.status = ctk.CTkLabel(header, text="", font=f["small"],
                                   text_color=C["text_dim"])
        self.status.grid(row=0, column=1, padx=(0, 10))

        ctk.CTkButton(header, text="🔄  重新加载", width=110, height=38,
                      corner_radius=10, fg_color="transparent",
                      hover_color=C["card_hover"], border_width=1,
                      border_color=C["border"], text_color=C["text_dim"],
                      font=f["body"], command=self.load
                      ).grid(row=0, column=2, padx=(0, 10))

        ctk.CTkButton(header, text="💾  保存", width=110, height=38,
                      corner_radius=10, font=f["h2"], fg_color=C["accent"],
                      hover_color=C["accent_hover"], command=self.save
                      ).grid(row=0, column=3)

        # ---- 滚动区 ----
        scroll = ctk.CTkScrollableFrame(
            self.frame, fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        scroll.grid(row=1, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        # ---- 按分组渲染卡片 ----
        for gi, group in enumerate(GROUP_ORDER):
            fields = [fd for fd in PROP_FIELDS if fd[0] == group]
            if not fields:
                continue
            self._render_group(scroll, group, fields, gi)

    def _render_group(self, parent, title, fields, row):
        f = self.f

        card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=16,
                            border_width=1, border_color=C["border"])
        card.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        card.grid_columnconfigure(1, weight=1)

        # 组标题
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(14, 8))
        ctk.CTkLabel(head, text=title, font=f["h1"],
                     text_color=C["accent"]).pack(side="left")
        ctk.CTkLabel(head, text=f"  {len(fields)} 项", font=f["small"],
                     text_color=C["text_faint"]).pack(side="left")

        # 分隔线
        ctk.CTkFrame(card, height=1, fg_color=C["border"]).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 4))

        # 字段
        for i, (_, key, label, typ) in enumerate(fields):
            r = i + 2
            ctk.CTkLabel(card, text=label, font=f["body"],
                         text_color=C["text"], anchor="w").grid(
                row=r, column=0, sticky="w", padx=(20, 12), pady=7)
            self._render_widget(card, r, key, typ)

    def _render_widget(self, card, row, key, typ):
        f = self.f

        if typ == "bool":
            var = ctk.StringVar(value="false")
            ctk.CTkSwitch(card, text="", variable=var,
                          onvalue="true", offvalue="false",
                          progress_color=C["accent"]).grid(
                row=row, column=1, sticky="w", padx=(0, 20), pady=7)
            self._vars[key] = ("bool", var)

        elif typ.startswith("enum:"):
            options = typ.split(":", 1)[1].split(",")
            var = ctk.StringVar(value=options[0])
            ctk.CTkOptionMenu(card, values=options, variable=var,
                              width=200, fg_color=C["console_bg"],
                              button_color=C["accent"],
                              button_hover_color=C["accent_hover"]).grid(
                row=row, column=1, sticky="w", padx=(0, 20), pady=7)
            self._vars[key] = ("enum", var)

        elif typ == "password":
            var = ctk.StringVar()
            ctk.CTkEntry(card, textvariable=var, height=36, corner_radius=9,
                         font=f["body"], fg_color=C["console_bg"],
                         border_color=C["border"], border_width=1,
                         show="•").grid(
                row=row, column=1, sticky="ew", padx=(0, 20), pady=7)
            self._vars[key] = ("password", var)

        else:   # str / int
            var = ctk.StringVar()
            ctk.CTkEntry(card, textvariable=var, height=36, corner_radius=9,
                         font=f["body"], fg_color=C["console_bg"],
                         border_color=C["border"], border_width=1).grid(
                row=row, column=1, sticky="ew", padx=(0, 20), pady=7)
            self._vars[key] = (typ, var)

    # ========================================================
    #  钩子
    # ========================================================
    def on_show(self):
        self.load()

    # ========================================================
    #  读写
    # ========================================================
    def load(self):
        path = self._props_path
        if not path.exists():
            self.status.configure(text="⚠ 未找到 server.properties",
                                  text_color=C["orange"])
            return
        try:
            data = {}
            for line in path.read_text(encoding="utf-8",
                                       errors="replace").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                data[k.strip()] = v.strip()

            for key, (typ, var) in self._vars.items():
                if key not in data:
                    continue
                v = data[key]
                if typ == "bool":
                    var.set("true" if v.lower() == "true" else "false")
                else:
                    var.set(v)

            self.status.configure(text=f"✔ 已加载 {len(data)} 项",
                                  text_color=C["green"])
        except Exception as e:
            self.status.configure(text=f"加载失败：{e}", text_color=C["red"])

    def save(self):
        if self.app.is_running:
            if not messagebox.askyesno(
                "服务器运行中",
                "server.properties 的修改需要重启服务器才能生效。\n\n继续保存吗？"
            ):
                return

        path = self._props_path
        if not path.exists():
            self.app.log_to_console("找不到 server.properties", "error")
            return

        # ---- 类型校验（只校验 int 字段） ----
        for key, (typ, var) in self._vars.items():
            if typ != "int":
                continue
            v = var.get().strip()
            if v == "":
                continue
            try:
                int(v)
            except ValueError:
                messagebox.showerror("参数错误",
                                     f"「{key}」必须是整数，当前值为 {v!r}")
                return

        try:
            # 备份原文件
            bak = path.with_suffix(".properties.bak")
            shutil.copy2(path, bak)

            updates = {k: var.get() for k, (_, var) in self._vars.items()}

            text = path.read_text(encoding="utf-8", errors="replace")
            out, seen = [], set()
            for line in text.splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    out.append(line)
                    continue
                k = s.split("=", 1)[0].strip()
                if k in updates:
                    out.append(f"{k}={updates[k]}")
                    seen.add(k)
                else:
                    out.append(line)

            # 补上原文件中不存在的字段
            for k, v in updates.items():
                if k not in seen:
                    out.append(f"{k}={v}")

            path.write_text("\n".join(out) + "\n", encoding="utf-8")

            self.status.configure(text="✔ 已保存", text_color=C["green"])
            self.app.log_to_console(
                f"server.properties 已保存（备份：{bak.name}）", "ok")

            # ---- RCON 同步 ----
            self._sync_rcon_to_config(updates)

        except Exception as e:
            self.status.configure(text=f"保存失败：{e}", text_color=C["red"])
            self.app.log_to_console(f"保存失败：{e}", "error")

    def _sync_rcon_to_config(self, updates):
        """
        server.properties 里的 rcon.port / rcon.password 与
        server_config.json 是同一份数据的两个副本，保存时保持同步。
        """
        cfg = self.app.config_data
        changed = False

        new_port_raw = updates.get("rcon.port", "").strip()
        if new_port_raw:
            try:
                new_port = int(new_port_raw)
                if new_port != cfg.get("rcon_port"):
                    cfg["rcon_port"] = new_port
                    changed = True
            except ValueError:
                pass

        new_pwd = updates.get("rcon.password", "")
        if new_pwd and new_pwd != cfg.get("rcon_password"):
            cfg["rcon_password"] = new_pwd
            changed = True

        if changed and save_config(cfg):
            self.app.log_to_console(
                "RCON 端口 / 密码已同步到 server_config.json", "ok")