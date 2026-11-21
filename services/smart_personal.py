"""
P141-P149: 智能化与个性化
- P141: 用户画像构建
- P142: 行为模式识别
- P143: 智能推荐引擎
- P144: 自适应学习曲线
- P145: 个性化提醒
- P146: 工作风格分析
- P147: 效率预测模型
- P148: 上下文感知
- P149: 多目标优化建议
"""
import logging
import threading
import time
import math
from datetime import datetime, timedelta
from collections import defaultdict, deque
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P141: 用户画像 ──────────────────────────
class UserProfile:
    """动态用户画像"""

    def __init__(self):
        self._traits: dict[str, Any] = defaultdict(float)
        self._preferences: dict[str, Any] = {}
        self._history: deque = deque(maxlen=1000)
        self._lock = threading.Lock()

    def update_trait(self, name: str, value: float, weight: float = 0.1) -> None:
        """加权更新特质(EMA)"""
        with self._lock:
            old = self._traits[name]
            self._traits[name] = old * (1 - weight) + value * weight

    def set_preference(self, key: str, value: Any) -> None:
        with self._lock:
            self._preferences[key] = value

    def get_trait(self, name: str) -> float:
        return self._traits.get(name, 0.0)

    def get_preference(self, key: str, default=None):
        return self._preferences.get(key, default)

    def record_event(self, event_type: str, data: dict | None = None) -> None:
        with self._lock:
            self._history.append({
                "type": event_type,
                "data": data or {},
                "timestamp": datetime.now().isoformat()
            })

    def get_profile(self) -> dict:
        with self._lock:
            return {
                "traits": dict(self._traits),
                "preferences": dict(self._preferences),
                "event_count": len(self._history)
            }


_user_profile = UserProfile()


def get_user_profile() -> UserProfile:
    return _user_profile


# ─── P142: 行为模式识别 ──────────────────────────
class BehaviorPatternMiner:
    """挖掘周期性行为模式"""

    def __init__(self):
        self._sequences: list[list[str]] = []

    def add_sequence(self, sequence: list[str]) -> None:
        self._sequences.append(sequence)
        if len(self._sequences) > 1000:
            self._sequences = self._sequences[-500:]

    def find_frequent_patterns(self, min_support: float = 0.1) -> list:
        """发现频繁模式(简化版 GSP)"""
        if not self._sequences:
            return []
        total = len(self._sequences)
        # 单项频率
        item_count: dict[str, int] = defaultdict(int)
        for seq in self._sequences:
            for item in set(seq):
                item_count[item] += 1
        frequent = [
            {"pattern": [item], "support": round(c / total, 3)}
            for item, c in item_count.items()
            if c / total >= min_support
        ]
        frequent.sort(key=lambda x: x["support"], reverse=True)
        return frequent[:20]


_behavior_miner = BehaviorPatternMiner()


# ─── P143: 智能推荐引擎 ──────────────────────────
class RecommendationEngine:
    """多策略推荐引擎"""

    def __init__(self):
        self._rules: list[dict] = []
        self._feedback: dict[str, int] = defaultdict(int)

    def add_rule(self, name: str, condition: Callable, action: str,
                 priority: int = 5) -> None:
        self._rules.append({
            "name": name, "condition": condition,
            "action": action, "priority": priority
        })

    def recommend(self, context: dict) -> list:
        results = []
        for rule in self._rules:
            try:
                if rule["condition"](context):
                    results.append({
                        "rule": rule["name"],
                        "action": rule["action"],
                        "priority": rule["priority"],
                        "feedback_score": self._feedback.get(rule["name"], 0)
                    })
            except Exception:
                continue
        results.sort(key=lambda x: (x["priority"], x["feedback_score"]), reverse=True)
        return results[:10]

    def feedback(self, rule_name: str, positive: bool) -> None:
        self._feedback[rule_name] += 1 if positive else -1


_rec_engine = RecommendationEngine()


