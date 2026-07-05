import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import date

sys.path.insert(0, '.')

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

_REAL_BACKUP_FILE = None


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    screenshots_dir = data_dir / "screenshots"
    screenshots_dir.mkdir()
    reports_dir = data_dir / "reports"
    reports_dir.mkdir()

    monkeypatch.setattr("config.BASE_DIR", tmp_path)
    monkeypatch.setattr("config.DATA_DIR", data_dir)
    monkeypatch.setattr("config.SCREENSHOT_DIR", screenshots_dir)
    monkeypatch.setattr("config.REPORT_DIR", reports_dir)
    monkeypatch.setattr("config.DB_PATH", data_dir / "xiaohei.db")
    monkeypatch.setattr("config.SETTINGS_PATH", data_dir / "settings.json")

    monkeypatch.setattr("db.DB_PATH", data_dir / "xiaohei.db")
    global _REAL_BACKUP_FILE
    _REAL_BACKUP_FILE = __import__("file_utils", fromlist=["backup_file"]).backup_file
    monkeypatch.setattr("file_utils.backup_file", lambda *a, **kw: None)
    monkeypatch.setattr("config.backup_file", lambda *a, **kw: None)

    import db as _db
    _db.init_db()

    monkeypatch.setattr("server._WEBHOOK_PATH", data_dir / "webhooks.json")
    monkeypatch.setattr("server._AUTO_REPORT_PATH", data_dir / "auto_report.json")
    monkeypatch.setattr("server._TOKEN_PATH", data_dir / ".api_token")

    import importlib
    import report as _report
    monkeypatch.setattr("report.REPORT_DIR", reports_dir)
    monkeypatch.setattr("report.SCREENSHOT_INTERVAL_SEC", 60)
    importlib.reload(_report)
    monkeypatch.setattr("report.REPORT_DIR", reports_dir)

    yield


# ──────────────────────────────────────────────
# db.py
# ──────────────────────────────────────────────

class TestDb:
    def test_init_db_creates_tables(self, tmp_path):
        import db
        db_path = tmp_path / "data" / "test_init.db"
        with patch("db.DB_PATH", db_path):
            db.init_db()
        assert db_path.exists()

    def test_insert_and_query_activity(self):
        import db
        db.insert_activity(
            "2026-07-05 10:00:00", "", "Code.exe", "main.py - VS Code",
            "开发", "编写代码"
        )
        rows = db.get_activities("2026-07-05", "2026-07-05")
        assert len(rows) == 1
        assert rows[0]["app_name"] == "Code.exe"
        assert rows[0]["category"] == "开发"

    def test_get_activities_date_range(self):
        import db
        db.insert_activity("2026-07-04 09:00:00", "", "WeChat.exe", "Chat", "沟通", "聊天")
        rows = db.get_activities("2026-07-05", "2026-07-05")
        assert len(rows) == 0

    def test_get_daily_summary(self):
        import db
        db.insert_activity("2026-07-05 10:00:00", "", "Code.exe", "main.py", "开发", "写代码")
        db.insert_activity("2026-07-05 11:00:00", "", "WeChat.exe", "Chat", "沟通", "聊天")
        summary = db.get_daily_summary("2026-07-05", "2026-07-05")
        assert summary["total"] == 2
        assert "开发" in summary["categories"]
        assert "沟通" in summary["categories"]

    def test_get_hourly_activity(self):
        import db
        db.insert_activity("2026-07-05 10:00:00", "", "Code.exe", "main.py", "开发", "写代码")
        db.insert_activity("2026-07-05 10:30:00", "", "Code.exe", "main.py", "开发", "写代码2")
        db.insert_activity("2026-07-05 14:00:00", "", "WeChat.exe", "Chat", "沟通", "聊天")
        hourly = db.get_hourly_activity("2026-07-05")
        assert len(hourly) == 24
        assert hourly[10]["count"] == 2
        assert hourly[14]["count"] == 1
        assert hourly[0]["count"] == 0

    def test_get_conn(self):
        import db
        with db.get_conn() as conn:
            row = conn.execute("SELECT 1 AS val").fetchone()
            assert row["val"] == 1

    def test_insert_manual_activity(self):
        import db
        db.insert_manual_activity(
            "2026-07-05 15:00:00", "Typora.exe", "README.md", "文档", "写文档", 30
        )
        rows = db.get_activities("2026-07-05", "2026-07-05")
        assert any(r["app_name"] == "Typora.exe" for r in rows)

    def test_upsert_app_usage(self):
        import db
        db.upsert_app_usage("Code.exe", "main.py", "2026-07-05 10:00:00", "2026-07-05 10:30:00")
        db.upsert_app_usage("Code.exe", "main.py", "2026-07-05 10:00:00", "2026-07-05 10:45:00")
        usage = db.get_app_usage("2026-07-05", "2026-07-05")
        code_usage = [u for u in usage if u["app_name"] == "Code.exe"]
        assert len(code_usage) == 1
        assert code_usage[0]["duration_min"] == 45.0

    def test_save_and_get_reports(self):
        import db
        db.save_report("2026-07-05", "# 日报内容")
        db.save_report("2026-07-05", "# 更新的日报内容")
        reports = db.get_reports("2026-07-05", "2026-07-05")
        assert len(reports) == 1
        assert "更新" in reports[0]["content"]


