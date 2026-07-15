"""P111-P119: 弹性与可靠性 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import resilience_reliability

bp = Blueprint('resilience_routes', __name__)


@bp.route("/api/resilience/retry-stats")
def resilience_retry_stats():
    """P111: 重试统计"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"stats": resilience_reliability.retry_stats.get()})


@bp.route("/api/resilience/breakers")
def resilience_breakers():
    """P112: 熔断器状态"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"breakers": resilience_reliability.get_all_breakers_status()})


@bp.route("/api/resilience/buckets")
def resilience_buckets():
    """P114: 令牌桶状态"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"buckets": resilience_reliability.get_all_buckets_stats()})


@bp.route("/api/resilience/bulkheads")
def resilience_bulkheads():
    """P115: 舱壁状态"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    stats = {name: b.stats() for name, b in resilience_reliability._BULKHEADS.items()}
    return jsonify({"bulkheads": stats})


@bp.route("/api/resilience/backup", methods=["POST"])
def resilience_backup():
    """P116: 创建备份"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    backup_dir = data.get("backup_dir", "")
    include_screenshots = data.get("include_screenshots", False)
    if not backup_dir:
        return jsonify({"error": "需要 backup_dir 参数"}), 400
    return jsonify(resilience_reliability.create_backup(backup_dir, include_screenshots))


@bp.route("/api/resilience/backups")
def resilience_list_backups():
    """P116: 列出备份"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    backup_dir = request.args.get("backup_dir", "")
    return jsonify({"backups": resilience_reliability.list_backups(backup_dir)})


@bp.route("/api/resilience/restore", methods=["POST"])
def resilience_restore():
    """P116: 恢复备份"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    backup_path = data.get("backup_path", "")
    return jsonify(resilience_reliability.restore_backup(backup_path))


@bp.route("/api/resilience/snapshot")
def resilience_snapshot():
    """P117: 状态快照"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({
        "current": resilience_reliability.take_snapshot(),
        "history": resilience_reliability.get_snapshots()
    })


@bp.route("/api/resilience/fault-inject", methods=["POST"])
def resilience_fault_inject():
    """P118: 故障注入(测试用)"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    fault_type = data.get("type", "delay")
    duration = float(data.get("duration", "0.5"))
    try:
        return jsonify(resilience_reliability.inject_fault(fault_type, duration))
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@bp.route("/api/resilience/healing/check", methods=["POST"])
def resilience_healing_check():
    """P119: 自愈检查"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(resilience_reliability.run_healing_check())


@bp.route("/api/resilience/healing/history")
def resilience_healing_history():
    """P119: 自愈历史"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"history": resilience_reliability.get_healing_history()})
