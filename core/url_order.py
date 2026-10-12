"""根据用户偏好排序官方/镜像 URL。

用户可配置"下载源优先级"（download_prefer）：
  - "official"（默认）：官方源优先，镜像作为备用
  - "mirror"：镜像源优先，官方作为备用

无论选哪个，另一个都会保留在列表里作为兜底。
"""


def order_urls(official, mirror, prefer="official"):
    """
    返回排好序的 URL 列表。
    official / mirror 可以是字符串或字符串列表。
    """
    off_list = _normalize(official)
    mir_list = _normalize(mirror)

    if prefer == "mirror":
        return mir_list + off_list
    return off_list + mir_list


def _normalize(x):
    if not x:
        return []
    if isinstance(x, str):
        return [x]
    seen = set()
    result = []
    for u in x:
        if not u or u in seen:
            continue
        seen.add(u)
        result.append(u)
    return result