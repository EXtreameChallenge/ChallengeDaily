"""
P421-P500: 边缘计算+服务网格+API网关+消息队列+存储优化+数据库优化+缓存策略+负载均衡(80轮)
分模块汇总:
- P421-P430: 边缘计算(Edge Computing)
- P431-P440: 服务网格(Service Mesh)
- P441-P450: API网关增强
- P451-P460: 消息队列
- P461-P470: 存储优化
- P471-P480: 数据库优化
- P481-P490: 缓存策略
- P491-P500: 负载均衡
"""
from __future__ import annotations

import hashlib
import logging
import math
import random
import threading
import time
import zlib
import json
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ═════════ P421-P430: 边缘计算 ═════════

class EdgeNode:
    """边缘节点"""

    def __init__(self, node_id: str, location: str = "",
                 capacity: int = 100, latency_ms: float = 10):
        self.node_id = node_id
        self.location = location
        self.capacity = capacity
        self.latency_ms = latency_ms
        self.current_load = 0
        self.status = "online"
        self._lock = threading.Lock()

    def assign_task(self, task_size: int = 1) -> dict:
        with self._lock:
            if self.current_load + task_size > self.capacity:
                return {"accepted": False, "reason": "capacity_full"}
            self.current_load += task_size
            return {"accepted": True, "load": self.current_load / self.capacity}

    def release_task(self, task_size: int = 1) -> None:
        with self._lock:
            self.current_load = max(0, self.current_load - task_size)

    def get_status(self) -> dict:
        with self._lock:
            return {
                "node_id": self.node_id,
                "location": self.location,
                "capacity": self.capacity,
                "current_load": self.current_load,
                "utilization": round(self.current_load / self.capacity * 100, 2),
                "latency_ms": self.latency_ms,
                "status": self.status,
            }


class EdgeNetwork:
    """边缘计算网络"""

    def __init__(self):
        self._nodes: dict[str, EdgeNode] = {}
        self._lock = threading.Lock()

    def add_node(self, node: EdgeNode) -> None:
        with self._lock:
            self._nodes[node.node_id] = node

    def route_request(self, request_size: int = 1,
                      preferred_location: str = "") -> dict:
        with self._lock:
            nodes = list(self._nodes.values())
        if not nodes:
            return {"status": "error", "error": "无可用节点"}
        # 优先位置匹配
        candidates = [n for n in nodes if n.status == "online"]
        if preferred_location:
            local = [n for n in candidates if preferred_location in n.location]
            if local:
                candidates = local
        # 选择负载最低的
        candidates.sort(key=lambda n: n.current_load / n.capacity)
        for node in candidates:
            result = node.assign_task(request_size)
            if result["accepted"]:
                return {"status": "ok", "node": node.node_id,
                        "latency_ms": node.latency_ms, **result}
        return {"status": "error", "error": "所有节点已满"}

    def list_nodes(self) -> list[dict]:
        with self._lock:
            return [n.get_status() for n in self._nodes.values()]


_edge_network = EdgeNetwork()


class EdgeCache:
    """边缘缓存"""

    def __init__(self, max_size: int = 1000):
        self._cache: dict[str, dict] = {}
        self._max_size = max_size
        self._lock = threading.Lock()

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                # LRU淘汰
                oldest = min(self._cache.items(), key=lambda x: x[1].get("last_access", 0))
                self._cache.pop(oldest[0], None)
            self._cache[key] = {
                "value": value,
                "expires_at": time.time() + ttl,
                "last_access": time.time(),
            }

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if time.time() > entry["expires_at"]:
                self._cache.pop(key, None)
                return None
            entry["last_access"] = time.time()
            return entry["value"]

    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._cache), "max_size": self._max_size}


_edge_cache = EdgeCache()


# ═════════ P431-P440: 服务网格 ═════════

class ServiceMesh:
    """服务网格"""

    def __init__(self):
        self._services: dict[str, dict] = {}
        self._rules: list[dict] = []
        self._lock = threading.Lock()

    def register_service(self, name: str, host: str, port: int,
                         version: str = "v1") -> None:
        with self._lock:
            self._services[name] = {
                "host": host, "port": port, "version": version,
                "status": "healthy", "registered_at": datetime.now().isoformat(),
            }

    def add_routing_rule(self, source: str, target: str,
                         weight: int = 100, conditions: dict | None = None) -> None:
        with self._lock:
            self._rules.append({
                "source": source, "target": target,
                "weight": weight, "conditions": conditions or {},
            })

    def resolve(self, source: str, target: str) -> dict:
        with self._lock:
            service = self._services.get(target)
            rules = [r for r in self._rules
                     if r["source"] == source and r["target"] == target]
        if not service:
            return {"status": "error", "error": "服务未注册"}
        return {
            "status": "ok",
            "target": target,
            "host": service["host"],
            "port": service["port"],
            "version": service["version"],
            "rules": rules,
        }

    def list_services(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **v} for k, v in self._services.items()]


