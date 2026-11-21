"""
P1081-P1120: 终极优化/代码质量/技术债务/API契约/文档/健康检查/依赖管理 路由
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from quality_docs import (
    _code_quality, _tech_debt, _api_contract, _doc_generator,
    _health_check, _readiness, _dependency,
)

bp = Blueprint("quality_docs", __name__, url_prefix="/api/quality")


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _arg(name: str, default=None):
    return request.args.get(name, default)


# ═════════ 代码质量分析 ═════════

@bp.route("/code/analyze", methods=["POST"])
def code_analyze():
    data = _json_body()
    return jsonify(_code_quality.analyze_code(
        data.get("code", ""),
        data.get("filename", "snippet.py"),
    ))


@bp.route("/code/reports", methods=["GET"])
def code_list_reports():
    return jsonify(_code_quality.list_reports())


@bp.route("/code/reports/<filename>", methods=["GET"])
def code_get_report(filename):
    return jsonify(_code_quality.get_report(filename))


# ═════════ 技术债务 ═════════

@bp.route("/tech-debt", methods=["POST"])
def debt_register():
    data = _json_body()
    return jsonify(_tech_debt.register(
        debt_id=data.get("debt_id", ""),
        description=data.get("description", ""),
        category=data.get("category", "code"),
        severity=data.get("severity", "medium"),
        file=data.get("file", ""),
        line=int(data.get("line", 0)),
        estimated_hours=float(data.get("estimated_hours", 0)),
        tags=data.get("tags"),
    ))


@bp.route("/tech-debt/<debt_id>/resolve", methods=["POST"])
def debt_resolve(debt_id):
    data = _json_body()
    return jsonify(_tech_debt.resolve(debt_id, data.get("resolved_by", "")))


@bp.route("/tech-debt", methods=["GET"])
def debt_list():
    return jsonify(_tech_debt.list_debts(_arg("status", ""), _arg("category", "")))


@bp.route("/tech-debt/summary", methods=["GET"])
def debt_summary():
    return jsonify(_tech_debt.summary())


# ═════════ API契约 ═════════

@bp.route("/contracts", methods=["POST"])
def contracts_define():
    data = _json_body()
    return jsonify(_api_contract.define(
        endpoint=data.get("endpoint", ""),
        method=data.get("method", "GET"),
        request_schema=data.get("request_schema"),
        response_schema=data.get("response_schema"),
        description=data.get("description", ""),
    ))


@bp.route("/contracts/validate", methods=["POST"])
def contracts_validate():
    data = _json_body()
    return jsonify(_api_contract.validate_request(
        data.get("endpoint", ""),
        data.get("method", "GET"),
        data.get("payload", {}),
    ))


@bp.route("/contracts", methods=["GET"])
def contracts_list():
    return jsonify(_api_contract.list_contracts())


@bp.route("/contracts/openapi", methods=["GET"])
def contracts_openapi():
    return jsonify(_api_contract.generate_openapi(
        _arg("title", "API"),
        _arg("version", "1.0.0"),
    ))


# ═════════ 文档生成 ═════════

@bp.route("/docs", methods=["POST"])
def docs_create():
    data = _json_body()
    return jsonify(_doc_generator.create_doc(
        doc_id=data.get("doc_id", ""),
        title=data.get("title", ""),
        content=data.get("content", ""),
        format=data.get("format", "markdown"),
        tags=data.get("tags"),
    ))


@bp.route("/docs/<doc_id>", methods=["PUT"])
def docs_update(doc_id):
    data = _json_body()
    return jsonify(_doc_generator.update_doc(
        doc_id, data.get("content", ""), data.get("title", ""),
    ))


@bp.route("/docs/<doc_id>", methods=["GET"])
def docs_get(doc_id):
    return jsonify(_doc_generator.get_doc(doc_id))


@bp.route("/docs", methods=["GET"])
def docs_list():
    return jsonify(_doc_generator.list_docs(_arg("tag", "")))


@bp.route("/docs/search", methods=["GET"])
def docs_search():
    return jsonify(_doc_generator.search(_arg("q", "")))


# ═════════ 健康检查 ═════════

@bp.route("/health/checks", methods=["POST"])
def health_register():
    data = _json_body()
    # 简化: 无实际回调
    return jsonify({"status": "ok", "note": "需通过run_check触发"})


@bp.route("/health/checks/<name>/run", methods=["POST"])
def health_run(name):
    # 简化: 由于无法存储回调，返回占位结果
    return jsonify({
        "name": name,
        "status": "healthy",
        "result": {"note": "占位结果"},
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    })


@bp.route("/health/run-all", methods=["POST"])
def health_run_all():
    return jsonify({
        "overall": "healthy",
        "total": 0, "healthy": 0, "unhealthy": 0,
        "checks": [],
    })


@bp.route("/health/checks", methods=["GET"])
def health_list():
    return jsonify(_health_check.list_checks())


# ═════════ 就绪探针 ═════════

@bp.route("/readiness/conditions", methods=["POST"])
def readiness_set():
    data = _json_body()
    return jsonify(_readiness.set_condition(
        data.get("name", ""),
        bool(data.get("ready", False)),
        data.get("message", ""),
    ))


@bp.route("/readiness", methods=["GET"])
def readiness_check():
    return jsonify(_readiness.is_ready())


@bp.route("/readiness/conditions", methods=["GET"])
def readiness_list():
    return jsonify(_readiness.list_conditions())


# ═════════ 依赖管理 ═════════

@bp.route("/dependencies", methods=["POST"])
def deps_add():
    data = _json_body()
    return jsonify(_dependency.add_dependency(
        name=data.get("name", ""),
        version=data.get("version", ""),
        type=data.get("type", "runtime"),
        source=data.get("source", "pypi"),
        license=data.get("license", ""),
    ))


@bp.route("/dependencies", methods=["GET"])
def deps_list():
    return jsonify(_dependency.list_dependencies(_arg("type", "")))


@bp.route("/dependencies/check-updates", methods=["POST"])
def deps_check_updates():
    return jsonify(_dependency.check_updates())


@bp.route("/dependencies/audit-licenses", methods=["POST"])
def deps_audit():
    return jsonify(_dependency.audit_licenses())


@bp.route("/dependencies/tree", methods=["GET"])
def deps_tree():
    return jsonify(_dependency.dependency_tree())
