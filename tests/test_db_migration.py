"""
数据库迁移测试

覆盖：
- V22 迁移幂等性（已迁移的 DB 重跑不报错）
- V24 迁移幂等性（已迁移的 DB 重跑不报错）
- init_db 后所有表存在
"""
import db


def test_v22_migration_idempotent(temp_db):
    """已迁移到 V24 的 DB 重跑 init_db 不报错（V22 已包含在内）"""
    # temp_db fixture 已执行 init_db() 一次，DB 已在 V24
    # 再次执行不应抛出异常
    db.init_db()

    # 验证 schema 版本仍为 24
    with db.get_conn() as conn:
        row = conn.execute("SELECT value FROM schema_version WHERE key='version'").fetchone()
        assert row is not None
        assert int(row["value"]) == db.SCHEMA_VERSION


def test_v24_migration_idempotent(temp_db):
    """已迁移到 V24 的 DB 重跑 init_db 不报错"""
    db.init_db()
    db.init_db()  # 再次执行，验证幂等

    with db.get_conn() as conn:
        row = conn.execute("SELECT value FROM schema_version WHERE key='version'").fetchone()
        assert row is not None
        assert int(row["value"]) == 24


def test_init_db_creates_tables(temp_db):
    """init_db 后所有核心表存在"""
    expected_tables = {
        "activities",
        "app_usage",
        "reports",
        "schema_version",
        "app_category_rules",
        "daily_profiles",
        "user_profile",
        "user_corrections",
        "pomodoro_sessions",
        "todos",
        "diaries",
        "achievements",
        "countdowns",
        "chat_history",
        "habits",
        "habit_logs",
        "plan_meta",
        "profile_analysis_cache",
    }

    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        actual_tables = {r["name"] for r in rows}

    missing = expected_tables - actual_tables
    assert not missing, f"缺少表: {missing}"
