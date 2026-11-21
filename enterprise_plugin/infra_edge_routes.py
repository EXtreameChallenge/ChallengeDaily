"""P421-P500: 边缘+服务网格+网关+消息队列+存储/数据库/缓存/负载均衡路由"""
from flask import Blueprint, request, jsonify
from infra_edge import (
    _edge_network, _edge_cache, _service_mesh, _mesh_breaker,
    _gateway_adv, _mq, _topic_exchange, _storage_opt, _data_lifecycle,
    _query_opt, _index_advisor, _db_pool,
    CacheStrategy, _cache_warmup, _cache_invalidator,
    _load_balancer, _health_checker,
    EdgeNode,
)

bp = Blueprint("infra_edge", __name__, url_prefix="/api/infra")


# ─── 边缘计算 ───
@bp.route("/edge/node", methods=["POST"])
def edge_add_node():
    data = request.get_json(silent=True) or {}
    node = EdgeNode(data.get("id", ""), data.get("location", ""),
                    int(data.get("capacity", 100)), float(data.get("latency", 10)))
    _edge_network.add_node(node)
    return jsonify({"status": "ok"})


@bp.route("/edge/route", methods=["POST"])
def edge_route():
    data = request.get_json(silent=True) or {}
    return jsonify(_edge_network.route_request(int(data.get("size", 1)), data.get("location", "")))


@bp.route("/edge/nodes", methods=["GET"])
def edge_nodes():
    return jsonify({"nodes": _edge_network.list_nodes()})


@bp.route("/edge/cache", methods=["POST"])
def edge_cache_set():
    data = request.get_json(silent=True) or {}
    _edge_cache.set(data.get("key", ""), data.get("value"), int(data.get("ttl", 300)))
    return jsonify({"status": "ok"})


@bp.route("/edge/cache/<key>", methods=["GET"])
def edge_cache_get(key: str):
    return jsonify({"value": _edge_cache.get(key)})


@bp.route("/edge/cache/stats", methods=["GET"])
def edge_cache_stats():
    return jsonify(_edge_cache.stats())


# ─── 服务网格 ───
@bp.route("/mesh/service", methods=["POST"])
def mesh_register():
    data = request.get_json(silent=True) or {}
    _service_mesh.register_service(data.get("name", ""), data.get("host", ""),
                                   int(data.get("port", 80)), data.get("version", "v1"))
    return jsonify({"status": "ok"})


@bp.route("/mesh/route", methods=["POST"])
def mesh_route():
    data = request.get_json(silent=True) or {}
    return jsonify(_service_mesh.resolve(data.get("source", ""), data.get("target", "")))


@bp.route("/mesh/services", methods=["GET"])
def mesh_services():
    return jsonify({"services": _service_mesh.list_services()})


@bp.route("/mesh/breaker/failure", methods=["POST"])
def mesh_breaker_failure():
    data = request.get_json(silent=True) or {}
    return jsonify(_mesh_breaker.record_failure(data.get("service", "")))


@bp.route("/mesh/breaker/<service>", methods=["GET"])
def mesh_breaker_check(service: str):
    return jsonify({"can_request": _mesh_breaker.can_request(service)})


# ─── API网关 ───
@bp.route("/gateway/route", methods=["POST"])
def gateway_route_add():
    data = request.get_json(silent=True) or {}
    _gateway_adv.register_route(data.get("path", ""), data.get("upstream", ""),
                                data.get("methods"), data.get("auth", True),
                                int(data.get("rate_limit", 100)))
    return jsonify({"status": "ok"})


@bp.route("/gateway/rate/<path:path>", methods=["GET"])
def gateway_rate(path: str):
    return jsonify(_gateway_adv.check_rate(path))


@bp.route("/gateway/token", methods=["POST"])
def gateway_token():
    data = request.get_json(silent=True) or {}
    token = _gateway_adv.issue_token(data.get("user_id", ""), int(data.get("ttl", 3600)))
    return jsonify({"token": token})


@bp.route("/gateway/auth", methods=["POST"])
def gateway_auth():
    data = request.get_json(silent=True) or {}
    return jsonify(_gateway_adv.authenticate(data.get("token", "")))


@bp.route("/gateway/routes", methods=["GET"])
def gateway_routes():
    return jsonify({"routes": _gateway_adv.list_routes()})


# ─── 消息队列 ───
@bp.route("/mq/produce", methods=["POST"])
def mq_produce():
    data = request.get_json(silent=True) or {}
    return jsonify(_mq.produce(data.get("message"), int(data.get("priority", 0))))


@bp.route("/mq/consume", methods=["POST"])
def mq_consume():
    return jsonify(_mq.consume() or {"empty": True})


@bp.route("/mq/stats", methods=["GET"])
def mq_stats():
    return jsonify(_mq.get_stats())


@bp.route("/topic/publish", methods=["POST"])
def topic_publish():
    data = request.get_json(silent=True) or {}
    return jsonify(_topic_exchange.publish(data.get("topic", ""), data.get("message")))


