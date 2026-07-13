import threading
import logging

from flask import Blueprint, jsonify
from datetime import datetime as _datetime

logger = logging.getLogger(__name__)

bp = Blueprint('notifications', __name__)

_notifications: list[dict] = []
_notifications_lock = threading.Lock()
_next_id = 1  # 单调递增，避免 ID 碰撞


def add_notification(title: str, body: str, ntype: str = "info"):
    global _next_id
    with _notifications_lock:
        _notifications.append({
            "id": _next_id,
            "title": title,
            "body": body,
            "type": ntype,
            "timestamp": _datetime.now().isoformat(),
            "read": False,
        })
        _next_id += 1
        if len(_notifications) > 50:
            _notifications[:] = _notifications[-50:]
    # 推送 SSE 事件（通知订阅者实时刷新）
    try:
        from event_bus import push_event
        push_event('notification', {"title": title, "body": body, "type": ntype})
    except Exception:
        pass


@bp.route("/api/notifications")
def get_notifications():
    with _notifications_lock:
        unread = [n for n in _notifications if not n["read"]]
        for n in unread:
            n["read"] = True
        return jsonify({"notifications": unread})
