"""番茄钟专注记录 API（支持连续执行 + 任务深度关联）"""
from flask import Blueprint, request, jsonify
from routes.deps import check_token
import db
from datetime import datetime

bp = Blueprint('pomodoro', __name__, url_prefix='/api/pomodoro')

# 大番茄: 工作25min + 休息5min  |  小番茄: 工作20min + 休息10min
POMODORO_SIZES = {
    'big':   {'work': 25, 'short_break': 5, 'long_break': 15},
    'small': {'work': 20, 'short_break': 10, 'long_break': 15},
}
LONG_BREAK_INTERVAL = 4  # 每4个番茄一次长休息


@bp.route('/start', methods=['POST'])
def start_pomodoro():
    """开始番茄钟（支持读取关联任务的预估番茄数和大小）"""
    data = request.get_json(force=True, silent=True) or {}
    task = data.get('task', '').strip()
    duration_min = int(data.get('duration_min', 25))
    category = data.get('category', '开发')
    todo_id = data.get('todo_id')
    pomodoro_index = int(data.get('pomodoro_index', 1))  # 当前第几个番茄（连续执行）
    total_pomodoros = int(data.get('total_pomodoros', 1))  # 计划番茄总数

    # 如果关联了 todo，自动读取其 estimated_pomodoros 和 pomodoro_size
    if todo_id:
        with db.get_conn() as conn:
            todo = conn.execute("SELECT estimated_pomodoros, pomodoro_size, category, target_min FROM todos WHERE id=?", (todo_id,)).fetchone()
            if todo:
                total_pomodoros = todo['estimated_pomodoros'] or 1
                size_config = POMODORO_SIZES.get(todo['pomodoro_size'] or 'big', POMODORO_SIZES['big'])
                duration_min = size_config['work']
                if not category or category == '开发':
                    category = todo['category'] or '开发'

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    session_id = db.insert_pomodoro_session(
        start_time=now, end_time=None, duration_min=duration_min,
        task=task, category=category, status='running', interrupted_count=0, source='manual'
    )
    # 关联 todo_id + pomodoro_index/total_pomodoros
    update_data = {}
    if todo_id:
        update_data['todo_id'] = int(todo_id)
    if pomodoro_index > 1 or total_pomodoros > 1:
        update_data['pomodoro_index'] = pomodoro_index
        update_data['total_pomodoros'] = total_pomodoros
    if update_data:
        db.update_pomodoro_session(session_id, **update_data)

    return jsonify({
        "status": "ok", "id": session_id, "start_time": now,
        "todo_id": todo_id, "duration_min": duration_min,
        "pomodoro_index": pomodoro_index, "total_pomodoros": total_pomodoros,
    })


@bp.route('/stop', methods=['POST'])
def stop_pomodoro():
    """结束番茄钟"""
    data = request.get_json(force=True, silent=True) or {}
    session_id = data.get('id')
    status = data.get('status', 'completed')
    interrupted_count = int(data.get('interrupted_count', 0))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if session_id:
        db.update_pomodoro_session(session_id, end_time=now, status=status, interrupted_count=interrupted_count)
        # 完成时自动回写 todo 进度（V19 联动）
        if status == 'completed':
            with db.get_conn() as conn:
                row = conn.execute("SELECT todo_id, duration_min FROM pomodoro_sessions WHERE id=?", (session_id,)).fetchone()
                if row and row['todo_id']:
                    db.update_todo_progress(row['todo_id'], row['duration_min'])
    return jsonify({"status": "ok", "end_time": now})


@bp.route('/sessions', methods=['GET'])
def list_sessions():
    """查询番茄钟记录"""
    date_str = request.args.get('date')
    sessions = db.get_pomodoro_sessions(date_str)
    return jsonify({"sessions": sessions})


@bp.route('/stats', methods=['GET'])
def pomodoro_stats():
    """专注统计"""
    range_type = request.args.get('range', 'week')
    stats = db.get_pomodoro_stats(range_type)
    today = db.get_pomodoro_today_count()
    streak = db.get_pomodoro_streak()
    return jsonify({"stats": stats, "today": today, "streak": streak})


@bp.route('/today', methods=['GET'])
def pomodoro_today():
    """今日专注统计"""
    return jsonify(db.get_pomodoro_today_count())


@bp.route('/config', methods=['GET'])
def pomodoro_config():
    """获取番茄钟配置（大小番茄的工作/休息时长）"""
    return jsonify({
        "sizes": POMODORO_SIZES,
        "long_break_interval": LONG_BREAK_INTERVAL,
    })
