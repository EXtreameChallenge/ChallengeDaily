"""
P81-P89: DevOps 与基础设施模块
- P81: 综合健康检查
- P82: 性能指标收集(Counter/Histogram)
- P83: 日志聚合与错误统计
- P84: 配置热更新
- P85: 资源监控(CPU/Memory/Disk)
- P86: 优雅关闭机制
- P87: 进程管理
- P88: 部署清单生成
- P89: 版本管理与回滚
"""
import logging
import threading
import time
import json
import os
import sys
import platform

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P81: 综合健康检查 ──────────────────────────
def health_check_full() -> dict:
    """综合健康检查：数据库、磁盘、内存、AI、文件系统"""
    checks: list[dict] = []

    # 1. 数据库
    try:
        import db
        with db.get_conn() as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
            checks.append({"name": "database", "status": "ok", "detail": f"{cnt} activities"})
    except Exception as e:
        checks.append({"name": "database", "status": "error", "detail": str(e)[:100]})

    # 2. 内存
    if psutil is None:
        checks.append({"name": "memory", "status": "unknown", "detail": "psutil not installed"})
    else:
        try:
            mem = psutil.virtual_memory()
            status = "ok" if mem.percent < 85 else ("warn" if mem.percent < 95 else "error")
            checks.append({"name": "memory", "status": status, "detail": f"{mem.percent}% used"})
        except Exception:
            checks.append({"name": "memory", "status": "unknown", "detail": "psutil unavailable"})

    # 3. 磁盘
    if psutil is None:
        checks.append({"name": "disk", "status": "unknown", "detail": "psutil not installed"})
    else:
        try:
            disk = psutil.disk_usage(os.getcwd())
            free_gb = disk.free / (1024 ** 3)
            status = "ok" if free_gb > 1 else ("warn" if free_gb > 0.2 else "error")
            checks.append({"name": "disk", "status": status, "detail": f"{free_gb:.1f}GB free"})
        except Exception:
            checks.append({"name": "disk", "status": "unknown"})

    # 4. CPU
    if psutil is None:
        checks.append({"name": "cpu", "status": "unknown", "detail": "psutil not installed"})
    else:
        try:
            cpu = psutil.cpu_percent(interval=0.5)
            status = "ok" if cpu < 80 else ("warn" if cpu < 95 else "error")
            checks.append({"name": "cpu", "status": status, "detail": f"{cpu}%"})
        except Exception:
            checks.append({"name": "cpu", "status": "unknown"})

    # 5. 截图目录
    try:
        import config
        screenshots_dir = getattr(config, "SCREENSHOTS_DIR", None)
        if screenshots_dir and os.path.exists(screenshots_dir):
            checks.append({"name": "screenshots_dir", "status": "ok", "detail": screenshots_dir})
        else:
            checks.append({"name": "screenshots_dir", "status": "warn", "detail": "dir missing"})
    except Exception:
        checks.append({"name": "screenshots_dir", "status": "unknown"})

    # 汇总
    overall = "ok"
    for c in checks:
        if c["status"] == "error":
            overall = "error"
            break
        if c["status"] == "warn" and overall != "error":
            overall = "warn"

    return {
        "status": overall,
        "checks": checks,
        "timestamp": datetime.now().isoformat(),
        "uptime_seconds": _get_uptime()
    }


_START_TIME = time.time()


def _get_uptime() -> float:
    return round(time.time() - _START_TIME, 1)


# ─── P82: 性能指标收集 ──────────────────────────
_METRICS_LOCK = threading.RLock()
_counters: dict[str, float] = defaultdict(float)
_gauges: dict[str, float] = {}
_histograms: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))


def counter_inc(name: str, value: float = 1) -> None:
    with _METRICS_LOCK:
        _counters[name] += value


def gauge_set(name: str, value: float) -> None:
    with _METRICS_LOCK:
        _gauges[name] = value


def histogram_observe(name: str, value: float) -> None:
    with _METRICS_LOCK:
        _histograms[name].append(value)


def get_metrics() -> dict:
    with _METRICS_LOCK:
        hist_stats = {}
        for name, values in _histograms.items():
            if not values:
                continue
            sorted_v = sorted(values)
            n = len(sorted_v)
            hist_stats[name] = {
                "count": n,
                "min": round(sorted_v[0], 3),
                "max": round(sorted_v[-1], 3),
                "avg": round(sum(sorted_v) / n, 3),
                "p50": round(sorted_v[n // 2], 3),
                "p95": round(sorted_v[int(n * 0.95)] if n > 1 else sorted_v[0], 3),
                "p99": round(sorted_v[int(n * 0.99)] if n > 1 else sorted_v[0], 3),
            }
        return {
            "counters": dict(_counters),
            "gauges": dict(_gauges),
            "histograms": hist_stats,
            "collected_at": datetime.now().isoformat()
        }


class metrics_timer:
    """上下文管理器：测量代码块耗时并记录到 histogram"""

    def __init__(self, name: str):
        self.name = name
        self._start = 0

    def __enter__(self):
        self._start = time.time()
        return self

    def __exit__(self, *args):
        elapsed = (time.time() - self._start) * 1000  # ms
        histogram_observe(self.name, round(elapsed, 2))


# ─── P83: 日志聚合与错误统计 ──────────────────────────
_ERROR_STATS_LOCK = threading.Lock()
_error_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "last_msg": "", "last_time": None})


def record_error(module: str, message: str, level: str = "ERROR") -> None:
    with _ERROR_STATS_LOCK:
        stat = _error_stats[module]
        stat["count"] += 1
        stat["last_msg"] = message[:200]
        stat["last_time"] = datetime.now().isoformat()
        stat["level"] = level


