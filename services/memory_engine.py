"""
三阶段记忆系统核心
==================
1) 文档分块（按字数 / Markdown 标题感知）
2) 向量化（sqlite-vec + sentence-transformers bge-small-zh-v1.5）+ FTS5 全文索引
3) 统一记忆系统（Mem0 风格原子事实 + 混合检索 RRF 融合）

降级链：
  - sqlite-vec / sentence-transformers 不可用 → 仅 FTS5
  - FTS5 不可用 → 仅 LIKE 模糊匹配
  - LLM 抽取失败 → 简单关键词抽取

设计要点：
  - 向量模型延迟加载（首次 get_embedding 才下载 / 加载）
  - sqlite-vec 扩展按线程连接按需加载（通过连接属性去重）
  - 所有外部 import (sqlite_vec / sentence_transformers) 均 try/except
  - 所有写入路径幂等（基于 content_hash 增量同步）
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import config
from db import get_conn

logger = logging.getLogger(__name__)

# ── 常量 ────────────────────────────────────────────────────
EMBED_DIM = 512  # bge-small-zh-v1.5 输出维度
DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 50
RRF_K = 60  # Reciprocal Rank Fusion 常数
_MODEL_DIR: Path = config.DATA_DIR / "models" / "bge-small-zh-v1.5"

# ── 可选依赖：sqlite-vec ────────────────────────────────────
# 加载失败时降级为纯 FTS5 / LIKE
_sqlite_vec_module: Any = None
_sqlite_vec_loaded_conns: set[int] = set()  # 已加载扩展的连接 id 集合
_sqlite_vec_load_lock_per_conn = threading.Lock()


def _load_sqlite_vec(conn) -> bool:
    """在给定连接上加载 sqlite_vec 扩展（每连接只加载一次）。
    返回 True 表示加载成功（或已加载），False 表示不可用。
    """
    global _sqlite_vec_module
    conn_id = id(conn)
    # 快速路径：已加载过
    if conn_id in _sqlite_vec_loaded_conns:
        return True
    with _sqlite_vec_load_lock_per_conn:
        if conn_id in _sqlite_vec_loaded_conns:
            return True
        try:
            if _sqlite_vec_module is None:
                import sqlite_vec  # type: ignore
                _sqlite_vec_module = sqlite_vec
            conn.enable_load_extension(True)
            try:
                _sqlite_vec_module.load(conn)
            except Exception:
                # 某些版本 API 是 sqlite_vec.load(conn) 或 conn.load_extension(path)
                # 兜底：尝试通过模块路径加载
                try:
                    ext_path = Path(sqlite_vec.__file__).resolve()
                    conn.load_extension(str(ext_path))
                except Exception as e:
                    logger.debug(f"sqlite_vec.load 失败: {e}")
                    raise
            conn.enable_load_extension(False)
            _sqlite_vec_loaded_conns.add(conn_id)
            return True
        except Exception as e:
            logger.info(f"sqlite-vec 扩展不可用，将仅使用 FTS5/LIKE: {e}")
            return False


def is_vector_available() -> bool:
    """向量检索是否可用（sqlite-vec + 嵌入模型均能加载）"""
    return _is_sqlite_vec_available() and _is_embedding_available()


def _is_sqlite_vec_available() -> bool:
    """探测 sqlite-vec 模块是否可导入"""
    global _sqlite_vec_module
    if _sqlite_vec_module is not None:
        return True
    try:
        import sqlite_vec  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def _is_embedding_available() -> bool:
    """探测 sentence-transformers 是否可导入"""
    try:
        import sentence_transformers  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


# ── 可选依赖：sentence-transformers ─────────────────────────
_embedding_model: Any = None
_embedding_lock = threading.Lock()
_embedding_load_failed = False  # 标记加载失败，避免重复尝试


def _get_embedding_model():
    """延迟加载 bge-small-zh-v1.5 嵌入模型（线程安全，失败标记不再重试）"""
    global _embedding_model, _embedding_load_failed
    if _embedding_model is not None:
        return _embedding_model
    if _embedding_load_failed:
        return None
    with _embedding_lock:
        if _embedding_model is not None:
            return _embedding_model
        if _embedding_load_failed:
            return None
        try:
            import os
            # 强制离线模式：避免每次加载都向 HuggingFace 服务器发 HEAD 请求验证文件
            # （首次需通过 HF_ENDPOINT=https://hf-mirror.com 镜像预先下载到 ~/.cache/huggingface/hub）
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            from sentence_transformers import SentenceTransformer  # type: ignore
            _MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
            # 优先使用本地保存的目录 → 否则用 HF 缓存（离线模式）
            if _MODEL_DIR.exists() and any(_MODEL_DIR.iterdir()):
                logger.info(f"加载本地嵌入模型: {_MODEL_DIR}")
                _embedding_model = SentenceTransformer(str(_MODEL_DIR))
            else:
                logger.info("从 HF 缓存加载 bge-small-zh-v1.5（离线模式）...")
                # local_files_only=True 强制使用缓存，禁止网络请求
                _embedding_model = SentenceTransformer(
                    "BAAI/bge-small-zh-v1.5", local_files_only=True
                )
                # 尝试保存到本地目录，便于后续直接加载
                try:
                    _embedding_model.save(str(_MODEL_DIR))
                except Exception as save_err:
                    logger.debug(f"模型保存失败（不影响功能）: {save_err}")
            return _embedding_model
        except Exception as e:
            _embedding_load_failed = True
            logger.warning(f"嵌入模型加载失败，将仅使用 FTS5/LIKE: {e}")
            return None


def get_embedding(text: str) -> Optional[list[float]]:
    """生成文本的嵌入向量。模型不可用时返回 None。"""
    if not text or not text.strip():
        return None
    model = _get_embedding_model()
    if model is None:
        return None
    try:
        vec = model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec.tolist()]
    except Exception as e:
        logger.warning(f"嵌入生成失败: {e}")
        return None


# ── 文档分块 ────────────────────────────────────────────────
def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE,
               overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """按字数切块（带 overlap），不感知 Markdown 结构。
    用于非 Markdown 文本或简单分块场景。
    """
    if not text:
        return []
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    i = 0
    while i < len(text):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk.strip())
        i += step
    return chunks


def chunk_markdown(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE,
                   overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """按 Markdown 标题（# / ## / ###）感知分块。

    策略：
      1. 按行扫描，遇到 #/##/### 标题则切分（保留标题层级）
      2. 若单个 section 仍超过 chunk_size，再用 chunk_text 二次切块
      3. 空段落跳过
    """
    if not text:
        return []
    lines = text.splitlines()
    sections: list[str] = []
    current: list[str] = []
    heading_re = re.compile(r"^#{1,3}\s+\S")

    def flush():
        if current:
            content = "\n".join(current).strip()
            if content:
                sections.append(content)

    for line in lines:
        if heading_re.match(line):
            flush()
            current = [line]
        else:
            current.append(line)
    flush()

    # 没有 heading 则整篇作为单个 section
    if not sections:
        sections = [text.strip()] if text.strip() else []

    # 对超长 section 二次切块
    result: list[str] = []
    for sec in sections:
        if len(sec) <= chunk_size:
            result.append(sec)
        else:
            result.extend(chunk_text(sec, chunk_size=chunk_size, overlap=overlap))
    return result


def _content_hash(text: str) -> str:
    """sha256 内容指纹，用于增量同步"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── Schema 初始化 ───────────────────────────────────────────
