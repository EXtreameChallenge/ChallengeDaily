"""P0-4: 今日主页自然语言一句话摘要 API

GET /api/ai/today-summary
聚合今日活动、待办完成情况、番茄钟数据，调用 AI 生成一句话自然语言摘要；
AI 未配置或调用失败时降级为模板化摘要，保证接口始终可用。
"""
import logging
from datetime import date

from flask import Blueprint, jsonify, request

from routes.deps import check_token

logger = logging.getLogger(__name__)

bp = Blueprint('ai_today_summary', __name__, url_prefix='/api/ai')


def _fmt_minutes(minutes: float) -> str:
    """把分钟数格式化为中文可读时长（如 2小时15分 / 45分钟）"""
    minutes = int(round(minutes))
    if minutes >= 60:
        h = minutes // 60
        m = minutes % 60
        return f"{h}小时{m}分" if m else f"{h}小时"
    return f"{minutes}分钟"


def _collect_stats(today: str) -> dict:
    """聚合今日活动 / 待办 / 番茄钟统计数据"""
    from db import get_activities, get_daily_summary, get_todos, get_pomodoro_sessions

    # 活动：注意 activities.timestamp 是 "YYYY-MM-DD HH:MM:SS"，需要完整时间边界
    day_start = f"{today} 00:00:00"
    day_end = f"{today} 23:59:59"
    activities = get_activities(day_start, day_end)
    daily = get_daily_summary(today, today)

    # 总工作分钟数（interval_sec 单位为秒）
    total_sec = sum((a.get("interval_sec") or 0) for a in activities)
    total_min = total_sec / 60.0

    # 分类排行
    categories = daily.get("categories") or {}
    top_categories = sorted(categories.items(), key=lambda kv: kv[1], reverse=True)

    # 待办：status 为 'completed' / 'pending'
    todos = get_todos() or []
    todos_completed = sum(1 for t in todos if (t.get("status") == "completed"))
    todos_pending = len(todos) - todos_completed

    # 番茄钟：status 为 'completed' / 'running' / 'interrupted'
    pomodoros = get_pomodoro_sessions(today) or []
    pomo_completed = [p for p in pomodoros if (p.get("status") == "completed")]
    pomo_completed_count = len(pomo_completed)
    pomo_total_min = sum((p.get("duration_min") or 0) for p in pomo_completed)

    return {
        "total_min": round(total_min, 1),
        "total_activities": len(activities),
        "top_categories": [{"name": name, "count": count} for name, count in top_categories[:3]],
        "todos_total": len(todos),
        "todos_completed": todos_completed,
        "todos_pending": todos_pending,
        "pomodoro_completed": pomo_completed_count,
        "pomodoro_total_min": pomo_total_min,
    }


def _build_template_summary(stats: dict) -> str:
    """AI 不可用时的模板化一句话摘要"""
    work = _fmt_minutes(stats.get("total_min", 0))
    done = stats.get("todos_completed", 0)
    todo_total = stats.get("todos_total", 0)
    pomo = stats.get("pomodoro_completed", 0)
    pomo_min = stats.get("pomodoro_total_min", 0)

    parts = [f"今天工作了{work}"]
    if todo_total:
        parts.append(f"完成{done}/{todo_total}个待办")
    if pomo:
        parts.append(f"专注{pomo}个番茄钟（{_fmt_minutes(pomo_min)}）")
    return "，".join(parts) + "。"


def _build_ai_context(stats: dict) -> str:
    """组装给 AI 的数据上下文"""
    cats = stats.get("top_categories") or []
    cat_str = "、".join(c["name"] for c in cats) if cats else "暂无分类记录"
    return (
        f"今日工作时长：{_fmt_minutes(stats.get('total_min', 0))}；"
        f"活动记录数：{stats.get('total_activities', 0)}；"
        f"主要投入分类：{cat_str}；"
        f"待办完成：{stats.get('todos_completed', 0)}/{stats.get('todos_total', 0)}（未完成 {stats.get('todos_pending', 0)}）；"
        f"完成番茄钟：{stats.get('pomodoro_completed', 0)} 个，累计专注 {_fmt_minutes(stats.get('pomodoro_total_min', 0))}。"
    )


@bp.route('/today-summary', methods=['GET'])
def today_summary():
    """今日一句话自然语言摘要"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    today = date.today().isoformat()
    try:
        stats = _collect_stats(today)
    except Exception as e:
        logger.error(f"today-summary 数据聚合失败: {e}", exc_info=True)
        stats = {
            "total_min": 0, "total_activities": 0, "top_categories": [],
            "todos_total": 0, "todos_completed": 0, "todos_pending": 0,
            "pomodoro_completed": 0, "pomodoro_total_min": 0,
        }

    fallback = _build_template_summary(stats)
    summary = fallback

    # AI 调用：未配置或失败时静默降级，不影响接口返回
    try:
        import config
        if config.AI_API_KEY:
            from ai_client import _get_client
            client = _get_client()
            response = client.chat.completions.create(
                model=config.AI_TEXT_MODEL,
                messages=[
                    {"role": "system", "content": "你是一个简洁的时间管理助手，用一句话总结用户今天的工作状态，不超过50字。"},
                    {"role": "user", "content": _build_ai_context(stats)},
                ],
                max_tokens=150,
                temperature=0.7,
            )
            ai_text = (response.choices[0].message.content or "").strip()
            if ai_text:
                summary = ai_text
    except Exception as e:
        logger.warning(f"today-summary AI 调用失败，使用模板摘要: {e}")
        summary = fallback

    return jsonify({
        "summary": summary,
        "date": today,
        "stats": stats,
    })
