"""ChallengeDaily db layer — 活动采集、窗口记录与 App 使用原始写入。"""
from db import *  # noqa: F401,F403
from db import _execute_with_retry  # noqa: F401
_pending_commits = 0
_COMMIT_BATCH_SIZE = 1
_write_lock = threading.Lock()


# ── 批量提交优化 ──
# 避免每次 insert 都 fsync，改为延迟提交
# 参考 SQLite 性能指南：https://www.sqlite.org/withoutrowid.html
_pending_commits = 0
_COMMIT_BATCH_SIZE = 1  # activities 数据价值高，每条都立即提交
_write_lock = threading.Lock()  # 保护 _pending_commits 和写操作


def insert_activity(timestamp: str, screenshot: str, app_name: str,
                    window_title: str, category: str, summary: str,
                    interval_sec: int = 60, ai_detail: str = "",
                    windows_json: str = "[]") -> bool:
    """写入一条活动记录（批量提交优化，线程安全）

    Wave0-B20: 对 (timestamp, app_name, window_title) 幂等去重（V38 唯一表达式索引），
    事件钩子与主循环同秒并发采集时第二条被 IGNORE。返回是否真正插入。
    """
    global _pending_commits
    inserted = False
    with _write_lock:
        with get_conn() as conn:
            cursor = _execute_with_retry(conn,
                "INSERT OR IGNORE INTO activities (timestamp, screenshot, app_name, window_title, category, summary, interval_sec, ai_detail, windows_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (timestamp, screenshot, app_name, window_title, category, summary, interval_sec, ai_detail, windows_json),
            )
            inserted = cursor.rowcount > 0
            if inserted:
                _pending_commits += 1
                if _pending_commits >= _COMMIT_BATCH_SIZE:
                    conn.commit()
                    _pending_commits = 0
            else:
                logger.debug(f"重复采集被幂等忽略: {timestamp} {app_name}")
    # ── 数据飞轮：截图活动 → 自动 XP 奖励 ──
    # 异步发放，不影响截图写入性能；Wave0-B20: 仅真实插入才发 XP，避免重复采集刷经验
    if inserted:
        try:
            import growth_service
            duration_min = interval_sec / 60.0
            growth_service.award_exp_from_activity(category, duration_min)
        except Exception:
            pass  # XP 奖励失败不影响主流程
    return inserted


def merge_activity_interval(extra_sec: int, max_interval_sec: int = 300) -> bool:
    """Wave2-B42：相邻采样合并 — 把本次经过秒数并入最近一条活动。

    同一应用/窗口在短间隔（<30s）内再次采样时不再新开一行，而是累加
    上一条的 interval_sec（上限 max_interval_sec），避免 clamp 下限造成的多计。
    返回是否合并成功。
    """
    global _pending_commits
    if extra_sec <= 0:
        return False
    with _write_lock:
        with get_conn() as conn:
            cursor = _execute_with_retry(conn,
                "UPDATE activities SET interval_sec = MIN(?, interval_sec + ?) "
                "WHERE id = (SELECT id FROM activities ORDER BY id DESC LIMIT 1)",
                (max_interval_sec, int(extra_sec)),
            )
            merged = cursor.rowcount > 0
            if merged:
                _pending_commits += 1
                if _pending_commits >= _COMMIT_BATCH_SIZE:
                    conn.commit()
                    _pending_commits = 0
    return merged


def insert_manual_activity(timestamp: str, app_name: str, window_title: str,
                           category: str, summary: str, duration_min: int = 30):
    """手动补录一条活动记录（含生成 app_usage），返回新记录 id"""
    with get_conn() as conn:
        cursor = _execute_with_retry(conn,
            "INSERT INTO activities (timestamp, screenshot, app_name, window_title, category, summary) "
            "VALUES (?, '', ?, ?, ?, ?)",
            (timestamp, app_name, window_title, category, summary),
        )
        new_id = cursor.lastrowid
        # 同时写入 app_usage，让统计准确
        start_dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        end_dt = start_dt + timedelta(minutes=duration_min)
        end_time = end_dt.strftime("%Y-%m-%d %H:%M:%S")
        _execute_with_retry(conn,
            "INSERT INTO app_usage (app_name, window_title, start_time, end_time, duration_sec) "
            "VALUES (?, ?, ?, ?, ?)",
            (app_name, window_title, timestamp, end_time, duration_min * 60),
        )
        conn.commit()
        return new_id


def _flush_pending_commits():
    """刷新待提交的事务（读取数据前调用，确保数据一致）"""
    global _pending_commits
    with _write_lock:
        if _pending_commits > 0:
            with get_conn() as conn:
                conn.commit()
            _pending_commits = 0


def get_activities(start_date: str, end_date: str):
    """按日期范围查询活动记录（最新在前）"""
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM activities WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC",
            (f"{start_date} 00:00:00", f"{end_date} 23:59:59"),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_activities(limit: int = 5):
    """获取最近 N 条活动记录（最新在前），供 AI 分析时提供上下文"""
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT timestamp, app_name, window_title, category, summary, ai_detail, windows_json "
            "FROM activities ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_daily_summary(start_date: str, end_date: str):
    """聚合统计"""
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM activities "
            "WHERE timestamp >= ? AND timestamp <= ? "
            "GROUP BY category ORDER BY cnt DESC",
            (f"{start_date} 00:00:00", f"{end_date} 23:59:59"),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) as total FROM activities "
            "WHERE timestamp >= ? AND timestamp <= ?",
            (f"{start_date} 00:00:00", f"{end_date} 23:59:59"),
        ).fetchone()
        time_range = conn.execute(
            "SELECT MIN(timestamp) as first_ts, MAX(timestamp) as last_ts FROM activities "
            "WHERE timestamp >= ? AND timestamp <= ?",
            (f"{start_date} 00:00:00", f"{end_date} 23:59:59"),
        ).fetchone()

    categories = {dict(r)["category"]: dict(r)["cnt"] for r in rows}
    return {
        "total": dict(total)["total"] if total else 0,
        "categories": categories,
        "first_ts": dict(time_range)["first_ts"] if time_range else None,
        "last_ts": dict(time_range)["last_ts"] if time_range else None,
    }


