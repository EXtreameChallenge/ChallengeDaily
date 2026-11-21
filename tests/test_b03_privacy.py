"""
B03 隐私宣称回归：微信/飞书/QQ/银行/支付/密码管理器默认跳过采集；
敏感窗口同时由 AI 客户端第二道防线拦截（不上传云端）。
对应 README 宣称「微信、飞书、QQ、银行等敏感应用自动跳过」。
"""
import config
from screenshot_redactor import should_skip_capture


def test_b03_default_excluded_apps():
    assert config.is_app_excluded("Weixin.exe"), "微信必须在默认排除名单（内置底线）"
    assert config.is_app_excluded("Feishu.exe"), "飞书必须在默认排除名单"
    assert config.is_app_excluded("QQ.exe"), "QQ 必须在默认排除名单（B03 收口口径）"
    assert config.is_app_excluded("招商银行专业版.exe"), "银行类必须在默认排除名单"
    assert config.is_app_excluded("1Password.exe"), "密码管理器必须在默认排除名单"
    assert not config.is_app_excluded("Code.exe"), "普通开发应用不得被误排除"


def test_b03_user_settings_cannot_remove_privacy_floor(monkeypatch):
    monkeypatch.setattr(config, "load_settings", lambda: {"exclude_apps": ["SmokeTest"]})
    apps = config.get_exclude_apps()
    assert "SmokeTest" in apps, "用户配置应保留"
    assert any(a == "weixin" for a in apps), "内置隐私底线不得被用户配置覆盖掉"


def test_b03_should_skip_capture_rules():
    assert should_skip_capture("登录 - Chrome", "chrome.exe"), "登录页应跳过"
    assert should_skip_capture("在线支付 - 招商银行", "chrome.exe"), "支付/银行页应跳过"
    assert should_skip_capture("QQ - 聊天", "QQ.exe"), "QQ 属敏感沟通应用，应跳过"
    assert not should_skip_capture("main.py - Visual Studio Code", "Code.exe")


def test_b03_ai_client_blocks_sensitive_window(monkeypatch):
    """第二道防线：敏感窗口直接返回空分类，不会进入上传路径。"""
    import ai_client
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    result = ai_client.analyze_screenshot("whatever.jpg", "Weixin.exe", "微信")
    assert result["category"] == ""
    assert "未上传" in result["detail"] or "跳过" in result["summary"]
