"""B40: ActivityWatch / WakaTime / WebTracker 兼容层接口测试。"""
import base64
from datetime import datetime, timedelta

import pytest

import routes.aw_compat as aw
import routes.wakatime_compat as wk
import routes.web_tracker as wt


@pytest.fixture(autouse=True)
def reset_compat_caches(monkeypatch):
    monkeypatch.setattr(aw, "_buckets_cache", None, raising=False)
    monkeypatch.setattr(aw, "_stats_cache", None, raising=False)
    monkeypatch.setattr(wk, "_key_cache", None, raising=False)
    monkeypatch.setattr(wt, "_INITED", False, raising=False)


def test_aw_server_info_and_bucket_crud(authed_client, temp_db):
    r = authed_client.get("/api/v1/")
    assert r.status_code == 200
    assert r.get_json()["server"] == aw._AW_SERVER_ID

    r = authed_client.post("/api/v1/buckets/aw-test", json={
        "type": "window", "client": "aw-watcher-window", "hostname": "testhost"})
    assert r.status_code == 200
    assert r.get_json()["id"] == "aw-test"

    r = authed_client.get("/api/v1/buckets")
    assert r.status_code == 200
    assert "aw-test" in r.get_json()

    r = authed_client.get("/api/v1/buckets/aw-test")
    assert r.status_code == 200
    assert r.get_json()["type"] == "window"

    r = authed_client.delete("/api/v1/buckets/aw-test")
    assert r.status_code == 200
    assert r.get_json()["deleted"] == "aw-test"
    assert authed_client.get("/api/v1/buckets/aw-test").status_code == 404


def test_aw_bucket_invalid_type_and_events(authed_client, temp_db):
    r = authed_client.post("/api/v1/buckets/aw-test", json={"type": "bad"})
    assert r.status_code == 400
    r = authed_client.post("/api/v1/buckets/aw-test", json={"type": "window"})
    assert r.status_code == 200

    events = [
        {"timestamp": "2026-11-21T10:00:00Z", "duration": 60,
         "data": {"app": "Code.exe", "title": "main.py"}},
        {"timestamp": "2026-11-21T10:01:00Z", "duration": 120,
         "data": {"app": "Code.exe", "title": "main.py"}},
    ]
    r = authed_client.post("/api/v1/buckets/aw-test/events", json=events)
    assert r.status_code == 201
    assert r.get_json()["inserted"] == 2

    r = authed_client.get("/api/v1/buckets/aw-test/events?limit=10")
    assert r.status_code == 200
    assert len(r.get_json()) >= 2
    r = authed_client.get("/api/v1/buckets/aw-test/events?format=csv")
    assert r.status_code == 200
    assert "timestamp,duration" in r.get_data(as_text=True)


def test_aw_event_validation_and_heartbeat(authed_client, temp_db):
    assert authed_client.post("/api/v1/buckets/aw-test/events", data="not json").status_code == 400
    r = authed_client.post("/api/v1/buckets/aw-test/events", json={"bad": "object"})
    assert r.status_code == 201
    assert r.get_json()["inserted"] == 1

    hb = {"timestamp": "2026-11-21T11:00:00Z", "duration": 60,
          "data": {"app": "Code.exe", "title": "main.py"}}
    r = authed_client.post("/api/v1/buckets/aw-test/heartbeat", json=hb)
    assert r.status_code in (200, 201)
    # 第二次同 app/title/时间窗口 → 合并
    r2 = authed_client.post("/api/v1/buckets/aw-test/heartbeat", json=hb)
    assert r2.status_code in (200, 201)


def test_aw_optional_auth(monkeypatch, authed_client):
    monkeypatch.setattr(aw, "_AW_COMPAT_TOKEN", "secret")
    assert authed_client.get("/api/v1/").status_code == 401
    token = base64.b64encode(b"secret:").decode()
    r = authed_client.get("/api/v1/", headers={"Authorization": f"Basic {token}"})
    assert r.status_code == 200
    r = authed_client.get("/api/v1/", headers={"X-API-Token": "wrong"})
    assert r.status_code == 401


def test_aw_helpers():
    assert aw._iso_to_local_str("2026-11-21 10:00:00") == "2026-11-21 10:00:00"
    assert aw._iso_to_local_str("2026-11-21T10:00:00Z")
    assert aw._iso_to_local_str("bad")
    assert aw._bucket_type("x-afk") == aw.BUCKET_TYPE_AFK
    assert aw._bucket_type("web-browser") == aw.BUCKET_TYPE_WEB
    assert aw._bucket_type("editor-wakatime") == aw.BUCKET_TYPE_EDITOR
    assert aw._bucket_type("window") == aw.BUCKET_TYPE_WINDOW
    row = aw._event_to_activity_row({"timestamp": "2026-11-21T10:00:00Z", "duration": 0,
                                     "data": {"status": "afk"}}, aw.BUCKET_TYPE_AFK)
    assert row["app_name"] == "afk"
    row = aw._event_to_activity_row({"timestamp": "2026-11-21T10:00:00Z",
                                     "data": {"file": "x.py", "project": "p"}},
                                    aw.BUCKET_TYPE_EDITOR)
    assert row["window_title"] == "x.py"


