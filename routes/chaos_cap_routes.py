"""P361-P370: 混沌工程+容量规划路由"""
from flask import Blueprint, request, jsonify
from chaos_capacity import (
    _chaos, _fault_injector, _blast, _steady, _capacity, _planner,
    _forecaster, _scaler, _capacity_alert, _chaos_reporter,
)

bp = Blueprint("chaos_cap", __name__, url_prefix="/api/chaos-cap")


@bp.route("/chaos/create", methods=["POST"])
def chaos_create():
    data = request.get_json(silent=True) or {}
    return jsonify(_chaos.create(
        data.get("name", ""), data.get("target", ""),
        data.get("fault_type", ""), int(data.get("duration", 60)),
        data.get("params")))


@bp.route("/chaos/<name>/start", methods=["POST"])
def chaos_start(name: str):
    return jsonify(_chaos.start(name))


@bp.route("/chaos/<name>/stop", methods=["POST"])
def chaos_stop(name: str):
    return jsonify(_chaos.stop(name))


@bp.route("/chaos/list", methods=["GET"])
def chaos_list():
    return jsonify({"experiments": _chaos.list_experiments()})


@bp.route("/fault/types", methods=["GET"])
def fault_types():
    return jsonify({"faults": _fault_injector.list_faults()})


@bp.route("/fault/inject", methods=["POST"])
def fault_inject():
    data = request.get_json(silent=True) or {}
    fault_type = data.get("type", "latency")
    if fault_type == "latency":
        return jsonify(_fault_injector.inject_latency(int(data.get("delay_ms", 100))))
    elif fault_type == "error":
        return jsonify(_fault_injector.inject_error(float(data.get("error_rate", 0.1)), int(data.get("error_code", 500))))
    elif fault_type == "cpu_stress":
        return jsonify(_fault_injector.inject_cpu_stress(int(data.get("load", 80)), int(data.get("duration", 60))))
    elif fault_type == "network_partition":
        return jsonify(_fault_injector.inject_network_partition(data.get("target", "database")))
    return jsonify({"status": "error", "error": "未知故障类型"})


@bp.route("/blast-radius/limit", methods=["POST"])
def blast_set():
    data = request.get_json(silent=True) or {}
    _blast.set_limit(data.get("target", ""), float(data.get("max_percent", 5.0)),
                     int(data.get("max_count", 10)))
    return jsonify({"status": "ok"})


@bp.route("/blast-radius/check", methods=["POST"])
def blast_check():
    data = request.get_json(silent=True) or {}
    return jsonify(_blast.check(data.get("target", ""), int(data.get("total", 0)), int(data.get("affected", 0))))


@bp.route("/blast-radius/limits", methods=["GET"])
def blast_limits():
    return jsonify({"limits": _blast.get_limits()})


@bp.route("/steady-state/add", methods=["POST"])
def steady_add():
    data = request.get_json(silent=True) or {}
    _steady.add(data.get("name", ""), data.get("metric", ""),
                data.get("operator", "<"), float(data.get("threshold", 0)))
    return jsonify({"status": "ok"})


@bp.route("/steady-state/validate", methods=["POST"])
def steady_validate():
    data = request.get_json(silent=True) or {}
    return jsonify(_steady.validate(data.get("name", ""), float(data.get("value", 0))))


@bp.route("/steady-state/list", methods=["GET"])
def steady_list():
    return jsonify({"hypotheses": _steady.list_all()})


@bp.route("/capacity/assess", methods=["POST"])
def cap_assess():
    data = request.get_json(silent=True) or {}
    return jsonify(_capacity.assess(
        int(data.get("current_load", 0)),
        int(data.get("max_capacity", 0)),
        float(data.get("growth_rate", 0.1)),
        int(data.get("days_ahead", 30))))


@bp.route("/capacity/plan", methods=["POST"])
def cap_plan():
    data = request.get_json(silent=True) or {}
    return jsonify(_planner.plan(data.get("usage", {}), float(data.get("growth", 0.2)),
                                 float(data.get("margin", 0.2))))


@bp.route("/capacity/forecast", methods=["POST"])
def cap_forecast():
    data = request.get_json(silent=True) or {}
    return jsonify(_forecaster.forecast(
        data.get("historical", []), int(data.get("periods", 7)),
        data.get("method", "moving_avg")))


@bp.route("/autoscaler/policy", methods=["POST"])
def scaler_policy():
    data = request.get_json(silent=True) or {}
    _scaler.set_policy(data.get("name", ""), int(data.get("min", 1)), int(data.get("max", 10)),
                       float(data.get("scale_up", 70)), float(data.get("scale_down", 30)),
                       int(data.get("cooldown", 300)))
    return jsonify({"status": "ok"})


@bp.route("/autoscaler/decide", methods=["POST"])
def scaler_decide():
    data = request.get_json(silent=True) or {}
    return jsonify(_scaler.decide(data.get("name", ""), int(data.get("current", 1)), float(data.get("load", 0))))


@bp.route("/autoscaler/policies", methods=["GET"])
def scaler_policies():
    return jsonify({"policies": _scaler.list_policies()})


@bp.route("/capacity-alert/threshold", methods=["POST"])
def alert_threshold():
    data = request.get_json(silent=True) or {}
    _capacity_alert.set_threshold(data.get("metric", ""), float(data.get("threshold", 0)))
    return jsonify({"status": "ok"})


@bp.route("/capacity-alert/check", methods=["POST"])
def alert_check():
    data = request.get_json(silent=True) or {}
    return jsonify(_capacity_alert.check(data.get("metric", ""), float(data.get("value", 0))))


@bp.route("/capacity-alert/list", methods=["GET"])
def alert_list():
    return jsonify({"alerts": _capacity_alert.get_alerts()})


@bp.route("/report/<experiment>", methods=["GET"])
def chaos_report(experiment: str):
    return jsonify(_chaos_reporter.generate(experiment, _chaos, _steady))
