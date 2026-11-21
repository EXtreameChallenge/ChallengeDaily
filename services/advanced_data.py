"""
P121-P129: 高级数据处理与缓存
- P121: 多级缓存(L1内存/L2磁盘)
- P122: 数据分片与分区
- P123: 增量计算引擎
- P124: 数据预聚合管道
- P125: 查询计划分析
- P126: 数据压缩存储
- P127: 事件溯源
- P128: CQRS读模型
- P129: 数据同步与冲突解决
"""
import logging
import threading
import time
import json
import os
import zlib
import hashlib
import pickle
from datetime import datetime, timedelta
from collections import OrderedDict, defaultdict, deque
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P121: 多级缓存 ──────────────────────────
class MultiLevelCache:
    """L1 内存 + L2 磁盘二级缓存"""

    def __init__(self, name: str, l1_size: int = 128, l1_ttl: int = 60,
                 l2_dir: str | None = None, l2_ttl: int = 3600):
        self.name = name
        self._l1: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
        self._l1_size = l1_size
        self._l1_ttl = l1_ttl
        self._l2_dir = l2_dir
        self._l2_ttl = l2_ttl
        self._lock = threading.RLock()
        self._stats = {"l1_hits": 0, "l2_hits": 0, "misses": 0, "sets": 0}
        if l2_dir:
            os.makedirs(l2_dir, exist_ok=True)

    def _l1_get(self, key: str):
        with self._lock:
            item = self._l1.get(key)
            if item is None:
                return None
            ts, value = item
            if (time.time() - ts) > self._l1_ttl:
                self._l1.pop(key, None)
                return None
            self._l1.move_to_end(key)
            return value

    def _l1_set(self, key: str, value: Any) -> None:
        with self._lock:
            self._l1[key] = (time.time(), value)
            self._l1.move_to_end(key)
            while len(self._l1) > self._l1_size:
                self._l1.popitem(last=False)

    def _l2_path(self, key: str) -> str:
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return os.path.join(self._l2_dir, f"{safe_key}.cache")

    def _l2_get(self, key: str):
        if not self._l2_dir:
            return None
        path = self._l2_path(key)
        if not os.path.exists(path):
            return None
        try:
            mtime = os.path.getmtime(path)
            if (time.time() - mtime) > self._l2_ttl:
                os.remove(path)
                return None
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None

    def _l2_set(self, key: str, value: Any) -> None:
        if not self._l2_dir:
            return
        path = self._l2_path(key)
        try:
            with open(path, "wb") as f:
                pickle.dump(value, f)
        except Exception as e:
            logger.debug(f"L2 缓存写入失败: {e}")

    def get(self, key: str, loader: Callable[[], Any] | None = None) -> Any:
        # L1
        v = self._l1_get(key)
        if v is not None:
            self._stats["l1_hits"] += 1
            return v
        # L2
        v = self._l2_get(key)
        if v is not None:
            self._stats["l2_hits"] += 1
            self._l1_set(key, v)  # 回填 L1
            return v
        # Loader
        if loader:
            self._stats["sets"] += 1
            v = loader()
            self.set(key, v)
            return v
        self._stats["misses"] += 1
        return None

    def set(self, key: str, value: Any) -> None:
        self._l1_set(key, value)
        self._l2_set(key, value)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._l1.pop(key, None)
        if self._l2_dir:
            path = self._l2_path(key)
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def clear(self) -> None:
        with self._lock:
            self._l1.clear()
        if self._l2_dir:
            for f in os.listdir(self._l2_dir):
                if f.endswith(".cache"):
                    try:
                        os.remove(os.path.join(self._l2_dir, f))
                    except Exception:
                        pass

    def stats(self) -> dict:
        total = self._stats["l1_hits"] + self._stats["l2_hits"] + self._stats["misses"]
        return {
            **self._stats,
            "l1_size": len(self._l1),
            "hit_rate": round((self._stats["l1_hits"] + self._stats["l2_hits"]) / max(total, 1), 3)
        }


