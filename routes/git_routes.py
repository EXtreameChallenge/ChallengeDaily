"""P18-2: Git 集成 API 路由 — 仓库管理 + 代码产出报告"""
import logging
from datetime import date
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import git_integration

logger = logging.getLogger(__name__)
bp = Blueprint('git_integration', __name__)


@bp.route("/api/git/repositories", methods=["GET"])
def list_repos():
    """列出已配置的 git 仓库"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify({"repositories": git_integration.list_repositories()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/git/repositories", methods=["POST"])
def add_repo():
    """添加 git 仓库"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        path = (data.get("path") or "").strip()
        name = (data.get("name") or "").strip()
        enabled = bool(data.get("enabled", True))
        if not path:
            return jsonify({"error": "缺少 path"}), 400
        repo = git_integration.add_repository(path=path, name=name, enabled=enabled)
        return jsonify({"repository": repo}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"添加 git 仓库失败: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/api/git/repositories", methods=["DELETE"])
def remove_repo():
    """移除 git 仓库"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        path = (data.get("path") or "").strip()
        if not path:
            return jsonify({"error": "缺少 path"}), 400
        ok = git_integration.remove_repository(path)
        if not ok:
            return jsonify({"error": "仓库不存在"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/git/repositories/<path:p>", methods=["PUT"])
def update_repo(p: str):
    """更新 git 仓库配置（启用/禁用/重命名）"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        updated = git_integration.update_repository(p, **data)
        if not updated:
            return jsonify({"error": "仓库不存在"}), 404
        return jsonify({"repository": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/git/commits")
def get_commits():
    """查询仓库提交记录（参数：repo_path, since, until, limit）"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        repo_path = request.args.get("repo_path", "").strip()
        since = request.args.get("since", "")
        until = request.args.get("until", "")
        limit = request.args.get("limit", "100", type=int)
        if not repo_path:
            return jsonify({"error": "缺少 repo_path"}), 400
        limit = max(1, min(limit, 500))
        commits = git_integration.get_commits(repo_path, since_date=since or None,
                                              until_date=until or None, limit=limit)
        return jsonify({"commits": commits, "count": len(commits)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/git/code-report")
def code_report():
    """获取指定日期（默认今天）的代码产出报告"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        target = request.args.get("date", "")
        report = git_integration.generate_code_report(target or None)
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/git/weekly-report")
def weekly_report():
    """获取最近 7 天的代码产出汇总"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        end = request.args.get("end_date", "")
        report = git_integration.generate_weekly_code_report(end or None)
        return jsonify(report)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