_schema_initialized = False
_schema_init_lock = threading.Lock()


def init_memory_schema() -> None:
    """初始化记忆系统表 + 加载 sqlite-vec 扩展 + 创建向量虚表。
    幂等：重复调用安全。
    db.py V36 迁移已创建普通表 + FTS5 虚表，这里负责按需创建 vec0 虚表。
    """
    global _schema_initialized
    if _schema_initialized:
        return
    with _schema_init_lock:
        if _schema_initialized:
            return
        try:
            with get_conn() as conn:
                # 普通表 + FTS5 由 db.py V36 创建，这里仅作幂等保护
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS doc_chunks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source TEXT DEFAULT 'mubu',
                        source_id TEXT,
                        chunk_index INTEGER DEFAULT 0,
                        content TEXT,
                        content_hash TEXT,
                        created_at TEXT DEFAULT (datetime('now','localtime'))
                    );
                    CREATE INDEX IF NOT EXISTS idx_doc_chunks_source ON doc_chunks(source, source_id);

                    CREATE TABLE IF NOT EXISTS memories (
                        id TEXT PRIMARY KEY,
                        source_type TEXT,
                        source_id TEXT,
                        content TEXT,
                        metadata TEXT DEFAULT '{}',
                        created_at TEXT,
                        updated_at TEXT,
                        deleted_at TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_memories_source ON memories(source_type);

                    CREATE TABLE IF NOT EXISTS ingest_jobs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        job_type TEXT,
                        status TEXT DEFAULT 'pending',
                        total INTEGER DEFAULT 0,
                        done INTEGER DEFAULT 0,
                        error TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    );
                """)
                # FTS5 虚表（若 V36 已创建则幂等跳过）
                try:
                    conn.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts USING fts5("
                        "content, content='doc_chunks', content_rowid='id', tokenize='unicode61')"
                    )
                except Exception as fts_err:
                    logger.info(f"doc_chunks_fts 不可用（降级为 LIKE）: {fts_err}")

                # 向量虚表：仅在 sqlite-vec 可加载时创建
                if _load_sqlite_vec(conn):
                    try:
                        conn.execute(
                            f"CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_vec USING vec0("
                            f"embedding float[{EMBED_DIM}])"
                        )
                        conn.execute(
                            f"CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec USING vec0("
                            f"embedding float[{EMBED_DIM}])"
                        )
                        logger.info("向量虚表创建/就绪: doc_chunks_vec + memories_vec")
                    except Exception as vec_err:
                        logger.warning(f"向量虚表创建失败（降级为 FTS5/LIKE）: {vec_err}")
                conn.commit()
            _schema_initialized = True
            logger.info("记忆系统 schema 初始化完成")
        except Exception as e:
            logger.error(f"init_memory_schema 失败（非致命）: {e}", exc_info=True)


# ── FTS5 / 向量同步辅助 ─────────────────────────────────────
def _fts5_available(conn) -> bool:
    """检测 doc_chunks_fts 是否可用"""
    try:
        conn.execute("SELECT 1 FROM doc_chunks_fts LIMIT 0")
        return True
    except Exception:
        return False


def _vec_table_available(conn, table: str) -> bool:
    """检测向量虚表是否可用"""
    try:
        conn.execute(f"SELECT 1 FROM {table} LIMIT 0")
        return True
    except Exception:
        return False


def _insert_fts_row(conn, rowid: int, content: str) -> None:
    try:
        conn.execute(
            "INSERT INTO doc_chunks_fts(rowid, content) VALUES (?, ?)",
            (rowid, content),
        )
    except Exception as e:
        logger.debug(f"FTS5 插入失败（非致命）: {e}")


def _delete_fts_row(conn, rowid: int, content: str) -> None:
    try:
        conn.execute(
            "INSERT INTO doc_chunks_fts(doc_chunks_fts, rowid, content) VALUES ('delete', ?, ?)",
            (rowid, content),
        )
    except Exception as e:
        logger.debug(f"FTS5 删除失败（非致命）: {e}")


def _insert_vec_row(conn, table: str, rowid: int, embedding: list[float]) -> None:
    try:
        conn.execute(
            f"INSERT INTO {table}(rowid, embedding) VALUES (?, ?)",
            (rowid, json.dumps(embedding)),
        )
    except Exception as e:
        logger.debug(f"向量插入失败 table={table}（非致命）: {e}")


def _delete_vec_row(conn, table: str, rowid: int) -> None:
    try:
        conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (rowid,))
    except Exception as e:
        logger.debug(f"向量删除失败 table={table}（非致命）: {e}")


# ── 文档索引 ────────────────────────────────────────────────
def index_document(source: str, source_id: str, content: str,
                   title: str = "", force: bool = False) -> int:
    """索引单篇文档：分块 + FTS5 + 向量化。
    增量同步：若所有块 content_hash 与现有一致则跳过（force=True 强制重建）。
    返回实际写入的块数。
    """
    if not content or not content.strip():
        return 0
    init_memory_schema()
    # 拼接标题，让标题也参与检索
    full_text = f"{title}\n\n{content}" if title else content
    chunks = chunk_markdown(full_text)
    if not chunks:
        return 0

    new_hashes = [_content_hash(c) for c in chunks]

    with get_conn() as conn:
        # 查询现有块
        existing_rows = conn.execute(
            "SELECT id, chunk_index, content_hash FROM doc_chunks "
            "WHERE source = ? AND source_id = ? ORDER BY chunk_index",
            (source, source_id),
        ).fetchall()
        existing_hashes = [r["content_hash"] for r in existing_rows]

        # 增量判断：块数相同且所有 hash 一致 → 跳过
        if not force and len(existing_hashes) == len(new_hashes) and \
                all(a == b for a, b in zip(existing_hashes, new_hashes)):
            return 0

        # 删除旧块（含 FTS5 / 向量同步）
        for r in existing_rows:
            old_rowid = r["id"]
            old_content = ""
            try:
                old_content = conn.execute(
                    "SELECT content FROM doc_chunks WHERE id=?", (old_rowid,)
                ).fetchone()["content"]
            except Exception:
                pass
            _delete_fts_row(conn, old_rowid, old_content or "")
            _delete_vec_row(conn, "doc_chunks_vec", old_rowid)
        conn.execute(
            "DELETE FROM doc_chunks WHERE source = ? AND source_id = ?",
            (source, source_id),
        )

        # 写入新块
        written = 0
        for idx, (chunk, h) in enumerate(zip(chunks, new_hashes)):
            cur = conn.execute(
                "INSERT INTO doc_chunks (source, source_id, chunk_index, content, content_hash) "
                "VALUES (?, ?, ?, ?, ?)",
                (source, source_id, idx, chunk, h),
            )
            new_rowid = cur.lastrowid
            _insert_fts_row(conn, new_rowid, chunk)
            # 向量化（若可用）
            if _load_sqlite_vec(conn) and _vec_table_available(conn, "doc_chunks_vec"):
                emb = get_embedding(chunk)
                if emb is not None:
                    _insert_vec_row(conn, "doc_chunks_vec", new_rowid, emb)
            written += 1
        conn.commit()
        return written


def batch_index_documents(docs: list[dict],
                          on_progress: Optional[Callable[[int, int], None]] = None) -> dict:
    """批量索引文档。
    每个文档 dict 需含: source, source_id, content, title(可选)
    返回 {total, indexed, skipped, errors}
    同时在 ingest_jobs 表记录进度，供前端/状态查询使用。
    """
    init_memory_schema()
    total = len(docs)
    indexed = 0
    skipped = 0
    errors: list[str] = []
    job_id = create_ingest_job("batch_index", total) if total > 0 else None
    try:
        for i, d in enumerate(docs):
            try:
                source = str(d.get("source", "mubu"))
                source_id = str(d.get("source_id", ""))
                content = d.get("content", "") or ""
                title = d.get("title", "") or ""
                if not source_id or not content.strip():
                    skipped += 1
                else:
                    n = index_document(source, source_id, content, title=title)
                    if n > 0:
                        indexed += n
                    else:
                        skipped += 1
            except Exception as e:
                errors.append(f"{d.get('source_id', '?')}: {e}")
            # 每 5 篇更新一次进度（减少 DB 写入）
            if job_id and (i + 1) % 5 == 0:
                try:
                    update_ingest_job(job_id, done=i + 1)
                except Exception:
                    pass
            if on_progress:
                try:
                    on_progress(i + 1, total)
                except Exception:
                    pass
    finally:
        if job_id:
            try:
                err_summary = "; ".join(errors[:5]) if errors else None
                update_ingest_job(
                    job_id, done=total, status="done",
                    error=err_summary[:500] if err_summary else None
                )
            except Exception:
                pass
    return {"total": total, "indexed": indexed, "skipped": skipped, "errors": errors}


# ── 检索：BM25 (FTS5) + 向量余弦 + RRF 融合 ─────────────────
def _sanitize_fts_query(query: str) -> str:
    """转义 FTS5 特殊字符，避免语法注入。
    用双引号包裹并将内部双引号转义。
    """
    q = (query or "").strip()
    if not q:
        return ""
    # FTS5 字符串字面量：双引号内，双引号本身用 "" 转义
    safe = q.replace('"', '""')
    return f'"{safe}"'


def _search_fts5(conn, query: str, limit: int) -> list[dict]:
    """FTS5 BM25 检索，返回 [{rowid, content, rank}]"""
    safe_q = _sanitize_fts_query(query)
    if not safe_q:
        return []
    try:
        rows = conn.execute(
            "SELECT f.rowid, c.content, f.rank "
            "FROM doc_chunks_fts f JOIN doc_chunks c ON c.id = f.rowid "
            "WHERE doc_chunks_fts MATCH ? "
            "ORDER BY f.rank LIMIT ?",
            (safe_q, limit),
        ).fetchall()
        return [{"rowid": r["rowid"], "content": r["content"], "rank": r["rank"]} for r in rows]
    except Exception as e:
        logger.debug(f"FTS5 检索失败: {e}")
        return []


def _search_like(conn, query: str, limit: int) -> list[dict]:
    """LIKE 模糊匹配（FTS5 不可用时的最终降级）"""
    kw = f"%{(query or '').strip()}%"
    if not (query or "").strip():
        return []
    try:
        rows = conn.execute(
            "SELECT id, content FROM doc_chunks WHERE content LIKE ? LIMIT ?",
            (kw, limit),
        ).fetchall()
        return [{"rowid": r["id"], "content": r["content"], "rank": 0.0} for r in rows]
    except Exception as e:
        logger.debug(f"LIKE 检索失败: {e}")
        return []


def _search_vector(conn, query: str, limit: int) -> list[dict]:
    """向量余弦检索，返回 [{rowid, content, distance}]"""
    if not _load_sqlite_vec(conn) or not _vec_table_available(conn, "doc_chunks_vec"):
        return []
    emb = get_embedding(query)
    if emb is None:
        return []
    try:
        rows = conn.execute(
            "SELECT rowid, distance FROM doc_chunks_vec "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (json.dumps(emb), limit),
        ).fetchall()
        result = []
        for r in rows:
            # 取 content
            try:
                content_row = conn.execute(
                    "SELECT content FROM doc_chunks WHERE id=?", (r["rowid"],)
                ).fetchone()
                content = content_row["content"] if content_row else ""
            except Exception:
                content = ""
            result.append({"rowid": r["rowid"], "content": content, "distance": r["distance"]})
        return result
    except Exception as e:
        logger.debug(f"向量检索失败: {e}")
        return []


def _rrf_fuse(rank_lists: list[list[dict]], limit: int, k: int = RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion 融合多路检索结果。
    rank_lists: 每路检索按相关度从高到低排序的 list[{rowid, content, ...}]
    返回融合后按分数降序的前 limit 条 [{rowid, content, score}]
    """
    scores: dict[int, float] = {}
    content_map: dict[int, str] = {}
    for ranks in rank_lists:
        for pos, item in enumerate(ranks):
            rid = item["rowid"]
            scores[rid] = scores.get(rid, 0.0) + 1.0 / (k + pos + 1)
            content_map[rid] = item.get("content", "")
    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
    return [{"rowid": rid, "content": content_map[rid], "score": s} for rid, s in fused]


