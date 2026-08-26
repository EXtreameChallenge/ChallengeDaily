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

# ── 专注监督：三档严格度 + 关键词配置 ──
# relaxed:  仅检测游戏/短视频等明显无关应用（productivity_level <= -1）
# standard: 应用分类 + 窗口标题白/黑名单 + 任务相关性（默认）
# strict:    standard + 信息不足时可触发视觉模型分析（需前端手动触发）
DEFAULT_STRICTNESS = "standard"

# 默认白名单关键词（命中则判定为专注，覆盖其他判定）
_FOCUS_WHITELIST_KEYWORDS = [
    "教程", "课程", "文档", "api", "源码", "debug", "论文", "笔记",
    "documentation", "tutorial", "course", "github", "stackoverflow",
    "学习", "研究", "分析", "设计", "开发", "编写", "整理", "参考",
    "manual", "guide", "spec", "prd", "需求", "架构", "算法",
]

# 默认黑名单关键词（命中则判定为分心）
_FOCUS_BLACKLIST_KEYWORDS = [
    "推荐", "热门", "排行榜", "直播", "小说", "综艺", "追剧",
    "短视频", "游戏", "娱乐", "八卦", "购物", "促销", "秒杀",
    "抖音", "快手", "bilibili", "youtube", "netflix", "steam",
]

# 明显分心应用（relaxed 模式也检测）
_HARD_DISTRACTION_APPS = [
    "steam", "epic games", "原神", "英雄联盟", "王者荣耀",
    "抖音", "快手", "tiktok", "netflix", "爱奇艺", "腾讯视频",
    "优酷", "芒果tv", "bilibili", "b站",
]


def _load_focus_keywords():
    """从 settings 加载用户自定义白/黑名单关键词，合并默认值"""
    try:
        from config import load_settings
        s = load_settings()
        wl = s.get("focus_whitelist_keywords", []) or []
        bl = s.get("focus_blacklist_keywords", []) or []
        return list(set(_FOCUS_WHITELIST_KEYWORDS + wl)), list(set(_FOCUS_BLACKLIST_KEYWORDS + bl))
    except Exception:
        return list(_FOCUS_WHITELIST_KEYWORDS), list(_FOCUS_BLACKLIST_KEYWORDS)


def _calc_task_relevance(task_title, window_title, app_name):
    """计算任务标题与当前窗口的相关性，返回 0~1

    简单分词重叠度计算：任务关键词在窗口标题中出现的比例。
    无任务时返回 0.5（中性）。
    """
    if not task_title or not task_title.strip():
        return 0.5
    # 简单分词：中文按字、英文按词
    import re
    task_words = set(re.findall(r'[a-zA-Z0-9]+|[\u4e00-\u9fff]', task_title.lower()))
    # 过滤单字中文（噪声太大），保留2字以上的中文词和英文词
    task_words = {w for w in task_words if len(w) >= 2 or re.match(r'[a-zA-Z0-9]', w)}
    if not task_words:
        return 0.5
    title_lower = (window_title or "").lower() + " " + (app_name or "").lower()
    overlap = sum(1 for w in task_words if w in title_lower)
    return min(1.0, overlap / len(task_words) * 1.5)  # *1.5 让部分匹配也能得高分


def _is_excluded_app(app_name, window_title):
    """检查应用是否在排除列表中（复用 config.get_exclude_apps）"""
    try:
        from config import get_exclude_apps
        excluded = get_exclude_apps()
        app_lower = (app_name or "").lower()
        title_lower = (window_title or "").lower()
        for ex in excluded:
            ex_lower = str(ex).lower()
            if ex_lower and (ex_lower in app_lower or ex_lower in title_lower):
                return True
    except Exception:
        pass
    return False


