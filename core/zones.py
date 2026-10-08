"""保护区数据模型 + 清理命令构建。"""
import json
from pathlib import Path

ZONES_FILE = Path("protected_zones.json")

DIMENSION_CN = {
    "minecraft:overworld": "主世界",
    "minecraft:the_nether": "下界",
    "minecraft:the_end": "末地",
    "*": "全部维度",
}
DIMENSION_KEYS = ["minecraft:overworld", "minecraft:the_nether",
                  "minecraft:the_end"]
DIMENSION_OPTIONS = list(DIMENSION_CN.values())   # 含"全部维度"


def load_zones():
    if ZONES_FILE.exists():
        try:
            with open(ZONES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "zones" not in data:
                data["zones"] = []
            return data
        except Exception:
            return {"zones": []}
    save_zones({"zones": []})
    return {"zones": []}


def save_zones(data):
    try:
        with open(ZONES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False


def normalize_zone(zone):
    """把两个角变成 (x1,y1,z1,x2,y2,z2)，保证 min < max。"""
    x1, x2 = sorted([float(zone["x1"]), float(zone["x2"])])
    y1, y2 = sorted([float(zone["y1"]), float(zone["y2"])])
    z1, z2 = sorted([float(zone["z1"]), float(zone["z2"])])
    return x1, y1, z1, x2, y2, z2


def _zone_matches_dimension(zone, dimension):
    """判断保护区是否作用于指定维度。"""
    zdim = zone.get("dimension", "")
    return zdim == dimension or zdim == "*"


def build_clean_command(zones, dimension):
    """
    构建某维度的清理命令。
    - 该维度无任何保护区 → 返回 None（调用方应跳过，不动这个维度）
    - 有保护区 → 清理保护区外的掉落物
    """
    active = [z for z in zones
              if z.get("enabled", True)
              and _zone_matches_dimension(z, dimension)]

    if not active:
        return None

    unless_parts = []
    for z in active:
        try:
            x1, y1, z1, x2, y2, z2 = normalize_zone(z)
        except Exception:
            continue
        # dx/dy/dz 覆盖 [x, x+dx)，要含终点方块需 +1
        dx = x2 - x1 + 1
        dy = y2 - y1 + 1
        dz = z2 - z1 + 1
        unless_parts.append(
            f"unless entity @s[x={x1:g},y={y1:g},z={z1:g},"
            f"dx={dx:g},dy={dy:g},dz={dz:g}]"
        )

    if not unless_parts:
        return None

    unless_chain = " ".join(unless_parts)
    # ★ at @s 把执行位置切到每个物品自身，否则 @s[x=..] 以 RCON 出生点判定
    return (f"execute in {dimension} as @e[type=item] at @s "
            f"{unless_chain} run kill @s")


def build_clear_all_commands():
    """全清所有维度掉落物（无保护区时使用）。"""
    return [f"execute in {dim} run kill @e[type=item]"
            for dim in DIMENSION_KEYS]


def build_visualize_command(zone, duration_seconds=15):
    """在保护区 8 个角各生成一簇粒子。返回多行命令字符串。"""
    try:
        x1, y1, z1, x2, y2, z2 = normalize_zone(zone)
    except Exception:
        return None

    dim = zone.get("dimension", "minecraft:overworld")
    if dim == "*":
        dim = "minecraft:overworld"

    corners = [
        (x1, y1, z1), (x1, y1, z2), (x1, y2, z1), (x1, y2, z2),
        (x2, y1, z1), (x2, y1, z2), (x2, y2, z1), (x2, y2, z2),
    ]
    cmds = []
    for (cx, cy, cz) in corners:
        cmds.append(
            f"execute in {dim} run particle end_rod "
            f"{cx:g} {cy:g} {cz:g} 0.3 0.3 0.3 0.1 20 normal"
        )
    return "\n".join(cmds)