def _init_default_rules():
    _rec_engine.add_rule(
        "morning_deep_work",
        lambda ctx: 9 <= datetime.now().hour < 11,
        "建议进行深度工作（开发/设计）",
        priority=8
    )
    _rec_engine.add_rule(
        "afternoon_break",
        lambda ctx: 14 <= datetime.now().hour < 16,
        "下午易犯困，建议短暂休息或站会",
        priority=6
    )
    _rec_engine.add_rule(
        "low_focus",
        lambda ctx: ctx.get("focus_score", 1) < 0.4,
        "专注度低，建议番茄钟",
        priority=9
    )


_init_default_rules()


# ─── P144: 自适应学习曲线 ──────────────────────────
class LearningCurve:
    """追踪技能学习曲线"""

    def __init__(self):
        self._skills: dict[str, list[dict]] = defaultdict(list)

    def record(self, skill: str, level: float, timestamp: datetime | None = None) -> None:
        ts = timestamp or datetime.now()
        self._skills[skill].append({"level": level, "timestamp": ts.isoformat()})

    def get_curve(self, skill: str) -> list:
        return self._skills.get(skill, [])

    def predict_next(self, skill: str) -> float | None:
        """简单线性预测"""
        data = self._skills.get(skill, [])
        if len(data) < 2:
            return None
        # 最小二乘法
        n = len(data)
        xs = list(range(n))
        ys = [d["level"] for d in data]
        mean_x = sum(xs) / n
        mean_y = sum(ys) / n
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        den = sum((x - mean_x) ** 2 for x in xs)
        if den == 0:
            return mean_y
        slope = num / den
        intercept = mean_y - slope * mean_x
        return max(0.0, min(1.0, slope * n + intercept))


_learning_curve = LearningCurve()


# ─── P145: 个性化提醒 ──────────────────────────
class PersonalizedReminder:
    """基于用户习惯的智能提醒"""

    def __init__(self):
        self._reminders: list[dict] = []
        self._sent: deque = deque(maxlen=200)

    def schedule(self, reminder_type: str, message: str,
                 trigger_time: datetime | None = None,
                 condition: Callable | None = None) -> str:
        rid = f"rem_{int(time.time() * 1000)}_{len(self._reminders)}"
        self._reminders.append({
            "id": rid,
            "type": reminder_type,
            "message": message,
            "trigger_time": trigger_time.isoformat() if trigger_time else None,
            "condition": condition,
            "sent": False
        })
        return rid

    def check(self) -> list:
        """检查并发送到期提醒"""
        due = []
        now = datetime.now()
        for r in self._reminders:
            if r["sent"]:
                continue
            should_send = False
            if r["trigger_time"]:
                try:
                    t = datetime.fromisoformat(r["trigger_time"])
                    if now >= t:
                        should_send = True
                except Exception:
                    pass
            if r["condition"]:
                try:
                    should_send = r["condition"]()
                except Exception:
                    pass
            if should_send:
                r["sent"] = True
                due.append({"id": r["id"], "type": r["type"], "message": r["message"]})
                self._sent.append({"id": r["id"], "sent_at": now.isoformat()})
        return due

    def pending(self) -> list:
        return [r for r in self._reminders if not r["sent"]]


_reminder = PersonalizedReminder()


# ─── P146: 工作风格分析 ──────────────────────────
def analyze_work_style(recent_activities: list[dict]) -> dict:
    """分析用户工作风格"""
    if not recent_activities:
        return {"style": "unknown", "confidence": 0}

    # 按小时分布
    hour_dist = defaultdict(int)
    for a in recent_activities:
        try:
            ts = a.get("timestamp") or a.get("start_time")
            if ts:
                h = datetime.fromisoformat(str(ts)).hour
                hour_dist[h] += 1
        except Exception:
            continue

    if not hour_dist:
        return {"style": "unknown", "confidence": 0}

    # 早晨/下午/夜晚分布
    morning = sum(v for h, v in hour_dist.items() if 6 <= h < 12)
    afternoon = sum(v for h, v in hour_dist.items() if 12 <= h < 18)
    evening = sum(v for h, v in hour_dist.items() if 18 <= h < 24)
    night = sum(v for h, v in hour_dist.items() if 0 <= h < 6)
    total = morning + afternoon + evening + night

    if total == 0:
        return {"style": "unknown", "confidence": 0}

    morning_pct = morning / total
    afternoon_pct = afternoon / total
    evening_pct = evening / total
    night_pct = night / total

    if morning_pct > 0.4:
        style = "early_bird"
        confidence = round(morning_pct, 2)
    elif night_pct > 0.3:
        style = "night_owl"
        confidence = round(night_pct, 2)
    elif evening_pct > 0.4:
        style = "evening_person"
        confidence = round(evening_pct, 2)
    else:
        style = "balanced"
        confidence = round(afternoon_pct, 2)

    return {
        "style": style,
        "confidence": confidence,
        "distribution": {
            "morning": round(morning_pct, 3),
            "afternoon": round(afternoon_pct, 3),
            "evening": round(evening_pct, 3),
            "night": round(night_pct, 3)
        },
        "peak_hour": max(hour_dist.items(), key=lambda x: x[1])[0]
    }


