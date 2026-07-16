"""P271-P279: 实时通信系统 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import realtime_comm as rt

bp = Blueprint('realtime', __name__)


@bp.route("/api/realtime/connections")
def connections():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"connections": rt._ws_mgr.list_connections()})


@bp.route("/api/realtime/connections/register", methods=["POST"])
def conn_register():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    rt._ws_mgr.connect(data.get("id", ""), data.get("user", ""))
    return jsonify({"status": "ok"})


@bp.route("/api/realtime/connections/<conn_id>", methods=["DELETE"])
def conn_disconnect(conn_id):
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    rt._ws_mgr.disconnect(conn_id)
    return jsonify({"status": "ok"})


@bp.route("/api/realtime/broadcast", methods=["POST"])
def broadcast():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    count = rt._broadcaster.broadcast(data.get("topic", ""), data.get("message", {}))
    return jsonify({"delivered": count})


@bp.route("/api/realtime/rooms")
def rooms():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"rooms": rt._room_mgr.list_rooms()})


@bp.route("/api/realtime/rooms/join", methods=["POST"])
def room_join():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    rt._room_mgr.join(data.get("room", ""), data.get("conn", ""))
    return jsonify({"status": "ok"})


@bp.route("/api/realtime/rooms/<room>/members")
def room_members(room):
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"members": rt._room_mgr.get_members(room)})


@bp.route("/api/realtime/heartbeat/<conn_id>", methods=["POST"])
def heartbeat(conn_id):
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    rt._heartbeat.beat(conn_id)
    return jsonify({"alive": rt._heartbeat.check_alive(conn_id)})


@bp.route("/api/realtime/heartbeat/stale")
def heartbeat_stale():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"stale": rt._heartbeat.get_stale()})


@bp.route("/api/realtime/compress", methods=["POST"])
def compress():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    compressed = rt._compressor.compress_json(data.get("message", {}))
    return jsonify({"size": len(compressed), "compressed": compressed.hex()[:100]})


@bp.route("/api/realtime/event-bus/emit", methods=["POST"])
def event_emit():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    count = rt._event_bus.emit(data.get("event", ""), data.get("data", {}))
    return jsonify({"handlers_notified": count})


@bp.route("/api/realtime/event-bus/recent")
def event_recent():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    limit = int(request.args.get("limit", 50))
    return jsonify({"events": rt._event_bus.get_recent_events(limit)})


@bp.route("/api/realtime/channels")
def channels():
    if not check_token(request): return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"channels": rt._mux.list_channels()})
