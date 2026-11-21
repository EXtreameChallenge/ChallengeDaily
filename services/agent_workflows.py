"""
agent_workflows.py — Agent 工作流编排

用途：
    把"多步骤、可暂停、可恢复"的复合任务显式编排成有向图。每个节点要么调用 LLM，
    要么调用工具，要么等待人工确认（human 节点）。执行过程中每个节点结束都把
    状态序列化写入 agent_task_states 表，支持断点恢复。

内置工作流：
    - 制定计划：分析目标(LLM) → 拆解任务(LLM) → 创建待办(tool) → 设置提醒(tool)
                → 同步幕布(tool) → 人工确认(human)
    - 每日复盘：收集数据(tool) → 生成报告(LLM) → 保存日记(tool) → 推送通知(tool)

降级策略：
    - agent_db / agent_tools 未就绪时，使用本模块内置 SQLite 兜底 + 工具执行空壳。
    - LLM 不可用时，LLM 节点退化为把输入原样透传，不阻断流程。
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ── pydantic 可选 ──
try:
    from pydantic import BaseModel, Field
    _PYDANTIC_AVAILABLE = True
except Exception:  # pragma: no cover
    BaseModel = object  # type: ignore
    _PYDANTIC_AVAILABLE = False

# ── 外部模块：try/except 降级 ──
try:
    from db import get_conn
except Exception as _e:  # pragma: no cover
    get_conn = None  # type: ignore
    logger.warning("agent_workflows: 无法导入 db.get_conn: %s", _e)

try:
    import ai_client
except Exception:  # pragma: no cover
    ai_client = None  # type: ignore

try:
    import config
except Exception:  # pragma: no cover
    config = None  # type: ignore

# agent_db 提供任务状态持久化；未就绪时走本模块兜底
try:
    from agent_db import (
        save_task_state as _adb_save_task,
        get_task_state as _adb_get_task,
        update_task_state as _adb_update_task,
        log_audit as _adb_log_audit,
    )
    _AGENT_DB_AVAILABLE = True
except Exception:
    _adb_save_task = None
    _adb_get_task = None
    _adb_update_task = None
    _adb_log_audit = None
    _AGENT_DB_AVAILABLE = False
    logger.info("agent_workflows: agent_db 未就绪，启用内置任务状态存储")

# agent_tools 提供工具执行器映射；未就绪时空壳
try:
    from agent_tools import TOOL_EXECUTOR_MAP  # type: ignore
except Exception:
    TOOL_EXECUTOR_MAP = {}  # type: ignore


# ── WorkflowNode 模型 ─────────────────────────────────────────
if _PYDANTIC_AVAILABLE:

    class WorkflowNode(BaseModel):
        node_id: str
        name: str
        type: str = "llm"            # llm / tool / human
        prompt: str = ""             # llm 节点的 system/user 提示
        tool_name: str = ""          # tool 节点的工具名
        params: dict = Field(default_factory=dict)   # tool 节点的固定参数
        next_node: str = ""          # 下一节点 id（空表示结束）
        condition: str = ""          # 可选："条件表达式字符串"，预留分支能力

        class Config:
            extra = "allow"

else:  # pragma: no cover

    class WorkflowNode:  # type: ignore
        def __init__(self, **kw):
            self.node_id = kw.get("node_id", "")
            self.name = kw.get("name", "")
            self.type = kw.get("type", "llm")
            self.prompt = kw.get("prompt", "")
            self.tool_name = kw.get("tool_name", "")
            self.params = kw.get("params", {}) or {}
            self.next_node = kw.get("next_node", "")
            self.condition = kw.get("condition", "")

        def model_dump(self) -> dict:
            return {
                "node_id": self.node_id, "name": self.name, "type": self.type,
                "prompt": self.prompt, "tool_name": self.tool_name,
                "params": self.params, "next_node": self.next_node,
                "condition": self.condition,
            }


# ── 内置工作流定义 ───────────────────────────────────────────
def _n(node_id: str, name: str, ntype: str, next_node: str,
       prompt: str = "", tool_name: str = "", params: dict | None = None) -> dict:
    """统一构造节点 dict（无论 pydantic 是否可用都返回 dict）。"""
    return {
        "node_id": node_id, "name": name, "type": ntype,
        "prompt": prompt, "tool_name": tool_name,
        "params": params or {}, "next_node": next_node, "condition": "",
    }


WORKFLOWS: dict[str, dict] = {
    "制定计划": {
        "description": "帮用户把一个目标拆解成可执行待办，并设置提醒、同步到幕布",
        "entry": "n1",
        "nodes": [
            _n("n1", "分析目标", "llm", "n2",
               prompt="请分析用户目标，提炼出核心意图与成功标准。"),
            _n("n2", "拆解任务", "llm", "n3",
               prompt="基于分析结果，把目标拆成 3-7 个可执行的子任务。"),
            _n("n3", "创建待办", "tool", "n4", tool_name="create_todo"),
            _n("n4", "设置提醒", "tool", "n5", tool_name="create_reminder"),
            _n("n5", "同步幕布", "tool", "n6", tool_name="mubu_create_doc"),
            _n("n6", "人工确认", "human", "",
               prompt="请用户确认计划是否需要调整。"),
        ],
    },
    "每日复盘": {
        "description": "汇总今日数据，生成复盘报告，保存日记并推送通知",
        "entry": "r1",
        "nodes": [
            _n("r1", "收集数据", "tool", "r2",
               tool_name="get_daily_summary",
               params={"also": ["get_pomodoro_stats"]}),
            _n("r2", "生成报告", "llm", "r3",
               prompt="基于收集到的今日数据，写一段 200 字以内的每日复盘。"),
            _n("r3", "保存日记", "tool", "r4", tool_name="save_diary"),
            _n("r4", "推送通知", "tool", "", tool_name="push_notification"),
        ],
    },
}


# ── 兜底任务状态表 ───────────────────────────────────────────
_TASK_LOCK = threading.Lock()
_TASK_TABLE_INITED = False


def _ensure_task_table() -> bool:
    global _TASK_TABLE_INITED
    if _AGENT_DB_AVAILABLE:
        return True
    if _TASK_TABLE_INITED:
        return True
    if get_conn is None:
        return False
    with _TASK_LOCK:
        if _TASK_TABLE_INITED:
            return True
        try:
            with get_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_task_states (
                        task_id TEXT PRIMARY KEY,
                        workflow_name TEXT NOT NULL,
                        current_node TEXT,
                        state TEXT DEFAULT '{}',
                        status TEXT DEFAULT 'running',
                        created_at TEXT,
                        updated_at TEXT
                    )
                    """
                )
                conn.commit()
            _TASK_TABLE_INITED = True
            return True
        except Exception as e:
            logger.error("agent_workflows: 初始化 agent_task_states 失败: %s", e)
            return False


