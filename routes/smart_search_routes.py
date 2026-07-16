"""P231-P239: 智能搜索引擎 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import smart_search as ss

bp = Blueprint('smart_search', __name__)


@bp.route("/api/search")
def search():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    query = request.args.get("q", "")
    if not query:
        return jsonify({"results": [], "total": 0})
    cached = ss._cache.get(query)
    if cached is not None:
        ss._analytics.track(query, len(cached))
        return jsonify({"results": cached, "total": len(cached), "cached": True})
    results = ss._index.search(query)
    ss._cache.set(query, results)
    ss._suggester.record(query)
    ss._analytics.track(query, len(results))
    return jsonify({"results": results, "total": len(results)})


@bp.route("/api/search/index", methods=["POST"])
def search_index():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    ss._index.add_document(data.get("id", ""), data.get("content", ""), data.get("metadata"))
    if data.get("facets"):
        ss._faceted.index(data.get("id", ""), data["facets"])
    return jsonify({"status": "ok"})


@bp.route("/api/search/stats")
def search_stats():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({
        "index": ss._index.get_stats(),
        "cache": ss._cache.stats(),
        "analytics": ss._analytics.stats()
    })


@bp.route("/api/search/fuzzy")
def search_fuzzy():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    query = request.args.get("q", "")
    candidates = request.args.get("candidates", "").split(",")
    max_dist = int(request.args.get("max_distance", 2))
    return jsonify({"results": ss._fuzzy.search(query, candidates, max_dist)})


@bp.route("/api/search/suggest")
def search_suggest():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    prefix = request.args.get("prefix", "")
    return jsonify({"suggestions": ss._suggester.suggest(prefix)})


@bp.route("/api/search/highlight")
def search_highlight():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    text = request.args.get("text", "")
    query = request.args.get("q", "")
    return jsonify({"highlighted": ss._highlighter.snippet(text, query)})


@bp.route("/api/search/facets")
def search_facets():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"facets": ss._faceted.get_facets()})


@bp.route("/api/search/popular")
def search_popular():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"queries": ss._suggester.get_popular()})
