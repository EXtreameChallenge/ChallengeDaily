"""P191-P199: 可观测性体系 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import observability

bp = Blueprint('observability', __name__)


@bp.route("/api/observability/metrics")
def metrics_export():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(observability._metrics.export())


@bp.route("/api/observability/metrics/counter", methods=["POST"])
def metrics_counter():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    observability._metrics.inc_counter(data.get("name", ""), data.get("value", 1), data.get("tags"))
    return jsonify({"status": "ok"})


@bp.route("/api/observability/metrics/gauge", methods=["POST"])
def metrics_gauge():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    observability._metrics.set_gauge(data.get("name", ""), data.get("value", 0), data.get("tags"))
    return jsonify({"status": "ok"})


@bp.route("/api/observability/metrics/histogram", methods=["POST"])
def metrics_histogram():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    observability._metrics.observe_histogram(data.get("name", ""), data.get("value", 0), data.get("tags"))
    return jsonify({"status": "ok"})


@bp.route("/api/observability/metrics/histogram-stats")
def metrics_histogram_stats():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    name = request.args.get("name", "")
    return jsonify(observability._metrics.get_histogram_stats(name))


@bp.route("/api/observability/traces")
def traces_recent():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    limit = int(request.args.get("limit", 100))
    return jsonify({"spans": observability._tracer.get_recent_spans(limit)})


@bp.route("/api/observability/traces/<trace_id>")
def trace_detail(trace_id):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"spans": observability._tracer.get_trace(trace_id)})


@bp.route("/api/observability/logs")
def logs_search():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"logs": observability._log_agg.search(
        request.args.get("query", ""),
        request.args.get("level", ""),
        request.args.get("source", ""),
        int(request.args.get("limit", 100))
    )})


@bp.route("/api/observability/logs/stats")
def logs_stats():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(observability._log_agg.stats())


@bp.route("/api/observability/health")
def health_check():
    return jsonify(observability._health.run_all())


@bp.route("/api/observability/alerts/rules")
def alert_rules():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"rules": observability._alert_engine.list_rules()})


@bp.route("/api/observability/alerts/rules/add", methods=["POST"])
def alert_rules_add():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    observability._alert_engine.add_rule(
        data.get("name", ""), data.get("metric", ""),
        data.get("condition", ">"), data.get("threshold", 0),
        data.get("severity", "warning")
    )
    return jsonify({"status": "ok"})


@bp.route("/api/observability/alerts/incidents")
def alert_incidents():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"incidents": observability._alert_engine.get_incidents()})


@bp.route("/api/observability/slos")
def slos_list():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"slos": observability._slo_mgr.list_slos()})


@bp.route("/api/observability/slos/evaluate")
def slos_evaluate():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"results": observability._slo_mgr.evaluate_all()})