def _save_task_state(task_id: str, workflow_name: str, current_node: str,
                     state: dict, status: str) -> None:
    """持久化任务状态（agent_db 优先，兜底直写）。"""
    if _AGENT_DB_AVAILABLE and callable(_adb_save_task):
        try:
            _adb_save_task(task_id, workflow_name, current_node,
                           json.dumps(state, ensure_ascii=False, default=str), status)
            return
        except Exception as e:
            logger.warning("agent_workflows: agent_db.save_task_state 失败，降级: %s", e)

    if not _ensure_task_table():
        return
    try:
        now = datetime.now().isoformat(timespec="seconds")
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO agent_task_states
                    (task_id, workflow_name, current_node, state, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    current_node=excluded.current_node,
                    state=excluded.state,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (task_id, workflow_name, current_node,
                 json.dumps(state, ensure_ascii=False, default=str), status, now, now),
            )
            conn.commit()
    except Exception as e:
        logger.error("agent_workflows: 兜底保存任务状态失败: %s", e)


def _get_task_state(task_id: str) -> Optional[dict]:
    if not task_id:
        return None
    if _AGENT_DB_AVAILABLE and callable(_adb_get_task):
        try:
            row = _adb_get_task(task_id)
            if isinstance(row, dict):
                return row
        except Exception as e:
            logger.warning("agent_workflows: agent_db.get_task_state 失败: %s", e)
    if not _ensure_task_table():
        return None
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM agent_task_states WHERE task_id=?", (task_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        if isinstance(d.get("state"), str):
            try:
                d["state"] = json.loads(d["state"])
            except Exception:
                d["state"] = {}
        return d
    except Exception as e:
        logger.error("agent_workflows: 兜底读取任务状态失败: %s", e)
        return None


