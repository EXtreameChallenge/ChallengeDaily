# routes/daily_card.py
# 「今日完成」自动卡片 API — 借鉴 GoalDay 核心创新
# 自动汇总当天完成的待办、习惯打卡、专注会话、活动分类、成就解锁
# 解决各功能数据分散的问题，为日记提供"数据自动关联"能力
from flask import Blueprint, jsonify, request
from datetime import date
import logging

import config
from db import (
    get_conn, get_pomodoro_sessions, get_pomodoro_today_count,
    get_pomodoro_quality_score, get_daily_summary,
)
from routes.deps import check_token, validate_date

logger = logging.getLogger(__name__)

bp = Blueprint('daily_card', __name__)


@bp.route("/api/daily-card")
def get_daily_card():
    """获取指定日期的「今日完成」自动卡片数据。

    Query: date=YYYY-MM-DD（默认今天）

    返回聚合了 5 大数据源的结构化卡片：
    - todos_completed: 当日完成的待办
    - habits_logged: 当日习惯打卡
    - pomodoro: 番茄会话汇总
    - activities: 活动分类时长
    - achievements: 当日解锁成就
    - summary: 综合生产力评分
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    target = request.args.get("date") or date.today().isoformat()
    if not validate_date(target):
        return jsonify({"error": f"Invalid date format: {target}, expected YYYY-MM-DD"}), 400

    # ── 1. 待办完成情况 ──
    # completed_at 格式 'YYYY-MM-DD HH:MM:SS'，用 date() 截取
    todos_completed = []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, category, completed_at, priority "
            "FROM todos WHERE status='completed' AND date(completed_at)=? "
            "ORDER BY completed_at DESC",
            (target,),
        ).fetchall()
        for r in rows:
            todos_completed.append({
                "id": r["id"],
                "title": r["title"],
                "category": r["category"] or "其他",
                "completed_at": r["completed_at"],
                "priority": r["priority"],
            })

    # ── 2. 习惯打卡情况 ──
    # habit_logs.log_date 为纯 'YYYY-MM-DD'，可直接等值匹配
    habits_logged = []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT hl.habit_id, hl.log_date, hl.count, h.name, h.color, h.auto_category "
            "FROM habit_logs hl "
            "LEFT JOIN habits h ON hl.habit_id = h.id "
            "WHERE hl.log_date=? ORDER BY hl.habit_id",
            (target,),
        ).fetchall()
        for r in rows:
            habits_logged.append({
                "habit_id": r["habit_id"],
                "name": r["name"] or f"习惯#{r['habit_id']}",
                "count": r["count"],
                "color": r["color"],
                "category": r["auto_category"],
            })

    # ── 3. 番茄/专注会话 ──
    # 复用现有函数：sessions 列表 + 今日计数 + 质量评分
    sessions = get_pomodoro_sessions(target)
    pomodoro_sessions = []
    for s in sessions:
        pomodoro_sessions.append({
            "id": s["id"],
            "task": s.get("task") or "",
            "category": s.get("category") or "",
            "duration_min": s.get("duration_min", 0),
            "status": s.get("status", ""),
            "start_time": s.get("start_time", ""),
            "end_time": s.get("end_time", ""),
        })

    # 跨午夜修正：用 date(start_time)=? OR date(end_time)=? 避免漏掉昨夜开始的会话
    pomodoro_summary = {"count": 0, "total_min": 0}
    pomodoro_quality = None
    try:
        pomodoro_summary = get_pomodoro_today_count()
    except Exception as e:
        logger.warning("get_pomodoro_today_count failed: %s", e)
    try:
        pomodoro_quality = get_pomodoro_quality_score(target)
    except Exception as e:
        logger.warning("get_pomodoro_quality_score failed: %s", e)

    # ── 4. 活动分类时长 ──
    # activities 是快照表，时长 = COUNT × SCREENSHOT_INTERVAL_SEC / 60
    categories = {}
    total_activity_min = 0.0
    with get_conn() as conn:
        cat_rows = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM activities "
            "WHERE date(timestamp)=? GROUP BY category ORDER BY cnt DESC",
            (target,),
        ).fetchall()
    for r in cat_rows:
        cat = r["category"] or "其他"
        dur_min = round(r["cnt"] * config.SCREENSHOT_INTERVAL_SEC / 60, 1)
        categories[cat] = dur_min
        total_activity_min += dur_min

    # 活动时间范围
    daily_sum = get_daily_summary(target, target)
    first_ts = daily_sum.get("first_ts")
    last_ts = daily_sum.get("last_ts")

    # ── 5. 成就解锁 ──
    # unlocked_at 格式 'YYYY-MM-DD HH:MM:SS'，用 date() 截取
    achievements_unlocked = []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT code, name, description, icon, unlocked_at "
            "FROM achievements WHERE date(unlocked_at)=? "
            "ORDER BY unlocked_at DESC",
            (target,),
        ).fetchall()
        for r in rows:
            achievements_unlocked.append({
                "code": r["code"],
                "name": r["name"],
                "description": r["description"],
                "icon": r["icon"] or "🏆",
                "unlocked_at": r["unlocked_at"],
            })

    # ── 6. 综合生产力评分 ──
    # 评分维度：任务完成 + 专注时长 + 活动覆盖 + 打卡坚持
    todos_count = len(todos_completed)
    habits_count = len(habits_logged)
    focus_min = pomodoro_summary.get("total_min", 0)
    focus_count = pomodoro_summary.get("count", 0)

    # 简单加权评分（满分 100）
    # - 任务完成 30 分（每个 6 分，上限 30）
    # - 专注时长 30 分（每分钟 0.5 分，上限 30）
    # - 活动覆盖 20 分（每类 4 分，上限 20）
    # - 习惯打卡 20 分（每个 5 分，上限 20）
    score = min(30, todos_count * 6) + min(30, focus_min * 0.5) \
        + min(20, len(categories) * 4) + min(20, habits_count * 5)
    score = round(score, 1)

    # 评级
    grade = "D"
    if score >= 85:
        grade = "S"
    elif score >= 75:
        grade = "A"
    elif score >= 60:
        grade = "B"
    elif score >= 40:
        grade = "C"

    return jsonify({
        "date": target,
        "todos_completed": todos_completed,
        "todos_count": todos_count,
        "habits_logged": habits_logged,
        "habits_count": habits_count,
        "pomodoro_sessions": pomodoro_sessions,
        "pomodoro_count": focus_count,
        "pomodoro_total_min": focus_min,
        "pomodoro_quality": pomodoro_quality,
        "activity_categories": categories,
        "activity_total_min": round(total_activity_min, 1),
        "activity_first_ts": first_ts,
        "activity_last_ts": last_ts,
        "achievements_unlocked": achievements_unlocked,
        "achievements_count": len(achievements_unlocked),
        "summary": {
            "total_tasks": todos_count,
            "total_focus_min": focus_min,
            "total_work_min": round(total_activity_min, 1),
            "total_habits": habits_count,
            "total_achievements": len(achievements_unlocked),
            "productivity_score": score,
            "grade": grade,
        },
    })


@bp.route("/api/daily-card/text")
def get_daily_card_text():
    """生成「今日完成」卡片的可插入文本（Markdown 格式）。

    用于一键插入到日记正文，实现 GoalDay 的"数据自动关联"。
    Query: date=YYYY-MM-DD（默认今天）
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401

    target = request.args.get("date") or date.today().isoformat()
    if not validate_date(target):
        return jsonify({"error": f"Invalid date format: {target}, expected YYYY-MM-DD"}), 400

    # 复用主接口逻辑（内部调用）
    from flask import current_app
    with current_app.test_request_context(f"/api/daily-card?date={target}"):
        resp = get_daily_card()
        data = resp.get_json()

    lines = []
    s = data.get("summary", {})
    lines.append(f"## 今日完成 · {target}")
    lines.append("")
    lines.append(f"> 生产力评分 **{s.get('productivity_score', 0)}** ({s.get('grade', '-')}) "
                 f"| 任务 {s.get('total_tasks', 0)} · 专注 {s.get('total_focus_min', 0)}min "
                 f"| 工作 {s.get('total_work_min', 0)}min · 打卡 {s.get('total_habits', 0)}")

    # 待办
    todos = data.get("todos_completed", [])
    if todos:
        lines.append("")
        lines.append("### ✅ 已完成待办")
        for t in todos:
            lines.append(f"- [{t['category']}] {t['title']}")

    # 专注
    pomo = data.get("pomodoro_sessions", [])
    if pomo:
        lines.append("")
        lines.append(f"### 🍅 专注会话（{data.get('pomodoro_count', 0)} 次 / {data.get('pomodoro_total_min', 0)}min）")
        for s in pomo[:5]:
            task = s.get("task") or "未命名"
            dur = s.get("duration_min", 0)
            lines.append(f"- {task} · {dur}min")
        if len(pomo) > 5:
            lines.append(f"- ...及其他 {len(pomo) - 5} 次")

    # 活动
    cats = data.get("activity_categories", {})
    if cats:
        lines.append("")
        lines.append(f"### 📊 工作分布（{data.get('activity_total_min', 0)}min）")
        for cat, dur in list(cats.items())[:6]:
            lines.append(f"- {cat}: {dur}min")

    # 习惯
    habits = data.get("habits_logged", [])
    if habits:
        lines.append("")
        lines.append("### 🔥 习惯打卡")
        for h in habits:
            lines.append(f"- {h['name']} × {h['count']}")

    # 成就
    achs = data.get("achievements_unlocked", [])
    if achs:
        lines.append("")
        lines.append("### 🏆 解锁成就")
        for a in achs:
            lines.append(f"- {a['icon']} {a['name']} — {a['description']}")

    return jsonify({
        "date": target,
        "text": "\n".join(lines),
        "summary": s,
    })
