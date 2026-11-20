"""
B04 回归：小黑核心写操作必须真正落库（此前全部缺 commit，HTTP 报 ok 但数据为 0）。
"""
import sqlite3

import db
import xiaohei_core as xc


def _rows(table):
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
    finally:
        conn.close()


def test_create_work_record_persists(temp_db):
    rid = xc.create_work_record({"date": "2026-11-20", "title": "写 Wave1", "category": "编码开发"})["id"]
    rows = _rows("work_records")
    assert any(r["id"] == rid and r["title"] == "写 Wave1" for r in rows), f"未落库: {rows}"


def test_extract_from_activities_persists(temp_db):
    db.insert_activity("2026-11-20 10:00:00", "a.jpg", "Code.exe", "main.py", "开发", "写代码")
    db.insert_activity("2026-11-20 10:01:00", "b.jpg", "Code.exe", "main.py", "开发", "写代码")
    result = xc.extract_work_records_from_activities("2026-11-20")
    assert result["extracted"] >= 1
    rows = _rows("work_records")
    assert any(r["app_name"] == "Code.exe" for r in rows), f"extract 未落库: {rows}"
    # 幂等：再跑一次不重复生成
    again = xc.extract_work_records_from_activities("2026-11-20")
    assert again["extracted"] == 0
    assert len(_rows("work_records")) == len(rows)


def test_points_ledger_persists(temp_db):
    xc.points_grant(100, "test-grant", "b04")
    rows = _rows("points_ledger")
    assert any(r["item"] == "test-grant" and r["amount"] == 100 for r in rows), f"积分未落库: {rows}"
