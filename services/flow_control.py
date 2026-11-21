"""
P801-P840: 流量控制+限流+熔断+降级+背压+重试+超时+隔舱+漏桶+令牌桶+滑动窗口+并发控制(40轮)
"""
from __future__ import annotations

import logging
import hashlib
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═════════ P801-P810: 限流器 ═════════

class TokenBucket:
    """令牌桶限流"""

    def __init__(self, capacity: int = 100, refill_rate: float = 10.0):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self._tokens = float(capacity)
        self._last = time.time()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> dict:
        with self._lock:
            now = time.time()
            elapsed = now - self._last
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
            self._last = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return {"allowed": True, "tokens_left": round(self._tokens, 2)}
            return {"allowed": False, "tokens_left": round(self._tokens, 2),
                    "retry_after": round((tokens - self._tokens) / self.refill_rate, 2)}


class LeakyBucket:
    """漏桶限流"""

    def __init__(self, capacity: int = 100, leak_rate: float = 10.0):
        self.capacity = capacity
        self.leak_rate = leak_rate
        self._water = 0.0
        self._last = time.time()
        self._lock = threading.Lock()

    def pour(self, amount: int = 1) -> dict:
        with self._lock:
            now = time.time()
            elapsed = now - self._last
            self._water = max(0, self._water - elapsed * self.leak_rate)
            self._last = now
            if self._water + amount <= self.capacity:
                self._water += amount
                return {"allowed": True, "water": round(self._water, 2)}
            return {"allowed": False, "water": round(self._water, 2),
                    "capacity": self.capacity}


class SlidingWindow:
    """滑动窗口限流"""

    def __init__(self, max_requests: int = 100, window_sec: int = 60):
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._requests: dict[str, deque] = defaultdict(lambda: deque())
        self._lock = threading.Lock()

    def check(self, key: str) -> dict:
        with self._lock:
            now = time.time()
            reqs = self._requests[key]
            while reqs and reqs[0] < now - self.window_sec:
                reqs.popleft()
            if len(reqs) < self.max_requests:
                reqs.append(now)
                return {"allowed": True, "count": len(reqs),
                        "limit": self.max_requests}
            return {"allowed": False, "count": len(reqs),
                    "limit": self.max_requests,
                    "retry_after": int(reqs[0] + self.window_sec - now)}


class FixedWindow:
    """固定窗口限流"""

    def __init__(self, max_requests: int = 100, window_sec: int = 60):
        self.max_requests = max_requests
        self.window_sec = window_sec
        self._windows: dict[str, dict] = defaultdict(lambda: {"count": 0, "start": time.time()})
        self._lock = threading.Lock()

    def check(self, key: str) -> dict:
        with self._lock:
            now = time.time()
            win = self._windows[key]
            if now - win["start"] >= self.window_sec:
                win["count"] = 0
                win["start"] = now
            if win["count"] < self.max_requests:
                win["count"] += 1
                return {"allowed": True, "count": win["count"]}
            return {"allowed": False, "count": win["count"],
                    "reset_at": win["start"] + self.window_sec}


_token_bucket = TokenBucket()
_leaky_bucket = LeakyBucket()
_sliding_window = SlidingWindow()
_fixed_window = FixedWindow()


# ═════════ P811-P820: 熔断器 ═════════

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerAdv:
    """增强熔断器(支持状态机/失败率/慢调用/恢复探测)"""

    def __init__(self, name: str = "default", failure_threshold: int = 5,
                 failure_rate_threshold: float = 0.5,
                 slow_call_threshold_ms: float = 1000,
                 open_state_sec: int = 30,
                 half_open_max_calls: int = 3):
        self.name = name
        self.failure_threshold = failure_threshold
        self.failure_rate_threshold = failure_rate_threshold
        self.slow_call_threshold_ms = slow_call_threshold_ms
        self.open_state_sec = open_state_sec
        self.half_open_max_calls = half_open_max_calls
        self.state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._total_calls = 0
        self._slow_calls = 0
        self._opened_at: float = 0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    def record_success(self, duration_ms: float = 0) -> dict:
        with self._lock:
            self._total_calls += 1
            if duration_ms > self.slow_call_threshold_ms:
                self._slow_calls += 1
            if self.state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max_calls:
                    self._close()
            return {"state": self.state.value, "total": self._total_calls}

    def record_failure(self, duration_ms: float = 0) -> dict:
        with self._lock:
            self._total_calls += 1
            self._failure_count += 1
            if duration_ms > self.slow_call_threshold_ms:
                self._slow_calls += 1
            if self.state == CircuitState.HALF_OPEN:
                self._open()
            elif self.state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._open()
            return {"state": self.state.value, "failures": self._failure_count}

    def allow_request(self) -> dict:
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return {"allowed": True, "state": self.state.value}
            if self.state == CircuitState.OPEN:
                if time.time() - self._opened_at >= self.open_state_sec:
                    self.state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._success_count = 0
                    return {"allowed": True, "state": self.state.value}
                return {"allowed": False, "state": self.state.value,
                        "retry_after": int(self._opened_at + self.open_state_sec - time.time())}
            # half_open
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return {"allowed": True, "state": self.state.value}
            return {"allowed": False, "state": self.state.value}

    def _open(self) -> None:
        self.state = CircuitState.OPEN
        self._opened_at = time.time()

    def _close(self) -> None:
        self.state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0

    def reset(self) -> dict:
        with self._lock:
            self._close()
            self._total_calls = 0
            self._slow_calls = 0
            return {"status": "ok", "state": self.state.value}

    def stats(self) -> dict:
        with self._lock:
            failure_rate = (self._failure_count / self._total_calls
                            if self._total_calls > 0 else 0)
            return {
                "name": self.name,
                "state": self.state.value,
                "total_calls": self._total_calls,
                "failures": self._failure_count,
                "slow_calls": self._slow_calls,
                "failure_rate": round(failure_rate, 4),
            }


