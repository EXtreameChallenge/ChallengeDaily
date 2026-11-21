"""Agent 系统管理 API

提供 Agent 运行指标、技能库审核、审计日志、工作流任务状态等端点，
供前端 Agent 控制台展示与运维。
"""
import logging
import importlib.util
from flask import Blueprint, jsonify, request

import config
import routes.deps as deps
import agent_db

logger = logging.getLogger(__name__)
bp = Blueprint('agent_routes', __name__, url_prefix='/api/agent')


@bp.route('/status', methods=['GET'])
def agent_status():
    """返回当前 Agent 运行形态（引擎/角色/推理强度/团队状态）。

    engine 以运行时配置为准；配置 agno 但依赖不可用时如实返回 classic，
    避免前端展示一个并未运行的引擎。
    """
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    settings = config.load_settings()
    engine = str(settings.get('agent_engine') or config.AGENT_ENGINE or 'classic')
    if engine not in ('agno', 'classic'):
        engine = 'classic'
    if engine == 'agno' and importlib.util.find_spec('agno') is None:
        engine = 'classic'
    rounds = int(getattr(config, 'AGENT_MAX_TOOL_ROUNDS', 5) or 5)
    reasoning_level = 'low' if rounds <= 2 else 'high' if rounds > 5 else 'medium'
    return jsonify({
        'engine': engine,
        'role': 'single',
        'reasoning_level': reasoning_level,
        'team_active': False,
        'max_tool_rounds': rounds,
    })



@bp.route('/metrics', methods=['GET'])
def get_metrics():
    """返回 Agent 运行指标：总调用数、工具分布、平均耗时、失败率、技能数等。"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        metrics = agent_db.get_agent_metrics()
        # 失败率 = 危险/确认调用占比的近似值（审计表未单独存 error 标志，这里给聚合视图）
        return jsonify({"metrics": metrics})
    except Exception as e:
        logger.error(f"获取 Agent 指标失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/skills', methods=['GET'])
def list_skills():
    """技能库列表，支持 ?status=pending/approved/rejected 过滤。"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        status = request.args.get('status', '').strip() or None
        skills = agent_db.list_skills(status=status)
        return jsonify({"skills": skills, "count": len(skills)})
    except Exception as e:
        logger.error(f"查询技能库失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/skills/<skill_id>/approve', methods=['POST'])
def approve_skill(skill_id):
    """审核通过一个技能（pending → approved）。"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        ok = agent_db.update_skill_status(skill_id, "approved")
        return jsonify({"status": "ok" if ok else "noop"})
    except Exception as e:
        logger.error(f"审核技能失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/skills/<skill_id>/toggle', methods=['POST'])
def toggle_skill(skill_id):
    """启用/禁用一个技能：approved ⇄ rejected，返回切换后的 enabled 状态。"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        skill = agent_db.get_skill(skill_id)
        if not skill:
            return jsonify({"error": "skill_not_found"}), 404
        enabled_now = skill.get('status') == 'approved'
        target_status = 'rejected' if enabled_now else 'approved'
        ok = agent_db.update_skill_status(skill_id, target_status)
        return jsonify({
            "status": "ok" if ok else "noop",
            "enabled": not enabled_now if ok else enabled_now,
            "skill_status": target_status if ok else skill.get('status'),
        })
    except Exception as e:
        logger.error(f"切换技能状态失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/skills/<skill_id>', methods=['DELETE'])
def remove_skill(skill_id):
    """删除一个技能。"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        agent_db.delete_skill(skill_id)
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"删除技能失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/audit', methods=['GET'])
def audit_logs():
    """工具调用审计日志，支持 ?tool_name=xx&limit=100。"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        try:
            limit = int(request.args.get('limit', '100'))
        except ValueError:
            limit = 100
        tool_name = request.args.get('tool_name', '').strip() or None
        logs = agent_db.get_audit_logs(limit=limit, tool_name=tool_name)
        return jsonify({"logs": logs, "count": len(logs)})
    except Exception as e:
        logger.error(f"查询审计日志失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/tasks', methods=['GET'])
def list_tasks():
    """工作流任务状态列表，支持 ?status=running/paused/completed/failed。"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        status = request.args.get('status', '').strip() or None
        tasks = agent_db.list_task_states(status=status)
        return jsonify({"tasks": tasks, "count": len(tasks)})
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/tasks/<task_id>/resume', methods=['POST'])
def resume_task(task_id):
    """恢复一个 paused/failed 的工作流任务（状态置回 running）。"""
    if not deps.check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        ok = agent_db.update_task_state(task_id, status="running")
        return jsonify({"status": "ok" if ok else "not_found"})
    except Exception as e:
        logger.error(f"恢复任务失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500
