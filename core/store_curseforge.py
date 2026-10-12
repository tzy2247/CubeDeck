"""CurseForge 商店实现。

关键差异：
- 官方 API 需要 API Key（X-Api-Key 头）
- 默认走 MCIM 镜像，无需 Key；用户可自定义 API 地址
- Minecraft 的 gameId = 432，模组 classId = 6
- 文件下载 URL 可能为 null（作者关闭第三方分发），需要用 CDN 拼接
"""
import json
import time
import requests
from pathlib import Path

from core.store_base import BaseStoreProvider, StoreProject, StoreFile


# ============================================================
#  常量
# ============================================================
CF_API_BASE_OFFICIAL = "https://api.curseforge.com/v1"

CF_MIRRORS = [
    ("MCIM 镜像", "https://mod.mcimirror.top/curseforge/v1"),
]

CF_DEFAULT_API_BASE = CF_MIRRORS[0][1]

CF_GAME_ID_MINECRAFT = 432
CF_CLASS_MODS = 6
CF_CLASS_MODPACKS = 4471
CF_CLASS_RESOURCEPACKS = 12

# 加载器映射：内部名 → CurseForge 的 modLoaderType
LOADER_TO_CF = {
    "forge": 1,
    "fabric": 4,
    "quilt": 5,
    "neoforge": 6,
}

USER_AGENT = "CubeDeck/0.1.1"


