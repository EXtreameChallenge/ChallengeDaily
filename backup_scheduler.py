"""定时自动备份数据库（每日凌晨 3 点）+ T7: activities 归档"""
import threading
import logging
import time
import shutil
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_BACKUP_DIR = None
_scheduler_thread = None
_scheduler_stop = threading.Event()
_MAX_BACKUPS = 30  # 保留最近 30 个备份
# T7: 归档保留天数（超过此天数的 activities 迁移到归档库）
_ARCHIVE_RETENTION_DAYS = 90

def init_backup_scheduler(data_dir, db_path):
    """初始化自动备份调度器"""
    global _BACKUP_DIR
    _BACKUP_DIR = Path(data_dir) / "backups"
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    _scheduler_stop.clear()
    # 启动后台线程
    t = threading.Thread(target=_backup_loop, args=(db_path,), daemon=True, name="BackupScheduler")
    t.start()
    logger.info(f"自动备份调度器已启动，备份目录: {_BACKUP_DIR}")

def _backup_loop(db_path):
    """备份循环：每日凌晨 3 点触发"""
    while not _scheduler_stop.is_set():
        now = datetime.now()
        # 计算到下一个凌晨 3 点的秒数
        next_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_3am <= now:
            next_3am = next_3am.replace(day=now.day + 1)
        wait_sec = (next_3am - now).total_seconds()
        # 最多等 1 小时检查一次 stop 信号
        wait_sec = min(wait_sec, 3600)
        if _scheduler_stop.wait(wait_sec):
            break
        # 到达 3 点触发备份
        if datetime.now().hour == 3:
            try:
                _do_backup(db_path)
                _cleanup_old_backups()
                # T7: 备份后执行归档（将旧 activities 迁移到归档库）
                _do_archive(db_path)
            except Exception as e:
                logger.error(f"自动备份失败: {e}", exc_info=True)

def _do_backup(db_path):
    """执行一次备份"""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = _BACKUP_DIR / f"xiaohei-{ts}.db"
    shutil.copy2(db_path, backup_path)
    # 计算 SHA256
    with open(backup_path, 'rb') as f:
        sha256 = hashlib.sha256(f.read()).hexdigest()
    # 写 manifest
    manifest_path = backup_path.with_suffix('.manifest')
    manifest_path.write_text(
        f"file: {backup_path.name}\n"
        f"timestamp: {ts}\n"
        f"size: {backup_path.stat().st_size}\n"
        f"sha256: {sha256}\n"
        f"source: {db_path}\n",
        encoding='utf-8'
    )
    logger.info(f"自动备份完成: {backup_path} (sha256={sha256[:16]}...)")

def _cleanup_old_backups():
    """清理过期备份（保留最近 _MAX_BACKUPS 个）"""
    backups = sorted(_BACKUP_DIR.glob("xiaohei-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[_MAX_BACKUPS:]:
        try:
            old.unlink()
            old.with_suffix('.manifest').unlink(missing_ok=True)
            logger.info(f"清理过期备份: {old.name}")
        except Exception:
            pass

def stop_backup_scheduler():
    _scheduler_stop.set()

def manual_backup(db_path):
    """手动触发一次备份（供 API 调用）"""
    _do_backup(db_path)
    _cleanup_old_backups()


# ── T7: activities ATTACH DATABASE 归档 ──

def _do_archive(db_path):
    """将超过保留天数的 activities 迁移到归档库（使用 ATTACH DATABASE）

    步骤：
    1. ATTACH 归档库
    2. 在归档库创建 activities 表（如不存在）
    3. 在显式事务中：INSERT 旧数据到归档库 + DELETE 主库旧数据
    4. DETACH 归档库

    注意：归档库的 activities 表使用 original_id 保留原始 id，避免自增冲突。
    """
    import sqlite3
    from config import DATA_DIR

    archive_dir = DATA_DIR / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / "xiaohei-archive.db"

    cutoff = (date.today() - timedelta(days=_ARCHIVE_RETENTION_DAYS)).isoformat()
    cutoff_ts = f"{cutoff} 00:00:00"

    # 使用独立连接操作归档（避免与线程局部连接冲突）
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    try:
        conn.execute("ATTACH DATABASE ? AS archive", (str(archive_path),))
        # 确保归档表存在
        conn.execute("""
            CREATE TABLE IF NOT EXISTS archive.activities (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
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

        # 检查是否有需要归档的数据
        count_row = conn.execute(
            "SELECT COUNT(*) as cnt FROM main.activities WHERE timestamp < ?", (cutoff_ts,)
        ).fetchone()
        count = count_row["cnt"] if count_row else 0

        if count == 0:
            conn.execute("DETACH DATABASE archive")
            logger.debug("归档：无过期数据需要迁移")
            return 0

        # 显式事务：INSERT + DELETE 原子性
        conn.execute("BEGIN IMMEDIATE")
        try:
            # 迁移旧数据到归档库
            conn.execute("""
                INSERT INTO archive.activities
                    (timestamp, screenshot, app_name, window_title, category, summary,
                     interval_sec, ai_detail, windows_json, created_at, original_id)
                SELECT timestamp, screenshot, app_name, window_title, category, summary,
                       interval_sec, ai_detail, windows_json, created_at, id
                FROM main.activities
                WHERE timestamp < ?
            """, (cutoff_ts,))
            # 从主库删除已归档数据
            conn.execute("DELETE FROM main.activities WHERE timestamp < ?", (cutoff_ts,))
            conn.commit()
            logger.info(f"归档完成：迁移 {count} 条 activities（cutoff={cutoff_ts}）到 {archive_path.name}")
        except Exception:
            conn.rollback()
            raise
        finally:
            try:
                conn.execute("DETACH DATABASE archive")
            except Exception:
                pass
        return count
    except Exception as e:
        logger.error(f"归档失败: {e}", exc_info=True)
        try:
            conn.execute("DETACH DATABASE archive")
        except Exception:
            pass
        return 0
    finally:
        conn.close()


def auto_archive(db_path):
    """手动触发归档（供 API 调用）"""
    return _do_archive(db_path)
