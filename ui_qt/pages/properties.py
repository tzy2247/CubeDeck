"""服务器属性：一般模式只显示常用项，专家模式显示全部。"""
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QLineEdit,
    QCheckBox, QComboBox, QScrollArea, QWidget, QMessageBox, QFrame,
)

from ui_qt.theme import theme
from ui_qt.pages.base import BasePage
from ui_qt.widgets.card import Card


LABEL_WIDTH = 130


# ============================================================
#  字段定义
#  (key, 中文标签, 类型)
# ============================================================
PROP_FIELDS = {
    "基础": [
        ("motd", "服务器标语", "str"),
        ("server-ip", "绑定 IP", "str"),
        ("server-port", "服务器端口", "int"),
        ("max-players", "最大玩家数", "int"),
        ("online-mode", "正版验证", "bool"),
        ("white-list", "启用白名单", "bool"),
        ("enforce-whitelist", "强制白名单", "bool"),
        ("hide-online-players", "隐藏在线玩家列表", "bool"),
        ("accepts-transfers", "接受跨服转移", "bool"),
    ],
    "游戏玩法": [
        ("difficulty", "难度", "enum:peaceful,easy,normal,hard"),
        ("gamemode", "默认游戏模式",
         "enum:survival,creative,adventure,spectator"),
        ("force-gamemode", "强制游戏模式", "bool"),
        ("hardcore", "极限模式", "bool"),
        ("pvp", "允许 PVP", "bool"),
        ("allow-flight", "允许飞行", "bool"),
        ("allow-nether", "允许下界", "bool"),
        ("generate-structures", "生成结构", "bool"),
        ("spawn-protection", "出生点保护半径", "int"),
        ("level-name", "世界名称", "str"),
        ("level-seed", "世界种子", "str"),
        ("level-type", "世界类型（如 minecraft:normal）", "str"),
        ("max-world-size", "世界边界最大值", "int"),
        ("player-idle-timeout", "挂机踢出（分钟，0=禁用）", "int"),
        ("pause-when-empty-seconds", "空服暂停（秒，0=禁用）", "int"),
    ],
    "性能": [
        ("view-distance", "视距（区块）", "int"),
        ("simulation-distance", "模拟距离（区块）", "int"),
        ("max-tick-time", "最大 tick 时间（ms）", "int"),
        ("entity-broadcast-range-percentage", "实体广播范围（%）", "int"),
        ("max-chained-neighbor-updates", "链式方块更新上限", "int"),
        ("network-compression-threshold", "网络压缩阈值", "int"),
        ("sync-chunk-writes", "同步区块写入", "bool"),
        ("use-native-transport", "使用原生传输", "bool"),
        ("region-file-compression", "区域文件压缩",
         "enum:deflate,lz4,none"),
        ("rate-limit", "数据包速率限制", "int"),
        ("status-heartbeat-interval", "状态心跳间隔（ms）", "int"),
    ],
    "聊天 / 消息": [
        ("broadcast-console-to-ops", "向 OP 广播控制台指令", "bool"),
        ("broadcast-rcon-to-ops", "向 OP 广播 RCON 指令", "bool"),
        ("chat-spam-threshold-seconds", "聊天刷屏阈值（秒）", "int"),
        ("command-spam-threshold-seconds", "指令刷屏阈值（秒）", "int"),
        ("enforce-secure-profile", "强制安全聊天签名", "bool"),
        ("log-ips", "记录玩家 IP", "bool"),
        ("enable-code-of-conduct", "启用行为准则", "bool"),
        ("text-filtering-config", "文本过滤配置", "str"),
        ("text-filtering-version", "文本过滤版本", "int"),
    ],
    "RCON / 查询": [
        ("enable-rcon", "启用 RCON", "bool"),
        ("rcon.port", "RCON 端口", "int"),
        ("rcon.password", "RCON 密码", "password"),
        ("enable-query", "启用 Query", "bool"),
        ("query.port", "Query 端口", "int"),
        ("enable-status", "响应服务器列表状态", "bool"),
        ("enable-jmx-monitoring", "启用 JMX 监控", "bool"),
        ("prevent-proxy-connections", "阻止代理连接", "bool"),
    ],
    "权限": [
        ("op-permission-level", "OP 权限等级（1-4）", "int"),
        ("function-permission-level", "函数权限等级（1-4）", "int"),
    ],
    "资源包": [
        ("require-resource-pack", "强制资源包", "bool"),
        ("resource-pack", "资源包 URL", "str"),
        ("resource-pack-id", "资源包 ID", "str"),
        ("resource-pack-prompt", "资源包提示文本", "str"),
        ("resource-pack-sha1", "资源包 SHA1", "str"),
    ],
    "高级": [
        ("initial-enabled-packs", "初始启用数据包", "str"),
        ("initial-disabled-packs", "初始禁用数据包", "str"),
        ("generator-settings", "生成器设置（JSON）", "str"),
        ("bug-report-link", "Bug 报告链接", "str"),
        ("management-server-enabled", "启用管理服务器", "bool"),
        ("management-server-host", "管理服务器主机", "str"),
        ("management-server-port", "管理服务器端口（0=随机）", "int"),
        ("management-server-secret", "管理服务器密钥", "password"),
        ("management-server-tls-enabled", "管理服务器启用 TLS", "bool"),
        ("management-server-allowed-origins", "管理服务器允许的来源", "str"),
    ],
}


