"""待办清单 API（融入GoalDay打卡清单自动进度）"""
from flask import Blueprint, request, jsonify
from datetime import datetime, date
import db

bp = Blueprint('todos', __name__, url_prefix='/api/todos')


@bp.route('', methods=['GET'])
def list_todos():
    status = request.args.get('status', 'all')
    todos = db.get_todos(status if status != 'all' else None)
    return jsonify({"todos": todos})


@bp.route('', methods=['POST'])
def create_todo():
    data = request.get_json(force=True, silent=True) or {}
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "标题不能为空"}), 400
    todo_id = db.insert_todo(
        title=title,
        category=data.get('category', '开发'),
        mode=data.get('mode', 'timer'),
        target_min=int(data.get('target_min', 25)),
        repeat_type=data.get('repeat_type', 'none'),
        repeat_days=data.get('repeat_days', ''),
        due_date=data.get('due_date'),
        priority=int(data.get('priority', 2)),
    )
    return jsonify({"status": "ok", "id": todo_id})


@bp.route('/<int:todo_id>', methods=['PUT'])
def update_todo_route(todo_id):
    data = request.get_json(force=True, silent=True) or {}
    # 如果标记为完成，记录完成时间
    if data.get('status') == 'completed' and 'completed_at' not in data:
        data['completed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    db.update_todo(todo_id, **data)
    return jsonify({"status": "ok"})


@bp.route('/<int:todo_id>', methods=['DELETE'])
def delete_todo_route(todo_id):
    db.delete_todo(todo_id)
    return jsonify({"status": "ok"})


@bp.route('/<int:todo_id>/add-progress', methods=['POST'])
def add_progress(todo_id):
    """添加专注进度（GoalDay打卡清单自动记录）"""
    data = request.get_json(force=True, silent=True) or {}
    minutes = int(data.get('minutes', 25))
    db.update_todo_progress(todo_id, minutes)
    return jsonify({"status": "ok"})
