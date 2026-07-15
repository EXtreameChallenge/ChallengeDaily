"""
P20-3: 通用 Circuit Breaker（熔断器）
ai_client.py 中已有针对 AI 调用的熔断逻辑，本模块抽取出通用类，
可应用于 calendar_sync 的网络请求、git_integration 的 git 操作、
realtime_coach 的 DB 查询等关键外部依赖。

模式：closed → open → half_open → closed/open
- closed: 正常放行；累计失败 ≥ threshold 转为 open
- open: 冷却期内拒绝所有请求；冷却结束转为 half_open
- half_open: 允许有限试探请求；成功 → closed，失败 → open（指数退避）

线程安全：所有状态变更通过 threading.Lock 保护。
"""
import threading
import time
import logging
from functools import wraps
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """熔断器开启时抛出，调用方可捕获以走降级路径"""


class CircuitBreaker:
    """通用熔断器（线程安全）"""

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        cooldown_init_sec: float = 60.0,
        cooldown_max_sec: float = 600.0,
        half_open_max: int = 3,
    ):
        """
        Args:
            name: 熔断器名称（用于日志）
            failure_threshold: 连续失败次数触发熔断
            cooldown_init_sec: 熔断初始冷却时间
            cooldown_max_sec: 熔断最大冷却时间（指数退避上限）
            half_open_max: 半开状态允许的试探请求数
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_init_sec = cooldown_init_sec
        self.cooldown_max_sec = cooldown_max_sec
        self.half_open_max = half_open_max

        self._lock = threading.Lock()
        self._state = "closed"
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._half_open_tries = 0
        self._cooldown_sec = cooldown_init_sec

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    def allow(self) -> bool:
        """检查是否允许请求通过。返回 True 放行，False 熔断中。"""
        with self._lock:
            if self._state == "closed":
                return True
            if self._state == "open":
                if time.monotonic() - self._opened_at >= self._cooldown_sec:
                    self._state = "half_open"
                    self._half_open_tries = 0
                    logger.info(f"[CB:{self.name}] OPEN → HALF_OPEN")
                    return True
                return False
            if self._state == "half_open":
                if self._half_open_tries < self.half_open_max:
                    self._half_open_tries += 1
                    return True
                # 半开状态试探耗尽 → 重新熔断
                self._cooldown_sec = min(self._cooldown_sec * 2, self.cooldown_max_sec)
                self._state = "open"
                self._opened_at = time.monotonic()
                self._half_open_tries = 0
                logger.warning(
                    f"[CB:{self.name}] HALF_OPEN → OPEN（试探耗尽），冷却 {self._cooldown_sec}s"
                )
                return False
            return True

    def record_success(self):
        """记录一次成功请求，重置熔断器"""
        with self._lock:
            if self._state == "half_open":
                logger.info(f"[CB:{self.name}] HALF_OPEN → CLOSED（试探成功）")
            self._state = "closed"
            self._consecutive_failures = 0
            self._cooldown_sec = self.cooldown_init_sec

    def record_failure(self):
        """记录一次失败请求，累计失败次数（指数退避冷却）"""
        with self._lock:
            self._consecutive_failures += 1
            if self._state == "half_open":
                self._cooldown_sec = min(self._cooldown_sec * 2, self.cooldown_max_sec)
                self._state = "open"
                self._opened_at = time.monotonic()
                logger.warning(
                    f"[CB:{self.name}] HALF_OPEN → OPEN（试探失败），冷却 {self._cooldown_sec}s"
                )
            elif self._consecutive_failures >= self.failure_threshold:
                self._cooldown_sec = self.cooldown_init_sec
                self._state = "open"
                self._opened_at = time.monotonic()
                logger.warning(
                    f"[CB:{self.name}] CLOSED → OPEN（连续 {self._consecutive_failures} 次失败），"
                    f"冷却 {self._cooldown_sec}s"
                )

    def reset(self):
        """强制重置熔断器到 closed 状态（运维操作）"""
        with self._lock:
            self._state = "closed"
            self._consecutive_failures = 0
            self._half_open_tries = 0
            self._cooldown_sec = self.cooldown_init_sec
            logger.info(f"[CB:{self.name}] 已强制重置为 CLOSED")

    def status(self) -> dict:
        """获取当前状态快照（供 health/监控 API 使用）"""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state,
                "consecutive_failures": self._consecutive_failures,
                "cooldown_remaining_sec": max(
                    0, self._cooldown_sec - (time.monotonic() - self._opened_at)
                ) if self._state == "open" else 0,
                "cooldown_sec": self._cooldown_sec,
                "half_open_tries": self._half_open_tries,
            }

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        在熔断器保护下调用 func。
        - 熔断开启时抛出 CircuitOpenError
        - func 抛异常时记录失败并重新抛出
        - func 成功时记录成功并返回结果
        """
        if not self.allow():
            raise CircuitOpenError(f"熔断器 {self.name} 处于 OPEN 状态")
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            # 不记录业务异常（如 KeyError、ValueError）为熔断失败
            # 仅对网络/IO/超时类异常记录失败
            if _is_infra_error(e):
                self.record_failure()
            raise

    def decorator(self, func: Callable) -> Callable:
        """装饰器形式：@cb.decorator"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)
        wrapper.circuit_breaker = self  # 暴露引用便于运维
        return wrapper


def _is_infra_error(e: Exception) -> bool:
    """判断异常是否为基础设施错误（应触发熔断），而非业务错误"""
    # 网络类异常（requests/urllib/http.client）
    infra_keywords = (
        "timeout", "timed out", "connection", "ConnectionError",
        "NetworkError", "DNS", "refused", "reset", "unreachable",
        "ECONNREFUSED", "ECONNRESET", "ETIMEDOUT", "EAI_AGAIN",
        "SSLError", "ProxyError", "MaxRetryError",
        "OperationalError",  # SQLite 锁/IO 错误
        "subprocess", "CalledProcessError",  # git 子进程
    )
    msg = str(e).lower()
    return any(kw.lower() in msg for kw in infra_keywords)


# ── 预置熔断器实例（按子系统分组） ──
_calendar_cb = None
_git_cb = None
_coach_cb = None
_instances_lock = threading.Lock()


def get_calendar_breaker() -> CircuitBreaker:
    """日历订阅网络请求熔断器"""
    global _calendar_cb
    with _instances_lock:
        if _calendar_cb is None:
            _calendar_cb = CircuitBreaker(
                name="calendar_sync",
                failure_threshold=3,
                cooldown_init_sec=300,  # 日历订阅失败 5 分钟冷却
                cooldown_max_sec=3600,
                half_open_max=1,
            )
        return _calendar_cb


def get_git_breaker() -> CircuitBreaker:
    """git 子进程调用熔断器"""
    global _git_cb
    with _instances_lock:
        if _git_cb is None:
            _git_cb = CircuitBreaker(
                name="git_integration",
                failure_threshold=5,
                cooldown_init_sec=60,
                cooldown_max_sec=600,
                half_open_max=2,
            )
        return _git_cb


def get_coach_breaker() -> CircuitBreaker:
    """realtime_coach 数据库查询熔断器"""
    global _coach_cb
    with _instances_lock:
        if _coach_cb is None:
            _coach_cb = CircuitBreaker(
                name="realtime_coach",
                failure_threshold=3,
                cooldown_init_sec=30,
                cooldown_max_sec=300,
                half_open_max=2,
            )
        return _coach_cb


def all_breakers_status() -> dict:
    """获取所有预置熔断器状态（供 /api/health 端点使用）"""
    return {
        "calendar_sync": get_calendar_breaker().status(),
        "git_integration": get_git_breaker().status(),
        "realtime_coach": get_coach_breaker().status(),
    }
