"""ChallengeDaily db layer — 番茄钟与待办事项。"""
from db import *  # noqa: F401,F403
from db import _execute_with_retry  # noqa: F401
from db_layers.activities import _flush_pending_commits  # noqa: F401

def insert_pomodoro_session(start_time, end_time, duration_min, task="", category="开发", status="completed", interrupted_count=0, source="manual"):
    _flush_pending_commits()
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO pomodoro_sessions (start_time, end_time, duration_min, task, category, status, interrupted_count, source) VALUES (?,?,?,?,?,?,?,?)",
            (start_time, end_time, duration_min, task, category, status, interrupted_count, source)
        )
        conn.commit()
        return cursor.lastrowid

def update_pomodoro_session(session_id, **kwargs):
    # 白名单校验：防止通过 kwargs 注入非法列名
    safe = {k: v for k, v in kwargs.items() if k in _ALLOWED_POMODORO_FIELDS}
    if not safe:
        logger.warning(f"update_pomodoro_session: 无合法字段可更新, kwargs={list(kwargs.keys())}")
        return False
    _flush_pending_commits()
    with get_conn() as conn:
        sets = ", ".join([f"{k}=?" for k in safe])
        vals = list(safe.values()) + [session_id]
        conn.execute(f"UPDATE pomodoro_sessions SET {sets} WHERE id=?", vals)
        conn.commit()
        return True