def test_wakatime_status_key_and_heartbeat(authed_client, client, temp_db):
    status = authed_client.get("/api/wakatime/status")
    assert status.status_code == 200
    assert status.get_json()["enabled"] is True
    key = authed_client.get("/api/wakatime/key").get_json()["api_key"]
    assert len(key) == 40
    auth = "Basic " + base64.b64encode(key.encode()).decode()

    # 无 key → 401
    raw = client.application.test_client()
    assert raw.post("/api/heartbeat", json={"entity": "/tmp/a.py"}).status_code == 401
    hb = {
        "entity": "/tmp/a.py", "type": "file", "category": "coding",
        "language": "Python", "project": "demo", "branch": "main",
        "time": 1763700000,
    }
    r = raw.post(f"/api/heartbeat?api_key={key}", json=hb)
    assert r.status_code == 201
    assert r.get_json()["data"]["activity_id"] > 0
    # 第二条同 entity 在 2 分钟内 → 合并
    r2 = raw.post(f"/api/heartbeat?api_key={key}", json=hb)
    assert r2.status_code == 201
    assert r2.get_json()["status"] in ("ok", "merged")

    bulk = {"entity": "/tmp/b.py", "type": "file", "category": "coding", "time": 1763700300}
    r = raw.post(f"/api/v1/users/current/heartbeats?api_key={key}", json=[bulk, bulk])
    assert r.status_code == 201
    assert r.get_json()["summary"]["received"] >= 2


def test_wakatime_validation_and_management(authed_client, client, temp_db):
    key = authed_client.get("/api/wakatime/key").get_json()["api_key"]
    raw = client.application.test_client()
    assert raw.post(f"/api/v1/users/current/heartbeats?api_key={key}", json=[]).status_code == 201
    assert raw.post(f"/api/v1/users/current/heartbeats?api_key={key}", json="bad").status_code == 400
    assert raw.post(f"/api/heartbeat?api_key={key}", json={}).status_code == 400
    assert authed_client.post("/api/wakatime/test").status_code == 200

    before = key
    new = authed_client.post("/api/wakatime/key").get_json()["api_key"]
    assert new != before
    # 旧 key 失效
    assert raw.post(f"/api/heartbeat?api_key={before}",
                    json={"entity": "/tmp/x.py"}).status_code == 401


def test_web_tracker_endpoints(authed_client, temp_db):
    today = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    r = authed_client.post("/api/web-activity/", json={
        "url": "https://github.com/x", "domain": "github.com", "title": "repo",
        "start_time": today, "duration_sec": 60, "tab_id": 1})
    assert r.status_code == 201
    assert r.get_json()["status"] == "ok"
    r = authed_client.post("/api/web-activity/", json={"title": "no domain"})
    assert r.status_code == 400
    assert authed_client.post("/api/web-activity/", json={"domain": "bad",
                                                          "start_time": "bad"}).status_code == 201

    r = authed_client.post("/api/web-activity/batch", json={"activities": [
        {"domain": "gitee.com", "title": "code", "start_time": today, "duration_sec": 30},
        {"domain": "", "title": "bad"},
        "not-an-object",
    ]})
    assert r.status_code == 201
    body = r.get_json()
    assert body["count"] == 1
    assert len(body["errors"]) == 2

    r = authed_client.get("/api/web-activity/stats/today")
    assert r.status_code == 200
    assert r.get_json()["record_count"] >= 2
    assert r.get_json()["top_domains"]


def test_web_tracker_token_and_helpers(monkeypatch, authed_client, temp_db):
    monkeypatch.setattr(wt, "_WEB_TOKEN", "secret")
    assert authed_client.post("/api/web-activity/", json={"domain": "github.com"}).status_code == 401
    r = authed_client.post("/api/web-activity/", json={"domain": "github.com"},
                           headers={"Authorization": "Bearer secret"})
    assert r.status_code == 201
    assert wt._infer_category("github.com") == "开发"
    assert wt._infer_category("unknown.com") == "其他"
    assert wt._parse_start_time(1763700000) == datetime.fromtimestamp(1763700000).strftime("%Y-%m-%d %H:%M:%S")
    assert wt._parse_start_time("2026-11-21 10:00:00") == "2026-11-21 10:00:00"
    assert wt._parse_start_time("2026-11-21T10:00:00Z")
