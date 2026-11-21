"""ChallengeDaily db layer — 日记、目标与成就。"""
from db import *  # noqa: F401,F403
from db import _execute_with_retry  # noqa: F401
from db_layers.activities import _flush_pending_commits, get_activities  # noqa: F401
from db_layers.productivity import get_pomodoro_stats, get_pomodoro_streak, get_pomodoro_today_count  # noqa: F401

def upsert_diary(diary_date, mood="", weather="", content="", tags="", highlights="", gratitude="", media_json="[]", font_style=""):
    _flush_pending_commits()
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM diaries WHERE diary_date=?", (diary_date,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE diaries SET mood=?, weather=?, content=?, tags=?, highlights=?, gratitude=?, media_json=?, font_style=?, updated_at=datetime('now','localtime') WHERE diary_date=?",
                (mood, weather, content, tags, highlights, gratitude, media_json, font_style, diary_date)
            )
        else:
            conn.execute(
                "INSERT INTO diaries (diary_date, mood, weather, content, tags, highlights, gratitude, media_json, font_style) VALUES (?,?,?,?,?,?,?,?,?)",
                (diary_date, mood, weather, content, tags, highlights, gratitude, media_json, font_style)
            )
        conn.commit()
        return True

def get_diary(diary_date):
    _flush_pending_commits()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM diaries WHERE diary_date=?", (diary_date,)).fetchone()
        return dict(row) if row else None

def get_diaries(limit=30):
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM diaries ORDER BY diary_date DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

def get_diary_dates():
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute("SELECT diary_date FROM diaries ORDER BY diary_date DESC").fetchall()
        return [r["diary_date"] for r in rows]


def get_mood_heatmap(year=None):
    """心情热力图：返回指定年份每天的心情（GoalDay集大成——心情趋势可视化）"""
    _flush_pending_commits()
    import datetime as _dt
    if year is None:
        year = _dt.date.today().year
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT diary_date, mood FROM diaries WHERE diary_date LIKE ? AND mood != '' ORDER BY diary_date",
            (f"{year}%",),
        ).fetchall()
    return [{"date": r["diary_date"], "mood": r["mood"]} for r in rows]


# ── 长期目标管理（GoalDay集大成） ──
def create_goal(title, description="", category="personal", timeframe="yearly",
                start_date=None, target_date=None, key_results=None,
                linked_todos=None, linked_habits=None, color="#6366f1"):
    _flush_pending_commits()
    import datetime as _dt
    import json as _json
    if start_date is None:
        start_date = _dt.date.today().isoformat()
    if target_date is None:
        # yearly=一年后, quarterly=3月后, monthly=1月后
        delta = {"yearly": 365, "quarterly": 90, "monthly": 30}.get(timeframe, 365)
        target_date = (_dt.date.today() + _dt.timedelta(days=delta)).isoformat()
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO goals (title, description, category, timeframe, start_date, target_date,
               key_results, linked_todos, linked_habits, color)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (title, description, category, timeframe, start_date, target_date,
             _json.dumps(key_results or [], ensure_ascii=False),
             _json.dumps(linked_todos or [], ensure_ascii=False),
             _json.dumps(linked_habits or [], ensure_ascii=False),
             color),
        )
        conn.commit()
        return cur.lastrowid


def get_goals(status=None, timeframe=None):
    _flush_pending_commits()
    import json as _json
    with get_conn() as conn:
        sql = "SELECT * FROM goals WHERE 1=1"
        params = []
        if status:
            sql += " AND status=?"
            params.append(status)
        if timeframe:
            sql += " AND timeframe=?"
            params.append(timeframe)
        sql += " ORDER BY target_date ASC"
        rows = conn.execute(sql, params).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d['key_results'] = _json.loads(d.get('key_results') or '[]')
        d['linked_todos'] = _json.loads(d.get('linked_todos') or '[]')
        d['linked_habits'] = _json.loads(d.get('linked_habits') or '[]')
        results.append(d)
    return results


def update_goal(goal_id, **kwargs):
    _flush_pending_commits()
    import json as _json
    allowed = {'title', 'description', 'category', 'timeframe', 'start_date', 'target_date',
               'status', 'progress', 'key_results', 'linked_todos', 'linked_habits', 'color'}
    with get_conn() as conn:
        sets = []
        params = []
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            if k in ('key_results', 'linked_todos', 'linked_habits'):
                v = _json.dumps(v, ensure_ascii=False)
            sets.append(f"{k}=?")
            params.append(v)
        if not sets:
            return False
        sets.append("updated_at=datetime('now','localtime')")
        params.append(goal_id)
        conn.execute(f"UPDATE goals SET {','.join(sets)} WHERE id=?", params)
        conn.commit()
        return True