class CircuitRegistry:
    """熔断器注册表"""

    def __init__(self):
        self._breakers: dict[str, CircuitBreakerAdv] = {}
        self._lock = threading.Lock()

    def get_or_create(self, name: str, **kwargs) -> CircuitBreakerAdv:
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreakerAdv(name=name, **kwargs)
            return self._breakers[name]

    def list_all(self) -> list[dict]:
        with self._lock:
            return [cb.stats() for cb in self._breakers.values()]

    def reset(self, name: str) -> dict:
        with self._lock:
            cb = self._breakers.get(name)
            return cb.reset() if cb else {"status": "error", "error": "熔断器不存在"}


_circuit_registry = CircuitRegistry()


# ═════════ P821-P830: 降级 + 背压 ═════════

class DegradationManager:
    """服务降级管理"""

    def __init__(self):
        self._rules: dict[str, dict] = {}
        self._degraded: set[str] = set()
        self._fallbacks: dict[str, Callable] = {}
        self._lock = threading.Lock()

    def register_rule(self, service: str, trigger_qps: int = 1000,
                      fallback: str = "static_response",
                      levels: list[str] | None = None) -> dict:
        with self._lock:
            self._rules[service] = {
                "trigger_qps": trigger_qps,
                "fallback": fallback,
                "levels": levels or ["L1", "L2", "L3"],
                "current_level": "normal",
            }
            return {"status": "ok"}

    def trigger(self, service: str, level: str = "L1") -> dict:
        with self._lock:
            if service not in self._rules:
                return {"status": "error", "error": "服务未注册"}
            self._degraded.add(service)
            self._rules[service]["current_level"] = level
            return {"status": "ok", "service": service, "level": level}

    def recover(self, service: str) -> dict:
        with self._lock:
            self._degraded.discard(service)
            if service in self._rules:
                self._rules[service]["current_level"] = "normal"
            return {"status": "ok"}

    def check(self, service: str) -> dict:
        with self._lock:
            rule = self._rules.get(service)
            if not rule:
                return {"degraded": False}
            return {
                "degraded": service in self._degraded,
                "level": rule["current_level"],
                "fallback": rule["fallback"],
            }

    def list_rules(self) -> list[dict]:
        with self._lock:
            return [{"service": k, **v} for k, v in self._rules.items()]


class Backpressure:
    """背压控制"""

    def __init__(self, max_inflight: int = 100):
        self.max_inflight = max_inflight
        self._inflight = 0
        self._rejected = 0
        self._lock = threading.Lock()

    def acquire(self) -> dict:
        with self._lock:
            if self._inflight < self.max_inflight:
                self._inflight += 1
                return {"accepted": True, "inflight": self._inflight}
            self._rejected += 1
            return {"accepted": False, "inflight": self._inflight,
                    "rejected_total": self._rejected}

    def release(self) -> dict:
        with self._lock:
            self._inflight = max(0, self._inflight - 1)
            return {"inflight": self._inflight}

    def stats(self) -> dict:
        with self._lock:
            return {
                "inflight": self._inflight,
                "max": self.max_inflight,
                "rejected": self._rejected,
                "utilization": round(self._inflight / self.max_inflight, 4),
            }


_degradation = DegradationManager()
_backpressure = Backpressure()


# ═════════ P831-P840: 重试 + 超时 + 隔舱 ═════════

