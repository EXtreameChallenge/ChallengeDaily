"""周计划 API（月/周/日三级层级 + 拖拽分配 + 番茄数据条）"""
from flask import Blueprint, request, jsonify
from datetime import date, datetime, timedelta
import db

bp = Blueprint('week_plan', __name__, url_prefix='/api/week-plan')


def _week_start_of(d: date) -> str:
    """ISO 8601 周一 YYYY-MM-DD"""
    return (d - timedelta(days=d.weekday())).strftime('%Y-%m-%d')


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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


@bp.route('/unassigned', methods=['GET'])
def unassigned():
    """获取待分配区任务"""
    try:
        tasks = db.get_unassigned_todos()
        return jsonify({'todos': tasks})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/assign', methods=['POST'])
def assign():
    """拖拽分配任务到某天/某周/升级层级"""
    data = request.get_json(force=True, silent=True) or {}
    todo_id = data.get('todo_id')
    if not todo_id:
        return jsonify({'error': 'todo_id 必填'}), 400
    assigned_date = data.get('assigned_date')
    week_start = data.get('week_start')
    task_level = data.get('task_level', 'day')
    try:
        db.assign_todo(int(todo_id), assigned_date, week_start, task_level)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/unassign', methods=['POST'])
def unassign_route():
    """移回待分配区"""
    data = request.get_json(force=True, silent=True) or {}
    todo_id = data.get('todo_id')
    if not todo_id:
        return jsonify({'error': 'todo_id 必填'}), 400
    try:
        db.unassign_todo(int(todo_id))
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/split', methods=['POST'])
def split():
    """月任务拆解为周任务（或周任务拆解为日任务）"""
    data = request.get_json(force=True, silent=True) or {}
    parent_id = data.get('parent_id')
    title = (data.get('title') or '').strip()
    week_start = data.get('week_start')
    if not parent_id or not title or not week_start:
        return jsonify({'error': 'parent_id/title/week_start 必填'}), 400
    try:
        new_id = db.split_task(
            parent_id=int(parent_id),
            title=title,
            week_start=week_start,
            task_level=data.get('task_level', 'week'),
            category=data.get('category', '开发'),
            mode=data.get('mode', 'timer'),
            target_min=int(data.get('target_min', 25)),
            priority=int(data.get('priority', 2)),
        )
        return jsonify({'status': 'ok', 'id': new_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


# 导入 datetime 用于 stats 端点

