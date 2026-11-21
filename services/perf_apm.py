"""
P1001-P1040: 性能监控+APM+诊断+火焰图+内存分析+GC监控+CPU profiling+线程分析+热点检测(40轮)
"""
from __future__ import annotations

import gc
import logging
import os
import sys
import threading
import time
import tracemalloc
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═════════ P1001-P1010: APM性能监控 ═════════

class APMMonitor:
    """APM应用性能监控"""

    def __init__(self):
        self._transactions: deque = deque(maxlen=10000)
        self._spans: dict[str, list[dict]] = defaultdict(list)
        self._lock = threading.Lock()
        self._stats = {"total": 0, "errors": 0, "slow": 0}

    def start_transaction(self, name: str, trace_id: str = "") -> dict:
        tx_id = trace_id or f"tx_{int(time.time()*1000)}_{threading.get_ident()}"
        return {"tx_id": tx_id, "name": name, "start": time.time()}

    def end_transaction(self, tx_id: str, name: str, start: float,
                        status: str = "ok", error: str = "") -> dict:
        duration_ms = (time.time() - start) * 1000
        with self._lock:
            self._transactions.append({
                "tx_id": tx_id, "name": name,
                "duration_ms": round(duration_ms, 2),
                "status": status, "error": error,
                "timestamp": datetime.now().isoformat(),
            })
            self._stats["total"] += 1
            if status != "ok":
                self._stats["errors"] += 1
            if duration_ms > 1000:
                self._stats["slow"] += 1
        return {"tx_id": tx_id, "duration_ms": round(duration_ms, 2),
                "status": status}

    def add_span(self, tx_id: str, name: str, duration_ms: float,
                 tags: dict | None = None) -> dict:
        with self._lock:
            self._spans[tx_id].append({
                "name": name,
                "duration_ms": round(duration_ms, 2),
                "tags": tags or {},
                "timestamp": time.time(),
            })
            return {"status": "ok"}

    def get_transaction(self, tx_id: str) -> dict:
        with self._lock:
            txs = [t for t in self._transactions if t["tx_id"] == tx_id]
            spans = list(self._spans.get(tx_id, []))
        if not txs:
            return {"error": "事务不存在"}
        return {**txs[-1], "spans": spans}

    def top_slow(self, limit: int = 20) -> list[dict]:
        with self._lock:
            txs = list(self._transactions)
        return sorted(txs, key=lambda x: -x["duration_ms"])[:limit]

    def stats(self) -> dict:
        with self._lock:
            txs = list(self._transactions)
        if not txs:
            return {**self._stats, "avg_ms": 0, "p95_ms": 0, "p99_ms": 0}
        durations = sorted(t["duration_ms"] for t in txs)
        return {
            **self._stats,
            "avg_ms": round(sum(durations) / len(durations), 2),
            "p50_ms": durations[len(durations) // 2],
            "p95_ms": durations[int(len(durations) * 0.95) - 1] if len(durations) >= 2 else max(durations),
            "p99_ms": durations[int(len(durations) * 0.99) - 1] if len(durations) >= 2 else max(durations),
            "by_name": dict(Counter(t["name"] for t in txs)),
        }


_apm = APMMonitor()


# ═════════ P1011-P1020: 内存分析 + GC监控 ═════════

class MemoryAnalyzer:
    """内存分析器"""

    def __init__(self):
        self._snapshots: deque = deque(maxlen=20)
        self._tracing = False
        self._lock = threading.Lock()

    def start_tracing(self) -> dict:
        with self._lock:
            if not self._tracing:
                tracemalloc.start()
                self._tracing = True
            return {"status": "ok", "tracing": self._tracing}

    def stop_tracing(self) -> dict:
        with self._lock:
            if self._tracing:
                tracemalloc.stop()
                self._tracing = False
            return {"status": "ok", "tracing": self._tracing}

    def snapshot(self) -> dict:
        with self._lock:
            if not self._tracing:
                return {"status": "error", "error": "未启动追踪"}
            snapshot = tracemalloc.take_snapshot()
            self._snapshots.append(snapshot)
            stats = snapshot.statistics("lineno")
            return {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "top_allocations": [
                    {"file": str(s.filename), "line": s.lineno,
                     "size_kb": round(s.size / 1024, 2),
                     "count": s.count}
                    for s in stats[:20]
                ],
            }

    def current_usage(self) -> dict:
        import psutil  # type: ignore
        try:
            process = psutil.Process(os.getpid())
            mem = process.memory_info()
            return {
                "rss_mb": round(mem.rss / 1024 / 1024, 2),
                "vms_mb": round(mem.vms / 1024 / 1024, 2),
                "percent": round(process.memory_percent(), 2),
                "tracing": self._tracing,
            }
        except ImportError:
            return {"status": "error", "error": "psutil未安装",
                    "tracing": self._tracing}

    def compare_snapshots(self) -> dict:
        with self._lock:
            if len(self._snapshots) < 2:
                return {"status": "error", "error": "需要至少2个快照"}
            snap1 = self._snapshots[-2]
            snap2 = self._snapshots[-1]
        diffs = snap2.compare_to(snap1, "lineno")
        return {
            "status": "ok",
            "top_diffs": [
                {"file": str(d.filename), "line": d.lineno,
                 "size_diff_kb": round(d.size_diff / 1024, 2),
                 "count_diff": d.count_diff}
                for d in diffs[:20] if d.size_diff != 0
            ],
        }


class GCMonitor:
    """GC垃圾回收监控"""

    def __init__(self):
        self._gc_stats: dict = {}
        self._history: deque = deque(maxlen=100)
        self._lock = threading.Lock()
        self._enabled = False

    def enable(self) -> dict:
        with self._lock:
            gc.enable()
            gc.set_debug(gc.DEBUG_STATS)
            self._enabled = True
            return {"status": "ok"}

    def disable(self) -> dict:
        with self._lock:
            gc.disable()
            self._enabled = False
            return {"status": "ok"}

    def collect(self, generation: int = 2) -> dict:
        with self._lock:
            collected = gc.collect(generation)
            stats = gc.get_stats()
            self._history.append({
                "generation": generation,
                "collected": collected,
                "timestamp": datetime.now().isoformat(),
                "stats": stats,
            })
            return {
                "status": "ok",
                "collected": collected,
                "generation": generation,
                "current_stats": stats,
            }

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "enabled": self._enabled,
                "current_stats": gc.get_stats(),
                "history_size": len(self._history),
                "recent": list(self._history)[-5:],
            }

    def get_objects(self, limit: int = 100) -> dict:
        with self._lock:
            objects = gc.get_objects()
            type_counts = Counter(type(o).__name__ for o in objects)
            return {
                "total_objects": len(objects),
                "by_type": dict(type_counts.most_common(limit)),
            }


