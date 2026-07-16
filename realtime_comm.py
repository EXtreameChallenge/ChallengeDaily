"""
P271-P279: 实时通信系统
- P271: WebSocket 连接管理
- P272: 消息广播
- P273: 房间管理
- P274: 消息序列化
- P275: 心跳检测
- P276: 重连机制
- P277: 消息压缩
- P278: 通道复用
- P279: 实时事件总线
"""
import logging, threading, time, json, zlib
from collections import deque, defaultdict
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class WebSocketManager:
    """P271: WebSocket 连接管理"""
    def __init__(self):
        self._connections: dict[str, dict] = {}
        self._lock = threading.Lock()
    def connect(self, conn_id: str, user_id: str = "") -> None:
        with self._lock:
            self._connections[conn_id] = {"user_id": user_id, "connected_at": time.time(),
                                          "last_ping": time.time(), "rooms": set()}
    def disconnect(self, conn_id: str) -> None:
        with self._lock: self._connections.pop(conn_id, None)
    def get_connection(self, conn_id: str) -> dict | None:
        with self._lock:
            c = self._connections.get(conn_id)
            return dict(c) if c else None
    def list_connections(self) -> list[str]:
        with self._lock: return list(self._connections.keys())
    def ping(self, conn_id: str) -> None:
        with self._lock:
            if conn_id in self._connections:
                self._connections[conn_id]["last_ping"] = time.time()
    def cleanup_stale(self, timeout: int = 60) -> list[str]:
        now = time.time()
        stale = []
        with self._lock:
            for cid, conn in list(self._connections.items()):
                if now - conn["last_ping"] > timeout:
                    del self._connections[cid]
                    stale.append(cid)
        return stale

_ws_mgr = WebSocketManager()


class MessageBroadcaster:
    """P272: 消息广播"""
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
    def subscribe(self, topic: str, callback: Callable) -> None:
        with self._lock: self._subscribers[topic].append(callback)
    def unsubscribe(self, topic: str, callback: Callable) -> None:
        with self._lock:
            if topic in self._subscribers:
                self._subscribers[topic] = [cb for cb in self._subscribers[topic] if cb != callback]
    def broadcast(self, topic: str, message: dict) -> int:
        with self._lock: subs = list(self._subscribers.get(topic, []))
        for sub in subs:
            try: sub(message)
            except: pass
        return len(subs)

_broadcaster = MessageBroadcaster()


class RoomManager:
    """P273: 房间管理"""
    def __init__(self):
        self._rooms: dict[str, set[str]] = defaultdict(set)
        self._lock = threading.Lock()
    def join(self, room: str, conn_id: str) -> None:
        with self._lock: self._rooms[room].add(conn_id)
    def leave(self, room: str, conn_id: str) -> None:
        with self._lock: self._rooms[room].discard(conn_id)
    def get_members(self, room: str) -> list[str]:
        with self._lock: return list(self._rooms.get(room, set()))
    def list_rooms(self) -> dict:
        with self._lock: return {r: len(m) for r, m in self._rooms.items()}
    def broadcast_to_room(self, room: str, message: dict) -> int:
        with self._lock: members = list(self._rooms.get(room, set()))
        return len(members)

_room_mgr = RoomManager()


class MessageSerializer:
    """P274: 消息序列化"""
    @staticmethod
    def serialize(message: dict) -> str:
        return json.dumps(message, ensure_ascii=False, separators=(',', ':'))
    @staticmethod
    def deserialize(data: str) -> dict:
        try: return json.loads(data)
        except: return {}
    @staticmethod
    def serialize_batch(messages: list[dict]) -> str:
        return json.dumps(messages, ensure_ascii=False, separators=(',', ':'))

_serializer = MessageSerializer()


