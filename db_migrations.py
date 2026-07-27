"""
ChallengeDaily Windows 版 — SQLite Schema 迁移管理
从 db.py 拆分：包含 SCHEMA_VERSION、默认配置、ACL 设置、init_db 及完整 V1-V36 迁移逻辑
"""
import sqlite3
import logging

from config import DB_PATH

logger = logging.getLogger(__name__)

# ── 数据库 Schema 版本 ──
SCHEMA_VERSION = 36

# P-01: 默认数据保留天数（90 天）
DEFAULT_DATA_RETENTION_DAYS = 90


# P0-10: 数据库文件 ACL（Windows），仅当前用户可读写
def _set_db_acl(db_path):
    try:
        import win32security, win32con, win32api
        username = win32api.GetUserNameEx(win32con.NameSamCompatible)
        sid, _, _ = win32security.LookupAccountName(None, username)
        sd = win32security.SECURITY_DESCRIPTOR()
        sd.SetSecurityDescriptorOwner(sid, False)
        dacl = win32security.ACL()
        dacl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_ALL, sid)
        sd.SetSecurityDescriptorDacl(True, dacl, False)
        win32security.SetFileSecurity(str(db_path), win32security.DACL_SECURITY_INFORMATION, sd)
    except ImportError:
        pass  # 非 Windows 平台跳过


def init_db():
    """初始化数据库表 + Schema 版本管理"""
    try:
        _init_db_impl()
    except Exception as e:
        logger.error(f"init_db 失败: {e}", exc_info=True)
        raise


