"""统一下载层：多 URL 回退、自动重试、进度回调。

参考 PCL 的 NetFile 设计：一次下载请求包含多个候选 URL，
按顺序尝试，任一成功即完成。
"""
import time
import requests
from pathlib import Path
from typing import Callable, Optional


USER_AGENT = "CubeDeck/0.1.0 (contact: 481045614@qq.com)"
DEFAULT_TIMEOUT = 30


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
                 timeout=DEFAULT_TIMEOUT, max_retries=2):
        self.timeout = timeout
        self.max_retries = max_retries

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
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
    #  GET JSON（多 URL 回退）
    # ========================================================
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
                        timeout=self.timeout)
                    resp.raise_for_status()
                    return resp.json(), url
                except requests.exceptions.HTTPError as e:
                    code = e.response.status_code if e.response else 0
                    last_error = f"HTTP {code}"
                    if code in (401, 403, 404):
                        break       # 不重试
                except requests.exceptions.ConnectionError as e:
                    last_error = f"连接错误：{e}"
                except requests.exceptions.Timeout:
                    last_error = f"超时"
                except Exception as e:
                    last_error = str(e)

                if attempt < self.max_retries:
                    time.sleep(0.8 * (attempt + 1))

        raise RuntimeError(last_error or "所有 URL 均不可用")

    # ========================================================
    #  下载文件（多 URL 回退）
    # ========================================================
    def download_file(self, urls, dest_path,
                      progress_callback: Optional[Callable] = None,
                      headers=None) -> DownloadResult:
        """
        urls: 字符串或列表。按顺序尝试。
        返回 DownloadResult。
        """
        if isinstance(urls, str):
            urls = [urls]

        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        last_error = None

        for url in urls:
            for attempt in range(self.max_retries + 1):
                try:
                    with self.session.get(
                            url, stream=True, timeout=90,
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

                    return DownloadResult(
                        ok=True, url=url, size=downloaded)
                except requests.exceptions.HTTPError as e:
                    code = e.response.status_code if e.response else 0
                    last_error = f"HTTP {code}"
                    if code in (401, 403, 404):
                        break
                except Exception as e:
                    last_error = str(e)

                if attempt < self.max_retries:
                    time.sleep(0.8 * (attempt + 1))

        return DownloadResult(ok=False, error=last_error)