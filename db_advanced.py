"""
P841-P880: 数据库高级+索引顾问+查询优化+读写分离+分库分表+慢查询+连接池+事务+ORM映射(40轮)
"""
from __future__ import annotations

import re
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

logger = __import__("logging").getLogger(__name__)


# ═════════ P841-P850: 索引顾问 ═════════

class IndexAdvisorAdv:
    """增强索引顾问"""

    def __init__(self):
        self._queries: deque = deque(maxlen=1000)
        self._indexes: dict[str, list[dict]] = defaultdict(list)
        self._recommendations: list[dict] = []
        self._lock = threading.Lock()

    def record_query(self, table: str, columns: list[str],
                     where_clause: str = "", duration_ms: float = 0) -> None:
        with self._lock:
            self._queries.append({
                "table": table,
                "columns": columns,
                "where": where_clause,
                "duration_ms": duration_ms,
                "timestamp": time.time(),
            })

    def add_existing_index(self, table: str, columns: list[str],
                           name: str = "", unique: bool = False) -> None:
        with self._lock:
            self._indexes[table].append({
                "name": name or f"idx_{table}_{'_'.join(columns)}",
                "columns": columns,
                "unique": unique,
            })

    def analyze(self) -> list[dict]:
        with self._lock:
            queries = list(self._queries)
            indexes = {k: list(v) for k, v in self._indexes.items()}
        # 统计列使用频率
        col_usage: dict[tuple[str, str], int] = Counter()
        slow_queries = []
        for q in queries:
            for c in q["columns"]:
                col_usage[(q["table"], c)] += 1
            if q["duration_ms"] > 100:
                slow_queries.append(q)
        # 生成建议
        recommendations = []
        for (table, col), count in col_usage.most_common(20):
            existing = [i for i in indexes.get(table, []) if col in i["columns"]]
            if not existing and count >= 3:
                recommendations.append({
                    "type": "single_column",
                    "table": table,
                    "column": col,
                    "query_count": count,
                    "reason": f"列 {col} 在 {count} 次查询中频繁使用但无索引",
                    "estimated_benefit": "high" if count >= 10 else "medium",
                })
        # 复合索引建议
        table_cols: dict[str, list[str]] = defaultdict(list)
        for q in queries:
            if len(q["columns"]) >= 2:
                table_cols[q["table"]].append(tuple(q["columns"][:3]))
        for table, col_tuples in table_cols.items():
            combo_counts = Counter(col_tuples)
            for cols, cnt in combo_counts.most_common(5):
                if cnt < 5:
                    continue
                rec = {
                    "type": "composite",
                    "table": table,
                    "columns": list(cols),
                    "query_count": cnt,
                    "reason": f"复合查询 ({','.join(cols)}) 出现 {cnt} 次",
                }
                recommendations.append(rec)
        with self._lock:
            self._recommendations = recommendations
        return recommendations

    def list_existing(self) -> dict:
        with self._lock:
            return {k: list(v) for k, v in self._indexes.items()}

    def slow_query_report(self, threshold_ms: float = 100) -> dict:
        with self._lock:
            queries = list(self._queries)
        slow = [q for q in queries if q["duration_ms"] > threshold_ms]
        return {
            "total_queries": len(queries),
            "slow_count": len(slow),
            "slow_pct": round(len(slow) / max(1, len(queries)) * 100, 2),
            "by_table": dict(Counter(q["table"] for q in slow)),
            "top_slow": sorted(slow, key=lambda x: -x["duration_ms"])[:10],
        }


_index_advisor = IndexAdvisorAdv()


# ═════════ P851-P860: 查询优化器 ═════════

