"""
P881-P920: 缓存策略+多级缓存+预热+穿透/击穿/雪崩防护+淘汰策略+压缩+序列化+一致性(40轮)
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import zlib
from collections import OrderedDict, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

logger = __import__("logging").getLogger(__name__)


class EvictionPolicy(Enum):
    LRU = "lru"
    LFU = "lfu"
    FIFO = "fifo"
    TTL = "ttl"
    RANDOM = "random"


# ═════════ P881-P890: 多级缓存 ═════════

class CacheLevel(Enum):
    L1 = "L1"  # 本地内存
    L2 = "L2"  # 分布式缓存
    L3 = "L3"  # 持久化


class MultiLevelCache:
    """多级缓存(L1内存 + L2分布式 + L3持久化)"""

    def __init__(self, l1_size: int = 1000, l2_size: int = 10000,
                 l3_enabled: bool = False):
        self.l1_size = l1_size
        self.l2_size = l2_size
        self.l3_enabled = l3_enabled
        self._l1: OrderedDict = OrderedDict()  # 本地内存
        self._l2: OrderedDict = OrderedDict()  # 模拟分布式
        self._l3: dict = {}  # 模拟持久化
        self._stats = {"l1_hits": 0, "l2_hits": 0, "l3_hits": 0, "misses": 0}
        self._lock = threading.RLock()

    def get(self, key: str) -> dict:
        with self._lock:
            # L1
            if key in self._l1:
                self._stats["l1_hits"] += 1
                self._l1.move_to_end(key)
                return {"value": self._l1[key], "level": "L1", "hit": True}
            # L2
            if key in self._l2:
                self._stats["l2_hits"] += 1
                value = self._l2.pop(key)
                # 提升到L1
                self._promote_to_l1(key, value)
                return {"value": value, "level": "L2", "hit": True}
            # L3
            if self.l3_enabled and key in self._l3:
                self._stats["l3_hits"] += 1
                value = self._l3[key]
                self._promote_to_l1(key, value)
                return {"value": value, "level": "L3", "hit": True}
            self._stats["misses"] += 1
            return {"hit": False, "level": None}

    def set(self, key: str, value: Any, ttl_sec: int = 300) -> dict:
        with self._lock:
            expires_at = time.time() + ttl_sec
            entry = {"value": value, "expires_at": expires_at}
            self._promote_to_l1(key, entry)
            return {"status": "ok", "level": "L1"}

    def _promote_to_l1(self, key: str, value: Any) -> None:
        self._l1[key] = value
        self._l1.move_to_end(key)
        if len(self._l1) > self.l1_size:
            # 淘汰到L2
            old_key, old_val = self._l1.popitem(last=False)
            self._l2[old_key] = old_val
            if len(self._l2) > self.l2_size:
                # L2淘汰
                old_key2, _ = self._l2.popitem(last=False)
                if self.l3_enabled:
                    self._l3[old_key2] = _

    def invalidate(self, key: str) -> dict:
        with self._lock:
            existed = key in self._l1 or key in self._l2 or key in self._l3
            self._l1.pop(key, None)
            self._l2.pop(key, None)
            self._l3.pop(key, None)
            return {"status": "ok", "existed": existed}

    def clear(self) -> dict:
        with self._lock:
            l1_count = len(self._l1)
            l2_count = len(self._l2)
            l3_count = len(self._l3)
            self._l1.clear()
            self._l2.clear()
            self._l3.clear()
            return {"status": "ok", "cleared": l1_count + l2_count + l3_count}

    def stats(self) -> dict:
        with self._lock:
            total = sum(self._stats.values())
            return {
                **self._stats,
                "l1_size": len(self._l1),
                "l2_size": len(self._l2),
                "l3_size": len(self._l3),
                "hit_rate": round(sum([self._stats["l1_hits"], self._stats["l2_hits"],
                                       self._stats["l3_hits"]]) / max(1, total), 4),
            }


_mlcache = MultiLevelCache()


# ═════════ P891-P900: 缓存策略 ═════════

class CacheStrategyMgr:
    """缓存策略管理(cache-aside/read-through/write-through/write-behind)"""

    def __init__(self):
        self._strategies: dict[str, dict] = {}
        self._store: dict[str, Any] = {}
        self._write_behind_queue: deque = deque()
        self._lock = threading.Lock()

    def register(self, name: str, strategy: str = "cache-aside",
                 ttl_sec: int = 300) -> dict:
        with self._lock:
            self._strategies[name] = {
                "strategy": strategy,
                "ttl_sec": ttl_sec,
                "created_at": datetime.now().isoformat(),
            }
            return {"status": "ok"}

    def get(self, name: str, key: str, loader: Callable | None = None) -> dict:
        with self._lock:
            strat = self._strategies.get(name)
            if not strat:
                return {"hit": False, "error": "策略不存在"}
            cache_key = f"{name}:{key}"
            entry = self._store.get(cache_key)
            if entry and entry["expires_at"] > time.time():
                return {"hit": True, "value": entry["value"],
                        "strategy": strat["strategy"]}
            if entry and entry["expires_at"] <= time.time():
                self._store.pop(cache_key, None)
            # 缓存未命中
            if strat["strategy"] in ("read-through", "cache-aside") and loader:
                try:
                    value = loader()
                    self._store[cache_key] = {
                        "value": value,
                        "expires_at": time.time() + strat["ttl_sec"],
                    }
                    return {"hit": False, "value": value, "loaded": True,
                            "strategy": strat["strategy"]}
                except Exception as e:
                    return {"hit": False, "error": str(e)}
            return {"hit": False, "strategy": strat["strategy"]}

    def set(self, name: str, key: str, value: Any,
            writer: Callable | None = None) -> dict:
        with self._lock:
            strat = self._strategies.get(name)
            if not strat:
                return {"status": "error", "error": "策略不存在"}
            cache_key = f"{name}:{key}"
            self._store[cache_key] = {
                "value": value,
                "expires_at": time.time() + strat["ttl_sec"],
            }
            if strat["strategy"] == "write-through" and writer:
                try:
                    writer(value)
                    return {"status": "ok", "written": True,
                            "strategy": "write-through"}
                except Exception as e:
                    return {"status": "error", "error": str(e)}
            elif strat["strategy"] == "write-behind":
                self._write_behind_queue.append({"key": cache_key, "value": value})
                return {"status": "ok", "queued": True,
                        "strategy": "write-behind"}
            return {"status": "ok", "strategy": strat["strategy"]}

    def flush_write_behind(self, writer: Callable) -> dict:
        with self._lock:
            queue = list(self._write_behind_queue)
            self._write_behind_queue.clear()
        results = []
        for item in queue:
            try:
                writer(item["value"])
                results.append({"key": item["key"], "status": "ok"})
            except Exception as e:
                results.append({"key": item["key"], "status": "error",
                                "error": str(e)})
        return {"flushed": len(results), "results": results}

    def list_strategies(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **v} for k, v in self._strategies.items()]


_cache_strategy = CacheStrategyMgr()


# ═════════ P901-P910: 穿透/击穿/雪崩防护 ═════════

class CacheShield:
    """缓存穿透/击穿/雪崩防护"""

    def __init__(self):
        self._bloom_filter: set = set()  # 简化版布隆过滤器
        self._null_cache: dict[str, float] = {}  # 空值缓存
        self._null_ttl = 60  # 空值缓存60秒
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._lock = threading.Lock()
        # 雪崩防护: 随机TTL
        self._base_ttl = 300
        self._jitter_max = 60
        # 统计
        self._stats = {"penetration_blocked": 0, "breakdown_blocked": 0,
                       "avalanche_prevented": 0}

    def get_with_shield(self, key: str, loader: Callable,
                        ttl_sec: int | None = None) -> dict:
        # 穿透防护: 布隆过滤器
        with self._lock:
            if key in self._null_cache:
                if self._null_cache[key] > time.time():
                    self._stats["penetration_blocked"] += 1
                    return {"hit": True, "value": None, "reason": "null_cache"}
                self._null_cache.pop(key, None)
        # 击穿防护: 互斥锁
        lock = self._locks[key]
        if lock.acquire(blocking=False):
            try:
                try:
                    value = loader()
                except Exception as e:
                    return {"hit": False, "error": str(e)}
                if value is None:
                    with self._lock:
                        self._null_cache[key] = time.time() + self._null_ttl
                    return {"hit": False, "value": None}
                # 雪崩防护: 随机TTL
                actual_ttl = ttl_sec or self._base_ttl
                jitter = __import__("random").randint(0, self._jitter_max)
                actual_ttl += jitter
                self._stats["avalanche_prevented"] += 1
                return {"hit": False, "value": value, "ttl_sec": actual_ttl,
                        "loaded": True}
            finally:
                lock.release()
        else:
            self._stats["breakdown_blocked"] += 1
            return {"hit": False, "reason": "loading", "retry": True}

    def add_to_bloom(self, key: str) -> None:
        with self._lock:
            self._bloom_filter.add(key)

    def might_exist(self, key: str) -> bool:
        with self._lock:
            return key in self._bloom_filter

    def stats(self) -> dict:
        with self._lock:
            return {**self._stats,
                    "bloom_size": len(self._bloom_filter),
                    "null_cache_size": len(self._null_cache)}


_cache_shield = CacheShield()


# ═════════ P911-P920: 淘汰策略 + 压缩 + 预热 ═════════

class EvictionCache:
    """支持多种淘汰策略的缓存"""

    def __init__(self, max_size: int = 1000, policy: EvictionPolicy = EvictionPolicy.LRU):
        self.max_size = max_size
        self.policy = policy
        self._store: OrderedDict = OrderedDict()
        self._freq: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._stats = {"evicted": 0, "expired": 0, "hits": 0, "misses": 0}

    def get(self, key: str) -> dict:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                self._stats["misses"] += 1
                return {"hit": False}
            if entry["expires_at"] < time.time():
                self._store.pop(key, None)
                self._stats["expired"] += 1
                self._stats["misses"] += 1
                return {"hit": False, "reason": "expired"}
            self._stats["hits"] += 1
            self._freq[key] += 1
            if self.policy == EvictionPolicy.LRU:
                self._store.move_to_end(key)
            return {"hit": True, "value": entry["value"]}

    def set(self, key: str, value: Any, ttl_sec: int = 300) -> dict:
        with self._lock:
            self._store[key] = {"value": value,
                                "expires_at": time.time() + ttl_sec}
            self._freq[key] = 1
            if self.policy == EvictionPolicy.LRU:
                self._store.move_to_end(key)
            self._evict_if_needed()
            return {"status": "ok", "size": len(self._store)}

    def _evict_if_needed(self) -> None:
        while len(self._store) > self.max_size:
            if self.policy == EvictionPolicy.LRU:
                key, _ = self._store.popitem(last=False)
            elif self.policy == EvictionPolicy.FIFO:
                key, _ = self._store.popitem(last=False)
            elif self.policy == EvictionPolicy.LFU:
                key = min(self._freq, key=lambda k: self._freq[k])
                self._store.pop(key, None)
                self._freq.pop(key, None)
            elif self.policy == EvictionPolicy.RANDOM:
                import random
                key = random.choice(list(self._store.keys()))
                self._store.pop(key, None)
            else:
                key, _ = self._store.popitem(last=False)
            self._freq.pop(key, None)
            self._stats["evicted"] += 1

    def stats(self) -> dict:
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            return {**self._stats, "size": len(self._store),
                    "max_size": self.max_size,
                    "hit_rate": round(self._stats["hits"] / max(1, total), 4)}


class CacheSerializer:
    """缓存序列化与压缩"""

    @staticmethod
    def serialize(value: Any, compress: bool = False) -> dict:
        try:
            data = json.dumps(value, default=str).encode("utf-8")
            original_size = len(data)
            if compress:
                data = zlib.compress(data, level=6)
            return {
                "status": "ok",
                "data": data.hex(),
                "original_size": original_size,
                "serialized_size": len(data),
                "compressed": compress,
                "ratio": round(len(data) / max(1, original_size), 4),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    def deserialize(data_hex: str, compressed: bool = False) -> dict:
        try:
            data = bytes.fromhex(data_hex)
            if compressed:
                data = zlib.decompress(data)
            value = json.loads(data.decode("utf-8"))
            return {"status": "ok", "value": value, "size": len(data)}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class CacheWarmer:
    """缓存预热"""

    def __init__(self):
        self._warmers: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register(self, name: str, keys: list[str],
                 loader: Callable | None = None) -> dict:
        with self._lock:
            self._warmers[name] = {
                "keys": keys,
                "loader": loader,
                "warmed": 0,
                "last_run": None,
            }
            return {"status": "ok"}

    def warmup(self, name: str) -> dict:
        with self._lock:
            warmer = self._warmers.get(name)
            if not warmer:
                return {"status": "error", "error": "预热器不存在"}
            keys = warmer["keys"]
            loader = warmer["loader"]
        warmed = 0
        errors = []
        for key in keys:
            try:
                if loader:
                    value = loader(key)
                    _mlcache.set(key, value)
                    warmed += 1
            except Exception as e:
                errors.append({"key": key, "error": str(e)})
        with self._lock:
            self._warmers[name]["warmed"] = warmed
            self._warmers[name]["last_run"] = datetime.now().isoformat()
        return {"status": "ok", "warmed": warmed, "errors": errors}

    def list_warmers(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **{kk: vv for kk, vv in v.items() if kk != "loader"}}
                    for k, v in self._warmers.items()]


_eviction_cache = EvictionCache()
_cache_serializer = CacheSerializer()
_cache_warmer = CacheWarmer()