_service_mesh = ServiceMesh()


class CircuitBreaker:
    """熔断器"""

    def __init__(self, threshold: int = 5, timeout: int = 60):
        self._failures: dict[str, int] = defaultdict(int)
        self._states: dict[str, str] = defaultdict(lambda: "closed")
        self._opened_at: dict[str, float] = {}
        self.threshold = threshold
        self.timeout = timeout
        self._lock = threading.Lock()

    def record_success(self, service: str) -> None:
        with self._lock:
            self._failures[service] = 0
            self._states[service] = "closed"
            self._opened_at.pop(service, None)

    def record_failure(self, service: str) -> dict:
        with self._lock:
            self._failures[service] += 1
            if self._failures[service] >= self.threshold:
                self._states[service] = "open"
                self._opened_at[service] = time.time()
                return {"tripped": True, "service": service}
            return {"tripped": False, "failures": self._failures[service]}

    def can_request(self, service: str) -> bool:
        with self._lock:
            state = self._states[service]
            if state == "closed":
                return True
            if state == "open":
                if time.time() - self._opened_at.get(service, 0) > self.timeout:
                    self._states[service] = "half_open"
                    return True
                return False
            return True  # half_open


_mesh_breaker = CircuitBreaker()


# ═════════ P441-P450: API网关增强 ═════════

class APIGatewayAdv:
    """增强API网关"""

    def __init__(self):
        self._routes: dict[str, dict] = {}
        self._rate_limits: dict[str, deque] = {}
        self._auth_tokens: dict[str, dict] = {}
        self._transformers: list[Callable] = []
        self._lock = threading.Lock()

    def register_route(self, path: str, upstream: str,
                       methods: list[str] | None = None,
                       auth_required: bool = True,
                       rate_limit: int = 100) -> None:
        with self._lock:
            self._routes[path] = {
                "upstream": upstream,
                "methods": methods or ["GET"],
                "auth_required": auth_required,
                "rate_limit": rate_limit,
            }
            self._rate_limits[path] = deque(maxlen=rate_limit)

    def check_rate(self, path: str) -> dict:
        with self._lock:
            route = self._routes.get(path)
            if not route:
                return {"allowed": False, "error": "路由不存在"}
            now = time.time()
            limits = self._rate_limits[path]
            while limits and limits[0] < now - 60:
                limits.popleft()
            if len(limits) >= route["rate_limit"]:
                return {"allowed": False, "error": "限流"}
            limits.append(now)
            return {"allowed": True, "remaining": route["rate_limit"] - len(limits)}

    def authenticate(self, token: str) -> dict:
        with self._lock:
            auth = self._auth_tokens.get(token)
        if not auth:
            return {"valid": False, "error": "无效token"}
        if time.time() > auth.get("expires_at", 0):
            return {"valid": False, "error": "token已过期"}
        return {"valid": True, "user_id": auth.get("user_id")}

    def issue_token(self, user_id: str, ttl: int = 3600) -> str:
        token = hashlib.sha256(f"{user_id}:{time.time()}".encode()).hexdigest()[:32]
        with self._lock:
            self._auth_tokens[token] = {
                "user_id": user_id,
                "expires_at": time.time() + ttl,
            }
        return token

    def list_routes(self) -> list[dict]:
        with self._lock:
            return [{"path": k, **v} for k, v in self._routes.items()]


_gateway_adv = APIGatewayAdv()


# ═════════ P451-P460: 消息队列 ═════════

class MessageQueue:
    """消息队列"""

    def __init__(self, name: str = "default"):
        self.name = name
        self._queue: deque = deque(maxlen=10000)
        self._consumers: list[Callable] = []
        self._dead_letter: deque = deque(maxlen=1000)
        self._stats = {"produced": 0, "consumed": 0, "failed": 0}
        self._lock = threading.Lock()

    def produce(self, message: Any, priority: int = 0) -> dict:
        with self._lock:
            self._queue.append({
                "message": message,
                "priority": priority,
                "produced_at": time.time(),
                "attempts": 0,
            })
            self._stats["produced"] += 1
            return {"status": "ok", "queue_size": len(self._queue)}

    def consume(self) -> dict | None:
        with self._lock:
            if not self._queue:
                return None
            item = self._queue.popleft()
            self._stats["consumed"] += 1
            return item

    def register_consumer(self, fn: Callable) -> None:
        with self._lock:
            self._consumers.append(fn)

    def fail(self, message: dict, reason: str = "") -> None:
        with self._lock:
            self._dead_letter.append({
                "message": message,
                "reason": reason,
                "failed_at": time.time(),
            })
            self._stats["failed"] += 1

    def get_stats(self) -> dict:
        with self._lock:
            return {**self._stats, "queue_size": len(self._queue),
                    "dead_letter_size": len(self._dead_letter)}


