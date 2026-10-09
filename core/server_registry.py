"""多服务器注册表。

所有数据在 CubeDeck/ 目录下：
  CubeDeck/servers.json      — 注册表
  CubeDeck/<id>/             — 每个服务器的数据
"""
import json
import uuid
from pathlib import Path

from core import paths


REGISTRY_FILE = paths.SERVERS_FILE
LEGACY_CONFIG = paths.LEGACY_CONFIG_FILE


def load_registry():
    _migrate_if_needed()
    if REGISTRY_FILE.exists():
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "servers" not in data:
                data["servers"] = []
            return data
        except Exception:
            pass
    return {"active_id": None, "servers": []}


def save_registry(registry):
    try:
        paths.ensure_userdata_root()
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False


# ============================================================
#  迁移
# ============================================================
def _migrate_if_needed():
    paths.ensure_userdata_root()
    paths.migrate_legacy_files()

    if REGISTRY_FILE.exists():
        return
    if not LEGACY_CONFIG.exists():
        return

    try:
        with open(LEGACY_CONFIG, "r", encoding="utf-8") as f:
            old_cfg = json.load(f)
    except Exception:
        return

    server_path = old_cfg.get("server_path", "")
    name = Path(server_path).name if server_path else "默认服务器"

    server_id = "default"
    registry = {
        "active_id": server_id,
        "servers": [
            {"id": server_id, "name": name, "config": old_cfg},
        ],
    }
    save_registry(registry)

    # 迁移散落的旧数据文件到 CubeDeck/default/
    data_dir = paths.server_dir(server_id)
    import shutil
    for fname in paths.LEGACY_DATA_FILES:
        src = Path(fname)
        if src.exists():
            dst = data_dir / fname
            if not dst.exists():
                try:
                    shutil.move(str(src), str(dst))
                except Exception:
                    pass

    try:
        LEGACY_CONFIG.rename(LEGACY_CONFIG.with_suffix(".json.bak"))
    except Exception:
        pass


# ============================================================
#  查询
# ============================================================
def get_active_id():
    r = load_registry()
    aid = r.get("active_id")
    servers = r.get("servers", [])
    if aid and any(s["id"] == aid for s in servers):
        return aid
    return servers[0]["id"] if servers else None


def get_active():
    r = load_registry()
    aid = get_active_id()
    for s in r.get("servers", []):
        if s["id"] == aid:
            return s
    return None


def get_server(server_id):
    for s in load_registry().get("servers", []):
        if s["id"] == server_id:
            return s
    return None


def list_servers():
    return load_registry().get("servers", [])


def get_data_dir(server_id):
    return paths.server_dir(server_id)


# ============================================================
#  修改
# ============================================================
def set_active(server_id):
    r = load_registry()
    for s in r.get("servers", []):
        if s["id"] == server_id:
            r["active_id"] = server_id
            return save_registry(r)
    return False


def add_server(name, config):
    r = load_registry()
    server_id = uuid.uuid4().hex[:8]
    r["servers"].append({
        "id": server_id,
        "name": name,
        "config": config,
    })
    if not r.get("active_id"):
        r["active_id"] = server_id
    save_registry(r)
    paths.server_dir(server_id)
    return server_id


def update_server(server_id, name=None, config=None):
    r = load_registry()
    for s in r.get("servers", []):
        if s["id"] == server_id:
            if name is not None:
                s["name"] = name
            if config is not None:
                s["config"] = config
            return save_registry(r)
    return False


def remove_server(server_id):
    r = load_registry()
    servers = r.get("servers", [])
    r["servers"] = [s for s in servers if s["id"] != server_id]
    if r.get("active_id") == server_id:
        r["active_id"] = r["servers"][0]["id"] if r["servers"] else None
    save_registry(r)
    return True