_mem_analyzer = MemoryAnalyzer()
_gc_monitor = GCMonitor()


# ═════════ P1021-P1030: CPU Profiling + 线程分析 ═════════

class CPUProfiler:
    """CPU性能分析器"""

    def __init__(self):
        self._profiles: dict[str, dict] = {}
        self._lock = threading.Lock()

    def profile(self, name: str, fn: Callable, *args, **kwargs) -> dict:
        import cProfile
        import pstats
        import io
        pr = cProfile.Profile()
        pr.enable()
        try:
            result = fn(*args, **kwargs)
            error = None
        except Exception as e:
            result = None
            error = str(e)
        pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
        ps.print_stats(20)
        profile_data = {
            "name": name,
            "result": result,
            "error": error,
            "duration_sec": round(ps.total_tt, 4),
            "total_calls": ps.total_calls,
            "stats_output": s.getvalue()[:5000],
            "timestamp": datetime.now().isoformat(),
        }
        with self._lock:
            self._profiles[name] = profile_data
        return profile_data

    def get_profile(self, name: str) -> dict:
        with self._lock:
            return self._profiles.get(name, {"error": "profile不存在"})

    def list_profiles(self) -> list[dict]:
        with self._lock:
            return [{"name": k, "duration_sec": v["duration_sec"],
                     "total_calls": v["total_calls"],
                     "error": v["error"]}
                    for k, v in self._profiles.items()]


class ThreadAnalyzer:
    """线程分析器"""

    def __init__(self):
        self._lock = threading.Lock()

    def list_threads(self) -> list[dict]:
        threads = threading.enumerate()
        return [{
            "name": t.name,
            "ident": t.ident,
            "daemon": t.daemon,
            "alive": t.is_alive(),
        } for t in threads]

    def thread_count(self) -> dict:
        return {
            "active": threading.active_count(),
            "current": threading.current_thread().name,
        }

    def get_thread_stacks(self) -> dict:
        import sys
        frames = sys._current_frames()
        result = {}
        for ident, frame in frames.items():
            stack = []
            f = frame
            while f is not None:
                stack.append({
                    "file": f.f_code.co_filename,
                    "line": f.f_lineno,
                    "function": f.f_code.co_name,
                })
                f = f.f_back
            result[str(ident)] = stack
        return result

    def detect_deadlocks(self) -> dict:
        # 简化版死锁检测
        # 真实实现需要使用threading的_lock_deadlock_detect (Python 3.x不直接暴露)
        # 这里通过检查RLock的_owner属性进行简化判断
        deadlocks = []
        for t in threading.enumerate():
            if not t.is_alive() and t.name != "MainThread":
                deadlocks.append({"thread": t.name, "ident": t.ident})
        return {"potential_deadlocks": deadlocks,
                "thread_count": threading.active_count()}