_mq = MessageQueue()


class TopicExchange:
    """主题交换(发布订阅)"""

    def __init__(self):
        self._topics: dict[str, list[Callable]] = defaultdict(list)
        self._messages: dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self._lock = threading.Lock()

    def subscribe(self, topic: str, handler: Callable) -> None:
        with self._lock:
            self._topics[topic].append(handler)

    def publish(self, topic: str, message: Any) -> dict:
        with self._lock:
            handlers = list(self._topics.get(topic, []))
            self._messages[topic].append({
                "message": message,
                "published_at": time.time(),
            })
        delivered = 0
        for h in handlers:
            try:
                h(message)
                delivered += 1
            except Exception as e:
                logger.warning("订阅处理器失败: %s", e)
        return {"status": "ok", "topic": topic, "delivered": delivered}

    def get_topics(self) -> list[str]:
        with self._lock:
            return list(self._topics.keys())


_topic_exchange = TopicExchange()


# ═════════ P461-P470: 存储优化 ═════════

class StorageOptimizer:
    """存储优化器"""

    @staticmethod
    def compress_data(data: str) -> dict:
        compressed = zlib.compress(data.encode(), level=6)
        ratio = len(compressed) / len(data.encode()) if data else 0
        return {
            "original_size": len(data.encode()),
            "compressed_size": len(compressed),
            "ratio": round(ratio, 4),
            "savings_pct": round((1 - ratio) * 100, 2),
        }

    @staticmethod
    def deduplicate(chunks: list[str]) -> dict:
        unique = set(chunks)
        return {
            "total_chunks": len(chunks),
            "unique_chunks": len(unique),
            "duplicates": len(chunks) - len(unique),
            "savings_pct": round((1 - len(unique) / len(chunks)) * 100, 2) if chunks else 0,
        }

    @staticmethod
    def tiered_storage(data_size: int, access_frequency: str = "low") -> dict:
        if access_frequency == "high":
            tier = "hot"
            cost_per_gb = 0.15
        elif access_frequency == "medium":
            tier = "warm"
            cost_per_gb = 0.05
        else:
            tier = "cold"
            cost_per_gb = 0.01
        monthly_cost = data_size / 1024 * cost_per_gb  # 假设data_size为MB
        return {"tier": tier, "cost_per_gb_month": cost_per_gb,
                "monthly_cost": round(monthly_cost, 4)}


_storage_opt = StorageOptimizer()


class DataLifecycle:
    """数据生命周期管理"""

    def __init__(self):
        self._policies: dict[str, dict] = {}
        self._lock = threading.Lock()

    def set_policy(self, data_type: str, hot_days: int = 30,
                   warm_days: int = 90, cold_days: int = 365,
                   archive_after: int = 365, delete_after: int = 2555) -> None:
        with self._lock:
            self._policies[data_type] = {
                "hot_days": hot_days,
                "warm_days": warm_days,
                "cold_days": cold_days,
                "archive_after": archive_after,
                "delete_after": delete_after,
            }

    def get_tier(self, data_type: str, age_days: int) -> dict:
        with self._lock:
            policy = self._policies.get(data_type, {})
        if not policy:
            return {"tier": "hot", "action": "keep"}
        if age_days <= policy["hot_days"]:
            return {"tier": "hot", "action": "keep"}
        elif age_days <= policy["warm_days"]:
            return {"tier": "warm", "action": "move_to_warm"}
        elif age_days <= policy["cold_days"]:
            return {"tier": "cold", "action": "move_to_cold"}
        elif age_days <= policy["delete_after"]:
            return {"tier": "archive", "action": "archive"}
        else:
            return {"tier": "delete", "action": "delete"}

    def list_policies(self) -> list[dict]:
        with self._lock:
            return [{"data_type": k, **v} for k, v in self._policies.items()]


_data_lifecycle = DataLifecycle()


# ═════════ P471-P480: 数据库优化 ═════════

