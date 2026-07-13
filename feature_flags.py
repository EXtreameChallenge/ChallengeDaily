"""Feature Flag 框架（简单 JSON 配置 + 缓存）"""
import json
import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_flags = {}
_flags_lock = threading.Lock()
_flags_loaded_at = 0
_FLAGS_TTL_SEC = 300  # 5 分钟重新加载一次

# 默认 flag 定义
DEFAULT_FLAGS = {
    "ai_stream_chat": True,           # AI 流式对话
    "deep_insight": True,             # 深度洞察
    "auto_report": True,              # 自动日报
    "screenshot_redaction": False,    # 截屏脱敏（默认关，Phase 3 已实现）
    "circuit_breaker": True,          # 熔断器
    "token_rotation": True,           # Token 30 天轮换
    "rate_limiting": True,            # Rate Limiting
    "privacy_apps_filter": False,     # 隐私应用过滤
    "structured_logging": False,      # 结构化日志（默认关，保持兼容）
    "db_consistency_check": True,     # 数据库一致性校验
    "auto_backup": True,              # 自动备份
}

def _load_flags():
    """从 settings 表加载 flag（失败用默认值）"""
    global _flags, _flags_loaded_at
    now = time.time()
    if _flags and now - _flags_loaded_at < _FLAGS_TTL_SEC:
        return
    loaded = dict(DEFAULT_FLAGS)
    try:
        import db
        with db.get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='feature_flags'").fetchone()
            if row:
                user_flags = json.loads(row[0])
                loaded.update(user_flags)
    except Exception as e:
        logger.debug(f"加载 feature flags 失败，用默认值: {e}")
    with _flags_lock:
        _flags = loaded
        _flags_loaded_at = now

def is_enabled(flag_name: str, default: bool = False) -> bool:
    """检查 flag 是否启用"""
    _load_flags()
    with _flags_lock:
        return _flags.get(flag_name, default)

def get_all_flags() -> dict:
    """获取所有 flag"""
    _load_flags()
    with _flags_lock:
        return dict(_flags)

def set_flag(flag_name: str, enabled: bool):
    """设置单个 flag"""
    _load_flags()
    with _flags_lock:
        _flags[flag_name] = enabled
    try:
        import db
        with db.get_conn() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('feature_flags', ?)",
                        (json.dumps(_flags, ensure_ascii=False),))
    except Exception as e:
        logger.error(f"保存 feature flag 失败: {e}")
