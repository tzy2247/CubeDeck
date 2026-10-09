"""仪表盘：状态卡片 + 数据卡片 + 快捷操作 + 双折线图 + 动画。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

from ui_qt.theme import theme
from ui_qt.pages.base import BasePage
from ui_qt.widgets.card import Card
from ui_qt.widgets.line_chart import LineChart


class DashboardPage(BasePage):
    def __init__(self, state, parent=None):
        super().__init__(state, parent)

        # 数字变化阈值缓存
        self._last_tps = 0.0
        self._last_mem = 0.0
        # 动画计数器（延迟初始化）
        self._tps_counter = None
        self._mem_counter = None
        # 首屏入场动画只播一次
        self._entrance_played = False

        self._build()

        # 信号
        state.server_starting.connect(self._on_starting)
        state.server_started.connect(self._on_started)
        state.server_stopping.connect(self._on_stopping)
        state.server_stopped.connect(self._on_stopped)
        state.stats_updated.connect(self._on_stats)

    # ========================================================
    #  构建
    # ========================================================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ---- 状态横幅 ----
        self._banner = Card()
        bl = self._banner.body()
        bl.setContentsMargins(24, 20, 24, 20)

        row = QHBoxLayout()
        row.setSpacing(16)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 22px; "
            f"background: transparent;")
        row.addWidget(self._dot)

        info = QVBoxLayout()
        info.setSpacing(2)
        self._status_title = QLabel("服务器未运行")
        self._status_title.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 16px; font-weight: bold; background: transparent;")
        info.addWidget(self._status_title)

        self._status_sub = QLabel("点击右侧按钮启动服务器")
        self._status_sub.setStyleSheet(
            f"color: {theme.c('text_dim')}; "
            f"font-size: 12px; background: transparent;")
        info.addWidget(self._status_sub)
        row.addLayout(info)
        row.addStretch()

        self._toggle_btn = QPushButton("启动服务器")
        self._toggle_btn.setFixedSize(140, 42)
        self._toggle_btn.clicked.connect(self._toggle_server)
        self._apply_toggle_style("green", "启动服务器")
        row.addWidget(self._toggle_btn)

        bl.addLayout(row)
        root.addWidget(self._banner)

        # ---- 数据卡片 ----
        stats = QHBoxLayout()
        stats.setSpacing(12)
        self._stat_tps = self._stat_card("TPS", "--", "accent")
        self._stat_players = self._stat_card("在线玩家", "0 / 0", "green")
        self._stat_mem = self._stat_card("内存占用", "-- MB", "purple")
        self._stat_uptime = self._stat_card("运行时长", "--:--:--", "orange")
        for w in (self._stat_tps, self._stat_players,
                  self._stat_mem, self._stat_uptime):
            stats.addWidget(w, 1)
        root.addLayout(stats)

        # ---- 快捷操作 ----
        acts = QHBoxLayout()
        acts.setSpacing(10)
        acts.addWidget(self._action_btn("清理掉落物", self.state.clear_drops))
        acts.addWidget(self._action_btn("立即备份", self.state.do_backup))
        acts.addWidget(self._action_btn("重连 RCON",
                                         self.state.manual_reconnect_rcon))
        acts.addStretch()
        root.addLayout(acts)

        # ---- 图表 ----
        charts = QHBoxLayout()
        charts.setSpacing(12)

        self._tps_card = Card(title="TPS 趋势")
        self._tps_chart = LineChart(y_max=20, color_key="accent", y_suffix="")
        self._tps_card.body().addWidget(self._tps_chart)
        charts.addWidget(self._tps_card, 1)

        self._mem_card = Card(title="内存占用")
        self._mem_chart = LineChart(y_max=8192, color_key="purple",
                                     y_suffix=" MB")
        self._mem_card.body().addWidget(self._mem_chart)
        charts.addWidget(self._mem_card, 1)

        root.addLayout(charts, 1)

    def _stat_card(self, title, value, color_key):
        card = Card()
        bl = card.body()
        bl.setContentsMargins(20, 14, 20, 14)
        bl.setSpacing(4)

        head = QLabel(title)
        head.setStyleSheet(
            f"color: {theme.c('text_dim')}; font-size: 12px; "
            f"background: transparent;")
        bl.addWidget(head)

        val = QLabel(value)
        val.setStyleSheet(
            f"color: {theme.c('text')}; "
            f"font-size: 26px; font-weight: bold; "
            f"background: transparent;")
        bl.addWidget(val)

        card._value_label = val
        return card

    def _action_btn(self, text, callback):
        btn = QPushButton(text)
        btn.setObjectName("Ghost")
        btn.setFixedHeight(38)
        btn.clicked.connect(callback)
        return btn

    # ========================================================
    #  按钮状态
    # ========================================================
    def _toggle_server(self):
        if self.state.is_running:
            self.state.stop_server()
        else:
            self.state.start_server()

    def _apply_toggle_style(self, color_key, text):
        self._toggle_btn.setText(text)
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ "
            f"background-color: {theme.c(color_key)}; "
            f"color: #ffffff; border: none; border-radius: 8px; "
            f"font-size: 13px; font-weight: bold; }}"
            f"QPushButton:hover {{ "
            f"background-color: {theme.c(color_key + '_hover')}; }}")

    # ========================================================
    #  服务器事件
    # ========================================================
    def _on_starting(self):
        self._toggle_btn.setEnabled(False)
        self._apply_toggle_style("text_faint", "启动中…")
        self._dot.setStyleSheet(
            f"color: {theme.c('orange')}; font-size: 22px; "
            f"background: transparent;")
        self._status_title.setText("服务器正在启动…")
        self._status_sub.setText("等待服务端就绪")

    def _on_started(self):
        self._toggle_btn.setEnabled(True)
        self._apply_toggle_style("red", "停止服务器")
        self._dot.setStyleSheet(
            f"color: {theme.c('green')}; font-size: 22px; "
            f"background: transparent;")
        self._status_title.setText("服务器运行中")
        self._status_sub.setText("进程已启动，正在监听日志…")

    def _on_stopping(self):
        self._toggle_btn.setEnabled(False)
        self._apply_toggle_style("text_faint", "停止中…")
        self._dot.setStyleSheet(
            f"color: {theme.c('orange')}; font-size: 22px; "
            f"background: transparent;")
        self._status_title.setText("服务器正在停止…")
        self._status_sub.setText("正在保存世界并关闭进程…")

    def _on_stopped(self):
        self._toggle_btn.setEnabled(True)
        self._apply_toggle_style("green", "启动服务器")
        self._dot.setStyleSheet(
            f"color: {theme.c('text_faint')}; font-size: 22px; "
            f"background: transparent;")
        self._status_title.setText("服务器未运行")
        self._status_sub.setText("点击右侧按钮启动服务器")

        self._stat_tps._value_label.setText("--")
        self._stat_players._value_label.setText("0 / 0")
        self._stat_mem._value_label.setText("-- MB")
        self._stat_uptime._value_label.setText("--:--:--")
        self._tps_chart.clear()
        self._mem_chart.clear()

        # 重置计数器阈值
        self._last_tps = 0.0
        self._last_mem = 0.0

    # ========================================================
    #  数据更新
    # ========================================================
    def _on_stats(self, stats):
        """服务器状态每 2 秒推送一次。"""
        # ---- TPS：变化超过 0.3 才做数字动画 ----
        if "tps" in stats:
            val = stats["tps"]
            label = self._stat_tps._value_label
            if abs(val - self._last_tps) > 0.3:
                try:
                    from ui_qt.widgets.animations import NumberCounter
                    if self._tps_counter is None:
                        self._tps_counter = NumberCounter(label, duration=350)
                    self._tps_counter.animate_to(val, fmt="{:.1f}")
                except Exception:
                    label.setText(f"{val:.1f}")
            else:
                label.setText(f"{val:.1f}")
            self._last_tps = val
            self._tps_chart.push(val)

        # ---- 内存：变化超过 30MB 才做数字动画 ----
        if "mem" in stats:
            mem = stats["mem"]
            label = self._stat_mem._value_label
            if abs(mem - self._last_mem) > 30:
                try:
                    from ui_qt.widgets.animations import NumberCounter
                    if self._mem_counter is None:
                        self._mem_counter = NumberCounter(label, duration=350)
                    self._mem_counter.animate_to(mem, fmt="{:,.0f}",
                                                  suffix=" MB")
                except Exception:
                    label.setText(f"{mem:,.0f} MB")
            else:
                label.setText(f"{mem:,.0f} MB")
            self._last_mem = mem
            self._mem_chart.push(mem)

        # ---- 玩家数：直接设置（数字跳动更自然） ----
        if "players" in stats:
            self._stat_players._value_label.setText(stats["players"])

        # ---- 运行时长 ----
        if "uptime" in stats:
            e = stats["uptime"]
            h, r = divmod(e, 3600)
            m, s = divmod(r, 60)
            self._stat_uptime._value_label.setText(
                f"{h:02d}:{m:02d}:{s:02d}")

    # ========================================================
    #  生命周期
    # ========================================================
    def on_show(self):
        """首次显示时触发卡片错开入场动画。"""
        if self._entrance_played:
            return
        self._entrance_played = True

        try:
            from ui_qt.widgets.animations import stagger_appear
            cards = [
                self._banner,
                self._stat_tps,
                self._stat_players,
                self._stat_mem,
                self._stat_uptime,
                self._tps_card,
                self._mem_card,
            ]
            # 延迟 50ms 让布局完成
            stagger_appear(cards, direction="up", distance=16,
                           duration=300, step=55, initial_delay=50)
        except Exception:
            pass

    def on_server_started(self):
        self._on_started()

    def on_server_stopped(self):
        self._on_stopped()