"""ChallengeDaily db layer — 周/月计划、任务分配与画像分析。"""
from db import *  # noqa: F401,F403
from db import _execute_with_retry  # noqa: F401
from db_layers.activities import _flush_pending_commits  # noqa: F401
from db_layers.apps import _parse_json, _serialize_json  # noqa: F401

def get_random_quote():
    return random.choice(QUOTES)


# ── 周计划（月/周/日三级层级） ──
def _week_start_of(d: date) -> str:
    """返回 ISO 8601 周一日期字符串 YYYY-MM-DD"""
    return (d - timedelta(days=d.weekday())).strftime('%Y-%m-%d')


def get_month_tasks(month_key: str) -> list[dict]:
    """获取月任务及其下所有周任务的进度汇总"""
    _flush_pending_commits()
    with get_conn() as conn:
        months = conn.execute(
            "SELECT * FROM todos WHERE task_level='month' AND month_key=? ORDER BY priority ASC, sort_order ASC",
            (month_key,)
        ).fetchall()
        result = []
        for m in months:
            m_dict = dict(m)
            # 子任务进度
            children = conn.execute(
                "SELECT id, title, status, progress_min, target_min, week_start, assigned_date FROM todos WHERE parent_id=? ORDER BY week_start ASC, sort_order ASC",
                (m_dict['id'],)
            ).fetchall()
            total_target = sum(c['target_min'] or 0 for c in children)
            total_progress = sum(c['progress_min'] or 0 for c in children)
            m_dict['children'] = [dict(c) for c in children]
            m_dict['total_target_min'] = total_target
            m_dict['total_progress_min'] = total_progress
            m_dict['progress_pct'] = int(total_progress / total_target * 100) if total_target > 0 else 0
            result.append(m_dict)
        return result


def get_week_tasks(week_start: str) -> dict:
    """获取周任务+七日日任务（周计划主视图数据）"""
    _flush_pending_commits()
    with get_conn() as conn:
        # 周任务
        week_tasks = conn.execute(
            "SELECT * FROM todos WHERE task_level='week' AND week_start=? ORDER BY priority ASC, sort_order ASC",
            (week_start,)
        ).fetchall()
        # 该周内所有日任务（含已分配和未分配但属于该周）
        # 注意：待分配区是 task_level='day' AND assigned_date IS NULL，不属于特定周
        start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
        dates = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
        day_tasks_by_date = {}
        for d in dates:
            rows = conn.execute(
                "SELECT * FROM todos WHERE task_level='day' AND assigned_date=? ORDER BY priority ASC, sort_order ASC",
                (d,)
            ).fetchall()
            day_tasks_by_date[d] = [dict(r) for r in rows]
        return {
            'week_start': week_start,
            'dates': dates,
            'week_tasks': [dict(r) for r in week_tasks],
            'day_tasks': day_tasks_by_date,
        }


def get_unassigned_todos(limit: int = 50) -> list[dict]:
    """获取待分配区任务（task_level='day' AND assigned_date IS NULL）"""
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM todos WHERE task_level='day' AND assigned_date IS NULL ORDER BY priority ASC, sort_order ASC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def assign_todo(todo_id: int, assigned_date: str = None, week_start: str = None, task_level: str = 'day', plan_start_min: int = None) -> bool:
    """分配任务到某天/某周/升级层级，可选设置计划开始时刻"""
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute(
            "UPDATE todos SET assigned_date=?, week_start=?, task_level=?, plan_start_min=?, updated_at=datetime('now','localtime') WHERE id=?",
            (assigned_date, week_start, task_level, plan_start_min, todo_id)
        )
        conn.commit()
        return True


def unassign_todo(todo_id: int) -> bool:
    """移回待分配区（清空 assigned_date，task_level 保留为 day）"""
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute(
            "UPDATE todos SET assigned_date=NULL, updated_at=datetime('now','localtime') WHERE id=?",
            (todo_id,)
        )
        conn.commit()
        return True


def split_task(parent_id: int, title: str, week_start: str, task_level: str = 'week',
               category: str = '开发', mode: str = 'timer', target_min: int = 25, priority: int = 2) -> int:
    """月任务拆解为周任务（或周任务拆解为日任务）"""
    _flush_pending_commits()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO todos (title, category, mode, target_min, priority, parent_id, task_level, week_start, status) "
            "VALUES (?,?,?,?,?,?,?,?, 'pending')",
            (title, category, mode, target_min, priority, parent_id, task_level, week_start)
        )
        conn.commit()
        return cur.lastrowid


