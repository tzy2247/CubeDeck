"""AI 对话历史的持久化。"""
import json
import threading
from pathlib import Path

HISTORY_FILE = Path("ai_chat_history.json")
MAX_ENTRIES = 5000


class AIHistory:
    def __init__(self, path=HISTORY_FILE, max_entries=MAX_ENTRIES):
        self.path = Path(path)
        self.max_entries = max_entries
        self._entries = []
        self._lock = threading.Lock()
        self._load()

    # ---------- 读写 ----------
    def _load(self):
        if not self.path.exists():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._entries = list(data.get("entries", []))
            elif isinstance(data, list):
                self._entries = list(data)
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries:]
        except Exception:
            self._entries = []

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({
                    "version": 1,
                    "entries": self._entries,
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- 公开接口 ----------
    def append(self, entry: dict):
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries:]
            self._save()

    def recent(self, n=200):
        with self._lock:
            return list(self._entries[-n:])

    def all(self):
        with self._lock:
            return list(self._entries)

    def clear(self):
        with self._lock:
            self._entries = []
            self._save()

    def export(self, path) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def __len__(self):
        with self._lock:
            return len(self._entries)