"""
P1081-P1120: 终极优化+代码质量+技术债务+文档生成+API契约+依赖管理+健康检查+就绪探针(40轮)
"""
from __future__ import annotations

import ast
import os
import re
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

logger = __import__("logging").getLogger(__name__)


# ═════════ P1081-P1090: 代码质量分析 ═════════

class CodeQualityAnalyzer:
    """代码质量分析器"""

    def __init__(self):
        self._reports: dict[str, dict] = {}
        self._lock = threading.Lock()

    def analyze_code(self, code: str, filename: str = "snippet.py") -> dict:
        issues = []
        metrics = {"lines": 0, "code_lines": 0, "comment_lines": 0,
                   "blank_lines": 0, "functions": 0, "classes": 0,
                   "imports": 0, "complexity": 0}
        lines = code.split("\n")
        metrics["lines"] = len(lines)
        for line in lines:
            stripped = line.strip()
            if not stripped:
                metrics["blank_lines"] += 1
            elif stripped.startswith("#"):
                metrics["comment_lines"] += 1
            else:
                metrics["code_lines"] += 1
        # AST分析
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    metrics["functions"] += 1
                    # 圈复杂度
                    complexity = 1
                    for n in ast.walk(node):
                        if isinstance(n, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                            complexity += 1
                        elif isinstance(n, ast.BoolOp):
                            complexity += len(n.values) - 1
                    metrics["complexity"] += complexity
                    if complexity > 10:
                        issues.append({
                            "type": "high_complexity",
                            "severity": "warning",
                            "function": node.name,
                            "line": node.lineno,
                            "complexity": complexity,
                            "message": f"函数 {node.name} 圈复杂度 {complexity} 过高",
                        })
                elif isinstance(node, ast.ClassDef):
                    metrics["classes"] += 1
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    metrics["imports"] += 1
        except SyntaxError as e:
            issues.append({
                "type": "syntax_error",
                "severity": "critical",
                "line": e.lineno or 0,
                "message": str(e),
            })
        # 行长度检查
        for i, line in enumerate(lines, 1):
            if len(line) > 120:
                issues.append({
                    "type": "long_line",
                    "severity": "info",
                    "line": i,
                    "length": len(line),
                    "message": f"行长度 {len(line)} 超过 120 字符",
                })
        # 评分
        score = 100
        for issue in issues:
            if issue["severity"] == "critical":
                score -= 20
            elif issue["severity"] == "warning":
                score -= 5
            elif issue["severity"] == "info":
                score -= 1
        score = max(0, score)
        report = {
            "filename": filename,
            "metrics": metrics,
            "issues": issues,
            "issue_count": len(issues),
            "quality_score": score,
            "analyzed_at": datetime.now().isoformat(),
        }
        with self._lock:
            self._reports[filename] = report
        return report

    def list_reports(self) -> list[dict]:
        with self._lock:
            return [{"filename": k, "quality_score": v["quality_score"],
                     "issue_count": v["issue_count"],
                     "metrics": v["metrics"]}
                    for k, v in self._reports.items()]

    def get_report(self, filename: str) -> dict:
        with self._lock:
            return self._reports.get(filename, {"error": "报告不存在"})


_code_quality = CodeQualityAnalyzer()


# ═════════ P1091-P1100: 技术债务管理 ═════════

class TechDebtManager:
    """技术债务管理"""

    def __init__(self):
        self._debts: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register(self, debt_id: str, description: str,
                 category: str = "code", severity: str = "medium",
                 file: str = "", line: int = 0,
                 estimated_hours: float = 0, tags: list[str] | None = None) -> dict:
        with self._lock:
            self._debts[debt_id] = {
                "description": description,
                "category": category,
                "severity": severity,
                "file": file, "line": line,
                "estimated_hours": estimated_hours,
                "tags": tags or [],
                "status": "open",
                "created_at": datetime.now().isoformat(),
            }
            return {"status": "ok", "debt_id": debt_id}

    def resolve(self, debt_id: str, resolved_by: str = "") -> dict:
        with self._lock:
            d = self._debts.get(debt_id)
            if not d:
                return {"status": "error", "error": "债务不存在"}
            d["status"] = "resolved"
            d["resolved_by"] = resolved_by
            d["resolved_at"] = datetime.now().isoformat()
            return {"status": "ok"}

    def list_debts(self, status: str = "", category: str = "") -> list[dict]:
        with self._lock:
            debts = [{"debt_id": k, **v} for k, v in self._debts.items()]
        if status:
            debts = [d for d in debts if d["status"] == status]
        if category:
            debts = [d for d in debts if d["category"] == category]
        return debts

    def summary(self) -> dict:
        with self._lock:
            debts = list(self._debts.values())
        open_debts = [d for d in debts if d["status"] == "open"]
        return {
            "total": len(debts),
            "open": len(open_debts),
            "resolved": len(debts) - len(open_debts),
            "by_severity": dict(Counter(d["severity"] for d in open_debts)),
            "by_category": dict(Counter(d["category"] for d in open_debts)),
            "total_estimated_hours": sum(d["estimated_hours"] for d in open_debts),
        }


_tech_debt = TechDebtManager()


# ═════════ P1101-P1110: API契约 + 文档生成 ═════════

class APIContractManager:
    """API契约管理"""

    def __init__(self):
        self._contracts: dict[str, dict] = {}
        self._lock = threading.Lock()

    def define(self, endpoint: str, method: str,
               request_schema: dict | None = None,
               response_schema: dict | None = None,
               description: str = "") -> dict:
        with self._lock:
            self._contracts[f"{method}:{endpoint}"] = {
                "endpoint": endpoint,
                "method": method,
                "request_schema": request_schema or {},
                "response_schema": response_schema or {},
                "description": description,
                "defined_at": datetime.now().isoformat(),
            }
            return {"status": "ok"}

    def validate_request(self, endpoint: str, method: str,
                         payload: dict) -> dict:
        with self._lock:
            contract = self._contracts.get(f"{method}:{endpoint}")
        if not contract:
            return {"valid": True, "reason": "无契约定义"}
        schema = contract["request_schema"]
        issues = []
        for field_name, field_type in schema.items():
            if field_name not in payload:
                issues.append(f"缺少字段: {field_name}")
            elif not self._check_type(payload[field_name], field_type):
                issues.append(f"字段 {field_name} 类型不符，期望 {field_type}")
        return {"valid": len(issues) == 0, "issues": issues}

    def _check_type(self, value: Any, expected_type: str) -> bool:
        type_map = {
            "string": str, "int": int, "float": (int, float),
            "bool": bool, "list": list, "dict": dict,
        }
        py_type = type_map.get(expected_type, object)
        return isinstance(value, py_type)

    def list_contracts(self) -> list[dict]:
        with self._lock:
            return list(self._contracts.values())

    def generate_openapi(self, title: str = "API",
                         version: str = "1.0.0") -> dict:
        with self._lock:
            contracts = list(self._contracts.values())
        paths = {}
        for c in contracts:
            ep = c["endpoint"]
            method = c["method"].lower()
            if ep not in paths:
                paths[ep] = {}
            paths[ep][method] = {
                "summary": c["description"],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"type": "object",
                                       "properties": c["request_schema"]}
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "成功",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object",
                                           "properties": c["response_schema"]}
                            }
                        }
                    }
                },
            }
        return {
            "openapi": "3.0.0",
            "info": {"title": title, "version": version},
            "paths": paths,
        }