def _init_db_impl():
    """init_db 的实际实现（被 init_db 包装在 try/except 中）"""
    from db import get_conn  # 延迟导入，避免循环依赖

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
        _db_first_create = (current_version == 0)  # P0-10: 标记 DB 是否首次创建

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
        # 迁移加事务保护：备份 + 行数校验 + BEGIN/COMMIT
        if current_version < 9:
            try:
                conn.execute("BEGIN")
                # 迁移前备份（防止迁移失败导致数据丢失）
                conn.execute("DROP TABLE IF EXISTS app_usage_v9_backup")
                conn.execute("CREATE TABLE app_usage_v9_backup AS SELECT * FROM app_usage")
                old_count = conn.execute("SELECT COUNT(*) FROM app_usage").fetchone()[0]
                # 创建新表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS app_usage_v9 (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        app_name    TEXT NOT NULL,
                        window_title TEXT,
                        start_time  TEXT NOT NULL,
                        end_time    TEXT,
                        duration_sec INTEGER DEFAULT 0,
                        UNIQUE(app_name, window_title, start_time)
                    )
                """)
                # 同 (app, title, start) 多条时取 duration 最大者，避免迁移时唯一冲突
                conn.execute("""
                    INSERT OR IGNORE INTO app_usage_v9 (app_name, window_title, start_time, end_time, duration_sec)
                    SELECT app_name, window_title, start_time, end_time, MAX(duration_sec)
                    FROM app_usage
                    GROUP BY app_name, window_title, start_time
                """)
                # INSERT 后校验：若新表行数少于旧表，说明可能有数据丢失
                new_count = conn.execute("SELECT COUNT(*) FROM app_usage_v9").fetchone()[0]
                if new_count < old_count:
                    logger.warning(f"V9迁移: 数据可能丢失 {old_count} -> {new_count}")
                # 校验通过后再 DROP 旧表
                conn.execute("DROP TABLE IF EXISTS app_usage")
                conn.execute("ALTER TABLE app_usage_v9 RENAME TO app_usage")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_app_usage_app ON app_usage(app_name)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_app_usage_start ON app_usage(start_time)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_app_usage_title ON app_usage(app_name, window_title)")
                conn.execute("COMMIT")
                # 迁移成功后清理备份表
                conn.execute("DROP TABLE IF EXISTS app_usage_v9_backup")
            except Exception as e:
                logger.error(f"V9迁移失败，回滚: {e}")
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                # 迁移失败时从备份恢复
                try:
                    conn.execute("DROP TABLE IF EXISTS app_usage")
                    conn.execute("ALTER TABLE app_usage_v9_backup RENAME TO app_usage")
                except Exception:
                    pass
                raise

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

        # V21: habit_logs 唯一约束 + 复合索引
        if current_version < 21:
            # habit_logs 表加唯一索引（替代 UNIQUE 约束，避免重建表）
            # 注意：若已存在重复 (habit_id, log_date) 行，CREATE UNIQUE INDEX 会失败；
            # 此时先合并重复行再建索引
            try:
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_habit_logs_unique ON habit_logs(habit_id, log_date)"
                )
            except sqlite3.IntegrityError:
                # 合并重复行：保留最大 id 的行，其余删除并把 count 累加到保留行
                logger.warning("V21: habit_logs 存在重复行，开始合并...")
                dup_rows = conn.execute("""
                    SELECT habit_id, log_date, COUNT(*) as cnt
                    FROM habit_logs GROUP BY habit_id, log_date HAVING COUNT(*) > 1
                """).fetchall()
                for dup in dup_rows:
                    hid, ld = dup["habit_id"], dup["log_date"]
                    rows = conn.execute(
                        "SELECT id, count FROM habit_logs WHERE habit_id=? AND log_date=? ORDER BY id",
                        (hid, ld)
                    ).fetchall()
                    keep_id = rows[-1]["id"]
                    total = sum(r["count"] for r in rows)
                    conn.execute("UPDATE habit_logs SET count=? WHERE id=?", (total, keep_id))
                    conn.execute(
                        "DELETE FROM habit_logs WHERE habit_id=? AND log_date=? AND id<>?",
                        (hid, ld, keep_id)
                    )
                conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_habit_logs_unique ON habit_logs(habit_id, log_date)"
                )
                logger.info("V21: habit_logs 重复行合并完成")

        # V22: app_usage window_title NULL → NOT NULL DEFAULT ''，修复 UNIQUE 约束语义
        # SQL NULL != NULL 导致 NULL window_title 的行不参与 UNIQUE 冲突检测
        if current_version < 22:
            # 事务保护：DROP/RENAME 失败时回滚，避免数据丢失
            try:
                conn.execute("BEGIN IMMEDIATE")
                # 迁移前备份原表，便于异常恢复
                conn.execute("DROP TABLE IF EXISTS app_usage_v22_backup")
                conn.execute("CREATE TABLE app_usage_v22_backup AS SELECT * FROM app_usage")
                # 将现有 NULL 值替换为空字符串
                conn.execute("UPDATE app_usage SET window_title = '' WHERE window_title IS NULL")
                # 重建表以添加 NOT NULL 约束（SQLite 不支持 ALTER COLUMN）
                conn.execute("DROP TABLE IF EXISTS app_usage_v22")
                conn.execute("""
                    CREATE TABLE app_usage_v22 (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        app_name    TEXT NOT NULL,
                        window_title TEXT NOT NULL DEFAULT '',
                        start_time  TEXT NOT NULL,
                        end_time    TEXT,
                        duration_sec INTEGER DEFAULT 0,
                        UNIQUE(app_name, window_title, start_time)
                    )
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO app_usage_v22 (id, app_name, window_title, start_time, end_time, duration_sec)
                    SELECT id, app_name, COALESCE(window_title, ''), start_time, end_time, duration_sec FROM app_usage
                """)
                # 校验行数
                old_count = conn.execute("SELECT COUNT(*) FROM app_usage").fetchone()[0]
                new_count = conn.execute("SELECT COUNT(*) FROM app_usage_v22").fetchone()[0]
                if new_count < old_count:
                    logger.warning(f"V22 迁移：app_usage 行数减少 {old_count}->{new_count}，可能有重复数据被合并")
                conn.execute("DROP TABLE app_usage")
                conn.execute("ALTER TABLE app_usage_v22 RENAME TO app_usage")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_app_usage_app ON app_usage(app_name)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_app_usage_start ON app_usage(start_time)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_app_usage_start_app ON app_usage(start_time, app_name)")
                # 迁移成功，删除备份表
                conn.execute("DROP TABLE IF EXISTS app_usage_v22_backup")
                conn.execute("COMMIT")
                logger.info(f"V22: app_usage window_title NOT NULL DEFAULT '' 迁移完成 ({new_count} rows)")
            except Exception as v22_err:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                # 尝试从备份恢复
                try:
                    conn.execute("DROP TABLE IF EXISTS app_usage")
                    conn.execute("ALTER TABLE app_usage_v22_backup RENAME TO app_usage")
                except Exception:
                    pass
                logger.error(f"V22 迁移失败，已尝试回滚: {v22_err}", exc_info=True)
                raise

            # 复合索引优化（提升常用查询性能）
            conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_app_cat ON activities(app_name, category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pomodoro_start_status ON pomodoro_sessions(start_time, status)")

        # V23: AI 自我认知分析缓存表（累积理解系统）
        if current_version < 23:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS profile_analysis_cache (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_type TEXT NOT NULL,
                    result_json TEXT NOT NULL DEFAULT '{}',
                    confidence REAL DEFAULT 0.0,
                    data_points INTEGER DEFAULT 0,
                    created_at  TEXT DEFAULT (datetime('now','localtime')),
                    updated_at  TEXT DEFAULT (datetime('now','localtime')),
                    UNIQUE(analysis_type)
                );
                CREATE INDEX IF NOT EXISTS idx_profile_analysis_type ON profile_analysis_cache(analysis_type);
            """)

        # V24: 待办-番茄钟深度整合 — 预估番茄数 + 番茄大小 + 连续执行
        if current_version < 24:
            # SQLite ALTER TABLE ADD COLUMN 不支持 IF NOT EXISTS，需检查列存在性（避免重跑失败）
            existing_todos_cols = {row[1] for row in conn.execute("PRAGMA table_info(todos)").fetchall()}
            if 'estimated_pomodoros' not in existing_todos_cols:
                conn.execute("ALTER TABLE todos ADD COLUMN estimated_pomodoros INTEGER DEFAULT 1")
            if 'pomodoro_size' not in existing_todos_cols:
                conn.execute("ALTER TABLE todos ADD COLUMN pomodoro_size TEXT DEFAULT 'big'")

            existing_pomo_cols = {row[1] for row in conn.execute("PRAGMA table_info(pomodoro_sessions)").fetchall()}
            if 'pomodoro_index' not in existing_pomo_cols:
                conn.execute("ALTER TABLE pomodoro_sessions ADD COLUMN pomodoro_index INTEGER DEFAULT 1")
            if 'total_pomodoros' not in existing_pomo_cols:
                conn.execute("ALTER TABLE pomodoro_sessions ADD COLUMN total_pomodoros INTEGER DEFAULT 1")

        # V25: 创建 settings 表（用于 feature_flags / data_retention_days / privacy_apps 等配置）
        if current_version < 25:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key)")
            logger.info("V25: settings 表创建完成")

        # V26: 多媒体日记 — diaries 加 media_json 列（图片/语音/链接卡片 JSON）
        if current_version < 26:
            existing_diary_cols = {row[1] for row in conn.execute("PRAGMA table_info(diaries)").fetchall()}
            if 'media_json' not in existing_diary_cols:
                conn.execute("ALTER TABLE diaries ADD COLUMN media_json TEXT DEFAULT '[]'")
            if 'font_style' not in existing_diary_cols:
                conn.execute("ALTER TABLE diaries ADD COLUMN font_style TEXT DEFAULT ''")
            logger.info("V26: diaries 表扩展完成（media_json + font_style）")

        # V27: 长期目标管理（GoalDay集大成——年度/季度目标 + 关联待办 + 进度追踪）
        if current_version < 27:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS goals (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    title           TEXT NOT NULL,
                    description     TEXT DEFAULT '',
                    category        TEXT DEFAULT 'personal',  -- personal/work/health/learning/finance
                    timeframe       TEXT DEFAULT 'yearly',   -- yearly/quarterly/monthly
                    start_date      TEXT NOT NULL,
                    target_date     TEXT NOT NULL,
                    status          TEXT DEFAULT 'active',   -- active/completed/archived
                    progress        INTEGER DEFAULT 0,        -- 0-100
                    key_results     TEXT DEFAULT '[]',        -- JSON: 关键结果列表
                    linked_todos    TEXT DEFAULT '[]',        -- JSON: 关联待办ID
                    linked_habits   TEXT DEFAULT '[]',        -- JSON: 关联习惯ID
                    color           TEXT DEFAULT '#6366f1',
                    created_at      TEXT DEFAULT (datetime('now','localtime')),
                    updated_at      TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
                CREATE INDEX IF NOT EXISTS idx_goals_timeframe ON goals(timeframe);
            """)
            logger.info("V27: goals 表创建完成（长期目标管理）")

        # V28: 待办关联长期目标（GoalDay集大成——年目标→周计划→日执行闭环）
        if current_version < 28:
            existing_todo_cols = {row[1] for row in conn.execute("PRAGMA table_info(todos)").fetchall()}
            if 'goal_id' not in existing_todo_cols:
                conn.execute("ALTER TABLE todos ADD COLUMN goal_id INTEGER DEFAULT NULL")
            if 'week_start' not in existing_todo_cols:
                conn.execute("ALTER TABLE todos ADD COLUMN week_start TEXT DEFAULT NULL")
            if 'assigned_date' not in existing_todo_cols:
                conn.execute("ALTER TABLE todos ADD COLUMN assigned_date TEXT DEFAULT NULL")
            # 创建索引加速目标关联查询
            conn.execute("CREATE INDEX IF NOT EXISTS idx_todos_goal_id ON todos(goal_id)")
            logger.info("V28: todos 表扩展完成（goal_id + week_start + assigned_date）")

        # V29: habits 表新增 auto_category 字段（P6-2：习惯-采集数据自动联动）
        if current_version < 29:
            existing_habit_cols = {row[1] for row in conn.execute("PRAGMA table_info(habits)").fetchall()}
            if 'auto_category' not in existing_habit_cols:
                conn.execute("ALTER TABLE habits ADD COLUMN auto_category TEXT DEFAULT NULL")
            logger.info("V29: habits 表扩展完成（auto_category）")

        # V30: 报告全文检索（FTS5 外部内容表 + 触发器自动同步）
        # P8-1：实现报告内容秒级全文检索，支持 snippet 高亮与 MATCH 排序
        if current_version < 30:
            try:
                conn.executescript("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS reports_fts USING fts5(
                        report_date,
                        content,
                        content='reports',
                        content_rowid='id',
                        tokenize='unicode61'
                    );

                    CREATE TRIGGER IF NOT EXISTS reports_fts_ai AFTER INSERT ON reports BEGIN
                        INSERT INTO reports_fts(rowid, report_date, content)
                        VALUES (new.id, new.report_date, new.content);
                    END;

                    CREATE TRIGGER IF NOT EXISTS reports_fts_ad AFTER DELETE ON reports BEGIN
                        INSERT INTO reports_fts(reports_fts, rowid, report_date, content)
                        VALUES ('delete', old.id, old.report_date, old.content);
                    END;

                    CREATE TRIGGER IF NOT EXISTS reports_fts_au AFTER UPDATE ON reports BEGIN
                        INSERT INTO reports_fts(reports_fts, rowid, report_date, content)
                        VALUES ('delete', old.id, old.report_date, old.content);
                        INSERT INTO reports_fts(rowid, report_date, content)
                        VALUES (new.id, new.report_date, new.content);
                    END;
                """)
                # 回填已有数据
                conn.execute(
                    "INSERT OR IGNORE INTO reports_fts(rowid, report_date, content) "
                    "SELECT id, report_date, content FROM reports"
                )
                logger.info("V30: reports_fts 全文检索索引创建完成（含触发器与回填）")
            except Exception as e:
                logger.warning(f"V30 FTS5 创建失败（可能 SQLite 未启用 FTS5）: {e}")

        # V31: AI 重试队列 + 赛季成就表
        if current_version < 31:
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS ai_retry_queue (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        kind          TEXT NOT NULL,
                        payload       TEXT NOT NULL,
                        attempts      INTEGER DEFAULT 0,
                        last_attempt  TEXT,
                        created_at    TEXT,
                        status        TEXT DEFAULT 'pending'
                    );
                    CREATE INDEX IF NOT EXISTS idx_ai_retry_status ON ai_retry_queue(status, attempts);

                    CREATE TABLE IF NOT EXISTS achievement_seasons (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        season_key    TEXT NOT NULL UNIQUE,
                        start_date    TEXT NOT NULL,
                        end_date      TEXT NOT NULL,
                        created_at    TEXT DEFAULT (datetime('now','localtime'))
                    );
                    CREATE TABLE IF NOT EXISTS season_achievements (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        season_key    TEXT NOT NULL,
                        achievement_key TEXT NOT NULL,
                        user_id       INTEGER,
                        unlocked_at   TEXT,
                        progress      INTEGER DEFAULT 0,
                        UNIQUE(season_key, achievement_key)
                    );
                    CREATE INDEX IF NOT EXISTS idx_season_ach_key ON season_achievements(season_key, achievement_key);
                """)
                logger.info("V31: AI 重试队列 + 赛季成就表创建完成")
            except Exception as e:
                logger.warning(f"V31 schema 升级失败: {e}")

        # V32: AI 审计日志 + 用户个性化偏好
        # P11-3：审计日志（AI 调用审计链）+ P11-2：个性化偏好（报告风格/欢迎语开关）
        if current_version < 32:
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id            INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts            TEXT NOT NULL,
                        category      TEXT NOT NULL,
                        action        TEXT NOT NULL,
                        status        TEXT NOT NULL,
                        detail        TEXT,
                        duration_ms   INTEGER,
                        metadata      TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
                    CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_log(category);
                    CREATE INDEX IF NOT EXISTS idx_audit_status ON audit_log(status);

                    CREATE TABLE IF NOT EXISTS user_preferences (
                        key    TEXT PRIMARY KEY,
                        value  TEXT,
                        updated_at TEXT
                    );
                """)
                logger.info("V32: 审计日志 + 用户偏好表创建完成")
            except Exception as e:
                logger.warning(f"V32 schema 升级失败: {e}")

        # V33: P20-4 — 索引冗余清理 + 复合索引优化
        # 1. 新增复合索引：activities(timestamp, category) — 日报高频按时间+分类聚合
        # 2. 新增复合索引：activities(category, timestamp) — 按分类查询历史趋势
        # 3. 移除冗余索引 idx_activities_cat（已被 idx_activities_cat_ts 覆盖左前缀）
        #    （SQLite 不支持 DROP INDEX IF EXISTS，需先检查是否存在）
        # 4. 新增 habits(last_logged_date) 索引 — recommend_habits 高频查询
        if current_version < 33:
            try:
                # 复合索引：按时间过滤后按分类聚合（日报统计主路径）
                conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_ts_cat ON activities(timestamp, category)")
                # 复合索引：按分类查询历史趋势（深度分析、基准对比）
                conn.execute("CREATE INDEX IF NOT EXISTS idx_activities_cat_ts ON activities(category, timestamp)")
                # 习惯推荐路径：按最后打卡日期排序
                conn.execute("CREATE INDEX IF NOT EXISTS idx_habits_last_logged ON habits(last_logged_date DESC)")
                # 移除冗余索引（被 idx_activities_cat_ts 覆盖）
                try:
                    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_activities_cat'")
                    if cur.fetchone():
                        conn.execute("DROP INDEX idx_activities_cat")
                        logger.info("V33: 已移除冗余索引 idx_activities_cat（被 idx_activities_cat_ts 覆盖）")
                except Exception as drop_err:
                    logger.debug(f"V33: 移除 idx_activities_cat 失败（可忽略）: {drop_err}")
                logger.info("V33: 索引优化完成（新增 3 个复合索引，移除 1 个冗余索引）")
            except Exception as e:
                logger.warning(f"V33 schema 升级失败: {e}")

        # V34: 甘特图支持——任务计划开始时刻（分钟偏移，如 540=9:00）
        if current_version < 34:
            try:
                conn.execute("ALTER TABLE todos ADD COLUMN plan_start_min INTEGER DEFAULT NULL")
                logger.info("V34: todos 表新增 plan_start_min 字段（甘特图时间定位）")
            except Exception as e:
                logger.warning(f"V34 schema 升级失败: {e}")

        # V35: 成长系统 + 每日仪式
        if current_version < 35:
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS growth_profile (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        total_exp INTEGER DEFAULT 0,
                        level INTEGER DEFAULT 1,
                        current_level_exp INTEGER DEFAULT 0,
                        dimensions_json TEXT DEFAULT '{}',
                        streak_days INTEGER DEFAULT 0,
                        longest_streak INTEGER DEFAULT 0,
                        last_active_date TEXT,
                        initialized INTEGER DEFAULT 0,
                        updated_at TEXT DEFAULT (datetime('now','localtime'))
                    );

                    CREATE TABLE IF NOT EXISTS growth_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        exp_amount INTEGER NOT NULL,
                        dimension TEXT NOT NULL,
                        source TEXT NOT NULL,
                        source_id INTEGER,
                        quality_mult REAL DEFAULT 1.0,
                        streak_mult REAL DEFAULT 1.0,
                        note TEXT DEFAULT '',
                        created_at TEXT DEFAULT (datetime('now','localtime'))
                    );
                    CREATE INDEX IF NOT EXISTS idx_growth_log_date ON growth_log(created_at);
                    CREATE INDEX IF NOT EXISTS idx_growth_log_dim ON growth_log(dimension);

                    CREATE TABLE IF NOT EXISTS life_quests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        target_date TEXT,
                        status TEXT DEFAULT 'active',
                        progress REAL DEFAULT 0,
                        ai_breakdown_json TEXT DEFAULT '[]',
                        created_at TEXT DEFAULT (datetime('now','localtime'))
                    );

                    CREATE TABLE IF NOT EXISTS quest_stages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        quest_id INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        order_index INTEGER DEFAULT 0,
                        status TEXT DEFAULT 'pending',
                        estimated_hours REAL DEFAULT 0,
                        actual_hours REAL DEFAULT 0,
                        linked_todo_ids TEXT DEFAULT '[]',
                        FOREIGN KEY (quest_id) REFERENCES life_quests(id) ON DELETE CASCADE
                    );

                    CREATE TABLE IF NOT EXISTS daily_plans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL UNIQUE,
                        plan_json TEXT DEFAULT '[]',
                        mit_task TEXT DEFAULT '',
                        focus_target_min INTEGER DEFAULT 240,
                        limits_json TEXT DEFAULT '{}',
                        status TEXT DEFAULT 'planned',
                        adopted_ai INTEGER DEFAULT 0,
                        created_at TEXT DEFAULT (datetime('now','localtime'))
                    );

                    CREATE TABLE IF NOT EXISTS daily_reflections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL UNIQUE,
                        productivity_score REAL,
                        good_thing TEXT DEFAULT '',
                        improve_thing TEXT DEFAULT '',
                        ai_insights_json TEXT DEFAULT '[]',
                        report_generated INTEGER DEFAULT 0,
                        created_at TEXT DEFAULT (datetime('now','localtime'))
                    );

                    CREATE TABLE IF NOT EXISTS productivity_scores (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL UNIQUE,
                        score REAL NOT NULL,
                        deep_work_min INTEGER DEFAULT 0,
                        learning_min INTEGER DEFAULT 0,
                        exercise_min INTEGER DEFAULT 0,
                        distraction_count INTEGER DEFAULT 0,
                        total_active_min INTEGER DEFAULT 0,
                        created_at TEXT DEFAULT (datetime('now','localtime'))
                    );
                """)
                logger.info("V35: 成长系统+每日仪式表创建成功")
            except Exception as e:
                logger.warning(f"V35 schema 升级失败: {e}")

        # V36: 三阶段记忆系统——文档分块 + FTS5 + 向量检索 + Mem0 风格记忆
        # 表说明：
        #   doc_chunks       文档分块（source/source_id 区分来源）
        #   doc_chunks_fts   FTS5 全文索引（unicode61 分词，外部内容表）
        #   doc_chunks_vec   sqlite-vec 向量虚表（512 维，按需创建）
        #   memories         Mem0 风格原子事实（含软删除）
        #   memories_vec     记忆向量虚表（512 维，按需创建）
        #   ingest_jobs      摄入任务进度跟踪
        if current_version < 36:
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS doc_chunks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source TEXT DEFAULT 'mubu',
                        source_id TEXT,
                        chunk_index INTEGER DEFAULT 0,
                        content TEXT,
                        content_hash TEXT,
                        created_at TEXT DEFAULT (datetime('now','localtime'))
                    );
                    CREATE INDEX IF NOT EXISTS idx_doc_chunks_source ON doc_chunks(source, source_id);

                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        source_type TEXT,
                        source_id TEXT,
                        content TEXT,
                        metadata TEXT DEFAULT '{}',
                        created_at TEXT,
                        updated_at TEXT,
                        deleted_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source_type);

                    CREATE TABLE IF NOT EXISTS ingest_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_type TEXT,
                        status TEXT DEFAULT 'pending',
                        total INTEGER DEFAULT 0,
                        done INTEGER DEFAULT 0,
                        error TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    );
                """)
                # FTS5 虚表（可能因 SQLite 未启用 FTS5 而失败，单独 try）
                try:
                    conn.executescript("""
                        CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts USING fts5(
                            content, content='doc_chunks', content_rowid='id', tokenize='unicode61'
                        );
                    """)
                    logger.info("V36: doc_chunks_fts 全文索引创建成功")
                except Exception as fts_err:
                    logger.warning(f"V36: FTS5 创建失败（功能降级为 LIKE）: {fts_err}")
                # sqlite-vec 向量虚表：依赖 sqlite_vec 扩展，按需加载
                # 此处不直接创建 vec0 表（需要扩展已加载），交给 memory_engine.init_memory_schema 处理
                logger.info("V36: 记忆系统表创建成功（向量虚表由 memory_engine 按需创建）")
            except Exception as e:
                logger.warning(f"V36 schema 升级失败: {e}")

        # 更新版本号
        conn.execute(
            "INSERT OR REPLACE INTO schema_version (key, value) VALUES ('version', ?)",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()

    # P0-10: 首次创建 DB 文件时设置 ACL（仅当前用户可读写）
    if _db_first_create:
        _set_db_acl(DB_PATH)

    # WAL checkpoint 配置：每 1000 页自动 checkpoint
    try:
        with get_conn() as conn:
            conn.execute("PRAGMA wal_autocheckpoint=1000")
            # 启动时主动 checkpoint 一次，防止 WAL 文件过大
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        logger.info("WAL checkpoint 配置完成")
    except Exception as e:
        logger.warning(f"WAL checkpoint 配置失败: {e}")

    logger.info(f"Database initialized, schema version: {SCHEMA_VERSION}")