def get_error_stats() -> dict:
    with _ERROR_STATS_LOCK:
        return {
            "modules": dict(_error_stats),
            "total_errors": sum(s["count"] for s in _error_stats.values()),
            "queried_at": datetime.now().isoformat()
        }


def clear_error_stats() -> None:
    with _ERROR_STATS_LOCK:
        _error_stats.clear()


# ─── P84: 配置热更新 ──────────────────────────
_CONFIG_WATCHERS: dict[str, list[Callable]] = defaultdict(list)
_runtime_config: dict[str, Any] = {}


def register_config_watcher(key: str, callback: Callable) -> None:
    _CONFIG_WATCHERS[key].append(callback)


def update_config(key: str, value: Any) -> dict:
    """更新运行时配置并通知观察者"""
    old = _runtime_config.get(key)
    _runtime_config[key] = value
    notified = 0
    for cb in _CONFIG_WATCHERS.get(key, []):
        try:
            cb(key, old, value)
            notified += 1
        except Exception as e:
            logger.warning(f"配置观察者失败 {key}: {e}")
    return {"status": "ok", "key": key, "old": old, "new": value, "notified": notified}


def get_runtime_config() -> dict:
    return dict(_runtime_config)


# ─── P85: 资源监控 ──────────────────────────
_RESOURCE_HISTORY: deque = deque(maxlen=144)  # 24 小时，每 10 分钟一个点
_RESOURCE_LOCK = threading.Lock()


def sample_resources() -> dict:
    """采样当前资源使用"""
    if psutil is None:
        return {"error": "psutil not installed"}
    try:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(os.getcwd())
        sample = {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": mem.percent,
            "memory_used_mb": round(mem.used / (1024 ** 2), 1),
            "disk_percent": disk.percent,
            "disk_free_gb": round(disk.free / (1024 ** 3), 2),
            "process_count": len(psutil.pids()),
            "uptime_seconds": _get_uptime()
        }
        with _RESOURCE_LOCK:
            _RESOURCE_HISTORY.append(sample)
        return sample
    except Exception as e:
        return {"error": str(e)}


def get_resource_history() -> list:
    with _RESOURCE_LOCK:
        return list(_RESOURCE_HISTORY)


# ─── P86: 优雅关闭机制 ──────────────────────────
_SHUTDOWN_HOOKS: list[Callable] = []
_SHUTDOWN_STARTED = False
_SHUTDOWN_LOCK = threading.Lock()


def register_shutdown_hook(name: str, hook: Callable) -> None:
    _SHUTDOWN_HOOKS.append((name, hook))


def graceful_shutdown(timeout: float = 10.0) -> dict:
    """执行所有关闭钩子"""
    global _SHUTDOWN_STARTED
    with _SHUTDOWN_LOCK:
        if _SHUTDOWN_STARTED:
            return {"status": "already_shutting_down"}
        _SHUTDOWN_STARTED = True

    results = []
    start = time.time()
    for name, hook in _SHUTDOWN_HOOKS:
        if time.time() - start > timeout:
            results.append({"name": name, "status": "timeout"})
            break
        try:
            hook()
            results.append({"name": name, "status": "ok"})
        except Exception as e:
            results.append({"name": name, "status": "error", "error": str(e)[:100]})

    return {
        "status": "completed",
        "hooks": results,
        "duration_seconds": round(time.time() - start, 2)
    }


# ─── P87: 进程管理 ──────────────────────────
def list_processes(filter_name: str = "") -> list:
    """列出相关进程"""
    if psutil is None:
        return [{"error": "psutil not installed"}]
    try:
        result = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
            try:
                info = p.info
                if filter_name and filter_name.lower() not in (info["name"] or "").lower():
                    continue
                mem_mb = info["memory_info"].rss / (1024 ** 2) if info.get("memory_info") else 0
                result.append({
                    "pid": info["pid"],
                    "name": info["name"],
                    "cpu_percent": info["cpu_percent"] or 0,
                    "memory_mb": round(mem_mb, 1)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        result.sort(key=lambda x: x["memory_mb"], reverse=True)
        return result[:50]
    except Exception as e:
        return [{"error": str(e)}]


# ─── P88: 部署清单生成 ──────────────────────────
def generate_deploy_manifest() -> dict:
    """生成部署清单"""
    try:
        import sys
        manifest = {
            "app_name": "challenge-daily",
            "version": _read_version(),
            "generated_at": datetime.now().isoformat(),
            "environment": {
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "machine": platform.machine(),
                "processor": platform.processor(),
            },
            "resources": sample_resources(),
            "config": get_runtime_config(),
            "blueprints": _list_blueprints(),
            "required_packages": _list_required_packages(),
        }
        return manifest
    except Exception as e:
        return {"error": str(e)}


def _read_version() -> str:
    try:
        import db
        return getattr(db, "__version__", "1.0.0")
    except Exception:
        return "1.0.0"


def _list_blueprints() -> list:
    try:
        from routes import ALL_BLUEPRINTS
        return [bp.name for bp in ALL_BLUEPRINTS]
    except Exception:
        return []


def _list_required_packages() -> list:
    return ["flask", "waitress", "Pillow", "mss", "psutil", "openai", "requests"]


# ─── P89: 版本管理与回滚 ──────────────────────────
_VERSION_HISTORY: deque = deque(maxlen=20)


def record_version(version: str, notes: str = "") -> None:
    _VERSION_HISTORY.append({
        "version": version,
        "notes": notes,
        "installed_at": datetime.now().isoformat()
    })


def get_version_history() -> list:
    return list(_VERSION_HISTORY)


def get_current_version() -> str:
    if _VERSION_HISTORY:
        return _VERSION_HISTORY[-1]["version"]
    return _read_version()
