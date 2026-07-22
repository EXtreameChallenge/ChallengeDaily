"""每日仪式 API — V35（晨间规划 + 晚间复盘）"""
import json
import logging
from datetime import datetime, date, timedelta

from flask import Blueprint, request, jsonify

import db

logger = logging.getLogger(__name__)

bp = Blueprint('ritual', __name__, url_prefix='/api/ritual')


def template_insights(data):
    """AI 不可用时的模板洞察降级"""
    insights = []
    if data.get('deep_min', 0) > 120:
        insights.append({"type": "positive", "text": f"今日深度工作{data['deep_min']}分钟，表现不错！", "action_type": None})
    if data.get('distraction_count', 0) > 8:
        insights.append({"type": "action", "text": f"分心{data['distraction_count']}次偏多，建议设置屏蔽规则", "action_label": "创建规则", "action_type": "create_rule"})
    if data.get('tasks_done', 0) >= data.get('tasks_total', 1) and data.get('tasks_total', 0) > 0:
        insights.append({"type": "positive", "text": "今日任务全部完成！", "action_type": None})
    if not insights:
        insights.append({"type": "positive", "text": "今天也有在努力，明天继续加油！", "action_type": None})
    return insights[:3]


@bp.route('/morning', methods=['GET'])
def morning_ritual():
    """晨间仪式：聚合昨日数据+未完成任务+精力曲线+AI建议"""
    try:
        today_str = date.today().isoformat()
        yesterday_str = (date.today() - timedelta(days=1)).isoformat()

        # 昨日数据
        yesterday_stats = {}
        try:
            with db.get_conn() as conn:
                row = conn.execute(
                    "SELECT COALESCE(SUM(duration_min),0) as total_min, COUNT(*) as sessions "
                    "FROM pomodoro_sessions WHERE status='completed' AND date(start_time)=?",
                    (yesterday_str,)
                ).fetchone()
                yesterday_stats = {
                    'total_focus_min': row['total_min'] if row else 0,
                    'sessions': row['sessions'] if row else 0,
                }
                # 昨日完成任务数
                done_row = conn.execute(
                    "SELECT COUNT(*) as c FROM todos WHERE status='completed' AND date(completed_at)=?",
                    (yesterday_str,)
                ).fetchone()
                yesterday_stats['tasks_done'] = done_row['c'] if done_row else 0
        except Exception:
            pass

        # 未完成任务
        pending_tasks = []
        try:
            with db.get_conn() as conn:
                rows = conn.execute(
                    "SELECT id, title, priority, category, estimated_pomodoros "
                    "FROM todos WHERE status NOT IN ('completed', 'deleted') "
                    "ORDER BY priority ASC, created_at ASC LIMIT 10"
                ).fetchall()
                pending_tasks = [dict(r) for r in rows]
        except Exception:
            pass

        # 精力曲线
        energy_curve = []
        try:
            import scheduler_service
            energy_curve = scheduler_service.compute_energy_curve(14)
        except Exception:
            pass

        # AI 建议（可选）
        ai_suggestion = None
        try:
            ai_suggestion = _get_morning_ai_suggestion(yesterday_stats, pending_tasks, energy_curve)
        except Exception:
            pass

        # 检查是否已有今日计划
        existing_plan = None
        try:
            with db.get_conn() as conn:
                plan_row = conn.execute(
                    "SELECT * FROM daily_plans WHERE date=?", (today_str,)
                ).fetchone()
                if plan_row:
                    existing_plan = dict(plan_row)
        except Exception:
            pass

        return jsonify({
            "status": "ok",
            "date": today_str,
            "yesterday": yesterday_stats,
            "pending_tasks": pending_tasks,
            "energy_curve": energy_curve,
            "ai_suggestion": ai_suggestion,
            "existing_plan": existing_plan,
        })
    except Exception as e:
        logger.warning(f"晨间仪式数据获取失败: {e}")
        return jsonify({"status": "ok", "date": date.today().isoformat(),
                        "yesterday": {}, "pending_tasks": [], "energy_curve": [],
                        "ai_suggestion": None, "existing_plan": None})


