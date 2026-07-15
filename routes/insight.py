"""
P9-2：AI 主动洞察推送路由
"""
from flask import Blueprint, jsonify, request
from datetime import date
import logging

from morning_insight import generate_morning_insights
from routes.deps import safe_error, check_token

bp = Blueprint('insight', __name__)
logger = logging.getLogger(__name__)


@bp.route("/api/insight/morning")
def morning_insight():
    """获取今日晨报洞察

    GET /api/insight/morning?force=1  强制重新生成
    GET /api/insight/morning         仅在 7-11 点且未推送时生成
    """
    force = request.args.get("force", "0") == "1"
    try:
        insights = generate_morning_insights(force=force)
        return jsonify({
            "date": date.today().isoformat(),
            "insights": insights,
            "count": len(insights),
        })
    except Exception as e:
        return jsonify({"error": safe_error(e, "生成洞察失败")}), 500


@bp.route("/api/insight/morning/check")
def morning_insight_check():
    """检查今日是否已推送晨报（轻量接口，前端可轮询）"""
    from morning_insight import _is_already_pushed
    today = date.today().isoformat()
    return jsonify({
        "date": today,
        "pushed": _is_already_pushed(today),
    })
