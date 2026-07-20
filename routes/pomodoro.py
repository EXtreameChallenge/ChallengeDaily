"""番茄钟专注记录 API（支持连续执行 + 任务深度关联）"""
from flask import Blueprint, request, jsonify
from routes.deps import check_token
import db
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

bp = Blueprint('pomodoro', __name__, url_prefix='/api/pomodoro')

# 大番茄: 工作25min + 休息5min  |  小番茄: 工作20min + 休息10min
POMODORO_SIZES = {
    'big':   {'work': 25, 'short_break': 5, 'long_break': 15},
    'small': {'work': 20, 'short_break': 10, 'long_break': 15},
}
LONG_BREAK_INTERVAL = 4  # 每4个番茄一次长休息

# ── 分心停留去抖（参考 ManicTime 行业惯例：短暂一瞥不算分心）──
# 前台切到"生活"类应用后需连续停留 ≥30 秒才计 1 次有效分心；
# 同一次连续分心只计 1 次，切回工作类应用即结束 episode，下次重新计时。
DWELL_THRESHOLD_SEC = 30
_distraction_episodes = {}  # session_id -> {"first_seen": float, "counted": bool}


@bp.route('/start', methods=['POST'])
def start_pomodoro():
    """开始番茄钟（支持读取关联任务的预估番茄数和大小）"""
    data = request.get_json(force=True, silent=True) or {}
    task = data.get('task', '').strip()
    duration_min = int(data.get('duration_min', 25))
    category = data.get('category', '开发')
    todo_id = data.get('todo_id')
    pomodoro_index = int(data.get('pomodoro_index', 1))  # 当前第几个番茄（连续执行）
    total_pomodoros = int(data.get('total_pomodoros', 1))  # 计划番茄总数

    # 如果关联了 todo，自动读取其 estimated_pomodoros 和 pomodoro_size
    if todo_id:
        with db.get_conn() as conn:
            todo = conn.execute("SELECT estimated_pomodoros, pomodoro_size, category, target_min FROM todos WHERE id=?", (todo_id,)).fetchone()
            if todo:
                total_pomodoros = todo['estimated_pomodoros'] or 1
                size_config = POMODORO_SIZES.get(todo['pomodoro_size'] or 'big', POMODORO_SIZES['big'])
                duration_min = size_config['work']
                if not category or category == '开发':
                    category = todo['category'] or '开发'

    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    session_id = db.insert_pomodoro_session(
        start_time=now, end_time=None, duration_min=duration_min,
        task=task, category=category, status='running', interrupted_count=0, source='manual'
    )
    # 关联 todo_id + pomodoro_index/total_pomodoros
    update_data = {}
    if todo_id:
        update_data['todo_id'] = int(todo_id)
    if pomodoro_index > 1 or total_pomodoros > 1:
        update_data['pomodoro_index'] = pomodoro_index
        update_data['total_pomodoros'] = total_pomodoros
    if update_data:
        db.update_pomodoro_session(session_id, **update_data)

    # 推送 SSE 事件（番茄状态变化）
    try:
        from event_bus import push_event
        push_event('pomodoro_update', {
            "action": "start", "session_id": session_id, "duration_min": duration_min,
            "task": task, "category": category,
        })
    except Exception:
        pass

    # 学霸硬锁机激活（如果启用了严格模式）
    lock_level = int(data.get('lock_level', 0))  # 0=关 1=L1软提醒 2=L2硬拦截 3=L3锁屏
    custom_blacklist = data.get('custom_blacklist', [])
    if lock_level > 0:
        try:
            from lock_manager import lock_manager
            lock_manager.activate(
                level=lock_level,
                session_id=session_id,
                custom_blacklist=set(custom_blacklist),
            )
        except Exception as e:
            logger.warning(f"硬锁机激活失败: {e}")

    return jsonify({
        "status": "ok", "id": session_id, "start_time": now,
        "todo_id": todo_id, "duration_min": duration_min,
        "pomodoro_index": pomodoro_index, "total_pomodoros": total_pomodoros,
    })


@bp.route('/stop', methods=['POST'])
def stop_pomodoro():
    """结束番茄钟"""
    data = request.get_json(force=True, silent=True) or {}
    session_id = data.get('id')
    status = data.get('status', 'completed')
    interrupted_count = int(data.get('interrupted_count', 0))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if session_id:
        db.update_pomodoro_session(session_id, end_time=now, status=status, interrupted_count=interrupted_count)
        _distraction_episodes.pop(session_id, None)  # 清理分心去抖状态
        # 完成时自动回写 todo 进度（V19 联动）
        if status == 'completed':
            with db.get_conn() as conn:
                row = conn.execute("SELECT todo_id, duration_min FROM pomodoro_sessions WHERE id=?", (session_id,)).fetchone()
                if row and row['todo_id']:
                    db.update_todo_progress(row['todo_id'], row['duration_min'])
        # 推送 SSE 事件（番茄状态变化）
        try:
            from event_bus import push_event
            push_event('pomodoro_update', {
                "action": "stop", "session_id": session_id, "status": status,
                "interrupted_count": interrupted_count,
            })
        except Exception:
            pass
        # 关闭学霸硬锁机
        try:
            from lock_manager import lock_manager
            lock_manager.deactivate()
        except Exception:
            pass
    return jsonify({"status": "ok", "end_time": now})


