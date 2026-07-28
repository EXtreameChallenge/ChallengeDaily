"""成长系统 API — V35"""
from flask import Blueprint, request, jsonify
from datetime import date
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


@bp.route('/life-progress', methods=['GET'])
def get_life_progress():
    """人生进度：基于生日和预期寿命计算人生已过百分比及可视化数据"""
    try:
        from config import load_settings
        settings = load_settings()
        birthday_str = settings.get('birthday', '')
        life_exp = int(settings.get('life_expectancy', 80))
        if not birthday_str:
            return jsonify({"status": "ok", "life_progress": None,
                             "message": "未设置生日，请在设置中填写生日"})
        try:
            birthday = date.fromisoformat(birthday_str)
        except (ValueError, TypeError):
            return jsonify({"status": "ok", "life_progress": None,
                             "message": "生日格式无效，请使用 YYYY-MM-DD"})

        today = date.today()
        age_days = (today - birthday).days
        if age_days < 0:
            return jsonify({"status": "ok", "life_progress": None,
                             "message": "生日不能晚于今天"})

        total_days = life_exp * 365.25
        passed_days = age_days
        pct = round(passed_days / total_days * 100, 2)
        remaining_days = max(int(total_days - passed_days), 0)
        age_years = age_days / 365.25

        # 按周计算人生方格图（52 周/年 × life_exp 年）
        weeks_lived = int(age_days / 7)
        total_weeks = int(life_exp * 52)
        year_progress = round((today - date(today.year, 1, 1)).days / 365.25 * 100, 1)

        return jsonify({"status": "ok", "life_progress": {
            "birthday": birthday_str,
            "life_expectancy": life_exp,
            "age_years": round(age_years, 1),
            "passed_days": passed_days,
            "remaining_days": remaining_days,
            "total_days": int(total_days),
            "pct": pct,
            "weeks_lived": weeks_lived,
            "total_weeks": total_weeks,
            "year_progress": year_progress,
        }})
    except Exception as e:
        logger.warning(f"获取人生进度失败: {e}")
        return jsonify({"error": str(e)}), 500
