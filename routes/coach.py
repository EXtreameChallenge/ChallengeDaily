"""P7-1: AI 行为教练 API 路由（P16 扩展：生物钟+智能建议+智能休息）"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
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


@bp.route("/api/coach/chronotype")
def coach_chronotype():
    """P16-1: 生物钟检测 + 个性化问候"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        import chronotype
        return jsonify(chronotype.detect_chronotype())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/coach/suggestions")
def coach_suggestions():
    """P16-3: 主动智能建议引擎"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        import smart_suggestions
        suggestions = smart_suggestions.generate_suggestions()
        return jsonify({"status": "ok", "suggestions": suggestions, "count": len(suggestions)})
    except Exception as e:
        return jsonify({"error": str(e), "suggestions": []}), 500