class HeartbeatMonitor:
    """P275: 心跳检测"""
    def __init__(self):
        self._heartbeats: dict[str, float] = {}
        self._lock = threading.Lock()
        self._interval = 30
    def beat(self, conn_id: str) -> None:
        with self._lock: self._heartbeats[conn_id] = time.time()
    def check_alive(self, conn_id: str) -> bool:
        with self._lock:
            last = self._heartbeats.get(conn_id, 0)
            return time.time() - last < self._interval * 2
    def get_stale(self) -> list[str]:
        now = time.time()
        with self._lock:
            return [cid for cid, t in self._heartbeats.items() if now - t > self._interval * 2]
    def remove(self, conn_id: str) -> None:
        with self._lock: self._heartbeats.pop(conn_id, None)

_heartbeat = HeartbeatMonitor()


class ReconnectManager:
    """P276: 重连机制"""
    def __init__(self):
        self._strategies: dict[str, dict] = {}
        self._lock = threading.Lock()
    def register(self, conn_id: str, max_retries: int = 5,
                 backoff: float = 1.0, factor: float = 2.0) -> None:
        with self._lock:
            self._strategies[conn_id] = {"retries": 0, "max": max_retries,
                                         "backoff": backoff, "factor": factor}
    def should_reconnect(self, conn_id: str) -> bool:
        with self._lock:
            s = self._strategies.get(conn_id)
            if not s: return False
            s["retries"] += 1
            return s["retries"] <= s["max"]
    def get_delay(self, conn_id: str) -> float:
        with self._lock:
            s = self._strategies.get(conn_id, {})
            return s.get("backoff", 1) * (s.get("factor", 2) ** s.get("retries", 0))
    def reset(self, conn_id: str) -> None:
        with self._lock:
            if conn_id in self._strategies: self._strategies[conn_id]["retries"] = 0

_reconnect = ReconnectManager()


class MessageCompressor:
    """P277: 消息压缩"""
    @staticmethod
    def compress(data: str) -> bytes:
        return zlib.compress(data.encode("utf-8"), level=6)
    @staticmethod
    def decompress(data: bytes) -> str:
        return zlib.decompress(data).decode("utf-8")
    @staticmethod
    def compress_json(message: dict) -> bytes:
        return zlib.compress(json.dumps(message, ensure_ascii=False).encode("utf-8"))
    @staticmethod
    def decompress_json(data: bytes) -> dict:
        try: return json.loads(zlib.decompress(data).decode("utf-8"))
        except: return {}

_compressor = MessageCompressor()


class ChannelMultiplexer:
    """P278: 通道复用"""
    def __init__(self):
        self._channels: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self._lock = threading.Lock()
    def send(self, channel: str, data: dict) -> None:
        with self._lock: self._channels[channel].append({"data": data, "ts": time.time()})
    def recv(self, channel: str) -> dict | None:
        with self._lock:
            if self._channels[channel]:
                return self._channels[channel].popleft()
            return None
    def list_channels(self) -> dict:
        with self._lock: return {ch: len(q) for ch, q in self._channels.items()}

_mux = ChannelMultiplexer()


class EventBus:
    """P279: 实时事件总线"""
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._event_log: deque = deque(maxlen=1000)
        self._lock = threading.Lock()
    def on(self, event: str, handler: Callable) -> None:
        with self._lock: self._handlers[event].append(handler)
    def emit(self, event: str, data: dict = None) -> int:
        entry = {"event": event, "data": data or {}, "timestamp": datetime.now().isoformat()}
        with self._lock:
            self._event_log.append(entry)
            handlers = list(self._handlers.get(event, []))
        for h in handlers:
            try: h(data or {})
            except: pass
        return len(handlers)
    def get_recent_events(self, limit: int = 50) -> list[dict]:
        with self._lock: return list(self._event_log)[-limit:]
    def get_handlers(self, event: str = "") -> dict:
        with self._lock:
            if event: return {event: len(self._handlers.get(event, []))}
            return {e: len(h) for e, h in self._handlers.items()}

_event_bus = EventBus()
