"""
P921-P960: 消息队列/事件驱动/流处理 路由
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from mq_stream import (
    _mq_adv, _event_bus, _stream_processor,
    _consumer_group, _idempotency, _broadcast,
)

bp = Blueprint("mq_stream", __name__, url_prefix="/api/mq-stream")


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _arg(name: str, default=None):
    return request.args.get(name, default)


# ═════════ 消息队列 ═════════

@bp.route("/mq/produce", methods=["POST"])
def mq_produce():
    data = _json_body()
    return jsonify(_mq_adv.produce(
        topic=data.get("topic", ""),
        payload=data.get("payload"),
        headers=data.get("headers"),
        priority=int(data.get("priority", 0)),
        delay_sec=float(data.get("delay_sec", 0)),
    ))


@bp.route("/mq/consume", methods=["GET"])
def mq_consume():
    return jsonify(_mq_adv.consume(_arg("topic", ""), _arg("consumer", "")))


@bp.route("/mq/ack/<msg_id>", methods=["POST"])
def mq_ack(msg_id):
    return jsonify(_mq_adv.ack(msg_id))


@bp.route("/mq/nack/<msg_id>", methods=["POST"])
def mq_nack(msg_id):
    data = _json_body()
    return jsonify(_mq_adv.nack(msg_id, bool(data.get("requeue", True))))


@bp.route("/mq/process-delayed", methods=["POST"])
def mq_process_delayed():
    count = _mq_adv.process_delayed()
    return jsonify({"status": "ok", "ready": count})


@bp.route("/mq/dead-letters", methods=["GET"])
def mq_dead_letters():
    return jsonify(_mq_adv.get_dead_letters(int(_arg("limit", 50))))


@bp.route("/mq/stats", methods=["GET"])
def mq_stats():
    return jsonify(_mq_adv.stats())


# ═════════ 事件总线 ═════════

@bp.route("/event-bus/subscribe", methods=["POST"])
def eb_subscribe():
    data = _json_body()
    return jsonify(_event_bus.subscribe(
        event_type=data.get("event_type", ""),
        handler_id=data.get("handler_id", ""),
        priority=int(data.get("priority", 0)),
    ))


@bp.route("/event-bus/unsubscribe", methods=["POST"])
def eb_unsubscribe():
    data = _json_body()
    return jsonify(_event_bus.unsubscribe(
        data.get("event_type", ""),
        data.get("handler_id", ""),
    ))


@bp.route("/event-bus/publish", methods=["POST"])
def eb_publish():
    data = _json_body()
    return jsonify(_event_bus.publish(
        event_type=data.get("event_type", ""),
        payload=data.get("payload"),
        headers=data.get("headers"),
    ))


@bp.route("/event-bus/subscribers", methods=["GET"])
def eb_subscribers():
    return jsonify(_event_bus.list_subscribers(_arg("event_type", "")))


@bp.route("/event-bus/recent", methods=["GET"])
def eb_recent():
    return jsonify(_event_bus.recent_events(int(_arg("limit", 50))))


@bp.route("/event-bus/stats", methods=["GET"])
def eb_stats():
    return jsonify(_event_bus.stats())


# ═════════ 流处理 ═════════

@bp.route("/stream/<name>", methods=["POST"])
def stream_register(name):
    data = _json_body()
    return jsonify(_stream_processor.register_stream(
        name, int(data.get("window_sec", 60))))


@bp.route("/stream/<name>/send", methods=["POST"])
def stream_send(name):
    data = _json_body()
    return jsonify(_stream_processor.send(name, data.get("data")))


@bp.route("/stream/<name>/trigger", methods=["POST"])
def stream_trigger(name):
    return jsonify(_stream_processor.trigger_window(name))


@bp.route("/stream/<name>/aggregate", methods=["GET"])
def stream_aggregate(name):
    return jsonify(_stream_processor.aggregate(
        name, _arg("field", ""),
        _arg("agg", "count"),
    ))


@bp.route("/stream/stats", methods=["GET"])
def stream_stats():
    return jsonify(_stream_processor.stats())


# ═════════ 消费者组 + 幂等 + 广播 ═════════

@bp.route("/consumer-groups", methods=["POST"])
def cg_create():
    data = _json_body()
    return jsonify(_consumer_group.create(
        data.get("group", ""),
        data.get("topic", ""),
    ))


@bp.route("/consumer-groups/<group>/join", methods=["POST"])
def cg_join(group):
    data = _json_body()
    return jsonify(_consumer_group.join(group, data.get("consumer_id", "")))


@bp.route("/consumer-groups/<group>/leave", methods=["POST"])
def cg_leave(group):
    data = _json_body()
    return jsonify(_consumer_group.leave(group, data.get("consumer_id", "")))


@bp.route("/consumer-groups", methods=["GET"])
def cg_list():
    return jsonify(_consumer_group.list_groups())


@bp.route("/idempotency/check", methods=["POST"])
def idempotency_check():
    data = _json_body()
    return jsonify(_idempotency.check_and_mark(data.get("key", "")))


@bp.route("/idempotency/stats", methods=["GET"])
def idempotency_stats():
    return jsonify(_idempotency.stats())


@bp.route("/broadcast/subscribe", methods=["POST"])
def bc_subscribe():
    data = _json_body()
    return jsonify(_broadcast.subscribe(
        data.get("channel", ""),
        data.get("client_id", ""),
    ))


@bp.route("/broadcast/unsubscribe", methods=["POST"])
def bc_unsubscribe():
    data = _json_body()
    return jsonify(_broadcast.unsubscribe(
        data.get("channel", ""),
        data.get("client_id", ""),
    ))


@bp.route("/broadcast/<channel>", methods=["POST"])
def bc_publish(channel):
    data = _json_body()
    return jsonify(_broadcast.broadcast(channel, data.get("message")))


@bp.route("/broadcast/channels", methods=["GET"])
def bc_channels():
    return jsonify(_broadcast.list_channels())


@bp.route("/broadcast/<channel>/recent", methods=["GET"])
def bc_recent(channel):
    return jsonify(_broadcast.recent_messages(channel, int(_arg("limit", 20))))


@bp.route("/broadcast/stats", methods=["GET"])
def bc_stats():
    return jsonify(_broadcast.stats())