class DocGenerator:
    """文档生成器"""

    def __init__(self):
        self._docs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create_doc(self, doc_id: str, title: str, content: str,
                   format: str = "markdown", tags: list[str] | None = None) -> dict:
        with self._lock:
            self._docs[doc_id] = {
                "title": title,
                "content": content,
                "format": format,
                "tags": tags or [],
                "version": 1,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
            return {"status": "ok", "doc_id": doc_id, "version": 1}

    def update_doc(self, doc_id: str, content: str = "",
                   title: str = "") -> dict:
        with self._lock:
            d = self._docs.get(doc_id)
            if not d:
                return {"status": "error", "error": "文档不存在"}
            if title:
                d["title"] = title
            if content:
                d["content"] = content
            d["version"] += 1
            d["updated_at"] = datetime.now().isoformat()
            return {"status": "ok", "version": d["version"]}

    def get_doc(self, doc_id: str) -> dict:
        with self._lock:
            return self._docs.get(doc_id, {"error": "文档不存在"})

    def list_docs(self, tag: str = "") -> list[dict]:
        with self._lock:
            docs = [{"doc_id": k, "title": v["title"],
                     "version": v["version"], "tags": v["tags"],
                     "updated_at": v["updated_at"]}
                    for k, v in self._docs.items()]
        if tag:
            docs = [d for d in docs if tag in d["tags"]]
        return docs

    def search(self, query: str) -> list[dict]:
        with self._lock:
            results = []
            query_lower = query.lower()
            for doc_id, d in self._docs.items():
                if (query_lower in d["title"].lower() or
                        query_lower in d["content"].lower()):
                    results.append({
                        "doc_id": doc_id,
                        "title": d["title"],
                        "snippet": d["content"][:200],
                        "score": 1 if query_lower in d["title"].lower() else 0.5,
                    })
        return sorted(results, key=lambda x: -x["score"])


_api_contract = APIContractManager()
_doc_generator = DocGenerator()


# ═════════ P1111-P1120: 健康检查 + 就绪探针 + 依赖管理 ═════════

class HealthCheckManager:
    """健康检查管理器"""

    def __init__(self):
        self._checks: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register_check(self, name: str, check_fn: Callable,
                       critical: bool = True) -> dict:
        with self._lock:
            self._checks[name] = {
                "fn": check_fn,
                "critical": critical,
                "last_result": None,
                "last_run": None,
            }
            return {"status": "ok"}

    def run_check(self, name: str) -> dict:
        with self._lock:
            check = self._checks.get(name)
            if not check:
                return {"status": "error", "error": "检查不存在"}
            fn = check["fn"]
            critical = check["critical"]
        try:
            result = fn()
            status = "healthy" if result.get("healthy", False) else "unhealthy"
        except Exception as e:
            result = {"error": str(e)}
            status = "unhealthy"
        report = {
            "name": name,
            "status": status,
            "critical": critical,
            "result": result,
            "timestamp": datetime.now().isoformat(),
        }
        with self._lock:
            self._checks[name]["last_result"] = report
            self._checks[name]["last_run"] = report["timestamp"]
        return report

    def run_all(self) -> dict:
        with self._lock:
            names = list(self._checks.keys())
        results = [self.run_check(n) for n in names]
        all_healthy = all(r["status"] == "healthy" for r in results)
        critical_failed = any(r["status"] != "healthy" and r["critical"]
                              for r in results)
        return {
            "overall": "healthy" if all_healthy else (
                "critical" if critical_failed else "degraded"),
            "total": len(results),
            "healthy": sum(1 for r in results if r["status"] == "healthy"),
            "unhealthy": sum(1 for r in results if r["status"] != "healthy"),
            "checks": results,
        }

    def list_checks(self) -> list[dict]:
        with self._lock:
            return [{"name": k, "critical": v["critical"],
                     "last_run": v["last_run"]}
                    for k, v in self._checks.items()]


class ReadinessProbe:
    """就绪探针"""

    def __init__(self):
        self._conditions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set_condition(self, name: str, ready: bool,
                      message: str = "") -> dict:
        with self._lock:
            old = self._conditions.get(name, {})
            self._conditions[name] = {
                "ready": ready,
                "message": message,
                "updated_at": datetime.now().isoformat(),
                "previous_ready": old.get("ready"),
            }
            return {"status": "ok"}

    def is_ready(self) -> dict:
        with self._lock:
            conditions = dict(self._conditions)
        if not conditions:
            return {"ready": True, "reason": "无就绪条件"}
        unready = {k: v for k, v in conditions.items() if not v["ready"]}
        return {
            "ready": len(unready) == 0,
            "total_conditions": len(conditions),
            "ready_count": len(conditions) - len(unready),
            "unready_conditions": unready,
        }

    def list_conditions(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **v} for k, v in self._conditions.items()]


