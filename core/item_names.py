"""物品 ID → 中文名称映射。"""
import json
from pathlib import Path

_LANG_FILE = Path(__file__).parent.parent / "data" / "zh_cn.json"
_name_cache = None
_items_sorted = None


def _load():
    global _name_cache
    if _name_cache is not None:
        return _name_cache

    _name_cache = {}
    if not _LANG_FILE.exists():
        return _name_cache

    try:
        with open(_LANG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return _name_cache

    for key, value in raw.items():
        if key.startswith("item.minecraft."):
            _name_cache[key[len("item.minecraft."):]] = value
        elif key.startswith("block.minecraft."):
            _name_cache[key[len("block.minecraft."):]] = value
        elif key.startswith("enchantment.minecraft."):
            _name_cache[f"ench_{key[len('enchantment.minecraft.'):]}"] = value

    return _name_cache


def get_item_name(item_id: str) -> str:
    """'minecraft:diamond_sword' → '钻石剑'。查不到返回短 ID。"""
    if not item_id:
        return ""
    short = item_id.replace("minecraft:", "")
    if short == "air":
        return "空气"
    cache = _load()
    return cache.get(short, short)


def get_item_id(display_name: str) -> str:
    """'钻石剑' → 'minecraft:diamond_sword'。找不到返回空字符串。"""
    if not display_name:
        return ""
    cache = _load()
    for short_id, name in cache.items():
        if short_id.startswith("ench_"):
            continue
        if name == display_name:
            return f"minecraft:{short_id}"
    return ""


def get_all_item_ids():
    """
    返回 [(完整 ID, 中文名), ...]，按中文名排序。
    排除附魔、模板字符串（含 % 或 {）、空名。
    """
    global _items_sorted
    if _items_sorted is not None:
        return _items_sorted

    cache = _load()
    items = []
    for short_id, name in cache.items():
        if short_id.startswith("ench_"):
            continue
        if not name or not name.strip():
            continue
        if "%" in name or "{" in name:
            continue
        items.append((f"minecraft:{short_id}", name))

    items.sort(key=lambda x: x[1])
    _items_sorted = items
    return _items_sorted


def get_enchant_name(ench_id: str) -> str:
    """'minecraft:sharpness' → '锋利'。"""
    if not ench_id:
        return ""
    short = ench_id.replace("minecraft:", "")
    cache = _load()
    return cache.get(f"ench_{short}", short)