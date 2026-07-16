"""
P361-P370: 混沌工程 + 容量规划
- P361: 混沌实验管理
- P362: 故障注入器
- P363: 爆炸半径控制
- P364: 系统稳态假设
- P365: 容量评估器
- P366: 资源规划器
- P367: 负载预测
- P368: 自动扩缩容策略
- P369: 容量告警
- P370: 混沌实验报告
"""
from __future__ import annotations

import logging
import math
import random
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P361: 混沌实验管理 ──────────────────────────
class ChaosExperiment:
    """混沌实验管理"""

    def __init__(self):
        self._experiments: dict[str, dict] = {}
        self._running: set[str] = set()
        self._lock = threading.Lock()

    def create(self, name: str, target: str, fault_type: str,
               duration_sec: int = 60, params: dict | None = None) -> dict:
        with self._lock:
            if name in self._experiments:
                return {"status": "error", "error": "实验已存在"}
            self._experiments[name] = {
                "target": target,
                "fault_type": fault_type,
                "duration_sec": duration_sec,
                "params": params or {},
                "status": "created",
                "created_at": datetime.now().isoformat(),
            }
            return {"status": "ok", "experiment": name}

    def start(self, name: str) -> dict:
        with self._lock:
            exp = self._experiments.get(name)
            if not exp:
                return {"status": "error", "error": "实验不存在"}
            if name in self._running:
                return {"status": "error", "error": "实验正在运行"}
            self._running.add(name)
            exp["status"] = "running"
            exp["started_at"] = datetime.now().isoformat()
            return {"status": "ok", "experiment": name, "fault_type": exp["fault_type"]}

    def stop(self, name: str) -> dict:
        with self._lock:
            exp = self._experiments.get(name)
            if not exp:
                return {"status": "error", "error": "实验不存在"}
            self._running.discard(name)
            exp["status"] = "stopped"
            exp["stopped_at"] = datetime.now().isoformat()
            return {"status": "ok"}

    def list_experiments(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **v} for k, v in self._experiments.items()]


_chaos = ChaosExperiment()


# ─── P362: 故障注入器 ──────────────────────────
class FaultInjector:
    """故障注入器"""

    FAULT_TYPES = ["latency", "error", "cpu_stress", "memory_stress",
                   "network_partition", "disk_full", "dependency_down"]

    @classmethod
    def inject_latency(cls, delay_ms: int = 100) -> dict:
        return {"fault": "latency", "delay_ms": delay_ms,
                "description": f"注入{delay_ms}ms延迟"}

    @classmethod
    def inject_error(cls, error_rate: float = 0.1, error_code: int = 500) -> dict:
        return {"fault": "error", "error_rate": error_rate,
                "error_code": error_code,
                "description": f"注入{error_rate*100}%错误率"}

    @classmethod
    def inject_cpu_stress(cls, load_percent: int = 80, duration_sec: int = 60) -> dict:
        return {"fault": "cpu_stress", "load_percent": load_percent,
                "duration_sec": duration_sec,
                "description": f"CPU负载提升到{load_percent}%"}

    @classmethod
    def inject_network_partition(cls, target: str = "database") -> dict:
        return {"fault": "network_partition", "target": target,
                "description": f"隔离{target}网络"}

    @classmethod
    def should_fail(cls, error_rate: float) -> bool:
        return random.random() < error_rate

    @classmethod
    def list_faults(cls) -> list[str]:
        return list(cls.FAULT_TYPES)


_fault_injector = FaultInjector()


# ─── P363: 爆炸半径控制 ──────────────────────────
class BlastRadiusController:
    """爆炸半径控制"""

    def __init__(self):
        self._limits: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set_limit(self, target: str, max_affected_percent: float = 5.0,
                  max_affected_count: int = 10) -> None:
        with self._lock:
            self._limits[target] = {
                "max_percent": max_affected_percent,
                "max_count": max_affected_count,
            }

    def check(self, target: str, total_instances: int,
              affected_instances: int) -> dict:
        with self._lock:
            limit = self._limits.get(target, {"max_percent": 5.0, "max_count": 10})
        percent = (affected_instances / total_instances * 100) if total_instances > 0 else 0
        within_percent = percent <= limit["max_percent"]
        within_count = affected_instances <= limit["max_count"]
        return {
            "target": target,
            "total": total_instances,
            "affected": affected_instances,
            "percent": round(percent, 2),
            "limit_percent": limit["max_percent"],
            "limit_count": limit["max_count"],
            "allowed": within_percent and within_count,
            "reason": "ok" if (within_percent and within_count) else "超出爆炸半径限制",
        }

    def get_limits(self) -> dict:
        with self._lock:
            return dict(self._limits)