class QueryOptimizer:
    """查询优化器"""

    @staticmethod
    def analyze_query(query: str) -> dict:
        issues = []
        query_upper = query.upper()
        if "SELECT *" in query_upper:
            issues.append({"severity": "medium", "issue": "避免SELECT *,只查询需要的列"})
        if "WHERE" not in query_upper and "SELECT" in query_upper:
            issues.append({"severity": "high", "issue": "缺少WHERE子句可能导致全表扫描"})
        if "LIKE '%" in query_upper:
            issues.append({"severity": "high", "issue": "前缀通配符LIKE '%xxx'无法使用索引"})
        if "ORDER BY" in query_upper and "LIMIT" not in query_upper:
            issues.append({"severity": "low", "issue": "ORDER BY无LIMIT可能返回大量数据"})
        if "JOIN" in query_upper and "ON" not in query_upper:
            issues.append({"severity": "critical", "issue": "JOIN缺少ON条件(笛卡尔积)"})
        return {
            "query": query[:100],
            "issues": issues,
            "issue_count": len(issues),
            "estimated_cost": "high" if any(i["severity"] == "critical" for i in issues) else
                              "medium" if issues else "low",
        }


class IndexAdvisor:
    """索引顾问"""

    @staticmethod
    def recommend(table: str, columns: list[str],
                  query_patterns: list[str]) -> list[dict]:
        recommendations = []
        # 单列索引
        for col in columns:
            score = 0
            for pattern in query_patterns:
                if col in pattern.lower():
                    score += 10
            if score > 0:
                recommendations.append({
                    "type": "single",
                    "table": table,
                    "columns": [col],
                    "score": score,
                    "reason": f"列{col}在查询模式中频繁出现",
                })
        # 复合索引
        if len(columns) >= 2:
            recommendations.append({
                "type": "composite",
                "table": table,
                "columns": columns[:3],
                "score": 20,
                "reason": "多列联合查询建议复合索引",
            })
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations


class ConnectionPool:
    """数据库连接池"""

    def __init__(self, max_connections: int = 20):
        self.max_connections = max_connections
        self._pool: deque = deque(maxlen=max_connections)
        self._active: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._stats = {"created": 0, "reused": 0, "timed_out": 0}

    def acquire(self, timeout: float = 5.0) -> dict:
        with self._lock:
            if self._pool:
                conn = self._pool.popleft()
                self._stats["reused"] += 1
                conn_id = id(conn)
                self._active[conn_id] = conn
                return {"connection_id": conn_id, "source": "pool"}
            if len(self._active) < self.max_connections:
                conn = {"id": len(self._active) + 1, "created_at": time.time()}
                self._stats["created"] += 1
                conn_id = id(conn)
                self._active[conn_id] = conn
                return {"connection_id": conn_id, "source": "new"}
            self._stats["timed_out"] += 1
            return {"error": "pool_exhausted"}

    def release(self, conn_id: int) -> None:
        with self._lock:
            conn = self._active.pop(conn_id, None)
            if conn:
                self._pool.append(conn)

    def stats(self) -> dict:
        with self._lock:
            return {**self._stats, "pool_size": len(self._pool),
                    "active_count": len(self._active)}


_query_opt = QueryOptimizer
_index_advisor = IndexAdvisor
_db_pool = ConnectionPool()


# ═════════ P481-P490: 缓存策略 ═════════

class CacheStrategy:
    """缓存策略"""

    STRATEGIES = ["cache_aside", "read_through", "write_through",
                  "write_behind", "refresh_ahead"]

    @staticmethod
    def cache_aside(get_from_db: Callable, cache: dict, key: str) -> Any:
        if key in cache:
            return cache[key]
        value = get_from_db(key)
        if value is not None:
            cache[key] = value
        return value

    @staticmethod
    def write_through(write_db: Callable, cache: dict, key: str, value: Any) -> None:
        write_db(key, value)
        cache[key] = value

    @staticmethod
    def write_behind(queue: deque, cache: dict, key: str, value: Any) -> None:
        cache[key] = value
        queue.append({"key": key, "value": value, "timestamp": time.time()})


class CacheWarmup:
    """缓存预热"""

    def __init__(self):
        self._warmup_tasks: list[dict] = []
        self._lock = threading.Lock()

    def add_task(self, name: str, loader: Callable[[], dict],
                 priority: int = 0) -> None:
        with self._lock:
            self._warmup_tasks.append({
                "name": name, "loader": loader, "priority": priority,
            })
            self._warmup_tasks.sort(key=lambda x: x["priority"], reverse=True)

    def execute(self) -> dict:
        with self._lock:
            tasks = list(self._warmup_tasks)
        results = {}
        for task in tasks:
            try:
                data = task["loader"]()
                results[task["name"]] = {"status": "ok", "items": len(data) if isinstance(data, dict) else 0}
            except Exception as e:
                results[task["name"]] = {"status": "error", "error": str(e)}
        return results


