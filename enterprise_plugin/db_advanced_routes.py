"""
P841-P880: 数据库高级/索引/查询优化 路由
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from db_advanced import (
    _index_advisor, _query_optimizer, _read_write, _shard_mgr,
    _slow_query, _conn_pool, _tx_mgr,
)

bp = Blueprint("db_advanced", __name__, url_prefix="/api/db-adv")


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _arg(name: str, default=None):
    return request.args.get(name, default)


# ═════════ 索引顾问 ═════════

@bp.route("/index-advisor/queries", methods=["POST"])
def index_record_query():
    data = _json_body()
    _index_advisor.record_query(
        table=data.get("table", ""),
        columns=data.get("columns", []),
        where_clause=data.get("where", ""),
        duration_ms=float(data.get("duration_ms", 0)),
    )
    return jsonify({"status": "ok"})


@bp.route("/index-advisor/indexes", methods=["POST"])
def index_add_existing():
    data = _json_body()
    _index_advisor.add_existing_index(
        table=data.get("table", ""),
        columns=data.get("columns", []),
        name=data.get("name", ""),
        unique=bool(data.get("unique", False)),
    )
    return jsonify({"status": "ok"})


@bp.route("/index-advisor/indexes", methods=["GET"])
def index_list_existing():
    return jsonify(_index_advisor.list_existing())


@bp.route("/index-advisor/analyze", methods=["POST"])
def index_analyze():
    return jsonify(_index_advisor.analyze())


@bp.route("/index-advisor/slow-report", methods=["GET"])
def index_slow_report():
    return jsonify(_index_advisor.slow_query_report(float(_arg("threshold", 100))))


# ═════════ 查询优化器 ═════════

@bp.route("/query/parse", methods=["POST"])
def query_parse():
    data = _json_body()
    return jsonify(_query_optimizer.parse_query(data.get("sql", "")))


@bp.route("/query/explain", methods=["POST"])
def query_explain():
    data = _json_body()
    return jsonify(_query_optimizer.explain_plan(data.get("sql", "")))


@bp.route("/query/optimize-suggestions", methods=["POST"])
def query_suggestions():
    data = _json_body()
    return jsonify({"suggestions": _query_optimizer.suggest_optimization(data.get("sql", ""))})


# ═════════ 读写分离 + 分库分表 ═════════

@bp.route("/rw/master/<cluster>", methods=["POST"])
def rw_set_master(cluster):
    data = _json_body()
    _read_write.set_master(cluster, data.get("host", ""), int(data.get("port", 3306)))
    return jsonify({"status": "ok"})


@bp.route("/rw/slaves/<cluster>", methods=["POST"])
def rw_add_slave(cluster):
    data = _json_body()
    _read_write.add_slave(cluster, data.get("host", ""), int(data.get("port", 3306)))
    return jsonify({"status": "ok"})


@bp.route("/rw/route", methods=["GET"])
def rw_route():
    cluster = _arg("cluster", "default")
    op = _arg("op", "SELECT")
    return jsonify(_read_write.route(cluster, op))


@bp.route("/rw/clusters", methods=["GET"])
def rw_list():
    return jsonify(_read_write.list_clusters())


@bp.route("/shards/<table>", methods=["POST"])
def shards_register(table):
    data = _json_body()
    return jsonify(_shard_mgr.register_record(table, data.get("key", ""), data.get("record", {})))


@bp.route("/shards/<table>/<key>", methods=["GET"])
def shards_lookup(table, key):
    return jsonify(_shard_mgr.lookup(table, key))


@bp.route("/shards/stats", methods=["GET"])
def shards_stats():
    return jsonify(_shard_mgr.shard_stats())


# ═════════ 慢查询 + 连接池 + 事务 ═════════

@bp.route("/slow-queries", methods=["POST"])
def slow_record():
    data = _json_body()
    _slow_query.record(
        sql=data.get("sql", ""),
        duration_ms=float(data.get("duration_ms", 0)),
        table=data.get("table", ""),
    )
    return jsonify({"status": "ok"})


@bp.route("/slow-queries/top", methods=["GET"])
def slow_top():
    return jsonify(_slow_query.top_slow(int(_arg("limit", 20))))


@bp.route("/slow-queries/stats", methods=["GET"])
def slow_stats():
    return jsonify(_slow_query.stats())


@bp.route("/conn-pool/acquire", methods=["POST"])
def conn_acquire():
    data = _json_body()
    return jsonify(_conn_pool.acquire(data.get("conn_id", "")))


@bp.route("/conn-pool/release", methods=["POST"])
def conn_release():
    data = _json_body()
    return jsonify(_conn_pool.release(data.get("conn_id", "")))


@bp.route("/conn-pool/cleanup", methods=["POST"])
def conn_cleanup():
    return jsonify(_conn_pool.cleanup_idle())


@bp.route("/conn-pool/stats", methods=["GET"])
def conn_stats():
    return jsonify(_conn_pool.stats())


@bp.route("/tx/begin", methods=["POST"])
def tx_begin():
    data = _json_body()
    return jsonify(_tx_mgr.begin(
        data.get("tx_id", ""),
        data.get("isolation", "READ_COMMITTED"),
    ))


@bp.route("/tx/<tx_id>/savepoint", methods=["POST"])
def tx_savepoint(tx_id):
    data = _json_body()
    return jsonify(_tx_mgr.savepoint(tx_id, data.get("name", "")))


@bp.route("/tx/<tx_id>/commit", methods=["POST"])
def tx_commit(tx_id):
    return jsonify(_tx_mgr.commit(tx_id))


@bp.route("/tx/<tx_id>/rollback", methods=["POST"])
def tx_rollback(tx_id):
    data = _json_body()
    return jsonify(_tx_mgr.rollback(tx_id, data.get("to_savepoint", "")))


@bp.route("/tx/active", methods=["GET"])
def tx_active():
    return jsonify(_tx_mgr.list_active())
