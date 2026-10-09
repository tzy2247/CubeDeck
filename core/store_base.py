"""商店统一接口和数据模型。"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StoreProject:
    source: str
    project_id: str
    slug: str = ""
    title: str = ""
    description: str = ""
    author: str = ""
    downloads: int = 0
    follows: int = 0
    icon_url: str = ""
    latest_versions: list = field(default_factory=list)
    client_side: str = ""
    server_side: str = ""
    categories: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class StoreDependency:
    """依赖关系。"""
    project_id: str = ""
    version_id: str = ""
    dependency_type: str = "required"   # required / optional / incompatible / embedded


@dataclass
class StoreFile:
    file_id: str
    filename: str
    download_url: str
    size: int = 0
    game_versions: list = field(default_factory=list)
    loaders: list = field(default_factory=list)
    release_type: str = "release"
    dependencies: list = field(default_factory=list)   # [StoreDependency]
    fallback_urls: list = field(default_factory=list)  # 备用下载地址


class BaseStoreProvider:
    name = "base"
    display_name = "基础商店"

    def search(self, query="", project_type="mod",
               game_version=None, loader=None,
               index="relevance", offset=0, limit=20):
        raise NotImplementedError

    def get_project(self, project_id) -> Optional[StoreProject]:
        raise NotImplementedError

    def get_files(self, project_id, game_version=None,
                  loader=None) -> list:
        raise NotImplementedError

    def download(self, url, dest_path, progress_callback=None):
        raise NotImplementedError

    def test_connection(self):
        raise NotImplementedError