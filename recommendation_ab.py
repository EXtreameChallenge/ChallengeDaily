"""
P341-P350: 推荐系统 + A/B测试
- P341: 协同过滤推荐
- P342: 内容推荐(基于标签)
- P343: 混合推荐器
- P344: 推荐反馈循环
- P345: A/B测试框架
- P346: 实验分组器
- P347: 统计显著性检验
- P348: 指标追踪
- P349: 多变量测试(MVT)
- P350: 实验报告生成
"""
from __future__ import annotations

import logging
import math
import random
import threading
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P341: 协同过滤 ──────────────────────────
class CollaborativeFilter:
    """协同过滤推荐器"""

    def __init__(self):
        self._user_items: dict[str, set[str]] = defaultdict(set)
        self._item_users: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.Lock()

    def add_interaction(self, user_id: str, item_id: str) -> None:
        with self._lock:
            self._user_items[user_id].add(item_id)
            self._item_users[item_id].add(user_id)

    def recommend(self, user_id: str, top_k: int = 10) -> list[dict]:
        with self._lock:
            user_items = set(self._user_items.get(user_id, set()))
            if not user_items:
                # 冷启动:返回最热门项
                popular = sorted(
                    self._item_users.items(),
                    key=lambda x: len(x[1]),
                    reverse=True
                )[:top_k]
                return [{"item_id": item, "score": len(users), "reason": "popular"}
                        for item, users in popular]
            # 找相似用户(基于Jaccard)
            similar_users = []
            for item in user_items:
                for other_user in self._item_users.get(item, set()):
                    if other_user != user_id:
                        similar_users.append(other_user)
            # 推荐项
            item_scores = Counter()
            for other_user in similar_users:
                other_items = self._user_items.get(other_user, set())
                for item in other_items:
                    if item not in user_items:
                        item_scores[item] += 1
        results = [{"item_id": item, "score": score, "reason": "collaborative"}
                   for item, score in item_scores.most_common(top_k)]
        return results


_collab_filter = CollaborativeFilter()


# ─── P342: 内容推荐 ──────────────────────────
class ContentRecommender:
    """基于标签的内容推荐"""

    def __init__(self):
        self._items: dict[str, dict] = {}
        self._user_prefs: dict[str, Counter] = defaultdict(Counter)
        self._lock = threading.Lock()

    def add_item(self, item_id: str, tags: list[str], metadata: dict | None = None) -> None:
        with self._lock:
            self._items[item_id] = {
                "tags": tags,
                "metadata": metadata or {},
            }

    def record_preference(self, user_id: str, item_id: str, weight: float = 1.0) -> None:
        with self._lock:
            item = self._items.get(item_id)
            if item:
                for tag in item["tags"]:
                    self._user_prefs[user_id][tag] += weight

    def recommend(self, user_id: str, top_k: int = 10) -> list[dict]:
        with self._lock:
            prefs = self._user_prefs.get(user_id, Counter())
            if not prefs:
                # 冷启动
                items = list(self._items.items())[:top_k]
                return [{"item_id": iid, "score": 0, "reason": "cold_start"}
                        for iid, _ in items]
            scored = []
            for item_id, item in self._items.items():
                score = sum(prefs.get(tag, 0) for tag in item["tags"])
                if score > 0:
                    scored.append({"item_id": item_id, "score": score,
                                   "reason": "content_based"})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


_content_rec = ContentRecommender()


