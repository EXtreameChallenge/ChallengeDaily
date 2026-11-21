"""P301-P310: 无障碍路由"""
from flask import Blueprint, request, jsonify
from accessibility import (
    _wcag, _aria, _keyboard_nav, _contrast, _focus_mgr,
    _text_scaler, _anim_reducer, _voice_nav, GestureAlternative, _cognitive,
)

bp = Blueprint("accessibility", __name__, url_prefix="/api/a11y")


@bp.route("/wcag/check", methods=["POST"])
def wcag_check():
    data = request.get_json(silent=True) or {}
    html = data.get("html", "")
    return jsonify(_wcag.check_html(html))


@bp.route("/wcag/rules", methods=["GET"])
def wcag_rules():
    return jsonify({"rules": _wcag.list_rules()})


@bp.route("/wcag/violations", methods=["GET"])
def wcag_violations():
    return jsonify({"violations": _wcag.get_violations()})


@bp.route("/aria/labels", methods=["GET"])
def aria_list():
    return jsonify({"labels": _aria.list_labels()})


@bp.route("/aria/label", methods=["POST"])
def aria_set():
    data = request.get_json(silent=True) or {}
    _aria.set_label(data.get("element_id", ""), data.get("label", ""),
                    data.get("role", ""), data.get("describedby", ""))
    return jsonify({"status": "ok"})


@bp.route("/aria/generate", methods=["GET"])
def aria_generate():
    eid = request.args.get("element_id", "")
    return jsonify({"aria": _aria.generate_aria(eid)})


@bp.route("/keyboard/tab-order", methods=["POST"])
def kb_tab_order():
    data = request.get_json(silent=True) or {}
    _keyboard_nav.set_tab_order(data.get("elements", []))
    return jsonify({"status": "ok"})


@bp.route("/keyboard/shortcuts", methods=["POST"])
def kb_shortcut():
    data = request.get_json(silent=True) or {}
    _keyboard_nav.register_shortcut(data.get("combo", ""), data.get("action", ""))
    return jsonify({"status": "ok"})


@bp.route("/keyboard/shortcuts", methods=["GET"])
def kb_shortcuts_list():
    return jsonify({"shortcuts": _keyboard_nav.get_shortcuts(),
                    "tab_order": _keyboard_nav.get_tab_order()})


@bp.route("/contrast", methods=["GET"])
def contrast_check():
    fg = request.args.get("fg", "#000000")
    bg = request.args.get("bg", "#ffffff")
    level = request.args.get("level", "AA")
    return jsonify(_contrast.check_compliance(fg, bg, level))


@bp.route("/focus/history", methods=["GET"])
def focus_history():
    return jsonify({"current": _focus_mgr.pop_focus(),
                    "traps": _focus_mgr.get_focus_traps()})


@bp.route("/focus/trap", methods=["POST"])
def focus_trap():
    data = request.get_json(silent=True) or {}
    _focus_mgr.set_focus_trap(data.get("container", ""), data.get("elements", []))
    return jsonify({"status": "ok"})


@bp.route("/text-scale", methods=["GET"])
def text_scale_get():
    return jsonify({"scale": _text_scaler.get_scale(),
                    "levels": _text_scaler.list_levels()})


@bp.route("/text-scale", methods=["POST"])
def text_scale_set():
    data = request.get_json(silent=True) or {}
    action = data.get("action", "set")
    if action == "increase":
        return jsonify(_text_scaler.increase())
    elif action == "decrease":
        return jsonify(_text_scaler.decrease())
    else:
        return jsonify(_text_scaler.set_scale(float(data.get("scale", 1.0))))


@bp.route("/animation", methods=["GET"])
def anim_get():
    return jsonify({"reduced": _anim_reducer.is_enabled(),
                    "css_override": _anim_reducer.get_css_override()})


@bp.route("/animation", methods=["POST"])
def anim_set():
    data = request.get_json(silent=True) or {}
    if data.get("enable"):
        _anim_reducer.enable()
    else:
        _anim_reducer.disable()
    return jsonify({"status": "ok", "reduced": _anim_reducer.is_enabled()})


@bp.route("/voice/commands", methods=["GET"])
def voice_commands():
    return jsonify({"commands": _voice_nav.list_commands()})


@bp.route("/voice/parse", methods=["POST"])
def voice_parse():
    data = request.get_json(silent=True) or {}
    return jsonify(_voice_nav.parse_command(data.get("text", "")))


@bp.route("/voice/history", methods=["GET"])
def voice_history():
    return jsonify({"history": _voice_nav.get_history()})


@bp.route("/gesture/alternatives", methods=["GET"])
def gesture_alts():
    return jsonify({"gestures": GestureAlternative.list_gestures()})


@bp.route("/cognitive/assess", methods=["POST"])
def cognitive_assess():
    data = request.get_json(silent=True) or {}
    return jsonify(_cognitive.assess(data.get("factors", {})))


@bp.route("/cognitive/factors", methods=["GET"])
def cognitive_factors():
    return jsonify({"factors": _cognitive.list_factors()})
