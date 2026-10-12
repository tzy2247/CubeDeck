"""下载 Minecraft 服务端加载器（原版 / Paper / Purpur / Fabric / Forge / NeoForge / Quilt）。

特性：
- 官方源优先，FastMirror / BMCLAPI 作为备用源
- 自动回退，多源重试
- 适配 Minecraft 新版本号规则（26.x）
- 所有请求走统一的 Downloader（代理 + SSL 配置）

原版稳定性：
- manifest 只用 Mojang 官方源（BMCLAPI 的 manifest 镜像目前不稳定）
- version.json 和 server.jar 使用 官方 → BMCLAPI 双源

Paper / Purpur：
- 官方 API 优先
- BMCLAPI 作为备用源
- FastMirror 作为最后兜底

FastMirror API：
- 核心列表：GET /api/v3/
- 版本列表：见核心列表中的 mc_versions
- 构建列表：GET /api/v3/{core}/{mc_version}?offset=0&limit=100
- 构建详情：GET /api/v3/{core}/{mc_version}/{build_version}
"""
import json
import re
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass

from core.downloader import Downloader
from core.modrinth import USER_AGENT
from core.url_order import order_urls


# ============================================================
#  API 地址
# ============================================================
# Paper（官方 v3 + BMCLAPI 备选）
PAPER_API = "https://fill.papermc.io/v3"
PAPER_API_MIRROR = "https://bmclapi2.bangbang93.com/paper"

# Purpur
PURPUR_API = "https://api.purpurmc.org/v2"
PURPUR_API_MIRROR = "https://bmclapi2.bangbang93.com/purpur"

# Fabric / Quilt
FABRIC_META = "https://meta.fabricmc.net/v2"
QUILT_META = "https://meta.quiltmc.org/v3"

# Forge
FORGE_MAVEN = "https://maven.minecraftforge.net"
FORGE_MAVEN_MIRROR = "https://bmclapi2.bangbang93.com/maven"

# NeoForge
NEOFORGE_MAVEN = "https://neoforged.forgecdn.net/releases"
NEOFORGE_MOJANG_META = "https://neoforged.forgecdn.net/mojang-meta"
MOJANG_LIBRARIES = "https://libraries.minecraft.net/"

# 原版：Mojang 版本清单
MOJANG_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

# FastMirror（无极镜像）：国内稳定的服务端核心来源
FASTMIRROR_API = "https://download.fastmirror.net/api/v3"

# FastMirror 核心名映射（必须首字母大写）
FASTMIRROR_CORES = {
    "vanilla":  "Vanilla",
    "paper":    "Paper",
    "purpur":   "Purpur",
    "fabric":   "Fabric",
    "forge":    "Forge",
    "neoforge": None,       # FastMirror 没有 NeoForge
    "quilt":    None,       # FastMirror 没有 Quilt
}


@dataclass
class LoaderVersion:
    loader: str
    mc_version: str
    loader_version: str
    display: str = ""
    channel: str = "stable"


class LoaderDownloadError(Exception):
    pass


