"""P81-P89: DevOps 基础设施 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import devops_infra

bp = Blueprint('devops_routes', __name__)


@bp.route("/api/devops/health/full")
def devops_health_full():
    """P81: 综合健康检查"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(devops_infra.health_check_full())


@bp.route("/api/devops/metrics")
def devops_metrics():
    """P82: 性能指标"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(devops_infra.get_metrics())


@bp.route("/api/devops/errors")
def devops_errors():
    """P83: 错误统计"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(devops_infra.get_error_stats())


@bp.route("/api/devops/errors/clear", methods=["POST"])
def devops_errors_clear():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    devops_infra.clear_error_stats()
    return jsonify({"status": "ok"})


@bp.route("/api/devops/config", methods=["GET", "POST"])
def devops_config():
    """P84: 配置管理"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        results = []
        for k, v in data.items():
            results.append(devops_infra.update_config(k, v))
        return jsonify({"status": "ok", "updated": results})
    return jsonify(devops_infra.get_runtime_config())


@bp.route("/api/devops/resources")
def devops_resources():
    """P85: 资源监控"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({
        "current": devops_infra.sample_resources(),
        "history": devops_infra.get_resource_history()
    })


@bp.route("/api/devops/shutdown", methods=["POST"])
def devops_shutdown():
    """P86: 优雅关闭(需二次确认)"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    confirm = request.args.get("confirm", "")
    if confirm != "yes":
        return jsonify({"error": "需要 confirm=yes 参数"}), 400
    timeout = float(request.args.get("timeout", "10"))
    return jsonify(devops_infra.graceful_shutdown(timeout))


@bp.route("/api/devops/processes")
def devops_processes():
    """P87: 进程列表"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    filter_name = request.args.get("filter", "")
    return jsonify({"processes": devops_infra.list_processes(filter_name)})


@bp.route("/api/devops/manifest")
def devops_manifest():
    """P88: 部署清单"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(devops_infra.generate_deploy_manifest())


@bp.route("/api/devops/versions")
def devops_versions():
    """P89: 版本历史"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({
        "current": devops_infra.get_current_version(),
        "history": devops_infra.get_version_history()
    })


@bp.route("/api/devops/versions", methods=["POST"])
def devops_record_version():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    devops_infra.record_version(data.get("version", ""), data.get("notes", ""))
    return jsonify({"status": "ok"})
