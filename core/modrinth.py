"""Modrinth API 客户端，基于 requests。

相比 urllib，requests 的 HTTP 头更完整、TLS 兼容性更好，
能绕过 urllib 常见的 RemoteDisconnected 问题。
"""
import json
import time
from pathlib import Path

try:
    import requests
    from requests.adapters import HTTPAdapter
except ImportError:
    raise ImportError("需要安装 requests：pip install requests")


# ============================================================
#  镜像站列表（按优先级）
# ============================================================
MIRRORS = [
    ("镜像A",  "https://mod.mcimirror.top/modrinth/v2"),
]

DEFAULT_API_BASE = MIRRORS[0][1]

USER_AGENT = "CubeDeck/0.1.0"

DEFAULT_TIMEOUT = 120
MAX_DEBUG_LEN = 500


class ModrinthClient:
    def __init__(self, timeout=DEFAULT_TIMEOUT, proxy=None,
                 api_base=None, user_agent=None, verify_ssl=False,
                 max_retries=2, auto_fallback=True):
        self.timeout = timeout
        self.proxy = proxy
        self.user_agent = user_agent or USER_AGENT
        self.verify_ssl = verify_ssl
        self.max_retries = max_retries
        self.auto_fallback = auto_fallback

        if api_base:
            self.mirrors = [("自定义", api_base.rstrip("/"))]
        else:
            self.mirrors = list(MIRRORS)

        self.api_base = self.mirrors[0][1]

        # ---- requests session ----
        self.session = requests.Session()

        # 完整的浏览器风格 header
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        })

        if proxy:
            self.session.proxies = {
                "http": proxy,
                "https": proxy,
            }

        if not verify_ssl:
            self.session.verify = False
            try:
                import urllib3
                urllib3.disable_warnings(
                    urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass

        adapter = HTTPAdapter(
            pool_connections=4,
            pool_maxsize=8,
            max_retries=0,
        )
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ========================================================
    #  内部请求
    # ========================================================
    def _request_once(self, base_url, path, params=None):
        url = f"{base_url}{path}"
        resp = self.session.get(
            url, params=params, timeout=self.timeout)

        # 先看 HTTP 状态
        if resp.status_code >= 400:
            # 拿一段响应体帮助诊断
            body = self._extract_body(resp)
            raise requests.exceptions.HTTPError(
                f"HTTP {resp.status_code}: {body}",
                response=resp)

        # ★ 关键：检测非 JSON 响应
        text = resp.text
        if not text or not text.strip():
            raise RuntimeError(
                f"服务器返回空响应\n"
                f"  URL: {url}\n"
                f"  Content-Type: "
                f"{resp.headers.get('Content-Type', '(无)')}\n"
                f"  可能原因：镜像故障、反爬拦截、响应被中间层清空")

        ctype = resp.headers.get("Content-Type", "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 不是 JSON，把原文带出来
            preview = text[:MAX_DEBUG_LEN].replace("\n", " ")
            raise RuntimeError(
                f"响应不是合法 JSON\n"
                f"  URL: {url}\n"
                f"  Content-Type: {ctype}\n"
                f"  内容预览: {preview}")

    @staticmethod
    def _extract_body(resp, limit=MAX_DEBUG_LEN):
        """从响应里提取一段可读文本用于诊断。"""
        try:
            text = resp.text or ""
        except Exception:
            return "(无法读取响应体)"
        text = text.strip().replace("\n", " ")
        return text[:limit] if text else "(空)"

    def _request(self, path, params=None):
        last_error = None

        for idx, (name, base_url) in enumerate(self.mirrors):
            for attempt in range(self.max_retries + 1):
                try:
                    result = self._request_once(base_url, path, params)
                    self.api_base = base_url
                    return result

                except requests.exceptions.HTTPError as e:
                    code = e.response.status_code if e.response is not None else 0
                    body = self._extract_body(e.response) if e.response else ""
                    last_error = self._format_http_error(code, name, body)
                    # 4xx 不重试，直接换镜像
                    if 400 <= code < 500:
                        break
                    if attempt < self.max_retries:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    break

                except requests.exceptions.SSLError as e:
                    last_error = f"[{name}] SSL 错误：{e}"
                    break

                except requests.exceptions.ProxyError as e:
                    last_error = (f"[{name}] 代理错误：{e}\n"
                                  f"  请检查代理地址和端口。")
                    break

                except requests.exceptions.ConnectionError as e:
                    last_error = self._format_connection_error(e, name)
                    if attempt < self.max_retries:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    break

                except requests.exceptions.Timeout:
                    last_error = f"[{name}] 请求超时（{self.timeout}s）"
                    if attempt < self.max_retries:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    break

                except RuntimeError as e:
                    # 来自 _request_once 的 JSON 解析 / 空响应错误
                    last_error = f"[{name}] {e}"
                    # 不重试，直接下一个镜像
                    break

                except Exception as e:
                    last_error = f"[{name}] 请求失败：{e}"
                    if attempt < self.max_retries:
                        time.sleep(1.0 * (attempt + 1))
                        continue
                    break

            # 尝试下一个镜像
            if not self.auto_fallback:
                break

        raise RuntimeError(last_error or "所有镜像均不可用")

    # ========================================================
    #  错误格式化
    # ========================================================
    @staticmethod
    def _format_http_error(code, name, body=""):
        snippet = f"\n  {body[:200]}" if body else ""

        if code == 403:
            return (f"[{name}] 403 权限拒绝\n"
                    f"  1. User-Agent 可能不在镜像白名单\n"
                    f"  2. 请求频率过高被限流"
                    f"{snippet}")
        if code == 404:
            return f"[{name}] 404 接口不存在{snippet}"
        if code == 429:
            return f"[{name}] 429 请求过频繁，请稍后重试"
        if code >= 500:
            return (f"[{name}] 服务器错误 {code}，镜像可能故障"
                    f"{snippet}")
        return f"[{name}] HTTP {code}{snippet}"

    @staticmethod
    def _format_connection_error(e, name):
        msg = str(e)
        low = msg.lower()

        if "remote end closed" in low or "connection aborted" in low:
            return f"[{name}] 服务器主动关闭连接"
        if "timed out" in low:
            return f"[{name}] 连接超时"
        if "connection refused" in low:
            return f"[{name}] 连接被拒绝，镜像可能已下线"
        if "name or service not known" in low:
            return f"[{name}] 域名解析失败"
        return f"[{name}] 连接错误：{msg[:200]}"

    # ========================================================
    #  公开 API
    # ========================================================
    def search(self, query="", project_type="plugin",
               game_version=None, loader=None,
               index="relevance", offset=0, limit=20):
        facets = []

        if project_type:
            facets.append([f"project_type:{project_type}"])

        if loader:
            facets.append([f"categories:{loader}"])

        if game_version:
            facets.append([f"versions:{game_version}"])

        params = {
            "query": query,
            "offset": offset,
            "limit": limit,
            "index": index,
        }
        if facets:
            params["facets"] = json.dumps(facets)

        return self._request("/search", params)

    def get_project(self, project_id_or_slug):
        return self._request(f"/project/{project_id_or_slug}")

    def get_versions(self, project_id_or_slug, game_version=None,
                     loader=None):
        params = {}
        if game_version:
            params["game_versions"] = f'["{game_version}"]'
        if loader:
            params["loaders"] = f'["{loader}"]'
        return self._request(
            f"/project/{project_id_or_slug}/version", params)

    def get_version(self, version_id):
        return self._request(f"/version/{version_id}")

    def test_connection(self):
        try:
            self.search(query="", project_type="plugin", limit=1)
            return True, f"连接正常（{self._current_mirror_name()}）"
        except Exception as e:
            return False, str(e)

    def _current_mirror_name(self):
        for name, url in self.mirrors:
            if url == self.api_base:
                return name
        return "自定义"

    # ========================================================
    #  下载
    # ========================================================
    def download(self, url, dest_path, progress_callback=None):
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                with self.session.get(
                        url, stream=True,
                        timeout=90, allow_redirects=True) as resp:
                    resp.raise_for_status()
                    total = int(resp.headers.get("Content-Length", 0))
                    downloaded = 0

                    with open(dest_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=64 * 1024):
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)
                            if progress_callback:
                                try:
                                    progress_callback(downloaded, total)
                                except Exception:
                                    pass

                return dest_path

            except requests.exceptions.HTTPError as e:
                code = e.response.status_code if e.response else 0
                last_error = f"下载失败 HTTP {code}"
                if code in (403, 404):
                    break
            except requests.exceptions.ConnectionError as e:
                last_error = f"下载连接错误：{e}"
            except Exception as e:
                last_error = f"下载失败：{e}"

            if attempt < self.max_retries:
                time.sleep(1.5 * (attempt + 1))

        raise RuntimeError(last_error or "下载失败")