LOADERS = [
    ("vanilla",  "原版",     "官方服务端 · 无插件 · 纯净"),
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
    session.trust_env = False
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


def _fetch_text_multi(urls, proxy=None, timeout=30):
    """依次尝试多个 URL 返回文本，全失败抛异常。"""
    import time
    session = _make_requests_session(proxy)
    last_err = None

    for url in urls:
        for attempt in range(3):
            try:
                resp = session.get(url, timeout=timeout)
                resp.raise_for_status()
                text = resp.text
                if text and text.strip():
                    return text
                last_err = f"空响应（来自 {url}）"
                break
            except Exception as e:
                last_err = e
                if attempt < 2:
                    time.sleep(1.0 * (2 ** attempt))

    raise LoaderDownloadError(f"所有 URL 均不可用：{last_err}")


def _bmclapi_mirror(url: str) -> str:
    """把 Mojang 官方 URL 替换为 BMCLAPI 镜像。无匹配则返回原 URL。"""
    prefixes = [
        "https://piston-meta.mojang.com",
        "https://piston-data.mojang.com",
        "https://launchermeta.mojang.com",
        "https://launcher.mojang.com",
        "https://libraries.minecraft.net",
    ]
    for p in prefixes:
        if url.startswith(p):
            return "https://bmclapi2.bangbang93.com" + url[len(p):]
    return url


def _extract_mc_from_loader_version(loader, version):
    if loader == "forge":
        m = re.match(r"^(\d+\.\d+(?:\.\d+)?)", version)
        return m.group(1) if m else ""

    if loader == "neoforge":
        m = re.match(r"^(1\.\d+(?:\.\d+)?)-", version)
        if m:
            return m.group(1)

        m = re.match(r"^(\d+)\.(\d+)", version)
        if not m:
            return ""
        major = int(m.group(1))
        minor = m.group(2)

        if 20 <= major <= 25:
            return f"1.{major}.{minor}"

        if major >= 26:
            return f"{major}.{minor}"

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
#  FastMirror 辅助函数
# ============================================================
def _fm_find_core(data, core_name: str):
    """在 FastMirror 核心列表里找到指定核心。"""
    items = []
    if isinstance(data, dict):
        items = data.get("data", [])
    elif isinstance(data, list):
        items = data

    if not isinstance(items, list):
        return None

    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "")
        if name.lower() == core_name.lower():
            return item
    return None


def _fm_get_mc_versions(dl, core: str):
    """
    从 FastMirror 获取某核心支持的 MC 版本列表。
    数据源：GET /api/v3/ → data[].mc_versions
    """
    fm_core = FASTMIRROR_CORES.get(core.lower())
    if not fm_core:
        return []

    try:
        data, _ = dl.get_json(f"{FASTMIRROR_API}/")
    except Exception:
        return []

    core_info = _fm_find_core(data, fm_core)
    if not core_info:
        return []

    mc_versions = core_info.get("mc_versions", [])
    if not isinstance(mc_versions, list):
        return []

    result = []
    for v in mc_versions:
        if not isinstance(v, str):
            continue
        low = v.lower()
        # 跳过快照/预发布
        if any(tag in low for tag in
               ("snapshot", "pre-", "pre", "rc-", "rc",
                "craftmine", "combat", "experimental",
                "obfuscated", "deep_dark", "shareware",
                "_unobfuscated")):
            continue
        # 跳过周快照（25w46a）
        if re.match(r"^\d+w\d+", v):
            continue
        result.append(v)

    # 去重
    seen = set()
    deduped = []
    for v in result:
        if v not in seen:
            seen.add(v)
            deduped.append(v)

    return deduped


def _fm_get_builds(dl, core: str, mc_version: str):
    """
    从 FastMirror 获取某核心 + MC 版本的构建列表。
    响应结构：
      data.builds[].core_version  → "build133"
      data.count                  → 总数
    返回 [(纯数字版本号, 显示文本), ...]
    """
    fm_core = FASTMIRROR_CORES.get(core.lower())
    if not fm_core:
        return []

    builds = []
    offset = 0
    limit = 100
    max_pages = 10
    page = 0

    while page < max_pages:
        page += 1
        try:
            data, _ = dl.get_json(
                f"{FASTMIRROR_API}/{fm_core}/{mc_version}"
                f"?offset={offset}&limit={limit}")
        except Exception:
            break

        if not isinstance(data, dict) or not data.get("success"):
            break

        payload = data.get("data", {})
        if not isinstance(payload, dict):
            break

        page_builds = payload.get("builds", [])
        total = payload.get("count", 0)

        if not isinstance(page_builds, list):
            break

        for b in page_builds:
            if not isinstance(b, dict):
                continue

            core_version = b.get("core_version", "")
            if not core_version:
                continue

            # "build133" → "133"
            display_version = core_version.replace("build", "").strip()

            time_str = (b.get("update_time", "") or "")[:10]
            display = f"{fm_core} #{display_version}"
            if time_str:
                display += f"  {time_str}"

            builds.append((display_version, display))

        offset += limit
        if offset >= total or not page_builds:
            break

    return builds


