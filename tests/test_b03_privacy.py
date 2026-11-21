"""
B03 隐私宣称回归（最终口径）：
- 微信/飞书/银行/支付/密码管理器：默认跳过采集；
- QQ：记录使用时长并归"沟通"，但截图不上传、不做内容分析；
- AI 客户端第二道防线拦截敏感/排除/禁止上传窗口。
"""
import config
from screenshot_redactor import should_skip_capture, is_no_upload_window


def test_b03_default_excluded_apps():
    assert config.is_app_excluded("Weixin.exe"), "微信必须在默认排除名单（内置底线）"
    assert config.is_app_excluded("Feishu.exe"), "飞书必须在默认排除名单"
    assert not config.is_app_excluded("QQ.exe"), "QQ 应记录时长，不得整窗跳过"
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
    assert not should_skip_capture("QQ - 聊天", "QQ.exe"), "QQ 记录时长，不得整窗跳过"
    assert is_no_upload_window("QQ - 聊天", "QQ.exe"), "QQ 截图禁止上传"
    assert not should_skip_capture("main.py - Visual Studio Code", "Code.exe")


def test_b03_ai_client_blocks_sensitive_window(monkeypatch):
    """第二道防线：敏感窗口直接返回空分类，不会进入上传路径。"""
    import ai_client
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    result = ai_client.analyze_screenshot("whatever.jpg", "Weixin.exe", "微信")
    assert result["category"] == ""
    assert "未上传" in result["detail"] or "跳过" in result["summary"]


def test_b03_ai_client_blocks_qq_upload(monkeypatch):
    """QQ 记录时长但截图不上传：AI 客户端返回空分类，分类交给规则（沟通）。"""
    import ai_client
    from classifier import classify
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    result = ai_client.analyze_screenshot("whatever.jpg", "QQ.exe", "QQ - 聊天")
    assert result["category"] == ""
    assert classify("QQ.exe", result["category"], "QQ - 聊天") == "沟通"


def test_b03_qq_work_record_category_is_meeting():
    """小黑工作记录里 QQ 归「会议沟通」，与采集侧「沟通」口径一致。"""
    from xiaohei_core import _classify_app
    assert _classify_app("QQ.exe") == "会议沟通"
