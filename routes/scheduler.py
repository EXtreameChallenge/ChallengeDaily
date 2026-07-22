"""日程调度 API — V35"""
import json
import logging
from datetime import date

from flask import Blueprint, request, jsonify

import db

logger = logging.getLogger(__name__)

bp = Blueprint('scheduler', __name__, url_prefix='/api/scheduler')


@bp.route('/suggest', methods=['GET'])
def suggest_schedule():
    """获取 AI 排程建议（降级 fallback）"""
    try:
        import scheduler_service
        result = scheduler_service.generate_schedule()

        # 映射字段名：后端 start/end/task_title → 前端 time_start/time_end/task
        schedule = []
        for block in result.get('schedule', []):
            schedule.append({
                'time_start': block.get('start', ''),
                'time_end': block.get('end', ''),
                'task': block.get('task_title', ''),
                'type': block.get('type', 'normal'),
            })

        return jsonify({
            "status": "ok",
            "schedule": schedule,
            "source": result.get('source', 'fallback'),
            "energy_curve": result.get('energy_curve', []),
        })
    except Exception as e:
        logger.warning(f"排程建议失败: {e}")
        return jsonify({"status": "ok", "schedule": [], "source": "error"})


@bp.route('/adopt', methods=['POST'])
def adopt_schedule():
    """采纳排程：保存到 daily_plans"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        schedule = data.get('schedule', [])
        today_str = date.today().isoformat()

        plan_json = json.dumps(schedule, ensure_ascii=False)
        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO daily_plans (date, plan_json, mit_task, focus_target_min, limits_json, status, adopted_ai) "
                "VALUES (?,?,?,?,?,?,?)",
                (today_str, plan_json, '', 240, '{}', 'confirmed', 1)
            )
            conn.commit()

        return jsonify({"status": "ok", "date": today_str})
    except Exception as e:
        logger.warning(f"采纳排程失败: {e}")
        return jsonify({"error": str(e)}), 500
