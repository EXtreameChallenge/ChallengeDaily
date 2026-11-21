"""P211-P219: 多端跨平台支持 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import cross_platform as cp

bp = Blueprint('cross_platform', __name__)


@bp.route("/api/platform/detect")
def platform_detect():
    ua = request.headers.get("User-Agent", "")
    return jsonify(cp._platform.detect(ua))


@bp.route("/api/platform/capabilities")
def platform_capabilities():
    ua = request.headers.get("User-Agent", "")
    platform = cp._platform.detect(ua)
    return jsonify(cp._platform.get_capabilities(platform))


@bp.route("/api/platform/responsive")
def responsive_layout():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    width = int(request.args.get("width", 1920))
    layout_id = request.args.get("layout", "default")
    if layout_id not in cp._responsive._layouts:
        cp._responsive.configure(layout_id)
    return jsonify(cp._responsive.get_layout(layout_id, width))


@bp.route("/api/platform/breakpoints")
def responsive_breakpoints():
    return jsonify({"breakpoints": cp._responsive.list_breakpoints()})


@bp.route("/api/platform/shortcuts")
def shortcuts_list():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"shortcuts": cp._keyboard.list_shortcuts()})


@bp.route("/api/platform/shortcuts/register", methods=["POST"])
def shortcuts_register():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    def noop(ctx=None):
        return {"ok": True}
    cp._keyboard.register(
        data.get("combo", ""), noop,
        data.get("description", ""), data.get("scope", "global")
    )
    return jsonify({"status": "ok"})


@bp.route("/api/platform/clipboard")
def clipboard_recent():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"items": cp._clipboard.get_recent()})


@bp.route("/api/platform/clipboard/push", methods=["POST"])
def clipboard_push():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    cp._clipboard.push(data.get("content", ""), data.get("type", "text"))
    return jsonify({"status": "ok"})


@bp.route("/api/platform/notifications")
def notifications_list():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"notifications": cp._notifier.get_all()})


@bp.route("/api/platform/notify", methods=["POST"])
def notify():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    notif = cp._notifier.notify(
        data.get("title", ""), data.get("body", ""),
        data.get("priority", "normal"), data.get("category", "default")
    )
    return jsonify(notif)


@bp.route("/api/platform/theme")
def theme_get():
    return jsonify({"theme": cp._theme_sync.get_theme(), "auto_sync": cp._theme_sync._auto_sync})


@bp.route("/api/platform/theme/set", methods=["POST"])
def theme_set():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    cp._theme_sync.set_theme(data.get("theme", "light"))
    return jsonify({"status": "ok"})


@bp.route("/api/platform/device-capabilities")
def device_capabilities():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"capabilities": cp._device_cap.get_all()})