def delete_goal(goal_id):
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute("DELETE FROM goals WHERE id=?", (goal_id,))
        conn.commit()
        return True


def get_goal_progress(goal_id):
    """获取目标进度：关联待办总数/已完成数/自动计算进度百分比"""
    _flush_pending_commits()
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM todos WHERE goal_id=?", (goal_id,)).fetchone()[0]
        completed = conn.execute(
            "SELECT COUNT(*) FROM todos WHERE goal_id=? AND status='completed'", (goal_id,)
        ).fetchone()[0]
    return {
        "total_todos": total,
        "completed_todos": completed,
        "auto_progress": round(completed / total * 100, 1) if total > 0 else 0,
    }


def get_goal_summary():
    """目标概览：所有活跃目标的进度摘要（用于仪表盘）"""
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, title, category, timeframe, target_date, progress, color, status FROM goals WHERE status='active' ORDER BY target_date ASC"
        ).fetchall()
    return [dict(r) for r in rows]


# ── 成就系统 ──
def get_achievements():
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM achievements ORDER BY unlocked_at DESC").fetchall()
        return [dict(r) for r in rows]

def unlock_achievement(code, name, description="", icon="🏆"):
    _flush_pending_commits()
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM achievements WHERE code=?", (code,)).fetchone()
        if existing:
            return False
        conn.execute("INSERT INTO achievements (code, name, description, icon, unlocked_at) VALUES (?,?,?,?,datetime('now','localtime'))",
                     (code, name, description, icon))
        conn.commit()
        return True

