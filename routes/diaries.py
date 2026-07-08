"""每日日记 API（融入GoalDay一日一页+心情+翻页）"""
from flask import Blueprint, request, jsonify
from datetime import date
import db
from routes.deps import validate_date

bp = Blueprint('diaries', __name__, url_prefix='/api/diaries')


@bp.route('/<diary_date>', methods=['GET'])
def get_diary_route(diary_date):
    """获取某天日记"""
    # diary_date 格式校验：防止非法字符串直接落库
    if not validate_date(diary_date):
        return jsonify({"error": "diary_date 日期格式无效，需 YYYY-MM-DD"}), 400
    diary = db.get_diary(diary_date)
    return jsonify({"diary": diary})


@bp.route('', methods=['POST'])
def save_diary():
    """保存/更新日记（一日一页）"""
    data = request.get_json(force=True, silent=True) or {}
    diary_date = data.get('diary_date', date.today().isoformat())
    # diary_date 格式校验：防止非法字符串直接落库
    if not validate_date(diary_date):
        return jsonify({"error": "diary_date 日期格式无效，需 YYYY-MM-DD"}), 400
    db.upsert_diary(
        diary_date=diary_date,
        mood=data.get('mood', ''),
        weather=data.get('weather', ''),
        content=data.get('content', ''),
        tags=data.get('tags', ''),
        highlights=data.get('highlights', ''),
        gratitude=data.get('gratitude', ''),
    )
    return jsonify({"status": "ok", "diary_date": diary_date})


@bp.route('/list', methods=['GET'])
def list_diaries():
    """日记列表（翻页浏览）"""
    try:
        limit = int(request.args.get('limit', 30))
        if limit < 1 or limit > 200:
            limit = 30
    except (TypeError, ValueError):
        limit = 30
    diaries = db.get_diaries(limit)
    dates = db.get_diary_dates()
    return jsonify({"diaries": diaries, "dates": dates})
