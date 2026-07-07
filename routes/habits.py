"""习惯追踪 API"""
from flask import Blueprint, request, jsonify
import db

bp = Blueprint('habits', __name__, url_prefix='/api/habits')


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
    hid = db.insert_habit(name, int(data.get('target_count', 1)), data.get('period', 'daily'), data.get('color', '#7B68EE'))
    return jsonify({"status": "ok", "id": hid})


@bp.route('/<int:hid>/log', methods=['POST'])
def log_habit_route(hid):
    data = request.get_json(force=True, silent=True) or {}
    log_date = data.get('log_date')
    count = int(data.get('count', 1))
    db.log_habit(hid, log_date, count)
    return jsonify({"status": "ok"})


@bp.route('/<int:hid>', methods=['DELETE'])
def delete_habit_route(hid):
    db.delete_habit(hid)
    return jsonify({"status": "ok"})