def _judge_focus(app_name, window_title, category, task_title, strictness):
    """核心判定逻辑，返回 (judgment, relevance_score, judgment_method)

    judgment: focused / suspected / distracted / excluded
    judgment_method: text_rule / whitelist / blacklist / hard_app / fallback
    """
    # 1. 排除应用 → 直接 focused（不参与分心判定）
    if _is_excluded_app(app_name, window_title):
        return "excluded", 1.0, "excluded"

    whitelist, blacklist = _load_focus_keywords()
    app_lower = (app_name or "").lower()
    title_lower = (window_title or "").lower()
    combined = title_lower + " " + app_lower

    # 2. 白名单命中 → focused（覆盖其他判定）
    for kw in whitelist:
        if kw.lower() in combined:
            return "focused", 0.9, "whitelist"

    # 3. 黑名单命中 → distracted
    for kw in blacklist:
        if kw.lower() in combined:
            return "distracted", 0.1, "blacklist"

    # 4. 明显分心应用（所有模式都检测）
    for app in _HARD_DISTRACTION_APPS:
        if app.lower() in app_lower:
            return "distracted", 0.05, "hard_app"

    # 5. 任务相关性
    relevance = _calc_task_relevance(task_title, window_title, app_name)

    # 6. 按严格度判定
    if strictness == "relaxed":
        # relaxed: 仅明显分心应用（已在上面处理），其他都算 focused
        return "focused", relevance, "text_rule"

    # standard / strict: 结合分类和相关性
    # 分类为"生活"且相关性低 → distracted
    # 分类为"生活"且相关性中等 → suspected
    # 分类非"生活" → focused（除非相关性极低）
    if category == "生活":
        if relevance < 0.2:
            return "distracted", relevance, "text_rule"
        elif relevance < 0.5:
            return "suspected", relevance, "text_rule"
        else:
            return "focused", relevance, "text_rule"
    else:
        # 非生活类应用，相关性极低也可能是分心（如用浏览器逛购物网站）
        if relevance < 0.1 and category in ("未知", "其他"):
            return "suspected", relevance, "text_rule"
        return "focused", relevance, "text_rule"


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
            # V35: 番茄完成奖励EXP
            try:
                import growth_service
                dim = growth_service.infer_dimension_from_todo(row['todo_id']) if row and row['todo_id'] else 'deep_think'
                exp = growth_service.calculate_exp(row['duration_min'] if row else 25, dim, interrupted_count, growth_service.get_streak_days())
                growth_service.award_exp(exp, dim, 'pomodoro', session_id, f"番茄钟完成 {row['duration_min'] if row else 25}min")
                from event_bus import push_event
                push_event('growth_update', {'exp_awarded': exp, 'dimension': dim, 'source': 'pomodoro'})
            except Exception as e:
                logger.warning(f"EXP奖励失败: {e}")
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


