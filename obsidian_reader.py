"""
Obsidian 笔记读入模块
====================
扫描用户的 Obsidian vault，把 .md 笔记读入本地数据库并向量化，
作为 AI 知识库（RAG 上下文、语义检索、待办提取、数据统计）。

与 obsidian_sync.py 的区别：
  - obsidian_sync.py：幕布 → Obsidian（写出，把幕布笔记写成 vault 里的 .md）
  - obsidian_reader.py：Obsidian → 项目（读入，把 vault 里的 .md 扫进数据库和向量库）

两个模块配合形成完整闭环：
  幕布 → SQLite → Obsidian vault → SQLite(obsidian_notes) → 向量库 → AI 上下文
"""
import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from config import load_settings, save_settings
from db import get_conn, insert_todo
from file_utils import atomic_write_text

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────
_EXCLUDE_DIRS = {".obsidian", ".trash", ".git", ".idea", ".vscode", "node_modules", "__pycache__"}
_EXCLUDE_FILES = {".DS_Store", "desktop.ini"}

# 双向链接 [[note]] 或 [[note|alias]]
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
# 正文里的 #标签（不匹配 markdown 标题 #）
_TAG_RE = re.compile(r"(?<!\w)#([\w\u4e00-\u9fa5][\w\u4e00-\u9fa5/_-]*)")
# 待办复选框 - [ ] / - [x]
_TODO_RE = re.compile(r"^\s*[-*]\s*\[\s*\]\s*(.+)$", re.M)
_TODO_DONE_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]\s*(.+)$", re.M)

# 待办关键词（启发式）
_TODO_KEYWORDS = ["TODO", "待办", "要做", "需要", "计划", "明天", "下周", "TODO:"]


# ═══════════════════════════════════════════════════
# 表结构
# ═══════════════════════════════════════════════════

_OBSIDIAN_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS obsidian_notes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    note_path       TEXT NOT NULL UNIQUE,       -- vault 内相对路径（唯一键）
    title           TEXT NOT NULL DEFAULT '',
    folder          TEXT DEFAULT '',             -- 所在文件夹（相对路径）
    content_md      TEXT DEFAULT '',             -- 正文（不含 frontmatter）
    frontmatter_json TEXT DEFAULT '{}',          -- 原始 frontmatter（JSON）
    tags            TEXT DEFAULT '',              -- 逗号分隔
    links           TEXT DEFAULT '',              -- 逗号分隔的双向链接目标
    mtime           REAL DEFAULT 0,               -- 文件修改时间戳
    size            INTEGER DEFAULT 0,            -- 文件字节数
    word_count      INTEGER DEFAULT 0,            -- 正文字数
    sync_time       TEXT NOT NULL,                -- 最后扫描时间
    extra_json      TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_obsidian_notes_folder ON obsidian_notes(folder);
CREATE INDEX IF NOT EXISTS idx_obsidian_notes_mtime ON obsidian_notes(mtime);
CREATE INDEX IF NOT EXISTS idx_obsidian_notes_title ON obsidian_notes(title);

