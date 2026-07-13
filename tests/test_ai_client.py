"""
AI 客户端测试

覆盖：
- _validate_ai_response 白名单字段保留，其他丢弃
- 熔断器 closed 状态放行
- 熔断器 open 状态拒绝
- 熔断器 half_open 恢复
"""
import time
import pytest

import ai_client


# ── 每个测试前后重置熔断器状态 ──

@pytest.fixture(autouse=True)
def _reset_circuit_breaker():
    ai_client._cb_state = "closed"
    ai_client._cb_consecutive_failures = 0
    ai_client._cb_opened_at = 0.0
    ai_client._cb_half_open_tries = 0
    ai_client._cb_cooldown_sec = ai_client._CB_COOLDOWN_INIT_SEC
    yield
    ai_client._cb_state = "closed"
    ai_client._cb_consecutive_failures = 0
    ai_client._cb_opened_at = 0.0
    ai_client._cb_half_open_tries = 0
    ai_client._cb_cooldown_sec = ai_client._CB_COOLDOWN_INIT_SEC


# ── 白名单校验 ──

def test_validate_ai_response_whitelist():
    """白名单字段保留，其他丢弃"""
    data = {
        "category": "开发",
        "summary": "编写代码",
        "detail": "正在修改 auth 模块",
        "windows": [{"app_name": "code.exe"}],
        # 以下字段应被丢弃
        "malicious_field": "evil",
        "exec_command": "rm -rf /",
        "system_prompt_leak": "你是一个...",
    }
    result = ai_client._validate_ai_response(data)

    # 白名单字段保留
    assert "category" in result
    assert "summary" in result
    assert "detail" in result
    assert "windows" in result

    # 非白名单字段被丢弃
    assert "malicious_field" not in result
    assert "exec_command" not in result
    assert "system_prompt_leak" not in result


# ── 熔断器 closed 状态 ──

def test_circuit_breaker_closed_state():
    """正常状态（closed）放行请求"""
    ai_client._cb_state = "closed"
    assert ai_client._cb_check() is True


# ── 熔断器 open 状态 ──

def test_circuit_breaker_open_state():
    """熔断后（open）拒绝请求"""
    ai_client._cb_state = "open"
    ai_client._cb_opened_at = time.monotonic()  # 刚刚熔断
    ai_client._cb_cooldown_sec = 60  # 60 秒冷却
    assert ai_client._cb_check() is False


# ── 熔断器 half_open 恢复 ──

def test_circuit_breaker_half_open_recovery():
    """半开状态允许试探请求，成功后恢复为 closed"""
    ai_client._cb_state = "half_open"
    ai_client._cb_half_open_tries = 0

    # 半开状态允许试探请求通过
    assert ai_client._cb_check() is True

    # 记录一次成功 → 状态恢复为 closed
    ai_client._cb_record_success()
    assert ai_client._cb_state == "closed"
    assert ai_client._cb_consecutive_failures == 0
