"""
Obsidian 定时同步调度器
======================
每隔一段时间自动执行增量同步：
  1. 幕布 → Obsidian（写出 .md 文件，增量：未变更的跳过）
  2. Obsidian → 项目（扫描 + 向量化，增量：未变更的跳过）

设计要点：
  - 增量同步，没变化的自动跳过，不会重复干活
  - vault 未配置时静默跳过，不报错
  - 出错不影响主流程，记录日志后等待下次
  - 可通过配置调整同步间隔
"""
import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)

_scheduler_thread = None
_scheduler_stop = threading.Event()
_last_sync_time = None

# 默认同步间隔（秒）：15 分钟
DEFAULT_INTERVAL_SEC = 15 * 60


def get_interval_sec() -> int:
    """获取同步间隔（秒），优先从 settings 读取"""
    try:
        from config import load_settings
        settings = load_settings()
        minutes = settings.get("obsidian_sync_interval_min", 15)
        return max(60, int(minutes) * 60)  # 最短 1 分钟
    except Exception:
        return DEFAULT_INTERVAL_SEC


def init_obsidian_scheduler():
    """初始化 Obsidian 定时同步调度器（幂等，重复调用安全）"""
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("Obsidian 定时同步调度器已在运行，跳过重复启动")
        return
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(target=_sync_loop, daemon=True, name="ObsidianSyncScheduler")
    _scheduler_thread.start()
    logger.info("Obsidian 定时同步调度器已启动（间隔 %d 分钟）", get_interval_sec() // 60)


def stop_obsidian_scheduler():
    """停止调度器"""
    _scheduler_stop.set()
    logger.info("Obsidian 定时同步调度器已停止")


def _sync_loop():
    """同步循环：每隔一段时间执行一次增量同步"""
    # 启动后先等 2 分钟，避免和后端启动、首次幕布同步抢资源
    if _scheduler_stop.wait(120):
        return

    while not _scheduler_stop.is_set():
        try:
            _run_sync_once()
        except Exception as e:
            logger.error(f"Obsidian 定时同步异常: {e}", exc_info=True)

        # 等待下一次同步（可被 stop 信号中断）
        interval = get_interval_sec()
        _scheduler_stop.wait(interval)


def _run_sync_once():
    """执行一次完整的增量同步"""
    global _last_sync_time

    # 检查 vault 是否配置
    try:
        import obsidian_sync
        if not obsidian_sync.is_vault_configured():
            logger.debug("Obsidian vault 未配置，跳过定时同步")
            return
    except Exception as e:
        logger.warning(f"检查 vault 配置失败: {e}")
        return

    start_time = time.time()
    logger.info("Obsidian 定时同步开始")

    # 第一步：幕布 → Obsidian 写出
    try:
        import obsidian_sync
        result = obsidian_sync.sync_mubu_to_obsidian(force=False)
        logger.info(
            f"  幕布→Obsidian: 总计{result.get('total_docs', 0)}篇, "
            f"写入{result.get('written', 0)}, 跳过{result.get('skipped', 0)}, "
            f"失败{result.get('failed', 0)}"
        )
    except Exception as e:
        logger.warning(f"  幕布→Obsidian 写出失败（非致命）: {e}")

    # 第二步：Obsidian → 项目扫描 + 向量化
    try:
        import obsidian_reader
        obsidian_reader.init_obsidian_schema()
        result = obsidian_reader.scan_vault(force=False)
        logger.info(
            f"  Obsidian→项目: 总计{result.get('total_files', 0)}文件, "
            f"扫描{result.get('scanned', 0)}, 跳过{result.get('skipped', 0)}, "
            f"向量化{result.get('indexed', 0)}, 失败{result.get('failed', 0)}"
        )
    except Exception as e:
        logger.warning(f"  Obsidian→项目扫描失败（非致命）: {e}")

    elapsed = time.time() - start_time
    _last_sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"Obsidian 定时同步完成，耗时 {elapsed:.1f} 秒")


def get_scheduler_status() -> dict:
    """获取调度器状态"""
    return {
        "running": bool(_scheduler_thread and _scheduler_thread.is_alive()),
        "interval_min": get_interval_sec() // 60,
        "last_sync": _last_sync_time or "",
    }
