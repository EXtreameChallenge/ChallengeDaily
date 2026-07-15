"""
ChallengeDaily Windows 版 — 入口：调度器 + HTTP 服务
企业级：单实例保护、日志轮转、graceful shutdown
"""
import atexit
import hashlib
import logging
import logging.handlers
import os
import socket
import sys
import threading
import time
from datetime import date, datetime

from config import HTTP_PORT, RETENTION_DAYS, DATA_DIR, BASE_DIR
import config
from db import init_db
from collector import Collector
from server import start_server
from report import generate_daily_report

# ── 单实例保护（Windows 命名互斥体 + 端口预占） ──
# msvcrt 文件锁在跨进程快速启动场景下不可靠，已导致多个 Python 实例同时运行。
# 改用 CreateMutexW 命名互斥体，这是 Windows 官方推荐的多进程互斥方案。
_singleton_mutex = None


def _acquire_singleton():
    """确保只有一个实例运行。若已有实例或端口被占，直接退出。"""
    global _singleton_mutex

    # 1) 命名互斥体：跨进程可靠互斥
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        CreateMutexW = kernel32.CreateMutexW
        CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        CreateMutexW.restype = wintypes.HANDLE

        # 基于数据目录生成唯一互斥体名，避免不同安装/副本互相影响
        # 注意：必须使用确定性哈希（如 SHA256），Python 内置 hash() 会随进程随机化。
        data_dir_hash = hashlib.sha256(str(DATA_DIR.resolve()).encode("utf-8")).hexdigest()[:16]
        mutex_name = f"ChallengeDaily_SingleInstance_{data_dir_hash}"

        _singleton_mutex = CreateMutexW(None, False, mutex_name)
        err = ctypes.get_last_error()
        if not _singleton_mutex:
            print(f"无法创建单实例互斥体: {err}")
            sys.exit(1)
        if err == 183:  # ERROR_ALREADY_EXISTS
            print("ChallengeDaily 已在运行中，不可重复启动。")
            sys.exit(1)
    except Exception as e:
        print(f"单实例保护初始化失败: {e}")
        sys.exit(1)

    # 2) 端口预占：进一步防止旧实例未释放端口导致的冲突
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", HTTP_PORT))
        sock.close()
    except OSError:
        sock.close()
        print(f"端口 {HTTP_PORT} 已被占用，可能是 ChallengeDaily 正在运行。")
        sys.exit(1)


def _release_singleton():
    """释放单实例锁（进程退出时由 atexit 调用）"""
    global _singleton_mutex
    if _singleton_mutex:
        try:
            import ctypes
            ctypes.WinDLL("kernel32").CloseHandle(_singleton_mutex)
            _singleton_mutex = None
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


def _get_version() -> str:
    """Read version from package.json for single source of truth."""
    import json
    try:
        pkg_path = BASE_DIR / "client" / "package.json"
        with open(pkg_path, "r", encoding="utf-8") as f:
            return "v" + json.load(f).get("version", "0.0.0")
    except Exception:
        return "v0.0.0"


def main():
    # 0. 单例保护
    _acquire_singleton()

    _version = _get_version()
    print(f"""
╔═══════════════════════════════════════╗
║   ChallengeDaily  Windows 版 {_version:<10} ║
║   截图 → AI 分析 → 分类 → Markdown   ║
╚═══════════════════════════════════════╝
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
            in_work_hours = True  # 默认值，防止 try 块内异常导致 NameError
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

                    # P9-2：晨报洞察推送（7-11 点每小时整点检查一次，去重在 morning_insight 内处理）
                    if now_minutes == 0 and 7 <= datetime.now().hour < 11:
                        try:
                            from morning_insight import push_morning_insights_if_due
                            push_morning_insights_if_due()
                        except Exception as e:
                            logger.debug(f"晨报洞察推送异常: {e}")

            except Exception as e:
                logger.error(f"采集循环异常: {e}")

            # 自适应休眠：非工作时间 5 分钟醒一次，工作时间使用 P8-3 自适应间隔
            if in_work_hours:
                # P8-3：尝试从采集器获取自适应间隔，回退到默认间隔
                adaptive = None
                try:
                    adaptive = collector.get_adaptive_interval()
                except Exception:
                    adaptive = None
                sleep_sec = adaptive if (adaptive and adaptive > 0) else config.SCREENSHOT_INTERVAL_SEC
            else:
                sleep_sec = 300
            stop.wait(timeout=sleep_sec)

    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C，正在退出...")

    _shutdown()
    logger.info("ChallengeDaily已退出")


if __name__ == "__main__":
    main()
