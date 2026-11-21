"""P141-P149: 智能个性化 API"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import smart_personal as sp

bp = Blueprint('smart_routes', __name__)


@bp.route("/api/smart/profile")
def smart_profile():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(sp.get_user_profile().get_profile())


@bp.route("/api/smart/profile/traits", methods=["POST"])
def smart_update_trait():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    sp.get_user_profile().update_trait(data.get("name", ""), float(data.get("value", 0)), float(data.get("weight", 0.1)))
    return jsonify({"status": "ok"})


@bp.route("/api/smart/recommendations")
def smart_recommendations():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    ctx = request.args.to_dict()
    return jsonify({"recommendations": sp._rec_engine.recommend(ctx)})


@bp.route("/api/smart/recommendations/feedback", methods=["POST"])
def smart_rec_feedback():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    sp._rec_engine.feedback(data.get("rule", ""), data.get("positive", True))
    return jsonify({"status": "ok"})


@bp.route("/api/smart/learning-curve/<skill>")
def smart_learning_curve(skill):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({
        "skill": skill,
        "curve": sp._learning_curve.get_curve(skill),
        "predicted_next": sp._learning_curve.predict_next(skill)
    })


@bp.route("/api/smart/reminders/pending")
def smart_reminders_pending():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"reminders": sp._reminder.pending()})


@bp.route("/api/smart/reminders", methods=["POST"])
def smart_schedule_reminder():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    rid = sp._reminder.schedule(data.get("type", ""), data.get("message", ""))
    return jsonify({"id": rid})


@bp.route("/api/smart/work-style")
def smart_work_style():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(sp.analyze_work_style([]))


@bp.route("/api/smart/predict-efficiency")
def smart_predict_efficiency():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(sp.predict_efficiency([]))


@bp.route("/api/smart/context")
def smart_context():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(sp._context.snapshot())


@bp.route("/api/smart/optimize", methods=["POST"])
def smart_optimize():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    return jsonify({"suggestions": sp.multi_objective_optimize(data)})
