"""P0-2：我的资料（用户画像）API

GET  /api/user/profile  获取用户画像
POST /api/user/profile  保存用户画像
"""
import logging

from flask import Blueprint, jsonify, request

import routes.deps as deps
from user_profile import get_profile, save_profile, init_table

logger = logging.getLogger(__name__)

bp = Blueprint('user_profile', __name__, url_prefix='/api/user')

# 模块加载时确保表存在（幂等）
try:
    init_table()
except Exception as e:
    logger.warning(f"user_profile 初始化表失败: {e}")


@bp.route('/profile', methods=['GET'])
def get_user_profile():
    """获取用户画像"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        profile = get_profile()
        return jsonify({"profile": profile})
    except Exception as e:
        logger.error(f"获取用户画像失败: {e}", exc_info=True)
        return jsonify({"error": deps.safe_error(e, "获取用户画像失败")}), 500


@bp.route('/profile', methods=['POST'])
def post_user_profile():
    """保存用户画像"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        profile = save_profile(data)
        return jsonify({"status": "ok", "profile": profile})
    except Exception as e:
        logger.error(f"保存用户画像失败: {e}", exc_info=True)
        return jsonify({"error": deps.safe_error(e, "保存用户画像失败")}), 500
