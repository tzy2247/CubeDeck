"""下载 Minecraft 服务端加载器（Paper / Purpur / Fabric / Forge / NeoForge / Quilt）。

特性：
- 国内镜像优先（BMCLAPI）
- 自动回退到官方源
- 适配 Minecraft 新版本号规则（26.x）
- 所有请求走统一的 Downloader（代理 + SSL 配置）
"""
import json
import re
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass

from core.downloader import Downloader
from core.modrinth import USER_AGENT


# ============================================================
#  API 地址
# ============================================================
# Paper（官方 v3 + BMCLAPI 备选）
# 注意：api.papermc.io/v2 已弃用，必须使用 fill.papermc.io/v3[reference:2]
PAPER_API = "https://fill.papermc.io/v3"
PAPER_API_MIRROR = "https://bmclapi2.bangbang93.com/paper"

# Purpur（官方 API 在国内可能不稳定，优先使用 BMCLAPI 镜像）
PURPUR_API = "https://api.purpurmc.org/v2"
PURPUR_API_MIRROR = "https://bmclapi2.bangbang93.com/purpur"

# Fabric / Quilt
FABRIC_META = "https://meta.fabricmc.net/v2"
QUILT_META = "https://meta.quiltmc.org/v3"

# Forge
FORGE_MAVEN = "https://maven.minecraftforge.net"
FORGE_MAVEN_MIRROR = "https://bmclapi2.bangbang93.com/maven"

# NeoForge（使用用户指定的三个仓库）
NEOFORGE_MAVEN = "https://neoforged.forgecdn.net/releases"
NEOFORGE_MOJANG_META = "https://neoforged.forgecdn.net/mojang-meta"
MOJANG_LIBRARIES = "https://libraries.minecraft.net/"


@dataclass
class LoaderVersion:
    loader: str
    mc_version: str
    loader_version: str
    display: str = ""
    channel: str = "stable"


class LoaderDownloadError(Exception):
    pass


# ============================================================
#  支持的加载器列表
# ============================================================
LOADERS = [
    ("paper",    "Paper",    "插件服 · 高性能 · 推荐"),
    ("purpur",   "Purpur",   "插件服 · Paper 分支 · 可配置性强"),
    ("fabric",   "Fabric",   "模组服 · 轻量 · 更新快"),
    ("forge",    "Forge",    "模组服 · 老牌 · 兼容性好"),
    ("neoforge", "NeoForge", "模组服 · Forge 分支 · 新版本推荐"),
    ("quilt",    "Quilt",    "模组服 · Fabric 分支"),
]


# ============================================================
#  工具函数
# ============================================================
def _make_requests_session(proxy):
    import requests
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.verify = False
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    return session


def _fetch_text_multi(urls, proxy=None, timeout=20):
    """依次尝试多个 URL 返回文本，全失败抛异常。"""
    session = _make_requests_session(proxy)
    last_err = None

    for url in urls:
        try:
            resp = session.get(url, timeout=timeout)
            resp.raise_for_status()
            text = resp.text
            if text and text.strip():
                return text
        except Exception as e:
            last_err = e
            continue

    raise LoaderDownloadError(f"所有 URL 均不可用：{last_err}")


def _extract_mc_from_loader_version(loader, version):
    """
    NeoForge 版本号有 3 种格式：
      1. 1.20.1-47.1.76            早期，带 MC 前缀
      2. 20.2.59-beta / 21.1.172   MC 1.20.2 ~ 1.21.11
      3. 26.3.0.33-beta            MC 1.21.11 之后（新命名）
      另有 1.0.x 这类项目初期版本，应忽略

    Forge 一直是旧格式：1.21.1-58.1.0
    """
    if loader == "forge":
        m = re.match(r"^(\d+\.\d+(?:\.\d+)?)", version)
        return m.group(1) if m else ""

    if loader == "neoforge":
        # 格式 1：1.20.1-xxx
        m = re.match(r"^(1\.\d+(?:\.\d+)?)-", version)
        if m:
            return m.group(1)

        # 格式 2 / 3：major.minor...
        m = re.match(r"^(\d+)\.(\d+)", version)
        if not m:
            return ""
        major = int(m.group(1))
        minor = m.group(2)

        # MC 1.20.2 ~ 1.21.11 → NeoForge 20.x ~ 21.x（含 20 ~ 25 兜底）
        if 20 <= major <= 25:
            return f"1.{major}.{minor}"

        # MC 1.21.11 之后 → 新格式（年份.月份）
        if major >= 26:
            return f"{major}.{minor}"

        # 其它（如 1.0.x 项目初期版本）忽略
        return ""

    return ""


