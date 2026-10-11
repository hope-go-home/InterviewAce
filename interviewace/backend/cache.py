"""进程内 TTL + LRU 缓存（线程安全）

用途：
- Embedding 缓存：同一句话不重复调 API（问答/练习/评测的 query 高度重复）
- LLM 响应缓存：对 temperature=0 的确定性调用（评分/裁判）按 prompt hash 缓存

为什么不引 Redis：当前单机单进程，进程内缓存足够；多实例部署时再换 Redis。
"""
import hashlib
import threading
import time
from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    """带 TTL 的 LRU 缓存，线程安全"""

    def __init__(self, maxsize: int = 1024, ttl: float = 3600.0, name: str = "cache"):
        self.maxsize = maxsize
        self.ttl = ttl
        self.name = name
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                self._misses += 1
                return None
            ts, val = item
            if time.time() - ts >= self.ttl:
                del self._data[key]
                self._misses += 1
                return None
            self._data.move_to_end(key)
            self._hits += 1
            return val

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "name": self.name, "size": len(self._data),
                "hits": self._hits, "misses": self._misses,
                "hit_rate": round(self._hits / total, 3) if total else 0.0,
            }

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


def hash_key(*parts: Any) -> str:
    """把任意输入拼成稳定的缓存键"""
    raw = "||".join(str(p) for p in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ---------------- 全局缓存实例 ----------------

# 稠密查询向量（同一句问题重复问很常见）
dense_cache = TTLCache(maxsize=2048, ttl=3600, name="dense_embedding")
# 稀疏查询向量
sparse_cache = TTLCache(maxsize=2048, ttl=3600, name="sparse_embedding")
# 确定性 LLM 调用（评分/裁判，temperature=0）
llm_cache = TTLCache(maxsize=1024, ttl=1800, name="llm_response")


def all_stats() -> list[dict]:
    return [dense_cache.stats(), sparse_cache.stats(), llm_cache.stats()]