class DependencyManager:
    """依赖管理器"""

    def __init__(self):
        self._dependencies: dict[str, dict] = {}
        self._lock = threading.Lock()

    def add_dependency(self, name: str, version: str,
                       type: str = "runtime",
                       source: str = "pypi",
                       license: str = "") -> dict:
        with self._lock:
            self._dependencies[name] = {
                "version": version,
                "type": type,
                "source": source,
                "license": license,
                "added_at": datetime.now().isoformat(),
            }
            return {"status": "ok"}

    def check_updates(self) -> dict:
        with self._lock:
            deps = dict(self._dependencies)
        # 模拟版本检查
        updates_available = []
        for name, info in deps.items():
            # 简化: 检查是否以0.x开头(视为早期版本)
            if info["version"].startswith("0."):
                updates_available.append({
                    "name": name,
                    "current_version": info["version"],
                    "latest_version": "1.0.0",
                    "type": "major",
                })
        return {
            "total_dependencies": len(deps),
            "updates_available": len(updates_available),
            "updates": updates_available,
        }

    def audit_licenses(self) -> dict:
        with self._lock:
            deps = dict(self._dependencies)
        risky_licenses = []
        unknown_licenses = []
        for name, info in deps.items():
            if not info["license"]:
                unknown_licenses.append(name)
            elif info["license"].upper() in ("GPL", "AGPL", "LGPL"):
                risky_licenses.append({"name": name, "license": info["license"]})
        return {
            "total": len(deps),
            "unknown_licenses": unknown_licenses,
            "risky_licenses": risky_licenses,
            "safe": len(deps) - len(unknown_licenses) - len(risky_licenses),
        }

    def list_dependencies(self, type: str = "") -> list[dict]:
        with self._lock:
            deps = [{"name": k, **v} for k, v in self._dependencies.items()]
        if type:
            deps = [d for d in deps if d["type"] == type]
        return deps

    def dependency_tree(self) -> dict:
        with self._lock:
            return {
                "root": "application",
                "dependencies": [
                    {"name": k, "version": v["version"], "type": v["type"]}
                    for k, v in self._dependencies.items()
                ],
            }


_health_check = HealthCheckManager()
_readiness = ReadinessProbe()
_dependency = DependencyManager()