def _mc_version_sort_key(v):
    parts = v.split(".")
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    while len(result) < 3:
        result.append(0)
    return tuple(result)


# ============================================================
#  列表获取
# ============================================================
def list_mc_versions(loader, proxy=None, timeout=20):
    """返回该加载器支持的 MC 版本列表（字符串，新→旧）。"""
    loader = loader.lower()
    dl = Downloader(proxy=proxy, verify_ssl=False, timeout=timeout)

    # ---------- Paper (v3 API) ----------
    if loader == "paper":
        last_err = None
        # 官方 v3
        try:
            data, _ = dl.get_json(f"{PAPER_API}/projects/paper")
            versions_map = data.get("versions", {})
            all_versions = []
            for _minor, versions in versions_map.items():
                all_versions.extend(versions)

            seen = set()
            result = []
            for v in all_versions:
                if v not in seen:
                    seen.add(v)
                    result.append(v)
            if result:
                return result
        except Exception as e:
            last_err = e

        # BMCLAPI 备选
        try:
            data, _ = dl.get_json(PAPER_API_MIRROR)
            versions = data.get("versions", [])
            if versions:
                return list(versions)
        except Exception as e:
            last_err = e

        raise LoaderDownloadError(
            f"Paper 版本列表获取失败：{last_err}\n"
            f"  官方：{PAPER_API}\n"
            f"  镜像：{PAPER_API_MIRROR}")

    # ---------- Purpur ----------
    if loader == "purpur":
        last_err = None
        urls = [
            f"{PURPUR_API}/purpur",
            PURPUR_API_MIRROR,
        ]
        for url in urls:
            try:
                data, _ = dl.get_json(url)
                versions = data.get("versions", [])
                if versions:
                    return list(reversed(versions))
            except Exception as e:
                last_err = e
                continue
        raise LoaderDownloadError(f"Purpur 版本列表获取失败：{last_err}")

    # ---------- Fabric ----------
    if loader == "fabric":
        try:
            data, _ = dl.get_json(f"{FABRIC_META}/versions/game")
            return [v["version"] for v in data if v.get("stable")]
        except Exception as e:
            raise LoaderDownloadError(f"Fabric 版本列表获取失败：{e}")

    # ---------- Quilt ----------
    if loader == "quilt":
        try:
            data, _ = dl.get_json(f"{QUILT_META}/versions/game")
            return [v["version"] for v in data
                    if v.get("stable") and v.get("version")]
        except Exception as e:
            raise LoaderDownloadError(f"Quilt 版本列表获取失败：{e}")

    # ---------- Forge / NeoForge ----------
    if loader in ("forge", "neoforge"):
        if loader == "forge":
            urls = [
                f"{FORGE_MAVEN}/net/minecraftforge/forge/maven-metadata.xml",
                f"{FORGE_MAVEN_MIRROR}/net/minecraftforge/forge/maven-metadata.xml",
            ]
        else:
            # NeoForge 使用用户指定的 forgecdn.net 仓库
            urls = [
                f"{NEOFORGE_MAVEN}/net/neoforged/neoforge/maven-metadata.xml",
            ]

        text = _fetch_text_multi(urls, proxy=proxy, timeout=timeout)
        versions = re.findall(r"<version>([^<]+)</version>", text)

        mc_set = set()
        for v in versions:
            mc = _extract_mc_from_loader_version(loader, v)
            if mc:
                mc_set.add(mc)

        return sorted(mc_set, key=_mc_version_sort_key, reverse=True)

    raise LoaderDownloadError(f"不支持的加载器：{loader}")


