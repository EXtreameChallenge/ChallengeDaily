"""
P381-P400: 隐私保护 + 数据血缘 + 元数据 + 数据质量(20轮)
- P381: PII数据发现器
- P382: 数据脱敏管道
- P383: 匿名化处理
- P384: 数据主体请求(DSR)
- P385: 同意管理
- P386: 数据血缘追踪
- P387: 血缘可视化
- P388: 影响分析
- P389: 元数据目录
- P390: 元数据版本管理
- P391: 数据质量规则
- P392: 数据质量评分
- P393: 异常检测
- P394: 数据质量报告
- P395: 数据质量监控
- P396: 数据质量告警
- P397: 数据质量修复
- P398: 数据质量趋势
- P399: 元数据搜索
- P400: 隐私影响评估
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P381: PII数据发现器 ──────────────────────────
class PIIDiscoverer:
    """PII数据发现器"""

    PATTERNS = {
        "email": (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "high"),
        "phone": (r"1[3-9]\d{9}", "high"),
        "id_card": (r"\d{17}[\dXx]", "critical"),
        "bank_card": (r"\d{16,19}", "high"),
        "ip": (r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "medium"),
        "passport": (r"[A-Z]\d{8}", "high"),
        "name_cn": (r"[\u4e00-\u9fff]{2,4}", "low"),
        "address": (r"[\u4e00-\u9fff]{2,}(省|市|区|县|路|街|号)", "medium"),
    }

    @classmethod
    def scan(cls, text: str) -> list[dict]:
        findings = []
        for pii_type, (pattern, severity) in cls.PATTERNS.items():
            for m in re.finditer(pattern, text):
                findings.append({
                    "type": pii_type,
                    "value": m.group(),
                    "start": m.start(),
                    "end": m.end(),
                    "severity": severity,
                })
        findings.sort(key=lambda x: x["start"])
        return findings

    @classmethod
    def scan_dict(cls, data: dict) -> dict[str, list[dict]]:
        results = {}
        for key, value in data.items():
            if isinstance(value, str):
                findings = cls.scan(value)
                if findings:
                    results[key] = findings
        return results


_pii = PIIDiscoverer()


# ─── P382: 数据脱敏管道 ──────────────────────────
class RedactionPipeline:
    """数据脱敏管道(多阶段)"""

    @staticmethod
    def mask_email(email: str) -> str:
        if "@" not in email:
            return email
        local, domain = email.split("@", 1)
        if len(local) <= 2:
            return "*" * len(local) + "@" + domain
        return local[0] + "*" * (len(local) - 2) + local[-1] + "@" + domain

    @staticmethod
    def mask_phone(phone: str) -> str:
        if len(phone) < 7:
            return "*" * len(phone)
        return phone[:3] + "*" * (len(phone) - 7) + phone[-4:]

    @staticmethod
    def mask_id_card(id_card: str) -> str:
        if len(id_card) < 6:
            return "*" * len(id_card)
        return id_card[:6] + "*" * (len(id_card) - 10) + id_card[-4:]

    @staticmethod
    def mask_bank_card(card: str) -> str:
        if len(card) < 8:
            return "*" * len(card)
        return card[:4] + "*" * (len(card) - 8) + card[-4:]

    @classmethod
    def redact(cls, text: str, pii_findings: list[dict]) -> str:
        # 从后往前替换以保持位置
        sorted_findings = sorted(pii_findings, key=lambda x: x["start"], reverse=True)
        result = text
        for f in sorted_findings:
            value = f["value"]
            start, end = f["start"], f["end"]
            if f["type"] == "email":
                masked = cls.mask_email(value)
            elif f["type"] == "phone":
                masked = cls.mask_phone(value)
            elif f["type"] == "id_card":
                masked = cls.mask_id_card(value)
            elif f["type"] == "bank_card":
                masked = cls.mask_bank_card(value)
            else:
                masked = "*" * len(value)
            result = result[:start] + masked + result[end:]
        return result


_redact = RedactionPipeline()


# ─── P383: 匿名化处理 ──────────────────────────
class Anonymizer:
    """数据匿名化"""

    @staticmethod
    def hash_anonymize(value: str, salt: str = "") -> str:
        return hashlib.sha256((value + salt).encode()).hexdigest()[:16]

    @staticmethod
    def generalize(value: str, level: int = 1) -> str:
        """泛化处理"""
        if "@" in value and level == 1:
            # 邮箱泛化到域名
            return "*@" + value.split("@")[1]
        elif value.isdigit() and level == 1:
            # 数字泛化到范围
            n = len(value)
            if n >= 4:
                return value[:2] + "*" * (n - 4) + value[-2:]
        return "*" * len(value)

    @staticmethod
    def perturb(value: float, noise_range: float = 0.1) -> float:
        """数值扰动"""
        import random
        noise = random.uniform(-noise_range, noise_range)
        return value * (1 + noise)

    @staticmethod
    def k_anonymity(records: list[dict], quasi_identifiers: list[str],
                    k: int = 5) -> dict:
        """K-匿名检查"""
        groups = defaultdict(list)
        for r in records:
            key = tuple(r.get(qi, "") for qi in quasi_identifiers)
            groups[key].append(r)
        violations = [k for k, v in groups.items() if len(v) < k]
        return {
            "total_groups": len(groups),
            "violations": len(violations),
            "k_value": k,
            "is_k_anonymous": len(violations) == 0,
        }


_anon = Anonymizer()


# ─── P384: 数据主体请求(DSR) ──────────────────────────
class DSRHandler:
    """数据主体请求处理"""

    REQUEST_TYPES = ["access", "deletion", "portability", "rectification", "restriction"]

    def __init__(self):
        self._requests: deque = deque(maxlen=500)
        self._lock = threading.Lock()

    def create(self, user_id: str, request_type: str,
               details: dict | None = None) -> dict:
        if request_type not in self.REQUEST_TYPES:
            return {"status": "error", "error": "未知请求类型"}
        with self._lock:
            req_id = f"dsr_{len(self._requests) + 1}"
            self._requests.append({
                "request_id": req_id,
                "user_id": user_id,
                "type": request_type,
                "details": details or {},
                "status": "pending",
                "created_at": datetime.now().isoformat(),
            })
            return {"status": "ok", "request_id": req_id}

    def process(self, request_id: str, status: str = "completed") -> dict:
        with self._lock:
            for r in self._requests:
                if r["request_id"] == request_id:
                    r["status"] = status
                    r["processed_at"] = datetime.now().isoformat()
                    return {"status": "ok"}
            return {"status": "error", "error": "请求不存在"}

    def list_requests(self, user_id: str | None = None) -> list[dict]:
        with self._lock:
            reqs = list(self._requests)
        if user_id:
            reqs = [r for r in reqs if r["user_id"] == user_id]
        return reqs


_dsr = DSRHandler()


# ─── P385: 同意管理 ──────────────────────────
class ConsentManager:
    """同意管理"""

    def __init__(self):
        self._consents: dict[str, dict[str, dict]] = defaultdict(dict)
        self._lock = threading.Lock()

    def grant(self, user_id: str, purpose: str,
              lawful_basis: str = "consent") -> dict:
        with self._lock:
            self._consents[user_id][purpose] = {
                "granted": True,
                "lawful_basis": lawful_basis,
                "granted_at": datetime.now().isoformat(),
                "withdrawn_at": None,
            }
            return {"status": "ok"}

    def withdraw(self, user_id: str, purpose: str) -> dict:
        with self._lock:
            if purpose in self._consents[user_id]:
                self._consents[user_id][purpose]["granted"] = False
                self._consents[user_id][purpose]["withdrawn_at"] = datetime.now().isoformat()
                return {"status": "ok"}
            return {"status": "error", "error": "未找到同意记录"}

    def check(self, user_id: str, purpose: str) -> bool:
        with self._lock:
            c = self._consents.get(user_id, {}).get(purpose)
            return c["granted"] if c else False

    def list_consents(self, user_id: str) -> dict:
        with self._lock:
            return dict(self._consents.get(user_id, {}))


_consent = ConsentManager()


# ─── P386: 数据血缘追踪 ──────────────────────────
class DataLineage:
    """数据血缘追踪"""

    def __init__(self):
        self._nodes: dict[str, dict] = {}
        self._edges: list[tuple[str, str, dict]] = []
        self._lock = threading.Lock()

    def add_node(self, node_id: str, node_type: str,
                 metadata: dict | None = None) -> None:
        with self._lock:
            self._nodes[node_id] = {
                "type": node_type,
                "metadata": metadata or {},
                "added_at": datetime.now().isoformat(),
            }

    def add_edge(self, src: str, dst: str,
                 transformation: str = "", metadata: dict | None = None) -> None:
        with self._lock:
            self._edges.append((src, dst, {
                "transformation": transformation,
                "metadata": metadata or {},
            }))

    def get_upstream(self, node_id: str) -> list[dict]:
        with self._lock:
            upstream = [{"source": s, "target": node_id, **data}
                        for s, d, data in self._edges if d == node_id]
            return upstream

    def get_downstream(self, node_id: str) -> list[dict]:
        with self._lock:
            downstream = [{"source": node_id, "target": d, **data}
                          for s, d, data in self._edges if s == node_id]
            return downstream

    def get_full_lineage(self, node_id: str, direction: str = "both") -> dict:
        result = {}
        if direction in ("upstream", "both"):
            result["upstream"] = self.get_upstream(node_id)
        if direction in ("downstream", "both"):
            result["downstream"] = self.get_downstream(node_id)
        return result


_lineage = DataLineage()


# ─── P387: 血缘可视化 ──────────────────────────
class LineageVisualizer:
    """血缘可视化"""

    @staticmethod
    def to_d3_format(lineage: DataLineage) -> dict:
        nodes = [{"id": nid, **data} for nid, data in lineage._nodes.items()]
        links = [{"source": s, "target": d, **data}
                 for s, d, data in lineage._edges]
        return {"nodes": nodes, "links": links}

    @staticmethod
    def to_dot_format(lineage: DataLineage) -> str:
        lines = ["digraph lineage {"]
        for nid, data in lineage._nodes.items():
            lines.append(f'  "{nid}" [label="{nid}", type="{data["type"]}"];')
        for src, dst, data in lineage._edges:
            label = data.get("transformation", "")
            lines.append(f'  "{src}" -> "{dst}" [label="{label}"];')
        lines.append("}")
        return "\n".join(lines)


_lineage_viz = LineageVisualizer()


# ─── P388: 影响分析 ──────────────────────────
class ImpactAnalyzer:
    """影响分析"""

    @staticmethod
    def analyze(lineage: DataLineage, node_id: str) -> dict:
        # 下游影响(递归)
        visited = set()
        impact_set = set()
        queue = [node_id]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            downstream = lineage.get_downstream(current)
            for d in downstream:
                if d["target"] not in visited:
                    impact_set.add(d["target"])
                    queue.append(d["target"])
        return {
            "source": node_id,
            "impacted_nodes": list(impact_set),
            "impact_count": len(impact_set),
            "risk_level": "critical" if len(impact_set) > 10 else
                          "high" if len(impact_set) > 5 else
                          "medium" if len(impact_set) > 0 else "low",
        }


_impact = ImpactAnalyzer()


# ─── P389: 元数据目录 ──────────────────────────
class MetadataCatalog:
    """元数据目录"""

    def __init__(self):
        self._catalog: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register(self, asset_id: str, name: str, asset_type: str,
                 owner: str = "", description: str = "",
                 schema: dict | None = None, tags: list[str] | None = None) -> None:
        with self._lock:
            self._catalog[asset_id] = {
                "name": name,
                "type": asset_type,
                "owner": owner,
                "description": description,
                "schema": schema or {},
                "tags": tags or [],
                "registered_at": datetime.now().isoformat(),
            }

    def get(self, asset_id: str) -> dict | None:
        with self._lock:
            return self._catalog.get(asset_id)

    def search(self, query: str = "", tags: list[str] | None = None) -> list[dict]:
        with self._lock:
            results = []
            for aid, data in self._catalog.items():
                if query and query.lower() not in data["name"].lower() and \
                   query.lower() not in data.get("description", "").lower():
                    continue
                if tags and not any(t in data["tags"] for t in tags):
                    continue
                results.append({"asset_id": aid, **data})
            return results

    def list_all(self) -> list[dict]:
        with self._lock:
            return [{"asset_id": k, **v} for k, v in self._catalog.items()]


_catalog = MetadataCatalog()


# ─── P390: 元数据版本管理 ──────────────────────────
class MetadataVersioning:
    """元数据版本管理"""

    def __init__(self):
        self._versions: dict[str, deque] = defaultdict(lambda: deque(maxlen=50))
        self._lock = threading.Lock()

    def save_version(self, asset_id: str, metadata: dict) -> dict:
        with self._lock:
            version_num = len(self._versions[asset_id]) + 1
            self._versions[asset_id].append({
                "version": version_num,
                "metadata": metadata,
                "saved_at": datetime.now().isoformat(),
            })
            return {"status": "ok", "version": version_num}

    def get_version(self, asset_id: str, version: int) -> dict | None:
        with self._lock:
            versions = list(self._versions.get(asset_id, deque()))
            for v in versions:
                if v["version"] == version:
                    return v
            return None

    def get_history(self, asset_id: str) -> list[dict]:
        with self._lock:
            return list(self._versions.get(asset_id, deque()))


_meta_version = MetadataVersioning()


# ─── P391-P400: 数据质量系列 ──────────────────────────
class DataQualityRules:
    """数据质量规则"""

    def __init__(self):
        self._rules: dict[str, dict] = {}
        self._lock = threading.Lock()

    def add(self, rule_id: str, dimension: str, check_fn: Callable[[Any], bool],
            description: str = "") -> None:
        with self._lock:
            self._rules[rule_id] = {
                "dimension": dimension,
                "check": check_fn,
                "description": description,
            }

    def validate(self, rule_id: str, value: Any) -> dict:
        with self._lock:
            rule = self._rules.get(rule_id)
        if not rule:
            return {"valid": False, "error": "规则不存在"}
        try:
            passed = rule["check"](value)
            return {"rule_id": rule_id, "valid": passed,
                    "dimension": rule["dimension"]}
        except Exception as e:
            return {"rule_id": rule_id, "valid": False, "error": str(e)}

    def list_rules(self) -> list[dict]:
        with self._lock:
            return [{"rule_id": k, "dimension": v["dimension"],
                     "description": v["description"]}
                    for k, v in self._rules.items()]


_dq_rules = DataQualityRules()


class DataQualityScorer:
    """数据质量评分"""

    DIMENSIONS = ["completeness", "accuracy", "consistency",
                  "timeliness", "validity", "uniqueness"]

    @staticmethod
    def score(scores: dict[str, float]) -> dict:
        total = 0
        valid_dims = 0
        for dim in DataQualityScorer.DIMENSIONS:
            if dim in scores:
                s = max(0, min(100, scores[dim]))
                total += s
                valid_dims += 1
        overall = total / valid_dims if valid_dims > 0 else 0
        grade = "A" if overall >= 90 else "B" if overall >= 80 else \
                "C" if overall >= 70 else "D" if overall >= 60 else "F"
        return {
            "overall_score": round(overall, 2),
            "grade": grade,
            "dimension_scores": scores,
            "dimensions_evaluated": valid_dims,
        }


_dq_scorer = DataQualityScorer()


class DataQualityMonitor:
    """数据质量监控"""

    def __init__(self):
        self._history: deque = deque(maxlen=1000)
        self._alerts: deque = deque(maxlen=200)
        self._lock = threading.Lock()

    def record(self, dataset: str, scores: dict[str, float]) -> dict:
        result = _dq_scorer.score(scores)
        with self._lock:
            self._history.append({
                "dataset": dataset,
                "scores": scores,
                "overall": result["overall_score"],
                "grade": result["grade"],
                "timestamp": datetime.now().isoformat(),
            })
            # 告警
            if result["overall_score"] < 70:
                self._alerts.append({
                    "dataset": dataset,
                    "score": result["overall_score"],
                    "grade": result["grade"],
                    "severity": "high" if result["overall_score"] < 50 else "medium",
                    "timestamp": datetime.now().isoformat(),
                })
        return result

    def get_history(self, dataset: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            h = list(self._history)
        if dataset:
            h = [x for x in h if x["dataset"] == dataset]
        h.reverse()
        return h[:limit]

    def get_alerts(self, limit: int = 50) -> list[dict]:
        with self._lock:
            a = list(self._alerts)
        a.reverse()
        return a[:limit]

    def get_trend(self, dataset: str, periods: int = 7) -> dict:
        with self._lock:
            h = [x for x in self._history if x["dataset"] == dataset]
        h = h[-periods:]
        if not h:
            return {"dataset": dataset, "trend": "unknown"}
        scores = [x["overall"] for x in h]
        avg = sum(scores) / len(scores)
        trend = "improving" if len(scores) > 1 and scores[-1] > scores[0] else \
                "declining" if len(scores) > 1 and scores[-1] < scores[0] else "stable"
        return {"dataset": dataset, "avg_score": round(avg, 2),
                "trend": trend, "data_points": len(scores)}


_dq_monitor = DataQualityMonitor()


# ─── P400: 隐私影响评估 ──────────────────────────
class PrivacyImpactAssessment:
    """隐私影响评估(PIA)"""

    def __init__(self):
        self._assessments: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, project_name: str, data_types: list[str],
               purposes: list[str], recipients: list[str],
               retention_days: int) -> dict:
        risk_score = 0
        if "id_card" in data_types or "biometric" in data_types:
            risk_score += 30
        if "health" in data_types:
            risk_score += 25
        if "financial" in data_types:
            risk_score += 20
        if len(purposes) > 3:
            risk_score += 15
        if len(recipients) > 5:
            risk_score += 10
        if retention_days > 365:
            risk_score += 10
        risk_level = ("low" if risk_score < 25 else
                      "medium" if risk_score < 50 else
                      "high" if risk_score < 75 else "critical")
        with self._lock:
            aid = f"pia_{len(self._assessments) + 1}"
            self._assessments[aid] = {
                "project": project_name,
                "data_types": data_types,
                "purposes": purposes,
                "recipients": recipients,
                "retention_days": retention_days,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "requires_review": risk_score >= 50,
                "created_at": datetime.now().isoformat(),
            }
            return {"assessment_id": aid, **self._assessments[aid]}

    def get(self, assessment_id: str) -> dict | None:
        with self._lock:
            return self._assessments.get(assessment_id)

    def list_all(self) -> list[dict]:
        with self._lock:
            return [{"assessment_id": k, **v} for k, v in self._assessments.items()]


_pia = PrivacyImpactAssessment()