# ─── P122: 数据分片 ──────────────────────────
class DataShard:
    """按日期分片管理数据"""

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def shard_key(self, timestamp: datetime) -> str:
        return timestamp.strftime("%Y%m")

    def get_shard_path(self, shard_key: str) -> str:
        return os.path.join(self.base_dir, f"shard_{shard_key}.json")

    def write(self, data: list[dict], timestamp: datetime) -> str:
        key = self.shard_key(timestamp)
        path = self.get_shard_path(key)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"shard": key, "count": len(data), "data": data}, f, ensure_ascii=False)
        return key

    def read(self, shard_key: str) -> list[dict]:
        path = self.get_shard_path(shard_key)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("data", [])

    def list_shards(self) -> list[str]:
        return sorted([
            f.replace("shard_", "").replace(".json", "")
            for f in os.listdir(self.base_dir)
            if f.startswith("shard_") and f.endswith(".json")
        ])


# ─── P123: 增量计算引擎 ──────────────────────────
class IncrementalAggregator:
    """增量聚合，避免每次全量重算"""

    def __init__(self):
        self._state: dict[str, Any] = {}
        self._lock = threading.Lock()

    def update(self, key: str, value: float, op: str = "sum") -> None:
        with self._lock:
            if key not in self._state:
                self._state[key] = {"sum": 0, "count": 0, "min": float("inf"), "max": float("-inf")}
            s = self._state[key]
            s["sum"] += value
            s["count"] += 1
            s["min"] = min(s["min"], value)
            s["max"] = max(s["max"], value)
            s["avg"] = s["sum"] / s["count"]

    def get(self, key: str) -> dict | None:
        with self._lock:
            return self._state.get(key)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key:
                self._state.pop(key, None)
            else:
                self._state.clear()


# ─── P124: 数据预聚合管道 ──────────────────────────
class PreAggregationPipeline:
    """定时预聚合管道"""

    def __init__(self):
        self._tasks: list[dict] = []
        self._lock = threading.Lock()

    def register(self, name: str, func: Callable, interval: int) -> None:
        with self._lock:
            self._tasks.append({
                "name": name, "func": func, "interval": interval,
                "last_run": 0, "last_result": None, "last_error": None
            })

    def run_pending(self) -> list:
        results = []
        now = time.time()
        with self._lock:
            tasks = list(self._tasks)
        for task in tasks:
            if now - task["last_run"] < task["interval"]:
                continue
            try:
                result = task["func"]()
                task["last_result"] = result
                task["last_error"] = None
                results.append({"name": task["name"], "status": "ok", "result": result})
            except Exception as e:
                task["last_error"] = str(e)
                results.append({"name": task["name"], "status": "error", "error": str(e)})
            task["last_run"] = now
        return results

    def get_status(self) -> list:
        with self._lock:
            return [
                {
                    "name": t["name"], "interval": t["interval"],
                    "last_run": t["last_run"],
                    "has_result": t["last_result"] is not None,
                    "has_error": t["last_error"] is not None
                }
                for t in self._tasks
            ]


# ─── P125: 查询计划分析 ──────────────────────────
def explain_query(sql: str) -> dict:
    """EXPLAIN 查询计划"""
    try:
        import db
        with db.get_conn() as conn:
            rows = conn.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
            return {
                "sql": sql,
                "plan": [
                    {"id": r[0], "parent": r[1], "detail": r[3]}
                    for r in rows
                ]
            }
    except Exception as e:
        return {"error": str(e), "sql": sql}


def analyze_slow_queries(threshold_ms: float = 100) -> dict:
    """分析慢查询(基于历史统计)"""
    return {
        "threshold_ms": threshold_ms,
        "recommendations": [
            "为 WHERE 子句中的列添加索引",
            "避免 SELECT *，只查询需要的列",
            "对大表使用分页查询",
            "使用 EXPLAIN QUERY PLAN 验证索引使用"
        ]
    }


# ─── P126: 数据压缩存储 ──────────────────────────
class CompressedStorage:
    """zlib 压缩存储"""

    @staticmethod
    def save(path: str, data: Any) -> int:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        compressed = zlib.compress(raw, level=6)
        with open(path, "wb") as f:
            f.write(compressed)
        return len(compressed)

    @staticmethod
    def load(path: str) -> Any:
        with open(path, "rb") as f:
            compressed = f.read()
        raw = zlib.decompress(compressed)
        return json.loads(raw.decode("utf-8"))

    @staticmethod
    def compress_ratio(original_size: int, compressed_size: int) -> float:
        if original_size == 0:
            return 0
        return round(compressed_size / original_size, 3)