def hybrid_search(query: str, limit: int = 10) -> list[dict]:
    """混合检索：BM25(FTS5) + 向量余弦 → RRF 融合。
    自动降级：向量不可用 → 仅 FTS5；FTS5 不可用 → 仅 LIKE。
    返回 [{rowid, content, score, source}]
    """
    if not query or not query.strip():
        return []
    init_memory_schema()
    limit = max(1, min(100, int(limit)))
    fetch_n = max(limit * 3, 30)  # 多取一些给 RRF 融合

    with get_conn() as conn:
        rank_lists: list[list[dict]] = []
        # 1) 向量路（优先，失败自动跳过）
        vec_results = _search_vector(conn, query, fetch_n)
        if vec_results:
            rank_lists.append(vec_results)
        # 2) FTS5 路
        fts_results = _search_fts5(conn, query, fetch_n)
        if fts_results:
            rank_lists.append(fts_results)
        # 3) 全部失败 → LIKE 兜底
        if not rank_lists:
            like_results = _search_like(conn, query, fetch_n)
            if like_results:
                rank_lists.append(like_results)

        if not rank_lists:
            return []

        fused = _rrf_fuse(rank_lists, limit=limit)
        # 补充 source / source_id
        result = []
        for item in fused:
            rowid = item["rowid"]
            try:
                row = conn.execute(
                    "SELECT source, source_id, chunk_index FROM doc_chunks WHERE id=?",
                    (rowid,),
                ).fetchone()
                source = row["source"] if row else ""
                source_id = row["source_id"] if row else ""
            except Exception:
                source, source_id = "", ""
            result.append({
                "rowid": rowid,
                "content": item["content"],
                "score": round(item["score"], 6),
                "source": source,
                "source_id": source_id,
            })
        return result