# ─── P343: 混合推荐器 ──────────────────────────
class HybridRecommender:
    """混合推荐器(协同+内容加权)"""

    def __init__(self, collab: CollaborativeFilter, content: ContentRecommender,
                 collab_weight: float = 0.6, content_weight: float = 0.4):
        self._collab = collab
        self._content = content
        self._collab_w = collab_weight
        self._content_w = content_weight

    def recommend(self, user_id: str, top_k: int = 10) -> list[dict]:
        collab_recs = self._collab.recommend(user_id, top_k * 2)
        content_recs = self._content.recommend(user_id, top_k * 2)
        # 合并
        item_scores: dict[str, float] = {}
        for rec in collab_recs:
            item_scores[rec["item_id"]] = item_scores.get(rec["item_id"], 0) + \
                rec["score"] * self._collab_w
        for rec in content_recs:
            item_scores[rec["item_id"]] = item_scores.get(rec["item_id"], 0) + \
                rec["score"] * self._content_w
        sorted_items = sorted(item_scores.items(), key=lambda x: x[1], reverse=True)
        return [{"item_id": iid, "score": round(score, 3), "reason": "hybrid"}
                for iid, score in sorted_items[:top_k]]


_hybrid_rec = HybridRecommender(_collab_filter, _content_rec)


# ─── P344: 推荐反馈 ──────────────────────────
class FeedbackLoop:
    """推荐反馈循环"""

    def __init__(self):
        self._feedback: deque = deque(maxlen=1000)
        self._lock = threading.Lock()

    def record(self, user_id: str, item_id: str, action: str,
               rating: float | None = None) -> None:
        with self._lock:
            self._feedback.append({
                "user_id": user_id,
                "item_id": item_id,
                "action": action,  # click, like, dislike, purchase, ignore
                "rating": rating,
                "timestamp": datetime.now().isoformat(),
            })

    def get_stats(self) -> dict:
        with self._lock:
            fb = list(self._feedback)
        action_counts = Counter(f["action"] for f in fb)
        ratings = [f["rating"] for f in fb if f["rating"] is not None]
        return {
            "total_feedback": len(fb),
            "actions": dict(action_counts),
            "avg_rating": round(sum(ratings) / len(ratings), 3) if ratings else 0,
        }

    def get_user_feedback(self, user_id: str) -> list[dict]:
        with self._lock:
            return [f for f in self._feedback if f["user_id"] == user_id]


_feedback = FeedbackLoop()


# ─── P345: A/B测试框架 ──────────────────────────
class ABTest:
    """A/B测试框架"""

    def __init__(self):
        self._experiments: dict[str, dict] = {}
        self._assignments: dict[str, str] = {}  # user_id -> experiment:variant
        self._lock = threading.Lock()

    def create(self, name: str, variants: list[str],
               weights: list[float] | None = None) -> dict:
        with self._lock:
            if name in self._experiments:
                return {"status": "error", "error": "实验已存在"}
            if not variants:
                return {"status": "error", "error": "无变体"}
            if weights and len(weights) != len(variants):
                return {"status": "error", "error": "权重数量不匹配"}
            w = weights or [1.0 / len(variants)] * len(variants)
            total_w = sum(w)
            self._experiments[name] = {
                "variants": variants,
                "weights": [x / total_w for x in w],
                "created_at": datetime.now().isoformat(),
                "active": True,
            }
            return {"status": "ok", "experiment": name, "variants": variants}

    def assign(self, experiment: str, user_id: str) -> dict:
        with self._lock:
            exp = self._experiments.get(experiment)
            if not exp or not exp["active"]:
                return {"status": "error", "error": "实验不存在或未激活"}
            key = f"{experiment}:{user_id}"
            if key in self._assignments:
                return {"experiment": experiment, "user_id": user_id,
                        "variant": self._assignments[key]}
            # 基于hash分配
            random.seed(hash(key))
            r = random.random()
            cumulative = 0
            for i, w in enumerate(exp["weights"]):
                cumulative += w
                if r <= cumulative:
                    self._assignments[key] = exp["variants"][i]
                    return {"experiment": experiment, "user_id": user_id,
                            "variant": exp["variants"][i]}
            return {"experiment": experiment, "user_id": user_id,
                    "variant": exp["variants"][-1]}

    def list_experiments(self) -> list[dict]:
        with self._lock:
            return [
                {"name": k, **v, "assignments": sum(
                    1 for key in self._assignments if key.startswith(k + ":")
                )}
                for k, v in self._experiments.items()
            ]

    def stop(self, name: str) -> dict:
        with self._lock:
            if name in self._experiments:
                self._experiments[name]["active"] = False
                return {"status": "ok"}
            return {"status": "error", "error": "实验不存在"}


