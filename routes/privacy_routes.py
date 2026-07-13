"""隐私合规 API（PIPL 被遗忘权）"""
from flask import Blueprint, jsonify, request
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
