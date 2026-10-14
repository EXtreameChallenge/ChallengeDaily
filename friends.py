"""
ChallengeDaily — 朋友协作模块
借鉴小黑日报助手：好友列表 / 待办分配 / 协作邀请
"""
import json
import time
import uuid
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_FILE = Path.home() / ".challenge-daily" / "friends.json"
_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)


def _load() -> dict:
    if _DATA_FILE.exists():
        try:
            return json.loads(_DATA_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {"friends": [], "invitations": [], "sharedTodos": []}


def _save(data: dict):
    _DATA_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def list_friends() -> list:
    return _load()["friends"]


def add_friend(name: str, email: str = "") -> dict:
    data = _load()
    friend = {
        "id": str(uuid.uuid4()),
        "name": name,
        "email": email,
        "addedAt": time.time(),
        "status": "pending",
    }
    data["friends"].append(friend)
    _save(data)
    return {"ok": True, "friend": friend}


def send_invitation(friend_id: str, todo_id: str, message: str = "") -> dict:
    data = _load()
    invite = {
        "id": str(uuid.uuid4()),
        "friendId": friend_id,
        "todoId": todo_id,
        "message": message,
        "status": "pending",
        "sentAt": time.time(),
    }
    data["invitations"].append(invite)
    _save(invite)
    return {"ok": True, "invitation": invite}


def list_invitations() -> list:
    return _load()["invitations"]


def accept_invitation(invite_id: str) -> dict:
    data = _load()
    for inv in data["invitations"]:
        if inv["id"] == invite_id:
            inv["status"] = "accepted"
            data["sharedTodos"].append(inv)
            break
    _save(data)
    return {"ok": True}


def list_shared_todos() -> list:
    return _load()["sharedTodos"]