# ── LLM 调用辅助 ────────────────────────────────────────────
# 任务说明提到复用 offline_ai.call_ai，但当前项目无此函数；
# 这里实现一个本地 _call_llm 包装现有 OpenAI 客户端，遵循 routes/chat.py 模式。
def _call_llm(prompt: str, system: str = "", max_tokens: int = 800,
              temperature: float = 0.3) -> Optional[str]:
    """调用 LLM 生成文本。失败返回 None。
    复用 ai_client 中的 OpenAI 客户端 + 熔断器 / 限流。
    """
    if not config.AI_API_KEY:
        return None
    try:
        from ai_client import _get_client, _cb_check, _cb_record_success, _cb_record_failure, _rate_limit_check
        if not _cb_check():
            return None
        if not _rate_limit_check("text"):
            return None
        client = _get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = resp.choices[0].message.content or ""
        _cb_record_success()
        try:
            from offline_ai import mark_ai_success
            mark_ai_success()
        except Exception:
            pass
        return text.strip()
    except Exception as e:
        logger.warning(f"LLM 调用失败: {e}")
        try:
            from ai_client import _cb_record_failure
            _cb_record_failure()
        except Exception:
            pass
        return None


# ── 事实抽取（Mem0 风格） ───────────────────────────────────
_FACT_EXTRACTION_KEYWORDS = [
    "喜欢", "讨厌", "偏好", "目标", "计划", "正在", "负责", "工作", "项目",
    "家人", "生日", "住", "城市", "公司", "团队", "使用", "学习", "研究",
    "每天", "每周", "习惯", "坚持", "需要", "必须", "希望", "想要",
]


