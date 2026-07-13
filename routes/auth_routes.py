"""鉴权相关 API"""
from flask import Blueprint, jsonify, request
import routes.deps as deps
import secrets
import logging

logger = logging.getLogger(__name__)
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.route('/revoke', methods=['POST'])
def revoke_token():
    """撤销当前 token 并生成新 token（强制所有客户端重新鉴权）"""
    # 生成新 token
    deps.LOCAL_TOKEN = secrets.token_hex(16)
    deps._TOKEN_CREATED_AT = __import__('time').time()
    deps._save_token_impl()
    logger.info(f"[AUDIT] Token revoked by {request.remote_addr}")
    return jsonify({"status": "revoked", "message": "新 token 已生成，请通过客户端获取"})


@auth_bp.route('/status', methods=['GET'])
def token_status():
    """查询当前 token 状态（不返回 token 本身）"""
    import time
    age_sec = time.time() - deps._TOKEN_CREATED_AT
    remaining_sec = max(0, deps._TOKEN_MAX_AGE_SEC - age_sec)
    return jsonify({
        "created_at": deps._TOKEN_CREATED_AT,
        "age_days": round(age_sec / 86400, 1),
        "remaining_days": round(remaining_sec / 86400, 1),
        "expires_in_sec": remaining_sec,
    })