# ──────────────────────────────────────────────
# classifier.py
# ──────────────────────────────────────────────

class TestClassifier:
    def test_browsers_default_to_dev(self):
        from classifier import classify
        assert classify("chrome.exe") == "开发"
        assert classify("msedge.exe") == "开发"
        assert classify("firefox.exe") == "开发"

    def test_wechat_is_communication(self):
        from classifier import classify
        assert classify("WeChat.exe") == "沟通"

    def test_code_editors_are_dev(self):
        from classifier import classify
        assert classify("Code.exe") == "开发"
        assert classify("cursor.exe") == "开发"
        assert classify("pycharm64.exe") == "开发"

    def test_office_is_document(self):
        from classifier import classify
        assert classify("WINWORD.EXE") == "文档"
        assert classify("EXCEL.EXE") == "文档"

    def test_unknown_defaults_to_life(self):
        from classifier import classify
        assert classify("SomeRandomApp.exe") == "生活"

    def test_ai_category_direct_match(self):
        from classifier import classify
        assert classify("Unknown.exe", ai_category="开发") == "开发"

    def test_ai_category_alias(self):
        from classifier import classify
        assert classify("Unknown.exe", ai_category="软件开发") == "开发"
        assert classify("Unknown.exe", ai_category="即时通讯") == "沟通"

    def test_ai_category_keyword_match(self):
        from classifier import classify
        assert classify("Unknown.exe", ai_category="深度开发工作") == "开发"

    def test_ai_category_overrides_rule(self):
        from classifier import classify
        assert classify("WeChat.exe", ai_category="生活") == "生活"

    def test_music_is_life(self):
        from classifier import classify
        assert classify("Spotify.exe") == "生活"

    def test_teams_is_meeting(self):
        from classifier import classify
        assert classify("Teams.exe") == "会议"

    def test_figma_is_design(self):
        from classifier import classify
        assert classify("Figma.exe") == "设计"

    def test_terminal_is_dev(self):
        from classifier import classify
        assert classify("WindowsTerminal.exe") == "开发"
        assert classify("PowerShell.exe") == "开发"


# ──────────────────────────────────────────────
# config.py
# ──────────────────────────────────────────────