@bp.route('/morning/confirm', methods=['POST'])
def morning_confirm():
    """保存每日计划"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        today_str = data.get('date', date.today().isoformat())
        plan_json = json.dumps(data.get('plan', []), ensure_ascii=False)
        mit_task = data.get('mit_task', '')
        focus_target_min = int(data.get('focus_target_min', 240))
        limits_json = json.dumps(data.get('limits', {}), ensure_ascii=False)
        adopted_ai = 1 if data.get('adopted_ai', False) else 0

        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO daily_plans (date, plan_json, mit_task, focus_target_min, limits_json, status, adopted_ai) "
                "VALUES (?,?,?,?,?,?,?)",
                (today_str, plan_json, mit_task, focus_target_min, limits_json, 'confirmed', adopted_ai)
            )
            conn.commit()

        return jsonify({"status": "ok", "date": today_str})
    except Exception as e:
        logger.warning(f"保存每日计划失败: {e}")
        return jsonify({"error": str(e)}), 500


@bp.route('/evening', methods=['GET'])
def evening_ritual():
    """晚间仪式：计算生产力分数+生成洞察"""
    try:
        today_str = date.today().isoformat()

        # 计算生产力分数
        productivity = {}
        try:
            import growth_service
            productivity = growth_service.compute_productivity_score(today_str)
        except Exception:
            pass

        # 今日任务统计
        tasks_done = 0
        tasks_total = 0
        try:
            with db.get_conn() as conn:
                done_row = conn.execute(
                    "SELECT COUNT(*) as c FROM todos WHERE status='completed' AND date(completed_at)=?",
                    (today_str,)
                ).fetchone()
                tasks_done = done_row['c'] if done_row else 0
                total_row = conn.execute(
                    "SELECT COUNT(*) as c FROM todos WHERE status NOT IN ('deleted') AND date(created_at) <= ?",
                    (today_str,)
                ).fetchone()
                tasks_total = total_row['c'] if total_row else 0
        except Exception:
            pass

        # 生成洞察
        insight_data = {
            'deep_min': productivity.get('deep_work_min', 0),
            'distraction_count': productivity.get('distraction_count', 0),
            'tasks_done': tasks_done,
            'tasks_total': tasks_total,
            'score': productivity.get('score', 0),
        }

        insights = _get_evening_insights(insight_data)

        # 检查是否已有今日反思
        existing_reflection = None
        try:
            with db.get_conn() as conn:
                ref_row = conn.execute(
                    "SELECT * FROM daily_reflections WHERE date=?", (today_str,)
                ).fetchone()
                if ref_row:
                    existing_reflection = dict(ref_row)
        except Exception:
            pass

        return jsonify({
            "status": "ok",
            "date": today_str,
            "productivity": productivity,
            "tasks_done": tasks_done,
            "tasks_total": tasks_total,
            "insights": insights,
            "existing_reflection": existing_reflection,
        })
    except Exception as e:
        logger.warning(f"晚间仪式数据获取失败: {e}")
        return jsonify({"status": "ok", "date": date.today().isoformat(),
                        "productivity": {}, "tasks_done": 0, "tasks_total": 0,
                        "insights": [{"type": "positive", "text": "今天也有在努力，明天继续加油！", "action_type": None}],
                        "existing_reflection": None})


@bp.route('/evening/reflect', methods=['POST'])
def evening_reflect():
    """保存每日反思"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        today_str = data.get('date', date.today().isoformat())
        productivity_score = data.get('productivity_score')
        good_thing = data.get('good_thing', '')
        improve_thing = data.get('improve_thing', '')
        ai_insights = json.dumps(data.get('ai_insights', []), ensure_ascii=False)

        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO daily_reflections (date, productivity_score, good_thing, improve_thing, ai_insights_json, report_generated) "
                "VALUES (?,?,?,?,?,0)",
                (today_str, productivity_score, good_thing, improve_thing, ai_insights)
            )
            conn.commit()

        return jsonify({"status": "ok", "date": today_str})
    except Exception as e:
        logger.warning(f"保存每日反思失败: {e}")
        return jsonify({"error": str(e)}), 500


def _get_morning_ai_suggestion(yesterday_stats, pending_tasks, energy_curve) -> str | None:
    """尝试获取 AI 晨间建议"""
    try:
        from ai_client import _cb_check, _rate_limit_check, _get_client, _cb_record_success, _cb_record_failure
        import config

        if not _cb_check():
            return None
        if not _rate_limit_check("text"):
            return None

        client = _get_client()

        task_list = ", ".join([t.get('title', '') for t in pending_tasks[:5]])
        focus_min = yesterday_stats.get('total_focus_min', 0)

        prompt = (
            f"今天是新的一天。昨天专注了{focus_min}分钟。"
            f"今天待完成的任务有：{task_list}。"
            f"请给出一句简短的晨间鼓励和建议（不超过50字）。"
        )

        response = client.chat.completions.create(
            model=getattr(config, 'AI_MODEL', 'gpt-3.5-turbo'),
            messages=[
                {"role": "system", "content": "你是一个温暖高效的时间管理教练。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=100,
        )
        _cb_record_success()
        return response.choices[0].message.content.strip()

    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"AI 晨间建议失败: {e}")
        try:
            from ai_client import _cb_record_failure
            _cb_record_failure()
        except Exception:
            pass
        return None


def _get_evening_insights(data: dict) -> list:
    """获取晚间洞察：优先 AI，降级模板"""
    # 尝试 AI
    try:
        from ai_client import _cb_check, _rate_limit_check, _get_client, _cb_record_success, _cb_record_failure
        import config

        if _cb_check() and _rate_limit_check("text"):
            client = _get_client()
            prompt = (
                f"今日数据：深度工作{data.get('deep_min', 0)}分钟，"
                f"分心{data.get('distraction_count', 0)}次，"
                f"完成任务{data.get('tasks_done', 0)}/{data.get('tasks_total', 0)}个，"
                f"生产力分数{data.get('score', 0)}。\n"
                f"请给出最多3条简短洞察，JSON数组格式，每项包含type(positive/action)和text字段。"
                f"如果有可改进的action项，加上action_label和action_type字段。"
            )
            response = client.chat.completions.create(
                model=getattr(config, 'AI_MODEL', 'gpt-3.5-turbo'),
                messages=[
                    {"role": "system", "content": "你是一个数据分析教练，擅长从日常数据中给出 actionable 建议。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=500,
            )
            _cb_record_success()
            content = response.choices[0].message.content.strip()
            if '```' in content:
                content = content.split('```')[1]
                if content.startswith('json'):
                    content = content[4:]
            insights = json.loads(content)
            if isinstance(insights, list) and len(insights) > 0:
                return insights[:3]
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"AI 晚间洞察失败: {e}")
        try:
            from ai_client import _cb_record_failure
            _cb_record_failure()
        except Exception:
            pass

    # 降级：模板洞察
    return template_insights(data)
