"""P59: 关键路径测试 — 安全工具 + 错误处理 + 常量验证

覆盖 P20-P58 新增的核心功能模块。
"""
import pytest
import sys
import os

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestSecurityUtils:
    """P31-P40 安全工具测试"""

    def test_validate_date_string_valid(self):
        from security_utils import validate_date_string
        assert validate_date_string("2026-07-16") == "2026-07-16"

    def test_validate_date_string_invalid_format(self):
        from security_utils import validate_date_string
        with pytest.raises(ValueError):
            validate_date_string("2026/07/16")

    def test_validate_date_string_invalid_calendar(self):
        from security_utils import validate_date_string
        with pytest.raises(ValueError):
            validate_date_string("2026-02-30")  # 2月30日不存在

    def test_validate_int_in_range(self):
        from security_utils import validate_int
        assert validate_int(5, 0, 10) == 5

    def test_validate_int_out_of_range(self):
        from security_utils import validate_int
        with pytest.raises(ValueError):
            validate_int(15, 0, 10)

    def test_validate_int_default(self):
        from security_utils import validate_int
        assert validate_int("abc", 0, 10, default=5) == 5

    def test_validate_string_length_ok(self):
        from security_utils import validate_string_length
        assert validate_string_length("hello", max_len=10) == "hello"

    def test_validate_string_length_too_long(self):
        from security_utils import validate_string_length
        with pytest.raises(ValueError):
            validate_string_length("a" * 100, max_len=10)

    def test_sanitize_html(self):
        from security_utils import sanitize_html
        result = sanitize_html('<script>alert("xss")</script>')
        assert '<script>' not in result
        assert '&lt;script&gt;' in result

    def test_redact_pii_phone(self):
        from security_utils import redact_pii
        result = redact_pii("联系我 13812345678")
        assert "13812345678" not in result
        assert "138****5678" in result

    def test_redact_pii_email(self):
        from security_utils import redact_pii
        result = redact_pii("email: user@example.com")
        assert "user@example.com" not in result

    def test_detect_sql_injection(self):
        from security_utils import detect_sql_injection
        assert detect_sql_injection("1 OR 1=1") is True
        assert detect_sql_injection("normal text") is False

    def test_rate_limit(self):
        from security_utils import _rate_limiter
        _rate_limiter._buckets.clear()
        key = "test:rate_limit"
        # 前 3 次允许
        for _ in range(3):
            assert _rate_limiter.check(key, max_requests=3, window_sec=60) is True
        # 第 4 次拒绝
        assert _rate_limiter.check(key, max_requests=3, window_sec=60) is False

    def test_generate_secure_token(self):
        from security_utils import generate_secure_token
        token = generate_secure_token()
        assert len(token) > 20
        token2 = generate_secure_token()
        assert token != token2  # 唯一性

    def test_hash_token(self):
        from security_utils import hash_token
        h1 = hash_token("test_token")
        h2 = hash_token("test_token")
        assert h1 == h2  # 确定性
        assert len(h1) == 64  # SHA-256


class TestErrorHandler:
    """P54-P55 错误处理测试"""

    def test_safe_error_message_normal(self):
        from error_handler import safe_error_message
        err = ValueError("参数缺失")
        assert "参数缺失" in safe_error_message(err)

    def test_safe_error_message_sensitive(self):
        from error_handler import safe_error_message
        err = Exception("database connection failed: password=secret123")
        msg = safe_error_message(err)
        assert "secret123" not in msg

    def test_is_infra_error_timeout(self):
        from error_handler import is_infra_error
        assert is_infra_error(TimeoutError("request timed out")) is True

    def test_is_infra_error_business(self):
        from error_handler import is_infra_error
        assert is_infra_error(ValueError("invalid input")) is False

    def test_is_business_error(self):
        from error_handler import is_business_error
        assert is_business_error(ValueError("invalid")) is True
        assert is_business_error(TimeoutError("timeout")) is False


class TestConstants:
    """P52+P57 常量验证测试"""

    def test_bloom_weights_sum_to_one(self):
        from constants import BLOOM_WEIGHTS
        total = sum(BLOOM_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Bloom 权重总和应为 1.0, 实际为 {total}"

    def test_mood_weights_sum_to_one(self):
        from constants import (
            MOOD_WEIGHT_PRODUCTIVITY, MOOD_WEIGHT_FOCUS, MOOD_WEIGHT_RHYTHM,
            MOOD_WEIGHT_VARIETY, MOOD_WEIGHT_BREAK,
        )
        total = (MOOD_WEIGHT_PRODUCTIVITY + MOOD_WEIGHT_FOCUS + MOOD_WEIGHT_RHYTHM
                 + MOOD_WEIGHT_VARIETY + MOOD_WEIGHT_BREAK)
        assert abs(total - 1.0) < 0.001, f"情绪权重总和应为 1.0, 实际为 {total}"

    def test_thresholds_positive(self):
        from constants import (
            DEEP_WORK_MIN_MINUTES, FOCUS_SESSION_MIN_MINUTES,
            DISTRACTION_LIGHT_MIN, DISTRACTION_HEAVY_MIN,
            OVERWORK_THRESHOLD_MIN,
        )
        assert DEEP_WORK_MIN_MINUTES > 0
        assert FOCUS_SESSION_MIN_MINUTES > 0
        assert DISTRACTION_LIGHT_MIN < DISTRACTION_HEAVY_MIN
        assert DISTRACTION_HEAVY_MIN < OVERWORK_THRESHOLD_MIN


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