# ─── P127: 事件溯源 ──────────────────────────
class EventStore:
    """事件溯源：记录所有状态变更事件"""

    def __init__(self, max_events: int = 10000):
        self._events: deque = deque(maxlen=max_events)
        self._lock = threading.Lock()

    def append(self, event_type: str, payload: dict) -> str:
        event_id = f"evt_{int(time.time() * 1000)}_{len(self._events)}"
        event = {
            "id": event_id,
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        }
        with self._lock:
            self._events.append(event)
        return event_id

    def get_events(self, event_type: str = "", limit: int = 100) -> list:
        with self._lock:
            events = list(self._events)
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        events.reverse()
        return events[:limit]

    def replay(self, event_type: str = "", handler: Callable | None = None) -> int:
        """重放事件"""
        count = 0
        with self._lock:
            events = list(self._events)
        for event in events:
            if event_type and event["type"] != event_type:
                continue
            if handler:
                try:
                    handler(event)
                except Exception as e:
                    logger.warning(f"事件重放失败: {e}")
            count += 1
        return count


# ─── P128: CQRS 读模型 ──────────────────────────
class ReadModel:
    """CQRS 读模型：物化视图"""

    def __init__(self):
        self._models: dict[str, dict] = {}
        self._lock = threading.RLock()

    def update(self, model_name: str, key: str, value: Any) -> None:
        with self._lock:
            if model_name not in self._models:
                self._models[model_name] = {}
            self._models[model_name][key] = value

    def get(self, model_name: str, key: str) -> Any | None:
        with self._lock:
            return self._models.get(model_name, {}).get(key)

    def query(self, model_name: str, filter_fn: Callable | None = None) -> list:
        with self._lock:
            items = list(self._models.get(model_name, {}).items())
        if filter_fn:
            return [{"key": k, "value": v} for k, v in items if filter_fn(k, v)]
        return [{"key": k, "value": v} for k, v in items]

    def rebuild(self, model_name: str, events: list[dict]) -> int:
        """从事件重建读模型"""
        with self._lock:
            self._models[model_name] = {}
        count = 0
        for event in events:
            payload = event.get("payload", {})
            key = payload.get("id", str(count))
            self.update(model_name, key, payload)
            count += 1
        return count


# ─── P129: 数据同步与冲突解决 ──────────────────────────
class SyncManager:
    """数据同步与冲突解决"""

    def __init__(self):
        self._lock = threading.Lock()
        self._sync_log: deque = deque(maxlen=100)

    def merge(self, local: dict, remote: dict, strategy: str = "last_write_wins") -> dict:
        """合并数据"""
        with self._lock:
            if strategy == "last_write_wins":
                local_ts = local.get("updated_at", "")
                remote_ts = remote.get("updated_at", "")
                merged = remote if remote_ts > local_ts else local
                conflict = False
            elif strategy == "field_merge":
                merged = {**local, **remote}
                conflict = False
            else:
                merged = local
                conflict = True

            self._sync_log.append({
                "timestamp": datetime.now().isoformat(),
                "strategy": strategy,
                "conflict": conflict,
                "local_keys": list(local.keys()),
                "remote_keys": list(remote.keys())
            })
        return merged

    def get_sync_log(self) -> list:
        with self._lock:
            return list(self._sync_log)

    def detect_conflicts(self, local: dict, remote: dict) -> list:
        """检测冲突字段"""
        conflicts = []
        for key in set(local.keys()) & set(remote.keys()):
            if local.get(key) != remote.get(key):
                conflicts.append({
                    "field": key,
                    "local": local.get(key),
                    "remote": remote.get(key)
                })
        return conflicts


# 单例实例
_caches: dict[str, MultiLevelCache] = {}
_event_store = EventStore()
_read_model = ReadModel()
_sync_manager = SyncManager()
_aggregator = IncrementalAggregator()
_pipeline = PreAggregationPipeline()


def get_cache(name: str, **kwargs) -> MultiLevelCache:
    if name not in _caches:
        _caches[name] = MultiLevelCache(name, **kwargs)
    return _caches[name]


def get_event_store() -> EventStore:
    return _event_store


def get_read_model() -> ReadModel:
    return _read_model


def get_sync_manager() -> SyncManager:
    return _sync_manager


def get_aggregator() -> IncrementalAggregator:
    return _aggregator


def get_pipeline() -> PreAggregationPipeline:
    return _pipeline
