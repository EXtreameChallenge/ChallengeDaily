"""P121-P129: 高级数据 API"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import advanced_data

bp = Blueprint('advanced_data_routes', __name__)


@bp.route("/api/advanced/cache/<name>/stats")
def advanced_cache_stats(name):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    cache = advanced_data.get_cache(name)
    return jsonify(cache.stats())


@bp.route("/api/advanced/cache/<name>/clear", methods=["POST"])
def advanced_cache_clear(name):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    advanced_data.get_cache(name).clear()
    return jsonify({"status": "ok"})


@bp.route("/api/advanced/events")
def advanced_events():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    event_type = request.args.get("type", "")
    limit = int(request.args.get("limit", "100"))
    return jsonify({"events": advanced_data.get_event_store().get_events(event_type, limit)})


@bp.route("/api/advanced/events", methods=["POST"])
def advanced_events_append():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    eid = advanced_data.get_event_store().append(data.get("type", ""), data.get("payload", {}))
    return jsonify({"id": eid})


@bp.route("/api/advanced/read-model/<model>")
def advanced_read_model_query(model):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"items": advanced_data.get_read_model().query(model)})


@bp.route("/api/advanced/sync/log")
def advanced_sync_log():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"log": advanced_data.get_sync_manager().get_sync_log()})


@bp.route("/api/advanced/query-explain")
def advanced_query_explain():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    sql = request.args.get("sql", "")
    return jsonify(advanced_data.explain_query(sql))


@bp.route("/api/advanced/pipeline/status")
def advanced_pipeline_status():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"tasks": advanced_data.get_pipeline().get_status()})
