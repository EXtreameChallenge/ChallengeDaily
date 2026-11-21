"""
skill_library.py — Agent 自进化技能库

设计目标：
    Agent 在完成一次复杂任务（多次工具调用）后，自动反思并沉淀为"技能卡片"。
    下次遇到相似意图时，把已审核技能注入 system prompt，让 Agent 少走弯路。

数据流：
    对话历史 + 工具调用日志
        └─► extract_skill_from_conversation()  (LLM 反思，低 temperature)
                └─► save_skill()  (落库，默认 status=pending)
                        └─► approve_skill()  (人工/自动审核)
                                └─► match_skills() + inject_skills_to_prompt()
                                        (下次相似意图命中并注入 prompt)

降级策略：
    - agent_db 模块未就绪时，本模块自带基于 db.get_conn() 的 SQLite 兜底实现，
      表结构与 agent_db.save_skill 约定一致，后续 agent_db 上线后无缝切换。
    - LLM 不可用（无 API key / 熔断）时，extract 失败返回空 dict，不抛异常。
    - pydantic 未安装时，回退到普通 dataclass 风格的轻量模型。
"""
from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── pydantic 可选依赖（项目 requirements 已声明，本地未装时优雅降级） ──
try:
    from pydantic import BaseModel, Field
    _PYDANTIC_AVAILABLE = True
except Exception:  # pragma: no cover
    BaseModel = object  # type: ignore
    _PYDANTIC_AVAILABLE = False
    logger.info("skill_library: pydantic 未安装，回退到轻量模型")


# ── 外部模块：try/except 降级 ──
try:
    from db import get_conn
except Exception as _e:  # pragma: no cover
    get_conn = None  # type: ignore
    logger.warning("skill_library: 无法导入 db.get_conn，技能持久化将不可用: %s", _e)

try:
    import ai_client
except Exception as _e:  # pragma: no cover
    ai_client = None  # type: ignore
    logger.warning("skill_library: 无法导入 ai_client，LLM 反思将不可用: %s", _e)

try:
    import config
except Exception:  # pragma: no cover
    config = None  # type: ignore

# 优先使用 agent_db 提供的统一存储；未就绪时走本模块兜底
try:
    from agent_db import (
        save_skill as _agent_db_save_skill,
        list_skills as _agent_db_list_skills,
        get_skill as _agent_db_get_skill,
        update_skill_status as _agent_db_update_skill_status,
        delete_skill as _agent_db_delete_skill,
        init_agent_db as _agent_db_init,
    )
    _AGENT_DB_AVAILABLE = True
except Exception:
    _agent_db_save_skill = None
    _agent_db_list_skills = None
    _agent_db_get_skill = None
    _agent_db_update_skill_status = None
    _agent_db_delete_skill = None
    _agent_db_init = None
    _AGENT_DB_AVAILABLE = False
    logger.info("skill_library: agent_db 未就绪，启用本模块内置 SQLite 兜底存储")


# ── SkillCard 模型 ─────────────────────────────────────────────
_VALID_STATUS = {"pending", "approved", "rejected"}


if _PYDANTIC_AVAILABLE:

    class SkillCard(BaseModel):
        """一张可复用的"技能卡片"，描述一类任务的标准打法。"""
        id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
        name: str = ""
        description: str = ""
        trigger_keywords: list[str] = Field(default_factory=list)
        tool_sequence: list[str] = Field(default_factory=list)
        decisions: list[str] = Field(default_factory=list)
        pitfalls: list[str] = Field(default_factory=list)
        status: str = "pending"
        created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
        updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

        class Config:
            # 允许任意额外字段，兼容未来扩展
            extra = "allow"