_cache_warmup = CacheWarmup()


class CacheInvalidator:
    """缓存失效器"""

    def __init__(self):
        self._patterns: list[dict] = []
        self._invalidated: deque = deque(maxlen=200)
        self._lock = threading.Lock()

    def add_pattern(self, name: str, pattern: str, action: str = "delete") -> None:
        import re
        with self._lock:
            self._patterns.append({
                "name": name,
                "regex": re.compile(pattern),
                "action": action,
            })

    def invalidate(self, key: str) -> dict:
        import re
        with self._lock:
            patterns = list(self._patterns)
            self._invalidated.append({"key": key, "timestamp": time.time()})
        matched = []
        for p in patterns:
            if p["regex"].search(key):
                matched.append({"name": p["name"], "action": p["action"]})
        return {"key": key, "matched": matched, "should_invalidate": bool(matched)}

    def get_invalidated(self, limit: int = 50) -> list[dict]:
        with self._lock:
            inv = list(self._invalidated)
        inv.reverse()
        return inv[:limit]


_cache_invalidator = CacheInvalidator()


# ═════════ P491-P500: 负载均衡 ═════════

class LoadBalancer:
    """负载均衡器"""

    STRATEGIES = ["round_robin", "least_connections", "ip_hash", "random", "weighted"]

    def __init__(self, strategy: str = "round_robin"):
        self._backends: list[dict] = []
        self._strategy = strategy
        self._current: int = 0
        self._lock = threading.Lock()

    def add_backend(self, host: str, port: int, weight: int = 1) -> None:
        with self._lock:
            self._backends.append({
                "host": host, "port": port, "weight": weight,
                "connections": 0, "healthy": True,
            })

    def select(self, client_ip: str = "") -> dict | None:
        with self._lock:
            healthy = [b for b in self._backends if b["healthy"]]
            if not healthy:
                return None
            if self._strategy == "round_robin":
                backend = healthy[self._current % len(healthy)]
                self._current += 1
            elif self._strategy == "least_connections":
                backend = min(healthy, key=lambda x: x["connections"])
            elif self._strategy == "ip_hash":
                hash_val = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
                backend = healthy[hash_val % len(healthy)]
            elif self._strategy == "random":
                backend = random.choice(healthy)
            elif self._strategy == "weighted":
                total_weight = sum(b["weight"] for b in healthy)
                r = random.randint(1, total_weight)
                cumulative = 0
                backend = healthy[0]
                for b in healthy:
                    cumulative += b["weight"]
                    if r <= cumulative:
                        backend = b
                        break
            else:
                backend = healthy[0]
            backend["connections"] += 1
            return {"host": backend["host"], "port": backend["port"]}

    def release(self, host: str, port: int) -> None:
        with self._lock:
            for b in self._backends:
                if b["host"] == host and b["port"] == port:
                    b["connections"] = max(0, b["connections"] - 1)
                    break

    def set_health(self, host: str, port: int, healthy: bool) -> None:
        with self._lock:
            for b in self._backends:
                if b["host"] == host and b["port"] == port:
                    b["healthy"] = healthy
                    break

    def list_backends(self) -> list[dict]:
        with self._lock:
            return list(self._backends)

    def get_stats(self) -> dict:
        with self._lock:
            total = len(self._backends)
            healthy = sum(1 for b in self._backends if b["healthy"])
            return {
                "strategy": self._strategy,
                "total_backends": total,
                "healthy_backends": healthy,
                "total_connections": sum(b["connections"] for b in self._backends),
            }


_load_balancer = LoadBalancer(strategy="round_robin")


class HealthChecker:
    """健康检查器"""

    def __init__(self, interval: int = 30):
        self.interval = interval
        self._checks: dict[str, Callable] = {}
        self._results: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register(self, name: str, check_fn: Callable[[], bool]) -> None:
        with self._lock:
            self._checks[name] = check_fn

    def run_checks(self) -> dict:
        with self._lock:
            checks = dict(self._checks)
        results = {}
        for name, fn in checks.items():
            try:
                healthy = fn()
                results[name] = {"healthy": healthy, "timestamp": datetime.now().isoformat()}
                with self._lock:
                    self._results[name] = results[name]
            except Exception as e:
                results[name] = {"healthy": False, "error": str(e),
                                 "timestamp": datetime.now().isoformat()}
        overall = all(r["healthy"] for r in results.values()) if results else False
        return {"overall_healthy": overall, "checks": results}

    def get_results(self) -> dict:
        with self._lock:
            return dict(self._results)


_health_checker = HealthChecker()
