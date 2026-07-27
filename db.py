"""
ChallengeDaily Windows 版 — SQLite 数据库操作
企业级：线程局部连接、自动重试、schema 版本管理
优化：每线程独立连接避免 InterfaceError，WAL 只设一次
"""
import sqlite3
import threading
import time
import logging
import random
from datetime import datetime, date, timedelta
from typing import Optional
from contextlib import contextmanager
from config import DB_PATH, CATEGORIES
from db_migrations import init_db, SCHEMA_VERSION, DEFAULT_DATA_RETENTION_DAYS, _set_db_acl

logger = logging.getLogger(__name__)

# ── 线程局部连接（每线程独立 Connection，避免多线程共享导致 InterfaceError）──
_local = threading.local()
_conn_lock = threading.Lock()  # 仅保护 _init 等需要串行化的场景

# 标记 WAL 是否已在任何连接上设置（WAL 是数据库级属性，只需设一次）
_wal_initialized = False


def _get_thread_conn() -> sqlite3.Connection:
    """获取当前线程的局部连接（线程安全，每线程独立 Connection）"""
    global _wal_initialized
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        return conn
    # 为当前线程创建新连接
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-4096")  # P29: 4MB cache (from 2MB)
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")  # P23: 256MB memory-mapped I/O
    # WAL 模式只需设一次（是数据库级属性，非连接级）
    if not _wal_initialized:
        with _conn_lock:
            if not _wal_initialized:
                conn.execute("PRAGMA journal_mode=WAL")
                _wal_initialized = True
                logger.info("SQLite WAL 模式已启用 (synchronous=NORMAL)")
    else:
        conn.execute("PRAGMA journal_mode=WAL")  # 确保当前连接也在 WAL 模式
    logger.debug(f"SQLite 线程连接已建立: {threading.current_thread().name}")
    _local.conn = conn
    return conn


@contextmanager
def get_conn():
    """获取数据库连接（contextmanager，使用线程局部连接，不关闭）

    异常时重置当前线程的连接，避免损坏后影响后续操作。
    """
    conn = _get_thread_conn()
    try:
        yield conn
    except sqlite3.DatabaseError as e:
        # 连接可能损坏，重置当前线程连接以便下次重建
        logger.error(f"数据库连接异常，将重建: {e}")
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None
        raise


# T7: 归档数据库路径（与主库同目录下的 archives 子目录）
_ARCHIVE_DB_PATH = None

def _get_archive_db_path():
    """获取归档数据库路径（惰性初始化）"""
    global _ARCHIVE_DB_PATH
    if _ARCHIVE_DB_PATH is not None:
        return _ARCHIVE_DB_PATH
    from config import DATA_DIR
    archive_dir = DATA_DIR / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _ARCHIVE_DB_PATH = archive_dir / "xiaohei-archive.db"
    return _ARCHIVE_DB_PATH


