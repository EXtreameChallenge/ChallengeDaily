"""B32: xiaohei_core 补充单测（真实 SQLite 临时库）。"""
import json
from datetime import date

import pytest

import xiaohei_core as xc


def _today():
    return date.today().isoformat()


def test_work_record_crud_and_summary(temp_db):
    rid = xc.create_work_record({
        "title": "  写测试  ", "category": "不存在分类", "content": "内容",
        "app_name": "Code.exe", "duration_sec": 120,
    })["id"]
    # 非法分类回退到“其他”
    rows = xc.list_work_records(day=_today())
    assert any(r["id"] == rid and r["category"] == "其他" for r in rows)
    # 空标题会自动生成
    rid2 = xc.create_work_record({"title": ""})["id"]
    assert any(r["id"] == rid2 for r in xc.list_work_records())
    assert xc.update_work_record(rid, {"title": "改标题", "duration_sec": 60})["ok"]
    assert xc.update_work_record(99999, {"title": "x"})["ok"] is False
    summary = xc.get_work_records_daily_summary(_today())
    assert summary["count"] >= 2
    assert summary["total_seconds"] >= 60
    assert xc.list_work_records(category="其他")
    assert xc.delete_work_record(rid2)["ok"]
    assert all(r["id"] != rid2 for r in xc.list_work_records())


def test_extract_empty(temp_db):
    result = xc.extract_work_records_from_activities("2000-01-01")
    assert result["extracted"] == 0


def test_points_balance_consume_and_records(temp_db):
    assert xc.get_points_balance() == {"balance": 0, "credits": 0}
    assert xc.points_consume_amount(0, "x")["ok"] is False
    assert xc.points_consume_amount(10, "x")["error"] == "积分不足"
    xc.points_grant(100, "grant")
    assert xc.get_points_balance()["balance"] == 100
    assert xc.points_consume_amount(30, "consume")["ok"] is True
    assert xc.get_points_balance()["balance"] == 70
    assert xc.points_consume("ai_chat")["ok"] is True
    records = xc.get_points_usage_records()
    assert records["total"] >= 3
    assert xc.conn_exec_any("points_ledger") is True


def test_badges(temp_db):
    badges = xc.get_badges()
    assert len(badges) >= 6
    first = badges[0]["id"]
    r = xc.badge_track_progress(first, add=999)
    assert r["ok"] is True
    assert r["unlocked"] is True
    # 已解锁再次推进直接返回
    assert xc.badge_track_progress(first)["unlocked"] is True
    assert xc.badge_track_progress("no_such_badge")["ok"] is False


def test_templates(temp_db):
    templates = xc.list_templates()
    assert len(templates) >= 5
    assert xc.list_templates("日报")
    tid = xc.create_template({"name": "T", "category": "测试", "content": "C", "price": "3"})["id"]
    assert any(t["id"] == tid for t in xc.list_templates("测试"))
    use = xc.use_template(tid)
    assert use["ok"] is True
    assert use["downloads"] == 1
    assert xc.use_template(tid)["downloads"] == 2
    assert xc.use_template(99999)["ok"] is False
    assert xc.delete_template(tid)["ok"]


def test_token_and_frame_logs(temp_db):
    r = xc.record_token_usage("report", 10, 20, 3)
    assert r["total"] == 30
    summary = xc.get_token_usage_summary()
    assert summary["total_tokens"] >= 30
    assert summary["total_cost_points"] >= 3
    assert xc.list_token_usage()

    xc.log_frame_dedup("saved", 0.0, "x" * 600)
    xc.log_frame_dedup("skipped", 100.0, "dup")
    logs = xc.list_frame_dedup_log()
    assert len(logs) == 2
    assert len(logs[0]["detail"]) <= 500
    assert xc.clear_frame_dedup_log()["ok"]
    assert xc.list_frame_dedup_log() == []


def test_backup_export_preview_import_clear(temp_db, tmp_path):
    xc.create_work_record({"title": "备份记录"})
    out = xc.export_backup(str(tmp_path))
    assert out["ok"] is True
    assert out["size_bytes"] > 0

    preview = xc.preview_import_backup(out["file"])
    assert preview["ok"] is True
    assert preview["stats"]["work_records"] >= 1

    # 损坏备份
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    assert xc.preview_import_backup(str(bad))["ok"] is False
    assert xc.import_backup(str(bad))["ok"] is False

    clear = xc.clear_all_data()
    assert clear["ok"] is True
    imported = xc.import_backup(out["file"])
    assert imported["ok"] is True
    assert imported["imported"] >= 1

    stats = xc.get_storage_stats()
    assert "work_records" in stats
    assert stats["screenshot_dir_size_mb"] >= 0

    assert xc.preview_import_backup(str(tmp_path / "missing.json"))["ok"] is False


def test_apply_template_to_daily_report(temp_db, monkeypatch):
    tid = xc.create_template({"name": "模板A", "content": "正文"})["id"]
    import report
    saved = {}
    monkeypatch.setattr(report, "generate_daily_report", lambda day: "日报正文")
    monkeypatch.setattr(report, "_save", lambda content, day: saved.update(content=content, day=day))
    result = xc.apply_template_to_daily_report(tid, "2026-01-02")
    assert result["ok"] is True
    assert "模板A" in saved["content"]
    assert saved["day"] == "2026-01-02"
    assert xc.apply_template_to_daily_report(99999)["ok"] is False


def test_start_daily_auto_extract_guard(monkeypatch):
    class Alive:
        def is_alive(self):
            return True

    monkeypatch.setattr(xc, "_auto_extract_thread", Alive())
    xc.start_daily_auto_extract()  # 已有存活线程时不重复启动
