"""隐私合规 API（PIPL 被遗忘权 + P17 截图加密管理）"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import logging
import db

logger = logging.getLogger(__name__)
privacy_bp = Blueprint('privacy', __name__, url_prefix='/api/privacy')


@privacy_bp.route('/data', methods=['DELETE'])
def delete_all_user_data():
    """删除所有用户数据（被遗忘权）"""
    try:
        tables_to_clear = [
            'activities', 'app_usage', 'screenshots', 'reports',
            'todos', 'habits', 'habit_logs', 'diaries', 'week_plans',
            'countdowns', 'pomodoro_sessions', 'notifications',
            'app_tags', 'deep_insight_cache', 'ai_chat_history'
        ]
        with db.get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for table in tables_to_clear:
                try:
                    conn.execute(f"DELETE FROM {table}")
                except Exception as e:
                    logger.warning(f"清空 {table} 失败: {e}")
            conn.execute("COMMIT")
        logger.info(f"[AUDIT] User data deleted by {request.remote_addr}")
        return jsonify({"status": "deleted", "message": "所有用户数据已删除"})
    except Exception as e:
        logger.error(f"删除用户数据失败: {e}", exc_info=True)
        return jsonify({"error": "删除失败"}), 500


@privacy_bp.route('/export', methods=['GET'])
def export_all_user_data():
    """导出所有用户数据（数据可携带权）"""
    try:
        import json
        data = {}
        tables = ['activities', 'app_usage', 'reports', 'todos', 'habits', 'diaries']
        with db.get_conn() as conn:
            for table in tables:
                try:
                    rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                    cols = [d[0] for d in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
                    data[table] = [dict(zip(cols, row)) for row in rows]
                except Exception:
                    data[table] = []
        logger.info(f"[AUDIT] Data export by {request.remote_addr}")
        from flask import Response
        return Response(
            json.dumps(data, ensure_ascii=False, default=str, indent=2),
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename="user_data.json"'}
        )
    except Exception as e:
        logger.error(f"导出数据失败: {e}", exc_info=True)
        return jsonify({"error": "导出失败"}), 500


@privacy_bp.route('/retention', methods=['GET', 'PUT'])
def retention_policy():
    """查询/设置数据保留天数"""
    if request.method == 'GET':
        days = db.get_retention_days()
        return jsonify({"retention_days": days})
    else:
        data = request.get_json(silent=True) or {}
        days = data.get('days', 90)
        if not isinstance(days, int) or days < 1 or days > 3650:
            return jsonify({"error": "days 必须是 1-3650 的整数"}), 400
        with db.get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('data_retention_days', ?)", (str(days),))
        logger.info(f"[AUDIT] Retention set to {days} days by {request.remote_addr}")
        return jsonify({"status": "updated", "retention_days": days})


# ── P17-1: 截图加密管理 ──

@privacy_bp.route('/screenshot-encryption/status', methods=['GET'])
def screenshot_encryption_status():
    """查询截图加密状态"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        import screenshot_crypto
        from config import SCREENSHOT_DIR

        available = screenshot_crypto.is_encryption_available()
        total = 0
        encrypted = 0
        if SCREENSHOT_DIR.exists():
            for f in SCREENSHOT_DIR.iterdir():
                if not f.is_file() or not f.name.lower().endswith('.jpg'):
                    continue
                total += 1
                if screenshot_crypto.is_encrypted_file(str(f)):
                    encrypted += 1

        return jsonify({
            "available": available,
            "total_screenshots": total,
            "encrypted_screenshots": encrypted,
            "unencrypted_screenshots": total - encrypted,
            "coverage": round(encrypted / total * 100, 1) if total > 0 else 0,
        })
    except Exception as e:
        logger.error(f"查询加密状态失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@privacy_bp.route('/screenshot-encryption/migrate', methods=['POST'])
def screenshot_encryption_migrate():
    """批量加密已有截图"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        import screenshot_crypto
        result = screenshot_crypto.migrate_existing_screenshots()
        if result.get("failed") == -1:
            return jsonify({"error": "加密功能不可用（cryptography 库未安装）"}), 400
        logger.info(f"[AUDIT] Screenshot encryption migrate: {result} by {request.remote_addr}")
        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        logger.error(f"截图加密迁移失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
