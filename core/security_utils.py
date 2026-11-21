"""P31-P40: 安全工具集 — 输入验证、速率限制、PII 脱敏

集中管理安全相关功能，避免分散在各路由中重复实现。
"""
import hashlib
import logging
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from functools import wraps
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── P31: 输入验证框架 ──

_VALID_CATEGORIES = {
    "开发", "学习", "会议", "文档", "测试", "设计",
    "沟通", "休息", "娱乐", "社交", "生活", "其他",
    "工作", "摸鱼", "专注",
}


def validate_date_string(s: Any) -> str:
    """验证日期字符串格式 YYYY-MM-DD，并检查是否为有效日历日期"""
    if not s or not isinstance(s, str):
        raise ValueError("日期必须为非空字符串")
    s = s.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        raise ValueError(f"日期格式应为 YYYY-MM-DD，得到: {s}")
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"无效日历日期: {s}")
    return s


def validate_int(v: Any, min_val: int = 0, max_val: int = 10**9, default: Optional[int] = None) -> int:
    """验证整数范围"""
    try:
        n = int(v)
    except (ValueError, TypeError):
        if default is not None:
            return default
        raise ValueError(f"期望整数，得到: {type(v).__name__}")
    if n < min_val or n > max_val:
        if default is not None:
            return default
        raise ValueError(f"整数 {n} 超出范围 [{min_val}, {max_val}]")
    return n


def validate_string_length(s: Any, max_len: int = 1000, field_name: str = "input") -> str:
    """验证字符串长度"""
    if not isinstance(s, str):
        s = str(s) if s is not None else ""
    s = s.strip()
    if len(s) > max_len:
        raise ValueError(f"{field_name} 长度超限 ({len(s)} > {max_len})")
    return s


def validate_category(cat: Any) -> str:
    """验证分类值在允许的枚举内"""
    cat = validate_string_length(cat, max_len=20, field_name="category")
    if cat and cat not in _VALID_CATEGORIES:
        # 不强制拒绝，但记录警告
        logger.debug(f"非标准分类值: {cat}")
    return cat or "其他"


def sanitize_html(text: str) -> str:
    """P36: 基础 HTML 转义，防止 XSS"""
    if not text:
        return ""
    text = str(text)
    replacements = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#x27;",
        "/": "&#x2F;",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


# ── P32: API 速率限制 ──

class RateLimiter:
    """滑动窗口速率限制器"""

    def __init__(self):
        self._buckets: dict[str, deque] = defaultdict(lambda: deque())
        self._lock = threading.Lock()

    def check(self, key: str, max_requests: int, window_sec: float) -> bool:
        """检查是否允许请求。返回 True 表示允许，False 表示超限"""
        now = time.time()
        cutoff = now - window_sec
        with self._lock:
            bucket = self._buckets[key]
            # 清理过期记录
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= max_requests:
                return False
            bucket.append(now)
            return True

    def cleanup(self, max_age_sec: float = 3600):
        """清理过期的桶"""
        now = time.time()
        with self._lock:
            stale_keys = [
                k for k, v in self._buckets.items()
                if not v or (v and v[0] < now - max_age_sec)
            ]
            for k in stale_keys:
                del self._buckets[k]


_rate_limiter = RateLimiter()


def rate_limit(max_requests: int = 60, window_sec: float = 60, key_prefix: str = ""):
    """P32: 速率限制装饰器

    用法：
        @bp.route('/api/something')
        @rate_limit(max_requests=10, window_sec=60)
        def handler():
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            from flask import request, jsonify
            # 以 IP + endpoint 为 key
            client_ip = request.remote_addr or "unknown"
            endpoint = key_prefix or f.__name__
            rate_key = f"{client_ip}:{endpoint}"
            if not _rate_limiter.check(rate_key, max_requests, window_sec):
                logger.warning(f"速率限制触发: {rate_key} ({max_requests}/{window_sec}s)")
                return jsonify({
                    "error": "请求过于频繁，请稍后再试",
                    "retry_after": int(window_sec),
                }), 429
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ── P40: PII 脱敏 ──

_PII_PATTERNS = [
    # 手机号
    (re.compile(r"1[3-9]\d{9}"), lambda m: m.group()[:3] + "****" + m.group()[-4:]),
    # 邮箱
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), lambda m: m.group()[:2] + "***@" + m.group().split("@")[1]),
    # 身份证号
    (re.compile(r"\d{17}[\dXx]"), lambda m: m.group()[:6] + "********" + m.group()[-4:]),
    # 银行卡号
    (re.compile(r"\d{16,19}"), lambda m: m.group()[:4] + "****" + m.group()[-4:]),
]


def redact_pii(text: str) -> str:
    """P40: 脱敏文本中的 PII（手机号/邮箱/身份证/银行卡）"""
    if not text:
        return text
    result = str(text)
    for pattern, replacement in _PII_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def safe_log(message: str, level: int = logging.INFO, *args, **kwargs):
    """P40: 安全日志记录（自动脱敏 PII）"""
    redacted = redact_pii(message)
    logger.log(level, redacted, *args, **kwargs)


# ── P34: Token 安全工具 ──

def generate_secure_token(length: int = 32) -> str:
    """生成密码学安全的随机 token"""
    import secrets
    return secrets.token_urlsafe(length)


def hash_token(token: str) -> str:
    """Token 哈希存储（不存明文）"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── P35: SQL 注入检测 ──

_SQL_INJECTION_PATTERNS = [
    re.compile(r"(\b(OR|AND)\b\s+\d+\s*=\s*\d+)", re.IGNORECASE),
    re.compile(r"(--|;|/\*|\*/)", re.IGNORECASE),
    re.compile(r"(\b(UNION|SELECT|INSERT|DELETE|DROP|UPDATE)\b\s+.+\b(FROM|INTO|SET)\b)", re.IGNORECASE),
]


def detect_sql_injection(input_str: str) -> bool:
    """P35: 检测输入中可能的 SQL 注入模式"""
    if not input_str or not isinstance(input_str, str):
        return False
    for pattern in _SQL_INJECTION_PATTERNS:
        if pattern.search(input_str):
            logger.warning(f"疑似 SQL 注入输入: {input_str[:50]}")
            return True
    return False
