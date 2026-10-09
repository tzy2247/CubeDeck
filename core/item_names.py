"""物品 ID → 中文名称映射，支持原版 + 模组。

用户提供：
  - 单个语言文件路径（兼容老配置）
  - 语言文件目录（推荐，扫描目录下所有 .json）

支持任意命名空间：item.minecraft.diamond_sword → minecraft:diamond_sword
                  item.create.cogwheel        → create:cogwheel
"""
import json
import re
from pathlib import Path

# 用户配置（运行时由 app 注入）
_lang_file_override = None
_lang_dir_override = None

from core import paths

_FALLBACK_CANDIDATES = [
    Path(__file__).parent.parent / "lang" / "zh_cn.json",
    Path(__file__).parent.parent / "assets" / "lang" / "zh_cn.json",
]

# 缓存
_name_cache = None
_items_sorted = None
_loaded_files = []          # 记录实际加载了哪些文件
_load_errors = []           # 加载失败的记录

# 键格式：item.<namespace>.<path> / block.<namespace>.<path> / enchantment.<namespace>.<path>
_KEY_PATTERN = re.compile(r"^(item|block|enchantment)\.([^.]+)\.(.+)$")


# ============================================================
#  外部接口
# ============================================================
def set_lang_file(path):
    """设置单个语言文件路径。"""
    global _lang_file_override
    _lang_file_override = Path(path) if path else None
    _invalidate()


def set_lang_dir(path):
    """设置语言文件目录，扫描其中所有 .json。"""
    global _lang_dir_override
    _lang_dir_override = Path(path) if path else None
    _invalidate()


def set_lang_sources(file_path=None, dir_path=None):
    """一次设置文件 + 目录。"""
    global _lang_file_override, _lang_dir_override
    _lang_file_override = Path(file_path) if file_path else None
    _lang_dir_override = Path(dir_path) if dir_path else None
    _invalidate()


def get_lang_file():
    return _lang_file_override


def get_lang_dir():
    return _lang_dir_override


def loaded_files():
    """返回已成功加载的语言文件列表（去重）。"""
    _load()
    return list(_loaded_files)


def load_errors():
    """返回加载失败的记录 [(path, error), ...]。"""
    _load()
    return list(_load_errors)


def is_loaded() -> bool:
    return len(_load()) > 0


def loaded_count() -> int:
    return len(_load())


def _invalidate():
    global _name_cache, _items_sorted, _loaded_files, _load_errors
    _name_cache = None
    _items_sorted = None
    _loaded_files = []
    _load_errors = []


# ============================================================
#  读取与合并
# ============================================================
def _collect_files():
    """收集所有要加载的语言文件。"""
    files = []
    seen = set()

    def add(p):
        p = Path(p)
        if not p.exists() or not p.is_file():
            return
        try:
            key = str(p.resolve()).lower()
        except Exception:
            key = str(p).lower()
        if key in seen:
            return
        seen.add(key)
        files.append(p)

    # 目录扫描：优先
    if _lang_dir_override and _lang_dir_override.is_dir():
        for p in sorted(_lang_dir_override.rglob("*.json")):
            add(p)

    # 单文件
    if _lang_file_override:
        add(_lang_file_override)

    # 项目内兜底：按优先级遍历
    if not files:
        for cand in _FALLBACK_CANDIDATES:
            if cand.exists():
                add(cand)
                break

    return files


def _load():
    global _name_cache, _loaded_files, _load_errors
    if _name_cache is not None:
        return _name_cache

    _name_cache = {}
    _loaded_files = []
    _load_errors = []

    for path in _collect_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                _load_errors.append((str(path), "不是 JSON 对象"))
                continue

            count = 0
            for key, value in raw.items():
                if not isinstance(value, str):
                    continue
                m = _KEY_PATTERN.match(key)
                if not m:
                    continue
                kind, ns, name_path = m.groups()
                if kind == "enchantment":
                    _name_cache[f"ench_{ns}:{name_path}"] = value
                else:
                    # item 和 block 都存为 "<namespace>:<path>"
                    _name_cache[f"{ns}:{name_path}"] = value
                count += 1

            _loaded_files.append(str(path))
        except Exception as e:
            _load_errors.append((str(path), str(e)))

    return _name_cache


# ============================================================
#  查询
# ============================================================
def get_item_name(item_id: str) -> str:
    """
    'minecraft:diamond_sword' → '钻石剑'
    'create:cogwheel'         → '齿轮'（如果有对应语言文件）
    查不到返回短 ID。
    """
    if not item_id:
        return ""
    if ":" not in item_id:
        item_id = f"minecraft:{item_id}"
    if item_id == "minecraft:air":
        return "空气"

    cache = _load()
    if item_id in cache:
        return cache[item_id]
    # 找不到时返回短名（不含命名空间）
    return item_id.split(":", 1)[-1]


def get_item_id(display_name: str) -> str:
    """反向查找。找不到返回空字符串。"""
    if not display_name:
        return ""
    cache = _load()
    for full_id, name in cache.items():
        if full_id.startswith("ench_"):
            continue
        if name == display_name:
            return full_id
    return ""


def get_all_item_ids():
    """
    返回 [(完整 ID, 中文名), ...]，按中文名排序。
    排除附魔、模板字符串、空名。
    """
    global _items_sorted
    if _items_sorted is not None:
        return _items_sorted

    cache = _load()
    items = []
    for full_id, name in cache.items():
        if full_id.startswith("ench_"):
            continue
        if not name or not name.strip():
            continue
        if "%" in name or "{" in name:
            continue
        items.append((full_id, name))

    items.sort(key=lambda x: (x[1], x[0]))
    _items_sorted = items
    return _items_sorted


def get_enchant_name(ench_id: str) -> str:
    """'minecraft:sharpness' → '锋利'。"""
    if not ench_id:
        return ""
    if ":" not in ench_id:
        ench_id = f"minecraft:{ench_id}"
    cache = _load()
    return cache.get(f"ench_{ench_id}", ench_id.split(":", 1)[-1])