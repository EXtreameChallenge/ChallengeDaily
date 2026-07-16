"""P161-P169: 性能 API"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import perf_deep

bp = Blueprint('perf_routes', __name__)


@bp.route("/api/perf/hot-paths")
def perf_hot_paths():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"hot_paths": perf_deep.get_hot_path_stats()})


@bp.route("/api/perf/benchmark", methods=["POST"])
def perf_benchmark():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    # 简单 benchmark 示例
    def noop():
        pass
    result = perf_deep.Benchmark.run(
        data.get("name", "noop"),
        noop,
        iterations=int(data.get("iterations", "1000"))
    )
    return jsonify(result)
