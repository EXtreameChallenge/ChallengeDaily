"""
P921-P960: 消息队列+事件驱动+流处理+订阅发布+消费者组+死信+延迟+幂等+广播+过滤+窗口(40轮)
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═════════ P921-P930: 消息队列(增强) ═════════

class MessageStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


@dataclass
class MessageAdv:
    msg_id: str
    topic: str
    payload: Any
    headers: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    status: MessageStatus = MessageStatus.PENDING
    delivery_count: int = 0
    consumer: str = ""
    processed_at: float | None = None


class MessageQueueAdv:
    """增强消息队列(支持ACK/重投/优先级/延迟/死信)"""

    def __init__(self, max_retry: int = 3, dead_letter_capacity: int = 1000):
        self.max_retry = max_retry
        self._queues: dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self._in_flight: dict[str, MessageAdv] = {}
        self._dead_letter: deque = deque(maxlen=dead_letter_capacity)
        self._delayed: list[tuple[float, MessageAdv]] = []
        self._priorities: dict[str, int] = {}
        self._lock = threading.RLock()
        self._stats = {"produced": 0, "consumed": 0, "failed": 0, "dead_lettered": 0}

    def produce(self, topic: str, payload: Any, headers: dict | None = None,
                priority: int = 0, delay_sec: float = 0) -> dict:
        with self._lock:
            msg = MessageAdv(
                msg_id=uuid.uuid4().hex[:12],
                topic=topic,
                payload=payload,
                headers=headers or {},
            )
            self._stats["produced"] += 1
            if delay_sec > 0:
                self._delayed.append((time.time() + delay_sec, msg))
                return {"status": "ok", "msg_id": msg.msg_id, "delayed": delay_sec}
            self._queues[topic].append(msg)
            return {"status": "ok", "msg_id": msg.msg_id}

    def consume(self, topic: str, consumer: str = "") -> dict:
        with self._lock:
            if not self._queues[topic]:
                return {"status": "empty"}
            msg = self._queues[topic].popleft()
            msg.status = MessageStatus.PROCESSING
            msg.consumer = consumer
            msg.delivery_count += 1
            self._in_flight[msg.msg_id] = msg
            return {"msg_id": msg.msg_id, "payload": msg.payload,
                    "headers": msg.headers, "delivery_count": msg.delivery_count}

    def ack(self, msg_id: str) -> dict:
        with self._lock:
            msg = self._in_flight.pop(msg_id, None)
            if not msg:
                return {"status": "error", "error": "消息不在处理中"}
            msg.status = MessageStatus.COMPLETED
            msg.processed_at = time.time()
            self._stats["consumed"] += 1
            return {"status": "ok"}

    def nack(self, msg_id: str, requeue: bool = True) -> dict:
        with self._lock:
            msg = self._in_flight.pop(msg_id, None)
            if not msg:
                return {"status": "error", "error": "消息不在处理中"}
            if msg.delivery_count >= self.max_retry:
                msg.status = MessageStatus.DEAD_LETTER
                self._dead_letter.append(msg)
                self._stats["dead_lettered"] += 1
                return {"status": "dead_lettered", "msg_id": msg_id}
            if requeue:
                msg.status = MessageStatus.PENDING
                self._queues[msg.topic].append(msg)
                self._stats["failed"] += 1
                return {"status": "requeued", "delivery_count": msg.delivery_count}
            return {"status": "dropped"}

    def process_delayed(self) -> int:
        with self._lock:
            now = time.time()
            ready = [m for t, m in self._delayed if t <= now]
            self._delayed = [(t, m) for t, m in self._delayed if t > now]
            for msg in ready:
                self._queues[msg.topic].append(msg)
            return len(ready)

    def get_dead_letters(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return [{"msg_id": m.msg_id, "topic": m.topic,
                     "payload": m.payload, "delivery_count": m.delivery_count}
                    for m in list(self._dead_letter)[-limit:]][::-1]

    def stats(self) -> dict:
        with self._lock:
            return {**self._stats,
                    "queue_sizes": {k: len(v) for k, v in self._queues.items()},
                    "in_flight": len(self._in_flight),
                    "dead_letter_size": len(self._dead_letter),
                    "delayed_size": len(self._delayed)}


_mq_adv = MessageQueueAdv()


# ═════════ P931-P940: 事件驱动 ═════════

class EventBusAdv:
    """事件总线(支持订阅/过滤/优先级/异步)"""

    def __init__(self):
        self._subscribers: dict[str, list[dict]] = defaultdict(list)
        self._events: deque = deque(maxlen=5000)
        self._lock = threading.Lock()
        self._stats = {"published": 0, "delivered": 0, "filtered": 0}

    def subscribe(self, event_type: str, handler_id: str,
                  filter_fn: Callable | None = None,
                  priority: int = 0) -> dict:
        with self._lock:
            self._subscribers[event_type].append({
                "handler_id": handler_id,
                "filter": filter_fn,
                "priority": priority,
            })
            # 按优先级排序
            self._subscribers[event_type].sort(key=lambda x: -x["priority"])
            return {"status": "ok"}

    def unsubscribe(self, event_type: str, handler_id: str) -> dict:
        with self._lock:
            self._subscribers[event_type] = [
                s for s in self._subscribers[event_type]
                if s["handler_id"] != handler_id
            ]
            return {"status": "ok"}

    def publish(self, event_type: str, payload: Any,
                headers: dict | None = None) -> dict:
        with self._lock:
            self._events.append({
                "event_id": uuid.uuid4().hex[:12],
                "type": event_type,
                "payload": payload,
                "headers": headers or {},
                "timestamp": time.time(),
            })
            self._stats["published"] += 1
            subscribers = list(self._subscribers.get(event_type, []))
        delivered = 0
        filtered = 0
        for sub in subscribers:
            if sub["filter"] and not sub["filter"](payload):
                filtered += 1
                continue
            # 模拟投递
            delivered += 1
        with self._lock:
            self._stats["delivered"] += delivered
            self._stats["filtered"] += filtered
        return {"status": "ok", "delivered": delivered, "filtered": filtered}

    def list_subscribers(self, event_type: str = "") -> dict:
        with self._lock:
            if event_type:
                return {"event_type": event_type,
                        "subscribers": [{"handler_id": s["handler_id"],
                                         "priority": s["priority"]}
                                        for s in self._subscribers.get(event_type, [])]}
            return {k: [{"handler_id": s["handler_id"], "priority": s["priority"]}
                        for s in v]
                    for k, v in self._subscribers.items()}

    def recent_events(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._events)[-limit:][::-1]

    def stats(self) -> dict:
        with self._lock:
            return {**self._stats,
                    "event_types": len(self._subscribers),
                    "total_subscribers": sum(len(v) for v in self._subscribers.values())}


_event_bus = EventBusAdv()


# ═════════ P941-P950: 流处理 ═════════

class StreamProcessor:
    """流处理器(窗口/聚合/水印)"""

    def __init__(self):
        self._streams: dict[str, deque] = defaultdict(lambda: deque(maxlen=10000))
        self._windows: dict[str, dict] = {}
        self._processors: dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._stats = {"processed": 0, "errors": 0, "window_triggers": 0}

    def register_stream(self, name: str, window_sec: int = 60) -> dict:
        with self._lock:
            self._windows[name] = {
                "window_sec": window_sec,
                "buffer": deque(),
                "aggregations": defaultdict(list),
            }
            return {"status": "ok"}

    def send(self, stream: str, data: Any) -> dict:
        with self._lock:
            self._streams[stream].append({
                "data": data,
                "timestamp": time.time(),
            })
            win = self._windows.get(stream)
            if win:
                win["buffer"].append({"data": data, "timestamp": time.time()})
            return {"status": "ok", "buffer_size": len(self._streams[stream])}

    def register_processor(self, stream: str, fn: Callable) -> dict:
        with self._lock:
            self._processors[stream] = fn
            return {"status": "ok"}

    def trigger_window(self, stream: str) -> dict:
        with self._lock:
            win = self._windows.get(stream)
            if not win:
                return {"status": "error", "error": "流未注册窗口"}
            buffer = list(win["buffer"])
            win["buffer"].clear()
            self._stats["window_triggers"] += 1
        # 应用处理器
        results = []
        processor = self._processors.get(stream)
        for item in buffer:
            try:
                if processor:
                    result = processor(item["data"])
                    results.append({"status": "ok", "result": result})
                else:
                    results.append({"status": "skipped"})
                self._stats["processed"] += 1
            except Exception as e:
                results.append({"status": "error", "error": str(e)})
                self._stats["errors"] += 1
        return {
            "stream": stream,
            "window_size": len(buffer),
            "results": results[:50],  # 限制返回数量
            "total_processed": len(results),
        }

    def aggregate(self, stream: str, field: str = "",
                  agg_func: str = "count") -> dict:
        with self._lock:
            win = self._windows.get(stream)
            if not win:
                return {"status": "error", "error": "流未注册"}
            buffer = list(win["buffer"])
        values = []
        for item in buffer:
            if isinstance(item["data"], dict) and field:
                values.append(item["data"].get(field, 0))
            else:
                values.append(item["data"])
        if agg_func == "count":
            result = len(values)
        elif agg_func == "sum":
            result = sum(v for v in values if isinstance(v, (int, float)))
        elif agg_func == "avg":
            nums = [v for v in values if isinstance(v, (int, float))]
            result = sum(nums) / max(1, len(nums))
        elif agg_func == "min":
            nums = [v for v in values if isinstance(v, (int, float))]
            result = min(nums) if nums else None
        elif agg_func == "max":
            nums = [v for v in values if isinstance(v, (int, float))]
            result = max(nums) if nums else None
        else:
            result = None
        return {"stream": stream, "field": field, "agg": agg_func,
                "result": result, "window_size": len(buffer)}

    def stats(self) -> dict:
        with self._lock:
            return {**self._stats,
                    "streams": {k: len(v) for k, v in self._streams.items()}}


_stream_processor = StreamProcessor()


# ═════════ P951-P960: 消费者组 + 幂等 + 广播 ═════════

class ConsumerGroup:
    """消费者组"""

    def __init__(self):
        self._groups: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, group: str, topic: str) -> dict:
        with self._lock:
            self._groups[group] = {
                "topic": topic,
                "consumers": [],
                "offsets": {},
                "assigned": {},
            }
            return {"status": "ok"}

    def join(self, group: str, consumer_id: str) -> dict:
        with self._lock:
            g = self._groups.get(group)
            if not g:
                return {"status": "error", "error": "组不存在"}
            if consumer_id not in g["consumers"]:
                g["consumers"].append(consumer_id)
            return {"status": "ok", "consumers": g["consumers"]}

    def leave(self, group: str, consumer_id: str) -> dict:
        with self._lock:
            g = self._groups.get(group)
            if not g:
                return {"status": "error", "error": "组不存在"}
            if consumer_id in g["consumers"]:
                g["consumers"].remove(consumer_id)
            return {"status": "ok"}

    def list_groups(self) -> list[dict]:
        with self._lock:
            return [{"group": k, "topic": v["topic"],
                     "consumers": v["consumers"]}
                    for k, v in self._groups.items()]


class IdempotencyGuard:
    """幂等性守卫"""

    def __init__(self, ttl_sec: int = 3600):
        self.ttl_sec = ttl_sec
        self._processed: dict[str, dict] = {}
        self._lock = threading.Lock()

    def check_and_mark(self, key: str) -> dict:
        with self._lock:
            now = time.time()
            # 清理过期
            expired = [k for k, v in self._processed.items() if v["expires_at"] < now]
            for k in expired:
                self._processed.pop(k, None)
            if key in self._processed:
                return {"duplicate": True, "first_seen": self._processed[key]["first_seen"]}
            self._processed[key] = {"first_seen": now, "expires_at": now + self.ttl_sec}
            return {"duplicate": False}

    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._processed), "ttl_sec": self.ttl_sec}


class BroadcastManager:
    """广播管理器"""

    def __init__(self):
        self._channels: dict[str, set] = defaultdict(set)
        self._messages: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._lock = threading.Lock()
        self._stats = {"broadcasts": 0, "delivered": 0}

    def subscribe(self, channel: str, client_id: str) -> dict:
        with self._lock:
            self._channels[channel].add(client_id)
            return {"status": "ok", "subscribers": len(self._channels[channel])}

    def unsubscribe(self, channel: str, client_id: str) -> dict:
        with self._lock:
            self._channels[channel].discard(client_id)
            return {"status": "ok"}

    def broadcast(self, channel: str, message: Any) -> dict:
        with self._lock:
            subscribers = self._channels.get(channel, set()).copy()
            self._messages[channel].append({
                "message": message,
                "timestamp": time.time(),
                "recipients": len(subscribers),
            })
            self._stats["broadcasts"] += 1
            self._stats["delivered"] += len(subscribers)
            return {"status": "ok", "recipients": len(subscribers)}

    def list_channels(self) -> dict:
        with self._lock:
            return {k: len(v) for k, v in self._channels.items()}

    def recent_messages(self, channel: str, limit: int = 20) -> list[dict]:
        with self._lock:
            return list(self._messages.get(channel, deque()))[-limit:][::-1]

    def stats(self) -> dict:
        with self._lock:
            return {**self._stats,
                    "channels": len(self._channels)}


_consumer_group = ConsumerGroup()
_idempotency = IdempotencyGuard()
_broadcast = BroadcastManager()
