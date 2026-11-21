"""ChallengeDaily — 朋友协作模块（轮10 单源：SQLite enterprise_kv）

历史 `friends.json` 由 `enterprise_store.migrate_home_data()` 迁移后归档；
运行期不再读写 home JSON。
"""
import time
import uuid
import logging

import enterprise_store

logger = logging.getLogger(__name__)

_DEFAULT_DATA = {"friends": [], "invitations": [], "sharedTodos": []}


def _normalize(data) -> dict:
    """保证结构始终是带三个列表的字典；旧数据/半损坏数据可自愈。"""
    if not isinstance(data, dict):
        return {"friends": [], "invitations": [], "sharedTodos": []}
    for key, default in _DEFAULT_DATA.items():
        if not isinstance(data.get(key), list):
            data[key] = list(default)
    return data


def _load() -> dict:
    payload = enterprise_store.kv_get_json(enterprise_store.KV_FRIENDS, None)
    if payload is None:
        return {"friends": [], "invitations": [], "sharedTodos": []}
    return _normalize(payload)


def _save(data: dict):
    enterprise_store.kv_set_json(enterprise_store.KV_FRIENDS, _normalize(data))


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
    # B15: 必须保存完整 data，不能只保存单个 invite
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
