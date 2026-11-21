"""P221-P229: 知识图谱引擎 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import knowledge_graph as kg

bp = Blueprint('knowledge_graph', __name__)


@bp.route("/api/kg/nodes", methods=["GET", "POST"])
def kg_nodes():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        kg._graph.add_node(data.get("id", ""), data.get("label", ""),
                           data.get("type", ""), data.get("properties"))
        return jsonify({"status": "ok"})
    query = request.args.get("q", "")
    if query:
        return jsonify({"nodes": kg._graph.search_nodes(query)})
    return jsonify({"stats": kg._graph.get_stats()})


@bp.route("/api/kg/edges", methods=["POST"])
def kg_edges():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    kg._graph.add_edge(data.get("from", ""), data.get("to", ""),
                       data.get("relation", "related"), data.get("weight", 1.0),
                       data.get("properties"))
    return jsonify({"status": "ok"})


@bp.route("/api/kg/neighbors")
def kg_neighbors():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    node_id = request.args.get("id", "")
    return jsonify({"neighbors": kg._graph.get_neighbors(node_id)})


@bp.route("/api/kg/traverse")
def kg_traverse():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    start = request.args.get("start", "")
    method = request.args.get("method", "bfs")
    depth = int(request.args.get("depth", 10))
    if method == "dfs":
        return jsonify({"nodes": kg._traversal.dfs(kg._graph, start, depth)})
    return jsonify({"nodes": kg._traversal.bfs(kg._graph, start, depth)})


@bp.route("/api/kg/shortest-path")
def kg_shortest_path():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    start = request.args.get("start", "")
    end = request.args.get("end", "")
    return jsonify(kg._path_finder.find(kg._graph, start, end))


@bp.route("/api/kg/communities")
def kg_communities():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"communities": kg._community.detect(kg._graph)})


@bp.route("/api/kg/centrality")
def kg_centrality():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"degree": kg._centrality.degree_centrality(kg._graph)})


@bp.route("/api/kg/infer")
def kg_infer():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    node_id = request.args.get("id", "")
    depth = int(request.args.get("depth", 2))
    return jsonify({"inferred": kg._reasoning.infer_relations(kg._graph, node_id, depth)})


@bp.route("/api/kg/visualize")
def kg_visualize():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    limit = int(request.args.get("limit", 100))
    return jsonify(kg._visualizer.to_vis_data(kg._graph, limit))
