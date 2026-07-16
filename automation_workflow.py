"""
P201-P209: 自动化工作流引擎
- P201: 工作流定义
- P202: 任务节点
- P203: 条件分支
- P204: 循环控制
- P205: 并行执行
- P206: 错误处理
- P207: 重试策略
- P208: 超时控制
- P209: 工作流调度
"""
import logging
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P201: 工作流定义 ──────────────────────────
class Workflow:
    """工作流定义"""
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.nodes: dict[str, dict] = {}
        self.edges: list[tuple[str, str, str]] = []  # (from, to, condition)
        self.start_node: str = ""
        self._lock = threading.Lock()

    def add_node(self, node_id: str, action: Callable, name: str = "") -> None:
        with self._lock:
            self.nodes[node_id] = {
                "id": node_id, "action": action, "name": name or node_id,
                "status": "pending", "result": None, "error": None
            }
            if not self.start_node:
                self.start_node = node_id

    def add_edge(self, from_id: str, to_id: str, condition: str = "always") -> None:
        with self._lock:
            self.edges.append((from_id, to_id, condition))

    def get_next_nodes(self, node_id: str, result: Any = None) -> list[str]:
        next_ids = []
        for from_id, to_id, cond in self.edges:
            if from_id != node_id:
                continue
            if cond == "always" or cond == "success" and result is not None:
                next_ids.append(to_id)
            elif cond == "failure" and result is None:
                next_ids.append(to_id)
        return next_ids

    def to_dict(self) -> dict:
        return {
            "name": self.name, "description": self.description,
            "nodes": {k: {"name": v["name"], "status": v["status"]}
                      for k, v in self.nodes.items()},
            "edges": [{"from": f, "to": t, "condition": c} for f, t, c in self.edges],
            "start_node": self.start_node
        }


# ─── P202: 任务节点执行器 ──────────────────────────
class TaskExecutor:
    """任务节点执行"""
    def __init__(self):
        self._lock = threading.Lock()
        self._executions: deque = deque(maxlen=500)

    def execute_node(self, workflow: Workflow, node_id: str,
                     context: dict = None) -> dict:
        node = workflow.nodes.get(node_id)
        if not node:
            return {"status": "error", "error": "节点不存在"}
        context = context or {}
        start_time = time.time()
        try:
            result = node["action"](context)
            node["status"] = "completed"
            node["result"] = result
            status = "completed"
        except Exception as e:
            node["status"] = "failed"
            node["error"] = str(e)
            result = None
            status = "failed"
        exec_record = {
            "workflow": workflow.name, "node": node_id,
            "status": status, "duration_ms": (time.time() - start_time) * 1000,
            "timestamp": datetime.now().isoformat()
        }
        with self._lock:
            self._executions.append(exec_record)
        return {"status": status, "result": result, "node": node_id}

    def get_history(self, limit: int = 50) -> list[dict]:
        with self._lock:
            history = list(self._executions)
        history.reverse()
        return history[:limit]


_executor = TaskExecutor()


# ─── P203: 条件分支 ──────────────────────────
class ConditionBranch:
    """条件分支评估"""
    @staticmethod
    def evaluate(condition: str, context: dict) -> bool:
        if condition == "always":
            return True
        if condition == "never":
            return False
        if condition.startswith("context:"):
            key = condition[8:]
            return bool(context.get(key))
        if condition.startswith("eq:"):
            parts = condition[3:].split("=", 1)
            if len(parts) == 2:
                return str(context.get(parts[0])) == parts[1]
        if condition.startswith("gt:"):
            parts = condition[3:].split(">", 1)
            if len(parts) == 2:
                try:
                    return float(context.get(parts[0], 0)) > float(parts[1])
                except ValueError:
                    return False
        if condition.startswith("lt:"):
            parts = condition[3:].split("<", 1)
            if len(parts) == 2:
                try:
                    return float(context.get(parts[0], 0)) < float(parts[1])
                except ValueError:
                    return False
        return False


# ─── P204: 循环控制 ──────────────────────────
class LoopController:
    """循环执行控制"""
    def __init__(self):
        self._active_loops: dict[str, dict] = {}

    def start_loop(self, loop_id: str, max_iterations: int = 100,
                   interval: float = 0) -> str:
        self._active_loops[loop_id] = {
            "iteration": 0, "max": max_iterations,
            "interval": interval, "started_at": time.time(),
            "stopped": False
        }
        return loop_id

    def should_continue(self, loop_id: str) -> bool:
        loop = self._active_loops.get(loop_id)
        if not loop or loop["stopped"]:
            return False
        if loop["iteration"] >= loop["max"]:
            return False
        loop["iteration"] += 1
        return True

    def stop_loop(self, loop_id: str) -> None:
        if loop_id in self._active_loops:
            self._active_loops[loop_id]["stopped"] = True

    def get_status(self, loop_id: str) -> dict:
        loop = self._active_loops.get(loop_id)
        if not loop:
            return {}
        return {
            "iteration": loop["iteration"], "max": loop["max"],
            "stopped": loop["stopped"],
            "elapsed": time.time() - loop["started_at"]
        }


_loop_ctrl = LoopController()


