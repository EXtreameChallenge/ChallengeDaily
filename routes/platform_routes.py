"""P91-P99: 平台与集成 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import platform_integration

bp = Blueprint('platform_routes', __name__)


@bp.route("/api/platform/tray-menu")
def platform_tray_menu():
    """P91: 托盘菜单"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"items": platform_integration.build_tray_menu_items()})


@bp.route("/api/platform/shortcuts")
def platform_shortcuts():
    """P92: 快捷键列表"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({
        "registered": platform_integration.list_shortcuts(),
        "defaults": platform_integration.get_default_shortcuts()
    })


@bp.route("/api/platform/shortcuts", methods=["POST"])
def platform_register_shortcut():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    ok = platform_integration.register_shortcut(
        data.get("accelerator", ""),
        data.get("action", ""),
        data.get("description", "")
    )
    return jsonify({"status": "ok" if ok else "exists", "accelerator": data.get("accelerator")})


@bp.route("/api/platform/notifications")
def platform_notifications():
    """P93: 通知列表"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    unread = request.args.get("unread", "0") == "1"
    limit = int(request.args.get("limit", "50"))
    return jsonify({"notifications": platform_integration.get_notifications(unread, limit)})


@bp.route("/api/platform/notifications", methods=["POST"])
def platform_send_notification():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    notif = platform_integration.send_notification(
        data.get("title", ""),
        data.get("body", ""),
        data.get("level", "info"),
        data.get("action", ""),
        data.get("data")
    )
    return jsonify(notif)


@bp.route("/api/platform/notifications/read", methods=["POST"])
def platform_mark_read():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    notif_id = data.get("id", "")
    if notif_id == "all":
        n = platform_integration.mark_all_read()
        return jsonify({"status": "ok", "marked": n})
    ok = platform_integration.mark_notification_read(notif_id)
    return jsonify({"status": "ok" if ok else "not_found"})


@bp.route("/api/platform/clipboard")
def platform_clipboard():
    """P95: 剪贴板历史"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    limit = int(request.args.get("limit", "20"))
    return jsonify({"items": platform_integration.get_clipboard_history(limit)})


@bp.route("/api/platform/clipboard", methods=["POST"])
def platform_add_clipboard():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    item = platform_integration.add_clipboard_item(
        data.get("content", ""),
        data.get("type", "text")
    )
    return jsonify(item)


@bp.route("/api/platform/clipboard/clear", methods=["POST"])
def platform_clear_clipboard():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    n = platform_integration.clear_clipboard_history()
    return jsonify({"status": "ok", "cleared": n})


@bp.route("/api/platform/windows")
def platform_windows():
    """P96: 窗口状态"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(platform_integration.restore_window_layout())


@bp.route("/api/platform/displays")
def platform_displays():
    """P97: 显示器信息"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(platform_integration.get_display_info())


@bp.route("/api/platform/theme")
def platform_theme():
    """P98: 系统主题"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"theme": platform_integration.detect_system_theme()})


@bp.route("/api/platform/info")
def platform_info():
    """P99: 平台信息"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(platform_integration.get_platform_info())


@bp.route("/api/platform/protocol")
def platform_protocol():
    """P94: 协议处理"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    url = request.args.get("url", "")
    if not url:
        return jsonify({
            "registered": platform_integration.get_registered_protocols()
        })
    return jsonify(platform_integration.handle_protocol(url))