_ab_test = ABTest()


# ─── P346: 实验分组器 ──────────────────────────
class ExperimentGrouper:
    """实验分组器"""

    STRATEGIES = ["random", "hash", "sticky", "layered"]

    def __init__(self):
        self._groups: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self._lock = threading.Lock()

    def assign(self, experiment: str, user_id: str, strategy: str = "hash",
               num_groups: int = 2) -> int:
        if strategy == "random":
            group = random.randint(0, num_groups - 1)
        elif strategy == "hash":
            group = hash(user_id) % num_groups
        elif strategy == "sticky":
            with self._lock:
                existing = None
                for g, users in self._groups[experiment].items():
                    if user_id in users:
                        existing = int(g)
                        break
                group = existing if existing is not None else hash(user_id) % num_groups
        else:  # layered
            group = (hash(experiment) + hash(user_id)) % num_groups
        with self._lock:
            self._groups[experiment][str(group)].append(user_id)
        return group

    def get_groups(self, experiment: str) -> dict:
        with self._lock:
            return {g: len(users) for g, users in self._groups[experiment].items()}


_grouper = ExperimentGrouper()


# ─── P347: 统计显著性检验 ──────────────────────────
class SignificanceTest:
    """统计显著性检验"""

    @staticmethod
    def z_test(control: list[float], treatment: list[float]) -> dict:
        n1, n2 = len(control), len(treatment)
        if n1 < 2 or n2 < 2:
            return {"status": "error", "error": "样本不足"}
        m1 = sum(control) / n1
        m2 = sum(treatment) / n2
        v1 = sum((x - m1) ** 2 for x in control) / (n1 - 1)
        v2 = sum((x - m2) ** 2 for x in treatment) / (n2 - 1)
        se = math.sqrt(v1 / n1 + v2 / n2)
        if se == 0:
            return {"status": "error", "error": "标准误差为0"}
        z = (m2 - m1) / se
        # 双尾p值(近似)
        p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
        return {
            "control_mean": round(m1, 4),
            "treatment_mean": round(m2, 4),
            "z_score": round(z, 4),
            "p_value": round(p_value, 6),
            "significant": p_value < 0.05,
            "lift": round((m2 - m1) / m1 * 100, 2) if m1 != 0 else 0,
        }

    @staticmethod
    def chi_square(observed: list[list[float]]) -> dict:
        if not observed or not observed[0]:
            return {"status": "error", "error": "无数据"}
        rows = len(observed)
        cols = len(observed[0])
        row_sums = [sum(row) for row in observed]
        col_sums = [sum(observed[r][c] for r in range(rows)) for c in range(cols)]
        total = sum(row_sums)
        if total == 0:
            return {"status": "error", "error": "总样本为0"}
        chi2 = 0
        for r in range(rows):
            for c in range(cols):
                expected = row_sums[r] * col_sums[c] / total
                if expected > 0:
                    chi2 += (observed[r][c] - expected) ** 2 / expected
        df = (rows - 1) * (cols - 1)
        return {"chi_square": round(chi2, 4), "df": df,
                "significant": chi2 > 3.841 if df == 1 else chi2 > 5.991 if df == 2 else False}


_sig_test = SignificanceTest()


