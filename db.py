"""
ChallengeDaily Windows 版 — SQLite 数据库操作
企业级：持久连接、自动重试、schema 版本管理
优化：单持久连接避免频繁 connect/close，WAL 只设一次
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

logger = logging.getLogger(__name__)

# ── 数据库 Schema 版本 ──
SCHEMA_VERSION = 20

# ── 持久连接（避免每分钟 5-7 次 connect/close）──
_persistent_conn: Optional[sqlite3.Connection] = None
_conn_lock = threading.Lock()


def _get_persistent_conn() -> sqlite3.Connection:
    """获取持久连接（线程安全，WAL 只设一次）"""
    global _persistent_conn
    with _conn_lock:
        if _persistent_conn is None:
            _persistent_conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
            _persistent_conn.row_factory = sqlite3.Row
            # WAL 和 busy_timeout 只设一次
            _persistent_conn.execute("PRAGMA journal_mode=WAL")
            _persistent_conn.execute("PRAGMA busy_timeout=5000")
            _persistent_conn.execute("PRAGMA foreign_keys=ON")
            # 性能优化：减少 fsync 频率（WAL 模式下 NORMAL 足够安全）
            # 参考 SQLite 官方建议：https://www.sqlite.org/pragma.html#pragma_synchronous
            _persistent_conn.execute("PRAGMA synchronous=NORMAL")
            # 限制内存缓存大小为 2MB（负值=KB），避免长期运行内存增长
            _persistent_conn.execute("PRAGMA cache_size=-2048")
            # 临时表和中间结果存内存，避免磁盘 I/O
            _persistent_conn.execute("PRAGMA temp_store=MEMORY")
            logger.info("SQLite 持久连接已建立 (WAL模式, synchronous=NORMAL)")
        return _persistent_conn


@contextmanager
def get_conn():
    """获取数据库连接（contextmanager，使用持久连接不关闭）"""
    conn = _get_persistent_conn()
    yield conn


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
            except sqlite3.OperationalError:
                pass  # 列已存在

        # V4: 添加 activities.interval_sec 列，记录采集时的截图间隔
        if current_version < 4:
            try:
                conn.execute("ALTER TABLE activities ADD COLUMN interval_sec INTEGER DEFAULT 60")
            except sqlite3.OperationalError:
                pass  # 列已存在

        # V5: 添加 activities.ai_detail 列，记录 AI 详细分析
        if current_version < 5:
            try:
                conn.execute("ALTER TABLE activities ADD COLUMN ai_detail TEXT DEFAULT ''")
            except sqlite3.OperationalError:
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
            except sqlite3.OperationalError:
                pass  # 列已存在

        # V8: 用户画像 + 每日画像表
        if current_version < 8:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS daily_profiles (
                    date           TEXT PRIMARY KEY,
                    hourly_digest  TEXT DEFAULT '[]',
                    daily_summary  TEXT DEFAULT '',
                    work_patterns  TEXT DEFAULT '[]',
                    top_apps       TEXT DEFAULT '[]',
                    focus_hours    TEXT DEFAULT '[]',
                    productivity   TEXT DEFAULT '',
                    key_insights   TEXT DEFAULT '[]',
                    peak_hours     TEXT DEFAULT '',
                    work_rhythm    TEXT DEFAULT '',
                    content_types  TEXT DEFAULT '[]',
                    behavior_tags  TEXT DEFAULT '[]',
                    efficiency_pattern TEXT DEFAULT '',
                    generated_at   TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE TABLE IF NOT EXISTS user_profile (
                    id             INTEGER PRIMARY KEY CHECK (id = 1),
                    role_desc      TEXT DEFAULT '',
                    work_style     TEXT DEFAULT '',
                    habits         TEXT DEFAULT '{}',
                    app_overrides  TEXT DEFAULT '{}',
                    custom_rules   TEXT DEFAULT '[]',
                    peak_hours     TEXT DEFAULT '',
                    work_rhythm    TEXT DEFAULT '',
                    content_types  TEXT DEFAULT '[]',
                    behavior_tags  TEXT DEFAULT '[]',
                    efficiency_pattern TEXT DEFAULT '',
                    updated_at     TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE TABLE IF NOT EXISTS user_corrections (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name       TEXT NOT NULL,
                    correct_category TEXT DEFAULT '',
                    correct_desc   TEXT DEFAULT '',
                    notes          TEXT DEFAULT '',
                    created_at     TEXT DEFAULT (datetime('now','localtime'))
                );
            """)

        # V9: 唯一键改为 (app_name, window_title, start_time) 以支持多窗口分摊和内容维度统计
        # 旧约束 UNIQUE(app_name, start_time) 会阻止同应用不同窗口共存
        if current_version < 9:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS app_usage_v9 (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    app_name    TEXT NOT NULL,
                    window_title TEXT,
                    start_time  TEXT NOT NULL,
                    end_time    TEXT,
                    duration_sec INTEGER DEFAULT 0,
                    UNIQUE(app_name, window_title, start_time)
                );
                -- 同 (app, title, start) 多条时取 duration 最大者，避免迁移时唯一冲突
                INSERT OR IGNORE INTO app_usage_v9 (app_name, window_title, start_time, end_time, duration_sec)
                SELECT app_name, window_title, start_time, end_time, MAX(duration_sec)
                FROM app_usage
                GROUP BY app_name, window_title, start_time;
                DROP TABLE IF EXISTS app_usage;
                ALTER TABLE app_usage_v9 RENAME TO app_usage;
                CREATE INDEX IF NOT EXISTS idx_app_usage_app ON app_usage(app_name);
                CREATE INDEX IF NOT EXISTS idx_app_usage_start ON app_usage(start_time);
                CREATE INDEX IF NOT EXISTS idx_app_usage_title ON app_usage(app_name, window_title);
            """)

        # V10: 扩展 user_profile 表，支持用户画像蒸馏
        if current_version < 10:
            for col, deflt in [
                ("peak_hours", "TEXT DEFAULT ''"),
                ("work_rhythm", "TEXT DEFAULT ''"),
                ("content_types", "TEXT DEFAULT '[]'"),
                ("behavior_tags", "TEXT DEFAULT '[]'"),
                ("efficiency_pattern", "TEXT DEFAULT ''"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE user_profile ADD COLUMN {col} {deflt}")
                except sqlite3.OperationalError:
                    pass  # 列已存在

        # V11: 扩展 daily_profiles 表，支持日画像存储 AI 新增的蒸馏字段
        if current_version < 11:
            for col, deflt in [
                ("peak_hours", "TEXT DEFAULT ''"),
                ("work_rhythm", "TEXT DEFAULT ''"),
                ("content_types", "TEXT DEFAULT '[]'"),
                ("behavior_tags", "TEXT DEFAULT '[]'"),
                ("efficiency_pattern", "TEXT DEFAULT ''"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE daily_profiles ADD COLUMN {col} {deflt}")
                except sqlite3.OperationalError:
                    pass  # 列已存在

        # V12: 番茄钟专注记录
        if current_version < 12:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS pomodoro_sessions (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time       TEXT NOT NULL,
                    end_time         TEXT,
                    duration_min     INTEGER NOT NULL DEFAULT 25,
                    task             TEXT DEFAULT '',
                    category          TEXT DEFAULT '开发',
                    status           TEXT DEFAULT 'completed',
                    interrupted_count INTEGER DEFAULT 0,
                    source           TEXT DEFAULT 'manual',
                    created_at       TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_pomodoro_start ON pomodoro_sessions(start_time);
                CREATE INDEX IF NOT EXISTS idx_pomodoro_status ON pomodoro_sessions(status);
            """)

        # V13: 待办清单（融入GoalDay打卡清单自动进度）
        if current_version < 13:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS todos (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    title           TEXT NOT NULL,
                    category        TEXT DEFAULT '开发',
                    mode            TEXT DEFAULT 'timer',
                    target_min      INTEGER DEFAULT 25,
                    repeat_type     TEXT DEFAULT 'none',
                    repeat_days     TEXT DEFAULT '',
                    due_date        TEXT,
                    priority        INTEGER DEFAULT 2,
                    status          TEXT DEFAULT 'pending',
                    progress_min    INTEGER DEFAULT 0,
                    pomodoro_count  INTEGER DEFAULT 0,
                    sort_order      INTEGER DEFAULT 0,
                    created_at      TEXT DEFAULT (datetime('now','localtime')),
                    updated_at      TEXT DEFAULT (datetime('now','localtime')),
                    completed_at    TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
                CREATE INDEX IF NOT EXISTS idx_todos_due ON todos(due_date);
            """)

        # V14: 每日日记（融入GoalDay一日一页+心情+翻页）
        if current_version < 14:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS diaries (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    diary_date  TEXT UNIQUE NOT NULL,
                    mood        TEXT DEFAULT '',
                    weather     TEXT DEFAULT '',
                    content     TEXT DEFAULT '',
                    tags         TEXT DEFAULT '',
                    highlights  TEXT DEFAULT '',
                    gratitude   TEXT DEFAULT '',
                    created_at  TEXT DEFAULT (datetime('now','localtime')),
                    updated_at  TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_diary_date ON diaries(diary_date);
            """)

        # V15: 成就系统
        if current_version < 15:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS achievements (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    code        TEXT UNIQUE NOT NULL,
                    name        TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    icon        TEXT DEFAULT '🏆',
                    unlocked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS countdowns (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    color       TEXT DEFAULT '#7B68EE',
                    created_at  TEXT DEFAULT (datetime('now','localtime'))
                );
            """)

        # V16: AI对话历史
        if current_version < 16:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now','localtime'))
                );
            """)

        # V17: 习惯目标配置
        if current_version < 17:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS habits (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    name        TEXT NOT NULL,
                    target_count INTEGER DEFAULT 1,
                    period      TEXT DEFAULT 'daily',
                    color       TEXT DEFAULT '#7B68EE',
                    sort_order  INTEGER DEFAULT 0,
                    created_at  TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE TABLE IF NOT EXISTS habit_logs (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id    INTEGER NOT NULL,
                    log_date    TEXT NOT NULL,
                    count       INTEGER DEFAULT 1,
                    created_at  TEXT DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (habit_id) REFERENCES habits(id)
                );
                CREATE INDEX IF NOT EXISTS idx_habit_logs ON habit_logs(habit_id, log_date);
            """)

        # V18: 扩展 todos 表，增加层级与分配字段（周计划月/周/日三级层级）
        if current_version < 18:
            # SQLite ALTER TABLE ADD COLUMN 不支持 IF NOT EXISTS，需检查列存在性
            existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(todos)").fetchall()}
            new_cols = {
                'parent_id': 'INTEGER',                                  # 父任务ID（周→月，日→周）
                'task_level': "TEXT DEFAULT 'day'",                       # month | week | day
                'assigned_date': 'TEXT',                                  # 分配到哪天 YYYY-MM-DD（day级）
                'week_start': 'TEXT',                                      # 所属周起始 YYYY-MM-DD（week级，固定周一）
                'month_key': 'TEXT',                                       # 所属月份 YYYY-MM（month级）
                'color': "TEXT DEFAULT ''",                                # 自定义颜色
            }
            for col, typedef in new_cols.items():
                if col not in existing_cols:
                    conn.execute(f"ALTER TABLE todos ADD COLUMN {col} {typedef}")
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_todos_parent ON todos(parent_id);
                CREATE INDEX IF NOT EXISTS idx_todos_assigned ON todos(assigned_date);
                CREATE INDEX IF NOT EXISTS idx_todos_week ON todos(week_start);
                CREATE INDEX IF NOT EXISTS idx_todos_month ON todos(month_key);
                CREATE INDEX IF NOT EXISTS idx_todos_level ON todos(task_level);
            """)

        # V19: 番茄钟关联待办（修复历史脱钩）
        if current_version < 19:
            existing_pomodoro_cols = {row[1] for row in conn.execute("PRAGMA table_info(pomodoro_sessions)").fetchall()}
            if 'todo_id' not in existing_pomodoro_cols:
                conn.execute("ALTER TABLE pomodoro_sessions ADD COLUMN todo_id INTEGER")
            conn.executescript("CREATE INDEX IF NOT EXISTS idx_pomodoro_todo ON pomodoro_sessions(todo_id);")
            # 删除级联触发器：父任务删除时子任务 parent_id 置空
            conn.executescript("""
                CREATE TRIGGER IF NOT EXISTS todos_delete_cascade
                AFTER DELETE ON todos
                BEGIN
                    UPDATE todos SET parent_id = NULL WHERE parent_id = OLD.id;
                    UPDATE pomodoro_sessions SET todo_id = NULL WHERE todo_id = OLD.id;
                END;
            """)

        # V20: 周计划元数据表（周/月目标描述）
        if current_version < 20:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS plan_meta (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_type       TEXT NOT NULL,
                    plan_key        TEXT NOT NULL,
                    title           TEXT DEFAULT '',
                    goal            TEXT DEFAULT '',
                    created_at      TEXT DEFAULT (datetime('now','localtime')),
                    updated_at      TEXT DEFAULT (datetime('now','localtime')),
                    UNIQUE(plan_type, plan_key)
                );
            """)

        # 更新版本号
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (key, value) VALUES ('version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()

    logger.info(f"Database initialized, schema version: {SCHEMA_VERSION}")


# ── 批量提交优化 ──
# 避免每次 insert 都 fsync，改为延迟提交
# 参考 SQLite 性能指南：https://www.sqlite.org/withoutrowid.html
_pending_commits = 0
_COMMIT_BATCH_SIZE = 5  # 攒够 5 条或下次读取时提交
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


# ── 番茄钟 ──
def insert_pomodoro_session(start_time, end_time, duration_min, task="", category="开发", status="completed", interrupted_count=0, source="manual"):
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO pomodoro_sessions (start_time, end_time, duration_min, task, category, status, interrupted_count, source) VALUES (?,?,?,?,?,?,?,?)",
            (start_time, end_time, duration_min, task, category, status, interrupted_count, source)
        )
        conn.commit()
        cur = conn.execute("SELECT last_insert_rowid()")
        return cur.fetchone()[0]

def update_pomodoro_session(session_id, **kwargs):
    _flush_pending_commits()
    with get_conn() as conn:
        sets = ", ".join([f"{k}=?" for k in kwargs])
        vals = list(kwargs.values()) + [session_id]
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
        if today not in dates and yesterday not in dates:
            return 0
        streak = 0
        check_date = today if today in dates else yesterday
        while check_date in dates:
            streak += 1
            check_date = (datetime.strptime(check_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        return streak

def get_pomodoro_today_count():
    _flush_pending_commits()
    with get_conn() as conn:
        today = date.today().isoformat()
        row = conn.execute("SELECT COUNT(*) as cnt, COALESCE(SUM(duration_min),0) as total_min FROM pomodoro_sessions WHERE status='completed' AND date(start_time)=?", (today,)).fetchone()
        return {"count": row["cnt"], "total_min": row["total_min"]}

# ── 待办清单 ──
def insert_todo(title, category="开发", mode="timer", target_min=25, repeat_type="none", repeat_days="", due_date=None, priority=2,
                task_level="day", parent_id=None, assigned_date=None, week_start=None, month_key=None):
    _flush_pending_commits()
    with get_conn() as conn:
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM todos").fetchone()[0]
        # 修复：原 SQL 9 列只有 8 个 ? 占位符，补齐为 9 个
        # 扩展：支持 task_level/parent_id/assigned_date/week_start/month_key
        conn.execute(
            "INSERT INTO todos (title, category, mode, target_min, repeat_type, repeat_days, due_date, priority, sort_order, "
            "task_level, parent_id, assigned_date, week_start, month_key) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (title, category, mode, target_min, repeat_type, repeat_days, due_date, priority, max_order+1,
             task_level, parent_id, assigned_date, week_start, month_key)
        )
        conn.commit()
        cur = conn.execute("SELECT last_insert_rowid()")
        return cur.fetchone()[0]

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
    _flush_pending_commits()
    with get_conn() as conn:
        sets = ", ".join([f"{k}=?" for k in kwargs if k != "id"])
        vals = [v for k, v in kwargs.items() if k != "id"]
        vals.append(todo_id)
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
    _flush_pending_commits()
    with get_conn() as conn:
        row = conn.execute("SELECT progress_min, pomodoro_count, target_min, mode FROM todos WHERE id=?", (todo_id,)).fetchone()
        if not row:
            return False
        new_progress = row["progress_min"] + minutes
        new_count = row["pomodoro_count"] + 1
        # 如果是 goal 模式且达到目标，自动标记完成
        if row["mode"] == "goal" and new_progress >= row["target_min"]:
            conn.execute("UPDATE todos SET progress_min=?, pomodoro_count=?, status='completed', completed_at=datetime('now','localtime'), updated_at=datetime('now','localtime') WHERE id=?", (new_progress, new_count, todo_id))
        else:
            conn.execute("UPDATE todos SET progress_min=?, pomodoro_count=?, updated_at=datetime('now','localtime') WHERE id=?", (new_progress, new_count, todo_id))
        conn.commit()
        return True

# ── 每日日记 ──
def upsert_diary(diary_date, mood="", weather="", content="", tags="", highlights="", gratitude=""):
    _flush_pending_commits()
    with get_conn() as conn:
        existing = conn.execute("SELECT id FROM diaries WHERE diary_date=?", (diary_date,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE diaries SET mood=?, weather=?, content=?, tags=?, highlights=?, gratitude=?, updated_at=datetime('now','localtime') WHERE diary_date=?",
                (mood, weather, content, tags, highlights, gratitude, diary_date)
            )
        else:
            conn.execute(
                "INSERT INTO diaries (diary_date, mood, weather, content, tags, highlights, gratitude) VALUES (?,?,?,?,?,?,?)",
                (diary_date, mood, weather, content, tags, highlights, gratitude)
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
    """检查并解锁成就"""
    unlocked = []
    # 获取番茄钟统计
    today = get_pomodoro_today_count()
    streak = get_pomodoro_streak()
    stats = get_pomodoro_stats("month")
    total_count = sum(s["cnt"] for s in stats) if stats else 0
    total_min = sum(s["total_min"] for s in stats) if stats else 0

    checks = [
        ("first_pomodoro", "初心者", "完成第一个番茄钟", "🌱", today["count"] >= 1),
        ("pomodoro_100", "百斩", "累计完成100个番茄钟", "💯", total_count >= 100),
        ("pomodoro_1000", "千时", "累计专注1000小时", "⏰", total_min >= 60000),
        ("streak_7", "连续7天", "连续7天完成专注", "🔥", streak >= 7),
        ("streak_30", "坚持不懈", "连续30天完成专注", "💎", streak >= 30),
    ]
    for code, name, desc, icon, condition in checks:
        if condition and unlock_achievement(code, name, desc, icon):
            unlocked.append({"code": code, "name": name, "icon": icon})
    return unlocked

# ── 倒数日 ──
def insert_countdown(title, target_date, color="#7B68EE"):
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute("INSERT INTO countdowns (title, target_date, color) VALUES (?,?,?)", (title, target_date, color))
        conn.commit()
        cur = conn.execute("SELECT last_insert_rowid()")
        return cur.fetchone()[0]

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
        conn.execute("INSERT INTO chat_history (role, content) VALUES (?,?)", (role, content))
        conn.commit()
        cur = conn.execute("SELECT last_insert_rowid()")
        return cur.fetchone()[0]

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
def insert_habit(name, target_count=1, period="daily", color="#7B68EE"):
    _flush_pending_commits()
    with get_conn() as conn:
        max_order = conn.execute("SELECT COALESCE(MAX(sort_order),0) FROM habits").fetchone()[0]
        conn.execute("INSERT INTO habits (name, target_count, period, color, sort_order) VALUES (?,?,?,?,?)", (name, target_count, period, color, max_order+1))
        conn.commit()
        cur = conn.execute("SELECT last_insert_rowid()")
        return cur.fetchone()[0]

def get_habits():
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM habits ORDER BY sort_order ASC").fetchall()
        return [dict(r) for r in rows]

def log_habit(habit_id, log_date=None, count=1):
    _flush_pending_commits()
    if log_date is None:
        log_date = date.today().isoformat()
    with get_conn() as conn:
        existing = conn.execute("SELECT id, count FROM habit_logs WHERE habit_id=? AND log_date=?", (habit_id, log_date)).fetchone()
        if existing:
            conn.execute("UPDATE habit_logs SET count=? WHERE id=?", (existing["count"] + count, existing["id"]))
        else:
            conn.execute("INSERT INTO habit_logs (habit_id, log_date, count) VALUES (?,?,?)", (habit_id, log_date, count))
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

def delete_habit(habit_id):
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute("DELETE FROM habit_logs WHERE habit_id=?", (habit_id,))
        conn.execute("DELETE FROM habits WHERE id=?", (habit_id,))
        conn.commit()
        return True

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


def assign_todo(todo_id: int, assigned_date: str = None, week_start: str = None, task_level: str = 'day') -> bool:
    """分配任务到某天/某周/升级层级"""
    _flush_pending_commits()
    with get_conn() as conn:
        conn.execute(
            "UPDATE todos SET assigned_date=?, week_start=?, task_level=?, updated_at=datetime('now','localtime') WHERE id=?",
            (assigned_date, week_start, task_level, todo_id)
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