@contextmanager
def get_conn_with_archive():
    """获取带归档库 ATTACH 的连接（T7: 跨库查询 live + archived activities）

    用法：
        with db.get_conn_with_archive() as conn:
            rows = conn.execute("SELECT * FROM main.activities UNION ALL SELECT * FROM archive.activities")

    退出时自动 DETACH 归档库，避免连接泄漏。
    """
    conn = _get_thread_conn()
    archive_path = _get_archive_db_path()
    attached = False
    try:
        # 确保 archive 库有 activities 表
        conn.execute(f"ATTACH DATABASE ? AS archive", (str(archive_path),))
        attached = True
        conn.execute("""
            CREATE TABLE IF NOT EXISTS archive.activities (
                id          INTEGER PRIMARY KEY,
                timestamp   TEXT NOT NULL,
                screenshot  TEXT,
                app_name    TEXT,
                window_title TEXT,
                category    TEXT,
                summary     TEXT,
                interval_sec INTEGER DEFAULT 60,
                ai_detail   TEXT DEFAULT '',
                windows_json TEXT DEFAULT '[]',
                created_at  TEXT,
                original_id INTEGER,
                archived_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS archive.idx_archive_ts ON activities(timestamp)")
        yield conn
    except sqlite3.DatabaseError as e:
        logger.error(f"归档连接异常: {e}")
        try:
            if attached:
                conn.execute("DETACH DATABASE archive")
        except Exception:
            pass
        raise
    finally:
        if attached:
            try:
                conn.execute("DETACH DATABASE archive")
            except Exception:
                pass


def _execute_with_retry(conn, sql, params=(), max_retries=3):
    """带重试的 SQL 执行（处理 SQLITE_BUSY 锁冲突）"""
    for attempt in range(max_retries):
        try:
            return conn.execute(sql, params)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                wait = 0.1 * (2 ** attempt)
                logger.warning(f"SQLite busy, retry {attempt+1}/{max_retries} after {wait:.1f}s")
                time.sleep(wait)
                continue
            raise
        except sqlite3.IntegrityError as e:
            logger.error(f"SQLite IntegrityError: {e}, SQL: {sql[:100]}")
            raise
    raise sqlite3.OperationalError(f"Failed after {max_retries} retries")





# ── 批量提交优化 ──
# 避免每次 insert 都 fsync，改为延迟提交
# 参考 SQLite 性能指南：https://www.sqlite.org/withoutrowid.html
_pending_commits = 0
_COMMIT_BATCH_SIZE = 1  # activities 数据价值高，每条都立即提交
_write_lock = threading.Lock()  # 保护 _pending_commits 和写操作


def insert_activity(timestamp: str, screenshot: str, app_name: str,
                    window_title: str, category: str, summary: str,
                    interval_sec: int = 60, ai_detail: str = "",
                    windows_json: str = "[]"):
    """写入一条活动记录（批量提交优化，线程安全）"""
    global _pending_commits
    with _write_lock:
        with get_conn() as conn:
            _execute_with_retry(conn,
                "INSERT INTO activities (timestamp, screenshot, app_name, window_title, category, summary, interval_sec, ai_detail, windows_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (timestamp, screenshot, app_name, window_title, category, summary, interval_sec, ai_detail, windows_json),
            )
            _pending_commits += 1
            if _pending_commits >= _COMMIT_BATCH_SIZE:
                conn.commit()
                _pending_commits = 0


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


def _sanitize_csv_cell(val):
    """防止 CSV 公式注入：以 = + - @ 开头的单元格加单引号前缀"""
    s = str(val) if val is not None else ""
    if s and s[0] in ('=', '+', '-', '@'):
        return "'" + s
    return s


def export_activities_csv(start_date: str, end_date: str) -> str:
    """导出活动记录为 CSV 格式"""
    import csv
    import io
    rows = get_activities(start_date, end_date)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["timestamp", "app_name", "window_title", "category", "summary"])
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "timestamp": _sanitize_csv_cell(r.get("timestamp", "")),
            "app_name": _sanitize_csv_cell(r.get("app_name", "")),
            "window_title": _sanitize_csv_cell(r.get("window_title", "")),
            "category": _sanitize_csv_cell(r.get("category", "")),
            "summary": _sanitize_csv_cell(r.get("summary", "")),
        })
    return output.getvalue()


def export_app_usage_csv(start_date: str, end_date: str) -> str:
    """导出应用使用时长为 CSV 格式"""
    import csv
    import io
    rows = get_app_usage(start_date, end_date)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["app_name", "duration_min"])
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "app_name": _sanitize_csv_cell(r.get("app_name", "")),
            "duration_min": _sanitize_csv_cell(r.get("duration_min", "")),
        })
    return output.getvalue()


# ── 应用分类规则 ──

def _serialize_json(value) -> str:
    """将 Python 对象序列化为 JSON 字符串"""
    import json
    return json.dumps(value, ensure_ascii=False)


def _parse_json(text: str, default):
    """安全解析 JSON 字符串"""
    import json
    try:
        return json.loads(text) if text else default
    except Exception:
        return default


def get_app_category_rules() -> list[dict]:
    """获取所有应用分类规则"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM app_category_rules ORDER BY updated_at DESC"
        ).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item["tags"] = _parse_json(item.get("tags"), [])
        item["window_rules"] = _parse_json(item.get("window_rules"), {})
        result.append(item)
    return result


def get_app_category_rule(app_name: str) -> dict | None:
    """获取单个应用的分类规则"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM app_category_rules WHERE app_name = ?",
            (app_name,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["tags"] = _parse_json(item.get("tags"), [])
    item["window_rules"] = _parse_json(item.get("window_rules"), {})
    return item


def upsert_app_category_rule(
    app_name: str,
    primary_category: str = "",
    tags: list[str] | None = None,
    window_rules: dict | None = None,
    display_name: str = "",
) -> dict:
    """创建或更新应用分类规则"""
    tags = tags or []
    window_rules = window_rules or {}
    # 确保主标签在候选标签里
    if primary_category and primary_category not in tags:
        tags = [primary_category] + tags
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO app_category_rules
                (app_name, display_name, primary_category, tags, window_rules, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(app_name) DO UPDATE SET
                display_name=excluded.display_name,
                primary_category=excluded.primary_category,
                tags=excluded.tags,
                window_rules=excluded.window_rules,
                updated_at=excluded.updated_at
            """,
            (
                app_name,
                display_name,
                primary_category,
                _serialize_json(tags),
                _serialize_json(window_rules),
            ),
        )
        conn.commit()
    return get_app_category_rule(app_name)


def delete_app_category_rule(app_name: str) -> bool:
    """删除应用分类规则"""
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM app_category_rules WHERE app_name = ?",
            (app_name,),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_known_apps() -> list[dict]:
    """获取所有出现过应用名（来自 app_usage）及其规则"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT app_name FROM app_usage ORDER BY app_name"
        ).fetchall()
    rules = {r["app_name"]: r for r in get_app_category_rules()}
    result = []
    for r in rows:
        name = r["app_name"]
        result.append({
            "app_name": name,
            "rule": rules.get(name),
        })
    return result


# ── 番茄钟 ──
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