else:  # pragma: no cover - 本地无 pydantic 时的兜底

    class SkillCard:  # type: ignore
        """pydantic 缺失时的最小兼容模型，仅保留 to_dict/构造参数。"""

        def __init__(self, **data):
            self.id = data.get("id") or uuid.uuid4().hex[:12]
            self.name = data.get("name", "")
            self.description = data.get("description", "")
            self.trigger_keywords = data.get("trigger_keywords") or []
            self.tool_sequence = data.get("tool_sequence") or []
            self.decisions = data.get("decisions") or []
            self.pitfalls = data.get("pitfalls") or []
            self.status = data.get("status", "pending")
            now = datetime.now().isoformat(timespec="seconds")
            self.created_at = data.get("created_at", now)
            self.updated_at = data.get("updated_at", now)

        def model_dump(self) -> dict:
            return {
                "id": self.id,
                "name": self.name,
                "description": self.description,
                "trigger_keywords": self.trigger_keywords,
                "tool_sequence": self.tool_sequence,
                "decisions": self.decisions,
                "pitfalls": self.pitfalls,
                "status": self.status,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }


# ── 兜底存储：agent_skills 表 ──────────────────────────────────
_TABLE_INIT_LOCK = threading.Lock()
_TABLE_INITED = False


def _ensure_table() -> bool:
    """兜底场景下初始化 agent_skills 表（仅当 agent_db 未就绪时使用）。"""
    global _TABLE_INITED
    if _AGENT_DB_AVAILABLE:
        return True
    if _TABLE_INITED:
        return True
    if get_conn is None:
        return False
    with _TABLE_INIT_LOCK:
        if _TABLE_INITED:
            return True
        try:
            with get_conn() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS agent_skills (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT DEFAULT '',
                        trigger_keywords TEXT DEFAULT '[]',
                        tool_sequence TEXT DEFAULT '[]',
                        decisions TEXT DEFAULT '[]',
                        pitfalls TEXT DEFAULT '[]',
                        status TEXT DEFAULT 'pending',
                        created_at TEXT,
                        updated_at TEXT
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_agent_skills_status ON agent_skills(status)"
                )
                conn.commit()
            _TABLE_INITED = True
            logger.info("skill_library: 兜底表 agent_skills 已就绪")
            return True
        except Exception as e:
            logger.error("skill_library: 初始化 agent_skills 表失败: %s", e)
            return False


def _dumps_list(v: Any) -> str:
    """列表字段序列化为 JSON 字符串（DB 列存 TEXT）。"""
    try:
        if isinstance(v, str):
            return v
        return json.dumps(v or [], ensure_ascii=False)
    except Exception:
        return "[]"


def _loads_list(v: Any) -> list:
    """从 DB TEXT 列反序列化为 list。"""
    if not v:
        return []
    if isinstance(v, list):
        return v
    try:
        return json.loads(v)
    except Exception:
        return []


def _row_to_card(row: Any) -> dict:
    """sqlite.Row -> SkillCard dict。"""
    d = dict(row)
    d["trigger_keywords"] = _loads_list(d.get("trigger_keywords"))
    d["tool_sequence"] = _loads_list(d.get("tool_sequence"))
    d["decisions"] = _loads_list(d.get("decisions"))
    d["pitfalls"] = _loads_list(d.get("pitfalls"))
    return d


# ── LLM 反思：从对话 + 工具调用中抽取技能 ──────────────────────
_REFLECT_PROMPT = """你是一名资深 Agent 架构师。请基于下面这次完整任务执行过程，
反思并提炼成一张"可复用技能卡片"，供以后遇到相似任务时直接复用。

【任务对话历史】
{conversation_history}

【工具调用日志】
{tool_calls}

请只输出 JSON，字段如下：
{{
  "name": "技能短名（<=12字，动宾结构，例如：制定周计划）",
  "description": "这个技能适用什么场景，一句话说清",
  "trigger_keywords": ["命中用户意图时的关键词，3-6个"],
  "tool_sequence": ["按顺序调用的工具名，字符串数组"],
  "decisions": ["执行过程中的关键判断分支，例如：若X则走Y"],
  "pitfalls": ["容易踩的坑，例如：时间范围必须本地时区"]
}}
要求：
- 不要编造对话里没出现过的工具。
- trigger_keywords 用中文常见说法，覆盖用户可能的问法。
- 输出必须是合法 JSON，不要 markdown 代码块，不要解释。
"""