@bp.route('/sessions', methods=['GET'])
def list_sessions():
    """查询番茄钟记录"""
    date_str = request.args.get('date')
    sessions = db.get_pomodoro_sessions(date_str)
    return jsonify({"sessions": sessions})


@bp.route('/stats', methods=['GET'])
def pomodoro_stats():
    """专注统计"""
    range_type = request.args.get('range', 'week')
    stats = db.get_pomodoro_stats(range_type)
    today = db.get_pomodoro_today_count()
    streak = db.get_pomodoro_streak()
    return jsonify({"stats": stats, "today": today, "streak": streak})


@bp.route('/today', methods=['GET'])
def pomodoro_today():
    """今日专注统计"""
    return jsonify(db.get_pomodoro_today_count())


@bp.route('/quality', methods=['GET'])
def pomodoro_quality():
    """今日专注质量评分（时长×纯度×完成度）"""
    date_str = request.args.get('date')
    return jsonify(db.get_pomodoro_quality_score(date_str))


@bp.route('/config', methods=['GET'])
def pomodoro_config():
    """获取番茄钟配置（大小番茄的工作/休息时长）"""
    return jsonify({
        "sizes": POMODORO_SIZES,
        "long_break_interval": LONG_BREAK_INTERVAL,
    })


# ── P9-3：番茄钟增强 ──────────────────────────────────

@bp.route('/smart-duration', methods=['GET'])
def smart_duration():
    """P9-3：智能番茄时长建议

    基于最近 14 天历史数据，分析用户在哪个时长下完成率最高、中断率最低，
    推荐最适合自己的番茄时长。

    GET /api/pomodoro/smart-duration
    返回：{recommended_min, reason, analysis}
    """
    try:
        from datetime import date as _date, timedelta as _td
        today = _date.today()
        start_14 = (today - _td(days=14)).isoformat()
        with db.get_conn() as conn:
            # 按时长分组统计完成率与中断率
            rows = conn.execute(
                "SELECT duration_min, "
                "       COUNT(*) as total, "
                "       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed, "
                "       SUM(CASE WHEN status='interrupted' THEN 1 ELSE 0 END) as interrupted, "
                "       COALESCE(SUM(interrupted_count), 0) as total_distractions "
                "FROM pomodoro_sessions "
                "WHERE date(start_time) >= ? AND duration_min > 0 "
                "GROUP BY duration_min ORDER BY total DESC",
                (start_14,),
            ).fetchall()
        if not rows:
            return jsonify({
                "recommended_min": 25,
                "reason": "暂无历史数据，使用标准 25 分钟作为起点",
                "analysis": [],
            })
        analysis = []
        best_score = -1
        best_min = 25
        best_reason = ""
        for r in rows:
            total = r["total"] or 0
            completed = r["completed"] or 0
            interrupted = r["interrupted"] or 0
            distractions = r["total_distractions"] or 0
            completion_rate = completed / total if total else 0
            interrupt_rate = interrupted / total if total else 0
            avg_distractions = distractions / total if total else 0
            # 评分：完成率权重 0.6，中断率权重 0.3，分心次数权重 0.1
            score = completion_rate * 0.6 + (1 - interrupt_rate) * 0.3 + (1 - min(avg_distractions / 3, 1)) * 0.1
            analysis.append({
                "duration_min": r["duration_min"],
                "total": total,
                "completed": completed,
                "interrupted": interrupted,
                "completion_rate": round(completion_rate, 2),
                "interrupt_rate": round(interrupt_rate, 2),
                "avg_distractions": round(avg_distractions, 2),
                "score": round(score, 3),
            })
            if score > best_score and total >= 2:  # 至少 2 次才采纳
                best_score = score
                best_min = r["duration_min"]
                if completion_rate >= 0.8 and interrupt_rate <= 0.2:
                    best_reason = f"在 {best_min} 分钟时长下完成率 {completion_rate * 100:.0f}%，中断率仅 {interrupt_rate * 100:.0f}%，是你的黄金时长"
                elif completion_rate >= 0.6:
                    best_reason = f"在 {best_min} 分钟时长下完成率 {completion_rate * 100:.0f}%，表现最稳定"
                else:
                    best_reason = f"建议尝试 {best_min} 分钟，当前所有时长完成率都不高，可能需要调整工作环境"
        return jsonify({
            "recommended_min": best_min,
            "reason": best_reason or "基于历史数据推荐",
            "analysis": analysis,
        })
    except Exception as e:
        logger.error(f"smart_duration 失败: {e}", exc_info=True)
        return jsonify({"error": "智能时长分析失败"}), 500


