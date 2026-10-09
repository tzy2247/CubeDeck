"""多源商店管理器。"""
from core.store_modrinth import ModrinthProvider
from core.store_curseforge import CurseForgeProvider
from core.installer import ModInstaller
from core.downloader import Downloader


class StoreManager:
    def __init__(self, config, log_callback=None):
        self.config = config
        self.log = log_callback or (lambda m, t="info": None)
        self._providers = {}
        self._current_source = "modrinth"
        self._rebuild()

    def _rebuild(self):
        proxy = self.config.get("modrinth_proxy", "").strip() or None

        # 共享一个 Downloader（连接池复用）
        self._downloader = Downloader(
            proxy=proxy, verify_ssl=False)

        self._providers["modrinth"] = ModrinthProvider(
            proxy=proxy,
            api_base=self.config.get("modrinth_api_base", "").strip() or None,
            verify_ssl=False,
            downloader=self._downloader,
        )
        self._providers["curseforge"] = CurseForgeProvider(
            api_key=self.config.get("curseforge_api_key", "").strip(),
            timeout=30,
            proxy=proxy,
            verify_ssl=False,
        )
        # 每个 provider 一套 installer（因为 store 是 provider 绑定的）
        self._installers = {
            k: ModInstaller(p, self.log)
            for k, p in self._providers.items()
        }

    def reload(self):
        self._rebuild()

    # ---------- 源管理 ----------
    def set_source(self, source):
        if source not in self._providers:
            return False
        self._current_source = source
        return True

    def get_source(self):
        return self._current_source

    def list_sources(self):
        return [(k, v.display_name) for k, v in self._providers.items()]

    @property
    def provider(self):
        return self._providers[self._current_source]

    @property
    def installer(self):
        return self._installers[self._current_source]

    # ---------- 转发 ----------
    def search(self, *a, **kw):     return self.provider.search(*a, **kw)
    def get_project(self, *a):      return self.provider.get_project(*a)
    def get_files(self, *a, **kw):  return self.provider.get_files(*a, **kw)
    def download(self, *a, **kw):   return self.provider.download(*a, **kw)
    def test_connection(self):      return self.provider.test_connection()