class QueryOptimizerAdv:
    """查询优化器"""

    @staticmethod
    def parse_query(sql: str) -> dict:
        sql_lower = sql.lower().strip()
        info = {
            "type": "unknown",
            "tables": [],
            "has_join": False,
            "has_subquery": False,
            "has_where": False,
            "has_order": False,
            "has_group": False,
            "has_limit": False,
            "warnings": [],
        }
        if sql_lower.startswith("select"):
            info["type"] = "select"
        elif sql_lower.startswith("insert"):
            info["type"] = "insert"
        elif sql_lower.startswith("update"):
            info["type"] = "update"
        elif sql_lower.startswith("delete"):
            info["type"] = "delete"
        info["has_join"] = "join" in sql_lower
        info["has_subquery"] = sql_lower.count("select") > 1
        info["has_where"] = "where" in sql_lower
        info["has_order"] = "order by" in sql_lower
        info["has_group"] = "group by" in sql_lower
        info["has_limit"] = "limit" in sql_lower
        # 提取表名(from 后)
        from_match = re.search(r"from\s+(\w+)", sql_lower)
        if from_match:
            info["tables"].append(from_match.group(1))
        join_matches = re.findall(r"join\s+(\w+)", sql_lower)
        info["tables"].extend(join_matches)
        # 警告
        if info["type"] == "select" and not info["has_where"]:
            info["warnings"].append("SELECT无WHERE子句，可能全表扫描")
        if info["has_order"] and not info["has_limit"]:
            info["warnings"].append("ORDER BY无LIMIT，可能消耗大量内存")
        if info["has_subquery"]:
            info["warnings"].append("包含子查询，考虑改写为JOIN")
        if "select *" in sql_lower:
            info["warnings"].append("SELECT *，应明确指定列")
        if info["has_join"] and len(info["tables"]) > 3:
            info["warnings"].append(f"多表JOIN({len(info['tables'])}张)，考虑拆分")
        return info

    @staticmethod
    def explain_plan(sql: str) -> dict:
        info = QueryOptimizerAdv.parse_query(sql)
        steps = []
        if info["has_subquery"]:
            steps.append({"step": 1, "op": "SUBQUERY_SCAN",
                          "cost": "high", "warning": "子查询成本高"})
        steps.append({"step": len(steps) + 1, "op": "TABLE_SCAN",
                      "table": info["tables"][0] if info["tables"] else "unknown",
                      "cost": "high" if not info["has_where"] else "medium"})
        if info["has_join"]:
            for t in info["tables"][1:]:
                steps.append({"step": len(steps) + 1, "op": "NESTED_LOOP_JOIN",
                              "table": t, "cost": "medium"})
        if info["has_group"]:
            steps.append({"step": len(steps) + 1, "op": "HASH_GROUP",
                          "cost": "medium"})
        if info["has_order"]:
            steps.append({"step": len(steps) + 1, "op": "SORT",
                          "cost": "medium" if info["has_limit"] else "high"})
        if info["has_limit"]:
            steps.append({"step": len(steps) + 1, "op": "LIMIT",
                          "cost": "low"})
        return {
            "sql_preview": sql[:200],
            "total_steps": len(steps),
            "steps": steps,
            "estimated_cost": sum({"low": 1, "medium": 5, "high": 20}.get(s.get("cost", "medium"), 5) for s in steps),
            "warnings": info["warnings"],
        }

    @staticmethod
    def suggest_optimization(sql: str) -> list[str]:
        info = QueryOptimizerAdv.parse_query(sql)
        suggestions = []
        if "select *" in sql.lower():
            suggestions.append("明确指定所需列，避免SELECT *")
        if not info["has_where"] and info["type"] == "select":
            suggestions.append("添加WHERE子句限制扫描范围")
        if info["has_subquery"]:
            suggestions.append("考虑将子查询改写为JOIN")
        if info["has_order"] and not info["has_limit"]:
            suggestions.append("添加LIMIT避免排序全量数据")
        if info["has_join"] and len(info["tables"]) > 2:
            suggestions.append("多表JOIN考虑冗余字段或分步查询")
        if not suggestions:
            suggestions.append("查询语句已较为规范")
        return suggestions


_query_optimizer = QueryOptimizerAdv()


# ═════════ P861-P870: 读写分离 + 分库分表 ═════════