class TestConfig:
    def test_categories_list(self):
        from config import CATEGORIES
        assert isinstance(CATEGORIES, list)
        assert "开发" in CATEGORIES
        assert "生活" in CATEGORIES
        assert len(CATEGORIES) == 12

    def test_load_settings_defaults(self):
        from config import load_settings
        settings = load_settings()
        assert "exclude_apps" in settings
        assert "screenshot_interval_sec" in settings
        assert settings["screenshot_interval_sec"] == 60

    def test_save_and_load_settings(self, tmp_path):
        from config import SETTINGS_PATH
        settings_path = tmp_path / "data" / "settings.json"
        with patch("config.SETTINGS_PATH", settings_path):
            from config import save_settings, load_settings
            with patch("config.SETTINGS_PATH", settings_path):
                save_settings({"custom_report_instructions": "加粗标题"})
                loaded = load_settings()
                assert loaded["custom_report_instructions"] == "加粗标题"

    def test_save_settings_preserves_defaults(self, tmp_path):
        from config import save_settings, load_settings, SETTINGS_PATH
        settings_path = tmp_path / "data" / "settings.json"
        with patch("config.SETTINGS_PATH", settings_path):
            save_settings({"work_start_hour": 10})
            loaded = load_settings()
            assert loaded["work_start_hour"] == 10
            assert loaded["screenshot_interval_sec"] == 60


# ──────────────────────────────────────────────
# file_utils.py
# ──────────────────────────────────────────────

class TestFileUtils:
    def _real_backup(self):
        from file_utils import backup_file as _bf
        import file_utils as _fumod
        for attr_name in dir(_fumod):
            pass
        return _orig_backup

    def test_atomic_write_text(self, tmp_path):
        from file_utils import atomic_write_text
        target = tmp_path / "test.txt"
        atomic_write_text(target, "hello world")
        assert target.read_text(encoding="utf-8") == "hello world"

    def test_atomic_write_text_creates_dirs(self, tmp_path):
        from file_utils import atomic_write_text
        target = tmp_path / "sub" / "dir" / "test.txt"
        atomic_write_text(target, "nested")
        assert target.read_text(encoding="utf-8") == "nested"

    def test_atomic_write_bytes(self, tmp_path):
        from file_utils import atomic_write_bytes
        target = tmp_path / "test.bin"
        data = b"\x00\x01\x02\x03"
        atomic_write_bytes(target, data)
        assert target.read_bytes() == data

    def test_atomic_write_bytes_creates_dirs(self, tmp_path):
        from file_utils import atomic_write_bytes
        target = tmp_path / "deep" / "test.bin"
        atomic_write_bytes(target, b"data")
        assert target.exists()

    def test_backup_file(self, tmp_path):
        real_backup = _REAL_BACKUP_FILE
        src = tmp_path / "important.txt"
        src.write_text("original", encoding="utf-8")
        real_backup(src)
        bak = tmp_path / "backups" / "important.txt.bak.1"
        assert bak.exists()
        assert bak.read_text(encoding="utf-8") == "original"

    def test_backup_file_rolling(self, tmp_path):
        real_backup = _REAL_BACKUP_FILE
        src = tmp_path / "file.txt"
        src.write_text("v1", encoding="utf-8")
        real_backup(src)
        src.write_text("v2", encoding="utf-8")
        real_backup(src)
        bak1 = tmp_path / "backups" / "file.txt.bak.1"
        bak2 = tmp_path / "backups" / "file.txt.bak.2"
        assert bak1.read_text(encoding="utf-8") == "v2"
        assert bak2.read_text(encoding="utf-8") == "v1"

    def test_backup_file_nonexistent(self, tmp_path):
        real_backup = _REAL_BACKUP_FILE
        src = tmp_path / "nonexistent.txt"
        real_backup(src)
        assert not (tmp_path / "backups").exists() or not list((tmp_path / "backups").iterdir())


# ──────────────────────────────────────────────
# report.py
# ──────────────────────────────────────────────

