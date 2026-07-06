"""
ChallengeDaily Windows 版 — SQLite 数据库操作
企业级：连接池、自动重试、schema 版本管理
"""
import sqlite3
import time
import logging
from datetime import datetime, date, timedelta
from typing import Optional
from contextlib import contextmanager
from config import DB_PATH, CATEGORIES

logger = logging.getLogger(__name__)

# ── 数据库 Schema 版本 ──
SCHEMA_VERSION = 7


@contextmanager
def get_conn():
    """获取数据库连接（contextmanager，自动关闭）"""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


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
    raise sqlite3.OperationalError(f"Failed after {max_retries} retries")


def init_db():
    """初始化数据库表 + Schema 版本管理"""
    with get_conn() as conn:
        # 创建 schema 版本表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # 获取当前版本
        row = conn.execute(
            "SELECT value FROM schema_version WHERE key='version'"
        ).fetchone()
        current_version = int(row["value"]) if row else 0

        # V1: 基础表
        if current_version < 1:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS activities (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   TEXT NOT NULL,
                    screenshot  TEXT,
                    app_name    TEXT,
                    window_title TEXT,
                    category    TEXT,
                    summary     TEXT,
                    created_at  TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE TABLE IF NOT EXISTS app_usage (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name    TEXT NOT NULL,
                    window_title TEXT,
                    start_time  TEXT NOT NULL,
                    end_time    TEXT,
                    duration_sec INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_date TEXT NOT NULL UNIQUE,
                    content     TEXT NOT NULL,
                    created_at  TEXT DEFAULT (datetime('now','localtime'))
                );

                CREATE INDEX IF NOT EXISTS idx_activities_ts ON activities(timestamp);
                CREATE INDEX IF NOT EXISTS idx_activities_cat ON activities(category);
                CREATE INDEX IF NOT EXISTS idx_app_usage_app ON app_usage(app_name);
            """)

        # V2: 添加缺失索引 + app_usage 时间索引
        if current_version < 2:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date(timestamp))")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_app_usage_start ON app_usage(start_time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_date ON reports(report_date)")

        # V3: 添加 app_usage 唯一约束（app_name + start_time）
        if current_version < 3:
            # 创建新表带唯一约束
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS app_usage_v3 (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name    TEXT NOT NULL,
                    window_title TEXT,
                    start_time  TEXT NOT NULL,
                    end_time    TEXT,
                    duration_sec INTEGER DEFAULT 0,
                    UNIQUE(app_name, start_time)
                );
                INSERT OR IGNORE INTO app_usage_v3 (id, app_name, window_title, start_time, end_time, duration_sec)
                SELECT id, app_name, window_title, start_time, end_time, duration_sec FROM app_usage;
                DROP TABLE IF EXISTS app_usage;
                ALTER TABLE app_usage_v3 RENAME TO app_usage;
                CREATE INDEX IF NOT EXISTS idx_app_usage_app ON app_usage(app_name);
                CREATE INDEX IF NOT EXISTS idx_app_usage_start ON app_usage(start_time);
            """)

            # 添加 reports 表 template 列
            try:
                conn.execute("ALTER TABLE reports ADD COLUMN template TEXT DEFAULT 'standard'")
            except Exception:
                pass  # 列已存在

        # V4: 添加 activities.interval_sec 列，记录采集时的截图间隔
        if current_version < 4:
            try:
                conn.execute("ALTER TABLE activities ADD COLUMN interval_sec INTEGER DEFAULT 60")
            except Exception:
                pass  # 列已存在

        # V5: 添加 activities.ai_detail 列，记录 AI 详细分析
        if current_version < 5:
            try:
                conn.execute("ALTER TABLE activities ADD COLUMN ai_detail TEXT DEFAULT ''")
            except Exception:
                pass  # 列已存在

        # V6: 添加 app_category_rules 表，支持用户自定义应用分类规则和多标签
        if current_version < 6:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS app_category_rules (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name        TEXT NOT NULL UNIQUE,   -- 进程名（如 chrome.exe）
                    display_name    TEXT,                   -- 友好显示名
                    primary_category TEXT,                 -- 主分类（兜底）
                    tags            TEXT DEFAULT '[]',     -- JSON 数组，候选标签
                    window_rules    TEXT DEFAULT '{}',     -- JSON 对象：标题关键词 -> 分类
                    created_at      TEXT DEFAULT (datetime('now','localtime')),
                    updated_at      TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_app_rules_name ON app_category_rules(app_name);
            """)

        # V7: 添加 activities.windows_json 列，存储多窗口分析结果
        if current_version < 7:
            try:
                conn.execute("ALTER TABLE activities ADD COLUMN windows_json TEXT DEFAULT '[]'")
            except Exception:
                pass  # 列已存在

        # 更新版本号
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (key, value) VALUES ('version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()

    logger.info(f"Database initialized, schema version: {SCHEMA_VERSION}")


def insert_activity(timestamp: str, screenshot: str, app_name: str,
                    window_title: str, category: str, summary: str,
                    interval_sec: int = 60, ai_detail: str = "",
                    windows_json: str = "[]"):
    """写入一条活动记录"""
    with get_conn() as conn:
        _execute_with_retry(conn,
            "INSERT INTO activities (timestamp, screenshot, app_name, window_title, category, summary, interval_sec, ai_detail, windows_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (timestamp, screenshot, app_name, window_title, category, summary, interval_sec, ai_detail, windows_json),
        )
        conn.commit()


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


def get_activities(start_date: str, end_date: str):
    """按日期范围查询活动记录（最新在前）"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM activities WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC",
            (f"{start_date} 00:00:00", f"{end_date} 23:59:59"),
        ).fetchall()
    return [dict(r) for r in rows]


def get_recent_activities(limit: int = 5):
    """获取最近 N 条活动记录（最新在前），供 AI 分析时提供上下文"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT timestamp, app_name, window_title, category, summary "
            "FROM activities ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_daily_summary(start_date: str, end_date: str):
    """聚合统计"""
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
    """记录应用使用时长 — 基于 (app_name, start_time) 的真正 UPSERT"""
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
            "ON CONFLICT(app_name, start_time) DO UPDATE SET "
            "end_time=excluded.end_time, duration_sec=excluded.duration_sec, "
            "window_title=excluded.window_title",
            (app_name, window_title, start_time, end_time, duration),
        )
        conn.commit()


def get_app_usage(start_date: str, end_date: str):
    """查询应用使用时长统计"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT app_name, SUM(duration_sec) as total_sec FROM app_usage "
            "WHERE start_time >= ? AND start_time <= ? "
            "GROUP BY app_name ORDER BY total_sec DESC",
            (f"{start_date} 00:00:00", f"{end_date} 23:59:59"),
        ).fetchall()
    return [{"app_name": dict(r)["app_name"], "duration_min": round(dict(r)["total_sec"] / 60, 1)} for r in rows]


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


def cleanup_old_data(days: int):
    """清理超过保留天数的数据"""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with get_conn() as conn:
        conn.execute("DELETE FROM activities WHERE timestamp < ?", (f"{cutoff} 00:00:00",))
        conn.execute("DELETE FROM app_usage WHERE start_time < ?", (f"{cutoff} 00:00:00",))
        conn.execute("DELETE FROM reports WHERE report_date < ?", (cutoff,))
        conn.commit()


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
            "timestamp": r.get("timestamp", ""),
            "app_name": r.get("app_name", ""),
            "window_title": r.get("window_title", ""),
            "category": r.get("category", ""),
            "summary": r.get("summary", ""),
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
        writer.writerow(r)
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
