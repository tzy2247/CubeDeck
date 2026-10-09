"""Modrinth 商店实现。"""
from core.store_base import (
    BaseStoreProvider, StoreProject, StoreFile, StoreDependency,
)
from core.modrinth import ModrinthClient
from core.downloader import Downloader


class ModrinthProvider(BaseStoreProvider):
    name = "modrinth"
    display_name = "Modrinth"

    def __init__(self, proxy=None, api_base=None, verify_ssl=False,
                 downloader=None):
        self.client = ModrinthClient(
            proxy=proxy, api_base=api_base, verify_ssl=verify_ssl)
        self.downloader = downloader or Downloader(
            proxy=proxy, verify_ssl=verify_ssl)

    def search(self, query="", project_type="mod",
               game_version=None, loader=None,
               index="relevance", offset=0, limit=20):
        raw = self.client.search(
            query=query, project_type=project_type,
            game_version=game_version, loader=loader,
            index=index, offset=offset, limit=limit)

        hits = []
        for h in raw.get("hits", []):
            hits.append(StoreProject(
                source="modrinth",
                project_id=h.get("project_id", ""),
                slug=h.get("slug", ""),
                title=h.get("title", ""),
                description=h.get("description", ""),
                author=h.get("author", ""),
                downloads=h.get("downloads", 0),
                follows=h.get("follows", 0),
                icon_url=h.get("icon_url", ""),
                latest_versions=h.get("versions", [])[-5:],
                client_side=h.get("client_side", ""),
                server_side=h.get("server_side", ""),
                categories=h.get("categories", []),
                raw=h,
            ))

        return {"hits": hits, "total_hits": raw.get("total_hits", 0)}

    def get_project(self, project_id):
        raw = self.client.get_project(project_id)
        return StoreProject(
            source="modrinth",
            project_id=raw.get("id", ""),
            slug=raw.get("slug", ""),
            title=raw.get("title", ""),
            description=raw.get("description", ""),
            downloads=raw.get("downloads", 0),
            follows=raw.get("followers", 0),
            icon_url=raw.get("icon_url", ""),
            client_side=raw.get("client_side", ""),
            server_side=raw.get("server_side", ""),
            categories=raw.get("categories", []),
            raw=raw,
        )

    def get_files(self, project_id, game_version=None, loader=None):
        raw_versions = self.client.get_versions(
            project_id, game_version=game_version, loader=loader)

        files = []
        for v in raw_versions:
            # 解析依赖
            deps = []
            for d in v.get("dependencies", []):
                deps.append(StoreDependency(
                    project_id=d.get("project_id", "") or "",
                    version_id=d.get("version_id", "") or "",
                    dependency_type=d.get("dependency_type", "required"),
                ))

            for f in v.get("files", []):
                # 收集所有下载 URL（主 URL + 备用）
                fallback_urls = []
                if f.get("url"):
                    fallback_urls.append(f["url"])

                files.append(StoreFile(
                    file_id=f.get("hashes", {}).get("sha1", ""),
                    filename=f.get("filename", ""),
                    download_url=f.get("url", ""),
                    size=f.get("size", 0),
                    game_versions=v.get("game_versions", []),
                    loaders=v.get("loaders", []),
                    release_type=v.get("version_type", "release"),
                    dependencies=deps,
                    fallback_urls=fallback_urls,
                ))
        return files

    def download(self, url, dest_path, progress_callback=None):
        urls = [url] if isinstance(url, str) else list(url)
        result = self.downloader.download_file(
            urls, dest_path, progress_callback)
        if not result.ok:
            raise RuntimeError(result.error)
        return dest_path

    def test_connection(self):
        return self.client.test_connection()