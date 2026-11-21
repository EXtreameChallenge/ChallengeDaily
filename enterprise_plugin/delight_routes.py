"""P101-P109: 打磨与愉悦感 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import delight_polish

bp = Blueprint('delight_routes', __name__)


@bp.route("/api/delight/interactions")
def delight_interactions():
    """P101: 微交互动画"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"interactions": delight_polish.get_micro_interactions()})


@bp.route("/api/delight/celebration")
def delight_celebration():
    """P102: 庆祝效果"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    scene = request.args.get("scene", "confetti")
    return jsonify(delight_polish.get_celebration(scene))


@bp.route("/api/delight/celebration/trigger", methods=["POST"])
def delight_trigger_celebration():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    return jsonify(delight_polish.trigger_cebration(
        data.get("scene", "confetti"),
        data.get("reason", "")
    ))


@bp.route("/api/delight/greeting")
def delight_greeting():
    """P103: 问候语"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    hour = request.args.get("hour")
    hour = int(hour) if hour else None
    return jsonify({
        "greeting": delight_polish.get_greeting_by_hour(hour),
        "hour": hour if hour is not None else None
    })


@bp.route("/api/delight/badges/<tier>")
def delight_badge(tier):
    """P104: 徽章视觉"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(delight_polish.get_badge_style(tier))


@bp.route("/api/delight/badges")
def delight_badge_tiers():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"tiers": delight_polish.get_all_badge_tiers()})


@bp.route("/api/delight/emotions")
def delight_emotions():
    """P105: 情感色彩"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    emotion = request.args.get("emotion")
    if emotion:
        return jsonify(delight_polish.get_emotion_color(emotion))
    return jsonify({"emotions": delight_polish.get_all_emotions()})


@bp.route("/api/delight/sounds")
def delight_sounds():
    """P106: 声音反馈"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"sounds": delight_polish.get_sound_effects()})


@bp.route("/api/delight/emojis")
def delight_emojis():
    """P107: 表情符号"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    category = request.args.get("category", "")
    return jsonify({"emojis": delight_polish.get_emojis(category)})


@bp.route("/api/delight/quote")
def delight_quote():
    """P108: 励志名言"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    category = request.args.get("category", "")
    return jsonify(delight_polish.get_quote(category))


@bp.route("/api/delight/quotes/categories")
def delight_quote_categories():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"categories": delight_polish.get_quote_categories()})


@bp.route("/api/delight/diary-templates")
def delight_diary_templates():
    """P109: 日记模板"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"templates": delight_polish.get_diary_templates()})
