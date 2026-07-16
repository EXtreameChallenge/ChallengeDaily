"""
P161-P169: 性能深度优化
- P161: 连接池优化
- P162: 查询批处理器
- P163: 内存池
- P164: 对象复用
- P165: 懒加载注册表
- P166: 预编译语句缓存
- P167: 异步任务队列
- P168: 热路径优化
- P169: 性能基准测试
"""
import logging
import threading
import time
import queue
from collections import deque, defaultdict
from typing import Any, Callable, Optional
from functools import lru_cache

logger = logging.getLogger(__name__)


# ─── P161: 连接池优化 ──────────────────────────
class ConnectionPool:
    """通用连接池"""

    def __init__(self, factory: Callable, max_size: int = 10,
                 max_idle: int = 60, validate_on_borrow: bool = True):
        self._factory = factory
        self._max_size = max_size
        self._max_idle = max_idle
        self._validate = validate_on_borrow
        self._pool: deque = deque()
        self._in_use: set = set()
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._created_count = 0

    def acquire(self, timeout: float = 5.0) -> Any:
        with self._lock:
            while True:
                if self._pool:
                    conn = self._pool.popleft()
                    if self._validate and not self._validate_conn(conn):
                        self._created_count -= 1
                        continue
                    self._in_use.add(id(conn))
                    return conn
                if self._created_count < self._max_size:
                    conn = self._factory()
                    self._created_count += 1
                    self._in_use.add(id(conn))
                    return conn
                if not self._not_empty.wait(timeout):
                    raise TimeoutError("获取连接超时")

    def release(self, conn: Any) -> None:
        with self._lock:
            self._in_use.discard(id(conn))
            self._pool.append(conn)
            self._not_empty.notify()

    def _validate_conn(self, conn: Any) -> bool:
        try:
            if hasattr(conn, "closed") and conn.closed:
                return False
            return True
        except Exception:
            return False

    def stats(self) -> dict:
        with self._lock:
            return {
                "created": self._created_count,
                "in_use": len(self._in_use),
                "idle": len(self._pool),
                "max_size": self._max_size
            }


# ─── P162: 查询批处理 ──────────────────────────
class QueryBatcher:
    """批量查询处理器"""

    def __init__(self, executor: Callable, batch_size: int = 100,
                 flush_interval: float = 1.0):
        self._executor = executor
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._buffer: list = []
        self._lock = threading.Lock()
        self._last_flush = time.time()
        self._pending_results: dict[int, Any] = {}
        self._event_id = 0

    def add(self, query: Any) -> int:
        with self._lock:
            eid = self._event_id
            self._event_id += 1
            self._buffer.append((eid, query))
            if len(self._buffer) >= self._batch_size or \
               (time.time() - self._last_flush) > self._flush_interval:
                self._flush()
            return eid

    def _flush(self) -> None:
        if not self._buffer:
            return
        batch = list(self._buffer)
        self._buffer.clear()
        self._last_flush = time.time()
        try:
            results = self._executor([q for _, q in batch])
            for (eid, _), result in zip(batch, results):
                self._pending_results[eid] = result
        except Exception as e:
            logger.warning(f"批处理失败: {e}")
            for eid, _ in batch:
                self._pending_results[eid] = None

    def get_result(self, eid: int, timeout: float = 5.0) -> Any:
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if eid in self._pending_results:
                    return self._pending_results.pop(eid)
                if (time.time() - self._last_flush) > self._flush_interval:
                    self._flush()
            time.sleep(0.05)
        return None


# ─── P163: 内存池 ──────────────────────────
class MemoryPool:
    """对象内存池"""

    def __init__(self, factory: Callable, reset_fn: Callable | None = None,
                 max_size: int = 50):
        self._factory = factory
        self._reset_fn = reset_fn
        self._max_size = max_size
        self._pool: deque = deque()
        self._lock = threading.Lock()
        self._created = 0
        self._reused = 0

    def acquire(self) -> Any:
        with self._lock:
            if self._pool:
                obj = self._pool.popleft()
                self._reused += 1
                if self._reset_fn:
                    self._reset_fn(obj)
                return obj
            self._created += 1
        return self._factory()

    def release(self, obj: Any) -> None:
        with self._lock:
            if len(self._pool) < self._max_size:
                self._pool.append(obj)

    def stats(self) -> dict:
        with self._lock:
            return {
                "created": self._created,
                "reused": self._reused,
                "pool_size": len(self._pool),
                "max_size": self._max_size,
                "reuse_rate": round(self._reused / max(self._created + self._reused, 1), 3)
            }


# ─── P164: 对象复用 ──────────────────────────
class ObjectReuser:
    """通用对象复用"""

    def __init__(self):
        self._pools: dict[str, MemoryPool] = {}
        self._lock = threading.Lock()

    def register(self, name: str, factory: Callable,
                 reset_fn: Callable | None = None, max_size: int = 50) -> None:
        with self._lock:
            self._pools[name] = MemoryPool(factory, reset_fn, max_size)

    def acquire(self, name: str) -> Any:
        with self._lock:
            pool = self._pools.get(name)
        if pool:
            return pool.acquire()
        raise ValueError(f"未注册的对象类型: {name}")

    def release(self, name: str, obj: Any) -> None:
        with self._lock:
            pool = self._pools.get(name)
        if pool:
            pool.release(obj)

    def stats(self) -> dict:
        with self._lock:
            return {name: pool.stats() for name, pool in self._pools.items()}


