"""赛季排行榜 API 路由

基于匿名 benchmark 的群组对比，隐私优先：
- 不上传用户真实数据到服务器
- 排行榜中的同行由行业基准数据合成
- 群组成员仅展示匿名昵称
"""
import logging
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import season_leaderboard

logger = logging.getLogger(__name__)
bp = Blueprint('leaderboard', __name__, url_prefix='/api/leaderboard')


@bp.route('/season', methods=['GET'])
def get_season_leaderboard():
    """获取赛季排行榜

    query: month=YYYYMM（默认当月）, metric=productivity|exp|habit_streak|focus_min
    注意：函数名不能与 `import season_leaderboard` 的模块名冲突，否则会遮蔽模块绑定。
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        month = request.args.get('month', '').strip() or None
        metric = request.args.get('metric', 'productivity').strip()
        if metric not in ('productivity', 'exp', 'habit_streak', 'focus_min'):
            return jsonify({"error": "metric 仅支持 productivity/exp/habit_streak/focus_min"}), 400
        result = season_leaderboard.get_season_leaderboard(month=month, metric=metric)
        return jsonify(result)
    except Exception as e:
        logger.error(f"赛季排行榜查询失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/season/submit', methods=['POST'])
def submit_score():
    """提交匿名分数到 benchmark 服务（仅含脱敏聚合数据）"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        month = data.get('month', '').strip() or None
        result = season_leaderboard.submit_anonymous_score(month=month)
        return jsonify(result)
    except Exception as e:
        logger.error(f"提交匿名分数失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/season/history', methods=['GET'])
def season_history():
    """获取最近 N 个月赛季历史排名

    query: months=N（默认 6，最大 24）
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        months = int(request.args.get('months', '6'))
        months = max(1, min(months, 24))
        history = season_leaderboard.get_my_season_history(months=months)
        return jsonify({"history": history})
    except Exception as e:
        logger.error(f"赛季历史查询失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/season/summary', methods=['GET'])
def season_summary():
    """赛季总结：排名变化、超越百分比、维度对比、成就完成情况

    query: month=YYYYMM（默认当月）
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        month = request.args.get('month', '').strip() or None
        result = season_leaderboard.get_season_summary(month=month)
        return jsonify(result)
    except Exception as e:
        logger.error(f"赛季总结查询失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500
