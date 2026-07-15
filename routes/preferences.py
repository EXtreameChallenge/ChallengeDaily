"""P11-2：用户个性化偏好 API
存储用户的报告风格、欢迎语开关、个性化昵称等偏好到 user_preferences 表。
"""
import json
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request

import routes.deps as deps
import db

logger = logging.getLogger(__name__)
bp = Blueprint('preferences', __name__, url_prefix='/api/preferences')


# 默认偏好
DEFAULT_PREFS = {
    "nickname": "",                  # 昵称（用于个性化欢迎语）
    "greeting_enabled": True,        # 是否启用 AI 欢迎语
    "report_style": "balanced",      # 报告风格: concise(简洁) / balanced(均衡) / detailed(详尽)
    "encouragement_level": "warm",   # 鼓励强度: subtle(含蓄) / warm(温暖) / energetic(活泼)
    "disclosure_level": "beginner",  # 功能揭示级别: beginner(新手) / intermediate(进阶) / expert(专家)
    "tooltip_enabled": True,         # 是否显示教育 tooltip
}


def _get_pref(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM user_preferences WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return row["value"]


def _set_pref(conn, key: str, value) -> None:
    val_str = json.dumps(value, ensure_ascii=False)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO user_preferences (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=?, updated_at=?",
        (key, val_str, ts, val_str, ts),
    )
    conn.commit()


@bp.route('', methods=['GET'])
def get_preferences():
    """获取全部用户偏好（合并默认值）"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        with db.get_conn() as conn:
            result = dict(DEFAULT_PREFS)
            for k in DEFAULT_PREFS.keys():
                v = _get_pref(conn, k)
                if v is not None:
                    result[k] = v
        return jsonify({"preferences": result})
    except Exception as e:
        logger.error(f"获取偏好失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('', methods=['POST'])
def update_preferences():
    """批量更新用户偏好"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({"error": "Empty body"}), 400

    # 字段白名单 + 类型校验
    ALLOWED = {
        "nickname": str,
        "greeting_enabled": bool,
        "report_style": str,
        "encouragement_level": str,
        "disclosure_level": str,
        "tooltip_enabled": bool,
    }
    ENUM_CHECK = {
        "report_style": {"concise", "balanced", "detailed"},
        "encouragement_level": {"subtle", "warm", "energetic"},
        "disclosure_level": {"beginner", "intermediate", "expert"},
    }
    MAX_LEN = {"nickname": 30}

    cleaned = {}
    for k, v in data.items():
        if k not in ALLOWED:
            continue
        if not isinstance(v, ALLOWED[k]):
            # 兼容 bool 字段从前端传来的字符串
            if ALLOWED[k] is bool and isinstance(v, str):
                v = v.lower() in ("true", "1", "yes")
            else:
                return jsonify({"error": f"字段 {k} 类型错误"}), 400
        if k in ENUM_CHECK and v not in ENUM_CHECK[k]:
            return jsonify({"error": f"字段 {k} 取值非法"}), 400
        if k in MAX_LEN and isinstance(v, str) and len(v) > MAX_LEN[k]:
            return jsonify({"error": f"字段 {k} 长度超过限制（最大 {MAX_LEN[k]} 字符）"}), 400
        cleaned[k] = v

    try:
        with db.get_conn() as conn:
            for k, v in cleaned.items():
                _set_pref(conn, k, v)
        return jsonify({"status": "ok", "updated": list(cleaned.keys())})
    except Exception as e:
        logger.error(f"更新偏好失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/reset', methods=['POST'])
def reset_preferences():
    """重置偏好为默认值"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        with db.get_conn() as conn:
            conn.execute("DELETE FROM user_preferences")
            for k, v in DEFAULT_PREFS.items():
                _set_pref(conn, k, v)
        return jsonify({"status": "ok", "preferences": DEFAULT_PREFS})
    except Exception as e:
        logger.error(f"重置偏好失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500
