"""习惯追踪 API"""
from flask import Blueprint, request, jsonify
import db

bp = Blueprint('habits', __name__, url_prefix='/api/habits')

# period 枚举校验
_VALID_PERIODS = ('daily', 'weekly', 'monthly')
# target_count 合理区间
_MIN_TARGET_COUNT = 1
_MAX_TARGET_COUNT = 100


def _safe_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@bp.route('', methods=['GET'])
def list_habits():
    habits = db.get_habits()
    logs = db.get_habit_logs(days=30)
    return jsonify({"habits": habits, "logs": logs})


@bp.route('', methods=['POST'])
def create_habit():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"error": "习惯名称不能为空"}), 400
    # period 枚举校验
    period = data.get('period', 'daily')
    if period not in _VALID_PERIODS:
        return jsonify({"error": f"period 必须是 {','.join(_VALID_PERIODS)} 之一"}), 400
    # target_count 范围校验
    target_count = _safe_int(data.get('target_count', 1), 1)
    if target_count < _MIN_TARGET_COUNT or target_count > _MAX_TARGET_COUNT:
        return jsonify({"error": f"target_count 必须在 {_MIN_TARGET_COUNT}-{_MAX_TARGET_COUNT} 之间"}), 400
    hid = db.insert_habit(name, target_count, period, data.get('color', '#7B68EE'))
    return jsonify({"status": "ok", "id": hid})


@bp.route('/<int:hid>/log', methods=['POST'])
def log_habit_route(hid):
    data = request.get_json(force=True, silent=True) or {}
    log_date = data.get('log_date')
    count = _safe_int(data.get('count', 1), 1)
    db.log_habit(hid, log_date, count)
    return jsonify({"status": "ok"})


@bp.route('/<int:hid>', methods=['DELETE'])
def delete_habit_route(hid):
    db.delete_habit(hid)
    return jsonify({"status": "ok"})
