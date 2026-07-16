"""
P191-P199: 可观测性体系
- P191: 指标采集器
- P192: 直方图指标
- P193: 计数器指标
- P194: 仪表盘指标
- P195: 分布式追踪
- P196: 日志聚合
- P197: 健康检查
- P198: 告警规则引擎
- P199: SLO 管理
"""
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P191-P194: 指标系统 ──────────────────────────
class MetricsCollector:
    """指标采集器(计数器/仪表盘/直方图)"""
    def __init__(self):
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def inc_counter(self, name: str, value: float = 1, tags: dict = None) -> None:
        key = self._make_key(name, tags)
        with self._lock:
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, tags: dict = None) -> None:
        key = self._make_key(name, tags)
        with self._lock:
            self._gauges[key] = value

    def observe_histogram(self, name: str, value: float, tags: dict = None) -> None:
        key = self._make_key(name, tags)
        with self._lock:
            self._histograms[key].append(value)
            if len(self._histograms[key]) > 10000:
                self._histograms[key] = self._histograms[key][-5000:]

    def get_counter(self, name: str, tags: dict = None) -> float:
        return self._counters.get(self._make_key(name, tags), 0)

    def get_gauge(self, name: str, tags: dict = None) -> float:
        return self._gauges.get(self._make_key(name, tags), 0)

    def get_histogram_stats(self, name: str, tags: dict = None) -> dict:
        key = self._make_key(name, tags)
        vals = self._histograms.get(key, [])
        if not vals:
            return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}
        s = sorted(vals)
        return {
            "count": len(vals), "sum": sum(vals),
            "avg": sum(vals) / len(vals),
            "min": vals[0], "max": vals[-1],
            "p50": s[len(s) // 2],
            "p90": s[int(len(s) * 0.9)] if len(s) > 1 else s[0],
            "p99": s[int(len(s) * 0.99)] if len(s) > 1 else s[0],
        }

    def export(self) -> dict:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {k: len(v) for k, v in self._histograms.items()},
                "timestamp": datetime.now().isoformat()
            }

    @staticmethod
    def _make_key(name: str, tags: dict = None) -> str:
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"


_metrics = MetricsCollector()


# ─── P195: 分布式追踪 ──────────────────────────
class DistributedTracer:
    """分布式追踪"""
    def __init__(self):
        self._spans: deque = deque(maxlen=5000)
        self._active: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start_span(self, trace_id: str, span_id: str,
                   parent_id: str = "", operation: str = "") -> dict:
        span = {
            "trace_id": trace_id, "span_id": span_id,
            "parent_id": parent_id, "operation": operation,
            "start_time": time.time(), "end_time": None,
            "tags": {}, "status": "active"
        }
        with self._lock:
            self._active[span_id] = span
        return span

    def finish_span(self, span_id: str, status: str = "ok") -> None:
        with self._lock:
            span = self._active.pop(span_id, None)
            if span:
                span["end_time"] = time.time()
                span["duration_ms"] = (span["end_time"] - span["start_time"]) * 1000
                span["status"] = status
                self._spans.append(span)

    def add_tag(self, span_id: str, key: str, value: Any) -> None:
        with self._lock:
            span = self._active.get(span_id)
            if span:
                span["tags"][key] = value

    def get_trace(self, trace_id: str) -> list[dict]:
        with self._lock:
            return [s for s in self._spans if s["trace_id"] == trace_id]

    def get_recent_spans(self, limit: int = 100) -> list[dict]:
        with self._lock:
            spans = list(self._spans)
        spans.reverse()
        return spans[:limit]


_tracer = DistributedTracer()


# ─── P196: 日志聚合 ──────────────────────────
class LogAggregator:
    """结构化日志聚合"""
    def __init__(self):
        self._logs: deque = deque(maxlen=10000)
        self._lock = threading.Lock()

    def log(self, level: str, message: str,
            source: str = "", extra: dict = None) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level.upper(),
            "message": message,
            "source": source,
            "extra": extra or {}
        }
        with self._lock:
            self._logs.append(entry)

    def search(self, query: str = "", level: str = "",
               source: str = "", limit: int = 100) -> list[dict]:
        with self._lock:
            logs = list(self._logs)
        result = []
        for log in reversed(logs):
            if level and log["level"] != level.upper():
                continue
            if source and log["source"] != source:
                continue
            if query and query.lower() not in log["message"].lower():
                continue
            result.append(log)
            if len(result) >= limit:
                break
        return result

    def stats(self) -> dict:
        with self._lock:
            logs = list(self._logs)
        level_counts = defaultdict(int)
        for log in logs:
            level_counts[log["level"]] += 1
        return {
            "total": len(logs),
            "by_level": dict(level_counts),
        }


_log_agg = LogAggregator()


