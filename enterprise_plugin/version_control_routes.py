"""P251-P259: 版本控制系统 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import version_control as vc

bp = Blueprint('version_control', __name__)


@bp.route("/api/vc/commit", methods=["POST"])
def vc_commit():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    cid = vc._commit_mgr.commit(data.get("message", ""), data.get("author", ""), data.get("files"))
    return jsonify({"commit_id": cid})


@bp.route("/api/vc/log")
def vc_log():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    limit = int(request.args.get("limit", 50))
    return jsonify({"log": vc._commit_mgr.get_log(limit)})


@bp.route("/api/vc/branches")
def vc_branches():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"branches": vc._branch_mgr.list_branches(), "head": vc._repo._head})


@bp.route("/api/vc/branches/create", methods=["POST"])
def vc_branch_create():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    ok = vc._branch_mgr.create(data.get("name", ""), data.get("from", ""))
    return jsonify({"status": "ok" if ok else "exists"})


@bp.route("/api/vc/branches/switch", methods=["POST"])
def vc_branch_switch():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    ok = vc._branch_mgr.switch(data.get("name", ""))
    return jsonify({"status": "ok" if ok else "not_found"})


@bp.route("/api/vc/merge", methods=["POST"])
def vc_merge():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(vc.MergeStrategy.merge(vc._repo, data.get("source", ""), data.get("target", "")))


@bp.route("/api/vc/staging", methods=["GET", "POST"])
def vc_staging():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        if data.get("action") == "commit":
            cid = vc._staging.commit_staged(data.get("message", ""), data.get("author", ""))
            return jsonify({"commit_id": cid})
        vc._staging.add(data.get("file", ""), data.get("content", ""))
        return jsonify({"status": "ok"})
    return jsonify({"staged": vc._staging.get_staged()})


@bp.route("/api/vc/diff", methods=["POST"])
def vc_diff():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    if data.get("commit1") and data.get("commit2"):
        return jsonify(vc._diff_engine.diff_commits(vc._repo, data["commit1"], data["commit2"]))
    result = vc._diff_engine.diff_files(data.get("content1", ""), data.get("content2", ""))
    return jsonify(result)


@bp.route("/api/vc/tags", methods=["GET", "POST"])
def vc_tags():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        ok = vc._tag_mgr.create(data.get("name", ""), data.get("commit", ""), data.get("message", ""))
        return jsonify({"status": "ok" if ok else "error"})
    return jsonify({"tags": vc._tag_mgr.list_tags()})


@bp.route("/api/vc/changes")
def vc_changes():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"changes": vc._changeset.get_recent()})


@bp.route("/api/vc/conflicts/detect", methods=["POST"])
def vc_conflicts_detect():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    return jsonify({"conflicts": vc._conflict_marker.detect_conflicts(data.get("content", ""))})
