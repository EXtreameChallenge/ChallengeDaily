"""
ChallengeDaily — Agent 系统专用数据库表与访问层

本模块负责 Agent 相关的三张表：
  - agent_skills    : 技能库（从历史对话中沉淀的可复用工具编排技能）
  - agent_task_states: 工作流任务状态机（Planner→Executor→Reviewer 等多步流程的断点续跑）
  - agent_audit_log  : 工具调用审计日志（谁、在什么风险级别下、调用了什么、耗时多久）

设计要点：
  1. 全部复用 db.get_conn() 的线程局部连接，不另开连接池；
  2. 所有写操作幂等建表（CREATE TABLE IF NOT EXISTS），首次调用自动初始化；
  3. 任何异常都降级为“不影响主流程”——记日志、返回空值/False，绝不让 Agent 崩溃；
  4. JSON 字段统一用 json.dumps/loads，保证跨版本可读。
"""
import json
import logging
import uuid
from datetime import datetime

import db

logger = logging.getLogger(__name__)


def _now() -> str:
    """当前本地时间字符串（与项目其它表保持一致）"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_agent_db() -> None:
    """幂等创建 Agent 相关三张表。

    在服务启动或首次使用 Agent 时调用，重复调用不会报错。
    """
    try:
        with db.get_conn() as conn:
            # ── 技能库表 ──
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_skills (
                    id               TEXT PRIMARY KEY,
                    name             TEXT NOT NULL,
                    description      TEXT DEFAULT '',
                    trigger_keywords TEXT DEFAULT '[]',   -- JSON 数组：触发关键词
                    tool_sequence    TEXT DEFAULT '[]',   -- JSON 数组：工具调用序列
                    decisions        TEXT DEFAULT '[]',   -- JSON 数组：中间决策记录
                    pitfalls         TEXT DEFAULT '',     -- 沉淀的坑/注意事项
                    status           TEXT DEFAULT 'pending', -- pending/approved/rejected
                    created_at       TEXT,
                    updated_at       TEXT
                )
                """
            )
            # ── 工作流任务状态表 ──
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_task_states (
                    task_id       TEXT PRIMARY KEY,
                    workflow_name TEXT DEFAULT '',
                    current_node  TEXT DEFAULT '',
                    state         TEXT DEFAULT '{}',     -- JSON：任意中间状态
                    status        TEXT DEFAULT 'running', -- running/paused/completed/failed
                    created_at    TEXT,
                    updated_at    TEXT
                )
                """
            )
            # ── 工具调用审计日志表 ──
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_audit_log (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id       TEXT DEFAULT '',
                    tool_name      TEXT DEFAULT '',
                    risk_level     TEXT DEFAULT 'READ_ONLY',
                    params         TEXT DEFAULT '{}',     -- JSON：入参快照
                    result_preview TEXT DEFAULT '',        -- 结果截断预览（不存全量，防膨胀）
                    confirmed      INTEGER DEFAULT 0,      -- 0=未确认直接执行 1=用户确认后执行
                    cost_ms        INTEGER DEFAULT 0,       -- 耗时毫秒
                    created_at     TEXT
                )
            """
            )
            # 常用查询索引
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_skills_status ON agent_skills(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_task_status ON agent_task_states(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_audit_tool ON agent_audit_log(tool_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_agent_audit_created ON agent_audit_log(created_at)")
            conn.commit()
        logger.info("Agent 数据表初始化完成（agent_skills/agent_task_states/agent_audit_log）")
    except Exception as e:
        # 建表失败不致命：Agent 相关功能降级，但不影响主程序
        logger.warning(f"init_agent_db 失败（Agent 功能将降级）: {e}")


# ═══════════════════════════════════════════════════════════════
# 技能库 CRUD
# ═══════════════════════════════════════════════════════════════

def save_skill(name: str, description: str = "", trigger_keywords=None,
               tool_sequence=None, decisions=None, pitfalls: str = "",
               status: str = "pending", skill_id: str = "") -> str:
    """保存一条技能，返回技能 id。id 为空时自动生成。"""
    init_agent_db()
    sid = skill_id or str(uuid.uuid4())
    now = _now()
    try:
        with db.get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_skills
                    (id, name, description, trigger_keywords, tool_sequence, decisions,
                     pitfalls, status, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sid, name, description,
                    json.dumps(trigger_keywords or [], ensure_ascii=False),
                    json.dumps(tool_sequence or [], ensure_ascii=False),
                    json.dumps(decisions or [], ensure_ascii=False),
                    pitfalls, status, now, now,
                ),
            )
            conn.commit()
        return sid
    except Exception as e:
        logger.warning(f"save_skill 失败: {e}")
        return ""


def list_skills(status: str | None = None) -> list[dict]:
    """列出技能，可按状态过滤。返回的 JSON 字段已反序列化。"""
    init_agent_db()
    try:
        with db.get_conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM agent_skills WHERE status=? ORDER BY updated_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_skills ORDER BY updated_at DESC"
                ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                for k in ("trigger_keywords", "tool_sequence", "decisions"):
                    try:
                        d[k] = json.loads(d.get(k) or "[]")
                    except Exception:
                        d[k] = []
                result.append(d)
            return result
    except Exception as e:
        logger.warning(f"list_skills 失败: {e}")
        return []


def get_skill(skill_id: str) -> dict | None:
    """按 id 获取单条技能，不存在返回 None。"""
    init_agent_db()
    try:
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM agent_skills WHERE id=?", (skill_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            for k in ("trigger_keywords", "tool_sequence", "decisions"):
                try:
                    d[k] = json.loads(d.get(k) or "[]")
                except Exception:
                    d[k] = []
            return d
    except Exception as e:
        logger.warning(f"get_skill 失败: {e}")
        return None


def update_skill_status(skill_id: str, status: str) -> bool:
    """更新技能审核状态（pending/approved/rejected）。"""
    init_agent_db()
    if status not in ("pending", "approved", "rejected"):
        logger.warning(f"update_skill_status 非法状态: {status}")
        return False
    try:
        with db.get_conn() as conn:
            conn.execute(
                "UPDATE agent_skills SET status=?, updated_at=? WHERE id=?",
                (status, _now(), skill_id),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.warning(f"update_skill_status 失败: {e}")
        return False


def delete_skill(skill_id: str) -> bool:
    """删除技能。"""
    init_agent_db()
    try:
        with db.get_conn() as conn:
            conn.execute("DELETE FROM agent_skills WHERE id=?", (skill_id,))
            conn.commit()
        return True
    except Exception as e:
        logger.warning(f"delete_skill 失败: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# 工作流任务状态
# ═══════════════════════════════════════════════════════════════

def save_task_state(task_id: str, workflow_name: str, current_node: str,
                    state: dict | None = None, status: str = "running") -> bool:
    """保存/覆盖一个工作流任务的状态（用于断点续跑）。"""
    init_agent_db()
    now = _now()
    try:
        with db.get_conn() as conn:
            # created_at 用 COALESCE 保留原记录创建时间（UPSERT 不覆盖），updated_at 每次刷新
            conn.execute(
                """
                INSERT OR REPLACE INTO agent_task_states
                    (task_id, workflow_name, current_node, state, status, created_at, updated_at)
                VALUES (?,?,?,?,?, COALESCE((SELECT created_at FROM agent_task_states WHERE task_id=?), ?), ?)
                """,
                (
                    task_id, workflow_name, current_node,
                    json.dumps(state or {}, ensure_ascii=False),
                    status, task_id, now, now,
                ),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.warning(f"save_task_state 失败: {e}")
        return False


def get_task_state(task_id: str) -> dict | None:
    """获取任务状态，不存在返回 None。"""
    init_agent_db()
    try:
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM agent_task_states WHERE task_id=?", (task_id,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["state"] = json.loads(d.get("state") or "{}")
            except Exception:
                d["state"] = {}
            return d
    except Exception as e:
        logger.warning(f"get_task_state 失败: {e}")
        return None


def update_task_state(task_id: str, current_node: str | None = None,
                      state: dict | None = None, status: str | None = None) -> bool:
    """局部更新任务状态字段（只更新传入的非 None 字段）。"""
    init_agent_db()
    try:
        sets = []
        params = []
        if current_node is not None:
            sets.append("current_node=?")
            params.append(current_node)
        if state is not None:
            sets.append("state=?")
            params.append(json.dumps(state, ensure_ascii=False))
        if status is not None:
            sets.append("status=?")
            params.append(status)
        if not sets:
            return False
        sets.append("updated_at=?")
        params.append(_now())
        params.append(task_id)
        with db.get_conn() as conn:
            conn.execute(
                f"UPDATE agent_task_states SET {','.join(sets)} WHERE task_id=?",
                params,
            )
            conn.commit()
        return True
    except Exception as e:
        logger.warning(f"update_task_state 失败: {e}")
        return False


def list_task_states(status: str | None = None) -> list[dict]:
    """列出任务状态，可按状态过滤。"""
    init_agent_db()
    try:
        with db.get_conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM agent_task_states WHERE status=? ORDER BY updated_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_task_states ORDER BY updated_at DESC"
                ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["state"] = json.loads(d.get("state") or "{}")
                except Exception:
                    d["state"] = {}
                result.append(d)
            return result
    except Exception as e:
        logger.warning(f"list_task_states 失败: {e}")
        return []


# ═══════════════════════════════════════════════════════════════
# 审计日志与指标
# ═══════════════════════════════════════════════════════════════

def log_audit(trace_id: str, tool_name: str, risk_level: str, params=None,
              result_preview: str = "", confirmed: int = 0, cost_ms: int = 0) -> int:
    """写一条工具调用审计日志，返回自增 id。"""
    init_agent_db()
    try:
        with db.get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO agent_audit_log
                    (trace_id, tool_name, risk_level, params, result_preview, confirmed, cost_ms, created_at)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (
                    trace_id, tool_name, risk_level,
                    json.dumps(params or {}, ensure_ascii=False)[:2000],
                    (result_preview or "")[:500],
                    int(confirmed), int(cost_ms), _now(),
                ),
            )
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.warning(f"log_audit 失败: {e}")
        return 0


def get_audit_logs(limit: int = 100, tool_name: str | None = None) -> list[dict]:
    """查询审计日志（最新在前），可按工具名过滤。"""
    init_agent_db()
    try:
        with db.get_conn() as conn:
            if tool_name:
                rows = conn.execute(
                    "SELECT * FROM agent_audit_log WHERE tool_name=? ORDER BY id DESC LIMIT ?",
                    (tool_name, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_audit_log ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["params"] = json.loads(d.get("params") or "{}")
                except Exception:
                    d["params"] = {}
                result.append(d)
            return result
    except Exception as e:
        logger.warning(f"get_audit_logs 失败: {e}")
        return []


def get_agent_metrics() -> dict:
    """汇总 Agent 运行指标，供 /api/agent/metrics 使用。

    返回：总工具调用数、工具分布、平均耗时、危险操作数、失败率、技能数等。
    任何异常都降级为返回空指标，不影响主流程。
    """
    init_agent_db()
    metrics = {
        "total_tool_calls": 0,
        "tool_distribution": {},
        "avg_cost_ms": 0,
        "dangerous_calls": 0,
        "confirmed_calls": 0,
        "skill_count": 0,
        "approved_skills": 0,
        "active_tasks": 0,
    }
    try:
        with db.get_conn() as conn:
            # 工具调用总量与平均耗时
            row = conn.execute(
                "SELECT COUNT(*) AS cnt, AVG(cost_ms) AS avg_ms FROM agent_audit_log"
            ).fetchone()
            if row:
                metrics["total_tool_calls"] = row["cnt"] or 0
                metrics["avg_cost_ms"] = round(row["avg_ms"] or 0, 1)
            # 危险/需确认操作数
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM agent_audit_log WHERE risk_level='DANGEROUS'"
            ).fetchone()
            if row:
                metrics["dangerous_calls"] = row["cnt"] or 0
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM agent_audit_log WHERE confirmed=1"
            ).fetchone()
            if row:
                metrics["confirmed_calls"] = row["cnt"] or 0
            # 工具分布（最近 500 条内 Top10）
            rows = conn.execute(
                """SELECT tool_name, COUNT(*) AS cnt FROM agent_audit_log
                   WHERE id > (SELECT COALESCE(MAX(id)-500,0) FROM agent_audit_log)
                   GROUP BY tool_name ORDER BY cnt DESC LIMIT 10"""
            ).fetchall()
            metrics["tool_distribution"] = {r["tool_name"]: r["cnt"] for r in rows}
            # 技能数
            row = conn.execute("SELECT COUNT(*) AS cnt FROM agent_skills").fetchone()
            if row:
                metrics["skill_count"] = row["cnt"] or 0
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM agent_skills WHERE status='approved'"
            ).fetchone()
            if row:
                metrics["approved_skills"] = row["cnt"] or 0
            # 活跃任务数
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM agent_task_states WHERE status='running'"
            ).fetchone()
            if row:
                metrics["active_tasks"] = row["cnt"] or 0
    except Exception as e:
        logger.warning(f"get_agent_metrics 失败: {e}")
    return metrics
