"""倒数日 API"""
from flask import Blueprint, request, jsonify
import db

bp = Blueprint('countdowns', __name__, url_prefix='/api/countdowns')


@bp.route('', methods=['GET'])
def list_countdowns():
    countdowns = db.get_countdowns()
    return jsonify({"countdowns": countdowns})


@bp.route('', methods=['POST'])
def create_countdown():
    data = request.get_json(force=True, silent=True) or {}
    title = data.get('title', '').strip()
    target_date = data.get('target_date', '')
    color = data.get('color', '#7B68EE')
    if not title or not target_date:
        return jsonify({"error": "标题和目标日期不能为空"}), 400
    cid = db.insert_countdown(title, target_date, color)
    return jsonify({"status": "ok", "id": cid})


@bp.route('/<int:cid>', methods=['DELETE'])
def delete_countdown_route(cid):
    db.delete_countdown(cid)
    return jsonify({"status": "ok"})