@bp.route('/report', methods=['GET'])
def pomodoro_report():
    """P9-3：番茄钟报告

    分析最近 N 天的番茄钟质量，找出最佳时段、最常见中断原因、质量趋势。

    GET /api/pomodoro/report?days=7
    """
    try:
        days = int(request.args.get('days', '7'))
        days = max(1, min(days, 90))
        from datetime import date as _date, timedelta as _td
        today = _date.today()
        start = (today - _td(days=days - 1)).isoformat()

        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT id, start_time, end_time, duration_min, task, category, "
                "       status, interrupted_count, source, todo_id "
                "FROM pomodoro_sessions "
                "WHERE date(start_time) >= ? "
                "ORDER BY start_time ASC",
                (start,),
            ).fetchall()
        if not rows:
            return jsonify({
                "range_days": days,
                "total_sessions": 0,
                "message": "该时段内暂无番茄钟记录",
            })

        sessions = [dict(r) for r in rows]
        total = len(sessions)
        completed = [s for s in sessions if s.get("status") == "completed"]
        interrupted = [s for s in sessions if s.get("status") == "interrupted"]
        total_min = sum(s.get("duration_min", 0) for s in completed)
        total_distractions = sum(s.get("interrupted_count", 0) for s in sessions)

        # 按时段分析质量
        period_stats: dict[str, dict] = {}
        for s in sessions:
            try:
                hour = int(s["start_time"][11:13])
            except (ValueError, IndexError):
                continue
            if 6 <= hour < 12:
                period = "上午"
            elif 12 <= hour < 18:
                period = "下午"
            elif 18 <= hour < 22:
                period = "晚间"
            else:
                period = "夜间"
            if period not in period_stats:
                period_stats[period] = {"total": 0, "completed": 0, "min": 0, "distractions": 0}
            period_stats[period]["total"] += 1
            if s.get("status") == "completed":
                period_stats[period]["completed"] += 1
                period_stats[period]["min"] += s.get("duration_min", 0)
            period_stats[period]["distractions"] += s.get("interrupted_count", 0)

        # 找出最佳时段（完成率最高且样本 >=2）
        best_period = None
        best_period_score = -1
        for p, st in period_stats.items():
            if st["total"] < 2:
                continue
            rate = st["completed"] / st["total"]
            if rate > best_period_score:
                best_period_score = rate
                best_period = p

        # 按分类统计
        cat_stats: dict[str, int] = {}
        for s in completed:
            cat = s.get("category", "未知")
            cat_stats[cat] = cat_stats.get(cat, 0) + 1

        # 按天统计趋势
        daily_trend: list[dict] = []
        day_map: dict[str, dict] = {}
        for s in sessions:
            try:
                d = s["start_time"][:10]
            except (ValueError, IndexError):
                continue
            if d not in day_map:
                day_map[d] = {"date": d, "total": 0, "completed": 0, "min": 0}
            day_map[d]["total"] += 1
            if s.get("status") == "completed":
                day_map[d]["completed"] += 1
                day_map[d]["min"] += s.get("duration_min", 0)
        daily_trend = sorted(day_map.values(), key=lambda x: x["date"])

        # 关联任务统计
        task_sessions = [s for s in sessions if s.get("todo_id")]
        unique_tasks = len(set(s["todo_id"] for s in task_sessions))

        return jsonify({
            "range_days": days,
            "total_sessions": total,
            "completed_sessions": len(completed),
            "interrupted_sessions": len(interrupted),
            "completion_rate": round(len(completed) / total, 2) if total else 0,
            "total_focus_min": total_min,
            "total_focus_hour": round(total_min / 60, 1),
            "avg_distractions_per_session": round(total_distractions / total, 2) if total else 0,
            "best_period": best_period,
            "best_period_completion_rate": round(best_period_score, 2) if best_period_score >= 0 else None,
            "period_stats": {k: v for k, v in period_stats.items()},
            "category_stats": cat_stats,
            "daily_trend": daily_trend,
            "linked_task_count": unique_tasks,
            "linked_task_ratio": round(len(task_sessions) / total, 2) if total else 0,
            "suggestions": _generate_pomodoro_suggestions(
                len(completed), total, total_distractions, best_period, unique_tasks, total
            ),
        })
    except Exception as e:
        logger.error(f"pomodoro_report 失败: {e}", exc_info=True)
        return jsonify({"error": "番茄报告生成失败"}), 500


