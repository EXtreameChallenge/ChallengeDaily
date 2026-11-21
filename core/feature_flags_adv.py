"""
P351-P360: 功能开关 + 灰度发布
- P351: 功能开关管理
- P352: 开关状态评估器
- P353: 用户分组定向
- P354: 灰度发布(百分比)
- P355: 开关依赖关系
- P356: 开关变更审计
- P357: 开关历史时间线
- P358: 紧急开关(秒级回滚)
- P359: 开关模板预设
- P360: 开关同步广播
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P351: 功能开关管理 ──────────────────────────
class FeatureFlag:
    """功能开关"""

    def __init__(self, name: str, enabled: bool = False,
                 description: str = "", owner: str = ""):
        self.name = name
        self.enabled = enabled
        self.description = description
        self.owner = owner
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.rules: list[dict] = []  # 定向规则
        self.percentage: float = 0.0  # 灰度百分比


class FeatureFlagManager:
    """功能开关管理器"""

    def __init__(self):
        self._flags: dict[str, FeatureFlag] = {}
        self._lock = threading.Lock()

    def create(self, name: str, enabled: bool = False, description: str = "",
               owner: str = "") -> dict:
        with self._lock:
            if name in self._flags:
                return {"status": "error", "error": "开关已存在"}
            self._flags[name] = FeatureFlag(name, enabled, description, owner)
            return {"status": "ok", "flag": name}

    def toggle(self, name: str, enabled: bool) -> dict:
        with self._lock:
            flag = self._flags.get(name)
            if not flag:
                return {"status": "error", "error": "开关不存在"}
            flag.enabled = enabled
            flag.updated_at = datetime.now().isoformat()
            return {"status": "ok", "flag": name, "enabled": enabled}

    def get(self, name: str) -> dict | None:
        with self._lock:
            flag = self._flags.get(name)
            if not flag:
                return None
            return {
                "name": flag.name,
                "enabled": flag.enabled,
                "description": flag.description,
                "owner": flag.owner,
                "percentage": flag.percentage,
                "rules": flag.rules,
                "created_at": flag.created_at,
                "updated_at": flag.updated_at,
            }

    def list_all(self) -> list[dict]:
        with self._lock:
            return [self.get(name) for name in self._flags]

    def delete(self, name: str) -> bool:
        with self._lock:
            return self._flags.pop(name, None) is not None

    def set_percentage(self, name: str, percentage: float) -> dict:
        with self._lock:
            flag = self._flags.get(name)
            if not flag:
                return {"status": "error", "error": "开关不存在"}
            flag.percentage = max(0.0, min(100.0, percentage))
            flag.updated_at = datetime.now().isoformat()
            return {"status": "ok", "percentage": flag.percentage}

    def add_rule(self, name: str, rule: dict) -> dict:
        with self._lock:
            flag = self._flags.get(name)
            if not flag:
                return {"status": "error", "error": "开关不存在"}
            flag.rules.append(rule)
            flag.updated_at = datetime.now().isoformat()
            return {"status": "ok", "rule_count": len(flag.rules)}


_flag_mgr = FeatureFlagManager()


# ─── P352: 开关状态评估器 ──────────────────────────
class FlagEvaluator:
    """开关状态评估器(综合多个因素)"""

    def __init__(self, flag_mgr: FeatureFlagManager):
        self._mgr = flag_mgr

    def evaluate(self, name: str, user_id: str = "",
                 user_attributes: dict | None = None) -> dict:
        flag = self._mgr.get(name)
        if not flag:
            return {"enabled": False, "reason": "not_found"}
        if not flag["enabled"]:
            return {"enabled": False, "reason": "globally_disabled"}
        # 检查规则
        for rule in flag["rules"]:
            if self._match_rule(rule, user_id, user_attributes or {}):
                return {"enabled": True, "reason": "rule_match", "rule": rule}
        # 检查灰度
        if flag["percentage"] > 0:
            if self._user_in_percentage(name, user_id, flag["percentage"]):
                return {"enabled": True, "reason": "percentage"}
            return {"enabled": False, "reason": "not_in_percentage"}
        # 完全开启
        if flag["percentage"] == 0 and not flag["rules"]:
            return {"enabled": True, "reason": "fully_enabled"}
        return {"enabled": False, "reason": "no_match"}

    @staticmethod
    def _match_rule(rule: dict, user_id: str, attrs: dict) -> bool:
        rule_type = rule.get("type", "")
        if rule_type == "user_list":
            return user_id in rule.get("users", [])
        elif rule_type == "attribute":
            key = rule.get("key", "")
            value = rule.get("value")
            return attrs.get(key) == value
        elif rule_type == "attribute_in":
            key = rule.get("key", "")
            return attrs.get(key) in rule.get("values", [])
        return False

    @staticmethod
    def _user_in_percentage(name: str, user_id: str, percentage: float) -> bool:
        hash_val = int(hashlib.md5(f"{name}:{user_id}".encode()).hexdigest(), 16) % 10000
        return hash_val < percentage * 100


_evaluator = FlagEvaluator(_flag_mgr)


# ─── P353: 用户分组定向 ──────────────────────────
class UserTargeting:
    """用户分组定向"""

    def __init__(self):
        self._segments: dict[str, dict] = {}
        self._user_segments: dict[str, set[str]] = {}
        self._lock = threading.Lock()

    def create_segment(self, name: str, criteria: dict) -> None:
        with self._lock:
            self._segments[name] = criteria

    def assign_user(self, user_id: str, segment: str) -> None:
        with self._lock:
            if user_id not in self._user_segments:
                self._user_segments[user_id] = set()
            self._user_segments[user_id].add(segment)

    def get_user_segments(self, user_id: str) -> list[str]:
        with self._lock:
            return list(self._user_segments.get(user_id, set()))

    def match_user(self, user_id: str, user_attrs: dict) -> list[str]:
        with self._lock:
            matches = []
            for name, criteria in self._segments.items():
                if self._match_criteria(criteria, user_attrs):
                    matches.append(name)
            return matches

    @staticmethod
    def _match_criteria(criteria: dict, attrs: dict) -> bool:
        for key, value in criteria.items():
            if key not in attrs or attrs[key] != value:
                return False
        return True

    def list_segments(self) -> dict:
        with self._lock:
            return dict(self._segments)


_targeting = UserTargeting()


# ─── P354: 灰度发布 ──────────────────────────
class GradualRollout:
    """灰度发布(百分比逐步提升)"""

    def __init__(self, flag_mgr: FeatureFlagManager):
        self._mgr = flag_mgr
        self._rollout_plans: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create_plan(self, flag_name: str, stages: list[dict]) -> dict:
        """stages: [{"percentage": 10, "duration_hours": 24}, ...]"""
        with self._lock:
            self._rollout_plans[flag_name] = {
                "stages": stages,
                "current_stage": 0,
                "started_at": datetime.now().isoformat(),
            }
        self._mgr.set_percentage(flag_name, stages[0]["percentage"] if stages else 0)
        return {"status": "ok", "flag": flag_name, "stages": len(stages)}

    def advance(self, flag_name: str) -> dict:
        with self._lock:
            plan = self._rollout_plans.get(flag_name)
            if not plan:
                return {"status": "error", "error": "无灰度计划"}
            plan["current_stage"] = min(plan["current_stage"] + 1, len(plan["stages"]) - 1)
            stage = plan["stages"][plan["current_stage"]]
        self._mgr.set_percentage(flag_name, stage["percentage"])
        return {"status": "ok", "current_stage": plan["current_stage"],
                "percentage": stage["percentage"]}

    def get_plan(self, flag_name: str) -> dict | None:
        with self._lock:
            plan = self._rollout_plans.get(flag_name)
            if not plan:
                return None
            current = plan["stages"][plan["current_stage"]]
            return {
                "current_stage": plan["current_stage"],
                "total_stages": len(plan["stages"]),
                "current_percentage": current["percentage"],
                "started_at": plan["started_at"],
            }


_rollout = GradualRollout(_flag_mgr)


# ─── P355: 开关依赖关系 ──────────────────────────
class FlagDependency:
    """开关依赖关系"""

    def __init__(self):
        self._dependencies: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def add(self, flag: str, depends_on: str) -> dict:
        with self._lock:
            if flag not in self._dependencies:
                self._dependencies[flag] = []
            if depends_on not in self._dependencies[flag]:
                self._dependencies[flag].append(depends_on)
            return {"status": "ok"}

    def get_dependencies(self, flag: str) -> list[str]:
        with self._lock:
            return list(self._dependencies.get(flag, []))

    def check(self, flag: str, flag_states: dict[str, bool]) -> dict:
        deps = self.get_dependencies(flag)
        all_met = all(flag_states.get(d, False) for d in deps)
        return {
            "flag": flag,
            "dependencies": deps,
            "all_met": all_met,
            "unmet": [d for d in deps if not flag_states.get(d, False)],
        }


_dependency = FlagDependency()


# ─── P356: 开关变更审计 ──────────────────────────
class FlagAuditLog:
    """开关变更审计日志"""

    def __init__(self):
        self._logs: deque = deque(maxlen=1000)
        self._lock = threading.Lock()

    def log(self, flag: str, action: str, actor: str,
            old_value: Any = None, new_value: Any = None) -> None:
        with self._lock:
            self._logs.append({
                "flag": flag,
                "action": action,
                "actor": actor,
                "old_value": old_value,
                "new_value": new_value,
                "timestamp": datetime.now().isoformat(),
            })

    def get_logs(self, flag: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            logs = list(self._logs)
        if flag:
            logs = [l for l in logs if l["flag"] == flag]
        logs.reverse()
        return logs[:limit]


_audit = FlagAuditLog()


# ─── P357: 开关历史时间线 ──────────────────────────
class FlagTimeline:
    """开关历史时间线"""

    def __init__(self):
        self._timelines: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._lock = threading.Lock()

    def record(self, flag: str, event: str, details: dict | None = None) -> None:
        with self._lock:
            self._timelines[flag].append({
                "event": event,
                "details": details or {},
                "timestamp": datetime.now().isoformat(),
            })

    def get_timeline(self, flag: str) -> list[dict]:
        with self._lock:
            return list(self._timelines.get(flag, deque()))


_timeline = FlagTimeline()


# ─── P358: 紧急开关 ──────────────────────────
class KillSwitch:
    """紧急开关(秒级回滚)"""

    def __init__(self, flag_mgr: FeatureFlagManager, audit: FlagAuditLog):
        self._mgr = flag_mgr
        self._audit = audit
        self._kill_switches: set[str] = set()
        self._lock = threading.Lock()

    def register(self, name: str) -> None:
        with self._lock:
            self._kill_switches.add(name)

    def activate(self, name: str, actor: str = "system") -> dict:
        result = self._mgr.toggle(name, False)
        self._audit.log(name, "kill_switch_activated", actor)
        return result

    def activate_all(self, actor: str = "system") -> dict:
        with self._lock:
            switches = list(self._kill_switches)
        results = {}
        for s in switches:
            results[s] = self.activate(s, actor)
        return {"status": "ok", "count": len(switches), "results": results}

    def list_kill_switches(self) -> list[str]:
        with self._lock:
            return list(self._kill_switches)


_kill = KillSwitch(_flag_mgr, _audit)


# ─── P359: 开关模板 ──────────────────────────
class FlagTemplate:
    """开关模板预设"""

    TEMPLATES = {
        "new_feature": {
            "enabled": False,
            "percentage": 0,
            "description": "新功能开关",
            "rules": [],
        },
        "beta_test": {
            "enabled": True,
            "percentage": 10,
            "description": "Beta测试开关",
            "rules": [{"type": "attribute", "key": "beta_tester", "value": True}],
        },
        "ab_test": {
            "enabled": True,
            "percentage": 50,
            "description": "A/B测试开关",
            "rules": [],
        },
        "admin_only": {
            "enabled": True,
            "percentage": 0,
            "description": "仅管理员可见",
            "rules": [{"type": "attribute", "key": "role", "value": "admin"}],
        },
        "maintenance": {
            "enabled": False,
            "percentage": 0,
            "description": "维护模式开关",
            "rules": [],
        },
    }

    @classmethod
    def get_template(cls, name: str) -> dict | None:
        return cls.TEMPLATES.get(name)

    @classmethod
    def list_templates(cls) -> dict:
        return {k: v["description"] for k, v in cls.TEMPLATES.items()}

    @classmethod
    def create_from_template(cls, mgr: FeatureFlagManager, flag_name: str,
                             template_name: str) -> dict:
        template = cls.TEMPLATES.get(template_name)
        if not template:
            return {"status": "error", "error": "模板不存在"}
        result = mgr.create(flag_name, template["enabled"], template["description"])
        if result["status"] == "ok":
            mgr.set_percentage(flag_name, template["percentage"])
            for rule in template["rules"]:
                mgr.add_rule(flag_name, rule)
        return result


# ─── P360: 开关同步广播 ──────────────────────────
class FlagBroadcaster:
    """开关变更同步广播"""

    def __init__(self):
        self._listeners: list[Callable[[str, dict], None]] = []
        self._broadcast_log: deque = deque(maxlen=200)
        self._lock = threading.Lock()

    def subscribe(self, listener: Callable[[str, dict], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def broadcast(self, event: str, data: dict) -> None:
        with self._lock:
            listeners = list(self._listeners)
            self._broadcast_log.append({
                "event": event,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            })
        for listener in listeners:
            try:
                listener(event, data)
            except Exception as e:
                logger.warning("广播监听器失败: %s", e)

    def get_broadcast_log(self, limit: int = 50) -> list[dict]:
        with self._lock:
            log = list(self._broadcast_log)
        log.reverse()
        return log[:limit]


_broadcaster = FlagBroadcaster()

