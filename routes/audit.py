"""P11-3：审计日志 API
提供审计日志查询和统计接口，供前端审计页面展示。
"""
import logging
from flask import Blueprint, jsonify, request

import routes.deps as deps

logger = logging.getLogger(__name__)
bp = Blueprint('audit', __name__, url_prefix='/api/audit')


@bp.route('/logs', methods=['GET'])
def query_logs():
    """查询审计日志
    query: category=ai_vision&status=failure&limit=100&offset=0
    """
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from audit_logger import query_audit_logs
        category = request.args.get('category', '').strip() or None
        status = request.args.get('status', '').strip() or None
        try:
            limit = int(request.args.get('limit', '100'))
            offset = int(request.args.get('offset', '0'))
        except ValueError:
            limit, offset = 100, 0
        logs = query_audit_logs(category=category, status=status, limit=limit, offset=offset)
        return jsonify({"logs": logs, "count": len(logs)})
    except Exception as e:
        logger.error(f"查询审计日志失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/stats', methods=['GET'])
def get_stats():
    """获取审计统计"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from audit_logger import get_audit_stats
        stats = get_audit_stats()
        return jsonify({"stats": stats})
    except Exception as e:
        logger.error(f"获取审计统计失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/cleanup', methods=['POST'])
def cleanup():
    """清理过期审计日志"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        from audit_logger import cleanup_old_audit_logs
        deleted = cleanup_old_audit_logs()
        return jsonify({"status": "ok", "deleted": deleted})
    except Exception as e:
        logger.error(f"清理审计日志失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500