def _call_llm_for_reflection(conversation_history: str, tool_calls: str) -> Optional[dict]:
    """调用 ai_client._get_client() 让 LLM 反思生成技能卡片 JSON。失败返回 None。"""
    if ai_client is None or config is None:
        logger.info("skill_library: ai_client/config 不可用，跳过 LLM 反思")
        return None
    if not getattr(config, "AI_API_KEY", ""):
        logger.info("skill_library: 未配置 AI_API_KEY，跳过 LLM 反思")
        return None

    try:
        # 低 temperature，保证 JSON 结构稳定
        params = config.AI_PARAMS.get("agent", {"max_tokens": 800, "temperature": 0.3})
        # 反思任务更接近结构化抽取，强制低温
        temperature = min(params.get("temperature", 0.3), 0.3)
        max_tokens = max(params.get("max_tokens", 800), 1200)

        prompt = _REFLECT_PROMPT.format(
            conversation_history=(conversation_history or "")[:2000],
            tool_calls=(tool_calls or "")[:2000],
        )
        client = ai_client._get_client()
        resp = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": "你是 Agent 技能沉淀专家，只输出合法 JSON。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # 复用 ai_client 里的 JSON 提取逻辑（若存在）
        parser = getattr(ai_client, "_parse_json_response", None)
        if callable(parser):
            data = parser(raw)
        else:
            try:
                data = json.loads(raw)
            except Exception:
                data = None
        if isinstance(data, dict) and data.get("name"):
            return data
        logger.warning("skill_library: LLM 反思返回内容不合法: %s", raw[:120])
        return None
    except Exception as e:
        logger.warning("skill_library: LLM 反思调用失败: %s", e)
        return None


def extract_skill_from_conversation(conversation_history: str, tool_calls: str) -> dict:
    """从对话历史 + 工具调用日志中，用 LLM 反思提炼一张技能卡片。

    返回：dict（符合 SkillCard 字段）；LLM 不可用时返回空 dict。
    """
    data = _call_llm_for_reflection(conversation_history, tool_calls)
    if not data:
        return {}
    # 字段归一化 + 防御
    card = {
        "name": str(data.get("name", ""))[:60],
        "description": str(data.get("description", ""))[:300],
        "trigger_keywords": [str(k) for k in (data.get("trigger_keywords") or [])][:20],
        "tool_sequence": [str(t) for t in (data.get("tool_sequence") or [])][:20],
        "decisions": [str(d) for d in (data.get("decisions") or [])][:20],
        "pitfalls": [str(p) for p in (data.get("pitfalls") or [])][:20],
        "status": "pending",
    }
    if not card["name"]:
        return {}
    return card


# ── CRUD：优先走 agent_db，否则走兜底 SQLite ──────────────────
def save_skill(skill_data: dict) -> str:
    """保存一张技能卡片（默认 status=pending 待审核），返回 skill_id。"""
    if not isinstance(skill_data, dict) or not skill_data.get("name"):
        logger.warning("skill_library.save_skill: 缺少 name，拒绝保存")
        return ""

    # 1) 优先走 agent_db（签名：save_skill(name, description, trigger_keywords, tool_sequence, decisions, pitfalls, status)）
    if _AGENT_DB_AVAILABLE and callable(_agent_db_save_skill):
        try:
            sid = _agent_db_save_skill(
                name=skill_data["name"],
                description=skill_data.get("description", ""),
                trigger_keywords=skill_data.get("trigger_keywords", []),
                tool_sequence=skill_data.get("tool_sequence", []),
                decisions=skill_data.get("decisions", []),
                pitfalls=skill_data.get("pitfalls", []),
                status=skill_data.get("status", "pending"),
            )
            return str(sid or "")
        except Exception as e:
            logger.warning("skill_library: agent_db.save_skill 失败，降级兜底: %s", e)

    # 2) 兜底：直接写 agent_skills 表
    if not _ensure_table():
        return ""
    try:
        card = SkillCard(**skill_data)
        now = datetime.now().isoformat(timespec="seconds")
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO agent_skills
                    (id, name, description, trigger_keywords, tool_sequence, decisions, pitfalls, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card.id,
                    card.name,
                    card.description,
                    _dumps_list(card.trigger_keywords),
                    _dumps_list(card.tool_sequence),
                    _dumps_list(card.decisions),
                    _dumps_list(card.pitfalls),
                    card.status if card.status in _VALID_STATUS else "pending",
                    card.created_at or now,
                    card.updated_at or now,
                ),
            )
            conn.commit()
        logger.info("skill_library: 技能卡片已保存(id=%s, name=%s)", card.id, card.name)
        return card.id
    except Exception as e:
        logger.error("skill_library: 兜底保存技能失败: %s", e)
        return ""


