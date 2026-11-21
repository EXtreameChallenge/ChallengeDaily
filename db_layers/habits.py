"""ChallengeDaily db layer — 倒数日、聊天记录与习惯。"""
from db import *  # noqa: F401,F403
from db import _execute_with_retry  # noqa: F401
from db_layers.activities import _flush_pending_commits, get_activities  # noqa: F401

def insert_countdown(title, target_date, color="#7B68EE"):
    _flush_pending_commits()
    with get_conn() as conn:
        cursor = conn.execute("INSERT INTO countdowns (title, target_date, color) VALUES (?,?,?)", (title, target_date, color))
        conn.commit()
        return cursor.lastrowid

def get_countdowns():
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM countdowns ORDER BY target_date ASC").fetchall()
        return [dict(r) for r in rows]

def delete_countdown(cid):
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute("DELETE FROM countdowns WHERE id=?", (cid,))
        conn.commit()
        return True

# ── AI对话历史 ──
def insert_chat(role, content):
    _flush_pending_commits()
    with get_conn() as conn:
        cursor = conn.execute("INSERT INTO chat_history (role, content) VALUES (?,?)", (role, content))
        conn.commit()
        return cursor.lastrowid

def get_chat_history(limit=50):
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM chat_history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return list(reversed([dict(r) for r in rows]))

def clear_chat_history():
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute("DELETE FROM chat_history")
        conn.commit()
        return True

# ── 习惯追踪 ──
def insert_habit(name, target_count=1, period="daily", color="#7B68EE", auto_category=None):
    _flush_pending_commits()
    with get_conn() as conn:
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM habits").fetchone()[0]
        cursor = conn.execute("INSERT INTO habits (name, target_count, period, color, sort_order, auto_category) VALUES (?,?,?,?,?,?)", (name, target_count, period, color, max_order+1, auto_category))
        conn.commit()
        return cursor.lastrowid

def update_habit(habit_id, **kwargs):
    """更新习惯（P6-2：支持 auto_category 等字段）"""
    _flush_pending_commits()
    allowed = {'name', 'target_count', 'period', 'color', 'sort_order', 'auto_category'}
    with get_conn() as conn:
        sets = []
        params = []
        for k, v in kwargs.items():
            if k not in allowed:
                continue
            sets.append(f"{k}=?")
            params.append(v)
        if not sets:
            return False
        params.append(habit_id)
        conn.execute(f"UPDATE habits SET {','.join(sets)} WHERE id=?", params)
        conn.commit()
        return True

def get_habits():
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM habits ORDER BY sort_order ASC").fetchall()
        return [dict(r) for r in rows]

def auto_check_habits(target_date=None):
    """P6-2：根据活动分类时长自动为习惯打卡
    对于设置了 auto_category 的习惯，查询当日该分类的活动时长（分钟），
    如果达到 target_count 阈值则自动打卡。
    """
    from config import SCREENSHOT_INTERVAL_SEC
    _flush_pending_commits()
    if target_date is None:
        target_date = date.today().isoformat()
    interval_min = SCREENSHOT_INTERVAL_SEC / 60
    # 查询当日活动按分类聚合
    activities = get_activities(target_date, target_date)
    cat_minutes = {}
    for a in activities:
        cat = a.get("category", "其他")
        cat_minutes[cat] = cat_minutes.get(cat, 0) + interval_min
    # 查询所有设置了 auto_category 的习惯
    with get_conn() as conn:
        habits = conn.execute("SELECT * FROM habits WHERE auto_category IS NOT NULL").fetchall()
        # 查询当日已打卡的习惯ID集合
        logged = conn.execute("SELECT habit_id FROM habit_logs WHERE log_date=?", (target_date,)).fetchall()
        logged_ids = {r["habit_id"] for r in logged}
    auto_logged = []
    for h in habits:
        h = dict(h)
        auto_cat = h.get("auto_category", "")
        if not auto_cat:
            continue
        # 支持逗号分隔的多个分类
        cats = [c.strip() for c in auto_cat.split(",") if c.strip()]
        total_min = sum(cat_minutes.get(c, 0) for c in cats)
        # 阈值：target_count * 30 分钟（每个单位 30 分钟）
        threshold_min = h["target_count"] * 30
        if total_min >= threshold_min and h["id"] not in logged_ids:
            log_habit(h["id"], target_date, h["target_count"])
            auto_logged.append({
                "habit_id": h["id"],
                "habit_name": h["name"],
                "auto_category": auto_cat,
                "minutes": round(total_min, 1),
                "target_count": h["target_count"],
            })
    return auto_logged

