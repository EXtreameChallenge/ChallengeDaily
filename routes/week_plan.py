"""周计划 API（月/周/日三级层级 + 拖拽分配 + 番茄数据条）"""
from flask import Blueprint, request, jsonify
from datetime import date, datetime, timedelta
import logging
import db
from routes.deps import safe_error, validate_date

logger = logging.getLogger(__name__)

bp = Blueprint('week_plan', __name__, url_prefix='/api/week-plan')


def _week_start_of(d: date) -> str:
    """ISO 8601 周一 YYYY-MM-DD"""
    return (d - timedelta(days=d.weekday())).strftime('%Y-%m-%d')


def _safe_int(value, default):
    """安全的 int 转换：非法值返回 default，避免 ValueError 直接 500"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@bp.route('/month/<month_key>', methods=['GET'])
def get_month(month_key: str):
    """获取月任务及其下所有周任务进度"""
    try:
        tasks = db.get_month_tasks(month_key)
        meta = db.get_plan_meta('month', month_key) or {}
        return jsonify({
            'month_key': month_key,
            'month_tasks': tasks,
            'title': meta.get('title', ''),
            'goal': meta.get('goal', ''),
        })
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


@bp.route('/week/<week_start>', methods=['GET'])
def get_week(week_start: str):
    """获取周任务+七日日任务"""
    try:
        data = db.get_week_tasks(week_start)
        meta = db.get_plan_meta('week', week_start) or {}
        return jsonify({
            **data,
            'title': meta.get('title', ''),
            'goal': meta.get('goal', ''),
        })
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


@bp.route('/unassigned', methods=['GET'])
def unassigned():
    """获取待分配区任务"""
    try:
        tasks = db.get_unassigned_todos()
        return jsonify({'todos': tasks})
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


@bp.route('/assign', methods=['POST'])
def assign():
    """拖拽分配任务到某天/某周/升级层级，可选设置计划开始时刻"""
    data = request.get_json(force=True, silent=True) or {}
    todo_id = data.get('todo_id')
    if not todo_id:
        return jsonify({'error': 'todo_id 必填'}), 400
    assigned_date = data.get('assigned_date')
    week_start = data.get('week_start')
    task_level = data.get('task_level', 'day')
    plan_start_min = data.get('plan_start_min')  # 可选：分钟偏移（540=9:00）
    if plan_start_min is not None:
        plan_start_min = _safe_int(plan_start_min, None)
    try:
        db.assign_todo(_safe_int(todo_id, 0), assigned_date, week_start, task_level, plan_start_min)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


@bp.route('/unassign', methods=['POST'])
def unassign_route():
    """移回待分配区"""
    data = request.get_json(force=True, silent=True) or {}
    todo_id = data.get('todo_id')
    if not todo_id:
        return jsonify({'error': 'todo_id 必填'}), 400
    try:
        db.unassign_todo(_safe_int(todo_id, 0))
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


@bp.route('/task-time', methods=['PUT'])
def update_task_time():
    """更新任务的计划开始时刻（甘特图拖拽调时间用）"""
    data = request.get_json(force=True, silent=True) or {}
    todo_id = data.get('todo_id')
    if not todo_id:
        return jsonify({'error': 'todo_id 必填'}), 400
    plan_start_min = data.get('plan_start_min')  # null 表示清除
    if plan_start_min is not None:
        plan_start_min = _safe_int(plan_start_min, None)
    try:
        db.update_todo(_safe_int(todo_id, 0), plan_start_min=plan_start_min)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


@bp.route('/split', methods=['POST'])
def split():
    """月任务拆解为周任务（或周任务拆解为日任务）"""
    data = request.get_json(force=True, silent=True) or {}
    parent_id = data.get('parent_id')
    title = (data.get('title') or '').strip()
    week_start = data.get('week_start')
    if not parent_id or not title or not week_start:
        return jsonify({'error': 'parent_id/title/week_start 必填'}), 400
    # week_start 格式校验：防止非法字符串直接落库
    if not validate_date(week_start):
        return jsonify({'error': 'week_start 日期格式无效，需 YYYY-MM-DD'}), 400
    try:
        new_id = db.split_task(
            parent_id=_safe_int(parent_id, 0),
            title=title,
            week_start=week_start,
            task_level=data.get('task_level', 'week'),
            category=data.get('category', '开发'),
            mode=data.get('mode', 'timer'),
            target_min=_safe_int(data.get('target_min', 25), 25),
            priority=_safe_int(data.get('priority', 2), 2),
        )
        return jsonify({'status': 'ok', 'id': new_id})
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


@bp.route('/meta', methods=['PUT'])
def update_meta():
    """更新周/月元数据（标题、目标）"""
    data = request.get_json(force=True, silent=True) or {}
    plan_type = data.get('plan_type')
    plan_key = data.get('plan_key')
    if plan_type not in ('month', 'week') or not plan_key:
        return jsonify({'error': 'plan_type(month|week) 和 plan_key 必填'}), 400
    try:
        db.update_plan_meta(
            plan_type=plan_type,
            plan_key=plan_key,
            title=data.get('title', ''),
            goal=data.get('goal', ''),
        )
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


def _task_completed_day(task: dict) -> str | None:
    """任务完成日期：优先 completed_at，缺失时回退 updated_at 的日期部分。"""
    if task.get('status') != 'completed':
        return None
    for key in ('completed_at', 'updated_at'):
        raw = str(task.get(key) or '')
        if len(raw) >= 10 and validate_date(raw[:10]):
            return raw[:10]
    return None


@bp.route('/sprint/<week_start>', methods=['GET'])
def sprint(week_start: str):
    """Sprint 视图：本周任务统计 + 燃尽图 + 每日完成量。

    全部来自 todos 真实状态；未来日期不编造 actual 值（返回 null）。
    """
    if not validate_date(week_start):
        return jsonify({'error': 'week_start 日期格式无效，需 YYYY-MM-DD'}), 400
    try:
        data = db.get_week_tasks(week_start)
        week_tasks = data.get('week_tasks') or []
        day_map = data.get('day_tasks') or {}
        dates = data.get('dates') or []
        all_tasks = list(week_tasks) + [t for tasks in day_map.values() for t in tasks]

        total_tasks = len(all_tasks)
        completed_tasks = sum(1 for t in all_tasks if t.get('status') == 'completed')
        remaining_tasks = max(0, total_tasks - completed_tasks)
        completion_rate = round(completed_tasks / total_tasks * 100, 1) if total_tasks else 0
        today_str = date.today().strftime('%Y-%m-%d')

        daily_completion = []
        for day in dates:
            day_tasks = day_map.get(day) or []
            daily_completion.append({
                'date': day,
                'total': len(day_tasks),
                'completed': sum(1 for t in day_tasks if t.get('status') == 'completed'),
            })

        completed_days = [_task_completed_day(t) for t in all_tasks]
        burndown = []
        for idx, day in enumerate(dates):
            ideal = round(total_tasks - (total_tasks * idx / max(1, len(dates) - 1)), 1)
            actual = None
            if day <= today_str:
                completed_by_day = sum(
                    1 for done_day in completed_days if done_day and done_day <= day
                )
                actual = max(0, total_tasks - completed_by_day)
            burndown.append({'date': day, 'ideal': ideal, 'actual': actual})

        return jsonify({
            'week_start': week_start,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'remaining_tasks': remaining_tasks,
            'completion_rate': completion_rate,
            'burndown': burndown,
            'daily_completion': daily_completion,
        })
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


@bp.route('/sprint-goal/<week_start>', methods=['GET'])
def get_sprint_goal(week_start: str):
    """读取本周 Sprint 目标（复用周计划 goal 字段，不额外造存储）。"""
    if not validate_date(week_start):
        return jsonify({'error': 'week_start 日期格式无效，需 YYYY-MM-DD'}), 400
    meta = db.get_plan_meta('week', week_start) or {}
    return jsonify({'week_start': week_start, 'goal_text': meta.get('goal', '')})


@bp.route('/sprint-goal/<week_start>', methods=['POST'])
def save_sprint_goal(week_start: str):
    """保存本周 Sprint 目标到周计划元数据。"""
    if not validate_date(week_start):
        return jsonify({'error': 'week_start 日期格式无效，需 YYYY-MM-DD'}), 400
    data = request.get_json(force=True, silent=True) or {}
    goal_text = str(data.get('goal_text') or '').strip()
    if len(goal_text) > 500:
        return jsonify({'error': 'goal_text 最长 500 字'}), 400
    try:
        meta = db.get_plan_meta('week', week_start) or {}
        db.update_plan_meta(
            plan_type='week',
            plan_key=week_start,
            title=meta.get('title', ''),
            goal=goal_text,
        )
        return jsonify({'status': 'ok', 'goal_text': goal_text})
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


@bp.route('/stats', methods=['GET'])
def stats():
    """本周/本月数据条统计"""
    range_type = request.args.get('range', 'week')
    date_str = request.args.get('date')
    try:
        if range_type == 'month':
            if not date_str:
                date_str = date.today().strftime('%Y-%m')
            return jsonify(db.get_month_plan_stats(date_str))
        else:
            # week
            if date_str:
                d = datetime.strptime(date_str, '%Y-%m-%d').date()
            else:
                d = date.today()
            week_start = _week_start_of(d)
            return jsonify(db.get_week_plan_stats(week_start))
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


@bp.route('/today', methods=['GET'])
def today():
    """获取今日日任务（Focus 页和 Overview 页使用）"""
    try:
        today_str = date.today().strftime('%Y-%m-%d')
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM todos WHERE task_level='day' AND assigned_date=? ORDER BY priority ASC, sort_order ASC",
                (today_str,)
            ).fetchall()
        return jsonify({'todos': [dict(r) for r in rows], 'date': today_str})
    except Exception as e:
        return jsonify({'error': safe_error(e, "操作失败")}), 500


# 导入 datetime 用于 stats 端点


@bp.route('/auto-split', methods=['POST'])
def auto_split():
    """AI 拆解月目标为周待办草案（不直接写入，返回给用户确认）

    body: {goal_title, goal_description, week_start}
    返回：{draft_tasks: [...], status: "draft"} 或 {error}
    """
    data = request.get_json(silent=True) or {}
    goal_title = (data.get('goal_title') or '').strip()
    goal_description = (data.get('goal_description') or '').strip()
    week_start = data.get('week_start') or ''
    if not goal_title:
        return jsonify({'error': '目标标题不能为空'}), 400
    try:
        from ai_client import _get_client
        from prompt import _sanitize_user_input
        import json as _json

        client = _get_client()
        prompt = (
            f"请将以下月度目标拆解为 5-7 个周待办任务（JSON 数组格式）：\n"
            f"目标：{_sanitize_user_input(goal_title)}\n"
            f"描述：{_sanitize_user_input(goal_description, 500)}\n"
            f"周开始日期：{week_start}\n\n"
            "要求：\n"
            "1. 每个待办包含 title（任务名）、target_min（预计分钟数）、category（分类）、day（1-5 表示周一到周五）\n"
            "2. 任务粒度合理（每个 25-100 分钟可完成）\n"
            "3. 按 5 个工作日分配\n\n"
            '返回格式：[{"title":"任务1","target_min":60,"category":"开发","day":1},...]'
        )
        response = client.chat.completions.create(
            model='glm-4-flash',
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=1000,
            temperature=0.7,
        )
        content = response.choices[0].message.content or ''
        # 提取 JSON 数组
        start = content.find('[')
        end = content.rfind(']') + 1
        if start >= 0 and end > start:
            tasks = _json.loads(content[start:end])
            return jsonify({'draft_tasks': tasks, 'status': 'draft'})
        return jsonify({'error': 'AI 返回格式错误', 'raw': content[:200]}), 500
    except Exception as e:
        logger.error(f"AI 拆解失败: {e}", exc_info=True)
        return jsonify({'error': safe_error(e, '拆解失败')}), 500
