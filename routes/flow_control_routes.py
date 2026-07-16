"""
P801-P840: 流控/限流/熔断/降级 路由
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from flow_control import (
    _token_bucket, _leaky_bucket, _sliding_window, _fixed_window,
    _circuit_registry, _degradation, _backpressure,
    _retry_policy, _timeout_guard, _bulkhead, _flow_controller,
)

bp = Blueprint("flow_control", __name__, url_prefix="/api/flow")


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _arg(name: str, default=None):
    return request.args.get(name, default)


# ═════════ 限流器 ═════════

@bp.route("/token-bucket/consume", methods=["POST"])
def token_bucket_consume():
    data = _json_body()
    return jsonify(_token_bucket.consume(int(data.get("tokens", 1))))


@bp.route("/leaky-bucket/pour", methods=["POST"])
def leaky_bucket_pour():
    data = _json_body()
    return jsonify(_leaky_bucket.pour(int(data.get("amount", 1))))


@bp.route("/sliding-window/check", methods=["GET"])
def sliding_window_check():
    return jsonify(_sliding_window.check(_arg("key", "default")))


@bp.route("/fixed-window/check", methods=["GET"])
def fixed_window_check():
    return jsonify(_fixed_window.check(_arg("key", "default")))


# ═════════ 熔断器 ═════════

@bp.route("/circuits", methods=["GET"])
def circuits_list():
    return jsonify(_circuit_registry.list_all())


@bp.route("/circuits/<name>", methods=["POST"])
def circuits_create(name):
    data = _json_body()
    cb = _circuit_registry.get_or_create(
        name,
        failure_threshold=int(data.get("failure_threshold", 5)),
        failure_rate_threshold=float(data.get("failure_rate_threshold", 0.5)),
        slow_call_threshold_ms=float(data.get("slow_call_threshold_ms", 1000)),
        open_state_sec=int(data.get("open_state_sec", 30)),
        half_open_max_calls=int(data.get("half_open_max_calls", 3)),
    )
    return jsonify({"status": "ok", "name": name, "state": cb.state.value})


@bp.route("/circuits/<name>/allow", methods=["GET"])
def circuits_allow(name):
    cb = _circuit_registry.get_or_create(name)
    return jsonify(cb.allow_request())


@bp.route("/circuits/<name>/success", methods=["POST"])
def circuits_record_success(name):
    data = _json_body()
    cb = _circuit_registry.get_or_create(name)
    return jsonify(cb.record_success(float(data.get("duration_ms", 0))))


@bp.route("/circuits/<name>/failure", methods=["POST"])
def circuits_record_failure(name):
    data = _json_body()
    cb = _circuit_registry.get_or_create(name)
    return jsonify(cb.record_failure(float(data.get("duration_ms", 0))))


@bp.route("/circuits/<name>/reset", methods=["POST"])
def circuits_reset(name):
    return jsonify(_circuit_registry.reset(name))


@bp.route("/circuits/<name>/stats", methods=["GET"])
def circuits_stats(name):
    cb = _circuit_registry.get_or_create(name)
    return jsonify(cb.stats())


# ═════════ 降级 + 背压 ═════════

@bp.route("/degradation/rules", methods=["GET"])
def degradation_rules():
    return jsonify(_degradation.list_rules())


@bp.route("/degradation/rules", methods=["POST"])
def degradation_register():
    data = _json_body()
    return jsonify(_degradation.register_rule(
        service=data.get("service", ""),
        trigger_qps=int(data.get("trigger_qps", 1000)),
        fallback=data.get("fallback", "static_response"),
        levels=data.get("levels"),
    ))


@bp.route("/degradation/<service>/trigger", methods=["POST"])
def degradation_trigger(service):
    data = _json_body()
    return jsonify(_degradation.trigger(service, data.get("level", "L1")))


@bp.route("/degradation/<service>/recover", methods=["POST"])
def degradation_recover(service):
    return jsonify(_degradation.recover(service))


@bp.route("/degradation/<service>/check", methods=["GET"])
def degradation_check(service):
    return jsonify(_degradation.check(service))


@bp.route("/backpressure/acquire", methods=["POST"])
def backpressure_acquire():
    return jsonify(_backpressure.acquire())


@bp.route("/backpressure/release", methods=["POST"])
def backpressure_release():
    return jsonify(_backpressure.release())


@bp.route("/backpressure/stats", methods=["GET"])
def backpressure_stats():
    return jsonify(_backpressure.stats())


# ═════════ 重试 + 超时 + 隔舱 ═════════

@bp.route("/retry/next-delay", methods=["GET"])
def retry_next_delay():
    attempt = int(_arg("attempt", 1))
    return jsonify(_retry_policy.next_delay(attempt))


@bp.route("/retry/execute", methods=["POST"])
def retry_execute():
    data = _json_body()
    fn = data.get("fn")
    args = data.get("args", [])
    # 安全限制：仅允许无副作用函数名 "echo"
    if fn == "echo":
        return jsonify(_retry_policy.execute(lambda x: f"echo:{x}", *args))
    return jsonify({"status": "error", "error": "函数不允许"}), 400


@bp.route("/timeout/<operation>", methods=["GET"])
def timeout_get(operation):
    return jsonify(_timeout_guard.get(operation))


@bp.route("/timeout/<operation>", methods=["POST"])
def timeout_set(operation):
    data = _json_body()
    return jsonify(_timeout_guard.set(operation, int(data.get("timeout_ms", 5000))))


@bp.route("/timeout", methods=["GET"])
def timeout_list():
    return jsonify(_timeout_guard.list_all())


@bp.route("/bulkheads", methods=["GET"])
def bulkheads_list():
    return jsonify(_bulkhead.list_all())


@bp.route("/bulkheads", methods=["POST"])
def bulkheads_create():
    data = _json_body()
    return jsonify(_bulkhead.create(
        name=data.get("name", ""),
        max_concurrent=int(data.get("max_concurrent", 10)),
        max_queue=int(data.get("max_queue", 20)),
    ))


@bp.route("/bulkheads/<name>/acquire", methods=["POST"])
def bulkheads_acquire(name):
    return jsonify(_bulkhead.acquire(name))


@bp.route("/bulkheads/<name>/release", methods=["POST"])
def bulkheads_release(name):
    return jsonify(_bulkhead.release(name))


@bp.route("/bulkheads/<name>/stats", methods=["GET"])
def bulkheads_stats(name):
    return jsonify(_bulkhead.stats(name))


# ═════════ 流量编排器 ═════════

@bp.route("/strategies", methods=["GET"])
def strategies_list():
    return jsonify(_flow_controller.list_strategies())


@bp.route("/strategies/<name>", methods=["POST"])
def strategies_register(name):
    data = _json_body()
    return jsonify(_flow_controller.register(
        name=name,
        strategy=data.get("strategy", "token_bucket"),
        **{k: v for k, v in data.items() if k != "strategy"}
    ))


@bp.route("/strategies/<name>/check", methods=["GET"])
def strategies_check(name):
    return jsonify(_flow_controller.check(name, _arg("key", "")))