class TestReport:
    def test_time_period(self):
        from report import _time_period
        assert _time_period(0) == "凌晨"
        assert _time_period(3) == "凌晨"
        assert _time_period(5) == "凌晨"
        assert _time_period(6) == "早上"
        assert _time_period(8) == "早上"
        assert _time_period(9) == "上午"
        assert _time_period(11) == "上午"
        assert _time_period(12) == "中午"
        assert _time_period(13) == "中午"
        assert _time_period(14) == "下午"
        assert _time_period(17) == "下午"
        assert _time_period(18) == "晚上"
        assert _time_period(21) == "晚上"
        assert _time_period(22) == "深夜"
        assert _time_period(23) == "深夜"

    def test_natural_overview_no_data(self):
        from report import _natural_overview
        result = _natural_overview([], [], None, None, "0s", 0)
        assert "暂无" in result

    def test_natural_overview_with_data(self):
        from report import _natural_overview
        cat_narratives = [
            {"category": "开发", "total_sec": 3600, "all_summaries": ["写代码"]},
            {"category": "沟通", "total_sec": 1800, "all_summaries": ["开会"]},
        ]
        result = _natural_overview(
            [{"category": "开发"}], cat_narratives,
            "2026-07-05 09:00:00", "2026-07-05 17:00:00",
            "4h", 3
        )
        assert "开发" in result
        assert "沟通" in result

    def test_merge_summaries_empty(self):
        from report import _merge_summaries
        assert _merge_summaries([]) == ""

    def test_merge_summaries_single(self):
        from report import _merge_summaries
        assert _merge_summaries(["写代码"]) == "写代码"

    def test_merge_summaries_two(self):
        from report import _merge_summaries
        result = _merge_summaries(["写代码", "开会"])
        assert "写代码" in result
        assert "开会" in result

    def test_merge_summaries_many(self):
        from report import _merge_summaries
        items = [f"任务{i}" for i in range(8)]
        result = _merge_summaries(items)
        assert "等" in result
        assert "项" in result


# ──────────────────────────────────────────────
# server.py — Flask test client tests
# ──────────────────────────────────────────────

@pytest.fixture()
def client():
    from server import app
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def auth_client(client):
    from server import _LOCAL_TOKEN
    from server import app

    class AuthClient:
        def __init__(self, test_client, token):
            self._client = test_client
            self._token = token

        def get(self, url, **kwargs):
            kwargs.setdefault("headers", {})
            kwargs["headers"]["X-API-Token"] = self._token
            return self._client.get(url, **kwargs)

        def post(self, url, json=None, **kwargs):
            kwargs.setdefault("headers", {})
            kwargs["headers"]["X-API-Token"] = self._token
            if json is not None:
                kwargs["json"] = json
            return self._client.post(url, **kwargs)

        def put(self, url, json=None, **kwargs):
            kwargs.setdefault("headers", {})
            kwargs["headers"]["X-API-Token"] = self._token
            if json is not None:
                kwargs["json"] = json
            return self._client.put(url, **kwargs)

        def delete(self, url, **kwargs):
            kwargs.setdefault("headers", {})
            kwargs["headers"]["X-API-Token"] = self._token
            return self._client.delete(url, **kwargs)

    return AuthClient(client, _LOCAL_TOKEN)


