"""
B41 数据卫生回归：7天保留清理必须能清掉 timestamp 非法的历史垃圾行
（BLOB / 非日期文本，来自旧版错误写入与恢复脚本残留），且不误伤正常行。
"""
import sqlite3
from datetime import date, timedelta

import db

_COLS = "(timestamp, app_name, window_title, category, summary)"
_VALS = "(?, ?, ?, ?, ?)"


def _insert(conn, ts, app, title):
    conn.execute(f"INSERT INTO activities {_COLS} VALUES {_VALS}", (ts, app, title, "开发", "s"))


def test_b41_cleanup_removes_garbage_timestamp_rows(temp_db):
    conn = sqlite3.connect(temp_db)
    conn.execute("PRAGMA journal_mode=WAL")
    # 三类垃圾行（复刻生产库实际形态）
    conn.execute(f"INSERT INTO activities {_COLS} VALUES {_VALS}", (b"\x00\x01\x02", None, None, None, None))
    _insert(conn, "幕布同步/2025.09.18.md", "幕布同步", "")
    _insert(conn, "sqlite_autoindex_productivity_scores_1", "productivity_scores", "1791")
    # 正常行：今日一条 + 超出保留期一条（后者按 7 天规则应被清，属预期行为）
    today = date.today().isoformat()
    _insert(conn, f"{today} 10:00:00", "Code.exe", "main.py")
    _insert(conn, "2026-01-01 08:00:00", "Code.exe", "old.py")
    conn.commit()
    conn.close()

    db.cleanup_old_data(7)

    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT timestamp FROM activities").fetchall()
    conn.close()

    assert [r[0] for r in rows] == [f"{today} 10:00:00"], f"应只剩今日正常行，实际: {rows}"
    assert db.count_activities_today() >= 1 if hasattr(db, "count_activities_today") else True


def test_b41_import_timestamp_rejects_garbage():
    """B41 写入源头加固：外部导入必须先归一化，垃圾时间戳不得入库。"""
    from routes.imports import _normalize_import_timestamp

    assert _normalize_import_timestamp("2026-11-21 10:00:00") == "2026-11-21 10:00:00"
    assert _normalize_import_timestamp("2026-11-21 10:00") == "2026-11-21 10:00:00"
    assert _normalize_import_timestamp("2026-11-21") == "2026-11-21 00:00:00"
    assert _normalize_import_timestamp("幕布同步/2025.09.18.md") is None
    assert _normalize_import_timestamp("sqlite_autoindex_productivity_scores_1") is None
    assert _normalize_import_timestamp(b"\x00\x01\x02") is None

