"""P18-1: 外部日历集成 API 路由"""
import logging
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import calendar_sync

logger = logging.getLogger(__name__)
bp = Blueprint('calendar', __name__)


@bp.route("/api/calendar/subscriptions", methods=["GET"])
def list_subs():
    """列出所有日历订阅"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify({"subscriptions": calendar_sync.list_subscriptions()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/calendar/subscriptions", methods=["POST"])
def add_sub():
    """添加日历订阅（ICS URL）"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        url = (data.get("url") or "").strip()
        name = (data.get("name") or "").strip()
        color = (data.get("color") or "#4A90E2").strip()
        if not url or not name:
            return jsonify({"error": "缺少 url 或 name"}), 400
        sub = calendar_sync.add_subscription(name=name, url=url, color=color)
        return jsonify({"subscription": sub}), 201
    except Exception as e:
        logger.error(f"添加日历订阅失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/api/calendar/subscriptions/<sub_id>", methods=["PUT"])
def update_sub(sub_id: str):
    """更新日历订阅属性"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        updated = calendar_sync.update_subscription(sub_id, **data)
        if not updated:
            return jsonify({"error": "订阅不存在"}), 404
        return jsonify({"subscription": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/calendar/subscriptions/<sub_id>", methods=["DELETE"])
def remove_sub(sub_id: str):
    """删除日历订阅"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        ok = calendar_sync.remove_subscription(sub_id)
        if not ok:
            return jsonify({"error": "订阅不存在"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/calendar/refresh", methods=["POST"])
def refresh_all():
    """强制刷新所有订阅"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        result = calendar_sync.refresh_all(force=True)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/calendar/today")
def today_events():
    """获取今日所有会议事件"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify({"events": calendar_sync.get_today_events()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/calendar/upcoming")
def upcoming_events():
    """获取未来 N 小时内的会议事件（默认 24 小时）"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        hours = request.args.get("hours", "24", type=int)
        hours = max(1, min(hours, 168))  # 1-168 小时
        return jsonify({"events": calendar_sync.get_upcoming_events(hours)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/calendar/current-meeting")
def current_meeting():
    """获取当前正在进行的会议"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        meeting = calendar_sync.get_current_meeting()
        return jsonify({"meeting": meeting, "in_meeting": meeting is not None})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