def _update_task_state(task_id: str, **kwargs) -> None:
    if not task_id or not kwargs:
        return
    if _AGENT_DB_AVAILABLE and callable(_adb_update_task):
        try:
            _adb_update_task(task_id, **kwargs)
            return
        except Exception as e:
            logger.warning("agent_workflows: agent_db.update_task_state 失败: %s", e)
    # 兜底：读出再写回
    cur = _get_task_state(task_id)
    if not cur:
        return
    state = cur.get("state") or {}
    for k, v in kwargs.items():
        if k == "state" and isinstance(v, dict):
            state.update(v)
        else:
            cur[k] = v
    _save_task_state(task_id, cur.get("workflow_name", ""),
                     cur.get("current_node", ""), state, cur.get("status", "running"))


# ── 节点执行器 ───────────────────────────────────────────────
def _run_llm_node(node: dict, state: dict) -> dict:
    """执行 LLM 节点：把 prompt + 已有 state 拼成 messages，调用 ai_client。"""
    prompt = node.get("prompt", "")
    context = json.dumps(state, ensure_ascii=False, default=str)[:1500]
    if ai_client is None or config is None or not getattr(config, "AI_API_KEY", ""):
        # 降级：不调用 LLM，直接把 prompt 作为结果透传
        return {"output": f"[LLM 降级] {prompt}", "node_type": "llm"}
    try:
        params = config.AI_PARAMS.get("agent", {"max_tokens": 800, "temperature": 0.5})
        client = ai_client._get_client()
        resp = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": "你是一个工作流节点执行器，简洁输出。"},
                {"role": "user", "content": f"{prompt}\n\n【已有状态】\n{context}"},
            ],
            max_tokens=params.get("max_tokens", 800),
            temperature=params.get("temperature", 0.5),
        )
        text = (resp.choices[0].message.content or "").strip()
        return {"output": text, "node_type": "llm"}
    except Exception as e:
        logger.warning("agent_workflows: LLM 节点 %s 执行失败: %s", node.get("node_id"), e)
        return {"output": f"[LLM 失败] {e}", "node_type": "llm", "error": str(e)}


def _run_tool_node(node: dict, state: dict) -> dict:
    """执行 tool 节点：从 TOOL_EXECUTOR_MAP 查执行器，未注册则空壳返回。"""
    tool_name = node.get("tool_name", "")
    executor = TOOL_EXECUTOR_MAP.get(tool_name) if isinstance(TOOL_EXECUTOR_MAP, dict) else None
    params = dict(node.get("params") or {})
    params["_state"] = state  # 把当前状态注入
    if executor is None:
        logger.info("agent_workflows: 工具 %s 未注册，空壳返回", tool_name)
        return {"output": f"[工具未注册] {tool_name}", "tool": tool_name, "ok": False}
    try:
        result = executor(**params) if callable(executor) else executor
        return {"output": result, "tool": tool_name, "ok": True}
    except Exception as e:
        logger.warning("agent_workflows: 工具 %s 执行失败: %s", tool_name, e)
        return {"output": str(e), "tool": tool_name, "ok": False, "error": str(e)}


# ── 工作流对外 API ───────────────────────────────────────────
def get_workflow(name: str) -> Optional[dict]:
    """按名称获取工作流定义。"""
    return WORKFLOWS.get(name)


def list_workflows() -> list[dict]:
    """列出所有内置工作流。"""
    return [{"name": k, "description": v.get("description", ""),
             "node_count": len(v.get("nodes", []))}
            for k, v in WORKFLOWS.items()]


def trigger_workflow(workflow_name: str, params: dict | None = None) -> str:
    """触发一个工作流，返回 task_id。"""
    wf = get_workflow(workflow_name)
    if not wf:
        logger.warning("agent_workflows: 未知工作流 %s", workflow_name)
        return ""
    task_id = uuid.uuid4().hex[:16]
    _save_task_state(task_id, workflow_name, wf.get("entry", ""),
                     {"params": params or {}, "history": []}, "running")
    logger.info("agent_workflows: 触发工作流 %s -> task_id=%s", workflow_name, task_id)
    return task_id


