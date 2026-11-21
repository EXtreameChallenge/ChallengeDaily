"""ChallengeDaily db layer — 报告存储、清理、小时分布与多日统计。"""
from db import *  # noqa: F401,F403
from db import _execute_with_retry  # noqa: F401

def save_report(report_date: str, content: str):
    """保存日报（覆盖式）"""
    with get_conn() as conn:
        _execute_with_retry(conn,
            "INSERT INTO reports (report_date, content) VALUES (?, ?) "
            "ON CONFLICT(report_date) DO UPDATE SET content=excluded.content",
            (report_date, content),
        )
        conn.commit()


def get_reports(start_date: str, end_date: str):
    """查询已生成的报告列表"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reports WHERE report_date >= ? AND report_date <= ? ORDER BY report_date DESC",
            (start_date, end_date),
        ).fetchall()
    return [dict(r) for r in rows]


def search_reports(query: str, limit: int = 20) -> list:
    """P8-1：FTS5 全文检索报告内容。

    Args:
        query: 检索关键词（自动加引号避免 FTS5 特殊语法注入）
        limit: 最多返回条数

    Returns:
        [{id, report_date, content, created_at, snippet}] 每条带高亮摘要
        若 FTS5 不可用或查询异常，回退到 LIKE 模糊匹配
    """
    if not query or not query.strip():
        return []
    q = query.strip()
    # 转义双引号并用引号包裹，规避 FTS5 语法注入
    safe_q = '"' + q.replace('"', '""') + '"'
    try:
        with get_conn() as conn:
            # 先尝试 FTS5（外部内容表）
            try:
                rows = conn.execute(
                    "SELECT r.id, r.report_date, r.content, r.created_at, "
                    "       snippet(reports_fts, 1, '【', '】', '...', 24) AS snippet "
                    "FROM reports_fts f JOIN reports r ON r.id = f.rowid "
                    "WHERE reports_fts MATCH ? "
                    "ORDER BY r.report_date DESC LIMIT ?",
                    (safe_q, limit),
                ).fetchall()
                if rows:
                    return [dict(r) for r in rows]
                # FTS5 查询成功但无结果，确认是真空结果而非回退
                # 这里若 FTS5 启用则直接返回空
                return []
            except Exception:
                # FTS5 未启用，回退到 LIKE
                logger.warning("FTS5 不可用，回退到 LIKE 模糊匹配")
                like = f"%{q}%"
                rows = conn.execute(
                    "SELECT id, report_date, content, created_at, "
                    "       substr(content, 1, 200) AS snippet "
                    "FROM reports WHERE content LIKE ? "
                    "ORDER BY report_date DESC LIMIT ?",
                    (like, limit),
                ).fetchall()
                return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"search_reports 失败: {e}", exc_info=True)
        return []


def cleanup_old_data(days: int):
    """清理超过保留天数的数据（显式事务保证多表删除原子性）"""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM activities WHERE timestamp < ?", (f"{cutoff} 00:00:00",))
        conn.execute("DELETE FROM app_usage WHERE start_time < ?", (f"{cutoff} 00:00:00",))
        conn.execute("DELETE FROM reports WHERE report_date < ?", (cutoff,))
        # 扩展清理范围：番茄钟、对话历史、习惯日志、每日画像、用户纠错
        conn.execute("DELETE FROM pomodoro_sessions WHERE start_time < ?", (f"{cutoff} 00:00:00",))
        conn.execute("DELETE FROM chat_history WHERE created_at < ?", (f"{cutoff} 00:00:00",))
        conn.execute("DELETE FROM habit_logs WHERE log_date < ?", (cutoff,))
        conn.execute("DELETE FROM daily_profiles WHERE date < ?", (cutoff,))
        conn.execute("DELETE FROM user_corrections WHERE created_at < ?", (f"{cutoff} 00:00:00",))
        # activities_deleted 表可能不存在，加 try/except 保护
        try:
            conn.execute("DELETE FROM activities_deleted WHERE deleted_at < ?", (f"{cutoff} 00:00:00",))
        except sqlite3.OperationalError as e:
            if "no such table" in str(e).lower():
                logger.debug("cleanup_old_data: activities_deleted 表不存在，跳过")
            else:
                raise
        # B41: timestamp 非法的历史垃圾行（BLOB/非日期文本，来自旧版错误写入与恢复脚本残留）
        # 永远匹配不到上面的文本比较，单独清除，防止永久驻留
        garbage = conn.execute(
            "DELETE FROM activities WHERE typeof(timestamp) != 'text' "
            "OR timestamp NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'"
        ).rowcount
        if garbage:
            logger.info(f"cleanup_old_data: 清除 timestamp 非法垃圾行 {garbage} 条")
        conn.commit()


def get_retention_days() -> int:
    """从 settings 表读取保留天数，默认 90"""
    try:
        with get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='data_retention_days'").fetchone()
            return int(row[0]) if row else DEFAULT_DATA_RETENTION_DAYS
    except Exception:
        return DEFAULT_DATA_RETENTION_DAYS


def auto_cleanup_old_data():
    """自动清理过期数据（供定时任务调用）"""
    days = get_retention_days()
    cleanup_old_data(days)
    logger.info(f"自动清理完成，保留 {days} 天数据")


def get_hourly_activity(target_date: str):
    """获取指定日期按小时聚合的活动数据"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS hour, "
            "       COUNT(*) as cnt, "
            "       GROUP_CONCAT(DISTINCT category) AS categories "
            "FROM activities "
            "WHERE date(timestamp) = ? "
            "GROUP BY hour ORDER BY hour",
            (target_date,),
        ).fetchall()

    hour_map = {r["hour"]: {"count": r["cnt"], "categories": (r["categories"] or "").split(",")} for r in rows}
    return [
        {
            "hour": h,
            "count": hour_map[h]["count"] if h in hour_map else 0,
            "categories": hour_map[h]["categories"] if h in hour_map else [],
        }
        for h in range(24)
    ]


def get_multi_day_stats(days: int = 7):
    """获取最近 N 天的每日统计摘要（单查询优化）"""
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date(timestamp) AS d, "
            "       COUNT(*) AS cnt, "
            "       COUNT(DISTINCT category) AS cat_count "
            "FROM activities "
            "WHERE date(timestamp) >= ? "
            "GROUP BY date(timestamp)",
            (cutoff,),
        ).fetchall()

    # 把有数据的天做成 map
    row_map = {r["d"]: {"count": r["cnt"], "category_count": r["cat_count"]} for r in rows}

    # 填充所有天（包括无数据的）
    results = []
    for i in range(days - 1, -1, -1):
        target = (date.today() - timedelta(days=i)).isoformat()
        info = row_map.get(target, {"count": 0, "category_count": 0})
        results.append({
            "date": target,
            "count": info["count"],
            "category_count": info["category_count"],
        })
    return results



