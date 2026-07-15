"""
P111-P119: 弹性与可靠性模块
- P111: 重试策略(指数退避)
- P112: 熔断器增强
- P113: 超时控制
- P114: 限流器(令牌桶)
- P115: 舱壁隔离
- P116: 数据备份与恢复
- P117: 状态快照
- P118: 故障注入测试
- P119: 自愈机制
"""
import logging
import threading
import time
import json
import os
import shutil
import random
from datetime import datetime, timedelta
from collections import deque
from typing import Any, Callable, Optional
from functools import wraps

logger = logging.getLogger(__name__)


# ─── P111: 重试策略(指数退避) ──────────────────────────
def retry_with_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
    exceptions: tuple = (Exception,)
):
    """指数退避重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(f"P111 重试 {max_retries} 次后仍失败: {e}")
                        raise
                    actual_delay = delay
                    if jitter:
                        actual_delay = delay * (0.5 + random.random() * 0.5)
                    logger.warning(f"P111 第 {attempt + 1} 次失败，{actual_delay:.1f}s 后重试: {e}")
                    time.sleep(actual_delay)
                    delay = min(delay * backoff_factor, max_delay)
        return wrapper
    return decorator


class RetryStats:
    """重试统计"""
    def __init__(self):
        self._lock = threading.Lock()
        self._stats: dict[str, dict] = {}

    def record(self, name: str, success: bool, attempts: int) -> None:
        with self._lock:
            if name not in self._stats:
                self._stats[name] = {"total": 0, "success": 0, "failure": 0, "total_attempts": 0}
            self._stats[name]["total"] += 1
            self._stats[name]["total_attempts"] += attempts
            if success:
                self._stats[name]["success"] += 1
            else:
                self._stats[name]["failure"] += 1

    def get(self) -> dict:
        with self._lock:
            return dict(self._stats)


retry_stats = RetryStats()


# ─── P112: 熔断器增强 ──────────────────────────
class CircuitBreakerEnhanced:
    """增强版熔断器：支持半开状态、滑动窗口、超时恢复"""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, name: str, failure_threshold: int = 5,
                 recovery_timeout: float = 60.0,
                 half_open_max_calls: int = 3):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._state = self.CLOSED
        self._failures: deque = deque(maxlen=failure_threshold * 2)
        self._last_failure_time = 0
        self._half_open_calls = 0
        self._half_open_successes = 0
        self._lock = threading.RLock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == self.OPEN:
                if time.time() - self._last_failure_time > self.recovery_timeout:
                    self._state = self.HALF_OPEN
                    self._half_open_calls = 0
                    self._half_open_successes = 0
                    logger.info(f"P112 熔断器 {self.name} 进入半开状态")
            return self._state

    def allow_request(self) -> bool:
        with self._lock:
            current_state = self.state
            if current_state == self.CLOSED:
                return True
            if current_state == self.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            return False

    def record_success(self) -> None:
        with self._lock:
            if self._state == self.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.half_open_max_calls:
                    self._state = self.CLOSED
                    self._failures.clear()
                    logger.info(f"P112 熔断器 {self.name} 恢复为关闭状态")
            else:
                # 清空部分失败记录
                if self._failures:
                    self._failures.popleft()

    def record_failure(self) -> None:
        with self._lock:
            self._last_failure_time = time.time()
            if self._state == self.HALF_OPEN:
                self._state = self.OPEN
                logger.warning(f"P112 熔断器 {self.name} 半开状态失败，重新打开")
            else:
                self._failures.append(time.time())
                if len(self._failures) >= self.failure_threshold:
                    self._state = self.OPEN
                    logger.warning(f"P112 熔断器 {self.name} 打开（{len(self._failures)} 次失败）")

    def get_status(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": self.state,
                "failures": len(self._failures),
                "threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "half_open_calls": self._half_open_calls,
                "half_open_successes": self._half_open_successes,
                "last_failure_ago": round(time.time() - self._last_failure_time, 1) if self._last_failure_time else None
            }


_BREAKERS: dict[str, CircuitBreakerEnhanced] = {}


def get_breaker(name: str, **kwargs) -> CircuitBreakerEnhanced:
    """获取或创建熔断器"""
    if name not in _BREAKERS:
        _BREAKERS[name] = CircuitBreakerEnhanced(name, **kwargs)
    return _BREAKERS[name]


def get_all_breakers_status() -> list:
    return [b.get_status() for b in _BREAKERS.values()]


# ─── P113: 超时控制 ──────────────────────────
class TimeoutError(Exception):
    pass


def run_with_timeout(func: Callable, timeout: float, *args, **kwargs) -> Any:
    """在线程中运行函数，超时则抛出异常"""
    result: dict = {"value": None, "error": None}
    done = threading.Event()

    def target():
        try:
            result["value"] = func(*args, **kwargs)
        except Exception as e:
            result["error"] = e
        finally:
            done.set()

    t = threading.Thread(target=target, daemon=True)
    t.start()
    if not done.wait(timeout):
        raise TimeoutError(f"操作超时 ({timeout}s)")
    if result["error"]:
        raise result["error"]
    return result["value"]


# ─── P114: 令牌桶限流器 ──────────────────────────
class TokenBucket:
    """令牌桶限流器"""

    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self._tokens = capacity
        self._last_refill = time.time()
        self._lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> bool:
        with self._lock:
            now = time.time()
            elapsed = now - self._last_refill
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
            self._last_refill = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait_acquire(self, tokens: float = 1.0, max_wait: float = 10.0) -> bool:
        start = time.time()
        while time.time() - start < max_wait:
            if self.acquire(tokens):
                return True
            time.sleep(0.05)
        return False

    def stats(self) -> dict:
        with self._lock:
            return {
                "capacity": self.capacity,
                "refill_rate": self.refill_rate,
                "current_tokens": round(self._tokens, 2),
                "utilization": round(1 - self._tokens / self.capacity, 3)
            }


_BUCKETS: dict[str, TokenBucket] = {}


def get_bucket(name: str, capacity: float = 10, refill_rate: float = 1.0) -> TokenBucket:
    if name not in _BUCKETS:
        _BUCKETS[name] = TokenBucket(capacity, refill_rate)
    return _BUCKETS[name]


def get_all_buckets_stats() -> dict:
    return {name: b.stats() for name, b in _BUCKETS.items()}


# ─── P115: 舱壁隔离 ──────────────────────────
class Bulkhead:
    """舱壁隔离：限制并发调用数"""

    def __init__(self, name: str, max_concurrent: int = 10, max_queue: int = 50):
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue
        self._semaphore = threading.Semaphore(max_concurrent)
        self._active = 0
        self._queued = 0
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 5.0) -> bool:
        with self._lock:
            if self._queued >= self.max_queue:
                return False
            self._queued += 1
        try:
            acquired = self._semaphore.acquire(timeout=timeout)
            with self._lock:
                self._queued -= 1
                if acquired:
                    self._active += 1
            return acquired
        except Exception:
            with self._lock:
                self._queued -= 1
            return False

    def release(self) -> None:
        with self._lock:
            self._active -= 1
        self._semaphore.release()

    def stats(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "max_concurrent": self.max_concurrent,
                "active": self._active,
                "queued": self._queued,
                "available": self.max_concurrent - self._active
            }


_BULKHEADS: dict[str, Bulkhead] = {}


def get_bulkhead(name: str, **kwargs) -> Bulkhead:
    if name not in _BULKHEADS:
        _BULKHEADS[name] = Bulkhead(name, **kwargs)
    return _BULKHEADS[name]


# ─── P116: 数据备份与恢复 ──────────────────────────
def create_backup(backup_dir: str, include_screenshots: bool = False) -> dict:
    """创建数据备份"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"backup_{timestamp}")
        os.makedirs(backup_path, exist_ok=True)

        # 备份数据库
        try:
            import db
            db_path = getattr(db, "DB_PATH", None)
            if db_path and os.path.exists(db_path):
                shutil.copy2(db_path, os.path.join(backup_path, "data.db"))
        except Exception as e:
            logger.warning(f"备份数据库失败: {e}")

        # 备份配置
        try:
            import config
            config_path = getattr(config, "CONFIG_PATH", None)
            if config_path and os.path.exists(config_path):
                shutil.copy2(config_path, os.path.join(backup_path, "config.json"))
        except Exception:
            pass

        # 备份截图(可选)
        if include_screenshots:
            try:
                import config
                screenshots_dir = getattr(config, "SCREENSHOTS_DIR", None)
                if screenshots_dir and os.path.exists(screenshots_dir):
                    shutil.copytree(screenshots_dir, os.path.join(backup_path, "screenshots"))
            except Exception as e:
                logger.warning(f"备份截图失败: {e}")

        # 写入清单
        manifest = {
            "backup_time": datetime.now().isoformat(),
            "backup_path": backup_path,
            "include_screenshots": include_screenshots,
            "files": os.listdir(backup_path)
        }
        with open(os.path.join(backup_path, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        return {"status": "ok", "backup_path": backup_path, "manifest": manifest}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def list_backups(backup_dir: str) -> list:
    """列出所有备份"""
    try:
        if not os.path.exists(backup_dir):
            return []
        backups = []
        for name in sorted(os.listdir(backup_dir), reverse=True):
            if name.startswith("backup_"):
                path = os.path.join(backup_dir, name)
                manifest_path = os.path.join(path, "manifest.json")
                info = {"name": name, "path": path}
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as f:
                            info["manifest"] = json.load(f)
                    except Exception:
                        pass
                backups.append(info)
        return backups
    except Exception as e:
        return [{"error": str(e)}]


def restore_backup(backup_path: str) -> dict:
    """从备份恢复"""
    try:
        if not os.path.exists(backup_path):
            return {"status": "error", "error": "备份路径不存在"}

        manifest_path = os.path.join(backup_path, "manifest.json")
        if not os.path.exists(manifest_path):
            return {"status": "error", "error": "清单文件缺失"}

        # 恢复数据库
        db_backup = os.path.join(backup_path, "data.db")
        if os.path.exists(db_backup):
            try:
                import db
                db_path = getattr(db, "DB_PATH", None)
                if db_path:
                    shutil.copy2(db_backup, db_path)
            except Exception as e:
                logger.warning(f"恢复数据库失败: {e}")

        return {"status": "ok", "restored_from": backup_path}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─── P117: 状态快照 ──────────────────────────
_SNAPSHOTS: deque = deque(maxlen=20)


def take_snapshot() -> dict:
    """采集当前系统状态快照"""
    try:
        import psutil
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent,
            "memory_used_mb": round(psutil.virtual_memory().used / (1024 ** 2), 1),
            "disk_free_gb": round(psutil.disk_usage(os.getcwd()).free / (1024 ** 3), 2),
            "process_count": len(psutil.pids()),
            "thread_count": threading.active_count(),
        }
        _SNAPSHOTS.append(snapshot)
        return snapshot
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


def get_snapshots() -> list:
    return list(_SNAPSHOTS)


def diff_snapshots(s1: dict, s2: dict) -> dict:
    """比较两个快照的差异"""
    diff = {}
    for key in set(s1.keys()) | set(s2.keys()):
        if key == "timestamp":
            continue
        v1 = s1.get(key)
        v2 = s2.get(key)
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            diff[key] = {"from": v1, "to": v2, "delta": round(v2 - v1, 3)}
    return diff


# ─── P118: 故障注入测试 ──────────────────────────
def inject_fault(fault_type: str, duration: float = 1.0) -> dict:
    """注入故障用于测试弹性"""
    faults = {
        "delay": "延迟",
        "error": "错误",
        "memory_spike": "内存尖峰",
        "cpu_spike": "CPU 尖峰"
    }
    if fault_type not in faults:
        return {"status": "error", "error": f"未知故障类型: {fault_type}", "available": list(faults.keys())}

    start = time.time()
    result = {"fault": fault_type, "description": faults[fault_type], "duration": duration}

    if fault_type == "delay":
        time.sleep(duration)
    elif fault_type == "error":
        raise RuntimeError(f"注入错误: {faults[fault_type]}")
    elif fault_type == "memory_spike":
        # 分配 10MB 内存
        data = bytearray(10 * 1024 * 1024)
        time.sleep(duration)
        del data
    elif fault_type == "cpu_spike":
        end = time.time() + duration
        while time.time() < end:
            pass  # CPU 自旋

    result["elapsed"] = round(time.time() - start, 3)
    result["status"] = "completed"
    return result


# ─── P119: 自愈机制 ──────────────────────────
_HEALING_RULES: list[dict] = []
_HEALING_HISTORY: deque = deque(maxlen=100)


def register_healing_rule(name: str, condition: Callable, action: Callable,
                          cooldown: float = 300) -> None:
    """注册自愈规则"""
    _HEALING_RULES.append({
        "name": name,
        "condition": condition,
        "action": action,
        "cooldown": cooldown,
        "last_triggered": 0
    })


def run_healing_check() -> dict:
    """执行自愈检查"""
    results = []
    now = time.time()
    for rule in _HEALING_RULES:
        try:
            if now - rule["last_triggered"] < rule["cooldown"]:
                continue
            if rule["condition"]():
                logger.info(f"P119 触发自愈规则: {rule['name']}")
                rule["action"]()
                rule["last_triggered"] = now
                results.append({"rule": rule["name"], "status": "triggered"})
                _HEALING_HISTORY.append({
                    "rule": rule["name"],
                    "timestamp": datetime.now().isoformat(),
                    "status": "triggered"
                })
            else:
                results.append({"rule": rule["name"], "status": "ok"})
        except Exception as e:
            results.append({"rule": rule["name"], "status": "error", "error": str(e)})
            _HEALING_HISTORY.append({
                "rule": rule["name"],
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error": str(e)[:100]
            })
    return {"checked": len(results), "results": results}


def get_healing_history() -> list:
    return list(_HEALING_HISTORY)


def register_default_healing_rules() -> None:
    """注册默认自愈规则"""
    def check_high_memory():
        try:
            import psutil
            return psutil.virtual_memory().percent > 90
        except Exception:
            return False

    def action_gc():
        import gc
        gc.collect()
        logger.info("P119 高内存自愈：执行 GC")

    def check_db_locked():
        try:
            import db
            with db.get_conn() as conn:
                conn.execute("SELECT 1").fetchone()
            return False
        except Exception:
            return True

    def action_db_reconnect():
        try:
            import db
            if hasattr(db, "_reset_conn"):
                db._reset_conn()
            logger.info("P119 数据库自愈：重置连接")
        except Exception as e:
            logger.warning(f"数据库自愈失败: {e}")

    register_healing_rule("high_memory_gc", check_high_memory, action_gc, cooldown=120)
    register_healing_rule("db_reconnect", check_db_locked, action_db_reconnect, cooldown=60)
