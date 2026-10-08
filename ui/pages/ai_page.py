"""AI 助手页：配置、对话、审核、人设。"""
import threading
import time
from tkinter import messagebox

import customtkinter as ctk

from core.theme import C
from core.config import save_config
from core.ai_client import AIClient


class AIPage:
    def __init__(self, parent, app):
        self.app = app
        self.f = app.fonts
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self._build()

    # ========================================================
    #  构建
    # ========================================================
    def _build(self):
        f = self.f
        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_rowconfigure(1, weight=1)

        # ---------- 顶部：状态 + 总开关 ----------
        top = ctk.CTkFrame(self.frame, fg_color=C["card"], corner_radius=14,
                           border_width=1, border_color=C["border"])
        top.grid(row=0, column=0, sticky="ew", pady=(0, 12))

        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(14, 8))
        ctk.CTkLabel(row, text="🤖   AI 助手", font=f["h1"],
                     text_color=C["text"]).pack(side="left")

        self.enable_var = ctk.StringVar(
            value="true" if self.app.config_data.get("ai_enabled") else "false")
        ctk.CTkSwitch(row, text="启用 AI", variable=self.enable_var,
                      onvalue="true", offvalue="false",
                      progress_color=C["accent"], font=f["body"],
                      command=self._toggle_enable).pack(side="right")

        self.status_label = ctk.CTkLabel(top, text="", font=f["small"],
                                         text_color=C["text_dim"], anchor="w")
        self.status_label.pack(anchor="w", padx=18, pady=(0, 14))

        # ---------- 标签页 ----------
        tabs = ctk.CTkTabview(
            self.frame, fg_color=C["card"],
            segmented_button_fg_color=C["sidebar"],
            segmented_button_selected_color=C["accent"],
            segmented_button_selected_hover_color=C["accent_hover"],
            segmented_button_unselected_color=C["sidebar"],
            text_color=C["text"], corner_radius=14,
            border_width=1, border_color=C["border"],
        )
        tabs.grid(row=1, column=0, sticky="nsew")

        self._build_config_tab(tabs.add("⚙  API 配置"))
        self._build_chat_tab(tabs.add("💬 对话设置"))
        self._build_mod_tab(tabs.add("🛡 行为审核"))
        self._build_prompt_tab(tabs.add("📝 人设"))
        self._build_log_tab(tabs.add("📋 对话记录"))

        self._refresh_status()

    # ---------- API 配置 ----------
    def _build_config_tab(self, parent):
        f = self.f
        card = ctk.CTkFrame(parent, fg_color=C["console_bg"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        card.pack(fill="x", padx=12, pady=12)

        ctk.CTkLabel(card, text="OpenAI 兼容接口",
                     font=f["h2"], text_color=C["accent"]
                     ).pack(anchor="w", padx=16, pady=(12, 8))

        self.base_url_entry = self._entry_row(
            card, "API 网址", self.app.config_data.get("ai_base_url", ""),
            placeholder="https://api.openai.com/v1")
        self.api_key_entry = self._entry_row(
            card, "API Key", self.app.config_data.get("ai_api_key", ""),
            show="•", placeholder="sk-...")
        self.model_entry = self._entry_row(
            card, "模型", self.app.config_data.get("ai_model", ""),
            placeholder="gpt-4o-mini / qwen-plus / deepseek-chat …")

        quick = ctk.CTkFrame(card, fg_color="transparent")
        quick.pack(fill="x", padx=16, pady=(4, 12))
        ctk.CTkLabel(quick, text="快速填充", font=f["small"],
                     text_color=C["text_dim"]).pack(side="left", padx=(0, 8))

        presets = [
            ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini"),
            ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat"),
            ("通义千问",
             "https://dashscope.aliyuncs.com/compatible-mode/v1",
             "qwen-plus"),
            ("智谱 GLM", "https://open.bigmodel.cn/api/paas/v4",
             "glm-4-flash"),
            ("Moonshot", "https://api.moonshot.cn/v1", "moonshot-v1-8k"),
        ]
        for name, url, model in presets:
            ctk.CTkButton(
                quick, text=name, width=80, height=28, corner_radius=7,
                font=f["small"], fg_color="transparent",
                hover_color=C["card_hover"], border_width=1,
                border_color=C["border"], text_color=C["text_dim"],
                command=lambda u=url, m=model: self._apply_preset(u, m),
            ).pack(side="left", padx=2)

        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.pack(fill="x", padx=12, pady=(0, 12))

        ctk.CTkButton(btns, text="💾  保存配置", width=130, height=38,
                      corner_radius=10, font=f["h2"],
                      fg_color=C["accent"], hover_color=C["accent_hover"],
                      command=self._save_config).pack(side="left")

        ctk.CTkButton(btns, text="🔌  测试连接", width=130, height=38,
                      corner_radius=10, font=f["h2"],
                      fg_color=C["green"], hover_color=C["green_hover"],
                      command=self._test_connection).pack(side="left", padx=(10, 0))

        self.test_result = ctk.CTkLabel(btns, text="", font=f["small"],
                                        text_color=C["text_dim"])
        self.test_result.pack(side="left", padx=(12, 0))

    def _entry_row(self, parent, label, value, show=None, placeholder=""):
        f = self.f
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(row, text=label, font=f["body"], text_color=C["text"],
                     width=90, anchor="w").pack(side="left")
        e = ctk.CTkEntry(row, height=36, corner_radius=8, font=f["body"],
                         fg_color=C["bg"], border_color=C["border"],
                         border_width=1, show=show,
                         placeholder_text=placeholder)
        e.pack(side="left", fill="x", expand=True, padx=(8, 0))
        e.insert(0, str(value))
        return e

    def _apply_preset(self, url, model):
        self.base_url_entry.delete(0, "end")
        self.base_url_entry.insert(0, url)
        self.model_entry.delete(0, "end")
        self.model_entry.insert(0, model)

    # ---------- 对话设置 ----------
    def _build_chat_tab(self, parent):
        f = self.f
        card = ctk.CTkFrame(parent, fg_color=C["console_bg"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        card.pack(fill="x", padx=12, pady=12)

        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(r1, text="允许 AI 回复玩家聊天", font=f["body"],
                     text_color=C["text"], anchor="w").pack(side="left")
        self.chat_enabled_var = ctk.StringVar(
            value="true" if self.app.config_data.get("ai_chat_enabled")
            else "false")
        ctk.CTkSwitch(r1, text="", variable=self.chat_enabled_var,
                      onvalue="true", offvalue="false",
                      progress_color=C["accent"]).pack(side="right")

        self.trigger_entry = self._entry_row(
            card, "触发前缀",
            self.app.config_data.get("ai_chat_trigger", "!"),
            placeholder="留空 = 回复所有消息")
        self.cooldown_entry = self._entry_row(
            card, "冷却（秒）",
            self.app.config_data.get("ai_chat_cooldown", 5))
        self.ctx_entry = self._entry_row(
            card, "上下文条数",
            self.app.config_data.get("ai_context_lines", 10))

        ctk.CTkLabel(
            card,
            text="💡 触发前缀为 `!` 时，玩家输入 `!你好` → AI 回复。\n"
                 "   留空则 AI 回复所有玩家聊天（成本较高，慎用）。",
            font=f["small"], text_color=C["text_faint"],
            justify="left",
        ).pack(anchor="w", padx=16, pady=(4, 14))

        ctk.CTkButton(parent, text="💾  保存", width=100, height=36,
                      corner_radius=10, font=f["h2"],
                      fg_color=C["accent"], hover_color=C["accent_hover"],
                      command=self._save_config).pack(pady=(0, 12))

    # ---------- 行为审核 ----------
    def _build_mod_tab(self, parent):
        f = self.f
        card = ctk.CTkFrame(parent, fg_color=C["console_bg"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        card.pack(fill="x", padx=12, pady=12)

        r1 = ctk.CTkFrame(card, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(r1, text="启用玩家行为审核", font=f["body"],
                     text_color=C["text"], anchor="w").pack(side="left")
        self.mod_enabled_var = ctk.StringVar(
            value="true" if self.app.config_data.get("ai_moderation_enabled")
            else "false")
        ctk.CTkSwitch(r1, text="", variable=self.mod_enabled_var,
                      onvalue="true", offvalue="false",
                      progress_color=C["accent"]).pack(side="right")

        r2 = ctk.CTkFrame(card, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(r2, text="违规时广播处理结果", font=f["body"],
                     text_color=C["text"], anchor="w").pack(side="left")
        self.mod_bc_var = ctk.StringVar(
            value="true" if self.app.config_data.get(
                "ai_moderation_broadcast", True) else "false")
        ctk.CTkSwitch(r2, text="", variable=self.mod_bc_var,
                      onvalue="true", offvalue="false",
                      progress_color=C["accent"]).pack(side="right")

        self.mod_cd_entry = self._entry_row(
            card, "审核冷却（秒）",
            self.app.config_data.get("ai_moderation_cooldown", 3))
        self.global_cd_entry = self._entry_row(
            card, "全局冷却（秒）",
            self.app.config_data.get("ai_global_cooldown", 1.0),
            placeholder="0 = 关闭全局冷却")

        ctk.CTkLabel(
            card,
            text=("💡 AI 对每条玩家消息进行违规检测。\n"
                  "   违规等级由 AI 决定：none / warn / kick / ban。\n"
                  "   全局冷却是所有玩家共享，防止瞬间刷爆 API。\n"
                  "   ⚠ 审核会产生 API 费用，冷却越短成本越高。"),
            font=f["small"], text_color=C["text_faint"],
            justify="left",
        ).pack(anchor="w", padx=16, pady=(4, 14))

        ctk.CTkButton(parent, text="💾  保存", width=100, height=36,
                      corner_radius=10, font=f["h2"],
                      fg_color=C["accent"], hover_color=C["accent_hover"],
                      command=self._save_config).pack(pady=(0, 12))

    # ---------- 人设 ----------
    def _build_prompt_tab(self, parent):
        f = self.f
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            parent,
            text="系统提示词：告诉 AI 它的角色、语气、行为准则。\n"
                 "必须要求 AI 返回 JSON（reply / violation / reason），"
                 "否则解析会失败。",
            font=f["small"], text_color=C["text_dim"], justify="left",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 6))

        self.prompt_box = ctk.CTkTextbox(
            parent, fg_color=C["console_bg"], corner_radius=12,
            border_width=1, border_color=C["border"],
            font=f["mono"], wrap="word", text_color=C["text"],
        )
        self.prompt_box.grid(row=1, column=0, sticky="nsew",
                             padx=12, pady=(0, 8))
        self.prompt_box.insert(
            "1.0", self.app.config_data.get("ai_system_prompt", ""))

        # 底部按钮区用 grid（与上面保持一致）
        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

        ctk.CTkButton(btns, text="💾  保存人设", width=120, height=36,
                      corner_radius=10, font=f["h2"],
                      fg_color=C["accent"], hover_color=C["accent_hover"],
                      command=self._save_config).pack(side="left")

        ctk.CTkButton(btns, text="↺  恢复默认", width=120, height=36,
                      corner_radius=10, font=f["body"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=self._reset_prompt).pack(side="left", padx=(10, 0))

    # ---------- 对话记录 ----------
    def _build_log_tab(self, parent):
        f = self.f
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        self.chat_box = ctk.CTkTextbox(
            parent, fg_color=C["console_bg"], corner_radius=12,
            border_width=1, border_color=C["border"],
            font=f["mono"], wrap="word", text_color=C["text"],
        )
        self.chat_box.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        try:
            tw = getattr(self.chat_box, "_textbox", None) or self.chat_box
            tw.tag_config("player", foreground="#7dd3fc")
            tw.tag_config("ai", foreground="#4ade80")
            tw.tag_config("mod", foreground="#fbbf24")
            tw.tag_config("err", foreground="#f87171")
        except Exception:
            pass

        btns = ctk.CTkFrame(parent, fg_color="transparent")
        btns.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))

        ctk.CTkButton(btns, text="🗑  清空记录", width=120, height=32,
                      corner_radius=8, font=f["body"],
                      fg_color="transparent", hover_color=C["card_hover"],
                      border_width=1, border_color=C["border"],
                      text_color=C["text_dim"],
                      command=self._clear_log).pack(side="left")

    # ========================================================
    #  生命周期
    # ========================================================
    def on_show(self):
        self._refresh_status()

    def _refresh_status(self):
        enabled = self.app.config_data.get("ai_enabled")
        last = getattr(self.app, "_last_ai_call_time", 0)
        count = len(getattr(self.app, "ai_chat_history", []))
        if enabled:
            text = (f"🟢 已启用   ·   最近调用：{self._fmt_time(last)}"
                    f"   ·   对话数：{count}")
            color = C["green"]
        else:
            text = "⚪ 未启用"
            color = C["text_faint"]
        try:
            self.status_label.configure(text=text, text_color=color)
        except Exception:
            pass

    @staticmethod
    def _fmt_time(ts):
        if not ts:
            return "—"
        return time.strftime("%H:%M:%S", time.localtime(ts))

    # ========================================================
    #  操作
    # ========================================================
    def _toggle_enable(self):
        self.app.config_data["ai_enabled"] = self.enable_var.get() == "true"
        if save_config(self.app.config_data):
            state = "开启" if self.app.config_data["ai_enabled"] else "关闭"
            self.app.log_to_console(f"AI 助手已{state}", "ok")
            self._refresh_status()

    def _save_config(self):
        cfg = self.app.config_data
        try:
            cooldown = int(self.cooldown_entry.get().strip() or 5)
            ctx = int(self.ctx_entry.get().strip() or 10)
            mod_cd = int(self.mod_cd_entry.get().strip() or 3)
            global_cd = float(self.global_cd_entry.get().strip() or 1.0)
            if global_cd < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "参数错误", "冷却/上下文必须是数字，且全局冷却 ≥ 0")
            return

        cfg["ai_base_url"] = self.base_url_entry.get().strip()
        cfg["ai_api_key"] = self.api_key_entry.get().strip()
        cfg["ai_model"] = self.model_entry.get().strip()
        cfg["ai_chat_enabled"] = self.chat_enabled_var.get() == "true"
        cfg["ai_chat_trigger"] = self.trigger_entry.get().strip()
        cfg["ai_chat_cooldown"] = cooldown
        cfg["ai_context_lines"] = ctx
        cfg["ai_moderation_enabled"] = self.mod_enabled_var.get() == "true"
        cfg["ai_moderation_broadcast"] = self.mod_bc_var.get() == "true"
        cfg["ai_moderation_cooldown"] = mod_cd
        cfg["ai_global_cooldown"] = global_cd
        cfg["ai_system_prompt"] = self.prompt_box.get("1.0", "end").strip()
        cfg["ai_enabled"] = self.enable_var.get() == "true"

        if save_config(cfg):
            self.app.log_to_console("AI 配置已保存", "ok")
            self.test_result.configure(text="✔ 已保存", text_color=C["green"])
            self._refresh_status()

    def _test_connection(self):
        self.test_result.configure(text="测试中…", text_color=C["text_dim"])

        def worker():
            client = AIClient(
                self.base_url_entry.get().strip(),
                self.api_key_entry.get().strip(),
                self.model_entry.get().strip(),
                timeout=15,
            )
            ok, msg = client.test_connection()
            color = C["green"] if ok else C["red"]
            self.app.ui(self.test_result.configure, text=msg, text_color=color)

        threading.Thread(target=worker, daemon=True).start()

    def _reset_prompt(self):
        from core.config import DEFAULT_CONFIG
        default = DEFAULT_CONFIG.get("ai_system_prompt", "")
        self.prompt_box.delete("1.0", "end")
        self.prompt_box.insert("1.0", default)

    def _clear_log(self):
        self.chat_box.delete("1.0", "end")

    # ========================================================
    #  外部调用
    # ========================================================
    def append_chat(self, player, message, reply, action, reason=""):
        def do():
            try:
                ts = time.strftime("%H:%M:%S")
                self.chat_box.insert("end", f"[{ts}] ", "player")
                self.chat_box.insert("end",
                                     f"<{player}> {message}\n", "player")
                if reply:
                    self.chat_box.insert("end",
                                         f"        🤖 {reply}\n", "ai")
                if action and action != "none":
                    self.chat_box.insert(
                        "end",
                        f"        ⚠ 审核：{action}  ({reason})\n", "mod")
                self.chat_box.see("end")

                total = int(self.chat_box.index("end-1c").split(".")[0])
                if total > 600:
                    self.chat_box.delete("1.0", f"{total - 600}.0")
            except Exception:
                pass
        self.app.ui(do)

    def append_error(self, msg):
        def do():
            try:
                ts = time.strftime("%H:%M:%S")
                self.chat_box.insert("end", f"[{ts}] ❌ {msg}\n", "err")
                self.chat_box.see("end")
            except Exception:
                pass
        self.app.ui(do)