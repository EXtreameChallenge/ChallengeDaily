"""用户画像 + 每日画像 + 纠正记录 API"""
import logging

from flask import Blueprint, jsonify, request

from routes.deps import safe_error
import config

logger = logging.getLogger(__name__)

bp = Blueprint('profile', __name__)


@bp.route("/api/profile", methods=["GET"])
def get_profile():
    """获取用户画像"""
    from context_manager import get_user_profile, get_user_corrections
    profile = get_user_profile()
    corrections = get_user_corrections()
    return jsonify({"profile": profile, "corrections": corrections})


@bp.route("/api/profile", methods=["POST"])
def save_profile():
    """保存用户画像"""
    data = request.get_json(force=True) if request.is_json else {}
    if not data:
        return jsonify({"error": "No data provided"}), 400
    from context_manager import save_user_profile
    save_user_profile(data)
    return jsonify({"ok": True})


@bp.route("/api/profile/correction", methods=["POST"])
def add_correction():
    """添加一条分类纠正"""
    data = request.get_json(force=True) if request.is_json else {}
    app_name = data.get("app_name", "")
    if not app_name:
        return jsonify({"error": "app_name is required"}), 400
    from context_manager import add_user_correction
    add_user_correction(
        app_name=app_name,
        correct_category=data.get("correct_category", ""),
        correct_desc=data.get("correct_desc", ""),
        notes=data.get("notes", ""),
    )
    return jsonify({"ok": True})


@bp.route("/api/profile/correction/<int:correction_id>", methods=["DELETE"])
def delete_correction(correction_id):
    """删除一条纠正"""
    from context_manager import delete_user_correction
    delete_user_correction(correction_id)
    return jsonify({"ok": True})


@bp.route("/api/profile/daily/<date_str>")
def get_daily_profile(date_str):
    """获取某天的日画像"""
    from context_manager import get_daily_profile as _get
    profile = _get(date_str)
    if not profile:
        return jsonify({"profile": None})
    return jsonify({"profile": profile})


@bp.route("/api/profile/daily/<date_str>/generate", methods=["POST"])
def generate_daily_profile(date_str):
    """手动触发生成某天的日画像"""
    from context_manager import generate_daily_profile as _gen, save_daily_profile as _save
    profile = _gen(date_str)
    if profile:
        _save(date_str, profile)
        return jsonify({"ok": True, "profile": profile})
    return jsonify({"ok": False, "error": "No data for this date"}), 404


@bp.route("/api/profile/weekly-context")
def get_weekly_context():
    """获取周上下文（供前端调试查看）"""
    days = request.args.get("days", 7, type=int)
    from context_manager import build_weekly_context
    context = build_weekly_context(days)
    return jsonify({"context": context})