def extract_facts(content: str, source_type: str = "mubu",
                  source_id: str = "") -> list[str]:
    """从文本中抽取原子事实（Mem0 风格）。
    优先用 LLM 抽取；失败时降级为关键词匹配的句子抽取。
    """
    if not content or not content.strip():
        return []
    text = content.strip()
    # 限制输入长度，避免 token 爆炸
    if len(text) > 4000:
        text = text[:4000]

    # 1) LLM 抽取
    system = (
        "你是一个事实抽取助手。从用户文本中抽取原子事实，每条事实是一句简洁陈述。"
        "只输出 JSON 数组，如 [\"用户喜欢用 Python\", \"用户住在上海\"]。"
        "若无明显事实，返回空数组 []。不要输出任何解释。"
    )
    prompt = f"从以下文本抽取原子事实（JSON 数组）：\n\n{text}"
    raw = _call_llm(prompt, system=system, max_tokens=600, temperature=0.2)
    if raw:
        facts = _parse_facts_json(raw)
        if facts:
            return facts[:30]  # 上限 30 条

    # 2) 降级：关键词匹配的句子抽取
    return _extract_facts_keyword(text)


def _parse_facts_json(raw: str) -> list[str]:
    """从 LLM 输出中解析 JSON 数组（容错）"""
    if not raw:
        return []
    # 提取第一个 [ ... ] 块
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
        if isinstance(arr, list):
            return [str(x).strip() for x in arr if str(x).strip()]
    except Exception:
        pass
    return []