def list_skills(status: Optional[str] = None) -> list[dict]:
    """列出技能。可按 status 过滤；只返回 approved 的给匹配用。"""
    if status is not None and status not in _VALID_STATUS:
        logger.warning("skill_library.list_skills: 非法 status=%s，忽略过滤", status)
        status = None

    # 1) 优先 agent_db
    if _AGENT_DB_AVAILABLE and callable(_agent_db_list_skills):
        try:
            rows = _agent_db_list_skills(status=status)
            return list(rows or [])
        except Exception as e:
            logger.warning("skill_library: agent_db.list_skills 失败，降级兜底: %s", e)

    # 2) 兜底
    if not _ensure_table():
        return []
    try:
        with get_conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM agent_skills WHERE status=? ORDER BY updated_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM agent_skills ORDER BY updated_at DESC"
                ).fetchall()
        return [_row_to_card(r) for r in rows]
    except Exception as e:
        logger.error("skill_library.list_skills 失败: %s", e)
        return []


def get_skill(skill_id: str) -> Optional[dict]:
    """按 id 查询单张技能卡片。"""
    if not skill_id:
        return None
    if _AGENT_DB_AVAILABLE and callable(_agent_db_get_skill):
        try:
            return _agent_db_get_skill(skill_id)
        except Exception as e:
            logger.warning("skill_library: agent_db.get_skill 失败，降级兜底: %s", e)
    if not _ensure_table():
        return None
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM agent_skills WHERE id=?", (skill_id,)
            ).fetchone()
        return _row_to_card(row) if row else None
    except Exception as e:
        logger.error("skill_library.get_skill 失败: %s", e)
        return None


