"""P351-P360: 功能开关+灰度发布路由"""
from flask import Blueprint, request, jsonify
from feature_flags_adv import (
    _flag_mgr, _evaluator, _targeting, _rollout, _dependency,
    _audit, _timeline, _kill, FlagTemplate, _broadcaster,
)

bp = Blueprint("flags_adv", __name__, url_prefix="/api/flags-adv")


@bp.route("/flags", methods=["GET"])
def flags_list():
    return jsonify({"flags": _flag_mgr.list_all()})


@bp.route("/flags", methods=["POST"])
def flags_create():
    data = request.get_json(silent=True) or {}
    return jsonify(_flag_mgr.create(
        data.get("name", ""), data.get("enabled", False),
        data.get("description", ""), data.get("owner", "")))


@bp.route("/flags/<name>", methods=["GET"])
def flags_get(name: str):
    result = _flag_mgr.get(name)
    return jsonify(result) if result else (jsonify({"error": "未找到"}), 404)


@bp.route("/flags/<name>/toggle", methods=["POST"])
def flags_toggle(name: str):
    data = request.get_json(silent=True) or {}
    enabled = data.get("enabled", False)
    result = _flag_mgr.toggle(name, enabled)
    _audit.log(name, "toggle", data.get("actor", ""), not enabled, enabled)
    _timeline.record(name, "toggle", {"enabled": enabled})
    _broadcaster.broadcast("flag_toggled", {"flag": name, "enabled": enabled})
    return jsonify(result)


@bp.route("/flags/<name>/percentage", methods=["POST"])
def flags_percentage(name: str):
    data = request.get_json(silent=True) or {}
    return jsonify(_flag_mgr.set_percentage(name, float(data.get("percentage", 0))))


@bp.route("/flags/<name>/rules", methods=["POST"])
def flags_rules(name: str):
    data = request.get_json(silent=True) or {}
    return jsonify(_flag_mgr.add_rule(name, data.get("rule", {})))


@bp.route("/evaluate/<name>", methods=["POST"])
def flags_evaluate(name: str):
    data = request.get_json(silent=True) or {}
    return jsonify(_evaluator.evaluate(
        name, data.get("user_id", ""), data.get("attributes", {})))


@bp.route("/targeting/segments", methods=["POST"])
def targeting_create():
    data = request.get_json(silent=True) or {}
    _targeting.create_segment(data.get("name", ""), data.get("criteria", {}))
    return jsonify({"status": "ok"})


@bp.route("/targeting/segments", methods=["GET"])
def targeting_list():
    return jsonify({"segments": _targeting.list_segments()})


@bp.route("/targeting/match", methods=["POST"])
def targeting_match():
    data = request.get_json(silent=True) or {}
    return jsonify({"matches": _targeting.match_user(
        data.get("user_id", ""), data.get("attributes", {}))})


@bp.route("/rollout/plan", methods=["POST"])
def rollout_create():
    data = request.get_json(silent=True) or {}
    return jsonify(_rollout.create_plan(data.get("flag", ""), data.get("stages", [])))


@bp.route("/rollout/<flag>/advance", methods=["POST"])
def rollout_advance(flag: str):
    return jsonify(_rollout.advance(flag))


@bp.route("/rollout/<flag>", methods=["GET"])
def rollout_get(flag: str):
    result = _rollout.get_plan(flag)
    return jsonify(result) if result else (jsonify({"error": "无计划"}), 404)


@bp.route("/dependency", methods=["POST"])
def dependency_add():
    data = request.get_json(silent=True) or {}
    return jsonify(_dependency.add(data.get("flag", ""), data.get("depends_on", "")))


@bp.route("/dependency/<flag>/check", methods=["POST"])
def dependency_check(flag: str):
    data = request.get_json(silent=True) or {}
    return jsonify(_dependency.check(flag, data.get("states", {})))


@bp.route("/audit", methods=["GET"])
def audit_list():
    flag = request.args.get("flag")
    return jsonify({"logs": _audit.get_logs(flag)})


@bp.route("/timeline/<flag>", methods=["GET"])
def timeline_get(flag: str):
    return jsonify({"timeline": _timeline.get_timeline(flag)})


@bp.route("/kill-switch/register", methods=["POST"])
def kill_register():
    data = request.get_json(silent=True) or {}
    _kill.register(data.get("name", ""))
    return jsonify({"status": "ok"})


@bp.route("/kill-switch/<name>/activate", methods=["POST"])
def kill_activate(name: str):
    data = request.get_json(silent=True) or {}
    return jsonify(_kill.activate(name, data.get("actor", "system")))


@bp.route("/kill-switch/all", methods=["POST"])
def kill_all():
    data = request.get_json(silent=True) or {}
    return jsonify(_kill.activate_all(data.get("actor", "system")))


@bp.route("/templates", methods=["GET"])
def templates_list():
    return jsonify({"templates": FlagTemplate.list_templates()})


@bp.route("/templates/<template>/create", methods=["POST"])
def templates_create(template: str):
    data = request.get_json(silent=True) or {}
    return jsonify(FlagTemplate.create_from_template(_flag_mgr, data.get("name", ""), template))


@bp.route("/broadcast/log", methods=["GET"])
def broadcast_log():
    return jsonify({"log": _broadcaster.get_broadcast_log()})
