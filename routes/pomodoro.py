"""番茄钟专注记录 API"""
from flask import Blueprint, request, jsonify
from routes.deps import check_token
import db
from datetime import datetime

bp = Blueprint('pomodoro', __name__, url_prefix='/api/pomodoro')


@bp.route('/start', methods=['POST'])
def start_pomodoro():
    """开始番茄钟"""
    data = request.get_json(force=True, silent=True) or {}
    task = data.get('task', '').strip()
    duration_min = int(data.get('duration_min', 25))
    category = data.get('category', '开发')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    session_id = db.insert_pomodoro_session(
        start_time=now, end_time=None, duration_min=duration_min,
        task=task, category=category, status='running', interrupted_count=0, source='manual'
    )
    return jsonify({"status": "ok", "id": session_id, "start_time": now})


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