@bp.route("/topic/topics", methods=["GET"])
def topic_list():
    return jsonify({"topics": _topic_exchange.get_topics()})


# ─── 存储 ───
@bp.route("/storage/compress", methods=["POST"])
def storage_compress():
    data = request.get_json(silent=True) or {}
    return jsonify(_storage_opt.compress_data(data.get("data", "")))


@bp.route("/storage/dedup", methods=["POST"])
def storage_dedup():
    data = request.get_json(silent=True) or {}
    return jsonify(_storage_opt.deduplicate(data.get("chunks", [])))


@bp.route("/storage/tier", methods=["POST"])
def storage_tier():
    data = request.get_json(silent=True) or {}
    return jsonify(_storage_opt.tiered_storage(int(data.get("size", 0)), data.get("frequency", "low")))


@bp.route("/storage/lifecycle/policy", methods=["POST"])
def storage_lifecycle_policy():
    data = request.get_json(silent=True) or {}
    _data_lifecycle.set_policy(data.get("data_type", ""), int(data.get("hot", 30)),
                               int(data.get("warm", 90)), int(data.get("cold", 365)),
                               int(data.get("archive", 365)), int(data.get("delete", 2555)))
    return jsonify({"status": "ok"})


@bp.route("/storage/lifecycle/<data_type>/<int:age>", methods=["GET"])
def storage_lifecycle_get(data_type: str, age: int):
    return jsonify(_data_lifecycle.get_tier(data_type, age))


# ─── 数据库 ───
@bp.route("/db/query-analyze", methods=["POST"])
def db_query_analyze():
    data = request.get_json(silent=True) or {}
    return jsonify(_query_opt.analyze_query(data.get("query", "")))


@bp.route("/db/index-advice", methods=["POST"])
def db_index_advice():
    data = request.get_json(silent=True) or {}
    return jsonify({"recommendations": _index_advisor.recommend(
        data.get("table", ""), data.get("columns", []), data.get("patterns", []))})


@bp.route("/db/pool/acquire", methods=["POST"])
def db_pool_acquire():
    return jsonify(_db_pool.acquire())


@bp.route("/db/pool/release/<int:conn_id>", methods=["POST"])
def db_pool_release(conn_id: int):
    _db_pool.release(conn_id)
    return jsonify({"status": "ok"})


@bp.route("/db/pool/stats", methods=["GET"])
def db_pool_stats():
    return jsonify(_db_pool.stats())


# ─── 缓存 ───
@bp.route("/cache/strategies", methods=["GET"])
def cache_strategies():
    return jsonify({"strategies": CacheStrategy.STRATEGIES})


@bp.route("/cache/warmup/task", methods=["POST"])
def cache_warmup_add():
    data = request.get_json(silent=True) or {}
    _cache_warmup.add_task(data.get("name", ""), lambda: {}, int(data.get("priority", 0)))
    return jsonify({"status": "ok"})


@bp.route("/cache/warmup/execute", methods=["POST"])
def cache_warmup_exec():
    return jsonify(_cache_warmup.execute())


@bp.route("/cache/invalidator/pattern", methods=["POST"])
def cache_inv_pattern():
    data = request.get_json(silent=True) or {}
    _cache_invalidator.add_pattern(data.get("name", ""), data.get("pattern", ""), data.get("action", "delete"))
    return jsonify({"status": "ok"})


@bp.route("/cache/invalidator/check", methods=["POST"])
def cache_inv_check():
    data = request.get_json(silent=True) or {}
    return jsonify(_cache_invalidator.invalidate(data.get("key", "")))


# ─── 负载均衡 ───
@bp.route("/lb/backend", methods=["POST"])
def lb_add_backend():
    data = request.get_json(silent=True) or {}
    _load_balancer.add_backend(data.get("host", ""), int(data.get("port", 80)), int(data.get("weight", 1)))
    return jsonify({"status": "ok"})


@bp.route("/lb/select", methods=["POST"])
def lb_select():
    data = request.get_json(silent=True) or {}
    return jsonify(_load_balancer.select(data.get("client_ip", "")))


@bp.route("/lb/health", methods=["POST"])
def lb_health():
    data = request.get_json(silent=True) or {}
    _load_balancer.set_health(data.get("host", ""), int(data.get("port", 80)), data.get("healthy", True))
    return jsonify({"status": "ok"})


@bp.route("/lb/backends", methods=["GET"])
def lb_backends():
    return jsonify({"backends": _load_balancer.list_backends(), "stats": _load_balancer.get_stats()})


@bp.route("/health-check/register", methods=["POST"])
def health_register():
    data = request.get_json(silent=True) or {}
    _health_checker.register(data.get("name", ""), lambda: True)
    return jsonify({"status": "ok"})


@bp.route("/health-check/run", methods=["POST"])
def health_run():
    return jsonify(_health_checker.run_checks())


@bp.route("/health-check/results", methods=["GET"])
def health_results():
    return jsonify(_health_checker.get_results())
