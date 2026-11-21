"""
ChallengeDaily — 通知中心模块
完整的通知管理：列表/未读计数/标记已读/原生通知
"""
import json
import time
import uuid
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

_NOTIFICATIONS_FILE = Path.home() / ".challenge-daily" / "notifications.json"
_notifications: list[dict] = []
_load_time = 0


def _ensure_dir():
    _NOTIFICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load():
    global _notifications, _load_time
    if _notifications and time.time() - _load_time < 60:
        return
    _ensure_dir()
    if _NOTIFICATIONS_FILE.exists():
        try:
            with open(_NOTIFICATIONS_FILE, 'r', encoding='utf-8') as f:
                _notifications = json.load(f)
        except Exception:
            _notifications = []
    _load_time = time.time()


def _save():
    _ensure_dir()
    try:
        with open(_NOTIFICATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(_notifications, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"通知保存失败: {e}")


def list_notifications(limit: int = 50) -> list[dict]:
    """获取通知列表"""
    _load()
    return sorted(_notifications, key=lambda x: x.get('timestamp', 0), reverse=True)[:limit]


def unread_count() -> int:
    """未读计数"""
    _load()
    return sum(1 for n in _notifications if not n.get('read'))


def mark_read(notification_id: str):
    """标记已读"""
    _load()
    for n in _notifications:
        if n.get('id') == notification_id:
            n['read'] = True
            break
    _save()


def mark_all_read():
    """全部标记已读"""
    _load()
    for n in _notifications:
        n['read'] = True
    _save()


def add_notification(title: str, body: str, type: str = "info", data: dict = None) -> dict:
    """添加通知"""
    _load()
    notif = {
        "id": str(uuid.uuid4()),
        "title": title,
        "body": body,
        "type": type,
        "read": False,
        "timestamp": time.time(),
        "timeStr": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "data": data or {},
    }
    _notifications.insert(0, notif)
    # 只保留最近100条
    if len(_notifications) > 100:
        _notifications = _notifications[:100]
    _save()
    return notif
