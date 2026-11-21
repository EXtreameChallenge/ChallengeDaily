"""
P241-P249: 协作系统
- P241: 用户会话管理
- P242: 实时协作通道
- P243: 操作转换(OT)
- P244: 冲突解决
- P245: 权限控制
- P246: 评论系统
- P247: 版本历史
- P248: 在线状态
- P249: 协作统计
"""
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P241: 用户会话管理 ──────────────────────────
class SessionManager:
    """协作用户会话"""
    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, user_id: str, room_id: str = "") -> str:
        import uuid
        session_id = str(uuid.uuid4())[:8]
        with self._lock:
            self._sessions[session_id] = {
                "user_id": user_id, "room_id": room_id,
                "created_at": time.time(), "last_active": time.time(),
                "active": True
            }
        return session_id

    def touch(self, session_id: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id]["last_active"] = time.time()

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            s = self._sessions.get(session_id)
            return dict(s) if s else None

    def list_active(self, room_id: str = "") -> list[dict]:
        now = time.time()
        with self._lock:
            sessions = [dict(s) for s in self._sessions.values()
                        if s["active"] and now - s["last_active"] < 300]
        if room_id:
            sessions = [s for s in sessions if s["room_id"] == room_id]
        return sessions

    def destroy(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


_sessions = SessionManager()


# ─── P242: 实时协作通道 ──────────────────────────
class CollaborationChannel:
    """实时协作消息通道"""
    def __init__(self):
        self._channels: dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.Lock()

    def publish(self, channel: str, message: dict) -> None:
        message["timestamp"] = datetime.now().isoformat()
        with self._lock:
            self._channels[channel].append(message)
            subscribers = list(self._subscribers.get(channel, []))
        for sub in subscribers:
            try:
                sub(message)
            except Exception:
                pass

    def subscribe(self, channel: str, callback: Callable) -> None:
        with self._lock:
            self._subscribers[channel].append(callback)

    def get_history(self, channel: str, limit: int = 50) -> list[dict]:
        with self._lock:
            msgs = list(self._channels.get(channel, []))
        return msgs[-limit:]

    def list_channels(self) -> list[str]:
        with self._lock:
            return list(self._channels.keys())


_channel = CollaborationChannel()


# ─── P243: 操作转换(OT) ──────────────────────────
class OperationalTransform:
    """简单操作转换"""
    @staticmethod
    def transform(op1: dict, op2: dict) -> dict:
        """转换两个并发操作"""
        if op1.get("type") != "insert" or op2.get("type") != "insert":
            return op2
        if op1["position"] < op2["position"]:
            return {**op2, "position": op2["position"] + len(op1.get("text", ""))}
        elif op1["position"] == op2["position"]:
            # 用用户ID作为tiebreaker
            if op1.get("user_id", "") < op2.get("user_id", ""):
                return {**op2, "position": op2["position"] + len(op1.get("text", ""))}
        return op2

    @staticmethod
    def apply(text: str, op: dict) -> str:
        if op["type"] == "insert":
            pos = min(op["position"], len(text))
            return text[:pos] + op.get("text", "") + text[pos:]
        elif op["type"] == "delete":
            pos = min(op["position"], len(text))
            length = min(op.get("length", 0), len(text) - pos)
            return text[:pos] + text[pos + length:]
        return text


# ─── P244: 冲突解决 ──────────────────────────
class ConflictResolver:
    """冲突解决策略"""
    STRATEGIES = ["last_write_wins", "first_write_wins", "merge", "manual"]

    @staticmethod
    def resolve(conflicts: list[dict], strategy: str = "last_write_wins") -> dict:
        if not conflicts:
            return {}
        if strategy == "last_write_wins":
            return max(conflicts, key=lambda x: x.get("timestamp", ""))
        elif strategy == "first_write_wins":
            return min(conflicts, key=lambda x: x.get("timestamp", ""))
        elif strategy == "merge":
            merged = {}
            for c in conflicts:
                merged.update(c.get("data", {}))
            return {"data": merged, "strategy": "merge"}
        return {"status": "manual_required", "conflicts": conflicts}


# ─── P245: 权限控制 ──────────────────────────
class CollaborationPermission:
    """协作权限"""
    PERMISSIONS = {
        "owner": ["read", "write", "delete", "share", "admin"],
        "editor": ["read", "write"],
        "commenter": ["read", "comment"],
        "viewer": ["read"],
    }

    def __init__(self):
        self._user_roles: dict[str, dict[str, str]] = defaultdict(dict)  # {room: {user: role}}
        self._lock = threading.Lock()

    def assign_role(self, room_id: str, user_id: str, role: str) -> None:
        with self._lock:
            self._user_roles[room_id][user_id] = role

    def check_permission(self, room_id: str, user_id: str, action: str) -> bool:
        with self._lock:
            role = self._user_roles.get(room_id, {}).get(user_id, "viewer")
        return action in self.PERMISSIONS.get(role, ["read"])

    def get_user_role(self, room_id: str, user_id: str) -> str:
        with self._lock:
            return self._user_roles.get(room_id, {}).get(user_id, "viewer")

    def list_room_users(self, room_id: str) -> dict:
        with self._lock:
            return dict(self._user_roles.get(room_id, {}))


_permissions = CollaborationPermission()


# ─── P246: 评论系统 ──────────────────────────
class CommentSystem:
    """协作评论"""
    def __init__(self):
        self._comments: dict[str, list[dict]] = defaultdict(list)
        self._lock = threading.Lock()

    def add(self, target_id: str, user_id: str, content: str,
            parent_id: str = "") -> dict:
        import uuid
        comment = {
            "id": str(uuid.uuid4())[:8],
            "target_id": target_id, "user_id": user_id,
            "content": content, "parent_id": parent_id,
            "timestamp": datetime.now().isoformat(),
            "resolved": False
        }
        with self._lock:
            self._comments[target_id].append(comment)
        return comment

    def resolve(self, target_id: str, comment_id: str) -> bool:
        with self._lock:
            for c in self._comments.get(target_id, []):
                if c["id"] == comment_id:
                    c["resolved"] = True
                    return True
            return False

    def get(self, target_id: str) -> list[dict]:
        with self._lock:
            return list(self._comments.get(target_id, []))


_comments = CommentSystem()


# ─── P247: 版本历史 ──────────────────────────
class VersionHistory:
    """文档版本历史"""
    def __init__(self):
        self._versions: dict[str, list[dict]] = defaultdict(list)
        self._lock = threading.Lock()

    def save_version(self, doc_id: str, content: str,
                     user_id: str = "", message: str = "") -> dict:
        with self._lock:
            version_num = len(self._versions[doc_id]) + 1
            version = {
                "version": version_num, "content": content,
                "user_id": user_id, "message": message,
                "timestamp": datetime.now().isoformat(),
                "size": len(content)
            }
            self._versions[doc_id].append(version)
        return version

    def get_version(self, doc_id: str, version: int) -> dict | None:
        with self._lock:
            versions = self._versions.get(doc_id, [])
            for v in versions:
                if v["version"] == version:
                    return v
            return None

    def get_history(self, doc_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            versions = list(self._versions.get(doc_id, []))
        versions.reverse()
        return versions[:limit]

    def diff(self, doc_id: str, v1: int, v2: int) -> dict:
        ver1 = self.get_version(doc_id, v1)
        ver2 = self.get_version(doc_id, v2)
        if not ver1 or not ver2:
            return {"error": "版本不存在"}
        c1, c2 = ver1["content"], ver2["content"]
        import difflib
        diff = list(difflib.unified_diff(
            c1.splitlines(keepends=True),
            c2.splitlines(keepends=True),
            fromfile=f"v{v1}", tofile=f"v{v2}"
        ))
        return {"diff": "".join(diff), "added": len(c2) - len(c1)}


_versions = VersionHistory()


# ─── P248: 在线状态 ──────────────────────────
class PresenceTracker:
    """用户在线状态"""
    def __init__(self):
        self._presence: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set_online(self, user_id: str, status: str = "online") -> None:
        with self._lock:
            self._presence[user_id] = {
                "status": status, "last_seen": time.time(),
                "is_online": True
            }

    def set_offline(self, user_id: str) -> None:
        with self._lock:
            if user_id in self._presence:
                self._presence[user_id]["is_online"] = False
                self._presence[user_id]["last_seen"] = time.time()

    def get_presence(self, user_id: str) -> dict | None:
        with self._lock:
            p = self._presence.get(user_id)
            if not p:
                return None
            # 5分钟无活动视为离线
            if p["is_online"] and time.time() - p["last_seen"] > 300:
                p["is_online"] = False
            return dict(p)

    def get_online_users(self) -> list[str]:
        now = time.time()
        with self._lock:
            return [uid for uid, p in self._presence.items()
                    if p["is_online"] and now - p["last_seen"] < 300]


_presence = PresenceTracker()


# ─── P249: 协作统计 ──────────────────────────
class CollaborationStats:
    """协作数据统计"""
    def __init__(self):
        self._events: deque = deque(maxlen=5000)
        self._lock = threading.Lock()

    def record(self, event_type: str, user_id: str,
               room_id: str = "", metadata: dict = None) -> None:
        with self._lock:
            self._events.append({
                "type": event_type, "user_id": user_id,
                "room_id": room_id, "metadata": metadata or {},
                "timestamp": datetime.now().isoformat()
            })

    def get_stats(self, room_id: str = "") -> dict:
        with self._lock:
            events = list(self._events)
        if room_id:
            events = [e for e in events if e["room_id"] == room_id]
        from collections import Counter
        type_counts = Counter(e["type"] for e in events)
        user_counts = Counter(e["user_id"] for e in events)
        return {
            "total_events": len(events),
            "by_type": dict(type_counts),
            "by_user": dict(user_counts.most_common(10)),
            "unique_users": len(user_counts)
        }


_collab_stats = CollaborationStats()
