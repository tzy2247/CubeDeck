"""清理区数据模型 + 命令构建。"""
import json
from pathlib import Path

_data_dir = Path(".")


def set_data_dir(d):
    global _data_dir
    _data_dir = Path(d)


def _clean_zones_file():
    return _data_dir / "clean_zones.json"


DIMENSION_CN = {
    "minecraft:overworld": "主世界",
    "minecraft:the_nether": "下界",
    "minecraft:the_end": "末地",
}
DIMENSION_KEYS = list(DIMENSION_CN.keys())


def load_clean_zones():
    path = _clean_zones_file()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "zones" not in data:
                data["zones"] = []
            return data
        except Exception:
            return {"zones": []}
    save_clean_zones({"zones": []})
    return {"zones": []}


def save_clean_zones(data):
    try:
        path = _clean_zones_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False


def normalize_clean_zone(zone):
    x1, x2 = sorted([float(zone["x1"]), float(zone["x2"])])
    y1, y2 = sorted([float(zone["y1"]), float(zone["y2"])])
    z1, z2 = sorted([float(zone["z1"]), float(zone["z2"])])
    return x1, y1, z1, x2, y2, z2


def build_clean_zone_command(zone):
    """为单个清理区生成清理命令（只清该区域内的掉落物）。"""
    try:
        x1, y1, z1, x2, y2, z2 = normalize_clean_zone(zone)
    except Exception:
        return None

    dim = zone.get("dimension", "minecraft:overworld")
    dx = x2 - x1 + 1
    dy = y2 - y1 + 1
    dz = z2 - z1 + 1

    return (
        f"execute in {dim} run kill "
        f"@e[type=item,x={x1:g},y={y1:g},z={z1:g},"
        f"dx={dx:g},dy={dy:g},dz={dz:g}]"
    )