def check_and_unlock_achievements():
    """检查并解锁成就（P6-4：补全5个缺失成就+3个隐藏彩蛋）"""
    from datetime import date as _date
    unlocked = []
    # 获取番茄钟统计
    today = get_pomodoro_today_count()
    streak = get_pomodoro_streak()
    stats = get_pomodoro_stats("month")
    total_count = sum(s["cnt"] for s in stats) if stats else 0
    total_min = sum(s["total_min"] for s in stats) if stats else 0

    # ── 查询今日活动数据（用于成就判定）──
    today_str = _date.today().isoformat()
    today_acts = []
    today_cats = {}
    earliest_ts = None
    latest_ts = None
    try:
        today_acts = get_activities(today_str, today_str)
        for a in today_acts:
            cat = a.get("category", "其他")
            today_cats[cat] = today_cats.get(cat, 0) + 1
            ts = a.get("timestamp", "")
            if ts:
                if earliest_ts is None or ts < earliest_ts:
                    earliest_ts = ts
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
    except Exception:
        pass

    # 深度工作时长（分钟）：活动数 × 采样间隔 / 60
    deep_min = 0
    try:
        from config import SCREENSHOT_INTERVAL_SEC
        deep_min = len(today_acts) * SCREENSHOT_INTERVAL_SEC / 60
    except Exception:
        pass

    # 今日待办完成情况
    today_total_todos = 0
    today_completed_todos = 0
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as total, SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as done "
                "FROM todos WHERE assigned_date=? OR (assigned_date IS NULL AND date(created_at)=?)",
                (today_str, today_str)
            ).fetchone()
            today_total_todos = row["total"] if row else 0
            today_completed_todos = row["done"] if row else 0
    except Exception:
        pass

    # 番茄钟效率
    pomo_efficiency = 0
    try:
        if today.get("total", 0) > 0:
            pomo_efficiency = today["count"] / today["total"]
    except Exception:
        pass

    # 最早/最晚活动时间的小时数
    earliest_hour = int(earliest_ts[11:13]) if earliest_ts and len(earliest_ts) >= 13 else 99
    latest_hour = int(latest_ts[11:13]) if latest_ts and len(latest_ts) >= 13 else -1

    # 累计活动天数
    total_active_days = 0
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT COUNT(DISTINCT date(timestamp)) as days FROM activities").fetchone()
            total_active_days = row["days"] if row else 0
    except Exception:
        pass

    # 最长连续同类活动（分钟）
    max_same_cat_streak_min = 0
    try:
        if today_acts:
            sorted_acts = sorted(today_acts, key=lambda x: x.get("timestamp", ""))
            current_cat = None
            current_count = 0
            for a in sorted_acts:
                cat = a.get("category", "其他")
                if cat == current_cat:
                    current_count += 1
                else:
                    current_cat = cat
                    current_count = 1
                if current_count > max_same_cat_streak_min:
                    max_same_cat_streak_min = current_count
            from config import SCREENSHOT_INTERVAL_SEC as _interval
            max_same_cat_streak_min = max_same_cat_streak_min * _interval / 60
    except Exception:
        pass

    checks = [
        # ── 番茄钟系列（原有5个）──
        ("first_pomodoro", "初心者", "完成第一个番茄钟", "🌱", False, today["count"] >= 1),
        ("pomodoro_100", "百斩", "累计完成100个番茄钟", "💯", False, total_count >= 100),
        ("pomodoro_1000", "千时", "累计专注1000小时", "⏰", False, total_min >= 60000),
        ("streak_7", "连续7天", "连续7天完成专注", "🔥", False, streak >= 7),
        ("streak_30", "坚持不懈", "连续30天完成专注", "💎", False, streak >= 30),
        # ── 补全5个缺失成就 ──
        ("deep_master", "深度大师", "单日深度工作≥4小时", "🧠", False, deep_min >= 240),
        ("early_bird", "早起鸟", "6:00前开始专注", "🐦", False, earliest_hour < 6),
        ("night_owl", "夜猫子", "23:00后仍在专注", "🦉", False, latest_hour >= 23),
        ("full_clear", "全勤奖", "一天完成所有待办", "✨", False,
         today_total_todos > 0 and today_completed_todos == today_total_todos),
        ("efficiency_king", "效率之王", "日专注效率≥80%", "👑", False, pomo_efficiency >= 0.8),
        # ── 隐藏彩蛋成就（hidden=True）──
        ("polymath", "多面手", "一天内涉及8个以上分类", "🎭", True, len(today_cats) >= 8),
        ("zen_master", "禅定", "连续4小时不切换分类", "🧘", True, max_same_cat_streak_min >= 240),
        ("century_mark", "百日修行", "累计记录100天活动", "🏛️", True, total_active_days >= 100),
        # P13-3：新增 3 个隐藏彩蛋成就
        ("night_owl_7", "夜猫子修行", "连续7天23点后仍在专注", "🌙", True, False),  # 需多日聚合，下方特殊判定
        ("habit_master", "习惯养成大师", "连续30天打卡任意习惯", "⭐", True, False),  # 需习惯数据，下方特殊判定
        ("ai_explorer", "AI 探索者", "累计与 AI 对话 100 次", "🤖", True, False),  # 需对话数据，下方特殊判定
    ]
    for code, name, desc, icon, hidden, condition in checks:
        if condition and unlock_achievement(code, name, desc, icon):
            unlocked.append({"code": code, "name": name, "icon": icon, "hidden": hidden})

    # P13-3：特殊判定的隐藏成就（需多日聚合数据）
    try:
        # 夜猫子修行：连续7天23点后仍在专注
        with get_conn() as conn:
            night_owl_rows = conn.execute(
                "SELECT DISTINCT date(timestamp) AS d FROM activities "
                "WHERE strftime('%H', timestamp) >= '23' "
                "AND date(timestamp) >= date('now', '-14 days') "
                "ORDER BY d DESC LIMIT 10"
            ).fetchall()
            if len(night_owl_rows) >= 7:
                # 检查是否连续7天
                night_dates = {r["d"] for r in night_owl_rows}
                consec = 0
                cur_date = _date.today()
                from datetime import timedelta as _td
                while cur_date.isoformat() in night_dates:
                    consec += 1
                    cur_date -= _td(days=1)
                if consec >= 7 and unlock_achievement("night_owl_7", "夜猫子修行", "连续7天23点后仍在专注", "🌙"):
                    unlocked.append({"code": "night_owl_7", "name": "夜猫子修行", "icon": "🌙", "hidden": True})

        # 习惯养成大师：连续30天打卡任意习惯
        with get_conn() as conn:
            habit_streak_rows = conn.execute(
                "SELECT log_date, COUNT(DISTINCT habit_id) AS cnt FROM habit_logs "
                "WHERE log_date >= date('now', '-35 days') "
                "GROUP BY log_date ORDER BY log_date DESC"
            ).fetchall()
            if len(habit_streak_rows) >= 30:
                habit_dates = {r["log_date"] for r in habit_streak_rows}
                consec = 0
                cur_date = _date.today()
                from datetime import timedelta as _td2
                while cur_date.isoformat() in habit_dates:
                    consec += 1
                    cur_date -= _td2(days=1)
                if consec >= 30 and unlock_achievement("habit_master", "习惯养成大师", "连续30天打卡任意习惯", "⭐"):
                    unlocked.append({"code": "habit_master", "name": "习惯养成大师", "icon": "⭐", "hidden": True})

        # AI 探索者：累计与 AI 对话 100 次
        with get_conn() as conn:
            ai_count_row = conn.execute(
                "SELECT COUNT(*) AS c FROM chat_history WHERE role='user'"
            ).fetchone()
            if ai_count_row and ai_count_row["c"] >= 100:
                if unlock_achievement("ai_explorer", "AI 探索者", "累计与 AI 对话 100 次", "🤖"):
                    unlocked.append({"code": "ai_explorer", "name": "AI 探索者", "icon": "🤖", "hidden": True})
    except Exception:
        pass

    return unlocked

# ── 倒数日 ──

