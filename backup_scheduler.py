"""定时自动备份数据库（每日凌晨 3 点）"""
import threading
import logging
import time
import shutil
import hashlib
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger(__name__)

_BACKUP_DIR = None
_scheduler_thread = None
_scheduler_stop = threading.Event()
_MAX_BACKUPS = 30  # 保留最近 30 个备份

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