class TestServerHealth:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] in ("ok", "degraded")
        assert "db_ok" in data

    def test_health_no_auth_required(self, client):
        resp = client.get("/api/health")
        assert resp.status_code != 401

    def test_index(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"ChallengeDaily" in resp.data


class TestServerAuth:
    def test_protected_route_requires_token(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 401

    def test_protected_route_with_token(self, auth_client):
        resp = auth_client.get("/api/status")
        assert resp.status_code == 200

    def test_options_bypasses_auth(self, client):
        resp = client.open("/api/status", method="OPTIONS")
        assert resp.status_code != 401


class TestServerStatus:
    def test_status(self, auth_client):
        resp = auth_client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "running" in data
        assert "interval_sec" in data


class TestServerActivities:
    def test_get_activities(self, auth_client):
        import db
        db.insert_activity("2026-07-05 10:00:00", "", "Code.exe", "main.py", "开发", "写代码")
        resp = auth_client.get("/api/activities?date=2026-07-05")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["activities"]) >= 1

    def test_get_activities_invalid_date(self, auth_client):
        resp = auth_client.get("/api/activities?date=bad-date")
        assert resp.status_code == 400

    def test_create_activity(self, auth_client):
        resp = auth_client.post("/api/activities", json={
            "timestamp": "2026-07-05 14:00:00",
            "category": "开发",
            "summary": "手动补录",
            "app_name": "Manual",
        })
        assert resp.status_code == 201
        assert resp.get_json()["status"] == "ok"

    def test_create_activity_missing_fields(self, auth_client):
        resp = auth_client.post("/api/activities", json={"timestamp": "2026-07-05 14:00:00"})
        assert resp.status_code == 400

    def test_create_activity_invalid_timestamp(self, auth_client):
        resp = auth_client.post("/api/activities", json={
            "timestamp": "not-a-timestamp",
            "category": "开发",
        })
        assert resp.status_code == 400

    def test_create_activity_invalid_category(self, auth_client):
        resp = auth_client.post("/api/activities", json={
            "timestamp": "2026-07-05 14:00:00",
            "category": "不存在的分类",
        })
        assert resp.status_code == 400

    def test_update_activity(self, auth_client):
        import db
        db.insert_activity("2026-07-05 09:00:00", "", "Code.exe", "app.py", "开发", "旧摘要")
        rows = db.get_activities("2026-07-05", "2026-07-05")
        act_id = rows[-1]["id"]
        resp = auth_client.put(f"/api/activities/{act_id}", json={
            "category": "文档",
            "summary": "新摘要",
        })
        assert resp.status_code == 200

    def test_update_activity_invalid_category(self, auth_client):
        resp = auth_client.put("/api/activities/1", json={"category": "无效分类"})
        assert resp.status_code == 400

    def test_update_activity_no_fields(self, auth_client):
        resp = auth_client.put("/api/activities/1", json={})
        assert resp.status_code == 400

    def test_update_activity_not_found(self, auth_client):
        resp = auth_client.put("/api/activities/99999", json={"summary": "test"})
        assert resp.status_code == 404


class TestServerSettings:
    def test_get_settings(self, auth_client):
        resp = auth_client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "exclude_apps" in data

    def test_update_settings(self, auth_client):
        resp = auth_client.post("/api/settings", json={
            "work_start_hour": 10,
        })
        assert resp.status_code == 200
        assert resp.get_json()["settings"]["work_start_hour"] == 10

    def test_update_settings_empty_body(self, auth_client):
        resp = auth_client.post("/api/settings", json=None, headers={"X-API-Token": auth_client._token, "Content-Type": "application/json"})
        if resp.status_code == 200:
            pass
        else:
            assert resp.status_code in (200, 400)


class TestServerWebhooks:
    def test_get_webhooks_empty(self, auth_client):
        resp = auth_client.get("/api/webhooks")
        assert resp.status_code == 200
        assert resp.get_json()["webhooks"] == []

    def test_add_webhook(self, auth_client):
        resp = auth_client.post("/api/webhooks", json={
            "url": "https://hooks.example.com/webhook",
            "name": "Test Hook",
            "type": "custom",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["webhook"]["url"] == "https://hooks.example.com/webhook"

    def test_add_webhook_empty_url(self, auth_client):
        resp = auth_client.post("/api/webhooks", json={"url": ""})
        assert resp.status_code == 400

    def test_add_webhook_ssrf_localhost(self, auth_client):
        resp = auth_client.post("/api/webhooks", json={"url": "http://localhost:8080/hook"})
        assert resp.status_code == 400

    def test_add_webhook_ssrf_private_ip(self, auth_client):
        resp = auth_client.post("/api/webhooks", json={"url": "https://192.168.1.1/hook"})
        assert resp.status_code == 400

    def test_add_webhook_ssrf_127_ip(self, auth_client):
        resp = auth_client.post("/api/webhooks", json={"url": "https://127.0.0.1/hook"})
        assert resp.status_code == 400

    def test_delete_webhook(self, auth_client):
        add_resp = auth_client.post("/api/webhooks", json={
            "url": "https://hooks.example.com/delete-test",
            "name": "ToDelete",
        })
        wh_id = add_resp.get_json()["webhook"]["id"]
        del_resp = auth_client.delete(f"/api/webhooks/{wh_id}")
        assert del_resp.status_code == 200

    def test_toggle_webhook(self, auth_client):
        add_resp = auth_client.post("/api/webhooks", json={
            "url": "https://hooks.example.com/toggle-test",
        })
        wh_id = add_resp.get_json()["webhook"]["id"]
        toggle_resp = auth_client.post(f"/api/webhooks/{wh_id}/toggle")
        assert toggle_resp.status_code == 200
        assert toggle_resp.get_json()["enabled"] is False


class TestServerAutoReport:
    def test_get_auto_report_config_defaults(self, auth_client):
        resp = auth_client.get("/api/auto-report/config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "enabled" in data
        assert "auto_time" in data

    def test_update_auto_report_config(self, auth_client):
        resp = auth_client.post("/api/auto-report/config", json={
            "enabled": True,
            "auto_time": "17:30",
        })
        assert resp.status_code == 200
        assert resp.get_json()["config"]["auto_time"] == "17:30"

    def test_update_auto_report_invalid_time_format(self, auth_client):
        resp = auth_client.post("/api/auto-report/config", json={
            "auto_time": "25:00",
        })
        assert resp.status_code == 400

    def test_update_auto_report_invalid_time_string(self, auth_client):
        resp = auth_client.post("/api/auto-report/config", json={
            "auto_time": "not-a-time",
        })
        assert resp.status_code == 400


class TestServerSearch:
    def test_search_activities(self, auth_client):
        import db
        db.insert_activity("2026-07-05 10:00:00", "", "Code.exe", "my project readme", "开发", "写代码")
        resp = auth_client.get("/api/activities/search?q=project&date=2026-07-05")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["activities"]) >= 1

    def test_search_activities_empty_query(self, auth_client):
        resp = auth_client.get("/api/activities/search?q=")
        assert resp.status_code == 200
        assert resp.get_json()["activities"] == []


class TestServerBackupInfo:
    def test_backup_info(self, auth_client):
        resp = auth_client.get("/api/backup/info")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "db_size_mb" in data
        assert "activities_count" in data
        assert "reports_count" in data

    def test_backup_create(self, auth_client):
        resp = auth_client.post("/api/backup")
        assert resp.status_code == 200
        assert resp.content_type == "application/zip"


class TestServerReports:
    def test_report_daily(self, auth_client):
        import db
        db.insert_activity("2026-07-05 10:00:00", "", "Code.exe", "main.py", "开发", "写代码")
        resp = auth_client.get("/api/report/daily?date=2026-07-05")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["date"] == "2026-07-05"
        assert len(data["content"]) > 0

    def test_report_daily_invalid_date(self, auth_client):
        resp = auth_client.get("/api/report/daily?date=invalid")
        assert resp.status_code == 400


class TestServerStats:
    def test_stats_today(self, auth_client):
        resp = auth_client.get("/api/stats/today")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "date" in data
        assert "categories" in data

    def test_stats_date_invalid(self, auth_client):
        resp = auth_client.get("/api/stats/date/bad")
        assert resp.status_code == 400

    def test_stats_hourly(self, auth_client):
        resp = auth_client.get("/api/stats/hourly?date=2026-07-05")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["hours"]) == 24
