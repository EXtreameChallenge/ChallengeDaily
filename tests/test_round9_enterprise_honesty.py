"""轮9 企业域诚实化回归：B22/B11/B23/B26/B29 的硬断言。"""
import json
import os

import config
from enterprise_features import telemetry
from report_channels import WeComReportChannel


def test_b22_core_endpoints_do_not_include_scaffold(authed_client):
    import routes
    import enterprise_plugin

    assert len(routes.ALL_BLUEPRINTS) == 60
    # 轮10：原 937 - 510 个 P 系列端点 + 2 个真实模板端点 = 429
    assert sum(len(bp.deferred_functions) for bp in routes.ALL_BLUEPRINTS) == 429
    assert len(enterprise_plugin.load_blueprints()) == 43

    status = authed_client.get("/api/enterprise/plugin/status").get_json()
    assert status["configured"] is False
    assert status["registered"] is False
    assert status["manifest_blueprints"] == 43
    assert status["manifest_endpoints"] == 811


def test_b22_clipboard_core_still_registered(authed_client):
    # 剪贴板 3 个端点留在 core，不能随 43 域一起移走
    resp = authed_client.get("/api/platform/clipboard")
    assert resp.status_code == 200
    assert "items" in resp.get_json()


def test_b22_plugin_registers_only_when_enabled(monkeypatch):
    from flask import Flask
    import enterprise_plugin

    monkeypatch.setenv("CHALLENGEDAILY_ENTERPRISE_PLUGIN", "1")
    app = Flask(__name__)
    status = enterprise_plugin.register(app)
    assert status["enabled"] is True
    assert status["registered"] is True
    assert status["blueprints"] == 43
    assert status["endpoints"] == 811
    assert len(app.url_map._rules) == 812  # 811 个 API 规则 + Flask 自带 static


def test_b11_enterprise_demo_modules_do_not_fake_success(authed_client):
    for path, payload in [
        ("/api/enterprise/publisher/bind", {"platform": "douyin", "account": "x"}),
        ("/api/enterprise/publisher/task", {"videoPath": "x.mp4", "platforms": ["douyin"]}),
        ("/api/enterprise/wechat/begin", {}),
        ("/api/enterprise/browser/deepseek", {"prompt": "x"}),
        ("/api/enterprise/mcp/add", {"name": "x", "command": "x"}),
        ("/api/enterprise/miniprogram/sync", {}),
        ("/api/enterprise/student/submit", {"email": "student@example.com"}),
        ("/api/enterprise/survey/submit", {"id": "x", "answers": {}}),
    ]:
        resp = authed_client.post(path, json=payload)
        data = resp.get_json()
        assert resp.status_code == 501, path
        assert data["status"] == "not_implemented", path
        assert data["implemented"] is False, path
        assert data.get("message"), path

    # 只读状态也明确标注，不把空数据伪装成真实状态
    for path in [
        "/api/enterprise/publisher/accounts",
        "/api/enterprise/wechat/state",
        "/api/enterprise/mcp/list",
        "/api/enterprise/miniprogram/status",
        "/api/enterprise/student/status",
        "/api/enterprise/festival/info",
        "/api/enterprise/survey/active",
    ]:
        data = authed_client.get(path).get_json()
        assert data["status"] == "not_implemented", path
        assert data["demo"] is True, path
        assert data["implemented"] is False, path


def test_b11_internal_demo_classes_do_not_fake_success():
    from enterprise_features import (
        publisher, wechat, browser_auto, mcp_manager, mini_sync,
        student_verification, efficiency_festival, survey_system,
    )

    assert publisher.create_task("x.mp4", ["douyin"])["ok"] is False
    assert wechat.begin_bind()["ok"] is False
    assert browser_auto.open_chatgpt("x")["ok"] is False
    assert mcp_manager.add("x", "x")["ok"] is False
    assert mini_sync.sync_now()["ok"] is False
    assert student_verification.submit("x@example.com")["verified"] is False
    assert efficiency_festival.get_info()["active"] is False
    assert survey_system.get_active()["surveys"] == []
    assert survey_system.submit("x", {})["ok"] is False


def test_b23_cv_no_random_faces_or_barcodes():
    from cv_engine import FaceDetector, BarcodeScanner, OCRExtractor

    face = FaceDetector.detect(640, 480)
    assert face["count"] == 0 and face["faces"] == []
    assert face["status"] == "not_implemented" and face["implemented"] is False

    barcode = BarcodeScanner.scan("image-1")
    assert barcode["data"] is None and barcode["type"] is None
    assert barcode["confidence"] == 0.0
    assert barcode["status"] == "not_implemented" and barcode["implemented"] is False

    ocr = OCRExtractor.extract("image-1")
    assert ocr["fields"] == {} and ocr["confidence"] == 0.0
    assert ocr["status"] == "not_implemented" and ocr["implemented"] is False


def test_b26_telemetry_default_off_and_toggle(tmp_path, monkeypatch):
    import enterprise_store
    enterprise_store.telemetry_clear()
    config.save_settings({**config.load_settings(), "telemetry_enabled": False})
    try:
        assert telemetry.track("capture_failed", {"stage": "screenshot"}) is False
        assert enterprise_store.telemetry_count() == 0

        config.save_settings({**config.load_settings(), "telemetry_enabled": True})
        assert telemetry.track("capture_failed", {"stage": "screenshot"}) is True
        events = telemetry.get_events()
        assert len(events) == 1
        assert events[0]["event"] == "capture_failed"
        assert events[0]["data"]["stage"] == "screenshot"
        assert enterprise_store.telemetry_count() == 1
    finally:
        config.save_settings({**config.load_settings(), "telemetry_enabled": False})
        enterprise_store.telemetry_clear()


def test_b29_wecom_webhook_payload_and_errcode(monkeypatch):
    captured = {}

    class FakeResponse:
        def __init__(self, body):
            self.body = body

        def read(self):
            return json.dumps(self.body).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=15):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse({"errcode": 0, "errmsg": "ok"})

    monkeypatch.setattr("report_channels.urllib.request.urlopen", fake_urlopen)
    channel = WeComReportChannel({
        "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"
    })
    result = channel.submit("今天完成了 B29", "2026-11-21")
    assert result["success"] is True
    assert result["channel"] == "wecom_report"
    assert captured["body"]["msgtype"] == "markdown"
    assert "工作日报 2026-11-21" in captured["body"]["markdown"]["content"]
    assert "今天完成了 B29" in captured["body"]["markdown"]["content"]

    # 非群机器人地址必须拒绝，避免把 webhook 配成任意 URL
    bad = WeComReportChannel({"webhook_url": "https://example.com/hook"}).submit("x")
    assert bad["success"] is False
    assert "企业微信群机器人地址" in bad["message"]
