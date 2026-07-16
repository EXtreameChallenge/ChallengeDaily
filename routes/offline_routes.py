"""P261-P269: 离线优先架构 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import offline_first as off

bp = Blueprint('offline', __name__)


@bp.route("/api/offline/storage", methods=["GET", "POST"])
def storage():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        off._storage.set(data.get("key", ""), data.get("value"), data.get("ttl", 0))
        return jsonify({"status": "ok"})
    key = request.args.get("key", "")
    return jsonify({"value": off._storage.get(key)})


@bp.route("/api/offline/queue", methods=["GET", "POST"])
def queue():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        item_id = off._offline_queue.enqueue(data.get("op", ""), data.get("data", {}))
        return jsonify({"id": item_id})
    return jsonify({"queue": off._offline_queue.peek(), "size": off._offline_queue.size()})


@bp.route("/api/offline/sync/status")
def sync_status():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    return jsonify(off._sync_strategy.get_sync_status())


@bp.route("/api/offline/sync/strategy", methods=["POST"])
def sync_strategy():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    off._sync_strategy.set_strategy(data.get("strategy", "incremental"))
    return jsonify({"status": "ok"})


@bp.route("/api/offline/network")
def network_status():
    return jsonify({"online": off._network.is_online()})


@bp.route("/api/offline/network/set", methods=["POST"])
def network_set():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    off._network.set_online(data.get("online", True))
    return jsonify({"status": "ok"})


@bp.route("/api/offline/cache/stats")
def cache_stats():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    return jsonify(off._cache.stats())


@bp.route("/api/offline/cache", methods=["POST"])
def cache_set():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    off._cache.set(data.get("key", ""), data.get("value"), data.get("layer", 1), data.get("ttl", 300))
    return jsonify({"status": "ok"})


@bp.route("/api/offline/cache/get")
def cache_get():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    key = request.args.get("key", "")
    return jsonify({"value": off._cache.get(key)})


@bp.route("/api/offline/incremental-sync", methods=["POST"])
def incremental_sync():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    result = off._incremental.sync(data.get("entity", ""), data.get("local", []), data.get("remote", []))
    return jsonify(result)


@bp.route("/api/offline/search", methods=["POST"])
def offline_search():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    if data.get("action") == "index":
        off._offline_search.index(data.get("id", ""), data.get("content", ""))
        return jsonify({"status": "ok"})
    return jsonify({"results": off._offline_search.search(data.get("query", ""))})