class ReadWriteSplitter:
    """读写分离"""

    def __init__(self):
        self._master: dict[str, dict] = {}
        self._slaves: dict[str, list[dict]] = defaultdict(list)
        self._round_robin: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def set_master(self, cluster: str, host: str, port: int = 3306) -> None:
        with self._lock:
            self._master[cluster] = {"host": host, "port": port, "role": "master"}

    def add_slave(self, cluster: str, host: str, port: int = 3306) -> None:
        with self._lock:
            self._slaves[cluster].append({"host": host, "port": port, "role": "slave"})

    def route(self, cluster: str, operation: str) -> dict:
        with self._lock:
            if operation.upper() in ("INSERT", "UPDATE", "DELETE", "DDL"):
                return self._master.get(cluster, {"error": "无主库"})
            slaves = self._slaves.get(cluster, [])
            if not slaves:
                return self._master.get(cluster, {"error": "无从库"})
            idx = self._round_robin[cluster] % len(slaves)
            self._round_robin[cluster] += 1
            return slaves[idx]

    def list_clusters(self) -> dict:
        with self._lock:
            return {
                "masters": dict(self._master),
                "slaves": {k: list(v) for k, v in self._slaves.items()},
            }


class ShardManager:
    """分库分表"""

    def __init__(self, shards: int = 4):
        self.shards = shards
        self._shard_maps: dict[str, dict] = {}  # table -> {key -> shard_id}
        self._lock = threading.Lock()

    def get_shard(self, table: str, key: Any) -> int:
        key_str = str(key)
        return int(__import__("hashlib").md5(key_str.encode()).hexdigest(), 16) % self.shards

    def register_record(self, table: str, key: Any, record: dict) -> dict:
        shard_id = self.get_shard(table, key)
        with self._lock:
            if table not in self._shard_maps:
                self._shard_maps[table] = {}
            self._shard_maps[table][str(key)] = {
                "shard": shard_id,
                "record": record,
            }
            return {"status": "ok", "shard": shard_id}

    def lookup(self, table: str, key: Any) -> dict:
        with self._lock:
            table_map = self._shard_maps.get(table, {})
            return table_map.get(str(key), {"error": "记录不存在"})

    def shard_stats(self) -> dict:
        with self._lock:
            stats = {}
            for table, records in self._shard_maps.items():
                shard_counts = Counter(v["shard"] for v in records.values())
                stats[table] = {
                    "total": len(records),
                    "by_shard": dict(shard_counts),
                    "balance": round(min(shard_counts.values()) / max(1, max(shard_counts.values())), 4) if shard_counts else 1.0,
                }
            return stats


_read_write = ReadWriteSplitter()
_shard_mgr = ShardManager()


# ═════════ P871-P880: 慢查询 + 连接池 + 事务管理 ═════════

class SlowQueryMonitor:
    """慢查询监控"""

    def __init__(self, threshold_ms: float = 100):
        self.threshold_ms = threshold_ms
        self._slow_queries: deque = deque(maxlen=500)
        self._lock = threading.Lock()

    def record(self, sql: str, duration_ms: float, table: str = "") -> None:
        if duration_ms >= self.threshold_ms:
            with self._lock:
                self._slow_queries.append({
                    "sql": sql[:500],
                    "duration_ms": round(duration_ms, 2),
                    "table": table,
                    "timestamp": datetime.now().isoformat(),
                })

    def top_slow(self, limit: int = 20) -> list[dict]:
        with self._lock:
            queries = list(self._slow_queries)
        return sorted(queries, key=lambda x: -x["duration_ms"])[:limit]

    def stats(self) -> dict:
        with self._lock:
            queries = list(self._slow_queries)
        if not queries:
            return {"total": 0, "avg_ms": 0, "max_ms": 0}
        durations = [q["duration_ms"] for q in queries]
        return {
            "total": len(queries),
            "avg_ms": round(sum(durations) / len(durations), 2),
            "max_ms": max(durations),
            "min_ms": min(durations),
            "p95_ms": sorted(durations)[int(len(durations) * 0.95) - 1] if len(durations) >= 2 else max(durations),
            "by_table": dict(Counter(q["table"] for q in queries if q["table"])),
        }


