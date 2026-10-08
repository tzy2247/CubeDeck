"""配置读写。"""
import json
from pathlib import Path

CONFIG_PATH = Path("server_config.json")

DEFAULT_CONFIG = {
    "server_path":              r"D:\gaming\Minecraft\server\26.3",
    "java_path":                r"C:\Program Files\Java\jdk-17\bin\java.exe",
    "rcon_password":            "your_password",
    "rcon_port":                25575,
    "memory_xmx":               "4G",
    "memory_xms":               "2G",
    "jvm_args":                 "",
    "auto_backup_enabled":      False,
    "auto_backup_interval_min": 60,
    "auto_backup_keep":         10,
    "auto_restart":             False,
    "keep_server_on_exit":      True,

    # 全局掉落物清理
    "global_clean_enabled":          False,
    "auto_drop_clean_interval_min":  30,

    # ---------- AI 助手 ----------
    "ai_enabled": False,
    "ai_base_url": "https://api.openai.com/v1",
    "ai_api_key": "",
    "ai_model": "gpt-4o-mini",

    "ai_chat_enabled": True,
    "ai_chat_trigger": "!",
    "ai_chat_cooldown": 5,
    "ai_context_lines": 10,

    "ai_moderation_enabled": False,
    "ai_moderation_cooldown": 3,
    "ai_moderation_broadcast": True,
    "ai_global_cooldown": 1.0,

    "ai_system_prompt": (
        "你是 Minecraft 服务器的 AI 助手。你需要：\n"
        "1. 友好、简短地回复玩家的聊天（不超过 50 字）\n"
        "2. 监控玩家行为，发现辱骂、刷屏、广告、作弊讨论时上报\n\n"
        "必须严格返回 JSON 格式（不要有额外文字）：\n"
        "{\n"
        '  "reply": "给玩家的回复，无需回复则为空字符串",\n'
        '  "violation": "none|warn|kick|ban",\n'
        '  "reason": "违规原因，无违规则为空"\n'
        "}"
    ),
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                loaded.setdefault(k, v)
            # 兼容旧字段名
            if ("auto_drop_clean_enabled" in loaded
                    and "global_clean_enabled" not in loaded):
                loaded["global_clean_enabled"] = loaded.pop(
                    "auto_drop_clean_enabled")
            loaded["rcon_port"] = int(str(loaded["rcon_port"]).strip())
            loaded["rcon_password"] = str(loaded["rcon_password"])
            return loaded
        except Exception:
            return dict(DEFAULT_CONFIG)
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> bool:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False