def _generate_pomodoro_suggestions(completed: int, total: int, distractions: int,
                                    best_period: str | None, linked_tasks: int, total_sessions: int) -> list:
    """生成番茄钟改进建议（规则引擎）"""
    suggestions = []
    if total == 0:
        return suggestions
    completion_rate = completed / total
    avg_distractions = distractions / total

    if completion_rate < 0.5:
        suggestions.append("完成率偏低，试试缩短番茄时长（如 20 分钟），或检查工作环境是否有干扰源")
    elif completion_rate >= 0.8:
        suggestions.append("完成率很高，专注力状态很好，可以尝试挑战更长的番茄时长")

    if avg_distractions > 2:
        suggestions.append(f"平均每个番茄被打断 {avg_distractions:.1f} 次，建议开启学霸模式或通知免打扰")

    if best_period:
        suggestions.append(f"你在{best_period}的完成率最高，建议把重要任务安排在这个时段")

    if linked_tasks == 0 and total_sessions >= 5:
        suggestions.append("大部分番茄钟未关联具体任务，建议开始时选择一个待办，让专注更有方向")
    elif linked_tasks / total_sessions < 0.3 and total_sessions >= 5:
        suggestions.append("只有少数番茄钟关联了任务，试着提升任务关联率，让每一段专注都有产出")

    if not suggestions:
        suggestions.append("番茄钟使用情况良好，继续保持~")

    return suggestions[:3]


@bp.route('/distraction-check', methods=['POST'])
def distraction_check():
    """番茄运行期间检测分心（前端定时调用）

    通过 get_foreground_app 获取当前前台应用，查询其最近一次分类。
    采用 30 秒停留去抖（行业惯例）：切到"生活"类应用需连续停留 ≥30 秒
    才计 1 次有效分心并累加 interrupted_count；不足 30 秒视为误触一瞥，
    不计数。同一次连续分心 episode 只计 1 次，切回工作类应用即结束 episode。
    注意：activities 表为快照表（无 start_time/end_time），按 timestamp 排序。
    """
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id')
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    try:
        from app_tracker import get_foreground_app
        app_info = get_foreground_app()
        app_name = app_info.get("app_name", "") or ""
        window_title = app_info.get("window_title", "") or ""

        with db.get_conn() as conn:
            # 查询最近一条匹配活动记录的分类（activities 是快照表，按 timestamp DESC）
            row = conn.execute(
                "SELECT category FROM activities "
                "WHERE app_name = ? OR window_title LIKE ? "
                "ORDER BY timestamp DESC LIMIT 1",
                (app_name, f"%{window_title[:50]}%"),
            ).fetchone()
            category = row[0] if row else "未知"
            distracting_now = category == "生活"

            # ── 30 秒停留去抖：短暂一瞥不算分心 ──
            now_ts = time.time()
            is_distraction = False
            if distracting_now:
                ep = _distraction_episodes.get(session_id)
                if ep is None:
                    # 首次切到生活类应用：开始计时，暂不计数
                    _distraction_episodes[session_id] = {"first_seen": now_ts, "counted": False}
                elif not ep["counted"] and now_ts - ep["first_seen"] >= DWELL_THRESHOLD_SEC:
                    # 连续停留满 30 秒：确认 1 次有效分心（同 episode 只计这一次）
                    is_distraction = True
                    ep["counted"] = True
            else:
                # 切回工作类应用：结束本次分心 episode，下次分心重新计时
                _distraction_episodes.pop(session_id, None)

            if is_distraction:
                conn.execute(
                    "UPDATE pomodoro_sessions "
                    "SET interrupted_count = interrupted_count + 1 WHERE id = ?",
                    (session_id,),
                )
                conn.commit()

            distraction_count = conn.execute(
                "SELECT interrupted_count FROM pomodoro_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()

        # 叠加学霸硬锁机拦截（L2 关进程 / L3 置顶窗口）
        lock_action = "none"
        try:
            from lock_manager import lock_manager
            if lock_manager.active_level > 0:
                lock_result = lock_manager.check_and_enforce()
                if lock_result.get("is_distraction"):
                    lock_action = lock_result.get("action", "none")
        except Exception:
            pass

        return jsonify({
            "is_distraction": is_distraction,
            "category": category,
            "app_name": app_name,
            "distraction_count": distraction_count[0] if distraction_count else 0,
            "lock_action": lock_action,
        })
    except Exception as e:
        logger.error(f"分心检测失败: {e}", exc_info=True)
        return jsonify({"error": "检测失败"}), 500
