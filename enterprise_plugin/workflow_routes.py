"""P201-P209: 自动化工作流引擎 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import automation_workflow as aw

bp = Blueprint('workflow', __name__)


@bp.route("/api/workflow/list")
def workflow_list():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"workflows": aw._engine.list_workflows()})


@bp.route("/api/workflow/run", methods=["POST"])
def workflow_run():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(aw._engine.run(data.get("name", ""), data.get("context", {})))


@bp.route("/api/workflow/define", methods=["POST"])
def workflow_define():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    wf = aw.Workflow(data.get("name", ""), data.get("description", ""))
    aw._engine.register(wf)
    return jsonify({"status": "ok"})


@bp.route("/api/workflow/history")
def workflow_history():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"history": aw._executor.get_history()})


@bp.route("/api/workflow/parallel", methods=["POST"])
def workflow_parallel():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    import json
    tasks_code = data.get("tasks", [])
    context = data.get("context", {})
    # 安全限制: 仅返回上下文信息,实际任务需服务端注册
    return jsonify({"status": "ok", "context": context, "task_count": len(tasks_code)})


@bp.route("/api/workflow/retry-policy", methods=["POST"])
def retry_policy_set():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    aw._retry_policy.set_policy(
        data.get("name", ""), data.get("max_retries", 3),
        data.get("backoff", 1.0), data.get("backoff_factor", 2.0),
        data.get("max_backoff", 60.0)
    )
    return jsonify({"status": "ok"})


@bp.route("/api/workflow/schedules")
def schedules_list():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"schedules": aw._scheduler.list_schedules()})


@bp.route("/api/workflow/schedules/add", methods=["POST"])
def schedules_add():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    aw._scheduler.schedule(
        data.get("name", ""), data.get("workflow", ""),
        data.get("cron", ""), data.get("delay", 0),
        data.get("repeat", False), data.get("interval", 0)
    )
    return jsonify({"status": "ok"})


@bp.route("/api/workflow/schedules/toggle", methods=["POST"])
def schedules_toggle():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    ok = aw._scheduler.toggle(data.get("name", ""), data.get("enabled", True))
    return jsonify({"status": "ok" if ok else "not_found"})
