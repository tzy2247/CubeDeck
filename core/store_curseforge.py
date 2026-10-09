"""CurseForge 商店实现。

关键差异：
- 需要 API Key（X-Api-Key 头）
- Minecraft 的 gameId = 432，模组 classId = 6
- 文件下载 URL 可能为 null（作者关闭第三方分发），需要用 CDN 拼接
- API Key 可以让用户自己填，也可以用内置的（有泄露风险）
"""
import json
import time
import requests
from pathlib import Path

from core.store_base import BaseStoreProvider, StoreProject, StoreFile


# ============================================================
#  常量
# ============================================================
CF_API_BASE = "https://api.curseforge.com/v1"
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
                 verify_ssl=False):
        self.api_key = api_key.strip()
        self.timeout = timeout
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
        if not self.api_key:
            raise RuntimeError(
                "CurseForge 需要 API Key。\n"
                "请到 设置 → 插件商店 里填写。\n"
                "申请地址：https://console.curseforge.com/#/api-keys")

        url = f"{CF_API_BASE}{path}"
        headers = {"x-api-key": self.api_key}

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
                    "可能 API Key 无效或已过期。")
            if code == 401:
                raise RuntimeError("CurseForge API Key 无效。")
            if code == 429:
                raise RuntimeError("CurseForge 请求过于频繁，请稍后重试。")
            raise RuntimeError(f"CurseForge HTTP {code}")
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(f"连接 CurseForge 失败：{e}")
        except Exception as e:
            raise RuntimeError(f"请求 CurseForge 失败：{e}")

    # ========================================================
    #  搜索
    # ========================================================
    def search(self, query="", project_type="mod",
               game_version=None, loader=None,
               index="relevance", offset=0, limit=20):
        # project_type → classId
        class_map = {
            "mod": CF_CLASS_MODS,
            "modpack": CF_CLASS_MODPACKS,
            "resourcepack": CF_CLASS_RESOURCEPACKS,
            "plugin": CF_CLASS_MODS,   # CurseForge 没有单独的 plugin 分类
        }
        class_id = class_map.get(project_type, CF_CLASS_MODS)

        # index → sortField
        # CurseForge 的 sortField 见文档：2=Popularity, 6=TotalDownloads
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
            # CurseForge 没有直接的 client_side / server_side 字段，
            # 通过 categories 判断
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

        # CurseForge 的搜索不返回 total_hits，用 pagination
        # 简单返回当前页数量，下一页按钮的判断稍后处理
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
                        # 拼接 CDN URL 作为主 URL
                        download_url = (
                            f"https://edge.forgecdn.net/files/"
                            f"{id_str[:4]}/{id_str[4:]}/{filename}")
                    else:
                        continue
                else:
                    continue

            # CurseForge 没有暴露依赖字段，置空
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
                fallback_urls=[download_url],  # ★
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
        if not self.api_key:
            return False, "未配置 API Key"
        try:
            # 请求一个最小的接口测试
            self._get("/games", {"pageSize": 1})
            return True, "连接正常"
        except Exception as e:
            return False, str(e)