CREATE TABLE IF NOT EXISTS obsidian_sync_state (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL
);
"""


def init_obsidian_schema():
    """初始化 Obsidian 读入相关表（幂等）"""
    try:
        with get_conn() as conn:
            conn.executescript(_OBSIDIAN_SCHEMA_V1)
            conn.commit()
        logger.info("Obsidian 读入表初始化成功")
    except Exception as e:
        logger.error(f"init_obsidian_schema 失败: {e}", exc_info=True)


def _set_state(key: str, value: str) -> None:
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO obsidian_sync_state (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def _get_state(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM obsidian_sync_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


# ═══════════════════════════════════════════════════
# 配置管理（复用 obsidian_sync 的 vault 路径）
# ═══════════════════════════════════════════════════

def get_vault_path() -> str:
    """获取 Obsidian vault 路径（优先环境变量，其次 settings.json）"""
    import obsidian_sync
    return obsidian_sync.get_vault_path()


def is_vault_configured() -> bool:
    import obsidian_sync
    return obsidian_sync.is_vault_configured()


# ═══════════════════════════════════════════════════
# 解析工具
# ═══════════════════════════════════════════════════

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 Markdown 文件的 YAML frontmatter，返回 (frontmatter_dict, 正文)"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    try:
        fm = yaml.safe_load(fm_text) or {}
        if not isinstance(fm, dict):
            fm = {}
    except Exception as e:
        logger.debug(f"frontmatter 解析失败: {e}")
        fm = {}
    return fm, body


def _extract_tags(fm: dict, body: str) -> list[str]:
    """从 frontmatter 和正文中提取标签"""
    tags = []
    # frontmatter 里的 tags
    fm_tags = fm.get("tags") or fm.get("tag")
    if isinstance(fm_tags, list):
        for t in fm_tags:
            t = str(t).strip().lstrip("#")
            if t and t not in tags:
                tags.append(t)
    elif isinstance(fm_tags, str):
        for t in re.split(r"[,\s]+", fm_tags):
            t = t.strip().lstrip("#")
            if t and t not in tags:
                tags.append(t)
    # 正文中的 #标签
    for m in _TAG_RE.finditer(body):
        t = m.group(1).strip()
        if t and t not in tags and len(t) < 50:
            tags.append(t)
    return tags


def _extract_links(body: str) -> list[str]:
    """提取正文中的双向链接目标"""
    links = []
    for m in _WIKILINK_RE.finditer(body):
        target = m.group(1).strip()
        if target and target not in links:
            links.append(target)
    return links


def _count_words(text: str) -> int:
    """粗略统计字数（中文字符 + 英文单词）"""
    if not text:
        return 0
    chinese = len(re.findall(r"[\u4e00-\u9fa5]", text))
    english = len(re.findall(r"[a-zA-Z]+", text))
    return chinese + english


# ═══════════════════════════════════════════════════
# 核心扫描逻辑
# ═══════════════════════════════════════════════════

def _iter_md_files(vault_root: Path):
    """遍历 vault 下所有 .md 文件，排除配置文件夹"""
    for root, dirs, files in os.walk(vault_root):
        # 原地修改 dirs 以排除不需要的文件夹
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS and not d.startswith(".")]
        for fname in files:
            if fname in _EXCLUDE_FILES:
                continue
            if fname.lower().endswith(".md"):
                yield Path(root) / fname


def _get_existing_mtimes() -> dict[str, float]:
    """从数据库读取已有笔记的 mtime，用于增量判断"""
    try:
        with get_conn() as conn:
            rows = conn.execute("SELECT note_path, mtime FROM obsidian_notes").fetchall()
            return {r["note_path"]: r["mtime"] for r in rows}
    except Exception:
        return {}


def scan_vault(force: bool = False) -> dict:
    """扫描 Obsidian vault，把新增/变更的笔记入库并向量化

    Args:
        force: True 时强制重新扫描所有文件（忽略 mtime 增量判断）

    Returns:
        dict: {
            "ok": bool,
            "vault_path": str,
            "total_files": int,       # vault 里 .md 总数
            "scanned": int,            # 本次实际读取解析的文件数
            "skipped": int,            # 跳过（未变更）的文件数
            "failed": int,
            "errors": list[str],
            "indexed": int,            # 触发向量化的笔记数
            "last_scan": str,
        }
    """
    result = {
        "ok": False, "vault_path": "", "total_files": 0,
        "scanned": 0, "skipped": 0, "failed": 0,
        "errors": [], "indexed": 0, "last_scan": "",
    }

    # 1. 检查 vault
    vault_path = get_vault_path()
    if not vault_path:
        result["errors"].append("Obsidian vault 路径未配置")
        _set_state("last_error", "vault 路径未配置")
        return result
    vault_root = Path(vault_path)
    if not vault_root.exists() or not vault_root.is_dir():
        result["errors"].append(f"vault 路径不存在: {vault_path}")
        _set_state("last_error", f"vault 路径不存在: {vault_path}")
        return result

    result["vault_path"] = str(vault_root)
    init_obsidian_schema()

    # 2. 收集所有 .md 文件
    all_files = list(_iter_md_files(vault_root))
    result["total_files"] = len(all_files)

    if not all_files:
        result["ok"] = True
        result["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _set_state("last_scan_time", result["last_scan"])
        _set_state("last_error", "")
        logger.info("vault 中没有 .md 文件")
        return result

    # 3. 增量判断
    existing_mtimes = _get_existing_mtimes() if not force else {}

    to_index = []  # 待向量化的笔记
    sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for filepath in all_files:
        try:
            rel_path = str(filepath.relative_to(vault_root)).replace("\\", "/")
            stat = filepath.stat()
            mtime = stat.st_mtime

            # 增量：mtime 未变则跳过
            if not force and rel_path in existing_mtimes and abs(existing_mtimes[rel_path] - mtime) < 1.0:
                result["skipped"] += 1
                continue

            # 读取文件
            text = filepath.read_text(encoding="utf-8", errors="replace")
            fm, body = _parse_frontmatter(text)

            # 标题：优先 frontmatter.title，其次文件名（去 .md）
            title = (fm.get("title") or "").strip()
            if not title:
                title = filepath.stem

            # 文件夹
            folder = str(Path(rel_path).parent).replace("\\", "/")
            if folder == ".":
                folder = ""

            # 标签、链接、字数
            tags = _extract_tags(fm, body)
            links = _extract_links(body)
            word_count = _count_words(body)

            # 入库（upsert）
            with get_conn() as conn:
                conn.execute("""
                    INSERT INTO obsidian_notes
                        (note_path, title, folder, content_md, frontmatter_json, tags, links,
                         mtime, size, word_count, sync_time, extra_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(note_path) DO UPDATE SET
                        title = excluded.title,
                        folder = excluded.folder,
                        content_md = excluded.content_md,
                        frontmatter_json = excluded.frontmatter_json,
                        tags = excluded.tags,
                        links = excluded.links,
                        mtime = excluded.mtime,
                        size = excluded.size,
                        word_count = excluded.word_count,
                        sync_time = excluded.sync_time
                """, (
                    rel_path, title, folder, body,
                    json.dumps(fm, ensure_ascii=False, default=str),
                    ",".join(tags), ",".join(links),
                    mtime, stat.st_size, word_count, sync_time, "{}"
                ))
                conn.commit()

            result["scanned"] += 1

            # 收集待向量化（有正文的笔记）
            if body.strip():
                to_index.append({
                    "source": "obsidian",
                    "source_id": rel_path,
                    "title": title,
                    "content": body,
                })

        except Exception as e:
            result["failed"] += 1
            err_msg = f"{filepath.name}: {e}"
            result["errors"].append(err_msg)
            logger.warning(f"扫描笔记失败 {filepath}: {e}", exc_info=True)

    # 4. 后台线程触发向量化
    if to_index:
        result["indexed"] = len(to_index)
        _trigger_memory_index(to_index)

    # 5. 记录状态
    result["ok"] = result["failed"] == 0
    result["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _set_state("last_scan_time", result["last_scan"])
    _set_state("total_files", str(result["total_files"]))
    _set_state("indexed_count", str(result["indexed"]))
    if result["errors"]:
        _set_state("last_error", "; ".join(result["errors"][:5]))
    else:
        _set_state("last_error", "")

    logger.info(
        f"Obsidian 扫描完成: 总计{result['total_files']}文件, "
        f"扫描{result['scanned']}, 跳过{result['skipped']}, "
        f"失败{result['failed']}, 向量化{result['indexed']}"
    )
    return result


def _trigger_memory_index(docs: list[dict]) -> None:
    """后台线程触发 memory_engine 批量索引（失败不影响主流程）"""
    try:
        import memory_engine

        def _worker():
            try:
                memory_engine.batch_index_documents(docs)
                logger.info(f"Obsidian 笔记向量化完成，共 {len(docs)} 篇")
            except Exception as e:
                logger.warning(f"Obsidian 向量化后台任务失败（非致命）: {e}")

        t = threading.Thread(target=_worker, name="obsidian-memory-index", daemon=True)
        t.start()
    except Exception as e:
        logger.warning(f"memory_engine 不可用，跳过向量化: {e}")


# ═══════════════════════════════════════════════════
# 查询 / 搜索
# ═══════════════════════════════════════════════════

def list_notes(folder: Optional[str] = None, limit: int = 100) -> list[dict]:
    """列出已扫描的笔记（不含正文）"""
    with get_conn() as conn:
        if folder:
            rows = conn.execute(
                "SELECT note_path, title, folder, tags, mtime, size, word_count, sync_time "
                "FROM obsidian_notes WHERE folder = ? ORDER BY mtime DESC LIMIT ?",
                (folder, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT note_path, title, folder, tags, mtime, size, word_count, sync_time "
                "FROM obsidian_notes ORDER BY mtime DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_note(note_path: str) -> Optional[dict]:
    """获取单篇笔记（含正文）"""
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM obsidian_notes WHERE note_path = ?", (note_path,)).fetchone()
        return dict(row) if row else None


def search_notes(query: str, limit: int = 20) -> list[dict]:
    """关键词搜索笔记（title + content_md）"""
    if not query or not query.strip():
        return []
    kw = f"%{query.strip()}%"
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT note_path, title, folder, content_md, mtime, word_count
            FROM obsidian_notes
            WHERE title LIKE ? OR content_md LIKE ?
            ORDER BY mtime DESC LIMIT ?
            """,
            (kw, kw, limit),
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            md = d.pop("content_md", "")
            idx = md.lower().find(query.lower())
            if idx >= 0:
                start = max(0, idx - 50)
                end = min(len(md), idx + len(query) + 50)
                d["snippet"] = ("..." if start > 0 else "") + md[start:end] + ("..." if end < len(md) else "")
            else:
                d["snippet"] = ""
            results.append(d)
        return results


# ═══════════════════════════════════════════════════
# 待办提取
# ═══════════════════════════════════════════════════

def extract_todos_from_note(note: dict) -> list[dict]:
    """从单篇 Obsidian 笔记正文提取待办项

    识别规则：
      1. "- [ ] xxx" 标准复选框
      2. 行首含 TODO/待办/要做 关键词
    """
    content = note.get("content_md", "") or ""
    if not content:
        return []
    todos = []
    note_path = note.get("note_path", "")
    for line in content.splitlines():
        line_stripped = line.strip()
        if not line_stripped:
            continue
        # 标准 markdown 复选框
        m = _TODO_RE.match(line)
        if m:
            title = m.group(1).strip()
            if title:
                todos.append({"title": title, "source": "obsidian:" + note_path, "completed": False})
            continue
        # 已完成的不提取
        if _TODO_DONE_RE.match(line):
            continue
        # 关键词触发
        for kw in _TODO_KEYWORDS:
            if kw in line_stripped and len(line_stripped) < 100:
                todos.append({"title": line_stripped, "source": "obsidian:" + note_path, "completed": False})
                break
    return todos


def extract_all_todos(limit: int = 200) -> dict:
    """从所有 Obsidian 笔记提取待办，并写入项目的 todos 表

    Returns:
        dict: {"extracted": int, "inserted": int, "todos": [...]}
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT note_path, title, content_md FROM obsidian_notes "
            "WHERE content_md IS NOT NULL AND content_md != '' "
            "ORDER BY mtime DESC LIMIT ?",
            (limit,),
        ).fetchall()

    all_todos = []
    seen_titles = set()
    for r in rows:
        note = dict(r)
        ts = extract_todos_from_note(note)
        for t in ts:
            t["note_title"] = note.get("title", "")
            # 去重（同标题只保留一次）
            if t["title"] not in seen_titles:
                seen_titles.add(t["title"])
                all_todos.append(t)

    # 写入 todos 表（简单插入，category 默认为"待办"）
    inserted = 0
    for t in all_todos:
        try:
            insert_todo(
                title=t["title"],
                category="待办",
                mode="timer",
                target_min=25,
                priority=2,
                task_level="day",
            )
            inserted += 1
        except Exception as e:
            logger.warning(f"插入待办失败: {t['title']}: {e}")

    return {
        "extracted": len(all_todos),
        "inserted": inserted,
        "todos": all_todos,
    }


# ═══════════════════════════════════════════════════
# 数据统计
# ═══════════════════════════════════════════════════

def get_stats() -> dict:
    """获取 Obsidian 笔记库的统计数据"""
    with get_conn() as conn:
        # 基础统计
        total = conn.execute("SELECT COUNT(*) as c FROM obsidian_notes").fetchone()["c"]
        total_words = conn.execute("SELECT COALESCE(SUM(word_count),0) as s FROM obsidian_notes").fetchone()["s"]
        total_size = conn.execute("SELECT COALESCE(SUM(size),0) as s FROM obsidian_notes").fetchone()["s"]

        # 文件夹分布（top 15）
        folder_rows = conn.execute(
            "SELECT folder, COUNT(*) as cnt FROM obsidian_notes "
            "WHERE folder != '' GROUP BY folder ORDER BY cnt DESC LIMIT 15"
        ).fetchall()
        folder_dist = [{"folder": r["folder"] or "(根目录)", "count": r["cnt"]} for r in folder_rows]

        # 标签分布（top 20）
        tag_rows = conn.execute("SELECT tags FROM obsidian_notes WHERE tags != ''").fetchall()
        tag_count = {}
        for r in tag_rows:
            for t in (r["tags"] or "").split(","):
                t = t.strip()
                if t:
                    tag_count[t] = tag_count.get(t, 0) + 1
        top_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)[:20]
        tag_dist = [{"tag": t, "count": c} for t, c in top_tags]

        # 最近 7 天修改的笔记数
        cutoff = time.time() - 7 * 86400
        recent_7 = conn.execute(
            "SELECT COUNT(*) as c FROM obsidian_notes WHERE mtime > ?", (cutoff,)
        ).fetchone()["c"]

        # 最近修改的笔记（top 10）
        recent_rows = conn.execute(
            "SELECT note_path, title, folder, mtime, word_count FROM obsidian_notes "
            "ORDER BY mtime DESC LIMIT 10"
        ).fetchall()
        recent_notes = [dict(r) for r in recent_rows]

        # 双向链接统计
        link_rows = conn.execute("SELECT links FROM obsidian_notes WHERE links != ''").fetchall()
        total_links = sum(len((r["links"] or "").split(",")) for r in link_rows)

    last_scan = _get_state("last_scan_time", "")
    last_error = _get_state("last_error", "")

    return {
        "total_notes": total,
        "total_words": total_words,
        "total_size_kb": round(total_size / 1024, 1),
        "recent_7_days": recent_7,
        "total_links": total_links,
        "folder_distribution": folder_dist,
        "tag_distribution": tag_dist,
        "recent_notes": recent_notes,
        "last_scan": last_scan,
        "last_error": last_error,
    }


# ═══════════════════════════════════════════════════
# 状态查询
# ═══════════════════════════════════════════════════

def get_reader_status() -> dict:
    """获取 Obsidian 读入整体状态"""
    vault_path = get_vault_path()
    vault_exists = bool(vault_path) and Path(vault_path).exists() if vault_path else False

    try:
        with get_conn() as conn:
            db_count = conn.execute("SELECT COUNT(*) as c FROM obsidian_notes").fetchone()["c"]
    except Exception:
        db_count = 0

    last_scan = _get_state("last_scan_time", "")
    last_error = _get_state("last_error", "")
    total_files = _get_state("total_files", "0")

    if not vault_path:
        status = "not_configured"
    elif not vault_exists:
        status = "vault_missing"
    elif last_error:
        status = "error"
    elif db_count > 0:
        status = "scanned"
    else:
        status = "idle"

    return {
        "vault_path": vault_path,
        "vault_exists": vault_exists,
        "db_note_count": db_count,
        "vault_total_files": int(total_files) if total_files.isdigit() else 0,
        "last_scan": last_scan,
        "last_error": last_error,
        "status": status,
    }