def get_pomodoro_sessions(date_str=None):
    _flush_pending_commits()
    with get_conn() as conn:
        if date_str:
            rows = conn.execute("SELECT * FROM pomodoro_sessions WHERE start_time LIKE ? ORDER BY start_time DESC", (f"{date_str}%",)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM pomodoro_sessions ORDER BY start_time DESC LIMIT 100").fetchall()
        return [dict(r) for r in rows]

def get_pomodoro_stats(range_type="week"):
    _flush_pending_commits()
    with get_conn() as conn:
        if range_type == "week":
            rows = conn.execute("""
                SELECT date(start_time) as d, COUNT(*) as cnt, SUM(duration_min) as total_min
                FROM pomodoro_sessions WHERE status='completed' AND start_time >= date('now','-7 days','localtime')
                GROUP BY date(start_time) ORDER BY d
            """).fetchall()
        else:
            rows = conn.execute("""
                SELECT date(start_time) as d, COUNT(*) as cnt, SUM(duration_min) as total_min
                FROM pomodoro_sessions WHERE status='completed' AND start_time >= date('now','-30 days','localtime')
                GROUP BY date(start_time) ORDER BY d
            """).fetchall()
        return [dict(r) for r in rows]

def get_pomodoro_streak():
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT DISTINCT date(start_time) as d FROM pomodoro_sessions
            WHERE status='completed' ORDER BY d DESC
        """).fetchall()
        if not rows:
            return 0
        dates = [r["d"] for r in rows]
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        # 如果今天没完成，从昨天开始数
        check_date = today if today in dates else yesterday
        if check_date not in dates:
            return 0
        streak = 0
        while check_date in dates:
            streak += 1
            check_date = (datetime.strptime(check_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        return streak

def get_pomodoro_today_count():
    _flush_pending_commits()
    with get_conn() as conn:
        today = date.today().isoformat()
        # 跨午夜修复：番茄钟可能从昨晚开始到今早结束，仅按 start_time 过滤会漏掉这些
        row = conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(duration_min),0) as total_min "
            "FROM pomodoro_sessions "
            "WHERE status='completed' AND (date(start_time)=? OR date(end_time)=?)",
            (today, today)
        ).fetchone()
        return {"count": row["cnt"], "total_min": row["total_min"]}


def get_pomodoro_quality_score(date_str=None):
    """专注质量评分：破解番茄TODO"为凑时长而专注"陷阱

    质量分 = 时长基准分 × 纯度系数 × 完成度系数
    - 时长基准分: min(total_min/120, 1) * 60  (120分钟满分60)
    - 纯度系数: 1 - interrupted_count/total_sessions * 0.5  (分心最多扣50%)
    - 完成度系数: completed_sessions/total_sessions
    """
    _flush_pending_commits()
    with get_conn() as conn:
        if date_str is None:
            date_str = date.today().isoformat()
        row = conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed, "
            "COALESCE(SUM(CASE WHEN status='completed' THEN duration_min ELSE 0 END), 0) as total_min, "
            "COALESCE(SUM(interrupted_count), 0) as total_interrupted "
            "FROM pomodoro_sessions "
            "WHERE date(start_time)=? OR date(end_time)=?",
            (date_str, date_str)
        ).fetchone()
        total = row["total"] or 0
        completed = row["completed"] or 0
        total_min = row["total_min"] or 0
        total_interrupted = row["total_interrupted"] or 0

        if total == 0:
            return {"score": 0, "grade": "—", "total_min": 0, "completed": 0,
                    "total": 0, "purity": 0, "completion": 0, "distraction_count": 0}

        # 时长基准分（120分钟满分60分）
        time_score = min(total_min / 120, 1) * 60
        # 纯度系数：每个分心番茄扣分，最低0.5
        avg_interrupted = total_interrupted / total
        purity = max(1 - avg_interrupted * 0.15, 0.5)
        # 完成度系数
        completion = completed / total

        score = round(time_score * purity * completion, 1)
        grade = "S" if score >= 80 else "A" if score >= 60 else "B" if score >= 40 else "C" if score >= 20 else "D"

        return {
            "score": score, "grade": grade, "total_min": total_min,
            "completed": completed, "total": total,
            "purity": round(purity * 100), "completion": round(completion * 100),
            "distraction_count": total_interrupted,
        }


# ── 待办清单 ──
_ALLOWED_TODO_FIELDS = {"title", "category", "mode", "target_min", "repeat_type", "repeat_days",
                        "due_date", "priority", "status", "completed_at", "task_level",
                        "parent_id", "assigned_date", "week_start", "month_key", "color",
                        "progress_min", "pomodoro_count", "estimated_pomodoros", "pomodoro_size",
                        "goal_id", "plan_start_min", "sort_order"}

# 番茄钟允许更新的字段白名单（防 SQL 注入：列名不能参数化，必须白名单校验）
_ALLOWED_POMODORO_FIELDS = {"status", "end_time", "duration_min", "interrupted_count", "task", "category",
                            "todo_id", "pomodoro_index", "total_pomodoros"}

def insert_todo(title, category="开发", mode="timer", target_min=25, repeat_type="none", repeat_days="", due_date=None, priority=2,
                task_level="day", parent_id=None, assigned_date=None, week_start=None, month_key=None, color=None,
                estimated_pomodoros=1, pomodoro_size="big", goal_id=None):
    _flush_pending_commits()
    with get_conn() as conn:
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM todos").fetchone()[0]
        cursor = conn.execute(
            "INSERT INTO todos (title, category, mode, target_min, repeat_type, repeat_days, due_date, priority, sort_order, "
            "task_level, parent_id, assigned_date, week_start, month_key, color, estimated_pomodoros, pomodoro_size, goal_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (title, category, mode, target_min, repeat_type, repeat_days, due_date, priority, max_order+1,
             task_level, parent_id, assigned_date, week_start, month_key, color, estimated_pomodoros, pomodoro_size, goal_id)
        )
        conn.commit()
        return cursor.lastrowid

def get_todos(status_filter=None, level=None, week_start=None, assigned_date=None, parent_id=None):
    _flush_pending_commits()
    with get_conn() as conn:
        sql = "SELECT * FROM todos WHERE 1=1"
        params = []
        if status_filter and status_filter != "all":
            sql += " AND status=?"
            params.append(status_filter)
        if level:
            sql += " AND task_level=?"
            params.append(level)
        if week_start:
            sql += " AND week_start=?"
            params.append(week_start)
        if assigned_date:
            sql += " AND assigned_date=?"
            params.append(assigned_date)
        if parent_id is not None:
            sql += " AND parent_id=?"
            params.append(parent_id)
        sql += " ORDER BY status ASC, priority ASC, sort_order ASC"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

def update_todo(todo_id, **kwargs):
    # 白名单校验：防止通过 kwargs 注入非法列名（id 不能被外部更新）
    safe = {k: v for k, v in kwargs.items() if k in _ALLOWED_TODO_FIELDS}
    if not safe:
        logger.warning(f"update_todo: 无合法字段可更新, kwargs={list(kwargs.keys())}")
        return False
    _flush_pending_commits()
    with get_conn() as conn:
        sets = ", ".join([f"{k}=?" for k in safe])
        vals = list(safe.values()) + [todo_id]
        conn.execute(f"UPDATE todos SET {sets}, updated_at=datetime('now','localtime') WHERE id=?", vals)
        conn.commit()
        return True

def delete_todo(todo_id):
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute("DELETE FROM todos WHERE id=?", (todo_id,))
        conn.commit()
        return True

def update_todo_progress(todo_id, minutes):
    # 原子更新：避免 read-modify-write 在并发场景下丢失更新
    _flush_pending_commits()
    with get_conn() as conn:
        # 先检查任务是否存在
        exists = conn.execute("SELECT 1 FROM todos WHERE id=?", (todo_id,)).fetchone()
        if not exists:
            return False
        # 直接原子加，避免读取后再写入造成竞态
        conn.execute(
            "UPDATE todos SET progress_min = progress_min + ?, pomodoro_count = pomodoro_count + 1, "
            "updated_at=datetime('now','localtime') WHERE id=?",
            (minutes, todo_id)
        )
        # 然后检查是否需要自动完成
        row = conn.execute("SELECT progress_min, target_min, mode, parent_id FROM todos WHERE id=?", (todo_id,)).fetchone()
        if row and row["mode"] == "goal" and row["progress_min"] >= row["target_min"]:
            conn.execute(
                "UPDATE todos SET status='completed', completed_at=datetime('now','localtime') WHERE id=?",
                (todo_id,)
            )
        # 子任务进度聚合到父任务：父 progress_min = SUM(子任务 progress_min)
        if row and row["parent_id"]:
            parent_id = row["parent_id"]
            agg = conn.execute(
                "SELECT COALESCE(SUM(progress_min), 0) as total FROM todos WHERE parent_id=?",
                (parent_id,)
            ).fetchone()
            conn.execute(
                "UPDATE todos SET progress_min=?, updated_at=datetime('now','localtime') WHERE id=?",
                (agg["total"], parent_id)
            )
            # 父任务自动完成检查
            parent_row = conn.execute("SELECT progress_min, target_min, mode FROM todos WHERE id=?", (parent_id,)).fetchone()
            if parent_row and parent_row["mode"] == "goal" and parent_row["progress_min"] >= parent_row["target_min"]:
                conn.execute(
                    "UPDATE todos SET status='completed', completed_at=datetime('now','localtime') WHERE id=?",
                    (parent_id,)
                )
        conn.commit()
        return True

# ── 每日日记 ──

