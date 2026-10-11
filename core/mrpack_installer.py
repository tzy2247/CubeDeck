"""解析并安装 Modrinth .mrpack 整合包。

.mrpack 结构：
    <root>/
        modrinth.index.json      # 索引：文件清单 + 依赖
        overrides/               # 通用覆盖文件
        client-overrides/        # 客户端专用（服务端跳过）
        server-overrides/        # 服务端专用（优先于 overrides）

服务端安装流程：
1. 读 modrinth.index.json
2. 按 files 列表下载（跳过 env.server=unsupported 的）
3. 应用 overrides/ + server-overrides/（后者覆盖前者）
"""
import json
import shutil
import zipfile
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class MrpackFile:
    path: str
    downloads: list = field(default_factory=list)
    hashes: dict = field(default_factory=dict)
    file_size: int = 0
    client_env: str = "required"
    server_env: str = "required"


@dataclass
class MrpackInfo:
    name: str = ""
    version_id: str = ""
    summary: str = ""
    mc_version: str = ""
    loader: str = ""
    loader_version: str = ""
    files: list = field(default_factory=list)


class MrpackError(Exception):
    pass


def parse_mrpack(mrpack_path):
    """解析 .mrpack，返回 MrpackInfo。不下载任何东西。"""
    mrpack_path = Path(mrpack_path)
    if not mrpack_path.exists():
        raise MrpackError(f"文件不存在：{mrpack_path}")

    if not zipfile.is_zipfile(mrpack_path):
        raise MrpackError("不是有效的 .mrpack（非 ZIP 格式）")

    with zipfile.ZipFile(mrpack_path, "r") as zf:
        try:
            index_bytes = zf.read("modrinth.index.json")
        except KeyError:
            raise MrpackError(
                "缺少 modrinth.index.json（不是有效的 Modrinth 整合包）")

        try:
            index = json.loads(index_bytes.decode("utf-8"))
        except Exception as e:
            raise MrpackError(f"modrinth.index.json 解析失败：{e}")

    if index.get("game") != "minecraft":
        raise MrpackError("不是 Minecraft 整合包")

    info = MrpackInfo()
    info.name = index.get("name", mrpack_path.stem)
    info.version_id = index.get("versionId", "")
    info.summary = index.get("summary", "")

    deps = index.get("dependencies", {}) or {}
    info.mc_version = deps.get("minecraft", "")

    for loader_key in ("fabric-loader", "forge", "neoforge", "quilt-loader"):
        if loader_key in deps:
            info.loader = loader_key.replace("-loader", "")
            info.loader_version = deps[loader_key]
            break

    for f in index.get("files", []):
        path = f.get("path", "")
        if not path:
            continue
        env = f.get("env", {}) or {}
        info.files.append(MrpackFile(
            path=path,
            downloads=f.get("downloads", []) or [],
            hashes=f.get("hashes", {}) or {},
            file_size=f.get("fileSize", 0),
            client_env=env.get("client", "required"),
            server_env=env.get("server", "required"),
        ))

    return info


def count_server_files(mrpack_path, include_optional=False):
    """预估服务端要下载的文件数。"""
    info = parse_mrpack(mrpack_path)
    n = 0
    for f in info.files:
        if f.server_env == "unsupported":
            continue
        if f.server_env == "optional" and not include_optional:
            continue
        if not f.downloads:
            continue
        n += 1
    return n, info


def install_mrpack(mrpack_path, server_dir, downloader,
                   log=None, progress=None, include_optional=False):
    """
    安装整合包到 server_dir。

    downloader: Downloader 实例
    log: (msg, tag) -> None
    progress: (current, total, name) -> None
    include_optional: 是否下载 env.server == "optional" 的文件

    返回 (成功数, 失败数, 跳过数, 错误列表)
    """
    if log is None:
        log = lambda m, t="info": None
    if progress is None:
        progress = lambda c, t, n: None

    mrpack_path = Path(mrpack_path)
    server_dir = Path(server_dir)
    server_dir.mkdir(parents=True, exist_ok=True)

    info = parse_mrpack(mrpack_path)
    log(f"整合包：{info.name}  ·  MC {info.mc_version}  ·  "
        f"{info.loader or '原版'}", "info")

    # ---------- 1. 过滤出服务端需要的文件 ----------
    server_files = []
    skipped_files = []
    for f in info.files:
        if f.server_env == "unsupported":
            skipped_files.append(f)
            continue
        if f.server_env == "optional" and not include_optional:
            skipped_files.append(f)
            continue
        if not f.downloads:
            skipped_files.append(f)
            continue
        server_files.append(f)

    log(f"待下载 {len(server_files)} 个文件"
        f"（跳过 {len(skipped_files)} 个客户端/可选）", "info")

    succeeded = 0
    failed = 0
    errors = []
    total = len(server_files)

    for i, f in enumerate(server_files):
        dest = server_dir / f.path
        progress(i + 1, total, f.path)

        # 已存在则跳过
        if dest.exists() and dest.stat().st_size > 0:
            succeeded += 1
            continue

        try:
            result = downloader.download_file(f.downloads, dest)
            if result.ok:
                succeeded += 1
            else:
                failed += 1
                errors.append((f.path, result.error))
                log(f"  ✖ {f.path}：{result.error}", "error")
        except Exception as e:
            failed += 1
            errors.append((f.path, str(e)))
            log(f"  ✖ {f.path}：{e}", "error")

    # ---------- 2. 应用 overrides ----------
    log("应用配置文件（overrides）…", "info")
    try:
        with zipfile.ZipFile(mrpack_path, "r") as zf:
            # 先 overrides，再 server-overrides（后者覆盖前者）
            for prefix in ("overrides/", "server-overrides/"):
                for name in zf.namelist():
                    if not name.startswith(prefix):
                        continue
                    if name.endswith("/"):
                        continue
                    rel = name[len(prefix):]
                    if not rel:
                        continue
                    target = server_dir / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        with zf.open(name) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                    except Exception as e:
                        log(f"  ✖ 覆盖 {rel} 失败：{e}", "warn")
    except Exception as e:
        log(f"覆盖文件失败：{e}", "error")

    log(f"整合包安装完成：成功 {succeeded}，失败 {failed}，"
        f"跳过 {len(skipped_files)}", "ok")
    return succeeded, failed, len(skipped_files), errors