def _fm_find_url(obj, depth=0):
    """从嵌套结构中递归查找第一个 http 下载链接。"""
    if depth > 8:
        return None

    if isinstance(obj, str):
        if obj.startswith("http"):
            return obj
        return None

    if isinstance(obj, dict):
        # 优先常见字段
        for k in ("url", "downloadUrl", "download_url",
                  "link", "download"):
            if k in obj and isinstance(obj[k], str):
                if obj[k].startswith("http"):
                    return obj[k]
        # 递归所有值
        for v in obj.values():
            r = _fm_find_url(v, depth + 1)
            if r:
                return r

    if isinstance(obj, list):
        for item in obj:
            r = _fm_find_url(item, depth + 1)
            if r:
                return r

    return None


def _fm_get_download_url(dl, core: str, mc_version: str,
                          build_version: str):
    """
    从 FastMirror 获取具体构建的下载链接。
    build_version 可以是纯数字（"133"）或带前缀（"build133"），
    函数会自动尝试两种格式。
    """
    fm_core = FASTMIRROR_CORES.get(core.lower())
    if not fm_core:
        return ""

    # 尝试两种格式
    candidates = []
    if build_version.startswith("build"):
        candidates.append(build_version)
    else:
        candidates.append(f"build{build_version}")
        candidates.append(build_version)

    for ver in candidates:
        try:
            data, _ = dl.get_json(
                f"{FASTMIRROR_API}/{fm_core}/{mc_version}/{ver}")
        except Exception:
            continue

        if not isinstance(data, dict) or not data.get("success"):
            continue

        url = _fm_find_url(data)
        if url:
            return url

    return ""


# ============================================================
#  列表获取
# ============================================================
def list_mc_versions(loader, proxy=None, timeout=30, prefer="official"):
    """返回该加载器支持的 MC 版本列表（字符串，新→旧）。"""
    loader = loader.lower()
    dl = Downloader(proxy=proxy, verify_ssl=False, timeout=timeout)

    # ---------- 原版：只用官方源 ----------
    if loader == "vanilla":
        try:
            data, _ = dl.get_json(MOJANG_MANIFEST)
            versions = data.get("versions", [])
            return [v["id"] for v in versions
                    if v.get("type") == "release"]
        except Exception as e:
            raise LoaderDownloadError(f"原版版本列表获取失败：{e}")

    # ---------- Paper：官方 → BMCLAPI → FastMirror ----------
    if loader == "paper":
        last_err = None

        # 官方 / BMCLAPI：按 prefer 排序
        ordered = order_urls(
            [f"{PAPER_API}/projects/paper"],
            [PAPER_API_MIRROR],
            prefer,
        )

        for url in ordered:
            try:
                data, _ = dl.get_json(url)
                if "projects" in url:
                    # 官方 v3 格式
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
                else:
                    # BMCLAPI 格式
                    versions = data.get("versions", [])
                    if versions:
                        return list(versions)
            except Exception as e:
                last_err = e

        # FastMirror 兜底
        fm_versions = _fm_get_mc_versions(dl, "paper")
        if fm_versions:
            return fm_versions

        raise LoaderDownloadError(
            f"Paper 版本列表获取失败：{last_err}\n"
            f"  尝试过：{ordered} + FastMirror")

    # ---------- Purpur：官方 → BMCLAPI → FastMirror ----------
    if loader == "purpur":
        last_err = None

        ordered = order_urls(
            [f"{PURPUR_API}/purpur"],
            [PURPUR_API_MIRROR],
            prefer,
        )

        for url in ordered:
            try:
                data, _ = dl.get_json(url)
                versions = data.get("versions", [])
                if versions:
                    return list(reversed(versions))
            except Exception as e:
                last_err = e

        fm_versions = _fm_get_mc_versions(dl, "purpur")
        if fm_versions:
            return fm_versions

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
            urls = order_urls(
                f"{FORGE_MAVEN}/net/minecraftforge/forge/maven-metadata.xml",
                f"{FORGE_MAVEN_MIRROR}/net/minecraftforge/forge/maven-metadata.xml",
                prefer,
            )
        else:
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