class CurseForgeProvider(BaseStoreProvider):
    name = "curseforge"
    display_name = "CurseForge"

    def __init__(self, api_key="", timeout=30, proxy=None,
                 verify_ssl=False, api_base=None):
        self.api_key = api_key.strip()
        self.timeout = timeout
        # ★ 决定基础地址：用户自定义 > 默认镜像
        if api_base:
            self.api_base = api_base.rstrip("/")
        else:
            self.api_base = CF_DEFAULT_API_BASE

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
        if not verify_ssl:
            self.session.verify = False
            try:
                import urllib3
                urllib3.disable_warnings()
            except Exception:
                pass

    # ========================================================
    #  内部请求
    # ========================================================
    def _get(self, path, params=None):
        # ★ 官方地址必须带 Key；镜像地址允许不带
        is_official = (self.api_base == CF_API_BASE_OFFICIAL)
        if is_official and not self.api_key:
            raise RuntimeError(
                "使用官方 CurseForge API 需要 API Key。\n"
                "请到 设置 → CurseForge 里填写，或使用内置镜像。\n"
                "申请地址：https://console.curseforge.com/#/api-keys")

        url = f"{self.api_base}{path}"
        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        try:
            resp = self.session.get(
                url, params=params, headers=headers,
                timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", data)
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else 0
            if code == 403:
                raise RuntimeError(
                    "CurseForge 403 权限拒绝。\n"
                    "可能 API Key 无效或已过期，或镜像拒绝该请求。")
            if code == 401:
                raise RuntimeError(
                    "CurseForge 401 未授权。\n"
                    "如果使用官方 API，请填写有效的 API Key。")
            if code == 429:
                raise RuntimeError("CurseForge 请求过于频繁，请稍后重试。")
            raise RuntimeError(f"CurseForge HTTP {code}")
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"连接 CurseForge 失败：{e}")
        except Exception as e:
            raise RuntimeError(f"请求 CurseForge 失败：{e}")

    def _mirror_name(self):
        """返回当前使用的镜像名称，用于状态提示。"""
        for name, url in CF_MIRRORS:
            if url == self.api_base:
                return name
        if self.api_base == CF_API_BASE_OFFICIAL:
            return "官方"
        return "自定义"

    # ========================================================
    #  搜索
    # ========================================================
    def search(self, query="", project_type="mod",
               game_version=None, loader=None,
               index="relevance", offset=0, limit=20):
        class_map = {
            "mod": CF_CLASS_MODS,
            "modpack": CF_CLASS_MODPACKS,
            "resourcepack": CF_CLASS_RESOURCEPACKS,
            "plugin": CF_CLASS_MODS,
        }
        class_id = class_map.get(project_type, CF_CLASS_MODS)

        sort_map = {
            "relevance": 2,
            "downloads": 6,
            "follows": 2,
            "newest": 11,
            "updated": 3,
        }
        sort_field = sort_map.get(index, 2)

        params = {
            "gameId": CF_GAME_ID_MINECRAFT,
            "classId": class_id,
            "searchFilter": query,
            "sortField": sort_field,
            "sortOrder": "desc",
            "index": offset,
            "pageSize": limit,
        }

        if game_version:
            params["gameVersion"] = game_version

        if loader and loader in LOADER_TO_CF:
            params["modLoaderType"] = LOADER_TO_CF[loader]

        raw = self._get("/mods/search", params)

        hits = []
        for m in raw or []:
            cats = [c.get("name", "").lower()
                    for c in m.get("categories", [])]
            if "client" in cats:
                client_side = "required"
            elif any("server" in c for c in cats):
                client_side = "optional"
            else:
                client_side = ""

            hits.append(StoreProject(
                source="curseforge",
                project_id=str(m.get("id", "")),
                slug=m.get("slug", ""),
                title=m.get("name", ""),
                description=m.get("summary", ""),
                author=", ".join(
                    a.get("name", "") for a in m.get("authors", [])),
                downloads=m.get("downloadCount", 0),
                follows=m.get("thumbsUpCount", 0),
                icon_url=(m.get("logo") or {}).get("thumbnailUrl", ""),
                latest_versions=[v for v in m.get(
                    "latestFilesIndexes", [])[:5]
                    if v.get("gameVersion")][:5],
                client_side=client_side,
                server_side="",
                categories=[c.get("name", "")
                            for c in m.get("categories", [])],
                raw=m,
            ))

        return {
            "hits": hits,
            "total_hits": offset + len(hits) + (1 if len(hits) == limit else 0),
        }

    # ========================================================
    #  项目详情
    # ========================================================
    def get_project(self, project_id):
        raw = self._get(f"/mods/{project_id}")
        return StoreProject(
            source="curseforge",
            project_id=str(raw.get("id", "")),
            slug=raw.get("slug", ""),
            title=raw.get("name", ""),
            description=raw.get("summary", ""),
            downloads=raw.get("downloadCount", 0),
            follows=raw.get("thumbsUpCount", 0),
            icon_url=(raw.get("logo") or {}).get("thumbnailUrl", ""),
            categories=[c.get("name", "")
                        for c in raw.get("categories", [])],
            raw=raw,
        )

    # ========================================================
    #  文件列表
    # ========================================================
    def get_files(self, project_id, game_version=None, loader=None):
        params = {"pageSize": 50}
        if game_version:
            params["gameVersion"] = game_version
        if loader and loader in LOADER_TO_CF:
            params["modLoaderType"] = LOADER_TO_CF[loader]

        raw = self._get(f"/mods/{project_id}/files", params)

        files = []
        for f in raw or []:
            download_url = f.get("downloadUrl")

            if not download_url:
                file_id = f.get("id", 0)
                filename = f.get("fileName", "")
                if file_id and filename:
                    id_str = str(file_id)
                    if len(id_str) >= 4:
                        download_url = (
                            f"https://edge.forgecdn.net/files/"
                            f"{id_str[:4]}/{id_str[4:]}/{filename}")
                    else:
                        continue
                else:
                    continue

            files.append(StoreFile(
                file_id=str(f.get("id", "")),
                filename=f.get("fileName", ""),
                download_url=download_url,
                size=f.get("fileLength", 0),
                game_versions=f.get("gameVersions", []),
                loaders=[],
                release_type={
                    1: "release", 2: "beta", 3: "alpha",
                }.get(f.get("releaseType", 1), "release"),
                dependencies=[],
                fallback_urls=[download_url],
            ))
        return files

    # ========================================================
    #  下载
    # ========================================================
    def download(self, url, dest_path, progress_callback=None):
        from core.downloader import Downloader
        if not hasattr(self, "_downloader"):
            self._downloader = Downloader(
                proxy=self.session.proxies.get("https") if self.session.proxies else None,
                verify_ssl=self.session.verify if isinstance(self.session.verify, bool) else False,
            )
        urls = [url] if isinstance(url, str) else list(url)
        result = self._downloader.download_file(
            urls, dest_path, progress_callback)
        if not result.ok:
            raise RuntimeError(result.error)
        return dest_path

    # ========================================================
    #  测试连接
    # ========================================================
    def test_connection(self):
        # ★ 镜像不强制要求 Key
        is_official = (self.api_base == CF_API_BASE_OFFICIAL)
        if is_official and not self.api_key:
            return False, "使用官方 API 需要配置 API Key"

        try:
            self._get("/games", {"pageSize": 1})
            return True, f"连接正常（{self._mirror_name()}）"
        except Exception as e:
            return False, str(e)