# ─── P348: 指标追踪 ──────────────────────────
class MetricsTracker:
    """实验指标追踪"""

    def __init__(self):
        self._metrics: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        self._lock = threading.Lock()

    def record(self, experiment: str, variant: str, value: float) -> None:
        with self._lock:
            self._metrics[experiment][variant].append(value)

    def get_stats(self, experiment: str) -> dict:
        with self._lock:
            exp_metrics = self._metrics.get(experiment, {})
            stats = {}
            for variant, values in exp_metrics.items():
                if values:
                    stats[variant] = {
                        "count": len(values),
                        "mean": round(sum(values) / len(values), 4),
                        "min": min(values),
                        "max": max(values),
                        "sum": sum(values),
                    }
        return stats

    def compare(self, experiment: str, control: str, treatment: str) -> dict:
        with self._lock:
            ctrl = list(self._metrics.get(experiment, {}).get(control, []))
            trt = list(self._metrics.get(experiment, {}).get(treatment, []))
        return _sig_test.z_test(ctrl, trt)


_metrics_tracker = MetricsTracker()


# ─── P349: 多变量测试 ──────────────────────────
class MultivariateTest:
    """多变量测试(MVT)"""

    def __init__(self):
        self._factors: dict[str, list[str]] = {}
        self._combinations: dict[str, dict] = {}
        self._lock = threading.Lock()

    def add_factor(self, name: str, levels: list[str]) -> None:
        with self._lock:
            self._factors[name] = levels
            self._rebuild_combinations()

    def _rebuild_combinations(self) -> None:
        # 笛卡尔积
        import itertools
        factor_names = list(self._factors.keys())
        if not factor_names:
            return
        level_lists = [self._factors[n] for n in factor_names]
        self._combinations = {}
        for combo in itertools.product(*level_lists):
            key = "|".join(f"{n}={v}" for n, v in zip(factor_names, combo))
            self._combinations[key] = {
                "factors": dict(zip(factor_names, combo)),
                "assignments": 0,
                "results": [],
            }

    def assign(self, user_id: str) -> dict:
        with self._lock:
            if not self._combinations:
                return {"status": "error", "error": "无变体组合"}
            combo_key = list(self._combinations.keys())[hash(user_id) % len(self._combinations)]
            self._combinations[combo_key]["assignments"] += 1
            return {"combination": combo_key,
                    "factors": self._combinations[combo_key]["factors"]}

    def record_result(self, combination: str, value: float) -> None:
        with self._lock:
            if combination in self._combinations:
                self._combinations[combination]["results"].append(value)

    def get_results(self) -> dict:
        with self._lock:
            results = {}
            for key, data in self._combinations.items():
                r = data["results"]
                results[key] = {
                    "factors": data["factors"],
                    "assignments": data["assignments"],
                    "mean": round(sum(r) / len(r), 4) if r else 0,
                    "count": len(r),
                }
        return results


_mvt = MultivariateTest()


# ─── P350: 实验报告 ──────────────────────────
class ExperimentReporter:
    """实验报告生成器"""

    @staticmethod
    def generate(experiment: str, ab_test: ABTest,
                 metrics: MetricsTracker) -> dict:
        exps = ab_test.list_experiments()
        exp = next((e for e in exps if e["name"] == experiment), None)
        if not exp:
            return {"status": "error", "error": "实验不存在"}
        stats = metrics.get_stats(experiment)
        report = {
            "experiment": experiment,
            "created_at": exp.get("created_at"),
            "active": exp.get("active"),
            "variants": exp["variants"],
            "total_assignments": exp.get("assignments", 0),
            "metrics_summary": stats,
            "comparisons": {},
            "recommendation": "",
        }
        # 两两比较
        variants = exp["variants"]
        for i in range(len(variants)):
            for j in range(i + 1, len(variants)):
                ctrl = variants[i]
                trt = variants[j]
                comp = metrics.compare(experiment, ctrl, trt)
                report["comparisons"][f"{ctrl}_vs_{trt}"] = comp
        # 推荐
        best_variant = None
        best_mean = float("-inf")
        for v, s in stats.items():
            if s["mean"] > best_mean:
                best_mean = s["mean"]
                best_variant = v
        if best_variant:
            report["recommendation"] = f"推荐变体: {best_variant} (均值={best_mean})"
        return report


_reporter = ExperimentReporter()
