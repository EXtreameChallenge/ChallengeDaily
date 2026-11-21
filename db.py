"""
ChallengeDaily Windows 版 — SQLite 数据库操作
企业级：线程局部连接、自动重试、schema 版本管理
优化：每线程独立连接避免 InterfaceError，WAL 只设一次
"""
import sqlite3
import threading
import time
import logging
import random
from datetime import datetime, date, timedelta
from typing import Optional
from contextlib import contextmanager
from config import DB_PATH, CATEGORIES
from db_migrations import init_db, SCHEMA_VERSION, DEFAULT_DATA_RETENTION_DAYS, _set_db_acl

logger = logging.getLogger(__name__)

# ── 线程局部连接（每线程独立 Connection，避免多线程共享导致 InterfaceError）──
_local = threading.local()
_conn_lock = threading.Lock()  # 仅保护 _init 等需要串行化的场景

# 标记 WAL 是否已在任何连接上设置（WAL 是数据库级属性，只需设一次）
_wal_initialized = False


def _get_thread_conn() -> sqlite3.Connection:
    """获取当前线程的局部连接（线程安全，每线程独立 Connection）"""
    global _wal_initialized
    conn = getattr(_local, 'conn', None)
    if conn is not None:
        return conn
    # 为当前线程创建新连接（busy_timeout/超时放宽：桌面端并发 AI 分析时减少 locked 误报）
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-4096")  # P29: 4MB cache (from 2MB)
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")  # P23: 256MB memory-mapped I/O
    # WAL 模式只需设一次（是数据库级属性，非连接级）
    if not _wal_initialized:
        with _conn_lock:
            if not _wal_initialized:
                conn.execute("PRAGMA journal_mode=WAL")
                _wal_initialized = True
                logger.info("SQLite WAL 模式已启用 (synchronous=NORMAL)")
    else:
        conn.execute("PRAGMA journal_mode=WAL")  # 确保当前连接也在 WAL 模式
    logger.debug(f"SQLite 线程连接已建立: {threading.current_thread().name}")
    _local.conn = conn
    return conn


def close_thread_conn() -> None:
    """关闭当前线程的 SQLite 连接；备份恢复前调用，避免文件句柄冲突。"""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None


@contextmanager
def get_conn():
    """获取数据库连接（contextmanager，使用线程局部连接，不关闭）

    异常时重置当前线程的连接，避免损坏后影响后续操作。
    """
    conn = _get_thread_conn()
    try:
        yield conn
    except sqlite3.DatabaseError as e:
        # 连接可能损坏，重置当前线程连接以便下次重建
        logger.error(f"数据库连接异常，将重建: {e}")
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None
        raise


# T7: 归档数据库路径（与主库同目录下的 archives 子目录）
_ARCHIVE_DB_PATH = None

def _get_archive_db_path():
    """获取归档数据库路径（惰性初始化）"""
    global _ARCHIVE_DB_PATH
    if _ARCHIVE_DB_PATH is not None:
        return _ARCHIVE_DB_PATH
    from config import DATA_DIR
    archive_dir = DATA_DIR / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _ARCHIVE_DB_PATH = archive_dir / "challengedaily-archive.db"
    return _ARCHIVE_DB_PATH


@contextmanager
def get_conn_with_archive():
    """获取带归档库 ATTACH 的连接（T7: 跨库查询 live + archived activities）

    用法：
        with db.get_conn_with_archive() as conn:
            rows = conn.execute("SELECT * FROM main.activities UNION ALL SELECT * FROM archive.activities")

    退出时自动 DETACH 归档库，避免连接泄漏。
    """
    conn = _get_thread_conn()
    archive_path = _get_archive_db_path()
    attached = False
    try:
        # 确保 archive 库有 activities 表
        conn.execute(f"ATTACH DATABASE ? AS archive", (str(archive_path),))
        attached = True
        conn.execute("""
            CREATE TABLE IF NOT EXISTS archive.activities (
                id          INTEGER PRIMARY KEY,
                timestamp   TEXT NOT NULL,
                screenshot  TEXT,
                app_name    TEXT,
                window_title TEXT,
                category    TEXT,
                summary     TEXT,
                interval_sec INTEGER DEFAULT 60,
                ai_detail   TEXT DEFAULT '',
                windows_json TEXT DEFAULT '[]',
                created_at  TEXT,
                original_id INTEGER,
                archived_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS archive.idx_archive_ts ON activities(timestamp)")
        yield conn
    except sqlite3.DatabaseError as e:
        logger.error(f"归档连接异常: {e}")
        try:
            if attached:
                conn.execute("DETACH DATABASE archive")
        except Exception:
            pass
        raise
    finally:
        if attached:
            try:
                conn.execute("DETACH DATABASE archive")
            except Exception:
                pass


def _execute_with_retry(conn, sql, params=(), max_retries=3):
    """带重试的 SQL 执行（处理 SQLITE_BUSY 锁冲突）"""
    for attempt in range(max_retries):
        try:
            return conn.execute(sql, params)
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                wait = 0.1 * (2 ** attempt)
                logger.warning(f"SQLite busy, retry {attempt+1}/{max_retries} after {wait:.1f}s")
                time.sleep(wait)
                continue
            raise
        except sqlite3.IntegrityError as e:
            logger.error(f"SQLite IntegrityError: {e}, SQL: {sql[:100]}")
            raise
    raise sqlite3.OperationalError(f"Failed after {max_retries} retries")
# ── B33: 按域拆分后的公共 API 重导出（调用方无需改 import）──
from db_layers.activities import *  # noqa: F401,F403
from db_layers.activities import _flush_pending_commits, _pending_commits  # noqa: F401
from db_layers.insights import *  # noqa: F401,F403
from db_layers.apps import *  # noqa: F401,F403
from db_layers.apps import _parse_json, _serialize_json, _sanitize_csv_cell  # noqa: F401
from db_layers.productivity import *  # noqa: F401,F403
from db_layers.journal import *  # noqa: F401,F403
from db_layers.habits import *  # noqa: F401,F403
from db_layers.planning import *  # noqa: F401,F403
from db_layers.planning import _week_start_of  # noqa: F401