def pause_task(task_id: str) -> bool:
    """暂停任务（在下个人工节点或下一轮调度时生效）。"""
    if not task_id:
        return False
    _update_task_state(task_id, status="paused")
    return True


def get_task_status(task_id: str) -> dict:
    """获取任务当前状态。"""
    row = _get_task_state(task_id)
    if not row:
        return {"task_id": task_id, "status": "not_found"}
    return {
        "task_id": task_id,
        "workflow_name": row.get("workflow_name"),
        "current_node": row.get("current_node"),
        "status": row.get("status"),
        "state": row.get("state"),
    }


def execute_workflow(workflow_name: str, initial_params: dict | None = None,
                     on_progress: Optional[Callable[[dict], None]] = None) -> dict:
    """同步执行一个工作流，直到遇到 human 节点或结束。

    on_progress: 每完成一个节点回调一次。
    返回：{"task_id", "status": "completed"|"paused"|"failed", "state": ..., "paused_node": ...}
    """
    wf = get_workflow(workflow_name)
    if not wf:
        return {"status": "failed", "error": f"未知工作流: {workflow_name}"}

    task_id = trigger_workflow(workflow_name, initial_params)
    return _resume(task_id, on_progress=on_progress)


def resume_task(task_id: str, on_progress: Optional[Callable[[dict], None]] = None,
                user_input: str = "") -> dict:
    """从断点恢复执行。如果是 human 节点，user_input 作为用户确认结果注入。"""
    return _resume(task_id, on_progress=on_progress, user_input=user_input)


def _resume(task_id: str, on_progress: Optional[Callable[[dict], None]] = None,
            user_input: str = "") -> dict:
    """内部：从 task_id 对应的 current_node 开始继续跑。"""
    row = _get_task_state(task_id)
    if not row:
        return {"status": "not_found", "task_id": task_id}

    workflow_name = row.get("workflow_name", "")
    wf = get_workflow(workflow_name)
    if not wf:
        return {"status": "failed", "error": f"工作流定义缺失: {workflow_name}"}

    nodes_by_id = {n["node_id"]: n for n in wf.get("nodes", [])}
    state = dict(row.get("state") or {})
    if user_input:
        state.setdefault("human_inputs", []).append(user_input)

    current_id = row.get("current_node") or wf.get("entry")
    max_steps = len(wf.get("nodes", [])) + 2  # 防死循环
    steps = 0

    while current_id and steps < max_steps:
        steps += 1
        node = nodes_by_id.get(current_id)
        if not node:
            _update_task_state(task_id, status="failed")
            return {"status": "failed", "error": f"节点不存在: {current_id}",
                    "task_id": task_id}

        node_type = node.get("type", "llm")
        progress = {"task_id": task_id, "node_id": current_id,
                    "node_name": node.get("name"), "type": node_type}

        # ── human 节点：暂停，等待外部确认 ──
        if node_type == "human":
            _update_task_state(task_id, current_node=current_id, status="paused",
                               state={"state": state, "waiting_for": "user"})
            progress["status"] = "paused"
            if on_progress:
                try:
                    on_progress(progress)
                except Exception:
                    pass
            return {"status": "paused", "task_id": task_id,
                    "paused_node": current_id, "state": state}

        # ── llm / tool 节点 ──
        if node_type == "llm":
            result = _run_llm_node(node, state)
        else:
            result = _run_tool_node(node, state)

        state.setdefault("history", []).append({
            "node_id": current_id, "name": node.get("name"),
            "result": result, "ts": time.time(),
        })
        _update_task_state(task_id, current_node=current_id, status="running",
                           state={"state": state})

        progress["result"] = result
        if on_progress:
            try:
                on_progress(progress)
            except Exception:
                pass

        current_id = node.get("next_node", "")

    # 流程结束
    _update_task_state(task_id, current_node="", status="completed",
                       state={"state": state})
    return {"status": "completed", "task_id": task_id, "state": state}


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    print("内置工作流：", list_workflows())
