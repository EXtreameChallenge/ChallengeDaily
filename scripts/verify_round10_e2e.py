#!/usr/bin/env python3
"""轮10 B24/B25/B37 隔离环境端到端验证（不触碰真实用户目录）。"""
import argparse
import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from legacy_aliases import install  # noqa: E402

install()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--home-dir", required=True)
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    home_dir = Path(args.home_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    home_dir.mkdir(parents=True, exist_ok=True)
    os.environ["CHALLENGE_DAILY_DATA_DIR"] = str(data_dir)
    os.environ["CHALLENGE_DAILY_HOME_DATA_DIR"] = str(home_dir)

    import config
    import db
    db.init_db()

    # 造真实业务数据
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO activities (timestamp, app_name, category, summary) VALUES (?,?,?,?)",
            ("2026-11-21 09:00:00", "Code", "开发", "轮10验证活动"),
        )
        conn.commit()

    (data_dir / "screenshots").mkdir(exist_ok=True)
    (data_dir / "screenshots" / "round10-test.png").write_bytes(b"fake-png")
    (data_dir / "reports").mkdir(exist_ok=True)
    (data_dir / "reports" / "round10-test.md").write_text("# report", encoding="utf-8")
    (data_dir / "logs").mkdir(exist_ok=True)
    (data_dir / "logs" / "round10-test.log").write_text("log line", encoding="utf-8")
    (data_dir / "benchmark_profile.json").write_text(
        json.dumps({"anonymous_id": "round10-test"}), encoding="utf-8"
    )
    (data_dir / "xiaohei.db.bak").write_bytes(b"old-db-backup")
    (data_dir / "screenshot_salt.bin").write_bytes(b"0123456789abcdef")
    config.save_settings({**config.load_settings(), "telemetry_enabled": False})

    # B24：home JSON 迁移
    (home_dir / "points.json").write_text(json.dumps({
        "balance": 120,
        "ledger": [{"amount": 100, "reason": "legacy"}],
    }), encoding="utf-8")
    (home_dir / "templates.json").write_text(json.dumps([
        {"name": "旧模板", "category": "日报", "content": "旧内容", "price": 5, "downloads": 1000},
    ], ensure_ascii=False), encoding="utf-8")
    (home_dir / "telemetry.jsonl").write_text(json.dumps({"event": "legacy", "data": {"x": 1}}) + "\n", encoding="utf-8")
    (home_dir / "friends.json").write_text(json.dumps({"friends": [], "invitations": [], "sharedTodos": []}), encoding="utf-8")
    (home_dir / "user.json").write_text(json.dumps({"name": "legacy"}), encoding="utf-8")

    import enterprise_store
    report = enterprise_store.migrate_home_data(backup=True)
    with db.get_conn() as conn:
        bal = conn.execute("SELECT COALESCE(SUM(CASE WHEN type='credit' THEN amount ELSE -amount END),0) b FROM points_ledger").fetchone()["b"]
        old_tpl = conn.execute("SELECT * FROM template_market WHERE name='旧模板'").fetchone()
    assert int(bal) == 120, bal
    assert old_tpl and int(old_tpl["downloads"]) == 0
    assert (data_dir / "backups").exists()
    assert not (home_dir / "points.json").exists()
    assert (data_dir / "archives" / "round10-home-json").exists()

    # B25：模板真实使用/下载计数与价格
    import xiaohei_core
    from enterprise_features import TemplateMarket
    assert xiaohei_core.use_template(int(old_tpl["id"]))["downloads"] == 1
    tpl = TemplateMarket().publish("新模板", "新内容", 7)
    assert tpl["template"]["price"] == 7, tpl

    # B37：备份 -> 导出 -> 删除 -> 扫描 -> 恢复
    from flask import Flask
    from routes.backup import bp as backup_bp
    from routes.privacy_routes import privacy_bp
    app = Flask(__name__)
    app.register_blueprint(backup_bp)
    app.register_blueprint(privacy_bp)
    client = app.test_client()
    backup_resp = client.post("/api/backup")
    assert backup_resp.status_code == 200 and len(backup_resp.data) > 0
    backup_zip = Path(tempfile.mkdtemp()) / "round10-e2e.zip"
    backup_zip.write_bytes(backup_resp.data)

    export_resp = client.get("/api/privacy/export")
    assert export_resp.status_code == 200
    exported = export_resp.get_json()
    assert exported["tables"]["activities"], "导出必须包含 activities"
    assert "screenshot_salt.bin" in exported["files"]
    assert "logs/round10-test.log" in exported["directories"]
    assert "benchmark_profile.json" in exported["files"]
    assert "xiaohei.db.bak" in exported["files"]

    delete_resp = client.delete("/api/privacy/data")
    assert delete_resp.status_code == 200
    deleted = delete_resp.get_json()
    assert deleted["scan"]["clean"] is True, deleted["scan"]
    assert deleted["scan"]["salt_files"] == []
    assert deleted["scan"]["home_files"] == []
    assert not (data_dir / "logs" / "round10-test.log").exists()
    assert not (data_dir / "benchmark_profile.json").exists()
    assert not (data_dir / "xiaohei.db.bak").exists()

    restore_resp = client.post(
        "/api/backup/restore",
        data={"file": (io.BytesIO(backup_zip.read_bytes()), "round10-e2e.zip")},
        content_type="multipart/form-data",
    )
    assert restore_resp.status_code == 200, restore_resp.get_data(as_text=True)
    with db.get_conn() as conn:
        restored_activities = conn.execute("SELECT COUNT(*) c FROM activities").fetchone()["c"]
        restored_tpl = conn.execute("SELECT downloads FROM template_market WHERE name='旧模板'").fetchone()
    assert restored_activities >= 1
    assert restored_tpl and int(restored_tpl["downloads"]) == 1
    assert (data_dir / "screenshot_salt.bin").exists()
    assert (data_dir / "screenshots" / "round10-test.png").exists()
    assert (data_dir / "archives" / "round10-home-json").exists()
    assert (data_dir / "logs" / "round10-test.log").exists()
    assert (data_dir / "benchmark_profile.json").exists()
    assert (data_dir / "xiaohei.db.bak").exists()

    print(json.dumps({
        "status": "ok",
        "migration_before": report["before"],
        "migration_after": report["after"],
        "points_balance": int(bal),
        "legacy_template_downloads_after_use": 1,
        "published_template_price": tpl["template"]["price"],
        "export_tables": len(exported["tables"]),
        "delete_rows": deleted["deleted"]["row_count"],
        "scan_clean": deleted["scan"]["clean"],
        "restored_activities": restored_activities,
        "restored_legacy_template_downloads": int(restored_tpl["downloads"]),
        "restored_salt": True,
        "restored_screenshot": True,
        "export_directories": len(exported["directories"]),
        "export_files": len(exported["files"]),
        "logs_removed_and_restored": True,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
