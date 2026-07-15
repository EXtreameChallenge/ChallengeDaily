"""P7-1: AI 行为教练 API 路由"""
from flask import Blueprint, jsonify
import realtime_coach

bp = Blueprint('coach', __name__)


@bp.route("/api/coach/status")
def coach_status():
    """获取当前行为教练状态（前端 30s 轮询）"""
    try:
        status = realtime_coach.get_coaching_status()
        # 自动推送告警到通知系统
        for alert in status.get("alerts", []):
            realtime_coach.trigger_alert_notification(alert)
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e), "alerts": [], "distraction_minutes": 0, "work_minutes": 0}), 500


@bp.route("/api/coach/daily-summary")
def coach_daily_summary():
    """今日行为教练汇总"""
    try:
        return jsonify(realtime_coach.get_daily_coaching_summary())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