# ─── P205: 并行执行 ──────────────────────────
class ParallelExecutor:
    """并行任务执行"""
    def __init__(self, max_workers: int = 4):
        self._max_workers = max_workers
        self._lock = threading.Lock()

    def run_parallel(self, tasks: list[Callable],
                     context: dict = None) -> list[dict]:
        import concurrent.futures
        results = []
        context = context or {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(task, context): i for i, task in enumerate(tasks)}
            for future in concurrent.futures.as_completed(futures):
                idx = futures[future]
                try:
                    result = future.result()
                    results.append({"index": idx, "status": "ok", "result": result})
                except Exception as e:
                    results.append({"index": idx, "status": "error", "error": str(e)})
        results.sort(key=lambda x: x["index"])
        return results


_parallel_exec = ParallelExecutor()


# ─── P206-P207: 错误处理与重试 ──────────────────────────
class RetryPolicy:
    """重试策略"""
    def __init__(self):
        self._policies: dict[str, dict] = {}

    def set_policy(self, name: str, max_retries: int = 3,
                   backoff: float = 1.0, backoff_factor: float = 2.0,
                   max_backoff: float = 60.0) -> None:
        self._policies[name] = {
            "max_retries": max_retries, "backoff": backoff,
            "backoff_factor": backoff_factor, "max_backoff": max_backoff,
            "attempts": 0
        }

    def should_retry(self, name: str) -> bool:
        policy = self._policies.get(name)
        if not policy:
            return False
        policy["attempts"] += 1
        return policy["attempts"] <= policy["max_retries"]

    def get_delay(self, name: str) -> float:
        policy = self._policies.get(name)
        if not policy:
            return 0
        delay = policy["backoff"] * (policy["backoff_factor"] ** (policy["attempts"] - 1))
        return min(delay, policy["max_backoff"])

    def reset(self, name: str) -> None:
        if name in self._policies:
            self._policies[name]["attempts"] = 0


_retry_policy = RetryPolicy()


# ─── P208: 超时控制 ──────────────────────────
class TimeoutController:
    """超时控制"""
    @staticmethod
    def run_with_timeout(func: Callable, timeout: float,
                         context: dict = None) -> dict:
        import concurrent.futures
        context = context or {}
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(func, context)
                result = future.result(timeout=timeout)
                return {"status": "ok", "result": result}
        except concurrent.futures.TimeoutExpired:
            return {"status": "timeout", "error": f"超时({timeout}s)"}
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ─── P209: 工作流调度 ──────────────────────────
class WorkflowScheduler:
    """工作流调度器"""
    def __init__(self):
        self._schedules: dict[str, dict] = {}
        self._lock = threading.Lock()

    def schedule(self, name: str, workflow_name: str,
                 cron: str = "", delay: float = 0,
                 repeat: bool = False, interval: float = 0) -> None:
        with self._lock:
            self._schedules[name] = {
                "workflow": workflow_name, "cron": cron,
                "delay": delay, "repeat": repeat, "interval": interval,
                "next_run": time.time() + delay if delay else 0,
                "last_run": None, "run_count": 0,
                "enabled": True
            }

    def get_due(self) -> list[str]:
        now = time.time()
        due = []
        with self._lock:
            for name, sched in self._schedules.items():
                if not sched["enabled"]:
                    continue
                if sched["next_run"] and now >= sched["next_run"]:
                    due.append(name)
        return due

    def mark_run(self, name: str) -> None:
        with self._lock:
            sched = self._schedules.get(name)
            if sched:
                sched["last_run"] = datetime.now().isoformat()
                sched["run_count"] += 1
                if sched["repeat"]:
                    sched["next_run"] = time.time() + sched["interval"]
                else:
                    sched["next_run"] = 0
                    sched["enabled"] = False

    def list_schedules(self) -> dict:
        with self._lock:
            return {k: {"workflow": v["workflow"], "enabled": v["enabled"],
                        "run_count": v["run_count"], "last_run": v["last_run"]}
                    for k, v in self._schedules.items()}

    def toggle(self, name: str, enabled: bool) -> bool:
        with self._lock:
            if name in self._schedules:
                self._schedules[name]["enabled"] = enabled
                return True
            return False


_scheduler = WorkflowScheduler()


# ─── 工作流引擎 ──────────────────────────
class WorkflowEngine:
    """工作流执行引擎"""
    def __init__(self):
        self._workflows: dict[str, Workflow] = {}
        self._lock = threading.Lock()

    def register(self, workflow: Workflow) -> None:
        with self._lock:
            self._workflows[workflow.name] = workflow

    def get(self, name: str) -> Workflow | None:
        with self._lock:
            return self._workflows.get(name)

    def run(self, name: str, context: dict = None) -> dict:
        wf = self.get(name)
        if not wf:
            return {"status": "error", "error": "工作流不存在"}
        context = context or {}
        results = []
        current = wf.start_node
        visited = set()
        while current and current not in visited:
            visited.add(current)
            exec_result = _executor.execute_node(wf, current, context)
            results.append(exec_result)
            if exec_result["status"] == "failed":
                break
            next_nodes = wf.get_next_nodes(current, exec_result.get("result"))
            current = next_nodes[0] if next_nodes else ""
        return {"status": "completed" if all(r["status"] == "completed" for r in results) else "failed",
                "results": results, "workflow": name}

    def list_workflows(self) -> list[str]:
        with self._lock:
            return list(self._workflows.keys())


_engine = WorkflowEngine()