class ConnectionPoolAdv:
    """增强连接池"""

    def __init__(self, max_connections: int = 20, idle_timeout_sec: int = 300):
        self.max_connections = max_connections
        self.idle_timeout_sec = idle_timeout_sec
        self._pool: deque = deque()
        self._active: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._stats = {"created": 0, "reused": 0, "timed_out": 0}

    def acquire(self, conn_id: str) -> dict:
        with self._lock:
            if self._pool:
                conn = self._pool.popleft()
                self._stats["reused"] += 1
            elif len(self._active) < self.max_connections:
                conn = {"id": f"conn_{self._stats['created']}",
                        "created_at": time.time()}
                self._stats["created"] += 1
            else:
                return {"status": "error", "error": "连接池已满",
                        "active": len(self._active)}
            self._active[conn_id] = conn
            return {"status": "ok", "conn": conn, "active": len(self._active)}

    def release(self, conn_id: str) -> dict:
        with self._lock:
            conn = self._active.pop(conn_id, None)
            if conn:
                self._pool.append(conn)
                return {"status": "ok", "pooled": len(self._pool)}
            return {"status": "error", "error": "连接ID不存在"}

    def cleanup_idle(self) -> dict:
        with self._lock:
            now = time.time()
            before = len(self._pool)
            self._pool = deque(c for c in self._pool
                               if now - c.get("created_at", 0) < self.idle_timeout_sec)
            cleaned = before - len(self._pool)
            self._stats["timed_out"] += cleaned
            return {"cleaned": cleaned, "remaining": len(self._pool)}

    def stats(self) -> dict:
        with self._lock:
            return {
                "max": self.max_connections,
                "active": len(self._active),
                "idle": len(self._pool),
                **self._stats,
            }


class TransactionManager:
    """事务管理器"""

    def __init__(self):
        self._transactions: dict[str, dict] = {}
        self._lock = threading.Lock()

    def begin(self, tx_id: str, isolation: str = "READ_COMMITTED") -> dict:
        with self._lock:
            self._transactions[tx_id] = {
                "state": "active",
                "isolation": isolation,
                "started_at": time.time(),
                "savepoints": [],
                "operations": 0,
            }
            return {"status": "ok", "tx_id": tx_id}

    def savepoint(self, tx_id: str, name: str) -> dict:
        with self._lock:
            tx = self._transactions.get(tx_id)
            if not tx:
                return {"status": "error", "error": "事务不存在"}
            tx["savepoints"].append({"name": name, "at_op": tx["operations"]})
            return {"status": "ok"}

    def commit(self, tx_id: str) -> dict:
        with self._lock:
            tx = self._transactions.pop(tx_id, None)
            if not tx:
                return {"status": "error", "error": "事务不存在"}
            duration = time.time() - tx["started_at"]
            return {"status": "ok", "duration_sec": round(duration, 4),
                    "operations": tx["operations"]}

    def rollback(self, tx_id: str, to_savepoint: str = "") -> dict:
        with self._lock:
            tx = self._transactions.get(tx_id)
            if not tx:
                return {"status": "error", "error": "事务不存在"}
            if to_savepoint:
                sp = next((s for s in tx["savepoints"] if s["name"] == to_savepoint), None)
                if sp:
                    tx["operations"] = sp["at_op"]
                    return {"status": "ok", "rolled_to": to_savepoint}
                return {"status": "error", "error": "savepoint不存在"}
            self._transactions.pop(tx_id)
            return {"status": "ok"}

    def list_active(self) -> list[dict]:
        with self._lock:
            now = time.time()
            return [{"tx_id": k, "duration_sec": round(now - v["started_at"], 2),
                     "operations": v["operations"], "isolation": v["isolation"]}
                    for k, v in self._transactions.items()]


_slow_query = SlowQueryMonitor()
_conn_pool = ConnectionPoolAdv()
_tx_mgr = TransactionManager()
