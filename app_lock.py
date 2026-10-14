"""
ChallengeDaily — 应用锁模块（含恢复词机制）
借鉴小黑日报助手的应用锁：密码 + 恢复词双重保障
"""
import hashlib
import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path.home() / ".challenge-daily" / "app_lock.json"
_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _load() -> dict:
    if _CONFIG_FILE.exists():
        try:
            return json.loads(_CONFIG_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def _save(data: dict):
    _CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def setup_lock(password: str, recovery_word: str) -> dict:
    """设置应用锁：密码 + 恢复词"""
    data = {
        "enabled": True,
        "passwordHash": _hash(password),
        "recoveryHash": _hash(recovery_word),
        "setupAt": datetime.now().isoformat(),
        "failedAttempts": 0,
    }
    _save(data)
    return {"ok": True, "message": "应用锁已启用"}


def verify_password(password: str) -> bool:
    """验证密码"""
    data = _load()
    if not data.get("enabled"):
        return True
    if data.get("passwordHash") == _hash(password):
        data["failedAttempts"] = 0
        _save(data)
        return True
    data["failedAttempts"] = data.get("failedAttempts", 0) + 1
    _save(data)
    return False


def verify_recovery(recovery_word: str) -> dict:
    """用恢复词重置密码（小黑日报助手核心功能）"""
    data = _load()
    if not data.get("enabled"):
        return {"ok": False, "error": "应用锁未启用"}
    if data.get("recoveryHash") == _hash(recovery_word):
        return {"ok": True, "message": "恢复词验证通过，可重置密码"}
    return {"ok": False, "error": "恢复词错误"}


def reset_password(new_password: str) -> dict:
    """重置密码（需先通过恢复词验证）"""
    data = _load()
    data["passwordHash"] = _hash(new_password)
    data["failedAttempts"] = 0
    _save(data)
    return {"ok": True, "message": "密码已重置"}


def disable_lock() -> dict:
    """关闭应用锁"""
    _save({"enabled": False})
    return {"ok": True}


def get_status() -> dict:
    """获取状态"""
    data = _load()
    return {
        "enabled": data.get("enabled", False),
        "failedAttempts": data.get("failedAttempts", 0),
    }