def list_loader_versions(loader, mc_version, proxy=None, timeout=20):
    """列出指定加载器 + MC 版本下的所有可用的加载器版本。"""
    loader = loader.lower()
    dl = Downloader(proxy=proxy, verify_ssl=False, timeout=timeout)

    # ---------- Paper (v3 API) ----------
    if loader == "paper":
        last_err = None
        # 官方 v3
        try:
            url = (f"{PAPER_API}/projects/paper/versions/"
                   f"{mc_version}/builds")
            data, _ = dl.get_json(url)
            builds = data if isinstance(data, list) else data.get("builds", [])

            result = []
            for b in builds:
                build_id = b.get("id") or b.get("build")
                if build_id is None:
                    continue
                channel = b.get("channel", "STABLE").lower()
                time_str = (b.get("time", "") or "")[:10]
                result.append(LoaderVersion(
                    loader="paper",
                    mc_version=mc_version,
                    loader_version=str(build_id),
                    display=f"Paper #{build_id}  {time_str}",
                    channel=channel,
                ))
            if result:
                return list(reversed(result))
        except Exception as e:
            last_err = e

        # BMCLAPI 备选
        try:
            url = f"{PAPER_API_MIRROR}/{mc_version}"
            data, _ = dl.get_json(url)
            builds = data.get("builds", [])
            result = []
            for b in builds:
                build_id = b.get("build")
                if build_id is None:
                    continue
                time_str = (b.get("time", "") or "")[:10]
                result.append(LoaderVersion(
                    loader="paper",
                    mc_version=mc_version,
                    loader_version=str(build_id),
                    display=f"Paper #{build_id}  {time_str}",
                ))
            if result:
                return list(reversed(result))
        except Exception as e:
            last_err = e

        raise LoaderDownloadError(f"Paper 构建列表获取失败：{last_err}")

    # ---------- Purpur ----------
    if loader == "purpur":
        last_err = None
        urls = [
            f"{PURPUR_API}/purpur/{mc_version}",
            f"{PURPUR_API_MIRROR}/{mc_version}",
        ]
        for url in urls:
            try:
                data, _ = dl.get_json(url)
                builds = data.get("builds", {}).get("all", [])
                if not builds:
                    continue
                result = []
                for b in builds:
                    result.append(LoaderVersion(
                        loader="purpur",
                        mc_version=mc_version,
                        loader_version=str(b),
                        display=f"Purpur 构建 #{b}",
                    ))
                return list(reversed(result))
            except Exception as e:
                last_err = e
                continue
        raise LoaderDownloadError(f"Purpur 构建列表获取失败：{last_err}")

    # ---------- Fabric ----------
    if loader == "fabric":
        try:
            data, _ = dl.get_json(
                f"{FABRIC_META}/versions/loader/{mc_version}")
            result = []
            for item in data:
                loader_info = item.get("loader", {})
                version = loader_info.get("version", "")
                if not version:
                    continue
                result.append(LoaderVersion(
                    loader="fabric",
                    mc_version=mc_version,
                    loader_version=version,
                    display=f"Fabric Loader {version}",
                ))
            return result
        except Exception as e:
            raise LoaderDownloadError(f"Fabric 版本列表获取失败：{e}")

    # ---------- Quilt ----------
    if loader == "quilt":
        try:
            data, _ = dl.get_json(
                f"{QUILT_META}/versions/loader/{mc_version}")
            result = []
            for item in data:
                loader_info = item.get("loader", {})
                version = loader_info.get("version", "")
                if not version:
                    continue
                result.append(LoaderVersion(
                    loader="quilt",
                    mc_version=mc_version,
                    loader_version=version,
                    display=f"Quilt Loader {version}",
                ))
            return result
        except Exception as e:
            raise LoaderDownloadError(f"Quilt 版本列表获取失败：{e}")

    # ---------- Forge / NeoForge ----------
    if loader in ("forge", "neoforge"):
        if loader == "forge":
            urls = [
                f"{FORGE_MAVEN}/net/minecraftforge/forge/maven-metadata.xml",
                f"{FORGE_MAVEN_MIRROR}/net/minecraftforge/forge/maven-metadata.xml",
            ]
        else:
            urls = [
                f"{NEOFORGE_MAVEN}/net/neoforged/neoforge/maven-metadata.xml",
            ]

        text = _fetch_text_multi(urls, proxy=proxy, timeout=timeout)
        all_versions = re.findall(r"<version>([^<]+)</version>", text)

        result = []
        for v in all_versions:
            mcv = _extract_mc_from_loader_version(loader, v)
            if mcv == mc_version:
                result.append(LoaderVersion(
                    loader=loader,
                    mc_version=mc_version,
                    loader_version=v,
                    display=f"{loader.title()} {v}",
                ))
        return list(reversed(result))

    raise LoaderDownloadError(f"不支持的加载器：{loader}")


