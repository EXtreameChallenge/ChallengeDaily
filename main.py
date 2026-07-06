"""
ChallengeDaily Windows 版 — 入口：调度器 + HTTP 服务
企业级：单实例保护、日志轮转、graceful shutdown
"""
import atexit
import logging
import logging.handlers
import os
import sys
import threading
import time
import msvcrt  # Windows 文件锁
from datetime import date, datetime

from config import HTTP_PORT, RETENTION_DAYS, DATA_DIR, BASE_DIR
import config
from db import init_db
from collector import Collector
from server import start_server
from report import generate_daily_report

# ── 单实例保护 ──
_LOCK_FILE = DATA_DIR / ".lock"
_lock_fh = None


def _acquire_singleton():
    """确保只有一个实例运行（Windows 文件锁）"""
    global _lock_fh
    try:
        _lock_fh = open(str(_LOCK_FILE), "w")
        msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
    except (OSError, IOError):
        print("ChallengeDaily 已在运行中，不可重复启动。")
        sys.exit(1)


def _release_singleton():
    """释放单实例锁"""
    global _lock_fh
    if _lock_fh:
        try:
            msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_UNLCK, 1)
            _lock_fh.close()
        except Exception:
            pass
        try:
            _LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass


# ── 日志配置（轮转） ──
_log_dir = DATA_DIR / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.handlers.RotatingFileHandler(
            str(_log_dir / "challenge-daily.log"),
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("challenge-daily")


# ── 设置缓存（避免每次采集循环都读磁盘）──
_settings_cache = {}
_settings_cache_time = 0
_SETTINGS_CACHE_TTL = 30  # 30秒缓存
_settings_cache_lock = threading.Lock()


def _get_cached_settings() -> dict:
    """读取缓存的设置，TTL 过期后刷新（线程安全）"""
    global _settings_cache, _settings_cache_time
    with _settings_cache_lock:
        now = time.time()
        if not _settings_cache or (now - _settings_cache_time) > _SETTINGS_CACHE_TTL:
            from config import load_settings
            _settings_cache = load_settings()
            _settings_cache_time = now
        return _settings_cache.copy()


def main():
    # 0. 单实例保护
    _acquire_singleton()

    print("""
╔══════════════════════════════════════╗
║       ChallengeDaily  Windows 版 v1.2.0    ║
║   截图 → AI 分析 → 分类 → Markdown   ║
╚══════════════════════════════════════╝
    """)

    # 1. 初始化数据库
    init_db()
    logger.info("数据库初始化完成")

    # 2. 打印配置信息
    logger.info(f"截图间隔: {config.SCREENSHOT_INTERVAL_SEC}s")
    logger.info(f"HTTP API 端口: {HTTP_PORT}")
    logger.info(f"数据保留: {RETENTION_DAYS} 天")
    logger.info(f"日志目录: {_log_dir}")

    # 3. 在后台线程中启动 HTTP API
    api_thread = threading.Thread(target=start_server, daemon=True)
    api_thread.start()
    logger.info(f"HTTP API 已启动: http://127.0.0.1:{HTTP_PORT}")

    # 4. 启动采集器
    collector = Collector()

    # 注入到 server，使 API 路由可复用同一实例
    from server import set_collector
    set_collector(collector)

    # 5. 注册 atexit 兜底
    _shutdown_done = False
    def _shutdown():
        nonlocal _shutdown_done
        if _shutdown_done:
            return
        _shutdown_done = True
        collector.stop()
        try:
            generate_daily_report()
            logger.info("已生成今日日报")
        except Exception as e:
            logger.error(f"生成日报失败: {e}")
        _release_singleton()

    atexit.register(_shutdown)

    # 6. 主循环
    collector.on_start()
    stop = threading.Event()
    import server as _server_module  # 避免使用 from ... import 绑定值
    logger.info("ChallengeDaily已启动，按 Ctrl+C 退出")

    try:
        while not stop.is_set():
            try:
                settings = _get_cached_settings()
                now_hour = datetime.now().hour
                work_start = settings.get("work_start_hour", 0)
                work_end = settings.get("work_end_hour", 24)
                in_work_hours = work_start <= now_hour < work_end

                if _server_module._collector_paused:
                    logger.debug("采集器已暂停，跳过本次采集")
                elif in_work_hours:
                    collector.capture_once()
                else:
                    logger.debug(f"当前 {now_hour}:00 不在工作时间 {work_start}:00-{work_end}:00 内，跳过采集")

                # 非工作时间降低检查频率（日报/备份只需每天一次）
                if in_work_hours:
                    try:
                        _server_module.check_auto_report()
                    except Exception as e:
                        logger.error(f"自动日报检查异常: {e}")

                    now_minutes = datetime.now().minute
                    if now_minutes == 0:
                        try:
                            from file_utils import auto_backup_critical_files
                            auto_backup_critical_files(DATA_DIR)
                        except Exception as e:
                            logger.error(f"自动备份失败: {e}")

            except Exception as e:
                logger.error(f"采集循环异常: {e}")

            # 自适应休眠：非工作时间 5 分钟醒一次，工作时间正常间隔
            sleep_sec = config.SCREENSHOT_INTERVAL_SEC if in_work_hours else 300
            stop.wait(timeout=sleep_sec)

    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，正在退出...")

    _shutdown()
    logger.info("ChallengeDaily已退出")


if __name__ == "__main__":
    main()
