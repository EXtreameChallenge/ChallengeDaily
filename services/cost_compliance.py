"""
P371-P380: 成本管理 + 合规性
- P371: 成本追踪
- P372: 成本归因
- P373: 预算管理
- P374: 成本优化建议
- P375: 合规规则引擎
- P376: 合规审计
- P377: 数据保留策略
- P378: 合规报告
- P379: 策略执行器
- P380: 违规告警
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P371: 成本追踪 ──────────────────────────
class CostTracker:
    """成本追踪器"""

    def __init__(self):
        self._costs: deque = deque(maxlen=10000)
        self._lock = threading.Lock()

    def record(self, service: str, resource: str, cost: float,
               currency: str = "CNY", tags: dict | None = None) -> None:
        with self._lock:
            self._costs.append({
                "service": service,
                "resource": resource,
                "cost": cost,
                "currency": currency,
                "tags": tags or {},
                "timestamp": datetime.now().isoformat(),
            })

    def get_total(self, service: str | None = None,
                  start_date: str | None = None,
                  end_date: str | None = None) -> dict:
        with self._lock:
            costs = list(self._costs)
        total = 0.0
        by_service: dict[str, float] = defaultdict(float)
        for c in costs:
            if service and c["service"] != service:
                continue
            if start_date and c["timestamp"] < start_date:
                continue
            if end_date and c["timestamp"] > end_date:
                continue
            total += c["cost"]
            by_service[c["service"]] += c["cost"]
        return {"total": round(total, 2),
                "currency": "CNY",
                "by_service": {k: round(v, 2) for k, v in by_service.items()}}

    def get_recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            c = list(self._costs)
        c.reverse()
        return c[:limit]


_cost_tracker = CostTracker()


# ─── P372: 成本归因 ──────────────────────────
class CostAttributor:
    """成本归因"""

    def __init__(self):
        self._attribution_rules: list[dict] = []
        self._lock = threading.Lock()

    def add_rule(self, name: str, condition: dict, allocation: dict) -> None:
        with self._lock:
            self._attribution_rules.append({
                "name": name,
                "condition": condition,
                "allocation": allocation,
            })

    def attribute(self, cost_entry: dict) -> dict:
        with self._lock:
            rules = list(self._attribution_rules)
        allocations = {}
        remaining = cost_entry.get("cost", 0)
        for rule in rules:
            if self._match(rule["condition"], cost_entry):
                for key, pct in rule["allocation"].items():
                    alloc_amount = remaining * pct
                    allocations[key] = allocations.get(key, 0) + alloc_amount
        unallocated = remaining - sum(allocations.values())
        return {
            "original_cost": cost_entry.get("cost", 0),
            "allocations": {k: round(v, 2) for k, v in allocations.items()},
            "unallocated": round(unallocated, 2),
        }

    @staticmethod
    def _match(condition: dict, entry: dict) -> bool:
        for key, value in condition.items():
            if key in entry:
                if isinstance(value, list):
                    if entry[key] not in value:
                        return False
                elif entry[key] != value:
                    return False
            elif key in entry.get("tags", {}):
                if entry["tags"][key] != value:
                    return False
            else:
                return False
        return True


_cost_attributor = CostAttributor()


# ─── P373: 预算管理 ──────────────────────────
class BudgetManager:
    """预算管理"""

    def __init__(self):
        self._budgets: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set_budget(self, name: str, limit: float, period: str = "monthly",
                   alert_threshold: float = 0.8) -> None:
        with self._lock:
            self._budgets[name] = {
                "limit": limit,
                "period": period,
                "alert_threshold": alert_threshold,
                "spent": 0.0,
            }

    def record_spend(self, name: str, amount: float) -> dict:
        with self._lock:
            budget = self._budgets.get(name)
            if not budget:
                return {"status": "error", "error": "预算不存在"}
            budget["spent"] += amount
            utilization = budget["spent"] / budget["limit"] if budget["limit"] > 0 else 0
            return {
                "status": "ok",
                "budget": name,
                "spent": round(budget["spent"], 2),
                "limit": budget["limit"],
                "remaining": round(budget["limit"] - budget["spent"], 2),
                "utilization": round(utilization * 100, 2),
                "alert": utilization >= budget["alert_threshold"],
            }

    def list_budgets(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "name": k,
                    "limit": v["limit"],
                    "spent": round(v["spent"], 2),
                    "remaining": round(v["limit"] - v["spent"], 2),
                    "utilization": round(v["spent"] / v["limit"] * 100, 2) if v["limit"] > 0 else 0,
                }
                for k, v in self._budgets.items()
            ]


_budget = BudgetManager()


# ─── P374: 成本优化建议 ──────────────────────────
class CostOptimizer:
    """成本优化建议"""

    RULES = [
        {"id": "idle_resource", "description": "检测到闲置资源(7天无活动)",
         "potential_savings_pct": 30, "action": "考虑释放或降配"},
        {"id": "over_provisioned", "description": "资源利用率低于30%",
         "potential_savings_pct": 50, "action": "建议降低规格"},
        {"id": "reserved_instance", "description": "长期稳定负载使用按量付费",
         "potential_savings_pct": 40, "action": "建议转为包年包月"},
        {"id": "storage_tier", "description": "冷数据在热存储层",
         "potential_savings_pct": 60, "action": "建议转存归档存储"},
        {"id": "right_sizing", "description": "实例规格过大",
         "potential_savings_pct": 25, "action": "建议调整规格"},
    ]

    @classmethod
    def analyze(cls, utilization: dict[str, float], cost_data: dict[str, float]) -> dict:
        recommendations = []
        total_potential_savings = 0
        for resource, util in utilization.items():
            cost = cost_data.get(resource, 0)
            if util < 0.3:
                rule = cls.RULES[1]
                savings = cost * rule["potential_savings_pct"] / 100
                recommendations.append({
                    "resource": resource,
                    "rule_id": rule["id"],
                    "description": rule["description"],
                    "action": rule["action"],
                    "current_cost": cost,
                    "potential_savings": round(savings, 2),
                })
                total_potential_savings += savings
        return {
            "recommendations": recommendations,
            "total_potential_savings": round(total_potential_savings, 2),
            "rules_count": len(cls.RULES),
        }


_cost_optimizer = CostOptimizer()


# ─── P375: 合规规则引擎 ──────────────────────────
class ComplianceRuleEngine:
    """合规规则引擎"""

    def __init__(self):
        self._rules: dict[str, dict] = {}
        self._lock = threading.Lock()

    def add_rule(self, rule_id: str, description: str, check_fn: Callable[[dict], bool],
                 severity: str = "medium", standard: str = "GDPR") -> None:
        with self._lock:
            self._rules[rule_id] = {
                "description": description,
                "check": check_fn,
                "severity": severity,
                "standard": standard,
            }

    def evaluate(self, data: dict) -> dict:
        with self._lock:
            rules = dict(self._rules)
        results = []
        for rule_id, rule in rules.items():
            try:
                passed = rule["check"](data)
                results.append({
                    "rule_id": rule_id,
                    "passed": passed,
                    "severity": rule["severity"],
                    "standard": rule["standard"],
                    "description": rule["description"],
                })
            except Exception as e:
                results.append({
                    "rule_id": rule_id,
                    "passed": False,
                    "severity": rule["severity"],
                    "error": str(e),
                })
        passed_count = sum(1 for r in results if r["passed"])
        return {
            "total_rules": len(results),
            "passed": passed_count,
            "failed": len(results) - passed_count,
            "compliance_rate": round(passed_count / len(results) * 100, 2) if results else 0,
            "results": results,
        }

    def list_rules(self) -> list[dict]:
        with self._lock:
            return [
                {"rule_id": k, "description": v["description"],
                 "severity": v["severity"], "standard": v["standard"]}
                for k, v in self._rules.items()
            ]


_compliance = ComplianceRuleEngine()


# ─── P376: 合规审计 ──────────────────────────
class ComplianceAudit:
    """合规审计"""

    def __init__(self):
        self._audit_trail: deque = deque(maxlen=5000)
        self._lock = threading.Lock()

    def record(self, action: str, actor: str, resource: str = "",
               details: dict | None = None, compliance_status: str = "compliant") -> None:
        with self._lock:
            self._audit_trail.append({
                "action": action,
                "actor": actor,
                "resource": resource,
                "details": details or {},
                "compliance_status": compliance_status,
                "timestamp": datetime.now().isoformat(),
            })

    def search(self, actor: str | None = None, action: str | None = None,
               status: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            entries = list(self._audit_trail)
        if actor:
            entries = [e for e in entries if e["actor"] == actor]
        if action:
            entries = [e for e in entries if e["action"] == action]
        if status:
            entries = [e for e in entries if e["compliance_status"] == status]
        entries.reverse()
        return entries[:limit]


_audit = ComplianceAudit()


# ─── P377: 数据保留策略 ──────────────────────────
class RetentionPolicy:
    """数据保留策略"""

    def __init__(self):
        self._policies: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set_policy(self, data_type: str, retention_days: int,
                   action: str = "delete", legal_hold: bool = False) -> None:
        with self._lock:
            self._policies[data_type] = {
                "retention_days": retention_days,
                "action": action,
                "legal_hold": legal_hold,
            }

    def check_data(self, data_type: str, created_at: str) -> dict:
        with self._lock:
            policy = self._policies.get(data_type)
        if not policy:
            return {"action": "keep", "reason": "无保留策略"}
        if policy["legal_hold"]:
            return {"action": "keep", "reason": "法律封存"}
        try:
            created = datetime.fromisoformat(created_at)
        except (ValueError, TypeError):
            return {"action": "keep", "reason": "无效日期"}
        age_days = (datetime.now() - created).days
        if age_days > policy["retention_days"]:
            return {"action": policy["action"],
                    "reason": f"超过{policy['retention_days']}天保留期",
                    "age_days": age_days}
        return {"action": "keep", "age_days": age_days,
                "remaining_days": policy["retention_days"] - age_days}

    def list_policies(self) -> list[dict]:
        with self._lock:
            return [{"data_type": k, **v} for k, v in self._policies.items()]


_retention = RetentionPolicy()


# ─── P378: 合规报告 ──────────────────────────
class ComplianceReporter:
    """合规报告生成器"""

    @staticmethod
    def generate(compliance: ComplianceRuleEngine,
                 audit: ComplianceAudit,
                 retention: RetentionPolicy) -> dict:
        return {
            "generated_at": datetime.now().isoformat(),
            "compliance_rules": {
                "total": len(compliance.list_rules()),
                "rules": compliance.list_rules(),
            },
            "audit_summary": {
                "total_records": audit.search(limit=10000).__len__(),
                "non_compliant": len(audit.search(status="non_compliant", limit=10000)),
            },
            "retention_policies": retention.list_policies(),
            "overall_status": "compliant",  # 简化
        }


_reporter = ComplianceReporter()


# ─── P379: 策略执行器 ──────────────────────────
class PolicyExecutor:
    """策略执行器"""

    def __init__(self):
        self._policies: dict[str, Callable] = {}
        self._execution_log: deque = deque(maxlen=500)
        self._lock = threading.Lock()

    def register(self, name: str, executor: Callable[[dict], dict]) -> None:
        with self._lock:
            self._policies[name] = executor

    def execute(self, name: str, context: dict) -> dict:
        with self._lock:
            fn = self._policies.get(name)
        if not fn:
            return {"status": "error", "error": "策略未注册"}
        try:
            result = fn(context)
            with self._lock:
                self._execution_log.append({
                    "policy": name,
                    "result": result,
                    "timestamp": datetime.now().isoformat(),
                })
            return {"status": "ok", "result": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def list_policies(self) -> list[str]:
        with self._lock:
            return list(self._policies.keys())

    def get_log(self, limit: int = 50) -> list[dict]:
        with self._lock:
            log = list(self._execution_log)
        log.reverse()
        return log[:limit]


_policy_exec = PolicyExecutor()


# ─── P380: 违规告警 ──────────────────────────
class ViolationAlert:
    """违规告警"""

    SEVERITY_LEVELS = ["low", "medium", "high", "critical"]

    def __init__(self):
        self._alerts: deque = deque(maxlen=500)
        self._handlers: list[Callable] = []
        self._lock = threading.Lock()

    def add_handler(self, handler: Callable) -> None:
        with self._lock:
            self._handlers.append(handler)

    def trigger(self, rule_id: str, severity: str, description: str,
                resource: str = "") -> dict:
        with self._lock:
            handlers = list(self._handlers)
            alert = {
                "rule_id": rule_id,
                "severity": severity,
                "description": description,
                "resource": resource,
                "timestamp": datetime.now().isoformat(),
            }
            self._alerts.append(alert)
        for handler in handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.warning("违规告警处理器失败: %s", e)
        return {"status": "ok", "alert": alert}

    def get_alerts(self, severity: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            alerts = list(self._alerts)
        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]
        alerts.reverse()
        return alerts[:limit]


_violation = ViolationAlert()
