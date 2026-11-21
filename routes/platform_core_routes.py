"""剪贴板核心端点：不属于企业仿真插件，始终注册。

P95 的剪贴板历史是真实本地功能（B36 已做 PII 脱敏），
其余 P91-P99 平台仿真端点已移入 enterprise_plugin，默认不注册。
"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import platform_integration

bp = Blueprint('platform_core_routes', __name__)


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