# ─── P147: 效率预测 ──────────────────────────
def predict_efficiency(history: list[dict], target_date: datetime | None = None) -> dict:
    """预测未来效率(基于历史移动平均)"""
    if not history:
        return {"predicted": 0.5, "confidence": 0, "method": "default"}

    values = [h.get("efficiency", 0.5) for h in history[-30:]]
    if not values:
        return {"predicted": 0.5, "confidence": 0, "method": "default"}

    # 7日加权移动平均
    window = min(7, len(values))
    recent = values[-window:]
    weights = [i + 1 for i in range(window)]
    weighted_sum = sum(v * w for v, w in zip(recent, weights))
    predicted = weighted_sum / sum(weights)

    # 置信度基于数据量
    confidence = min(1.0, len(values) / 30)

    return {
        "predicted": round(predicted, 3),
        "confidence": round(confidence, 3),
        "method": "weighted_moving_average",
        "window": window
    }


# ─── P148: 上下文感知 ──────────────────────────
class ContextAwareness:
    """上下文感知系统"""

    def __init__(self):
        self._context: dict[str, Any] = {}
        self._listeners: list[Callable] = []

    def update(self, key: str, value: Any) -> None:
        old = self._context.get(key)
        self._context[key] = value
        if old != value:
            for listener in self._listeners:
                try:
                    listener(key, old, value)
                except Exception as e:
                    logger.debug(f"上下文监听器失败: {e}")

    def get(self, key: str, default=None):
        return self._context.get(key, default)

    def snapshot(self) -> dict:
        return dict(self._context)

    def on_change(self, listener: Callable) -> None:
        self._listeners.append(listener)


_context = ContextAwareness()


# ─── P149: 多目标优化建议 ──────────────────────────
def multi_objective_optimize(metrics: dict) -> list:
    """基于多目标生成优化建议"""
    suggestions = []

    # 目标1: 效率
    eff = metrics.get("efficiency", 0.5)
    if eff < 0.5:
        suggestions.append({
            "objective": "efficiency",
            "priority": "high",
            "suggestion": "尝试番茄钟工作法，减少任务切换",
            "expected_gain": "15-25%"
        })

    # 目标2: 专注度
    focus = metrics.get("focus_depth", 0.5)
    if focus < 0.4:
        suggestions.append({
            "objective": "focus",
            "priority": "high",
            "suggestion": "关闭通知，安排深度工作时段",
            "expected_gain": "20-30%"
        })

    # 目标3: 工作生活平衡
    overtime = metrics.get("overtime_hours", 0)
    if overtime > 10:
        suggestions.append({
            "objective": "balance",
            "priority": "medium",
            "suggestion": "减少加班，保证 7 小时睡眠",
            "expected_gain": "健康改善"
        })

    # 目标4: 学习成长
    learning = metrics.get("learning_hours", 0)
    if learning < 5:
        suggestions.append({
            "objective": "growth",
            "priority": "medium",
            "suggestion": "每天安排 1 小时学习时间",
            "expected_gain": "技能提升"
        })

    # 目标5: 多样性
    diversity = metrics.get("category_diversity", 0.5)
    if diversity < 0.4:
        suggestions.append({
            "objective": "variety",
            "priority": "low",
            "suggestion": "尝试不同类型的工作，避免单调",
            "expected_gain": "创造力提升"
        })

    return suggestions
