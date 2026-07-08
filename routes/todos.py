"""待办清单 API（融入GoalDay打卡清单自动进度）"""
from flask import Blueprint, request, jsonify
from datetime import datetime, date
import db

bp = Blueprint('todos', __name__, url_prefix='/api/todos')

# 枚举校验常量
_VALID_TASK_LEVELS = ('month', 'week', 'day')
_VALID_CATEGORIES = ('开发', '测试', '运维', '数据分析', '产品', '设计',
                     '管理', '文档', '会议', '沟通', '学习', '生活')
# target_min 合理区间：5-480 分钟
_MIN_TARGET_MIN = 5
_MAX_TARGET_MIN = 480


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
    # task_level 枚举校验
    task_level = data.get('task_level', 'day')
    if task_level not in _VALID_TASK_LEVELS:
        return jsonify({"error": f"task_level 必须是 {','.join(_VALID_TASK_LEVELS)} 之一"}), 400
    # category 枚举校验
    category = data.get('category', '开发')
    if category not in _VALID_CATEGORIES:
        return jsonify({"error": f"category 必须是预定义分类之一"}), 400
    # target_min 范围校验
    target_min = _safe_int(data.get('target_min', 25), 25)
    if target_min < _MIN_TARGET_MIN or target_min > _MAX_TARGET_MIN:
        return jsonify({"error": f"target_min 必须在 {_MIN_TARGET_MIN}-{_MAX_TARGET_MIN} 分钟之间"}), 400
    try:
        todo_id = db.insert_todo(
            title=title,
            category=category,
            mode=data.get('mode', 'timer'),
            target_min=target_min,
            repeat_type=data.get('repeat_type', 'none'),
            repeat_days=data.get('repeat_days', ''),
            due_date=data.get('due_date'),
            priority=_safe_int(data.get('priority', 2), 2),
            task_level=task_level,
            parent_id=data.get('parent_id'),
            assigned_date=data.get('assigned_date'),
            week_start=data.get('week_start'),
            month_key=data.get('month_key'),
        )
    except Exception as e:
        return jsonify({"error": "创建待办失败"}), 500
    # 如果传了层级相关字段，需在 INSERT 后 UPDATE（insert_todo 不支持这些字段）
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
    minutes = _safe_int(data.get('minutes', 25), 25)
    db.update_todo_progress(todo_id, minutes)
    return jsonify({"status": "ok"})
