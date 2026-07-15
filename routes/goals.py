"""长期目标管理 API（GoalDay集大成——年度/季度/月度目标 + 关键结果 + 进度追踪）"""
from flask import Blueprint, request, jsonify
import db
from routes.deps import validate_date

bp = Blueprint('goals', __name__, url_prefix='/api/goals')


@bp.route('', methods=['GET'])
def list_goals():
    """获取目标列表，支持 status/timeframe 过滤"""
    status = request.args.get('status')
    timeframe = request.args.get('timeframe')
    goals = db.get_goals(status=status, timeframe=timeframe)
    return jsonify({"goals": goals})


@bp.route('', methods=['POST'])
def create_goal():
    """创建长期目标"""
    data = request.get_json(force=True, silent=True) or {}
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error": "目标标题不能为空"}), 400

    start_date = data.get('start_date', '')
    target_date = data.get('target_date', '')
    if target_date and not validate_date(target_date):
        return jsonify({"error": "target_date 日期格式无效，需 YYYY-MM-DD"}), 400
    if start_date and not validate_date(start_date):
        return jsonify({"error": "start_date 日期格式无效，需 YYYY-MM-DD"}), 400

    gid = db.create_goal(
        title=title,
        description=data.get('description', ''),
        category=data.get('category', 'personal'),
        timeframe=data.get('timeframe', 'yearly'),
        start_date=start_date or None,
        target_date=target_date or None,
        key_results=data.get('key_results', []),
        linked_todos=data.get('linked_todos', []),
        linked_habits=data.get('linked_habits', []),
        color=data.get('color', '#6366f1'),
    )
    return jsonify({"status": "ok", "id": gid})


@bp.route('/<int:gid>', methods=['PUT'])
def update_goal(gid):
    """更新目标（进度/状态/关键结果等）"""
    data = request.get_json(force=True, silent=True) or {}
    if not data:
        return jsonify({"error": "无更新字段"}), 400
    ok = db.update_goal(gid, **data)
    return jsonify({"status": "ok" if ok else "noop"})


@bp.route('/<int:gid>', methods=['DELETE'])
def delete_goal(gid):
    db.delete_goal(gid)
    return jsonify({"status": "ok"})


@bp.route('/mood-heatmap', methods=['GET'])
def mood_heatmap():
    """心情热力图数据（GoalDay集大成——心情趋势可视化）"""
    year = request.args.get('year', type=int)
    data = db.get_mood_heatmap(year=year)
    return jsonify({"data": data, "year": year or data[0]['date'][:4] if data else None})