def log_habit(habit_id, log_date=None, count=1):
    # UPSERT：依赖 V21 创建的唯一索引 idx_habit_logs_unique(habit_id, log_date)
    _flush_pending_commits()
    if log_date is None:
        log_date = date.today().isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO habit_logs (habit_id, log_date, count) VALUES (?, ?, ?)
            ON CONFLICT(habit_id, log_date) DO UPDATE SET count = count + ?
            """,
            (habit_id, log_date, count, count)
        )
        conn.commit()
        return True

def get_habit_logs(habit_id=None, days=30):
    _flush_pending_commits()
    cutoff = (date.today() - timedelta(days=int(days))).isoformat()
    with get_conn() as conn:
        if habit_id:
            rows = conn.execute("SELECT * FROM habit_logs WHERE habit_id=? AND log_date >= ? ORDER BY log_date DESC", (habit_id, cutoff)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM habit_logs WHERE log_date >= ? ORDER BY log_date DESC", (cutoff,)).fetchall()
        return [dict(r) for r in rows]


def get_habit_stats(habit_id: int, days: int = 30) -> dict:
    """P13-2：获取单个习惯的统计数据
    返回: { habit_id, streak_days, completion_rate, total_logs, recent_trend }
    recent_trend: 近 N 天每日打卡情况 [{date, logged, count}]
    """
    _flush_pending_commits()
    today = date.today()
    cutoff = (today - timedelta(days=int(days) - 1)).isoformat()
    with get_conn() as conn:
        # 获取近 N 天所有打卡记录
        rows = conn.execute(
            "SELECT log_date, count FROM habit_logs WHERE habit_id=? AND log_date >= ? ORDER BY log_date ASC",
            (habit_id, cutoff),
        ).fetchall()
        # 获取习惯信息
        habit_row = conn.execute("SELECT * FROM habits WHERE id=?", (habit_id,)).fetchone()
    if not habit_row:
        return {"habit_id": habit_id, "streak_days": 0, "completion_rate": 0,
                "total_logs": 0, "recent_trend": []}
    habit = dict(habit_row)
    period = habit.get("period", "daily")
    # 构造每日打卡字典
    log_map = {r["log_date"]: r["count"] for r in rows}
    # 计算连续打卡天数（从今天向前数）
    streak = 0
    cur = today
    while cur.isoformat() in log_map:
        streak += 1
        cur -= timedelta(days=1)
    # 计算完成率（近 N 天中打卡天数占比）
    total_days = int(days)
    logged_days = len(log_map)
    completion_rate = round(logged_days / total_days * 100, 1) if total_days > 0 else 0
    # 构造趋势数据
    trend = []
    for i in range(total_days):
        d = (today - timedelta(days=total_days - 1 - i)).isoformat()
        trend.append({"date": d, "logged": d in log_map, "count": log_map.get(d, 0)})
    return {
        "habit_id": habit_id,
        "streak_days": streak,
        "completion_rate": completion_rate,
        "total_logs": logged_days,
        "period": period,
        "target_count": habit.get("target_count", 1),
        "recent_trend": trend,
    }

def delete_habit(habit_id):
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute("DELETE FROM habit_logs WHERE habit_id=?", (habit_id,))
        conn.execute("DELETE FROM habits WHERE id=?", (habit_id,))
        conn.commit()
        return True

# P14-2：基于行为数据智能推荐习惯
# 推荐策略：
#   1. 数据驱动：统计近 30 天活动分类频次，对尚未建立习惯的高频分类推荐打卡
#   2. 经典补充：当用户习惯较少时，补充饮水/运动/阅读等通用健康习惯
#   3. 去重：排除已存在同名习惯或已关联同一 auto_category 的习惯
def recommend_habits(limit: int = 5) -> list:
    _flush_pending_commits()
    today = date.today()
    cutoff = (today - timedelta(days=30)).isoformat()
    # 1. 聚合近 30 天活动分类频次
    with get_conn() as conn:
        cat_rows = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM activities "
            "WHERE timestamp >= ? AND timestamp <= ? AND category IS NOT NULL AND category != '' "
            "GROUP BY category ORDER BY cnt DESC",
            (f"{cutoff} 00:00:00", f"{today.isoformat()} 23:59:59"),
        ).fetchall()
        habits_rows = conn.execute("SELECT name, auto_category FROM habits").fetchall()
    existing_names = {r["name"] for r in habits_rows}
    existing_autos = {r["auto_category"] for r in habits_rows if r["auto_category"]}

    suggestions = []
    # 数据驱动推荐：高频分类 → 建议打卡
    for r in cat_rows:
        cat = r["category"]
        cnt = r["cnt"]
        if cnt < 5:  # 频次过低不推荐
            continue
        # 去重：已有关联该分类的习惯
        if cat in existing_autos:
            continue
        avg_per_day = round(cnt / 30, 1)
        target = max(1, min(5, round(avg_per_day)))
        # 避免与已有习惯同名
        suggest_name = f"每日{cat}"
        if suggest_name in existing_names:
            suggest_name = f"{cat}打卡"
        if suggest_name in existing_names:
            continue
        suggestions.append({
            "name": suggest_name,
            "target_count": target,
            "period": "daily",
            "auto_category": cat,
            "reason": f"近 30 天你在「{cat}」上记录了 {cnt} 次活动，平均每日 {avg_per_day} 次",
            "source": "behavior",
            "score": cnt,
        })

    # 2. 经典补充：习惯总数不足 3 个时，推荐通用健康习惯
    if len(habits_rows) < 3:
        classics = [
            {"name": "每日饮水", "target_count": 8, "auto_category": None, "reason": "保持充足饮水有助于专注与精力，建议每日 8 杯"},
            {"name": "每日运动", "target_count": 1, "auto_category": None, "reason": "适度运动提升专注力与情绪，建议每日至少 1 次"},
            {"name": "每日阅读", "target_count": 1, "auto_category": "学习", "reason": "每日阅读累积知识，长期复利显著"},
        ]
        for c in classics:
            if c["name"] in existing_names:
                continue
            if c["auto_category"] and c["auto_category"] in existing_autos:
                continue
            suggestions.append({
                "name": c["name"],
                "target_count": c["target_count"],
                "period": "daily",
                "auto_category": c["auto_category"],
                "reason": c["reason"],
                "source": "classic",
                "score": 0,
            })

    # 排序：数据驱动优先（按 score 降序），经典补充在后；截断到 limit
    suggestions.sort(key=lambda x: (x["source"] == "behavior", x["score"]), reverse=True)
    return suggestions[:limit]


# ── 格言 ──
QUOTES = [
    "种一棵树最好的时间是十年前，其次是现在。",
    "不积跬步，无以至千里；不积小流，无以成江海。",
    "业精于勤，荒于嬉；行成于思，毁于随。",
    "天下事有难易乎？为之，则难者亦易矣；不为，则易者亦难矣。",
    "合抱之木，生于毫末；九层之台，起于累土；千里之行，始于足下。",
    "锲而舍之，朽木不折；锲而不舍，金石可镂。",
    "路漫漫其修远兮，吾将上下而求索。",
    "宝剑锋从磨砺出，梅花香自苦寒来。",
    "千磨万击还坚劲，任尔东西南北风。",
    "长风破浪会有时，直挂云帆济沧海。",
    "莫等闲，白了少年头，空悲切。",
    "盛年不重来，一日难再晨。及时当勉励，岁月不待人。",
    "三更灯火五更鸡，正是男儿读书时。",
    "黑发不知勤学早，白首方悔读书迟。",
    "少年易老学难成，一寸光阴不可轻。",
    "The best time to plant a tree was 20 years ago. The second best time is now.",
    "Focus is a matter of deciding what things you're not going to do.",
    "The successful warrior is the average man, with laser-like focus.",
    "Discipline is the bridge between goals and accomplishment.",
    "You don't have to be great to start, but you have to start to be great.",
]