def _set_status(skill_id: str, status: str) -> bool:
    """统一封装：更新状态（agent_db 优先，兜底直写）。"""
    if status not in _VALID_STATUS:
        return False
    if _AGENT_DB_AVAILABLE and callable(_agent_db_update_skill_status):
        try:
            return bool(_agent_db_update_skill_status(skill_id, status))
        except Exception as e:
            logger.warning("skill_library: agent_db.update_skill_status 失败，降级: %s", e)
    if not _ensure_table():
        return False
    try:
        now = datetime.now().isoformat(timespec="seconds")
        with get_conn() as conn:
            cur = conn.execute(
                "UPDATE agent_skills SET status=?, updated_at=? WHERE id=?",
                (status, now, skill_id),
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("skill_library._set_status 失败: %s", e)
        return False


def approve_skill(skill_id: str) -> bool:
    """审核通过一张技能卡片（pending → approved）。"""
    return _set_status(skill_id, "approved")


def delete_skill(skill_id: str) -> bool:
    """删除一张技能卡片。"""
    if not skill_id:
        return False
    if _AGENT_DB_AVAILABLE and callable(_agent_db_delete_skill):
        try:
            return bool(_agent_db_delete_skill(skill_id))
        except Exception as e:
            logger.warning("skill_library: agent_db.delete_skill 失败，降级: %s", e)
    if not _ensure_table():
        return False
    try:
        with get_conn() as conn:
            cur = conn.execute("DELETE FROM agent_skills WHERE id=?", (skill_id,))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("skill_library.delete_skill 失败: %s", e)
        return False


# ── 意图匹配：关键词命中 + 简单语义相似度（可选 embedding） ──
def _keyword_score(intent: str, skill: dict) -> float:
    """关键词命中得分：命中 trigger_keywords 的数量 / 关键词总数。"""
    intent_lower = (intent or "").lower()
    if not intent_lower:
        return 0.0
    kws = skill.get("trigger_keywords") or []
    if not kws:
        return 0.0
    hit = sum(1 for k in kws if k and k.lower() in intent_lower)
    return hit / len(kws)


def _embedding_score(intent: str, skill: dict) -> float:
    """可选：用 memory_engine.get_embedding 算 cosine 相似度。失败返回 0。"""
    try:
        from memory_engine import get_embedding  # 延迟导入
        emb_i = get_embedding(intent or "")
        emb_s = get_embedding((skill.get("name", "") + " " + skill.get("description", "")))
        if not emb_i or not emb_s or len(emb_i) != len(emb_s):
            return 0.0
        dot = sum(a * b for a, b in zip(emb_i, emb_s))
        n_i = sum(a * a for a in emb_i) ** 0.5
        n_s = sum(b * b for b in emb_s) ** 0.5
        if n_i == 0 or n_s == 0:
            return 0.0
        return dot / (n_i * n_s)
    except Exception:
        return 0.0


def match_skills(user_intent: str, top_k: int = 3) -> list[dict]:
    """根据用户意图匹配已审核（approved）技能。返回按得分排序的前 top_k 条。"""
    approved = list_skills(status="approved")
    if not approved:
        return []

    scored = []
    for sk in approved:
        kw = _keyword_score(user_intent, sk)
        emb = _embedding_score(user_intent, sk)
        # 关键词权重高，embedding 作为补充
        score = kw * 0.7 + emb * 0.3
        if score > 0:
            scored.append((score, sk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [sk for _, sk in scored[:top_k]]


def inject_skills_to_prompt(skills: list[dict]) -> str:
    """把匹配到的技能格式化成 system prompt 片段。空列表返回空串。"""
    if not skills:
        return ""
    lines = ["【历史沉淀的可复用技能】（遇到相似任务请优先复用以下打法，避免重复踩坑）："]
    for i, sk in enumerate(skills, 1):
        lines.append(f"{i}. 技能：{sk.get('name', '')}")
        if sk.get("description"):
            lines.append(f"   适用场景：{sk['description']}")
        if sk.get("tool_sequence"):
            lines.append(f"   推荐工具顺序：{' → '.join(sk['tool_sequence'])}")
        if sk.get("decisions"):
            lines.append(f"   关键判断：{'；'.join(sk['decisions'])}")
        if sk.get("pitfalls"):
            lines.append(f"   避坑：{'；'.join(sk['pitfalls'])}")
    return "\n".join(lines)


# ── 反思钩子：复杂任务结束后自动触发 ──────────────────────────
def trigger_skill_reflection(conversation_summary: str, tool_call_log: str,
                             min_tool_calls: int = 3) -> str:
    """Agent 完成复杂任务后调用的反思钩子。

    触发条件：tool_call_log 中工具调用次数 >= min_tool_calls，或对话摘要明显复杂。
    抽取成功后落库为 pending 技能，等待人工审核。
    返回：保存后的 skill_id（空串表示未触发或失败）。
    """
    try:
        call_count = len(re.findall(r"\btool[_ ]?call\b", tool_call_log or "", re.IGNORECASE))
        call_count = max(call_count, (tool_call_log or "").count("\n") // 2)
    except Exception:
        call_count = 0

    if call_count < min_tool_calls:
        logger.debug("skill_library: 工具调用次数不足(%d<%d)，跳过反思",
                     call_count, min_tool_calls)
        return ""

    try:
        skill_data = extract_skill_from_conversation(conversation_summary, tool_call_log)
        if not skill_data:
            return ""
        sid = save_skill(skill_data)
        if sid:
            logger.info("skill_library: 反思钩子已沉淀技能 id=%s name=%s",
                        sid, skill_data.get("name"))
        return sid
    except Exception as e:
        logger.warning("skill_library.trigger_skill_reflection 失败: %s", e)
        return ""