# ============================================================
#  常用字段集合（一般模式下显示）
# ============================================================
COMMON_KEYS = {
    # 基础
    "motd", "server-port", "max-players", "online-mode",
    "white-list", "enforce-whitelist",
    # 游戏玩法
    "difficulty", "gamemode", "pvp", "allow-flight",
    "spawn-protection", "level-name", "level-seed",
    # 性能
    "view-distance", "simulation-distance",
    # RCON
    "enable-rcon", "rcon.port", "rcon.password",
}


class PropertiesPage(BasePage):
    def __init__(self, state, parent=None):
        super().__init__(state, parent)

        # 完整数据（无论显示哪些字段，内存里都保存全量）
        self._all_data = {}

        # 当前渲染的 widget：key -> (typ, widget)
        self._vars = {}

        # 是否专家模式
        self._expert_mode = False

        self._build()
        self.load()

    @property
    def _props_path(self):
        return self.state.server_path / "server.properties"

    # ========================================================
    #  构建
    # ========================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ---- 顶部按钮栏 ----
        top = Card()
        tl = top.body()
        tl.setContentsMargins(20, 12, 20, 12)
        tr = QHBoxLayout()
        tr.setSpacing(10)

        save_btn = QPushButton("保存")
        save_btn.setObjectName("Accent")
        save_btn.setFixedHeight(36)
        save_btn.clicked.connect(self.save)
        tr.addWidget(save_btn)

        reload_btn = QPushButton("重新加载")
        reload_btn.setObjectName("Ghost")
        reload_btn.setFixedHeight(36)
        reload_btn.clicked.connect(self.load)
        tr.addWidget(reload_btn)

        tr.addStretch()

        # 专家模式开关
        self._expert_cb = QCheckBox("专家模式")
        self._expert_cb.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 13px; "
            f"background: transparent;")
        self._expert_cb.stateChanged.connect(self._on_expert_toggle)
        tr.addWidget(self._expert_cb)

        self._mode_hint = QLabel("一般模式 · 显示常用项")
        self._mode_hint.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 11px; "
            f"background: transparent; padding-left: 8px;")
        tr.addWidget(self._mode_hint)

        self._status = QLabel("")
        self._status.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 11px; "
            f"background: transparent; padding-left: 8px;")
        tr.addWidget(self._status)

        tl.addLayout(tr)
        root.addWidget(top)

        # ---- 滚动区 ----
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)

        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 8, 0)
        self._body_layout.setSpacing(12)

        self._scroll.setWidget(self._body)
        root.addWidget(self._scroll, 1)

    # ========================================================
    #  渲染卡片（按模式过滤字段）
    # ========================================================
    def _render_cards(self):
        # 清空
        self._vars.clear()
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # 遍历分组
        for group, fields in PROP_FIELDS.items():
            # 按模式过滤
            visible_fields = []
            for key, label, typ in fields:
                if self._expert_mode:
                    visible_fields.append((key, label, typ))
                else:
                    if key in COMMON_KEYS:
                        visible_fields.append((key, label, typ))

            if not visible_fields:
                continue

            card = Card(title=group)
            card_body = card.body()
            for key, label, typ in visible_fields:
                self._make_field(card_body, key, label, typ)
            self._body_layout.addWidget(card)

        self._body_layout.addStretch()

        # 从内存数据初始化 widget
        self._apply_data()

    # ========================================================
    #  表单组件
    # ========================================================
    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setFixedWidth(LABEL_WIDTH)
        lbl.setStyleSheet(
            f"color: {theme.c('text')}; font-size: 13px; "
            f"background: transparent;")
        return lbl

    def _make_field(self, parent, key, label, typ):
        if typ == "bool":
            cb = QCheckBox(label)
            cb.setStyleSheet(
                f"color: {theme.c('text')}; font-size: 13px; "
                f"background: transparent;")
            parent.addWidget(cb)
            self._vars[key] = ("bool", cb)
            return

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self._make_label(label))

        if typ.startswith("enum:"):
            widget = QComboBox()
            for opt in typ.split(":", 1)[1].split(","):
                widget.addItem(opt)
            widget.setFixedHeight(34)
            self._vars[key] = ("enum", widget)

        elif typ == "password":
            widget = QLineEdit()
            widget.setEchoMode(QLineEdit.Password)
            widget.setFixedHeight(34)
            self._vars[key] = ("password", widget)

        else:
            widget = QLineEdit()
            widget.setFixedHeight(34)
            self._vars[key] = (typ, widget)

        row.addWidget(widget, 1)
        parent.addLayout(row)

    # ========================================================
    #  模式切换
    # ========================================================
    def _on_expert_toggle(self, state_int):
        # 切换前把当前 widget 的值收集回内存
        self._collect_from_widgets()

        self._expert_mode = bool(state_int)

        if self._expert_mode:
            self._mode_hint.setText("专家模式 · 显示全部")
        else:
            self._mode_hint.setText("一般模式 · 显示常用项")

        self._render_cards()

    def _collect_from_widgets(self):
        """把当前所有 widget 的值收集到 self._all_data。"""
        for key, (typ, widget) in self._vars.items():
            try:
                if typ == "bool":
                    self._all_data[key] = (
                        "true" if widget.isChecked() else "false")
                elif typ == "enum":
                    self._all_data[key] = widget.currentText()
                else:
                    self._all_data[key] = widget.text()
            except Exception:
                pass

    def _apply_data(self):
        """用 self._all_data 的值初始化 widget。"""
        for key, (typ, widget) in self._vars.items():
            if key not in self._all_data:
                continue
            v = self._all_data[key]
            try:
                if typ == "bool":
                    widget.setChecked(str(v).lower() == "true")
                elif typ == "enum":
                    idx = widget.findText(str(v))
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                else:
                    widget.setText(str(v))
            except Exception:
                pass

    # ========================================================
    #  读写
    # ========================================================
    def load(self):
        path = self._props_path
        if not path.exists():
            self._status.setText("未找到 server.properties")
            self._status.setStyleSheet(
                f"color: {theme.c('orange')}; font-size: 11px; "
                f"background: transparent; padding-left: 8px;")
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

            self._all_data = data
            self._render_cards()

            self._status.setText(f"已加载 {len(data)} 项")
            self._status.setStyleSheet(
                f"color: {theme.c('green')}; font-size: 11px; "
                f"background: transparent; padding-left: 8px;")
        except Exception as e:
            self._status.setText(f"加载失败：{e}")
            self._status.setStyleSheet(
                f"color: {theme.c('red')}; font-size: 11px; "
                f"background: transparent; padding-left: 8px;")

    def save(self):
        if self.state.is_running:
            reply = QMessageBox.question(
                self, "服务器运行中",
                "修改需要重启服务器才能生效。\n\n继续保存吗？")
            if reply != QMessageBox.Yes:
                return

        path = self._props_path
        if not path.exists():
            QMessageBox.critical(self, "错误", "找不到 server.properties")
            return

        # 收集 widget 的值
        self._collect_from_widgets()

        # 校验整数
        for key, (typ, widget) in self._vars.items():
            if typ != "int":
                continue
            v = widget.text().strip()
            if v == "":
                continue
            try:
                int(v)
            except ValueError:
                QMessageBox.critical(
                    self, "参数错误", f"「{key}」必须是整数")
                return

        # 只保存当前模式下渲染的字段（其他字段保持原值）
        updates = {}
        for key in self._vars.keys():
            if key in self._all_data:
                updates[key] = self._all_data[key]

        try:
            bak = path.with_suffix(".properties.bak")
            shutil.copy2(path, bak)

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

            # 专家模式下补上原文件缺失的字段
            if self._expert_mode:
                for k, v in updates.items():
                    if k not in seen:
                        out.append(f"{k}={v}")

            path.write_text("\n".join(out) + "\n", encoding="utf-8")

            self._status.setText("已保存")
            self._status.setStyleSheet(
                f"color: {theme.c('green')}; font-size: 11px; "
                f"background: transparent; padding-left: 8px;")
            self.state.log("server.properties 已保存", "ok")

            self._sync_rcon(updates)
        except Exception as e:
            self._status.setText(f"保存失败：{e}")
            self._status.setStyleSheet(
                f"color: {theme.c('red')}; font-size: 11px; "
                f"background: transparent; padding-left: 8px;")
            self.state.log(f"保存失败：{e}", "error")

    def _sync_rcon(self, updates):
        cfg = self.state.config_data
        changed = False

        port_raw = updates.get("rcon.port", "")
        try:
            new_port = int(port_raw)
            if new_port != cfg.get("rcon_port"):
                cfg["rcon_port"] = new_port
                changed = True
        except (ValueError, TypeError):
            pass

        new_pwd = updates.get("rcon.password", "")
        if new_pwd and new_pwd != cfg.get("rcon_password"):
            cfg["rcon_password"] = new_pwd
            changed = True

        if changed:
            self.state.save_config()
            self.state.log("RCON 端口/密码已同步到配置", "ok")

    def on_show(self):
        self.load()