# ─── P165: 懒加载注册表 ──────────────────────────
class LazyRegistry:
    """懒加载注册表"""

    def __init__(self):
        self._factories: dict[str, Callable] = {}
        self._instances: dict[str, Any] = {}
        self._lock = threading.RLock()

    def register(self, name: str, factory: Callable) -> None:
        with self._lock:
            self._factories[name] = factory

    def get(self, name: str) -> Any:
        with self._lock:
            if name in self._instances:
                return self._instances[name]
            if name not in self._factories:
                raise KeyError(f"未注册: {name}")
            instance = self._factories[name]()
            self._instances[name] = instance
            return instance

    def is_loaded(self, name: str) -> bool:
        with self._lock:
            return name in self._instances

    def loaded_keys(self) -> list:
        with self._lock:
            return list(self._instances.keys())

    def reset(self, name: str | None = None) -> None:
        with self._lock:
            if name:
                self._instances.pop(name, None)
            else:
                self._instances.clear()


# ─── P166: 预编译语句缓存 ──────────────────────────
class PreparedStatementCache:
    """SQL 预编译语句缓存"""

    def __init__(self, max_size: int = 100):
        self._cache: dict[str, Any] = {}
        self._max_size = max_size
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0}

    def get_or_prepare(self, conn: Any, sql: str) -> Any:
        with self._lock:
            if sql in self._cache:
                self._stats["hits"] += 1
                return self._cache[sql]
            self._stats["misses"] += 1
            stmt = conn.prepare(sql) if hasattr(conn, "prepare") else sql
            if len(self._cache) >= self._max_size:
                # 简单 LRU
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[sql] = stmt
            return stmt

    def stats(self) -> dict:
        with self._lock:
            total = self._stats["hits"] + self._stats["misses"]
            return {
                **self._stats,
                "size": len(self._cache),
                "hit_rate": round(self._stats["hits"] / max(total, 1), 3)
            }


# ─── P167: 异步任务队列 ──────────────────────────
class AsyncTaskQueue:
    """后台异步任务队列"""

    def __init__(self, worker_count: int = 2, max_size: int = 1000):
        self._queue: queue.Queue = queue.Queue(maxsize=max_size)
        self._workers: list[threading.Thread] = []
        self._running = False
        self._stats = {"submitted": 0, "completed": 0, "failed": 0}
        self._lock = threading.Lock()

    def start(self, worker_count: int) -> None:
        self._running = True
        for i in range(worker_count):
            t = threading.Thread(target=self._worker, daemon=True, name=f"async_worker_{i}")
            t.start()
            self._workers.append(t)

    def _worker(self) -> None:
        while self._running:
            try:
                task = self._queue.get(timeout=1.0)
                try:
                    task["func"](*task.get("args", []), **task.get("kwargs", {}))
                    with self._lock:
                        self._stats["completed"] += 1
                except Exception as e:
                    logger.warning(f"异步任务失败: {e}")
                    with self._lock:
                        self._stats["failed"] += 1
                finally:
                    self._queue.task_done()
            except queue.Empty:
                continue

    def submit(self, func: Callable, *args, **kwargs) -> bool:
        try:
            self._queue.put_nowait({"func": func, "args": args, "kwargs": kwargs})
            with self._lock:
                self._stats["submitted"] += 1
            return True
        except queue.Full:
            return False

    def stop(self) -> None:
        self._running = False
        for t in self._workers:
            t.join(timeout=2.0)

    def stats(self) -> dict:
        with self._lock:
            return {
                **self._stats,
                "queue_size": self._queue.qsize(),
                "worker_count": len(self._workers)
            }


# ─── P168: 热路径优化 ──────────────────────────
_HOT_PATHS: dict[str, dict] = defaultdict(lambda: {"calls": 0, "total_time": 0})


def hot_path(name: str):
    """装饰器：标记并追踪热路径"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                with threading.Lock():
                    stat = _HOT_PATHS[name]
                    stat["calls"] += 1
                    stat["total_time"] += elapsed
        return wrapper
    return decorator


def get_hot_path_stats() -> dict:
    with threading.Lock():
        return {
            name: {
                "calls": s["calls"],
                "total_ms": round(s["total_time"] * 1000, 2),
                "avg_ms": round(s["total_time"] * 1000 / max(s["calls"], 1), 3)
            }
            for name, s in _HOT_PATHS.items()
        }


# ─── P169: 性能基准 ──────────────────────────
class Benchmark:
    """性能基准测试"""

    @staticmethod
    def run(name: str, func: Callable, iterations: int = 1000,
            warmup: int = 100) -> dict:
        # 预热
        for _ in range(warmup):
            try:
                func()
            except Exception:
                pass

        # 正式运行
        times: list[float] = []
        for _ in range(iterations):
            start = time.perf_counter()
            try:
                func()
            except Exception as e:
                return {"name": name, "error": str(e)}
            times.append(time.perf_counter() - start)

        times.sort()
        n = len(times)
        return {
            "name": name,
            "iterations": n,
            "min_ms": round(times[0] * 1000, 4),
            "max_ms": round(times[-1] * 1000, 4),
            "avg_ms": round(sum(times) / n * 1000, 4),
            "p50_ms": round(times[n // 2] * 1000, 4),
            "p95_ms": round(times[int(n * 0.95)] * 1000, 4),
            "p99_ms": round(times[int(n * 0.99)] * 1000, 4),
            "total_ms": round(sum(times) * 1000, 2)
        }

    @staticmethod
    def compare(benchmarks: list[dict]) -> dict:
        """对比多个基准测试结果"""
        if not benchmarks:
            return {}
        baseline = benchmarks[0]
        return {
            "baseline": baseline["name"],
            "comparisons": [
                {
                    "name": b["name"],
                    "speedup": round(baseline["avg_ms"] / b["avg_ms"], 3) if b.get("avg_ms") else 0,
                    "avg_ms": b.get("avg_ms", 0)
                }
                for b in benchmarks[1:]
            ]
        }
