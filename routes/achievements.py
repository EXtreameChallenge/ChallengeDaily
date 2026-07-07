"""成就系统 API"""
from flask import Blueprint, jsonify
import db

bp = Blueprint('achievements', __name__, url_prefix='/api/achievements')


@bp.route('', methods=['GET'])
def list_achievements():
    achievements = db.get_achievements()
    return jsonify({"achievements": achievements})


@bp.route('/check', methods=['POST'])
def check_achievements():
    """检查并解锁新成就"""
    newly_unlocked = db.check_and_unlock_achievements()
    return jsonify({"unlocked": newly_unlocked})


@bp.route('/quote', methods=['GET'])
def get_quote():
    """获取随机格言"""
    return jsonify({"quote": db.get_random_quote()})