# ============================================================
#  下载 / 安装
# ============================================================
def download_loader(loader, mc_version, loader_version, server_dir,
                    java_path=None, proxy=None, log=None, progress=None):
    if log is None:
        log = lambda m, t="info": None
    if progress is None:
        progress = lambda c, t, n: None

    loader = loader.lower()
    server_dir = Path(server_dir)
    server_dir.mkdir(parents=True, exist_ok=True)

    dl = Downloader(proxy=proxy, verify_ssl=False, timeout=60)

    try:
        if loader == "paper":
            return _install_paper(
                dl, mc_version, loader_version, server_dir, log, progress)
        elif loader == "purpur":
            return _install_purpur(
                dl, mc_version, loader_version, server_dir, log, progress)
        elif loader == "fabric":
            return _install_fabric(
                dl, mc_version, loader_version, server_dir, log, progress)
        elif loader == "quilt":
            return _install_quilt(
                dl, mc_version, loader_version, server_dir, log, progress)
        elif loader in ("forge", "neoforge"):
            return _install_forge_like(
                dl, loader, mc_version, loader_version,
                server_dir, java_path, log, progress)
        else:
            return False, f"不支持的加载器：{loader}"
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, str(e)


def _install_paper(dl, mc_version, build_id, server_dir, log, progress):
    log(f"获取 Paper 构建 #{build_id} 信息…", "info")

    filename = f"paper-{mc_version}-{build_id}.jar"

    # 官方 v3 下载 URL
    urls = [
        (f"{PAPER_API}/projects/paper/versions/{mc_version}"
         f"/builds/{build_id}/downloads/{filename}"),
        # BMCLAPI 备选
        f"{PAPER_API_MIRROR}/{mc_version}/{build_id}/download",
    ]

    target = server_dir / "server.jar"
    log(f"下载 {filename} → server.jar", "info")
    progress(0, 1, filename)

    result = dl.download_file(urls, target)
    if not result.ok:
        return False, (f"下载失败：{result.error}\n"
                       f"  尝试过：\n"
                       f"    {urls[0]}\n"
                       f"    {urls[1]}")

    progress(1, 1, filename)
    return True, f"Paper {mc_version} 构建 #{build_id} 已安装到 server.jar"


def _install_purpur(dl, mc_version, build_id, server_dir, log, progress):
    filename = f"purpur-{mc_version}-{build_id}.jar"
    urls = [
        f"{PURPUR_API}/purpur/{mc_version}/{build_id}/download",
        f"{PURPUR_API_MIRROR}/{mc_version}/{build_id}/download",
    ]

    target = server_dir / "server.jar"
    log(f"下载 Purpur {mc_version} 构建 #{build_id}", "info")
    progress(0, 1, filename)

    result = dl.download_file(urls, target)
    if not result.ok:
        return False, f"下载失败：{result.error}"

    progress(1, 1, filename)
    return True, f"Purpur {mc_version} 构建 #{build_id} 已安装到 server.jar"


def _install_fabric(dl, mc_version, loader_version, server_dir, log, progress):
    try:
        installer_versions, _ = dl.get_json(
            f"{FABRIC_META}/versions/installer")
        if not installer_versions:
            return False, "无法获取 Fabric Installer 版本"
        installer_version = installer_versions[0].get("version", "")
        if not installer_version:
            return False, "Installer 版本为空"
    except Exception as e:
        return False, f"获取 Fabric Installer 版本失败：{e}"

    url = (f"{FABRIC_META}/versions/loader/{mc_version}/"
           f"{loader_version}/{installer_version}/server/jar")

    target = server_dir / "server.jar"
    log(f"下载 Fabric Server Launcher "
        f"(MC {mc_version} + Loader {loader_version})", "info")
    progress(0, 1, "fabric-server-launch.jar")

    result = dl.download_file([url], target)
    if not result.ok:
        return False, f"下载失败：{result.error}"

    progress(1, 1, "fabric-server-launch.jar")
    return True, "Fabric 已安装到 server.jar（首次启动会自动下载 MC 服务端）"


