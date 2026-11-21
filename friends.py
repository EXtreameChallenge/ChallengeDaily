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

_DEFAULT_DATA = {"friends": [], "invitations": [], "sharedTodos": []}


def _normalize(data) -> dict:
    """保证 friends.json 始终是带三个列表的字典；旧文件/半损坏文件可自愈。"""
    if not isinstance(data, dict):
        return {"friends": [], "invitations": [], "sharedTodos": []}
    for key, default in _DEFAULT_DATA.items():
        if not isinstance(data.get(key), list):
            data[key] = list(default)
    return data


def _load() -> dict:
    if _DATA_FILE.exists():
        try:
            parsed = json.loads(_DATA_FILE.read_text(encoding='utf-8'))
            if not isinstance(parsed, dict):
                raise ValueError("friends.json 顶层不是对象")
            return _normalize(parsed)
        except Exception as e:
            # 损坏文件不能静默覆盖：先留证据备份，再回默认，避免用户数据被二次写坏
            backup = _DATA_FILE.with_name(
                f"{_DATA_FILE.name}.corrupt-{int(time.time())}.bak"
            )
            try:
                _DATA_FILE.replace(backup)
                logger.warning(f"friends.json 损坏，已备份到 {backup}: {e}")
            except Exception as be:
                logger.warning(f"friends.json 损坏且备份失败: {be}")
    return {"friends": [], "invitations": [], "sharedTodos": []}


def _save(data: dict):
    """原子写：先写临时文件再 replace，避免进程中断留下半个 JSON。"""
    data = _normalize(data)
    tmp = _DATA_FILE.with_name(f"{_DATA_FILE.name}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    tmp.replace(_DATA_FILE)


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
    # B15: 这里必须保存完整 data，不能保存单个 invite；旧写法会把 friends.json 覆盖成邀请对象
    _save(data)
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
