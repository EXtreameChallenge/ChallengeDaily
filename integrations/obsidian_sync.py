"""
Obsidian 同步模块
================
负责把本地数据库里的幕布文档（mubu_docs 表）写入用户的 Obsidian vault，
作为本地知识库。同时管理 vault 路径配置和同步状态。

数据流：
  SQLite (mubu_docs)
    → 重建幕布文件夹层级
    → 生成带 YAML frontmatter 的 Markdown
    → 写入 Obsidian vault / 幕布同步 / 文件夹层级 / 标题.md

设计要点：
  - 单向同步：只从项目写 Obsidian，不读回（读回由后续 obsidian_reader 负责）
  - 增量写入：通过 frontmatter 里的 mubu_edit_time 判断是否变更，未变更则跳过
  - 幂等：重复同步不会产生重复文件，按 doc_id 去重
  - 原子写入：使用 file_utils.atomic_write_text，避免半写文件
"""
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import mubu_sync
from config import load_settings, save_settings
from db import get_conn
from file_utils import atomic_write_text

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────
DEFAULT_MUBU_FOLDER = "幕布同步"          # vault 里存放幕布笔记的子文件夹
_SETTINGS_KEY_VAULT = "obsidian_vault_path"
_SETTINGS_KEY_FOLDER = "obsidian_mubu_folder"

# Windows 文件名非法字符
_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


# ═══════════════════════════════════════════════════
# 配置管理
# ═══════════════════════════════════════════════════

def get_vault_path() -> str:
    """获取 Obsidian vault 路径（优先环境变量，其次 settings.json）"""
    env_path = os.getenv("OBSIDIAN_VAULT_PATH", "").strip()
    if env_path:
        return env_path
    settings = load_settings()
    return (settings.get(_SETTINGS_KEY_VAULT) or "").strip()


def set_vault_path(path: str) -> bool:
    """设置 Obsidian vault 路径并持久化到 settings.json

    Returns:
        True 表示设置成功；False 表示路径不存在或不可访问
    """
    path = (path or "").strip().strip('"').strip("'")
    if not path:
        # 允许清空
        settings = load_settings()
        settings[_SETTINGS_KEY_VAULT] = ""
        save_settings(settings)
        return True
    p = Path(path)
    if not p.exists() or not p.is_dir():
        logger.warning(f"Obsidian vault 路径不存在或不是目录: {path}")
        return False
    settings = load_settings()
    settings[_SETTINGS_KEY_VAULT] = str(p.resolve())
    save_settings(settings)
    logger.info(f"Obsidian vault 路径已设置: {p.resolve()}")
    return True


def get_mubu_folder() -> str:
    """获取 vault 里幕布笔记的子文件夹名"""
    settings = load_settings()
    return (settings.get(_SETTINGS_KEY_FOLDER) or DEFAULT_MUBU_FOLDER).strip() or DEFAULT_MUBU_FOLDER


def set_mubu_folder(folder: str) -> None:
    """设置 vault 里幕布笔记的子文件夹名"""
    folder = (folder or "").strip() or DEFAULT_MUBU_FOLDER
    settings = load_settings()
    settings[_SETTINGS_KEY_FOLDER] = folder
    save_settings(settings)


def is_vault_configured() -> bool:
    """vault 路径是否已配置且存在"""
    path = get_vault_path()
    if not path:
        return False
    return Path(path).exists()


# ═══════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════

