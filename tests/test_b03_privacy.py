"""
隐私口径回归（2026-11-21 重大变更）：「自用全量模式」为默认。

- 默认不排除任何应用、不跳过任何窗口、不上传拦截关闭；全量采集与分析。
- 隐私机制保留为可配置开关：privacy_skip_capture / privacy_block_upload / privacy_redact。
- QQ 全量记录，分类交给 AI + 规则（规则口径：沟通 / 工作记录归会议沟通）。
"""
import config
from screenshot_redactor import should_skip_capture, is_no_upload_window


def test_full_mode_defaults():
    assert config.get_exclude_apps() == [], "默认排除名单应为空（全量采集）"
    assert config.is_app_excluded("Weixin.exe") is False
    assert config.is_app_excluded("招商银行专业版.exe") is False
    assert config.is_privacy_skip_enabled() is False
    assert config.is_privacy_block_upload_enabled() is False
    assert config.is_privacy_redact_enabled() is False


def test_privacy_switches_can_be_enabled(monkeypatch):
    """机制保留：开启开关后，旧的保守行为仍可用。"""
    import ai_client
    monkeypatch.setattr(config, "load_settings", lambda: {
        "privacy_skip_capture": True,
        "privacy_block_upload": True,
        "privacy_redact": True,
        "exclude_apps": ["SmokeTest"],
    })
    assert should_skip_capture("微信 - 聊天", "Weixin.exe") is True
    assert config.is_privacy_skip_enabled() is True

    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    result = ai_client.analyze_screenshot("whatever.jpg", "Weixin.exe", "微信")
    assert result["category"] == ""
    assert "未上传" in result["detail"] or "跳过" in result["summary"]


def test_privacy_gate_off_by_default_does_not_skip():
    """机制仍能识别敏感窗口，但默认开关关闭，采集层不会因此跳过。"""
    assert should_skip_capture("微信 - 聊天", "Weixin.exe") is True
    assert (config.is_privacy_skip_enabled()
            and should_skip_capture("微信 - 聊天", "Weixin.exe")) is False


def test_user_exclude_list_still_works(monkeypatch):
    """用户显式配置的排除项依然生效（全量模式不等于禁用配置）。"""
    monkeypatch.setattr(config, "load_settings", lambda: {"exclude_apps": ["SmokeTest"]})
    assert config.get_exclude_apps() == ["SmokeTest"]
    assert config.is_app_excluded("SmokeTest.exe") is True


def test_qq_full_record_and_category():
    """QQ 全量记录；AI 关闭上传拦截时正常分析，分类规则归沟通。"""
    from classifier import classify
    from xiaohei_core import _classify_app
    assert classify("QQ.exe", "", "QQ - 聊天") == "沟通"
    assert _classify_app("QQ.exe") == "会议沟通"
    assert is_no_upload_window("QQ - 聊天", "QQ.exe") is True  # 机制保留，可随开关启用