_blast = BlastRadiusController()


# ─── P364: 系统稳态假设 ──────────────────────────
class SteadyStateHypothesis:
    """系统稳态假设"""

    def __init__(self):
        self._hypotheses: dict[str, dict] = {}
        self._lock = threading.Lock()

    def add(self, name: str, metric: str, operator: str,
            threshold: float) -> None:
        with self._lock:
            self._hypotheses[name] = {
                "metric": metric,
                "operator": operator,
                "threshold": threshold,
            }

    def validate(self, name: str, current_value: float) -> dict:
        with self._lock:
            h = self._hypotheses.get(name)
            if not h:
                return {"valid": False, "error": "假设不存在"}
        op = h["operator"]
        threshold = h["threshold"]
        if op == "<":
            valid = current_value < threshold
        elif op == "<=":
            valid = current_value <= threshold
        elif op == ">":
            valid = current_value > threshold
        elif op == ">=":
            valid = current_value >= threshold
        elif op == "==":
            valid = current_value == threshold
        else:
            valid = False
        return {"valid": valid, "metric": h["metric"],
                "current": current_value, "threshold": threshold,
                "operator": op}

    def list_all(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **v} for k, v in self._hypotheses.items()]


_steady = SteadyStateHypothesis()


# ─── P365: 容量评估器 ──────────────────────────
class CapacityAssessor:
    """容量评估器"""

    @staticmethod
    def assess(current_load: int, max_capacity: int,
               growth_rate: float = 0.1, days_ahead: int = 30) -> dict:
        if max_capacity <= 0:
            return {"status": "error", "error": "容量无效"}
        utilization = current_load / max_capacity
        projected_load = current_load * (1 + growth_rate) ** (days_ahead / 30)
        projected_util = projected_load / max_capacity
        days_to_full = 0
        if growth_rate > 0 and utilization < 1:
            days_to_full = math.log(max_capacity / current_load) / math.log(1 + growth_rate) * 30
        return {
            "current_load": current_load,
            "max_capacity": max_capacity,
            "utilization": round(utilization * 100, 2),
            "projected_load": round(projected_load, 0),
            "projected_utilization": round(projected_util * 100, 2),
            "days_to_full_capacity": round(days_to_full, 1),
            "status": "critical" if utilization > 0.8 else
                      "warning" if utilization > 0.6 else "healthy",
        }


_capacity = CapacityAssessor()


# ─── P366: 资源规划器 ──────────────────────────
class ResourcePlanner:
    """资源规划器"""

    RESOURCE_TYPES = ["cpu", "memory", "disk", "network", "connections"]

    @staticmethod
    def plan(current_usage: dict[str, float], expected_growth: float = 0.2,
             safety_margin: float = 0.2) -> dict:
        plan = {}
        for resource in ResourcePlanner.RESOURCE_TYPES:
            current = current_usage.get(resource, 0)
            projected = current * (1 + expected_growth)
            recommended = projected * (1 + safety_margin)
            plan[resource] = {
                "current": round(current, 2),
                "projected": round(projected, 2),
                "recommended": round(recommended, 2),
                "headroom": round(recommended - current, 2),
            }
        return plan


_planner = ResourcePlanner()


# ─── P367: 负载预测 ──────────────────────────
class LoadForecaster:
    """负载预测器"""

    @staticmethod
    def forecast(historical: list[float], periods: int = 7,
                 method: str = "moving_avg") -> dict:
        if len(historical) < 2:
            return {"status": "error", "error": "历史数据不足"}
        if method == "moving_avg":
            window = min(7, len(historical))
            avg = sum(historical[-window:]) / window
            forecast = [avg] * periods
        elif method == "linear":
            n = len(historical)
            x_mean = (n - 1) / 2
            y_mean = sum(historical) / n
            num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(historical))
            den = sum((i - x_mean) ** 2 for i in range(n))
            slope = num / den if den != 0 else 0
            intercept = y_mean - slope * x_mean
            forecast = [slope * (n + i) + intercept for i in range(periods)]
        elif method == "exponential":
            alpha = 0.3
            smoothed = historical[0]
            for h in historical[1:]:
                smoothed = alpha * h + (1 - alpha) * smoothed
            forecast = [smoothed] * periods
        else:
            return {"status": "error", "error": "未知方法"}
        return {
            "method": method,
            "historical_len": len(historical),
            "forecast": [round(f, 2) for f in forecast],
            "periods": periods,
        }


