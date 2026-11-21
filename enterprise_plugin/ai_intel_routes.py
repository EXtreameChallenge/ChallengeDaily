"""P71-P79: AI 智能 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import ai_intelligence

bp = Blueprint('ai_intel_routes', __name__)


@bp.route("/api/ai-intel/templates")
def ai_templates():
    """P71: 列出提示词模板"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"templates": list(ai_intelligence._PROMPT_TEMPLATES.keys())})


@bp.route("/api/ai-intel/cache/stats")
def ai_cache_stats():
    """P72: AI 缓存统计"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(ai_intelligence.ai_cache_stats())


@bp.route("/api/ai-intel/model-ranking")
def ai_model_ranking():
    """P74: 模型质量排名"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"ranking": ai_intelligence.get_model_ranking()})


@bp.route("/api/ai-intel/budget")
def ai_budget():
    """P78: 预算查询"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(ai_intelligence.check_budget())


@bp.route("/api/ai-intel/budget/history")
def ai_budget_history():
    """P78: 用量历史"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    days = int(request.args.get("days", "7"))
    return jsonify({"history": ai_intelligence.get_usage_history(days)})


@bp.route("/api/ai-intel/budget", methods=["POST"])
def ai_set_budget():
    """P78: 设置预算"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    budget = int(data.get("budget", 200000))
    ai_intelligence.set_daily_budget(budget)
    return jsonify({"status": "ok", "budget": budget})


@bp.route("/api/ai-intel/questions/recommend")
def ai_questions_recommend():
    """P79: 推荐问题"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    ctx = request.args.get("context", "")
    limit = int(request.args.get("limit", "5"))
    return jsonify({"questions": ai_intelligence.recommend_questions(ctx, limit)})


@bp.route("/api/ai-intel/questions/feedback", methods=["POST"])
def ai_questions_feedback():
    """P79: 记录问答反馈"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    ai_intelligence.record_qa(
        data.get("question", ""),
        data.get("answer", ""),
        int(data.get("feedback", 0))
    )
    return jsonify({"status": "ok"})
