"""所有软件生成文件的路径定义。

- `lang/`       用户放语言文件，软件只读
- `CubeDeck/`   软件运行时数据，所有 .json 都在这里
"""
from pathlib import Path


# 运行时数据根目录
USERDATA_ROOT = Path("CubeDeck")

# 语言文件目录（只读）
LANG_ROOT = Path("lang")

# 全局文件
SERVERS_FILE = USERDATA_ROOT / "servers.json"
STATE_FILE = USERDATA_ROOT / "server_state.json"

# 每个服务器的数据目录前缀
SERVER_DATA_PREFIX = USERDATA_ROOT

# 旧位置（用于一次性迁移）
LEGACY_SERVERS_FILE = Path("servers.json")
LEGACY_STATE_FILE = Path("server_state.json")
LEGACY_CONFIG_FILE = Path("server_config.json")
LEGACY_DATA_ROOT = Path("userdata")        # 上一版的目录
LEGACY_LANG_DIRS = [Path("data"), Path("assets") / "lang"]

# 旧版散落在根目录的每服务器数据文件
LEGACY_DATA_FILES = [
    "permissions.json",
    "protected_zones.json",
    "clean_zones.json",
    "ai_chat_history.json",
    "server_state.json",
]


def ensure_userdata_root():
    USERDATA_ROOT.mkdir(parents=True, exist_ok=True)


def ensure_lang_root():
    LANG_ROOT.mkdir(parents=True, exist_ok=True)


def server_dir(server_id: str) -> Path:
    """返回某个服务器的数据目录（自动创建）。"""
    d = SERVER_DATA_PREFIX / server_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def migrate_legacy_files():
    """把旧位置的文件搬到新位置。只在启动时调用一次。"""
    import shutil

    ensure_userdata_root()

    # 1. 从上一版 userdata/ 迁移到 CubeDeck/
    if LEGACY_DATA_ROOT.exists() and LEGACY_DATA_ROOT.is_dir():
        for item in LEGACY_DATA_ROOT.iterdir():
            target = USERDATA_ROOT / item.name
            if target.exists():
                continue
            try:
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    shutil.move(str(item), str(target))
            except Exception:
                pass
        try:
            if not any(LEGACY_DATA_ROOT.iterdir()):
                LEGACY_DATA_ROOT.rmdir()
        except Exception:
            pass

    # 2. 根目录散落的文件
    if LEGACY_SERVERS_FILE.exists() and not SERVERS_FILE.exists():
        try:
            shutil.move(str(LEGACY_SERVERS_FILE), str(SERVERS_FILE))
        except Exception:
            pass

    if LEGACY_STATE_FILE.exists() and not STATE_FILE.exists():
        try:
            shutil.move(str(LEGACY_STATE_FILE), str(STATE_FILE))
        except Exception:
            pass

    # 3. 旧的语言文件目录 → lang/
    ensure_lang_root()
    for old_dir in LEGACY_LANG_DIRS:
        if not old_dir.exists() or not old_dir.is_dir():
            continue
        for item in old_dir.iterdir():
            if not item.is_file():
                continue
            if item.suffix.lower() != ".json":
                continue
            target = LANG_ROOT / item.name
            if target.exists():
                continue
            try:
                shutil.move(str(item), str(target))
            except Exception:
                pass