_forecaster = LoadForecaster()


# ─── P368: 自动扩缩容策略 ──────────────────────────
class AutoScaler:
    """自动扩缩容策略"""

    def __init__(self):
        self._policies: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set_policy(self, name: str, min_instances: int = 1,
                   max_instances: int = 10, scale_up_threshold: float = 70.0,
                   scale_down_threshold: float = 30.0,
                   cooldown_sec: int = 300) -> None:
        with self._lock:
            self._policies[name] = {
                "min": min_instances,
                "max": max_instances,
                "scale_up": scale_up_threshold,
                "scale_down": scale_down_threshold,
                "cooldown": cooldown_sec,
            }

    def decide(self, name: str, current_instances: int,
               current_load: float) -> dict:
        with self._lock:
            policy = self._policies.get(name)
            if not policy:
                return {"action": "none", "reason": "无策略"}
        if current_load >= policy["scale_up"] and current_instances < policy["max"]:
            return {"action": "scale_up", "new_instances": current_instances + 1,
                    "reason": f"负载{current_load}%超过阈值{policy['scale_up']}%"}
        elif current_load <= policy["scale_down"] and current_instances > policy["min"]:
            return {"action": "scale_down", "new_instances": current_instances - 1,
                    "reason": f"负载{current_load}%低于阈值{policy['scale_down']}%"}
        return {"action": "none", "reason": "负载正常"}

    def list_policies(self) -> dict:
        with self._lock:
            return dict(self._policies)


_scaler = AutoScaler()


# ─── P369: 容量告警 ──────────────────────────
class CapacityAlert:
    """容量告警"""

    def __init__(self):
        self._alerts: deque = deque(maxlen=200)
        self._thresholds: dict[str, float] = {}
        self._lock = threading.Lock()

    def set_threshold(self, metric: str, threshold: float) -> None:
        with self._lock:
            self._thresholds[metric] = threshold

    def check(self, metric: str, value: float) -> dict:
        with self._lock:
            threshold = self._thresholds.get(metric)
        if threshold is None:
            return {"alert": False, "reason": "无阈值"}
        triggered = value >= threshold
        if triggered:
            with self._lock:
                self._alerts.append({
                    "metric": metric,
                    "value": value,
                    "threshold": threshold,
                    "timestamp": datetime.now().isoformat(),
                })
        return {"alert": triggered, "metric": metric,
                "value": value, "threshold": threshold}

    def get_alerts(self, limit: int = 20) -> list[dict]:
        with self._lock:
            a = list(self._alerts)
        a.reverse()
        return a[:limit]


_capacity_alert = CapacityAlert()


# ─── P370: 混沌实验报告 ──────────────────────────
class ChaosReporter:
    """混沌实验报告生成器"""

    @staticmethod
    def generate(experiment_name: str, chaos: ChaosExperiment,
                 steady: SteadyStateHypothesis,
                 metrics: dict[str, float] | None = None) -> dict:
        exps = chaos.list_experiments()
        exp = next((e for e in exps if e["name"] == experiment_name), None)
        if not exp:
            return {"status": "error", "error": "实验不存在"}
        report = {
            "experiment": experiment_name,
            "target": exp["target"],
            "fault_type": exp["fault_type"],
            "status": exp["status"],
            "started_at": exp.get("started_at"),
            "stopped_at": exp.get("stopped_at"),
            "hypotheses": [],
            "metrics": metrics or {},
            "verdict": "unknown",
        }
        all_valid = True
        for h in steady.list_all():
            current_val = (metrics or {}).get(h["metric"], 0)
            result = steady.validate(h["name"], current_val)
            report["hypotheses"].append({
                "name": h["name"],
                "metric": h["metric"],
                "valid": result["valid"],
                "current": current_val,
                "threshold": h["threshold"],
            })
            if not result["valid"]:
                all_valid = False
        report["verdict"] = "passed" if all_valid else "failed"
        return report


_chaos_reporter = ChaosReporter()