def _slugify(text: str) -> str:
    """将标题转为 Obsidian 友好的文件名（保留中文，去除非法字符）"""
    cleaned = _INVALID_FILENAME_CHARS.sub("", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # 去除首尾的点（Windows 不允许文件名以点结尾）
    cleaned = cleaned.strip(".")
    return cleaned


def _read_frontmatter_edit_time(filepath: Path) -> Optional[int]:
    """从已存在的 .md 文件 frontmatter 中读取 mubu_edit_time，用于增量判断"""
    try:
        text = filepath.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return None
        end = text.find("\n---", 3)
        if end < 0:
            return None
        fm = text[3:end]
        m = re.search(r"^mubu_edit_time:\s*(\d+)", fm, re.M)
        if m:
            return int(m.group(1))
    except Exception as e:
        logger.debug(f"读取 frontmatter 失败 {filepath}: {e}")
    return None


def _build_note_content(doc: dict) -> str:
    """根据幕布文档生成 Obsidian Markdown 内容（frontmatter + 正文）"""
    doc_id = str(doc.get("doc_id", ""))
    title = (doc.get("title") or "").strip() or "未命名"
    edit_time = int(doc.get("edit_time", 0) or 0)
    content_md = doc.get("content_md", "") or ""
    extra = doc.get("extra_json", "{}")
    try:
        extra_dict = __import__("json").loads(extra) if isinstance(extra, str) else (extra or {})
    except Exception:
        extra_dict = {}

    # 编辑时间转可读格式
    edit_time_str = ""
    if edit_time > 0:
        try:
            edit_time_str = datetime.fromtimestamp(edit_time).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            edit_time_str = ""

    today = datetime.now().strftime("%Y-%m-%d")
    sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # frontmatter
    fm_lines = [
        "---",
        f"title: {title}",
        f"source: mubu",
        f"mubu_doc_id: {doc_id}",
        f"mubu_edit_time: {edit_time}",
        f"mubu_edit_time_readable: {edit_time_str}",
        f"mubu_sync_time: {sync_time}",
        f"created: {today}",
        "tags:",
        "  - 幕布同步",
        "  - mubu",
    ]
    # 如果 extra 里有标签，追加
    extra_tags = extra_dict.get("tags") or extra_dict.get("tag")
    if isinstance(extra_tags, list):
        for t in extra_tags[:10]:
            fm_lines.append(f"  - {str(t).strip()}")
    elif isinstance(extra_tags, str) and extra_tags.strip():
        fm_lines.append(f"  - {extra_tags.strip()}")

    fm_lines.append("---")
    frontmatter = "\n".join(fm_lines)

    # 正文：如果内容不以标题开头，补上一级标题
    body = content_md
    if body and not body.lstrip().startswith("#"):
        body = f"# {title}\n\n{body}"

    return f"{frontmatter}\n\n{body}\n"


# ═══════════════════════════════════════════════════
# 核心同步逻辑
# ═══════════════════════════════════════════════════

def _fetch_all_mubu_docs() -> list[dict]:
    """从 mubu_docs 表读取所有文档（含 folder）"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT doc_id, title, parent_id, type, content_md, content_json, edit_time, sync_time, extra_json "
            "FROM mubu_docs ORDER BY edit_time DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def _resolve_folder_chain(parent_id: str, folder_map: dict) -> list[str]:
    """根据 parent_id 逐级向上解析文件夹层级，返回文件夹名列表（从根到叶）"""
    chain = []
    pid = (parent_id or "").strip()
    visited = set()  # 防循环引用
    while pid and pid in folder_map and pid not in visited:
        visited.add(pid)
        folder = folder_map[pid]
        name = _slugify(folder.get("title", "")) or "未命名文件夹"
        chain.insert(0, name)
        pid = (folder.get("parent_id", "") or "").strip()
    return chain


def sync_mubu_to_obsidian(force: bool = False) -> dict:
    """把幕布文档同步到 Obsidian vault

    Args:
        force: True 时强制重写所有文件（忽略 edit_time 增量判断）

    Returns:
        dict: {
            "ok": bool,
            "vault_path": str,
            "mubu_folder": str,
            "total_docs": int,       # 幕布文档总数（doc 类型）
            "written": int,           # 本次写入/更新的文件数
            "skipped": int,           # 跳过（未变更）的文件数
            "failed": int,            # 失败数
            "errors": list[str],      # 错误信息
            "last_sync": str,         # 同步完成时间
        }
    """
    result = {
        "ok": False,
        "vault_path": "",
        "mubu_folder": "",
        "total_docs": 0,
        "written": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "last_sync": "",
    }

    # 1. 检查 vault 配置
    vault_path = get_vault_path()
    if not vault_path:
        result["errors"].append("Obsidian vault 路径未配置，请先在设置中指定")
        mubu_sync.set_sync_state("obsidian_last_error", "vault 路径未配置")
        return result
    vault_root = Path(vault_path)
    if not vault_root.exists() or not vault_root.is_dir():
        result["errors"].append(f"Obsidian vault 路径不存在: {vault_path}")
        mubu_sync.set_sync_state("obsidian_last_error", f"vault 路径不存在: {vault_path}")
        return result

    mubu_folder = get_mubu_folder()
    target_root = vault_root / mubu_folder
    target_root.mkdir(parents=True, exist_ok=True)

    result["vault_path"] = str(vault_root)
    result["mubu_folder"] = mubu_folder

    # 2. 读取幕布文档
    try:
        all_docs = _fetch_all_mubu_docs()
    except Exception as e:
        result["errors"].append(f"读取幕布文档失败: {e}")
        mubu_sync.set_sync_state("obsidian_last_error", f"读取幕布文档失败: {e}")
        return result

    # 分离 folder 和 doc
    folder_map = {d["doc_id"]: d for d in all_docs if d.get("type") == "folder"}
    doc_list = [d for d in all_docs if d.get("type") != "folder"]
    result["total_docs"] = len(doc_list)

    if not doc_list:
        result["ok"] = True
        result["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mubu_sync.set_sync_state("obsidian_last_sync_time", result["last_sync"])
        mubu_sync.set_sync_state("obsidian_last_error", "")
        mubu_sync.set_sync_state("obsidian_synced_count", "0")
        logger.info("幕布文档为空，无需同步到 Obsidian")
        return result

    # 3. 逐个写入
    used_paths = set()  # 防止同批次内路径冲突
    for doc in doc_list:
        try:
            doc_id = str(doc.get("doc_id", ""))
            title = (doc.get("title") or "").strip()
            edit_time = int(doc.get("edit_time", 0) or 0)

            # 解析文件夹层级
            chain = _resolve_folder_chain(doc.get("parent_id", ""), folder_map)
            rel_dir = Path(*chain) if chain else Path(".")
            abs_dir = target_root / rel_dir
            abs_dir.mkdir(parents=True, exist_ok=True)

            # 生成唯一文件名
            base_name = _slugify(title) or doc_id[:8] or "未命名"
            candidate = f"{base_name}.md"
            i = 2
            while (abs_dir / candidate).as_posix() in used_paths:
                candidate = f"{base_name}_{i}.md"
                i += 1
            used_paths.add((abs_dir / candidate).as_posix())
            filepath = abs_dir / candidate

            # 增量判断：文件已存在且 edit_time 未变 → 跳过
            if not force and filepath.exists():
                existing_edit = _read_frontmatter_edit_time(filepath)
                if existing_edit is not None and existing_edit == edit_time and edit_time > 0:
                    result["skipped"] += 1
                    continue

            # 生成内容并写入
            content = _build_note_content(doc)
            atomic_write_text(filepath, content)
            result["written"] += 1
            logger.debug(f"写入 Obsidian 笔记: {filepath}")

        except Exception as e:
            result["failed"] += 1
            err_msg = f"doc_id={doc.get('doc_id', '?')} title={doc.get('title', '?')}: {e}"
            result["errors"].append(err_msg)
            logger.warning(f"写入 Obsidian 笔记失败: {err_msg}", exc_info=True)

    # 4. 记录同步状态
    result["ok"] = result["failed"] == 0
    result["last_sync"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mubu_sync.set_sync_state("obsidian_last_sync_time", result["last_sync"])
    mubu_sync.set_sync_state("obsidian_synced_count", str(result["written"] + result["skipped"]))
    if result["errors"]:
        mubu_sync.set_sync_state("obsidian_last_error", "; ".join(result["errors"][:5]))
    else:
        mubu_sync.set_sync_state("obsidian_last_error", "")

    logger.info(
        f"幕布→Obsidian 同步完成: 总计{result['total_docs']}篇, "
        f"写入{result['written']}, 跳过{result['skipped']}, 失败{result['failed']}"
    )
    return result


# ═══════════════════════════════════════════════════
# 状态查询
# ═══════════════════════════════════════════════════

def get_sync_status() -> dict:
    """获取 Obsidian 同步整体状态"""
    vault_path = get_vault_path()
    vault_exists = bool(vault_path) and Path(vault_path).exists() if vault_path else False

    # 幕布文档数
    try:
        with get_conn() as conn:
            mubu_total = conn.execute("SELECT COUNT(*) as c FROM mubu_docs WHERE type='doc'").fetchone()["c"]
    except Exception:
        mubu_total = 0

    last_sync = mubu_sync.get_sync_state("obsidian_last_sync_time", "")
    last_error = mubu_sync.get_sync_state("obsidian_last_error", "")
    synced_count = mubu_sync.get_sync_state("obsidian_synced_count", "0")

    # 统计 vault 里实际文件数
    vault_file_count = 0
    if vault_exists:
        try:
            mubu_folder = get_mubu_folder()
            target_root = Path(vault_path) / mubu_folder
            if target_root.exists():
                vault_file_count = sum(1 for _ in target_root.rglob("*.md"))
        except Exception:
            pass

    # 状态判定
    if not vault_path:
        status = "not_configured"
    elif not vault_exists:
        status = "vault_missing"
    elif last_error:
        status = "error"
    elif mubu_total == 0:
        status = "no_mubu_docs"
    elif vault_file_count > 0:
        status = "synced"
    elif last_sync:
        status = "synced"
    else:
        status = "idle"

    return {
        "vault_path": vault_path,
        "vault_exists": vault_exists,
        "mubu_folder": get_mubu_folder(),
        "mubu_total_docs": mubu_total,
        "vault_file_count": vault_file_count,
        "synced_count": int(synced_count) if synced_count.isdigit() else 0,
        "last_sync": last_sync,
        "last_error": last_error,
        "status": status,
    }


def list_synced_notes(limit: int = 100) -> list[dict]:
    """列出 vault 里已同步的幕布笔记（文件列表，不含正文）"""
    vault_path = get_vault_path()
    if not vault_path or not Path(vault_path).exists():
        return []
    target_root = Path(vault_path) / get_mubu_folder()
    if not target_root.exists():
        return []

    notes = []
    for fp in target_root.rglob("*.md"):
        try:
            stat = fp.stat()
            rel = fp.relative_to(target_root)
            notes.append({
                "path": str(rel),
                "filename": fp.name,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            })
        except Exception:
            continue
        if len(notes) >= limit:
            break
    # 按修改时间倒序
    notes.sort(key=lambda x: x["mtime"], reverse=True)
    return notes