def _extract_facts_keyword(text: str) -> list[str]:
    """降级事实抽取：按句子切分，保留含事实关键词的句子"""
    if not text:
        return []
    # 按句号 / 换行切分
    sentences = re.split(r"[。\n!？!?]", text)
    facts: list[str] = []
    for s in sentences:
        s = s.strip()
        if not s or len(s) < 4 or len(s) > 80:
            continue
        if any(kw in s for kw in _FACT_EXTRACTION_KEYWORDS):
            facts.append(s)
    return facts[:20]


# ── 记忆 CRUD ───────────────────────────────────────────────
def add_memory(content: str, source_type: str = "manual",
               source_id: str = "", metadata: dict | None = None) -> str:
    """新增一条记忆（原子事实）。返回 memory_id。
    若向量可用则同步写入 memories_vec。
    """
    if not content or not content.strip():
        return ""
    init_memory_schema()
    mem_id = str(uuid.uuid4())
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta_str = json.dumps(metadata or {}, ensure_ascii=False)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO memories (id, source_type, source_id, content, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (mem_id, source_type, source_id, content.strip(), meta_str, now, now),
        )
        rowid = cur.lastrowid
        if _load_sqlite_vec(conn) and _vec_table_available(conn, "memories_vec"):
            emb = get_embedding(content)
            if emb is not None:
                _insert_vec_row(conn, "memories_vec", rowid, emb)
        conn.commit()
    return mem_id


