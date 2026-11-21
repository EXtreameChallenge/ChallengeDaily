"""P371-P380: 成本+合规路由"""
from flask import Blueprint, request, jsonify
from cost_compliance import (
    _cost_tracker, _cost_attributor, _budget, _cost_optimizer,
    _compliance, _audit, _retention, _reporter, _policy_exec, _violation,
)

bp = Blueprint("cost_compliance", __name__, url_prefix="/api/cost-compliance")


@bp.route("/cost/record", methods=["POST"])
def cost_record():
    data = request.get_json(silent=True) or {}
    _cost_tracker.record(data.get("service", ""), data.get("resource", ""),
                         float(data.get("cost", 0)), data.get("currency", "CNY"),
                         data.get("tags"))
    return jsonify({"status": "ok"})


@bp.route("/cost/total", methods=["GET"])
def cost_total():
    service = request.args.get("service")
    start = request.args.get("start")
    end = request.args.get("end")
    return jsonify(_cost_tracker.get_total(service, start, end))


@bp.route("/cost/recent", methods=["GET"])
def cost_recent():
    return jsonify({"costs": _cost_tracker.get_recent(int(request.args.get("limit", 50)))})


@bp.route("/cost/attribute", methods=["POST"])
def cost_attribute():
    data = request.get_json(silent=True) or {}
    return jsonify(_cost_attributor.attribute(data))


@bp.route("/budget", methods=["POST"])
def budget_set():
    data = request.get_json(silent=True) or {}
    _budget.set_budget(data.get("name", ""), float(data.get("limit", 0)),
                       data.get("period", "monthly"), float(data.get("alert_threshold", 0.8)))
    return jsonify({"status": "ok"})


@bp.route("/budget/spend", methods=["POST"])
def budget_spend():
    data = request.get_json(silent=True) or {}
    return jsonify(_budget.record_spend(data.get("name", ""), float(data.get("amount", 0))))


@bp.route("/budget/list", methods=["GET"])
def budget_list():
    return jsonify({"budgets": _budget.list_budgets()})


@bp.route("/cost/optimization", methods=["POST"])
def cost_opt():
    data = request.get_json(silent=True) or {}
    return jsonify(_cost_optimizer.analyze(data.get("utilization", {}), data.get("costs", {})))


@bp.route("/compliance/rules", methods=["GET"])
def compliance_rules():
    return jsonify({"rules": _compliance.list_rules()})


@bp.route("/compliance/evaluate", methods=["POST"])
def compliance_eval():
    data = request.get_json(silent=True) or {}
    return jsonify(_compliance.evaluate(data.get("data", {})))


@bp.route("/compliance/rule", methods=["POST"])
def compliance_add_rule():
    data = request.get_json(silent=True) or {}
    _compliance.add_rule(data.get("id", ""), data.get("description", ""),
                         lambda d: True,  # 默认检查器,实际需传入
                         data.get("severity", "medium"), data.get("standard", "GDPR"))
    return jsonify({"status": "ok"})


@bp.route("/audit/record", methods=["POST"])
def audit_record():
    data = request.get_json(silent=True) or {}
    _audit.record(data.get("action", ""), data.get("actor", ""),
                  data.get("resource", ""), data.get("details"),
                  data.get("status", "compliant"))
    return jsonify({"status": "ok"})


@bp.route("/audit/search", methods=["GET"])
def audit_search():
    return jsonify({"records": _audit.search(
        request.args.get("actor"), request.args.get("action"),
        request.args.get("status"), int(request.args.get("limit", 50)))})


@bp.route("/retention/policy", methods=["POST"])
def retention_set():
    data = request.get_json(silent=True) or {}
    _retention.set_policy(data.get("data_type", ""), int(data.get("days", 365)),
                          data.get("action", "delete"), data.get("legal_hold", False))
    return jsonify({"status": "ok"})


@bp.route("/retention/check", methods=["POST"])
def retention_check():
    data = request.get_json(silent=True) or {}
    return jsonify(_retention.check_data(data.get("data_type", ""), data.get("created_at", "")))


@bp.route("/retention/policies", methods=["GET"])
def retention_list():
    return jsonify({"policies": _retention.list_policies()})


@bp.route("/report", methods=["GET"])
def report():
    return jsonify(_reporter.generate(_compliance, _audit, _retention))


@bp.route("/policy/register", methods=["POST"])
def policy_register():
    data = request.get_json(silent=True) or {}
    _policy_exec.register(data.get("name", ""), lambda ctx: {"executed": True})
    return jsonify({"status": "ok"})


@bp.route("/policy/execute", methods=["POST"])
def policy_execute():
    data = request.get_json(silent=True) or {}
    return jsonify(_policy_exec.execute(data.get("name", ""), data.get("context", {})))


@bp.route("/violation/trigger", methods=["POST"])
def violation_trigger():
    data = request.get_json(silent=True) or {}
    return jsonify(_violation.trigger(
        data.get("rule_id", ""), data.get("severity", "medium"),
        data.get("description", ""), data.get("resource", "")))


@bp.route("/violation/list", methods=["GET"])
def violation_list():
    return jsonify({"alerts": _violation.get_alerts(
        request.args.get("severity"), int(request.args.get("limit", 50)))})
