"""SSE 事件总线（进程内发布/订阅）

独立模块，避免 server.py ↔ routes 之间的循环导入。
- push_event(): 供任何模块调用，推送事件到所有 SSE 订阅者
- subscribe(): 供 SSE 端点调用，返回一个新订阅者队列
- unsubscribe(): 取消订阅
"""
import queue
import threading
import time
import logging

logger = logging.getLogger(__name__)

_event_subscribers: list[queue.Queue] = []
_event_lock = threading.Lock()


def push_event(event_type: str, data: dict):
    """推送事件到所有 SSE 订阅者（非阻塞，慢消费者丢弃）"""
    evt = {"type": event_type, "data": data, "timestamp": time.time()}
    with _event_lock:
        for q in _event_subscribers:
            try:
                q.put_nowait(evt)
            except queue.Full:
                # 丢弃慢消费者的事件，避免阻塞推送方
                pass


def subscribe() -> queue.Queue:
    """创建新订阅者队列（maxsize=100，超出则丢弃）"""
    q: queue.Queue = queue.Queue(maxsize=100)
    with _event_lock:
        _event_subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue):
    """取消订阅"""
    with _event_lock:
        if q in _event_subscribers:
            _event_subscribers.remove(q)


def subscriber_count() -> int:
    """当前订阅者数量"""
    with _event_lock:
        return len(_event_subscribers)
