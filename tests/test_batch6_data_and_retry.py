"""B10/B15/B19/B35/B36 回归测试：本轮清尾巴的硬证据。"""
import base64
import json
from pathlib import Path

import pytest

import db
import friends
import offline_ai
import clipboard_monitor
import platform_integration


# ── B15: friends.py 数据完整性 ──────────────────────────

@pytest.fixture
def friends_file(tmp_path, monkeypatch):
    p = tmp_path / "friends.json"
    monkeypatch.setattr(friends, "_DATA_FILE", p)
    return p


def test_b15_send_invitation_preserves_friends_file(friends_file):
    friends.add_friend("阿泽", "aze@example.com")
    friends.send_invitation("friend-1", "todo-1", "一起做")
    raw = json.loads(friends_file.read_text(encoding="utf-8"))
    assert set(raw) == {"friends", "invitations", "sharedTodos"}
    assert len(raw["friends"]) == 1
    assert len(raw["invitations"]) == 1


def test_b15_load_normalizes_missing_or_bad_keys(friends_file):
    friends_file.write_text(json.dumps({"friends": [], "invitations": "bad"}), encoding="utf-8")
    data = friends._load()
    assert data["friends"] == []
    assert data["invitations"] == []
    assert data["sharedTodos"] == []


def test_b15_corrupt_file_is_backed_up_not_silently_overwritten(friends_file):
    friends_file.write_text("{bad json", encoding="utf-8")
    data = friends._load()
    assert data == {"friends": [], "invitations": [], "sharedTodos": []}
    backups = list(friends_file.parent.glob("friends.json.corrupt-*.bak"))
    assert backups, "损坏的 friends.json 必须先留备份"


# ── B10: 截图失败重试不再依赖已删除的原图 ───────────────

def test_b10_retry_uses_base64_and_removes_temp(monkeypatch):
    seen = {}

    def fake_analyze(path, app_name="", window_title="", **kwargs):
        p = Path(path)
        seen["exists_during_call"] = p.exists()
        seen["bytes"] = p.read_bytes()
        seen["path"] = str(p)
        return {"category": "开发", "summary": "ok"}

    monkeypatch.setattr("ai_client.analyze_screenshot", fake_analyze)
    payload = json.dumps({
        "image_b64": base64.b64encode(b"fake-image-bytes").decode(),
        "app_name": "VS Code",
        "window_title": "test.py",
    })
    assert offline_ai._retry_one("screenshot", payload) is True
    assert seen["exists_during_call"] is True
    assert seen["bytes"] == b"fake-image-bytes"
    assert not Path(seen["path"]).exists(), "重试临时截图必须用完即删"


def test_b10_old_missing_image_path_is_not_retried(monkeypatch):
    called = {"n": 0}

    def fake_analyze(*args, **kwargs):
        called["n"] += 1
        return {}

    monkeypatch.setattr("ai_client.analyze_screenshot", fake_analyze)
    payload = json.dumps({"image_path": "C:/definitely-not-exist/cd-shot.jpg"})
    assert offline_ai._retry_one("screenshot", payload) is False
    assert called["n"] == 0


def test_b10_failure_enqueues_base64_not_just_path(monkeypatch, tmp_path):
    import ai_client
    import config

    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    monkeypatch.setattr(ai_client, "_cb_check", lambda: True)
    monkeypatch.setattr(ai_client, "_rate_limit_check", lambda *args: True)
    monkeypatch.setattr(ai_client, "_get_client", lambda: object())
    captured = {}
    monkeypatch.setattr(offline_ai, "mark_ai_failure", lambda: None)
    monkeypatch.setattr(offline_ai, "enqueue_retry", lambda payload, kind: captured.update(payload=payload, kind=kind))

    img = tmp_path / "shot.jpg"
    img.write_bytes(b"fake-image")
    # 用一个会抛异常的假 client，触发最终失败分支
    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("boom")
    monkeypatch.setattr(ai_client, "_get_client", lambda: FakeClient())
    ai_client.analyze_screenshot(str(img), "VS Code", "test.py")
    expected = base64.b64encode(b"fake-image").decode()
    assert captured["kind"] == "screenshot"
    assert captured["payload"]["image_b64"] == expected


# ── B35: 年/月/周 heatmap 走范围查询 ────────────────────

def _insert(app, timestamp, interval=60, category="开发"):
    db.insert_activity(
        timestamp=timestamp,
        screenshot="",
        app_name=app,
        window_title="",
        category=category,
        summary="",
        interval_sec=interval,
    )


def test_b35_year_heatmap_has_half_open_year_bounds(authed_client, temp_db):
    _insert("Code", "2025-12-31 23:59:59", 120)
    _insert("Code", "2026-01-01 00:00:00", 300)
    _insert("Code", "2025-06-01 12:00:00", 60, category="生活")
    resp = authed_client.get("/api/stats/heatmap?range=year&date=2025-12-31")
    assert resp.status_code == 200
    data = {x["date"]: x["focus_min"] for x in resp.get_json()["data"]}
    assert data.get("2025-12-31") == 2
    assert "2026-01-01" not in data


def test_b35_week_heatmap_has_half_open_bounds(authed_client, temp_db):
    _insert("Code", "2025-12-26 00:00:00", 60)
    _insert("Code", "2026-01-01 23:59:59", 120)
    _insert("Code", "2026-01-02 00:00:00", 180)
    resp = authed_client.get("/api/stats/heatmap?range=week&date=2026-01-01")
    assert resp.status_code == 200
    data = {x["date"]: x["focus_min"] for x in resp.get_json()["data"]}
    assert data.get("2025-12-26") == 1
    assert data.get("2026-01-01") == 2
    assert "2026-01-02" not in data


# ── B36: 剪贴板入库前脱敏 ───────────────────────────────

def test_b36_clipboard_monitor_redacts_before_memory_and_history():
    clipboard_monitor._monitor = None  # 隔离单例，避免测试互相污染
    mon = clipboard_monitor.ClipboardMonitor()
    raw = "手机 13800138000 邮箱 a@b.com 身份证 110101199001011234 卡号 6222021234567890123"
    mon._handle_text(raw)
    ctx = mon.get_recent_context(1)
    assert "13800138000" not in ctx
    assert "a@b.com" not in ctx
    assert "110101199001011234" not in ctx
    assert "6222021234567890123" not in ctx


def test_b36_platform_clipboard_history_redacts_all_callers():
    platform_integration.clear_clipboard_history()
    item = platform_integration.add_clipboard_item("联系 13800138000 / a@b.com")
    assert "13800138000" not in item["content"]
    assert "a@b.com" not in item["content"]
    assert item["length"] == len("联系 13800138000 / a@b.com")


# ── B19: 自动更新 owner 口径锁 ──────────────────────────

def test_b19_auto_update_owner_matches_actual_repo():
    src = Path(__file__).resolve().parents[1] / "client" / "electron" / "main.cjs"
    text = src.read_text(encoding="utf-8")
    assert "owner: 'EXtreameChallenge'" in text
    assert "repo: 'ChallengeDaily'" in text