def upsert_app_usage(app_name: str, window_title: str, start_time: str, end_time: str):
    """记录应用使用时长 — 基于 (app_name, window_title, start_time) 的 UPSERT（批量提交优化）

    V9 起唯一键含 window_title，支持同应用不同窗口标题分别记录（内容维度）。
    """
    global _pending_commits
    with _write_lock:
        with get_conn() as conn:
            fmt = "%Y-%m-%d %H:%M:%S"
            try:
                dt_start = datetime.strptime(start_time, fmt)
                dt_end = datetime.strptime(end_time, fmt)
                duration = max(0, int((dt_end - dt_start).total_seconds()))
            except Exception:
                duration = 0

            _execute_with_retry(conn,
                "INSERT INTO app_usage (app_name, window_title, start_time, end_time, duration_sec) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(app_name, window_title, start_time) DO UPDATE SET "
                "end_time=excluded.end_time, duration_sec=excluded.duration_sec",
                (app_name, window_title, start_time, end_time, duration),
            )
            _pending_commits += 1
            if _pending_commits >= _COMMIT_BATCH_SIZE:
                conn.commit()
                _pending_commits = 0


def upsert_app_usage_multi(windows: list, start_time: str, end_time: str):
    """多窗口时长分摊写入 — 按 area_ratio 把 duration 分给所有可见窗口。

    windows: [{"app_name", "window_title", "area_ratio"}]（已归一化或不归一化均可）
    start_time/end_time: "%Y-%m-%d %H:%M:%S" 字符串

    - 空列表：直接返回，不写入
    - 单窗口：等价于 upsert_app_usage（duration 全归该窗口）
    - 多窗口：duration × (area_ratio / sum(area_ratio)) 分给各窗口，向下取整
    - 同一 (app_name, window_title) 出现多次时合并为一条
    """
    if not windows:
        return
    global _pending_commits

    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        dt_start = datetime.strptime(start_time, fmt)
        dt_end = datetime.strptime(end_time, fmt)
        total_duration = max(0, int((dt_end - dt_start).total_seconds()))
    except Exception:
        total_duration = 0
    if total_duration <= 0:
        return

    # 归一化面积比例，合并相同 (app, title)
    total_area = sum(float(w.get("area_ratio", 0)) for w in windows) or 1.0
    merged: dict[tuple[str, str], int] = {}
    for w in windows:
        app_name = w.get("app_name", "Unknown")
        window_title = w.get("window_title", "") or ""
        ratio = float(w.get("area_ratio", 0)) / total_area
        share = int(total_duration * ratio)  # 向下取整
        key = (app_name, window_title)
        merged[key] = merged.get(key, 0) + share
    # 把取整损失补到面积最大的窗口，保证总和 = total_duration
    assigned = sum(merged.values())
    if assigned < total_duration and merged:
        biggest = max(merged, key=merged.get)
        merged[biggest] += (total_duration - assigned)

    with _write_lock:
        with get_conn() as conn:
            for (app_name, window_title), duration in merged.items():
                _execute_with_retry(conn,
                    "INSERT INTO app_usage (app_name, window_title, start_time, end_time, duration_sec) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(app_name, window_title, start_time) DO UPDATE SET "
                    "end_time=excluded.end_time, duration_sec=excluded.duration_sec",
                    (app_name, window_title, start_time, end_time, duration),
                )
                _pending_commits += 1
                if _pending_commits >= _COMMIT_BATCH_SIZE:
                    conn.commit()
                    _pending_commits = 0


def get_app_usage(start_date: str, end_date: str):
    """查询应用使用时长统计（按 app_name 聚合，与历史接口兼容）"""
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT app_name, SUM(duration_sec) as total_sec FROM app_usage "
            "WHERE start_time >= ? AND start_time <= ? "
            "GROUP BY app_name ORDER BY total_sec DESC",
            (f"{start_date} 00:00:00", f"{end_date} 23:59:59"),
        ).fetchall()
    return [{"app_name": dict(r)["app_name"], "duration_min": round(dict(r)["total_sec"] / 60, 1)} for r in rows]


def get_app_usage_by_content(start_date: str, end_date: str):
    """按应用 + 窗口标题细分查询使用时长。

    返回 [{"app_name", "window_title", "duration_min"}]，按 app_name 时长降序、同 app 内按 title 降序。
    用于在应用记录页展开查看同应用下不同内容（标签页/文档）的占用时间。
    """
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT app_name, window_title, SUM(duration_sec) as total_sec "
            "FROM app_usage "
            "WHERE start_time >= ? AND start_time <= ? "
            "GROUP BY app_name, window_title "
            "ORDER BY app_name, total_sec DESC",
            (f"{start_date} 00:00:00", f"{end_date} 23:59:59"),
        ).fetchall()
    return [
        {
            "app_name": dict(r)["app_name"],
            "window_title": dict(r)["window_title"] or "",
            "duration_min": round(dict(r)["total_sec"] / 60, 1),
        }
        for r in rows
    ]



