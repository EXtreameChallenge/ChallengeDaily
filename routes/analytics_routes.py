"""P61-P69: 数据与分析 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import data_analytics

bp = Blueprint('analytics_routes', __name__)


@bp.route("/api/analytics/indexes")
def analytics_indexes():
    """P61: 索引分析与优化建议"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(data_analytics.analyze_indexes())


@bp.route("/api/analytics/indexes/apply", methods=["POST"])
def analytics_apply_indexes():
    """P61: 应用索引优化"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(data_analytics.apply_index_suggestions())


@bp.route("/api/analytics/aggregates")
def analytics_aggregates():
    """P62: 聚合预计算"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    period = request.args.get("period", "day")
    days = int(request.args.get("days", "30"))
    return jsonify(data_analytics.precompute_aggregates(period, days))


@bp.route("/api/analytics/integrity")
def analytics_integrity():
    """P64: 数据完整性校验"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(data_analytics.check_data_integrity())


@bp.route("/api/analytics/integrity/repair", methods=["POST"])
def analytics_repair():
    """P64: 修复数据完整性"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    dry_run = request.args.get("dry_run", "1") != "0"
    return jsonify(data_analytics.repair_data_integrity(dry_run))


@bp.route("/api/analytics/export")
def analytics_export():
    """P65: 数据导出"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    fmt = request.args.get("format", "json")
    table = request.args.get("table", "activities")
    start = request.args.get("start_date")
    end = request.args.get("end_date")
    return jsonify(data_analytics.export_data(fmt, table, start, end))


@bp.route("/api/analytics/anomalies")
def analytics_anomalies():
    """P66: 异常检测"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    days = int(request.args.get("days", "7"))
    return jsonify(data_analytics.detect_anomalies(days))


@bp.route("/api/analytics/archive", methods=["POST"])
def analytics_archive():
    """P67: 老旧数据归档"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    days = int(request.args.get("days", "180"))
    return jsonify(data_analytics.archive_old_data(days))


@bp.route("/api/analytics/extended-metrics")
def analytics_extended():
    """P68: 扩展统计指标"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    days = int(request.args.get("days", "7"))
    return jsonify(data_analytics.compute_extended_metrics(days))


@bp.route("/api/analytics/trend")
def analytics_trend():
    """P69: 趋势可视化数据"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    metric = request.args.get("metric", "duration")
    days = int(request.args.get("days", "30"))
    return jsonify(data_analytics.get_trend_data(metric, days))


@bp.route("/api/analytics/cache/invalidate", methods=["POST"])
def analytics_cache_invalidate():
    """缓存失效"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    prefix = request.args.get("prefix", "")
    n = data_analytics.cache_invalidate(prefix)
    return jsonify({"status": "ok", "invalidated": n})