def list_loader_versions(loader, mc_version, proxy=None, timeout=30,
                         prefer="official"):
    """列出指定加载器 + MC 版本下的所有可用的加载器版本。"""
    loader = loader.lower()
    dl = Downloader(proxy=proxy, verify_ssl=False, timeout=timeout)

    # ---------- 原版：只有一个 jar，返回占位项 ----------
    if loader == "vanilla":
        return [LoaderVersion(
            loader="vanilla",
            mc_version=mc_version,
            loader_version=mc_version,
            display=f"原版服务端 {mc_version}",
        )]

    # ---------- Paper：官方 → BMCLAPI → FastMirror ----------
    if loader == "paper":
        last_err = None

        # FastMirror
        fm_builds = _fm_get_builds(dl, "paper", mc_version)
        if fm_builds:
            result = []
            for version, display in fm_builds:
                result.append(LoaderVersion(
                    loader="paper",
                    mc_version=mc_version,
                    loader_version=version,
                    display=display,
                ))
            return result

        ordered = order_urls(
            [f"{PAPER_API}/projects/paper/versions/{mc_version}/builds"],
            [f"{PAPER_API_MIRROR}/{mc_version}"],
            prefer,
        )

        for url in ordered:
            try:
                data, _ = dl.get_json(url)
                if "projects" in url:
                    # 官方 v3
                    builds = data if isinstance(data, list) \
                        else data.get("builds", [])
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
                else:
                    # BMCLAPI
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

        # FastMirror 兜底
        fm_builds = _fm_get_builds(dl, "paper", mc_version)

    # ---------- Purpur：官方 → BMCLAPI → FastMirror ----------
    if loader == "purpur":
        last_err = None

        ordered = order_urls(
            [f"{PURPUR_API}/purpur/{mc_version}"],
            [f"{PURPUR_API_MIRROR}/{mc_version}"],
            prefer,
        )

        for url in ordered:
            try:
                data, _ = dl.get_json(url)
                builds = data.get("builds", {}).get("all", [])
                if builds:
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

        # FastMirror 兜底
        fm_builds = _fm_get_builds(dl, "purpur", mc_version)

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
            urls = order_urls(
                f"{FORGE_MAVEN}/net/minecraftforge/forge/maven-metadata.xml",
                f"{FORGE_MAVEN_MIRROR}/net/minecraftforge/forge/maven-metadata.xml",
                prefer,
            )
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
                    java_path=None, proxy=None, log=None, progress=None,
                    prefer="official"):
    if log is None:
        log = lambda m, t="info": None
    if progress is None:
        progress = lambda c, t, n: None

    loader = loader.lower()
    server_dir = Path(server_dir)
    server_dir.mkdir(parents=True, exist_ok=True)

    dl = Downloader(proxy=proxy, verify_ssl=False, timeout=60)

    try:
        if loader == "vanilla":
            return _install_vanilla(
                dl, mc_version, server_dir, log, progress, prefer)
        if loader == "paper":
            return _install_paper(
                dl, mc_version, loader_version, server_dir,
                proxy, log, progress, prefer)
        elif loader == "purpur":
            return _install_purpur(
                dl, mc_version, loader_version, server_dir,
                proxy, log, progress, prefer)
        elif loader == "fabric":
            return _install_fabric(
                dl, mc_version, loader_version, server_dir, log, progress)
        elif loader == "quilt":
            return _install_quilt(
                dl, mc_version, loader_version, server_dir, log, progress)
        elif loader in ("forge", "neoforge"):
            return _install_forge_like(
                dl, loader, mc_version, loader_version,
                server_dir, java_path, log, progress, prefer)
        else:
            return False, f"不支持的加载器：{loader}"
    except Exception as e:
        import traceback
        traceback.print_exc()
        return False, str(e)