def get_week_plan_stats(week_start: str) -> dict:
    """本周数据条统计：专注柱状图+完成率+深度+中断+连续"""
    _flush_pending_commits()
    start_date = datetime.strptime(week_start, '%Y-%m-%d').date()
    dates = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    with get_conn() as conn:
        # 每日专注分钟
        daily_focus = []
        for d in dates:
            row = conn.execute(
                "SELECT COALESCE(SUM(duration_min),0) as total FROM pomodoro_sessions WHERE date(start_time)=? AND status='completed'",
                (d,)
            ).fetchone()
            daily_focus.append({'date': d, 'focus_min': row['total'] or 0})
        # 本周总专注
        total_row = conn.execute(
            "SELECT COALESCE(SUM(duration_min),0) as total FROM pomodoro_sessions "
            "WHERE date(start_time)>=? AND date(start_time)<=? AND status='completed'",
            (dates[0], dates[6])
        ).fetchone()
        total_focus = total_row['total'] or 0
        # 本周深度工作（≥25min 完整番茄）
        deep_row = conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(duration_min),0) as total FROM pomodoro_sessions "
            "WHERE date(start_time)>=? AND date(start_time)<=? AND status='completed' AND duration_min>=25 AND interrupted_count=0",
            (dates[0], dates[6])
        ).fetchone()
        deep_focus = deep_row['total'] or 0
        # 中断次数
        interrupt_row = conn.execute(
            "SELECT COALESCE(SUM(interrupted_count),0) as total FROM pomodoro_sessions "
            "WHERE date(start_time)>=? AND date(start_time)<=?",
            (dates[0], dates[6])
        ).fetchone()
        interrupts = interrupt_row['total'] or 0
        # 完成率（本周日任务）
        completed_row = conn.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as done FROM todos "
            "WHERE task_level='day' AND assigned_date>=? AND assigned_date<=?",
            (dates[0], dates[6])
        ).fetchone()
        total_tasks = completed_row['total'] or 0
        completed_tasks = completed_row['done'] or 0
        # 连续天数（从今日向前数）
        streak = 0
        today = date.today()
        for i in range(365):
            d = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM pomodoro_sessions WHERE date(start_time)=? AND status='completed'",
                (d,)
            ).fetchone()
            if row['cnt'] > 0:
                streak += 1
            else:
                if i == 0:
                    continue
                break
        return {
            'week_start': week_start,
            'dates': dates,
            'daily_focus': daily_focus,
            'total_focus_min': total_focus,
            'deep_focus_min': deep_focus,
            'interrupt_count': interrupts,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'completion_rate': int(completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            'streak_days': streak,
        }


def get_month_plan_stats(month_key: str) -> dict:
    """本月数据条统计"""
    _flush_pending_commits()
    with get_conn() as conn:
        total_row = conn.execute(
            "SELECT COALESCE(SUM(duration_min),0) as total FROM pomodoro_sessions "
            "WHERE strftime('%Y-%m', start_time)=? AND status='completed'",
            (month_key,)
        ).fetchone()
        deep_row = conn.execute(
            "SELECT COALESCE(SUM(duration_min),0) as total FROM pomodoro_sessions "
            "WHERE strftime('%Y-%m', start_time)=? AND status='completed' AND duration_min>=25 AND interrupted_count=0",
            (month_key,)
        ).fetchone()
        interrupt_row = conn.execute(
            "SELECT COALESCE(SUM(interrupted_count),0) as total FROM pomodoro_sessions "
            "WHERE strftime('%Y-%m', start_time)=?",
            (month_key,)
        ).fetchone()
        completed_row = conn.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as done FROM todos "
            "WHERE task_level='day' AND strftime('%Y-%m', assigned_date)=?",
            (month_key,)
        ).fetchone()
        total_tasks = completed_row['total'] or 0
        completed_tasks = completed_row['done'] or 0
        return {
            'month_key': month_key,
            'total_focus_min': total_row['total'] or 0,
            'deep_focus_min': deep_row['total'] or 0,
            'interrupt_count': interrupt_row['total'] or 0,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'completion_rate': int(completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
        }


def update_plan_meta(plan_type: str, plan_key: str, title: str = '', goal: str = '') -> bool:
    """更新周/月元数据"""
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO plan_meta (plan_type, plan_key, title, goal, updated_at) "
            "VALUES (?, ?, ?, ?, datetime('now','localtime')) "
            "ON CONFLICT(plan_type, plan_key) DO UPDATE SET title=excluded.title, goal=excluded.goal, updated_at=datetime('now','localtime')",
            (plan_type, plan_key, title, goal)
        )
        conn.commit()
        return True


def get_plan_meta(plan_type: str, plan_key: str) -> dict | None:
    """获取周/月元数据"""
    _flush_pending_commits()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM plan_meta WHERE plan_type=? AND plan_key=?",
            (plan_type, plan_key)
        ).fetchone()
        return dict(row) if row else None


# ── AI 自我认知分析缓存（累积理解系统） ──

def get_profile_analysis(analysis_type: str) -> dict | None:
    """获取指定类型的 AI 分析缓存"""
    _flush_pending_commits()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM profile_analysis_cache WHERE analysis_type=?",
            (analysis_type,)
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item['result_json'] = _parse_json(item.get('result_json', '{}'), {})
        return item


def get_all_profile_analyses() -> list[dict]:
    """获取所有 AI 分析缓存"""
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM profile_analysis_cache ORDER BY updated_at DESC"
        ).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item['result_json'] = _parse_json(item.get('result_json', '{}'), {})
        result.append(item)
    return result


def upsert_profile_analysis(analysis_type: str, result_json: dict, confidence: float = 0.0, data_points: int = 0) -> bool:
    """创建或更新 AI 分析缓存"""
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO profile_analysis_cache (analysis_type, result_json, confidence, data_points, created_at, updated_at)
            VALUES (?, ?, ?, ?, datetime('now','localtime'), datetime('now','localtime'))
            ON CONFLICT(analysis_type) DO UPDATE SET
                result_json=excluded.result_json,
                confidence=excluded.confidence,
                data_points=excluded.data_points,
                updated_at=datetime('now','localtime')
            """,
            (analysis_type, _serialize_json(result_json), confidence, data_points)
        )
        conn.commit()
        return True


