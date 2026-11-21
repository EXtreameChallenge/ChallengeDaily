"""轮10 隐私数据面：被遗忘权与可携带权的统一实现。

覆盖：
- 主 SQLite 全部业务表（动态白名单，排除 settings/schema 等系统表）
- `~/.challenge-daily` 遗留数据文件与归档
- `DATA_DIR` 下的截图/报告/备份/归档等用户内容
- 截图加密盐值（APPDATA 旧位置 + 统一 DATA_DIR 位置）
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import stat
from datetime import datetime
from pathlib import Path

import config
import enterprise_store

logger = logging.getLogger(__name__)

# 系统/配置表不参与“被遗忘权”删除与导出；它们不是用户内容。
_PROTECTED_TABLES = {"settings", "schema_version", "sqlite_sequence", "sqlite_stat1"}
_SHADOW_MARKERS = (
    "_fts_config", "_fts_data", "_fts_docsize", "_fts_idx",
    "_vec_chunks", "_vec_info", "_vec_rowids", "_vector_chunks",
)

_USER_DIRS = ("screenshots", "reports", "backups", "insight_state", "calendar_cache", "archives")
_USER_FILES = (
    "settings.json", "settings.pre-fullmode.json", "auto_report.json",
    "webhooks.json", "vault.dat", "wakatime_api_key.json",
    "round10-migration.json",
)
_SALT_NAMES = ("screenshot_salt.bin", "legacy-screenshot_salt.bin")


def _is_system_table(name: str) -> bool:
    if not name or name in _PROTECTED_TABLES:
        return True
    if name.startswith("sqlite_"):
        return True
    return any(marker in name for marker in _SHADOW_MARKERS)


def _ensure_vec_extension(conn) -> None:
    """加载 sqlite-vec，确保向量虚表可查询/可清空。失败时不影响普通表。"""
    try:
        from memory_engine import _load_sqlite_vec
        _load_sqlite_vec(conn)
    except Exception as e:
        logger.debug(f"sqlite-vec 扩展加载失败（向量表可能不可读）: {e}")


def user_tables(conn) -> list[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    return [row[0] for row in rows if not _is_system_table(row[0])]


def _salt_paths() -> list[Path]:
    paths = [Path(config.DATA_DIR) / "screenshot_salt.bin"]
    legacy = Path(os.environ.get("APPDATA", str(Path.home()))) / "challenge-daily" / "backend-data" / "screenshot_salt.bin"
    if legacy.resolve() == paths[0].resolve():
        return paths
    # B46：只要显式指定了数据目录（测试/隔离环境/自定义目录），就不得顺手删除
    # 真实用户 legacy salt；否则 pytest 的 B37 端到端用例会误删生产盐值。
    if os.environ.get("CHALLENGE_DAILY_DATA_DIR"):
        return paths
    paths.append(legacy)
    return paths


def _salt_backup_dir() -> Path:
    """B46：盐值备份目录，被遗忘权必须连同备份一起删除。"""
    return Path(config.DATA_DIR) / "backups" / "salt"


def export_payload() -> dict:
    """可携带权导出：DB 全业务表 + 盐值 + home 遗留文件。"""
    import db
    payload = {
        "exported_at": datetime.now().isoformat(),
        "data_dir": str(config.DATA_DIR),
        "tables": {},
        "files": {},
    }
    with db.get_conn() as conn:
        _ensure_vec_extension(conn)
        for table in user_tables(conn):
            try:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
                payload["tables"][table] = [dict(row) for row in rows]
            except Exception as e:
                payload["tables"][table] = {"_export_error": str(e)}
    salt = Path(config.DATA_DIR) / "screenshot_salt.bin"
    if salt.exists():
        payload["files"]["screenshot_salt.bin"] = {
            "base64": base64.b64encode(salt.read_bytes()).decode("ascii"),
            "size": salt.stat().st_size,
        }
    if enterprise_store.HOME_DATA_DIR.exists():
        for path in enterprise_store.HOME_DATA_DIR.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(enterprise_store.HOME_DATA_DIR))
            try:
                payload["files"][f"home/{rel}"] = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                payload["files"][f"home/{rel}"] = {"_binary_size": path.stat().st_size}
    return payload


def _make_writable(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except Exception:
        pass


def _on_rm_error(func, path, exc_info):
    _make_writable(Path(path))
    try:
        func(path)
    except Exception:
        pass


def _delete_dir_contents(path: Path) -> int:
    removed = 0
    if not path.exists():
        return 0
    for child in path.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child, onerror=_on_rm_error)
            else:
                _make_writable(child)
                child.unlink()
            removed += 1
        except Exception as e:
            logger.warning(f"删除 {child} 失败: {e}")
    return removed


def delete_all() -> dict:
    """执行被遗忘权删除，返回可复核的清理清单。"""
    import db
    result = {
        "tables": {},
        "row_count": 0,
        "files_removed": [],
        "salt_removed": False,
        "errors": [],
    }
    with db.get_conn() as conn:
        _ensure_vec_extension(conn)
        vec_tables = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE sql LIKE '%USING vec0%'"
            ).fetchall()
        }
        tables = [t for t in user_tables(conn) if t not in vec_tables]
        try:
            conn.execute("BEGIN IMMEDIATE")
        except Exception:
            pass
        # sqlite-vec 虚表在脏 shadow 状态下无法 DELETE；整表重建是唯一可靠清空方式。
        for name, ddl in vec_tables.items():
            try:
                try:
                    before = int(conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0])
                except Exception:
                    before = 0
                conn.execute(f'DROP TABLE "{name}"')
                conn.execute(ddl)
                result["tables"][name] = before
                result["row_count"] += before
            except Exception as e:
                result["errors"].append(f"{name}: {e}")
                logger.warning(f"重建向量表 {name} 失败: {e}")
        for table in tables:
            try:
                before = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
                conn.execute(f"DELETE FROM {table}")
                result["tables"][table] = int(before)
                result["row_count"] += int(before)
            except Exception as e:
                result["errors"].append(f"{table}: {e}")
                logger.warning(f"清空 {table} 失败: {e}")
        conn.commit()

    for path in _salt_paths():
        try:
            if path.exists():
                path.unlink()
                result["salt_removed"] = True
                result["files_removed"].append(str(path))
        except Exception as e:
            result["errors"].append(f"{path}: {e}")

    backup_dir = _salt_backup_dir()
    if backup_dir.exists():
        removed = _delete_dir_contents(backup_dir)
        if removed:
            result["salt_removed"] = True
            result["files_removed"].append(f"{backup_dir} ({removed} entries)")

    if enterprise_store.HOME_DATA_DIR.exists():
        removed = _delete_dir_contents(enterprise_store.HOME_DATA_DIR)
        result["files_removed"].append(f"{enterprise_store.HOME_DATA_DIR} ({removed} entries)")
    for name in _USER_DIRS:
        path = Path(config.DATA_DIR) / name
        if path.exists():
            removed = _delete_dir_contents(path)
            if removed:
                result["files_removed"].append(f"{path} ({removed} entries)")
    for name in _USER_FILES:
        path = Path(config.DATA_DIR) / name
        if path.exists():
            try:
                path.unlink()
                result["files_removed"].append(str(path))
            except Exception as e:
                result["errors"].append(f"{path}: {e}")
    return result


def scan_state() -> dict:
    """删除后三目录扫描：DB 业务表、home、盐值。"""
    import db
    nonzero = {}
    with db.get_conn() as conn:
        _ensure_vec_extension(conn)
        for table in user_tables(conn):
            try:
                count = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]
                if count:
                    nonzero[table] = count
            except Exception:
                nonzero[table] = "unreadable"
    home_entries = []
    if enterprise_store.HOME_DATA_DIR.exists():
        home_entries = [str(p) for p in enterprise_store.HOME_DATA_DIR.rglob("*") if p.is_file()]
    salts = [str(p) for p in _salt_paths() if p.exists()]
    backup_dir = _salt_backup_dir()
    if backup_dir.exists():
        salts.extend(str(p) for p in backup_dir.rglob("*") if p.is_file())
    return {
        "db_nonzero_tables": nonzero,
        "home_files": home_entries,
        "salt_files": salts,
        "clean": not nonzero and not home_entries and not salts,
    }