# ============================================================
#  原版安装
# ============================================================
def _install_vanilla(dl, mc_version, server_dir, log, progress,
                     prefer="official"):
    log(f"获取原版服务端 {mc_version} 信息…", "info")

    try:
        manifest, _ = dl.get_json(MOJANG_MANIFEST)
    except Exception as e:
        return False, (f"获取版本清单失败：{e}\n"
                       f"  源：{MOJANG_MANIFEST}")

    version_info = None
    for v in manifest.get("versions", []):
        if v.get("id") == mc_version:
            version_info = v
            break

    if not version_info:
        return False, f"未在版本清单中找到 {mc_version}"

    version_url = version_info.get("url", "")
    if not version_url:
        return False, f"版本 {mc_version} 缺少元数据地址"

    version_urls = order_urls(
        version_url,
        _bmclapi_mirror(version_url),
        prefer,
    )
    seen = set()
    version_urls = [u for u in version_urls
                    if not (u in seen or seen.add(u))]

    try:
        version_data, _ = dl.get_json(version_urls)
    except Exception as e:
        return False, (f"获取版本详情失败：{e}\n"
                       f"  尝试过：\n"
                       + "\n".join(f"    {u}" for u in version_urls))

    server_info = version_data.get("downloads", {}).get("server")
    if not server_info:
        return False, (f"版本 {mc_version} 没有服务端下载"
                       f"（可能是快照或客户端专用版本）")

    server_url = server_info.get("url", "")
    if not server_url:
        return False, f"版本 {mc_version} 服务端下载地址为空"

    server_urls = order_urls(
        server_url,
        _bmclapi_mirror(server_url),
        prefer,
    )
    server_urls = [server_url, _bmclapi_mirror(server_url)]
    seen = set()
    server_urls = [u for u in server_urls
                   if not (u in seen or seen.add(u))]

    filename = f"minecraft-server-{mc_version}.jar"
    target = server_dir / "server.jar"

    log(f"下载 {filename} → server.jar", "info")
    progress(0, 1, filename)

    result = dl.download_file(server_urls, target, min_size=500 * 1024)
    if not result.ok:
        return False, (f"下载失败：{result.error}\n"
                       f"  尝试过：\n"
                       + "\n".join(f"    {u}" for u in server_urls))

    progress(1, 1, filename)
    return True, (f"原版服务端 {mc_version} 已安装到 server.jar\n"
                  f"提示：首次启动前需在目录中创建 eula.txt 并同意 EULA")


# ============================================================
#  Paper：官方 → BMCLAPI → FastMirror
# ============================================================
def _install_paper(dl, mc_version, build_id, server_dir,
                   proxy, log, progress, prefer="official"):
    log(f"获取 Paper 构建 #{build_id} 信息…", "info")

    filename = f"paper-{mc_version}-{build_id}.jar"

    urls = order_urls(
        [(f"{PAPER_API}/projects/paper/versions/{mc_version}"
          f"/builds/{build_id}/downloads/{filename}")],
        [f"{PAPER_API_MIRROR}/{mc_version}/{build_id}/download"],
        prefer,
    )

    fm_url = _fm_get_download_url(
        dl, "paper", mc_version, f"build{build_id}")
    if fm_url:
        urls.append(fm_url)
        log(f"  已加入 FastMirror 兜底源", "info")

    target = server_dir / "server.jar"
    log(f"下载 {filename} → server.jar", "info")
    progress(0, 1, filename)

    result = dl.download_file(urls, target, min_size=500 * 1024)
    if not result.ok:
        return False, (f"下载失败：{result.error}\n"
                       f"  尝试过：\n"
                       + "\n".join(f"    {u}" for u in urls))

    progress(1, 1, filename)
    return True, f"Paper {mc_version} 构建 #{build_id} 已安装到 server.jar"


