"""统一下载层：多 URL 回退、自动重试、进度回调。

稳定性策略：
- 连接错误 / 超时 / 5xx：重试（最多 max_retries 次，退避 1s/2s/4s）
- 4xx / 非 JSON 响应：不重试，直接换下一个 URL
- 下载完成后校验文件大小，过小视为失败
"""
import time
import requests
from pathlib import Path
from typing import Callable, Optional


USER_AGENT = "CubeDeck/0.1.0"
DEFAULT_TIMEOUT = 45
MIN_DOWNLOAD_SIZE = 100 * 1024


class DownloadResult:
    def __init__(self, ok, url="", error="", size=0):
        self.ok = ok
        self.url = url
        self.error = error
        self.size = size

    def __bool__(self):
        return self.ok


class Downloader:
    """统一下载器。所有商店共用。"""

    def __init__(self, proxy=None, verify_ssl=False,
                 timeout=DEFAULT_TIMEOUT, max_retries=3):
        self.timeout = timeout
        self.max_retries = max_retries

        self.session = requests.Session()
        # ★ 禁用 netrc / 环境变量查找（Python 3.12 GC abort 问题）
        self.session.trust_env = False
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            # ★ 不发送 Accept-Encoding，让 requests 自行处理
            #   避免某些镜像返回 gzip 但不声明 Content-Encoding
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

    @staticmethod
    def _backoff(attempt):
        """退避：1s → 2s → 4s"""
        return 1.0 * (2 ** attempt)

    def get_json(self, urls, params=None, headers=None):
        """
        urls: 字符串或列表。按顺序尝试。
        返回 (data, used_url) 或抛异常。
        """
        if isinstance(urls, str):
            urls = [urls]

        last_error = None
        for url in urls:
            for attempt in range(self.max_retries + 1):
                try:
                    resp = self.session.get(
                        url, params=params, headers=headers,
                        timeout=self.timeout, allow_redirects=True)
                    resp.raise_for_status()

                    # ★ 区分"HTTP 错误"和"响应不是 JSON"
                    try:
                        return resp.json(), url
                    except ValueError:
                        body = (resp.text or "")[:150].replace("\n", " ")
                        last_error = (
                            f"非 JSON 响应（HTTP {resp.status_code}，"
                            f"来自 {url}）：{body!r}")
                        break

                except requests.exceptions.HTTPError as e:
                    code = e.response.status_code if e.response else 0
                    last_error = f"HTTP {code}（来自 {url}）"
                    if code < 500:
                        break

                except requests.exceptions.ConnectionError as e:
                    last_error = f"连接错误（{url}）：{e}"

                except requests.exceptions.Timeout:
                    last_error = f"超时（{url}）"

                except Exception as e:
                    last_error = f"{url}：{e}"

                if attempt < self.max_retries:
                    time.sleep(self._backoff(attempt))

        raise RuntimeError(last_error or "所有 URL 均不可用")

    def download_file(self, urls, dest_path,
                      progress_callback: Optional[Callable] = None,
                      headers=None,
                      min_size: int = MIN_DOWNLOAD_SIZE) -> DownloadResult:
        if isinstance(urls, str):
            urls = [urls]

        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        last_error = None

        for url in urls:
            for attempt in range(self.max_retries + 1):
                try:
                    if dest_path.exists():
                        try:
                            dest_path.unlink()
                        except Exception:
                            pass

                    with self.session.get(
                            url, stream=True, timeout=180,
                            headers=headers, allow_redirects=True) as resp:
                        resp.raise_for_status()
                        total = int(resp.headers.get("Content-Length", 0))
                        downloaded = 0

                        with open(dest_path, "wb") as f:
                            for chunk in resp.iter_content(
                                    chunk_size=64 * 1024):
                                if not chunk:
                                    continue
                                f.write(chunk)
                                downloaded += len(chunk)
                                if progress_callback:
                                    try:
                                        progress_callback(downloaded, total)
                                    except Exception:
                                        pass

                    actual_size = dest_path.stat().st_size
                    if min_size > 0 and actual_size < min_size:
                        last_error = (
                            f"下载内容异常（{actual_size} 字节 < "
                            f"{min_size}，来自 {url}）")
                        try:
                            dest_path.unlink()
                        except Exception:
                            pass
                        break

                    return DownloadResult(
                        ok=True, url=url, size=actual_size)

                except requests.exceptions.HTTPError as e:
                    code = e.response.status_code if e.response else 0
                    last_error = f"HTTP {code}（来自 {url}）"
                    if code < 500:
                        break

                except requests.exceptions.ConnectionError as e:
                    last_error = f"连接错误（{url}）：{e}"

                except requests.exceptions.Timeout:
                    last_error = f"超时（{url}）"

                except Exception as e:
                    last_error = f"{url}：{e}"

                if attempt < self.max_retries:
                    time.sleep(self._backoff(attempt))

        return DownloadResult(ok=False, error=last_error)