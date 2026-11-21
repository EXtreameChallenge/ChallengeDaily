"""
P881-P920: 缓存策略/多级缓存/预热 路由
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from cache_advanced import (
    _mlcache, _cache_strategy, _cache_shield, _eviction_cache,
    _cache_serializer, _cache_warmer, EvictionPolicy,
)

bp = Blueprint("cache_advanced", __name__, url_prefix="/api/cache-adv")


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _arg(name: str, default=None):
    return request.args.get(name, default)


# ═════════ 多级缓存 ═════════

@bp.route("/mlc/get", methods=["GET"])
def mlc_get():
    return jsonify(_mlcache.get(_arg("key", "")))


@bp.route("/mlc/set", methods=["POST"])
def mlc_set():
    data = _json_body()
    return jsonify(_mlcache.set(
        data.get("key", ""),
        data.get("value"),
        int(data.get("ttl_sec", 300)),
    ))


@bp.route("/mlc/invalidate", methods=["POST"])
def mlc_invalidate():
    data = _json_body()
    return jsonify(_mlcache.invalidate(data.get("key", "")))


@bp.route("/mlc/clear", methods=["POST"])
def mlc_clear():
    return jsonify(_mlcache.clear())


@bp.route("/mlc/stats", methods=["GET"])
def mlc_stats():
    return jsonify(_mlcache.stats())


# ═════════ 缓存策略 ═════════

@bp.route("/strategies", methods=["GET"])
def strategies_list():
    return jsonify(_cache_strategy.list_strategies())


@bp.route("/strategies/<name>", methods=["POST"])
def strategies_register(name):
    data = _json_body()
    return jsonify(_cache_strategy.register(
        name=name,
        strategy=data.get("strategy", "cache-aside"),
        ttl_sec=int(data.get("ttl_sec", 300)),
    ))


@bp.route("/strategies/<name>/get", methods=["GET"])
def strategies_get(name):
    key = _arg("key", "")
    return jsonify(_cache_strategy.get(name, key))


@bp.route("/strategies/<name>/set", methods=["POST"])
def strategies_set(name):
    data = _json_body()
    return jsonify(_cache_strategy.set(
        name=name,
        key=data.get("key", ""),
        value=data.get("value"),
    ))


@bp.route("/strategies/flush-write-behind", methods=["POST"])
def strategies_flush():
    return jsonify({"status": "ok", "note": "需提供writer回调，本接口仅模拟"})


# ═════════ 缓存防护 ═════════

@bp.route("/shield/bloom", methods=["POST"])
def shield_bloom_add():
    data = _json_body()
    _cache_shield.add_to_bloom(data.get("key", ""))
    return jsonify({"status": "ok"})


@bp.route("/shield/bloom/check", methods=["GET"])
def shield_bloom_check():
    return jsonify({"exists": _cache_shield.might_exist(_arg("key", ""))})


@bp.route("/shield/stats", methods=["GET"])
def shield_stats():
    return jsonify(_cache_shield.stats())


# ═════════ 淘汰策略缓存 ═════════

@bp.route("/eviction/get", methods=["GET"])
def eviction_get():
    return jsonify(_eviction_cache.get(_arg("key", "")))


@bp.route("/eviction/set", methods=["POST"])
def eviction_set():
    data = _json_body()
    return jsonify(_eviction_cache.set(
        data.get("key", ""),
        data.get("value"),
        int(data.get("ttl_sec", 300)),
    ))


@bp.route("/eviction/policy", methods=["POST"])
def eviction_set_policy():
    data = _json_body()
    try:
        policy = EvictionPolicy(data.get("policy", "lru"))
        _eviction_cache.policy = policy
        return jsonify({"status": "ok", "policy": policy.value})
    except ValueError:
        return jsonify({"status": "error", "error": "无效策略"}), 400


@bp.route("/eviction/stats", methods=["GET"])
def eviction_stats():
    return jsonify(_eviction_cache.stats())


# ═════════ 序列化与压缩 ═════════

@bp.route("/serializer/serialize", methods=["POST"])
def serializer_serialize():
    data = _json_body()
    return jsonify(_cache_serializer.serialize(
        data.get("value"),
        compress=bool(data.get("compress", False)),
    ))


@bp.route("/serializer/deserialize", methods=["POST"])
def serializer_deserialize():
    data = _json_body()
    return jsonify(_cache_serializer.deserialize(
        data.get("data", ""),
        compressed=bool(data.get("compressed", False)),
    ))


# ═════════ 缓存预热 ═════════

@bp.route("/warmers", methods=["GET"])
def warmers_list():
    return jsonify(_cache_warmer.list_warmers())


@bp.route("/warmers/<name>", methods=["POST"])
def warmers_register(name):
    data = _json_body()
    return jsonify(_cache_warmer.register(
        name=name,
        keys=data.get("keys", []),
    ))


@bp.route("/warmers/<name>/warmup", methods=["POST"])
def warmers_warmup(name):
    return jsonify(_cache_warmer.warmup(name))
