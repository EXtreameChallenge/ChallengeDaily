"""
幕布文档同步模块
================
负责管理 mubu_docs 表，存储从幕布同步过来的文档。
实际的"拉取"动作由 Electron 主进程完成（利用 BrowserWindow + cookie），
本模块只负责：
  1. 表 schema
  2. 文档入库（upsert）
  3. 文档查询/搜索（供 routes / MCP / AI 上下文使用）
  4. 同步状态记录

数据流：
  Electron BrowserWindow (mubu.com)
    → 注入 JS 调用 mubu 内部 API 拿文档
    → HTTP POST /api/mubu/ingest 推给 Flask
    → 本模块 upsert 到 mubu_docs 表
"""
import json
import logging
import time
from datetime import datetime
from typing import Optional

from db import get_conn

logger = logging.getLogger(__name__)

# ── 表结构 ──────────────────────────────────────
# mubu_docs：存储幕布文档（按 doc_id 去重，重复同步覆盖）
# mubu_sync_state：同步状态（最后同步时间、文档数等）

_MUBU_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS mubu_docs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id          TEXT NOT NULL UNIQUE,       -- 幕布文档 id
    title           TEXT NOT NULL DEFAULT '',
    parent_id       TEXT DEFAULT '',            -- 父文件夹 id
    type            TEXT DEFAULT 'doc',          -- doc / folder
    content_md      TEXT DEFAULT '',             -- 文档正文（Markdown）
    content_json    TEXT DEFAULT '',             -- 原始树形结构（JSON）
    edit_time       INTEGER DEFAULT 0,           -- 幕布端最后编辑时间戳
    sync_time       TEXT NOT NULL,               -- 本地同步时间
    extra_json      TEXT DEFAULT '{}'            -- 额外元数据
);
CREATE INDEX IF NOT EXISTS idx_mubu_docs_parent ON mubu_docs(parent_id);
CREATE INDEX IF NOT EXISTS idx_mubu_docs_edit ON mubu_docs(edit_time);
CREATE INDEX IF NOT EXISTS idx_mubu_docs_title ON mubu_docs(title);

CREATE TABLE IF NOT EXISTS mubu_sync_state (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);
"""


def init_mubu_schema():
    """初始化幕布相关表（幂等，重复调用安全）"""
    try:
        with get_conn() as conn:
            conn.executescript(_MUBU_SCHEMA_V1)
            conn.commit()
            logger.info("幕布文档表初始化成功")
    except Exception as e:
        logger.error(f"init_mubu_schema 失败: {e}", exc_info=True)


# ── 文档入库 ──────────────────────────────────────

def upsert_doc(
    doc_id: str,
    title: str,
    parent_id: str = "",
    doc_type: str = "doc",
    content_md: str = "",
    content_json: str = "",
    edit_time: int = 0,
    extra: dict | None = None,
) -> None:
    """插入或更新一篇幕布文档（按 doc_id 去重）"""
    sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    extra_str = json.dumps(extra, ensure_ascii=False) if extra else "{}"
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO mubu_docs (doc_id, title, parent_id, type, content_md, content_json, edit_time, sync_time, extra_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                title = excluded.title,
                parent_id = excluded.parent_id,
                type = excluded.type,
                content_md = excluded.content_md,
                content_json = excluded.content_json,
                edit_time = excluded.edit_time,
                sync_time = excluded.sync_time,
                extra_json = excluded.extra_json
        """, (doc_id, title, parent_id, doc_type, content_md, content_json, edit_time, sync_time, extra_str))
        conn.commit()


def batch_upsert(docs: list[dict]) -> int:
    """批量入库文档，返回成功入库的数量

    每个文档需包含：doc_id, title（其余可选）
    入库后会在后台线程触发 memory_engine 的向量化索引（非阻塞，失败不影响入库）。
    """
    count = 0
    indexed_docs: list[dict] = []
    for d in docs:
        try:
            upsert_doc(
                doc_id=str(d.get("doc_id", "")),
                title=d.get("title", ""),
                parent_id=str(d.get("parent_id", "")),
                doc_type=d.get("type", "doc"),
                content_md=d.get("content_md", ""),
                content_json=d.get("content_json", ""),
                edit_time=int(d.get("edit_time", 0)),
                extra=d.get("extra"),
            )
            count += 1
            # 仅对有正文的 doc 类型触发向量化
            if d.get("type", "doc") == "doc" and (d.get("content_md") or "").strip():
                indexed_docs.append({
                    "source": "mubu",
                    "source_id": str(d.get("doc_id", "")),
                    "title": d.get("title", ""),
                    "content": d.get("content_md", ""),
                })
        except Exception as e:
            logger.warning(f"入库文档失败 doc_id={d.get('doc_id')}: {e}")

    # 后台线程触发向量化索引，避免阻塞 ingest 接口
    if indexed_docs:
        _trigger_memory_index(indexed_docs)
    return count


