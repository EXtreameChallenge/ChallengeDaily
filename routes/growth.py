"""成长系统 API — V35"""
from flask import Blueprint, request, jsonify
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('growth', __name__, url_prefix='/api/growth')


@bp.route('/profile', methods=['GET'])
def get_growth_profile():
    """获取成长档案"""
    try:
        import growth_service
        profile = growth_service.get_profile()
        return jsonify({"status": "ok", "profile": profile})
    except Exception as e:
        logger.warning(f"获取成长档案失败: {e}")
        return jsonify({"status": "ok", "profile": {
            'total_exp': 0, 'level': 1, 'current_level_exp': 0,
            'exp_to_next': 200, 'dimensions': {}, 'streak_days': 0,
            'longest_streak': 0, 'initialized': False
        }})


@bp.route('/log', methods=['GET'])
def get_growth_log():
    """获取经验记录"""
    try:
        import growth_service
        days = int(request.args.get('days', 7))
        days = max(1, min(days, 90))
        logs = growth_service.get_log(days)
        return jsonify({"status": "ok", "logs": logs})
    except Exception as e:
        logger.warning(f"获取经验记录失败: {e}")
        return jsonify({"status": "ok", "logs": []})


@bp.route('/award', methods=['POST'])
def award_exp():
    """手动奖励经验值"""
    try:
        import growth_service
        data = request.get_json(force=True, silent=True) or {}
        exp_amount = int(data.get('exp_amount', 0))
        dimension = data.get('dimension', 'deep_think')
        source = data.get('source', 'manual')
        source_id = data.get('source_id')
        note = data.get('note', '')

        if exp_amount <= 0:
            return jsonify({"error": "exp_amount 必须大于 0"}), 400
        if dimension not in growth_service.DIMENSION_MAP:
            return jsonify({"error": f"dimension 必须是 {list(growth_service.DIMENSION_MAP.keys())} 之一"}), 400

        result = growth_service.award_exp(exp_amount, dimension, source, source_id, note)

        # 推送 SSE 事件
        try:
            from event_bus import push_event
            push_event('growth_update', {'exp_awarded': exp_amount, 'dimension': dimension, 'source': source})
        except Exception:
            pass

        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        logger.warning(f"奖励经验失败: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route('/dimensions', methods=['PUT'])
def update_dimensions():
    """自定义维度配置（暂存 settings 表）"""
    try:
        import db
        data = request.get_json(force=True, silent=True) or {}
        dimensions_config = data.get('dimensions', {})
        if not dimensions_config:
            return jsonify({"error": "dimensions 不能为空"}), 400

        import json
        config_json = json.dumps(dimensions_config, ensure_ascii=False)
        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('custom_dimensions', ?)",
                (config_json,)
            )
            conn.commit()
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.warning(f"更新维度配置失败: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route('/initialize', methods=['POST'])
def initialize_growth():
    """冷启动：从历史数据初始化成长系统"""
    try:
        import growth_service
        result = growth_service.initialize_from_history()
        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        logger.warning(f"初始化成长系统失败: {e}")
        return jsonify({"error": str(e)}), 500
