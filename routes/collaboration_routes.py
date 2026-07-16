"""P241-P249: 协作系统 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import collaboration as collab

bp = Blueprint('collaboration', __name__)


@bp.route("/api/collab/sessions", methods=["POST"])
def session_create():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    sid = collab._sessions.create(data.get("user_id", ""), data.get("room_id", ""))
    return jsonify({"session_id": sid})


@bp.route("/api/collab/sessions/active")
def sessions_active():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    room = request.args.get("room", "")
    return jsonify({"sessions": collab._sessions.list_active(room)})


@bp.route("/api/collab/channel/publish", methods=["POST"])
def channel_publish():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    collab._channel.publish(data.get("channel", ""), data.get("message", {}))
    return jsonify({"status": "ok"})


@bp.route("/api/collab/channel/history")
def channel_history():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    ch = request.args.get("channel", "")
    return jsonify({"messages": collab._channel.get_history(ch)})


@bp.route("/api/collab/ot/apply", methods=["POST"])
def ot_apply():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    result = collab.OperationalTransform.apply(data.get("text", ""), data.get("op", {}))
    return jsonify({"text": result})


@bp.route("/api/collab/conflict/resolve", methods=["POST"])
def conflict_resolve():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    result = collab.ConflictResolver.resolve(data.get("conflicts", []), data.get("strategy", "last_write_wins"))
    return jsonify(result)


@bp.route("/api/collab/permissions", methods=["POST"])
def permissions_set():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    collab._permissions.assign_role(data.get("room", ""), data.get("user", ""), data.get("role", "viewer"))
    return jsonify({"status": "ok"})


@bp.route("/api/collab/permissions/check")
def permissions_check():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    room = request.args.get("room", "")
    user = request.args.get("user", "")
    action = request.args.get("action", "read")
    return jsonify({"allowed": collab._permissions.check_permission(room, user, action)})


@bp.route("/api/collab/comments", methods=["GET", "POST"])
def comments():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        comment = collab._comments.add(
            data.get("target", ""), data.get("user", ""),
            data.get("content", ""), data.get("parent", "")
        )
        return jsonify(comment)
    target = request.args.get("target", "")
    return jsonify({"comments": collab._comments.get(target)})


@bp.route("/api/collab/versions", methods=["POST"])
def version_save():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    ver = collab._versions.save_version(
        data.get("doc", ""), data.get("content", ""),
        data.get("user", ""), data.get("message", "")
    )
    return jsonify(ver)


@bp.route("/api/collab/versions/history")
def version_history():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    doc = request.args.get("doc", "")
    return jsonify({"versions": collab._versions.get_history(doc)})


@bp.route("/api/collab/presence")
def presence():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"online": collab._presence.get_online_users()})


@bp.route("/api/collab/stats")
def collab_stats():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    room = request.args.get("room", "")
    return jsonify(collab._collab_stats.get_stats(room))