def update_memory(memory_id: str, content: str,
                  metadata: dict | None = None) -> bool:
    """更新记忆内容（同时刷新向量）"""
    if not memory_id:
        return False
    init_memory_schema()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM memories WHERE id=? AND deleted_at IS NULL",
            (memory_id,),
        ).fetchone()
        if not row:
            return False
        meta_str = json.dumps(metadata or {}, ensure_ascii=False) if metadata is not None else None
        if meta_str is not None:
            conn.execute(
                "UPDATE memories SET content=?, metadata=?, updated_at=? WHERE id=?",
                (content.strip(), meta_str, now, memory_id),
            )
        else:
            conn.execute(
                "UPDATE memories SET content=?, updated_at=? WHERE id=?",
                (content.strip(), now, memory_id),
            )
        # 刷新向量（先删后插）
        if _load_sqlite_vec(conn) and _vec_table_available(conn, "memories_vec"):
            # rowid 即主键对应整数？memories.id 是 TEXT，vec0 rowid 需为整数
            # 这里用 memories 表中行的 rowid（隐藏 rowid）作为向量 rowid
            try:
                rid = conn.execute(
                    "SELECT rowid FROM memories WHERE id=?", (memory_id,)
                ).fetchone()["rowid"]
                _delete_vec_row(conn, "memories_vec", rid)
                emb = get_embedding(content)
                if emb is not None:
                    _insert_vec_row(conn, "memories_vec", rid, emb)
            except Exception as e:
                logger.debug(f"记忆向量刷新失败: {e}")
        conn.commit()
    return True


def delete_memory(memory_id: str) -> bool:
    """软删除记忆（设置 deleted_at），并清理向量"""
    if not memory_id:
        return False
    init_memory_schema()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, rowid FROM memories WHERE id=? AND deleted_at IS NULL",
            (memory_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE memories SET deleted_at=?, updated_at=? WHERE id=?",
            (now, now, memory_id),
        )
        if _load_sqlite_vec(conn) and _vec_table_available(conn, "memories_vec"):
            _delete_vec_row(conn, "memories_vec", row["rowid"])
        conn.commit()
    return True


def list_memories(source_type: str | None = None, limit: int = 100,
                  include_deleted: bool = False) -> list[dict]:
    """列出记忆（默认排除软删除）"""
    init_memory_schema()
    limit = max(1, min(500, int(limit)))
    with get_conn() as conn:
        sql = "SELECT id, source_type, source_id, content, metadata, created_at, updated_at, deleted_at FROM memories WHERE 1=1"
        params: list[Any] = []
        if not include_deleted:
            sql += " AND deleted_at IS NULL"
        if source_type:
            sql += " AND source_type=?"
            params.append(source_type)
        sql += " ORDER BY datetime(updated_at) DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["metadata"] = json.loads(d.get("metadata") or "{}")
            except Exception:
                d["metadata"] = {}
            result.append(d)
        return result


def search_memories(query: str, limit: int = 5) -> list[dict]:
    """检索记忆：向量 + FTS5（在 memories.content 上）/ LIKE 三路 RRF。
    返回 [{id, content, source_type, score}]
    """
    if not query or not query.strip():
        return []
    init_memory_schema()
    limit = max(1, min(50, int(limit)))
    fetch_n = max(limit * 3, 15)
    with get_conn() as conn:
        rank_lists: list[list[dict]] = []
        # 向量路
        if _load_sqlite_vec(conn) and _vec_table_available(conn, "memories_vec"):
            emb = get_embedding(query)
            if emb is not None:
                try:
                    rows = conn.execute(
                        "SELECT v.rowid, v.distance, m.id, m.content, m.source_type "
                        "FROM memories_vec v JOIN memories m ON m.rowid = v.rowid "
                        "WHERE v.embedding MATCH ? AND v.k = ? "
                        "AND m.deleted_at IS NULL "
                        "ORDER BY v.distance",
                        (json.dumps(emb), fetch_n),
                    ).fetchall()
                    if rows:
                        rank_lists.append([{
                            "rowid": r["rowid"],
                            "content": r["content"],
                            "id": r["id"],
                            "source_type": r["source_type"],
                        } for r in rows])
                except Exception as e:
                    logger.debug(f"记忆向量检索失败: {e}")

        # LIKE 路（memories 表无独立 FTS5 虚表，用 LIKE 兜底）
        kw = f"%{query.strip()}%"
        try:
            rows = conn.execute(
                "SELECT rowid, id, content, source_type FROM memories "
                "WHERE deleted_at IS NULL AND content LIKE ? LIMIT ?",
                (kw, fetch_n),
            ).fetchall()
            if rows:
                rank_lists.append([{
                    "rowid": r["rowid"],
                    "content": r["content"],
                    "id": r["id"],
                    "source_type": r["source_type"],
                } for r in rows])
        except Exception as e:
            logger.debug(f"记忆 LIKE 检索失败: {e}")

        if not rank_lists:
            return []

        fused = _rrf_fuse(rank_lists, limit=limit)
        result = []
        for item in fused:
            result.append({
                "id": item.get("id", ""),
                "content": item.get("content", ""),
                "source_type": item.get("source_type", ""),
                "score": round(item["score"], 6),
            })
        return result


