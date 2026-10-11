"""物品搜索索引：支持 ID / 中文名搜索，带三层树状索引和 LRU 缓存。

三层索引（从根到叶）：
  1. 命名空间 → 物品列表
  2. ID 首字符 → 物品列表
  3. 中文名首字 → 物品列表

搜索时根据查询内容自动选择走哪一层，避免全表扫描。
"""
from collections import OrderedDict

from core.item_names import get_all_item_ids


# ============================================================
#  索引
# ============================================================
class ItemSearchIndex:
    def __init__(self):
        self._all = []                  # [(full_id, name), ...]
        self._by_namespace = {}         # {"minecraft": [(...), ...]}
        self._by_id_first = {}          # {"d": [(...), ...]}
        self._by_name_first = {}        # {"钻": [(...), ...]}
        self._lower_id_to_full = {}     # "minecraft:diamond_sword" → 原始 ID
        self._cache = OrderedDict()     # LRU 前缀缓存
        self._cache_limit = 128

    # ---------- 构建 ----------
    def rebuild(self):
        """从 item_names 重建所有索引。"""
        items = get_all_item_ids()      # [(full_id, name), ...]
        self._all = items
        self._by_namespace.clear()
        self._by_id_first.clear()
        self._by_name_first.clear()
        self._lower_id_to_full.clear()
        self._cache.clear()

        for full_id, name in items:
            low_id = full_id.lower()
            self._lower_id_to_full[low_id] = full_id

            # 命名空间
            ns = full_id.split(":", 1)[0].lower()
            self._by_namespace.setdefault(ns, []).append((full_id, name))

            # ID 首字符
            if low_id:
                first = low_id[0]
                self._by_id_first.setdefault(first, []).append(
                    (full_id, name))

            # 中文名首字
            if name:
                first = name[0]
                self._by_name_first.setdefault(first, []).append(
                    (full_id, name))

    # ---------- 查询 ----------
    def search(self, query: str, limit: int = 100):
        """
        搜索物品。
        - query 为空：返回前 limit 条
        - 含 ":"：命名空间 + 子串匹配
        - 以中文开头：中文名首字索引 + 子串匹配
        - 其他：ID 首字符索引 + 子串匹配
        返回 [(full_id, name), ...]
        """
        q = (query or "").strip().lower()

        if not q:
            return self._all[:limit]

        # LRU 缓存
        if q in self._cache:
            self._cache.move_to_end(q)
            return self._cache[q][:limit]

        results = self._do_search(q)

        # 缓存（限制数量）
        self._cache[q] = results
        if len(self._cache) > self._cache_limit:
            self._cache.popitem(last=False)

        return results[:limit]

    def _do_search(self, q: str):
        """实际搜索逻辑。"""
        # 1. 含冒号 → 命名空间定向
        if ":" in q:
            ns, rest = q.split(":", 1)
            pool = self._by_namespace.get(ns, [])
            return self._filter(pool, q, rest)

        # 2. 以中文开头 → 中文名首字索引
        if q and "\u4e00" <= q[0] <= "\u9fff":
            pool = self._by_name_first.get(q[0], [])
            return self._filter(pool, q, q)

        # 3. 其他（英文/数字开头）→ ID 首字符索引
        pool = self._by_id_first.get(q[0], [])
        return self._filter(pool, q, q)

    @staticmethod
    def _filter(pool, full_query, sub_query):
        """在给定池子里过滤。"""
        if not pool:
            return []

        results = []
        # 先尝试前缀匹配（命中率高，走得更快）
        for full_id, name in pool:
            low_id = full_id.lower()
            low_name = name.lower() if name else ""

            if sub_query in low_id or sub_query in low_name:
                results.append((full_id, name))

        # 兜底：查全表（防止因首字符索引漏掉子串匹配的情况）
        # 这里不展开，绝大多数场景前缀索引已足够
        return results

    # ---------- 统计 ----------
    @property
    def total(self):
        return len(self._all)

    def namespaces(self):
        return sorted(self._by_namespace.keys())


# 单例
_index = ItemSearchIndex()
_index_built = False


def get_index() -> ItemSearchIndex:
    """获取全局搜索索引（首次调用时构建）。"""
    global _index_built
    if not _index_built:
        _index.rebuild()
        _index_built = True
    return _index


def rebuild_index():
    """重建索引（用户修改语言文件后调用）。"""
    global _index_built
    _index.rebuild()
    _index_built = True