# ─── P197: 健康检查 ──────────────────────────
class HealthChecker:
    """健康检查注册与执行"""
    def __init__(self):
        self._checks: dict[str, Callable] = {}
        self._lock = threading.Lock()

    def register(self, name: str, check_fn: Callable[[], dict]) -> None:
        with self._lock:
            self._checks[name] = check_fn

    def run_all(self) -> dict:
        results = {}
        overall = "healthy"
        with self._lock:
            checks = dict(self._checks)
        for name, fn in checks.items():
            try:
                result = fn()
                results[name] = result
                if result.get("status") != "healthy":
                    overall = "degraded"
            except Exception as e:
                results[name] = {"status": "unhealthy", "error": str(e)}
                overall = "unhealthy"
        return {"status": overall, "checks": results, "timestamp": datetime.now().isoformat()}

    def run_one(self, name: str) -> dict:
        with self._lock:
            fn = self._checks.get(name)
        if not fn:
            return {"status": "unknown", "error": "检查不存在"}
        try:
            return fn()
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


_health = HealthChecker()


# ─── P198: 告警规则引擎 ──────────────────────────
class AlertEngine:
    """告警规则引擎"""
    def __init__(self):
        self._rules: dict[str, dict] = {}
        self._incidents: deque = deque(maxlen=500)
        self._lock = threading.Lock()

    def add_rule(self, name: str, metric_name: str,
                 condition: str, threshold: float,
                 severity: str = "warning") -> None:
        with self._lock:
            self._rules[name] = {
                "metric": metric_name, "condition": condition,
                "threshold": threshold, "severity": severity,
                "enabled": True, "triggered_count": 0
            }

    def evaluate(self, metrics: dict[str, float]) -> list[dict]:
        alerts = []
        with self._lock:
            rules = dict(self._rules)
        for name, rule in rules.items():
            if not rule["enabled"]:
                continue
            value = metrics.get(rule["metric"], 0)
            triggered = False
            if rule["condition"] == ">" and value > rule["threshold"]:
                triggered = True
            elif rule["condition"] == "<" and value < rule["threshold"]:
                triggered = True
            elif rule["condition"] == "==" and value == rule["threshold"]:
                triggered = True
            elif rule["condition"] == "!=" and value != rule["threshold"]:
                triggered = True
            if triggered:
                alert = {
                    "rule": name, "metric": rule["metric"],
                    "value": value, "threshold": rule["threshold"],
                    "severity": rule["severity"],
                    "timestamp": datetime.now().isoformat()
                }
                alerts.append(alert)
                with self._lock:
                    rule["triggered_count"] += 1
                    self._incidents.append(alert)
        return alerts

    def list_rules(self) -> dict:
        with self._lock:
            return dict(self._rules)

    def get_incidents(self, limit: int = 50) -> list[dict]:
        with self._lock:
            incidents = list(self._incidents)
        incidents.reverse()
        return incidents[:limit]

    def toggle_rule(self, name: str, enabled: bool) -> bool:
        with self._lock:
            if name in self._rules:
                self._rules[name]["enabled"] = enabled
                return True
            return False


_alert_engine = AlertEngine()


# ─── P199: SLO 管理 ──────────────────────────
class SLOManager:
    """SLO/SLI 管理"""
    def __init__(self):
        self._slos: dict[str, dict] = {}
        self._lock = threading.Lock()

    def define(self, name: str, target: float, window_days: int = 30,
               sli_fn: Callable[[], float] = None) -> None:
        with self._lock:
            self._slos[name] = {
                "target": target, "window_days": window_days,
                "sli_fn": sli_fn, "current_sli": 0,
                "error_budget": 0, "status": "unknown"
            }

    def evaluate(self, name: str, current_sli: float = None) -> dict:
        with self._lock:
            slo = self._slos.get(name)
        if not slo:
            return {"error": "SLO 不存在"}
        sli = current_sli if current_sli is not None else 0
        if slo["sli_fn"]:
            try:
                sli = slo["sli_fn"]()
            except Exception:
                pass
        error_budget = max(0, 1 - sli) / max(0.001, 1 - slo["target"])
        status = "meeting" if sli >= slo["target"] else "violating"
        with self._lock:
            slo["current_sli"] = sli
            slo["error_budget"] = error_budget
            slo["status"] = status
        return {
            "name": name, "sli": sli, "target": slo["target"],
            "error_budget_remaining": error_budget, "status": status
        }

    def evaluate_all(self) -> list[dict]:
        with self._lock:
            names = list(self._slos.keys())
        return [self.evaluate(n) for n in names]

    def list_slos(self) -> dict:
        with self._lock:
            return {k: {"target": v["target"], "status": v["status"],
                        "current_sli": v["current_sli"]}
                    for k, v in self._slos.items()}


_slo_mgr = SLOManager()