# ============================================================
#  Purpur：官方 → BMCLAPI → FastMirror
# ============================================================
def _install_purpur(dl, mc_version, build_id, server_dir,
                    proxy, log, progress, prefer="official"):
    filename = f"purpur-{mc_version}-{build_id}.jar"
    urls = order_urls(
        [f"{PURPUR_API}/purpur/{mc_version}/{build_id}/download"],
        [f"{PURPUR_API_MIRROR}/{mc_version}/{build_id}/download"],
        prefer,
    )

    fm_url = _fm_get_download_url(
        dl, "purpur", mc_version, f"build{build_id}")
    if fm_url:
        urls.append(fm_url)
        log(f"  已加入 FastMirror 兜底源", "info")

    target = server_dir / "server.jar"
    log(f"下载 Purpur {mc_version} 构建 #{build_id}", "info")
    progress(0, 1, filename)

    result = dl.download_file(urls, target, min_size=500 * 1024)
    if not result.ok:
        return False, (f"下载失败：{result.error}\n"
                       f"  尝试过：\n"
                       + "\n".join(f"    {u}" for u in urls))

    progress(1, 1, filename)
    return True, f"Purpur {mc_version} 构建 #{build_id} 已安装到 server.jar"


# ============================================================
#  Fabric
# ============================================================
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

    result = dl.download_file([url], target, min_size=100 * 1024)
    if not result.ok:
        return False, f"下载失败：{result.error}"

    progress(1, 1, "fabric-server-launch.jar")
    return True, "Fabric 已安装到 server.jar（首次启动会自动下载 MC 服务端）"


# ============================================================
#  Quilt
# ============================================================
def _install_quilt(dl, mc_version, loader_version, server_dir, log, progress):
    installer_url = ("https://quiltmc.org/api/v1/"
                     "download-latest-installer/java-universal")
    installer_path = server_dir / "quilt-installer.jar"

    log("下载 Quilt Installer…", "info")
    progress(0, 3, "quilt-installer.jar")
    result = dl.download_file([installer_url], installer_path,
                              min_size=100 * 1024)
    if not result.ok:
        return False, f"下载 Installer 失败：{result.error}"

    return _run_installer(
        installer_path, server_dir,
        ["install", "server", mc_version,
         "--loader-version", loader_version, "--download-server"],
        "Quilt", log, progress, delete_after=True)


# ============================================================
#  Forge / NeoForge
# ============================================================
def _install_forge_like(dl, loader, mc_version, loader_version,
                        server_dir, java_path, log, progress,
                        prefer="official"):
    if loader == "forge":
        urls = order_urls(
            [(f"{FORGE_MAVEN}/net/minecraftforge/forge/"
              f"{loader_version}/"
              f"forge-{loader_version}-installer.jar")],
            [(f"{FORGE_MAVEN_MIRROR}/net/minecraftforge/forge/"
              f"{loader_version}/"
              f"forge-{loader_version}-installer.jar")],
            prefer,
        )
        label = "Forge"
    else:
        urls = [
            (f"{NEOFORGE_MAVEN}/net/neoforged/neoforge/"
             f"{loader_version}/"
             f"neoforge-{loader_version}-installer.jar"),
        ]
        label = "NeoForge"

    installer_path = server_dir / f"{loader}-installer.jar"
    log(f"下载 {label} Installer…", "info")
    progress(0, 2, installer_path.name)

    result = dl.download_file(urls, installer_path, min_size=100 * 1024)
    if not result.ok:
        return False, (f"下载 Installer 失败：{result.error}\n"
                       f"  尝试过：\n"
                       + "\n".join(f"    {u}" for u in urls))

    extra_jvm_args = []
    if loader == "neoforge":
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