@bp.route('/session-report', methods=['GET'])
def session_report():
    """单次番茄钟专注报告

    GET /api/pomodoro/session-report?session_id=xxx
    返回: {session_id, task, duration_min, actual_min, status, distraction_count,
           focus_score, grade, purity, completion, time_range, suggestions}
    """
    session_id = request.args.get('session_id', type=int)
    if not session_id:
        return jsonify({"error": "缺少 session_id"}), 400
    try:
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT id, task, start_time, end_time, duration_min, status, "
                "interrupted_count, todo_id FROM pomodoro_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return jsonify({"error": "番茄钟记录不存在"}), 404

        start_time = row['start_time']
        end_time = row['end_time']
        duration_min = row['duration_min'] or 0
        actual_min = 0
        if start_time and end_time:
            try:
                from datetime import datetime
                st = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                et = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                actual_min = max(0, round((et - st).total_seconds() / 60, 1))
            except Exception:
                actual_min = duration_min
        elif row['status'] == 'running':
            actual_min = duration_min  # 进行中用计划时长

        distraction_count = row['interrupted_count'] or 0
        status = row['status']

        # 专注度评分算法（0-100）
        # 完成度: actual_min / duration_min (最高1.0)
        completion = min(1.0, actual_min / duration_min) if duration_min > 0 else 0
        # 纯度: 1 - (分心次数 * 5%) 每次分心扣5%,最低0.3
        purity = max(0.3, 1.0 - distraction_count * 0.05)
        # 综合评分
        focus_score = round(completion * purity * 100)

        # 评级
        if focus_score >= 90:
            grade = 'S'
        elif focus_score >= 80:
            grade = 'A'
        elif focus_score >= 70:
            grade = 'B'
        elif focus_score >= 60:
            grade = 'C'
        else:
            grade = 'D'

        # 时间段
        time_range = ""
        if start_time:
            try:
                from datetime import datetime
                st = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                time_range = f"{st.strftime('%H:%M')}"
                if end_time:
                    et = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    time_range += f" - {et.strftime('%H:%M')}"
            except Exception:
                pass

        # 智能建议
        suggestions = []
        if distraction_count >= 3:
            suggestions.append(f"本次分心{distraction_count}次，建议下次开启学霸模式或使用白噪音减少干扰")
        if completion < 0.8 and status == 'interrupted':
            suggestions.append("番茄钟被中断，建议将任务拆分为更小的目标，或选择干扰较少的时段")
        if grade in ('S', 'A'):
            suggestions.append("专注度很高！保持这个节奏，休息一下继续")
        if not suggestions:
            suggestions.append("完成得不错，休息片刻后继续下一个番茄")

        return jsonify({
            "session_id": session_id,
            "task": row['task'] or "未命名任务",
            "duration_min": duration_min,
            "actual_min": actual_min,
            "status": status,
            "distraction_count": distraction_count,
            "focus_score": focus_score,
            "grade": grade,
            "purity": round(purity, 2),
            "completion": round(completion, 2),
            "time_range": time_range,
            "suggestions": suggestions,
        })
    except Exception as e:
        logger.error(f"单次番茄报告生成失败: {e}", exc_info=True)
        return jsonify({"error": "报告生成失败"}), 500


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

    增强版判定逻辑：
    1. 排除应用检查（复用 config.get_exclude_apps）
    2. 窗口标题白/黑名单关键词匹配
    3. 明显分心应用检测（游戏/短视频等）
    4. 任务相关性计算（任务标题与窗口标题重叠度）
    5. 三档严格度：relaxed / standard / strict

    采用 30 秒停留去抖：切到分心应用需连续停留 >=30 秒才计 1 次有效分心。
    异常时返回 is_distraction=false（宁可漏判不可误判，不崩溃）。
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
            # 查询番茄钟关联的任务标题（用于相关性计算）
            task_title = ""
            strictness = DEFAULT_STRICTNESS
            try:
                row = conn.execute(
                    "SELECT p.task, p.todo_id, t.title as todo_title "
                    "FROM pomodoro_sessions p LEFT JOIN todos t ON p.todo_id = t.id "
                    "WHERE p.id = ?", (session_id,)
                ).fetchone()
                if row:
                    task_title = row['todo_title'] or row['task'] or ""
            except Exception:
                pass

            # 从 settings 读取严格度（用户可配置）
            try:
                from config import load_settings
                s = load_settings()
                strictness = s.get("focus_strictness", DEFAULT_STRICTNESS)
                if strictness not in ("relaxed", "standard", "strict"):
                    strictness = DEFAULT_STRICTNESS
            except Exception:
                pass

            # 查询最近一条活动记录的分类（用于辅助判定）
            category = "未知"
            try:
                row = conn.execute(
                    "SELECT category FROM activities "
                    "WHERE app_name = ? OR window_title LIKE ? "
                    "ORDER BY timestamp DESC LIMIT 1",
                    (app_name, f"%{window_title[:50]}%"),
                ).fetchone()
                category = row[0] if row else "未知"
            except Exception:
                pass

            # 核心判定
            judgment, relevance_score, judgment_method = _judge_focus(
                app_name, window_title, category, task_title, strictness
            )

            # excluded 应用：不参与分心计数，直接返回
            if judgment == "excluded":
                distraction_count = conn.execute(
                    "SELECT interrupted_count FROM pomodoro_sessions WHERE id = ?", (session_id,)
                ).fetchone()
                return jsonify({
                    "is_distraction": False,
                    "category": category,
                    "app_name": app_name,
                    "window_title": window_title,
                    "distraction_count": distraction_count[0] if distraction_count else 0,
                    "judgment": "focused",
                    "relevance_score": 1.0,
                    "judgment_method": "excluded",
                    "strictness": strictness,
                    "lock_action": "none",
                })

            # 判定为分心或疑似分心 -> 30秒去抖
            distracting_now = judgment in ("distracted", "suspected")
            now_ts = time.time()
            is_distraction = False
            if distracting_now:
                ep = _distraction_episodes.get(session_id)
                if ep is None:
                    _distraction_episodes[session_id] = {"first_seen": now_ts, "counted": False}
                elif not ep["counted"] and now_ts - ep["first_seen"] >= DWELL_THRESHOLD_SEC:
                    # 只有明确 distracted 才计数，suspected 不计数（只是提醒）
                    if judgment == "distracted":
                        is_distraction = True
                        ep["counted"] = True
            else:
                _distraction_episodes.pop(session_id, None)

            if is_distraction:
                conn.execute(
                    "UPDATE pomodoro_sessions "
                    "SET interrupted_count = interrupted_count + 1 WHERE id = ?",
                    (session_id,),
                )
                conn.commit()

            distraction_count = conn.execute(
                "SELECT interrupted_count FROM pomodoro_sessions WHERE id = ?", (session_id,)
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
            "window_title": window_title,
            "distraction_count": distraction_count[0] if distraction_count else 0,
            "judgment": judgment,
            "relevance_score": round(relevance_score, 3),
            "judgment_method": judgment_method,
            "strictness": strictness,
            "task_title": task_title,
            "lock_action": lock_action,
        })
    except Exception as e:
        logger.error(f"分心检测失败: {e}", exc_info=True)
        # 异常兜底：返回非分心，不崩溃
        return jsonify({
            "is_distraction": False,
            "category": "未知",
            "app_name": "",
            "window_title": "",
            "distraction_count": 0,
            "judgment": "focused",
            "relevance_score": 0.5,
            "judgment_method": "error_fallback",
            "strictness": DEFAULT_STRICTNESS,
            "lock_action": "none",
        })
