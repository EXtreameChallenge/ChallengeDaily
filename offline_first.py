"""
P261-P269: 离线优先架构
- P261: 本地存储引擎
- P262: 离线队列
- P263: 同步策略
- P264: 冲突解决
- P265: 数据预加载
- P266: 缓存层
- P267: 网络状态检测
- P268: 增量同步
- P269: 离线搜索引擎
"""
import logging, threading, json, time
from collections import deque, defaultdict
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class LocalStorage:
    """P261: 本地存储引擎"""
    def __init__(self):
        self._store: dict[str, Any] = {}
        self._lock = threading.Lock()
    def set(self, key: str, value: Any, ttl: int = 0) -> None:
        with self._lock:
            self._store[key] = {"value": value, "ttl": ttl, "created": time.time()}
    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._store.get(key)
            if not item: return None
            if item["ttl"] > 0 and time.time() - item["created"] > item["ttl"]:
                del self._store[key]; return None
            return item["value"]
    def delete(self, key: str) -> bool:
        with self._lock: return self._store.pop(key, None) is not None
    def keys(self) -> list[str]:
        with self._lock: return list(self._store.keys())
    def size(self) -> int:
        with self._lock: return len(self._store)

_storage = LocalStorage()


class OfflineQueue:
    """P262: 离线操作队列"""
    def __init__(self):
        self._queue: deque = deque(maxlen=1000)
        self._lock = threading.Lock()
    def enqueue(self, operation: str, data: dict) -> str:
        import uuid
        item_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._queue.append({"id": item_id, "op": operation, "data": data,
                               "status": "pending", "attempts": 0, "created": datetime.now().isoformat()})
        return item_id
    def dequeue(self) -> dict | None:
        with self._lock:
            if not self._queue: return None
            return self._queue.popleft()
    def peek(self, limit: int = 10) -> list[dict]:
        with self._lock: return list(self._queue)[:limit]
    def size(self) -> int:
        with self._lock: return len(self._queue)
    def clear(self) -> None:
        with self._lock: self._queue.clear()

_offline_queue = OfflineQueue()


class SyncStrategy:
    """P263: 同步策略"""
    STRATEGIES = {"full": "全量同步", "incremental": "增量同步", "eventual": "最终一致"}
    def __init__(self):
        self._strategy = "incremental"
        self._last_sync: dict[str, str] = {}
    def set_strategy(self, strategy: str) -> None:
        if strategy in self.STRATEGIES: self._strategy = strategy
    def get_strategy(self) -> str: return self._strategy
    def mark_synced(self, entity: str) -> None:
        self._last_sync[entity] = datetime.now().isoformat()
    def needs_sync(self, entity: str, interval_sec: int = 300) -> bool:
        last = self._last_sync.get(entity)
        if not last: return True
        return (datetime.now() - datetime.fromisoformat(last)).total_seconds() > interval_sec
    def get_sync_status(self) -> dict:
        return {"strategy": self._strategy, "entities": dict(self._last_sync)}

_sync_strategy = SyncStrategy()


class NetworkDetector:
    """P267: 网络状态检测"""
    def __init__(self):
        self._online = True
        self._listeners: list[Callable] = []
        self._history: deque = deque(maxlen=100)
    def set_online(self, online: bool) -> None:
        old = self._online
        self._online = online
        self._history.append({"online": online, "timestamp": datetime.now().isoformat()})
        if old != online:
            for listener in self._listeners:
                try: listener(online)
                except: pass
    def is_online(self) -> bool: return self._online
    def on_change(self, callback: Callable) -> None: self._listeners.append(callback)
    def get_history(self) -> list[dict]: return list(self._history)

_network = NetworkDetector()


class CacheLayer:
    """P266: 多层缓存"""
    def __init__(self):
        self._l1: dict[str, dict] = {}
        self._l2: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._hits = 0; self._misses = 0
    def set(self, key: str, value: Any, layer: int = 1, ttl: int = 300) -> None:
        with self._lock:
            cache = self._l1 if layer == 1 else self._l2
            cache[key] = {"value": value, "ttl": ttl, "created": time.time()}
    def get(self, key: str) -> Any | None:
        with self._lock:
            for cache in [self._l1, self._l2]:
                item = cache.get(key)
                if item:
                    if item["ttl"] > 0 and time.time() - item["created"] > item["ttl"]:
                        cache.pop(key, None); continue
                    self._hits += 1; return item["value"]
            self._misses += 1; return None
    def invalidate(self, key: str) -> None:
        with self._lock:
            self._l1.pop(key, None); self._l2.pop(key, None)
    def stats(self) -> dict:
        total = self._hits + self._misses
        return {"l1_size": len(self._l1), "l2_size": len(self._l2),
                "hits": self._hits, "misses": self._misses,
                "hit_rate": round(self._hits / total, 3) if total else 0}

_cache = CacheLayer()


class DataPrefetcher:
    """P265: 数据预加载"""
    def __init__(self):
        self._prefetched: dict[str, Any] = {}
        self._lock = threading.Lock()
    def prefetch(self, key: str, fetch_fn: Callable) -> None:
        import threading as t
        def _fetch():
            try:
                result = fetch_fn()
                with self._lock: self._prefetched[key] = result
            except: pass
        t.Thread(target=_fetch, daemon=True).start()
    def get(self, key: str) -> Any | None:
        with self._lock: return self._prefetched.pop(key, None)
    def has(self, key: str) -> bool:
        with self._lock: return key in self._prefetched

_prefetcher = DataPrefetcher()


class IncrementalSync:
    """P268: 增量同步"""
    def __init__(self):
        self._sync_log: deque = deque(maxlen=500)
        self._lock = threading.Lock()
    def sync(self, entity: str, local_data: list, remote_data: list,
             key_field: str = "id") -> dict:
        local_map = {item.get(key_field): item for item in local_data}
        remote_map = {item.get(key_field): item for item in remote_data}
        added, updated, deleted = [], [], []
        for key, remote_item in remote_map.items():
            if key not in local_map:
                added.append(remote_item)
            elif local_map[key] != remote_item:
                updated.append(remote_item)
        for key in local_map:
            if key not in remote_map:
                deleted.append(local_map[key])
        result = {"entity": entity, "added": len(added), "updated": len(updated),
                  "deleted": len(deleted), "timestamp": datetime.now().isoformat()}
        with self._lock: self._sync_log.append(result)
        return result
    def get_log(self, limit: int = 20) -> list[dict]:
        with self._lock: return list(self._sync_log)[-limit:]

_incremental = IncrementalSync()


class OfflineSearch:
    """P269: 离线搜索"""
    def __init__(self):
        self._index: dict[str, list[str]] = defaultdict(list)
        self._lock = threading.Lock()
    def index(self, doc_id: str, content: str) -> None:
        tokens = set(content.lower().split())
        with self._lock:
            for token in tokens:
                self._index[token].append(doc_id)
    def search(self, query: str) -> list[str]:
        tokens = query.lower().split()
        if not tokens: return []
        with self._lock:
            results = None
            for token in tokens:
                docs = set(self._index.get(token, []))
                results = docs if results is None else results & docs
                if not results: return []
            return list(results or [])
    def clear(self) -> None:
        with self._lock: self._index.clear()

_offline_search = OfflineSearch()