def _install_quilt(dl, mc_version, loader_version, server_dir, log, progress):
    installer_url = ("https://quiltmc.org/api/v1/"
                     "download-latest-installer/java-universal")
    installer_path = server_dir / "quilt-installer.jar"

    log("下载 Quilt Installer…", "info")
    progress(0, 3, "quilt-installer.jar")
    result = dl.download_file([installer_url], installer_path)
    if not result.ok:
        return False, f"下载 Installer 失败：{result.error}"

    return _run_installer(
        installer_path, server_dir,
        ["install", "server", mc_version,
         "--loader-version", loader_version, "--download-server"],
        "Quilt", log, progress, delete_after=True)


def _install_forge_like(dl, loader, mc_version, loader_version,
                        server_dir, java_path, log, progress):
    """Forge / NeoForge：下载 installer，运行 --installServer。"""
    if loader == "forge":
        urls = [
            (f"{FORGE_MAVEN}/net/minecraftforge/forge/"
             f"{loader_version}/"
             f"forge-{loader_version}-installer.jar"),
            (f"{FORGE_MAVEN_MIRROR}/net/minecraftforge/forge/"
             f"{loader_version}/"
             f"forge-{loader_version}-installer.jar"),
        ]
        label = "Forge"
    else:
        # NeoForge：使用用户指定的 forgecdn.net 镜像
        urls = [
            (f"{NEOFORGE_MAVEN}/net/neoforged/neoforge/"
             f"{loader_version}/"
             f"neoforge-{loader_version}-installer.jar"),
        ]
        label = "NeoForge"

    installer_path = server_dir / f"{loader}-installer.jar"
    log(f"下载 {label} Installer…", "info")
    progress(0, 2, installer_path.name)

    result = dl.download_file(urls, installer_path)
    if not result.ok:
        return False, (f"下载 Installer 失败：{result.error}\n"
                       f"  尝试过：\n"
                       + "\n".join(f"    {u}" for u in urls))

    # NeoForge installer 需要通过 JVM 参数指定镜像仓库
    extra_jvm_args = []
    if loader == "neoforge":
        # 使用用户指定的仓库，确保 installer 能正确解析依赖
        extra_jvm_args = [
            f"-Dmaven.repo.remote={NEOFORGE_MAVEN}",
            f"-Dmaven.repo.local={server_dir / '.m2'}",
        ]

    return _run_installer(
        installer_path, server_dir,
        ["--installServer"],
        label, log, progress,
        delete_after=False,
        java_path=java_path,
        extra_jvm_args=extra_jvm_args)


def _run_installer(installer_path, server_dir, args, label,
                   log, progress, delete_after=True,
                   java_path=None, extra_jvm_args=None):
    java_exe = java_path or shutil.which("java") or "java"

    log(f"运行 {label} Installer（需要几秒到几分钟）…", "info")
    progress(1, 2, "installer 运行中")

    cmd = [java_exe]
    if extra_jvm_args:
        cmd.extend(extra_jvm_args)
    cmd.extend(["-jar", str(installer_path)])
    cmd.extend(args)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(server_dir),
            capture_output=True,
            text=True,
            timeout=900,
        )
    except subprocess.TimeoutExpired:
        return False, "Installer 执行超时（>15 分钟）"
    except FileNotFoundError:
        return False, f"找不到 Java：{java_exe}"
    except Exception as e:
        return False, f"运行 Installer 失败：{e}"

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-800:]
        return False, (f"Installer 执行失败（退出码 {proc.returncode}）：\n"
                       f"{err}")

    if delete_after:
        try:
            installer_path.unlink()
        except Exception:
            pass

    progress(2, 2, "完成")
    return True, (f"{label} 安装完成。\n"
                  f"运行脚本：run.sh / run.bat\n"
                  f"（首次运行会下载剩余依赖）")