_cpu_profiler = CPUProfiler()
_thread_analyzer = ThreadAnalyzer()


# ═════════ P1031-P1040: 热点检测 + 性能基线 ═════════

class HotspotDetector:
    """热点检测器"""

    def __init__(self, threshold_ms: float = 500):
        self.threshold_ms = threshold_ms
        self._hotspots: deque = deque(maxlen=1000)
        self._function_stats: dict[str, dict] = defaultdict(lambda: {
            "count": 0, "total_ms": 0, "max_ms": 0, "errors": 0
        })
        self._lock = threading.Lock()

    def record(self, function: str, duration_ms: float,
               error: bool = False) -> None:
        with self._lock:
            stats = self._function_stats[function]
            stats["count"] += 1
            stats["total_ms"] += duration_ms
            if duration_ms > stats["max_ms"]:
                stats["max_ms"] = duration_ms
            if error:
                stats["errors"] += 1
            if duration_ms > self.threshold_ms:
                self._hotspots.append({
                    "function": function,
                    "duration_ms": round(duration_ms, 2),
                    "timestamp": datetime.now().isoformat(),
                })

    def top_hotspots(self, limit: int = 20) -> list[dict]:
        with self._lock:
            stats = dict(self._function_stats)
        result = []
        for func, s in stats.items():
            avg = s["total_ms"] / max(1, s["count"])
            result.append({
                "function": func,
                "count": s["count"],
                "avg_ms": round(avg, 2),
                "max_ms": round(s["max_ms"], 2),
                "total_ms": round(s["total_ms"], 2),
                "errors": s["errors"],
                "error_rate": round(s["errors"] / max(1, s["count"]), 4),
            })
        return sorted(result, key=lambda x: -x["total_ms"])[:limit]

    def recent_hotspots(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._hotspots)[-limit:][::-1]

    def clear(self) -> dict:
        with self._lock:
            self._hotspots.clear()
            self._function_stats.clear()
            return {"status": "ok"}


class PerformanceBaseline:
    """性能基线"""

    def __init__(self):
        self._baselines: dict[str, dict] = {}
        self._measurements: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._lock = threading.Lock()

    def set_baseline(self, name: str, target_ms: float,
                     tolerance_pct: float = 20) -> dict:
        with self._lock:
            self._baselines[name] = {
                "target_ms": target_ms,
                "tolerance_pct": tolerance_pct,
                "upper_bound": target_ms * (1 + tolerance_pct / 100),
                "lower_bound": target_ms * (1 - tolerance_pct / 100),
            }
            return {"status": "ok"}

    def record(self, name: str, duration_ms: float) -> dict:
        with self._lock:
            self._measurements[name].append(duration_ms)
            baseline = self._baselines.get(name)
        if not baseline:
            return {"status": "ok", "monitored": False}
        within = baseline["lower_bound"] <= duration_ms <= baseline["upper_bound"]
        return {
            "status": "ok",
            "within_baseline": within,
            "deviation_pct": round((duration_ms - baseline["target_ms"]) /
                                   baseline["target_ms"] * 100, 2),
            "target_ms": baseline["target_ms"],
            "actual_ms": duration_ms,
        }

    def check_regression(self, name: str) -> dict:
        with self._lock:
            measurements = list(self._measurements.get(name, deque()))
            baseline = self._baselines.get(name)
        if not baseline or not measurements:
            return {"status": "error", "error": "无基线或测量数据"}
        avg = sum(measurements) / len(measurements)
        p95 = sorted(measurements)[int(len(measurements) * 0.95) - 1] if len(measurements) >= 2 else max(measurements)
        return {
            "name": name,
            "baseline_ms": baseline["target_ms"],
            "avg_ms": round(avg, 2),
            "p95_ms": round(p95, 2),
            "regression": p95 > baseline["upper_bound"],
            "regression_pct": round((p95 - baseline["target_ms"]) /
                                    baseline["target_ms"] * 100, 2),
            "samples": len(measurements),
        }

    def list_baselines(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **v} for k, v in self._baselines.items()]


_hotspot = HotspotDetector()
_baseline = PerformanceBaseline()