# ── 摄入任务进度 ─────────────────────────────────────────────
def create_ingest_job(job_type: str, total: int = 0) -> int:
    """创建摄入任务，返回 job_id"""
    init_memory_schema()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO ingest_jobs (job_type, status, total, done, created_at, updated_at) "
            "VALUES (?, 'running', ?, 0, ?, ?)",
            (job_type, total, now, now),
        )
        conn.commit()
        return cur.lastrowid


def update_ingest_job(job_id: int, done: int = None, status: str = None,
                      error: str = None, total: int = None) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sets, params = [], []
    if done is not None:
        sets.append("done=?")
        params.append(done)
    if status is not None:
        sets.append("status=?")
        params.append(status)
    if error is not None:
        sets.append("error=?")
        params.append(error)
    if total is not None:
        sets.append("total=?")
        params.append(total)
    if not sets:
        return
    sets.append("updated_at=?")
    params.append(now)
    params.append(job_id)
    with get_conn() as conn:
        conn.execute(f"UPDATE ingest_jobs SET {', '.join(sets)} WHERE id=?", params)
        conn.commit()


def get_indexing_status() -> dict:
    """获取向量化状态摘要"""
    init_memory_schema()
    with get_conn() as conn:
        try:
            chunk_count = conn.execute("SELECT COUNT(*) AS c FROM doc_chunks").fetchone()["c"]
        except Exception:
            chunk_count = 0
        try:
            mem_count = conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE deleted_at IS NULL"
            ).fetchone()["c"]
        except Exception:
            mem_count = 0
        # 已索引的 mubu 文档数（去重 source_id）
        try:
            indexed_docs = conn.execute(
                "SELECT COUNT(DISTINCT source_id) AS c FROM doc_chunks WHERE source='mubu'"
            ).fetchone()["c"]
        except Exception:
            indexed_docs = 0
        # 进行中的任务
        try:
            running = conn.execute(
                "SELECT * FROM ingest_jobs WHERE status='running' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            running_job = dict(running) if running else None
        except Exception:
            running_job = None
        # 最近完成的任务
        try:
            last_job = conn.execute(
                "SELECT * FROM ingest_jobs WHERE status IN ('done','failed') ORDER BY id DESC LIMIT 1"
            ).fetchone()
            last_job_dict = dict(last_job) if last_job else None
        except Exception:
            last_job_dict = None

    return {
        "vector_available": is_vector_available(),
        "sqlite_vec_available": _is_sqlite_vec_available(),
        "embedding_available": _is_embedding_available(),
        "embedding_model": "bge-small-zh-v1.5" if _is_embedding_available() else None,
        "chunk_count": chunk_count,
        "memory_count": mem_count,
        "indexed_doc_count": indexed_docs,
        "running_job": running_job,
        "last_job": last_job_dict,
    }


# ── AI 对话记忆上下文构建 ───────────────────────────────────
def build_memory_context(query: str, max_tokens: int = 2000) -> str:
    """构建供 AI 对话注入的记忆上下文。
    检索 memories + doc_chunks → RRF 融合 → 拼接为 Markdown 段落。
    max_tokens 估算：1 中文字符 ≈ 1.5 token，按字符数粗略控制。
    """
    if not query or not query.strip():
        return ""
    init_memory_schema()
    char_budget = int(max_tokens / 1.5)
    if char_budget < 50:
        char_budget = 50

    memories = search_memories(query, limit=5)
    chunks = hybrid_search(query, limit=8)

    lines: list[str] = []
    used = 0
    if memories:
        lines.append("## 相关记忆")
        for m in memories:
            line = f"- {m.get('content', '')}"
            if used + len(line) > char_budget:
                break
            lines.append(line)
            used += len(line) + 1
    if chunks:
        if lines:
            lines.append("")
        lines.append("## 相关文档片段")
        for c in chunks:
            content = (c.get("content") or "").strip().replace("\n", " ")
            if len(content) > 200:
                content = content[:200] + "..."
            line = f"- 〔{c.get('source', '')}〕{content}"
            if used + len(line) > char_budget:
                break
            lines.append(line)
            used += len(line) + 1
    return "\n".join(lines) if lines else ""