def _trigger_memory_index(docs: list[dict]) -> None:
    """在后台线程触发 memory_engine 批量索引（失败不影响主流程）"""
    try:
        import threading
        import memory_engine

        def _worker():
            try:
                memory_engine.batch_index_documents(docs)
                logger.info(f"记忆索引完成，共 {len(docs)} 篇文档")
            except Exception as e:
                logger.warning(f"记忆索引后台任务失败（非致命）: {e}")

        t = threading.Thread(target=_worker, name="memory-index", daemon=True)
        t.start()
    except Exception as e:
        logger.warning(f"memory_engine 不可用，跳过向量化: {e}")


# ── 查询/搜索 ──────────────────────────────────────

def list_docs(parent_id: Optional[str] = None, limit: int = 100) -> list[dict]:
    """列出文档列表（不含正文，节省带宽）"""
    with get_conn() as conn:
        if parent_id is None:
            rows = conn.execute(
                "SELECT doc_id, title, parent_id, type, edit_time, sync_time FROM mubu_docs ORDER BY edit_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT doc_id, title, parent_id, type, edit_time, sync_time FROM mubu_docs WHERE parent_id = ? ORDER BY title LIMIT ?",
                (parent_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


def get_doc(doc_id: str) -> Optional[dict]:
    """获取单篇文档（含正文）"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM mubu_docs WHERE doc_id = ?",
            (doc_id,),
        ).fetchone()
        return dict(row) if row else None


def search_docs(query: str, limit: int = 20) -> list[dict]:
    """关键词搜索文档（在 title 和 content_md 上 LIKE）

    返回含 doc_id / title / 命中片段 / sync_time
    """
    if not query or not query.strip():
        return []
    kw = f"%{query.strip()}%"
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT doc_id, title, content_md, edit_time, sync_time
            FROM mubu_docs
            WHERE type = 'doc' AND (title LIKE ? OR content_md LIKE ?)
            ORDER BY edit_time DESC
            LIMIT ?
            """,
            (kw, kw, limit),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            # 提取命中片段（前后 50 字符）
            md = d.pop("content_md", "")
            idx = md.lower().find(query.lower())
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(md), idx + len(query) + 50)
                d["snippet"] = ("..." if start > 0 else "") + md[start:end] + ("..." if end < len(md) else "")
            else:
                d["snippet"] = ""
            result.append(d)
        return result


def get_recent_docs(days: int = 7, limit: int = 50) -> list[dict]:
    """获取最近 N 天编辑过的文档（供 AI 上下文使用）"""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT doc_id, title, content_md, edit_time, sync_time
            FROM mubu_docs
            WHERE type = 'doc' AND edit_time > 0
            ORDER BY edit_time DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        # 按天过滤（edit_time 是秒级时间戳）
        if days > 0:
            cutoff = int(time.time()) - days * 86400
            rows = [r for r in rows if r["edit_time"] >= cutoff]
        return [dict(r) for r in rows]


def get_all_docs(limit: int = 1000) -> list[dict]:
    """获取所有文档（含正文），供全量向量化使用。

    Args:
        limit: 最多返回 N 篇 1-5000
    """
    limit = max(1, min(5000, int(limit)))
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT doc_id, title, parent_id, content_md, edit_time, sync_time
            FROM mubu_docs
            WHERE type = 'doc'
            ORDER BY edit_time DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_unindexed_docs(limit: int = 1000) -> list[dict]:
    """返回尚未向量化的文档（即 doc_chunks 表中不存在 source_id 对应记录的 mubu 文档）。
    用于增量全量同步——只索引新增/变更的文档。
    """
    limit = max(1, min(5000, int(limit)))
    with get_conn() as conn:
        # doc_chunks 表可能尚未创建（V36 未迁移），先做存在性检查
        try:
            conn.execute("SELECT 1 FROM doc_chunks LIMIT 0")
            chunk_table_ok = True
        except Exception:
            chunk_table_ok = False

        if chunk_table_ok:
            rows = conn.execute(
                """
                SELECT m.doc_id, m.title, m.parent_id, m.content_md, m.edit_time, m.sync_time
                FROM mubu_docs m
                LEFT JOIN (
                    SELECT DISTINCT source_id FROM doc_chunks WHERE source = 'mubu'
                ) c ON c.source_id = m.doc_id
                WHERE m.type = 'doc' AND (m.content_md IS NOT NULL AND m.content_md != '')
                  AND c.source_id IS NULL
                ORDER BY m.edit_time DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            # doc_chunks 表不存在 → 全部文档都未索引
            rows = conn.execute(
                """
                SELECT doc_id, title, parent_id, content_md, edit_time, sync_time
                FROM mubu_docs
                WHERE type = 'doc' AND (content_md IS NOT NULL AND content_md != '')
                ORDER BY edit_time DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def build_mubu_context_for_ai(days: int = 7, limit: int = 20) -> str:
    """构建供 AI prompt 注入的幕布笔记上下文段。

    返回格式化的 Markdown 段落；若无文档或获取失败，返回空字符串。
    供 morning_insight / report 等 AI prompt 构建处调用，失败不影响日报生成。
    """
    try:
        docs = get_recent_docs(days=days, limit=limit)
        if not docs:
            return ""
        lines = ["## 最近的幕布笔记（用户在幕布 app 里的思考记录）"]
        for d in docs:
            title = (d.get("title") or "").strip() or "（无标题）"
            content = (d.get("content_md") or "")[:500]
            lines.append(f"- 《{title}》：{content}")
        logger.info(f"已注入 {len(docs)} 篇幕布文档作为上下文")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"构建幕布上下文失败(非致命): {e}")
        return ""


# ── 同步状态 ──────────────────────────────────────

def set_sync_state(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO mubu_sync_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()


def get_sync_state(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM mubu_sync_state WHERE key = ?",
            (key,),
        ).fetchone()
        return row["value"] if row else default


def get_sync_status() -> dict:
    """获取整体同步状态"""
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) as c FROM mubu_docs").fetchone()["c"]
        doc_count = conn.execute("SELECT COUNT(*) as c FROM mubu_docs WHERE type='doc'").fetchone()["c"]
        last_sync = get_sync_state("last_sync_time", "")
        last_error = get_sync_state("last_error", "")
        cookie_ok = get_sync_state("cookie_valid", "0") == "1"
    # 计算前端可用的 status 字段
    if last_error:
        status = "error"
    elif not cookie_ok and last_sync:
        # 之前同步过但 cookie 已失效
        status = "cookie_invalid"
    elif not cookie_ok:
        # 从未登录/从未同步
        status = "idle"
    elif doc_count > 0:
        status = "synced"
    elif last_sync:
        status = "synced"
    else:
        status = "idle"
    return {
        "total": total,
        "doc_count": doc_count,
        "last_sync": last_sync,
        "last_sync_time": last_sync,
        "last_error": last_error,
        "cookie_valid": cookie_ok,
        "status": status,
    }


# ── 自动关联待办/习惯（启发式） ──────────────────────────────

_AUTO_TODO_KEYWORDS = ["TODO", "待办", "要做", "需要", "计划", "明天", "下周", "TODO:", "- [ ]"]
_AUTO_HABIT_KEYWORDS = ["每天", "每日", "习惯", "坚持", "每天", "每早", "每晚"]


def extract_todos_from_doc(doc: dict) -> list[dict]:
    """从文档正文里启发式提取待办项

    识别规则：
      1. "- [ ] xxx" 标准复选框
      2. 行首含 TODO/待办/要做 关键词
    """
    md = doc.get("content_md", "")
    if not md:
        return []
    todos = []
    for line in md.splitlines():
        line = line.strip()
        if not line:
            continue
        # 标准 markdown 复选框
        if line.startswith("- [ ] "):
            title = line[6:].strip()
            if title:
                todos.append({"title": title, "source": "mubu:" + doc.get("doc_id", "")})
                continue
        # 关键词触发
        for kw in _AUTO_TODO_KEYWORDS:
            if kw in line and len(line) < 100:
                todos.append({"title": line, "source": "mubu:" + doc.get("doc_id", "")})
                break
    return todos


# ── 初始化时调用 ──────────────────────────────────────

# 在 db.init_db 之后调用一次即可
# routes/__init__.py 不直接调用，由 main.py 或 server.py 显式调用