class RetryPolicy:
    """重试策略"""

    def __init__(self, max_attempts: int = 3, base_delay_ms: int = 100,
                 max_delay_ms: int = 5000, backoff_factor: float = 2.0,
                 jitter: bool = True):
        self.max_attempts = max_attempts
        self.base_delay_ms = base_delay_ms
        self.max_delay_ms = max_delay_ms
        self.backoff_factor = backoff_factor
        self.jitter = jitter

    def next_delay(self, attempt: int) -> dict:
        delay = min(self.base_delay_ms * (self.backoff_factor ** (attempt - 1)),
                    self.max_delay_ms)
        if self.jitter:
            import random
            delay = delay * (0.5 + random.random() * 0.5)
        return {
            "attempt": attempt,
            "delay_ms": round(delay, 2),
            "should_retry": attempt < self.max_attempts,
        }

    def execute(self, fn: Callable, *args, **kwargs) -> dict:
        import random
        last_error = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                result = fn(*args, **kwargs)
                return {"status": "ok", "result": result, "attempts": attempt}
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_attempts:
                    delay = self.next_delay(attempt)["delay_ms"]
                    time.sleep(delay / 1000)
        return {"status": "error", "error": last_error,
                "attempts": self.max_attempts}


class TimeoutGuard:
    """超时守卫"""

    def __init__(self, default_timeout_ms: int = 5000):
        self.default_timeout_ms = default_timeout_ms
        self._timeouts: dict[str, int] = {}
        self._lock = threading.Lock()

    def set(self, operation: str, timeout_ms: int) -> dict:
        with self._lock:
            self._timeouts[operation] = timeout_ms
            return {"status": "ok", "operation": operation,
                    "timeout_ms": timeout_ms}

    def get(self, operation: str) -> dict:
        with self._lock:
            return {"operation": operation,
                    "timeout_ms": self._timeouts.get(operation, self.default_timeout_ms)}

    def list_all(self) -> list[dict]:
        with self._lock:
            return [{"operation": k, "timeout_ms": v}
                    for k, v in self._timeouts.items()]


class Bulkhead:
    """隔舱模式"""

    def __init__(self):
        self._compartments: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, name: str, max_concurrent: int = 10,
               max_queue: int = 20) -> dict:
        with self._lock:
            self._compartments[name] = {
                "max_concurrent": max_concurrent,
                "max_queue": max_queue,
                "current": 0,
                "queue_depth": 0,
                "rejected": 0,
            }
            return {"status": "ok"}

    def acquire(self, name: str) -> dict:
        with self._lock:
            c = self._compartments.get(name)
            if not c:
                return {"accepted": False, "error": "隔舱不存在"}
            if c["current"] < c["max_concurrent"]:
                c["current"] += 1
                return {"accepted": True, "mode": "concurrent",
                        "current": c["current"]}
            if c["queue_depth"] < c["max_queue"]:
                c["queue_depth"] += 1
                return {"accepted": True, "mode": "queued",
                        "queue_depth": c["queue_depth"]}
            c["rejected"] += 1
            return {"accepted": False, "mode": "rejected",
                    "rejected_total": c["rejected"]}

    def release(self, name: str) -> dict:
        with self._lock:
            c = self._compartments.get(name)
            if not c:
                return {"status": "error", "error": "隔舱不存在"}
            if c["queue_depth"] > 0:
                c["queue_depth"] -= 1
            else:
                c["current"] = max(0, c["current"] - 1)
            return {"status": "ok", "current": c["current"],
                    "queue_depth": c["queue_depth"]}

    def stats(self, name: str) -> dict:
        with self._lock:
            c = self._compartments.get(name)
            return c if c else {"error": "隔舱不存在"}

    def list_all(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **v} for k, v in self._compartments.items()]


_retry_policy = RetryPolicy()
_timeout_guard = TimeoutGuard()
_bulkhead = Bulkhead()


# ═════════ 全局限流编排 ═════════

class FlowController:
    """流量编排器(统一管理限流/熔断/降级/背压)"""

    def __init__(self):
        self._strategies: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register(self, name: str, strategy: str = "token_bucket",
                 **kwargs) -> dict:
        with self._lock:
            self._strategies[name] = {
                "strategy": strategy,
                "params": kwargs,
                "created_at": datetime.now().isoformat(),
            }
            return {"status": "ok"}

    def check(self, name: str, key: str = "") -> dict:
        with self._lock:
            s = self._strategies.get(name)
            if not s:
                return {"allowed": True, "reason": "no_strategy"}
            strategy = s["strategy"]
            params = s["params"]
        if strategy == "token_bucket":
            return _token_bucket.consume(params.get("tokens", 1))
        elif strategy == "sliding_window":
            return _sliding_window.check(key or "default")
        elif strategy == "fixed_window":
            return _fixed_window.check(key or "default")
        elif strategy == "leaky_bucket":
            return _leaky_bucket.pour(params.get("amount", 1))
        return {"allowed": True, "reason": "unknown_strategy"}

    def list_strategies(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **v} for k, v in self._strategies.items()]


_flow_controller = FlowController()
