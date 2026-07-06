"""
ChallengeDaily Windows 版 — 截图模块
使用 mss 库进行跨平台屏幕截图，Pillow 做压缩缩放
优化：MSS 上下文复用、PIL Image 显式关闭、显示器信息缓存
"""
import base64
import hashlib
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from PIL import Image
import mss

from config import SCREENSHOT_DIR, SCREENSHOT_QUALITY, SCREENSHOT_MAX_WIDTH

# 上一次截图的感知哈希，用于画面去重
_last_phash: int | None = None
_phash_lock = threading.Lock()

# ── MSS 上下文复用（避免每 60 秒创建/销毁 GDI 资源）──
_mss_instance = None
_mss_lock = threading.Lock()
_monitors_cache = None
_monitors_cache_time = 0
_MONITORS_CACHE_TTL = 60  # 显示器信息 60 秒缓存（极少变化）


def _get_mss():
    """获取或创建 MSS 单例"""
    global _mss_instance
    with _mss_lock:
        if _mss_instance is None:
            _mss_instance = mss.mss()
        return _mss_instance


def _get_monitors():
    """获取显示器列表（带缓存）"""
    global _monitors_cache, _monitors_cache_time
    now = time.time()
    if _monitors_cache is None or (now - _monitors_cache_time) > _MONITORS_CACHE_TTL:
        sct = _get_mss()
        _monitors_cache = sct.monitors
        _monitors_cache_time = now
    return _monitors_cache


def _compute_phash(img: Image.Image, hash_size: int = 8) -> int:
    """
    计算图片的感知哈希 (pHash)。
    缩放到 hash_size x hash_size，转灰度，取均值二值化。
    返回 64-bit 整数。
    优化：使用 BILINEAR 替代 LANCZOS，8x8 缩放下视觉差异可忽略，
    但 CPU 开销降低约 60%（LANCZOS 需要更多卷积计算）。
    """
    # 缩小到 hash_size x hash_size，转灰度，取均值二值化
    gray = img.convert("L")
    small = gray.resize((hash_size, hash_size), Image.BILINEAR)
    gray.close()  # 显式关闭中间 Image
    pixels = list(small.getdata())
    small.close()  # 显式关闭
    avg = sum(pixels) / len(pixels)
    return sum((1 if p > avg else 0) << i for i, p in enumerate(pixels))


def _phash_distance(h1: int, h2: int) -> int:
    """计算两个感知哈希的汉明距离（不同bit数）"""
    return bin(h1 ^ h2).count("1")


def is_screen_duplicate(img: Image.Image, threshold: int = 5) -> bool:
    """
    判断当前截图是否与上一次几乎相同。
    threshold: 汉明距离阈值（0-64），越小越严格。5 是比较宽松的值。
    返回 True 表示画面重复。
    线程安全：通过 _phash_lock 保护全局 _last_phash。
    """
    global _last_phash
    current_hash = _compute_phash(img)
    with _phash_lock:
        if _last_phash is None:
            _last_phash = current_hash
            return False
        dist = _phash_distance(_last_phash, current_hash)
        _last_phash = current_hash
        return dist <= threshold


def get_active_monitor_index() -> int:
    """
    获取前台窗口所在的显示器索引（mss 的 1-based 索引）。
    使用缓存的显示器信息，避免每次创建 MSS 上下文。
    """
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return 0
        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        cx = (rect.left + rect.right) // 2
        cy = (rect.top + rect.bottom) // 2
        MONITOR_DEFAULTTONEAREST = 2
        monitor_handle = user32.MonitorFromPoint(
            ctypes.wintypes.POINT(cx, cy),
            MONITOR_DEFAULTTONEAREST,
        )
        if not monitor_handle:
            return 0
        monitors = _get_monitors()
        for i, mon in enumerate(monitors[1:], start=1):
            if (mon["left"] <= cx <= mon["left"] + mon["width"] and
                mon["top"] <= cy <= mon["top"] + mon["height"]):
                return i
        return 0
    except Exception:
        return 0


def take_screenshot(monitor_index: int = 0) -> tuple[str, str, bool]:
    """
    截取屏幕，保存到 data/screenshots/，返回 (文件名, 绝对路径, 是否画面重复)。
    monitor_index:
      - 0 = 全部显示器的合集（虚拟桌面）
      - 1, 2, ... = 第1、2个显示器
    """
    sct = _get_mss()
    monitors = _get_monitors()

    # 选择截图区域
    if monitor_index < len(monitors):
        monitor = monitors[monitor_index]
    else:
        monitor = monitors[0]

    sct_img = sct.grab(monitor)

    # 转换为 Pillow Image
    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

    try:
        # 画面去重检测
        is_duplicate = is_screen_duplicate(img)

        # 等比缩放（使用 BILINEAR 替代 LANCZOS，截图缩放质量差异可忽略，
        # 但 CPU 开销显著降低）
        w, h = img.size
        if w > SCREENSHOT_MAX_WIDTH:
            ratio = SCREENSHOT_MAX_WIDTH / w
            new_h = int(h * ratio)
            resized = img.resize((SCREENSHOT_MAX_WIDTH, new_h), Image.BILINEAR)
            img.close()  # 关闭原图
            img = resized

        # 生成文件名
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"screenshot_{ts}.jpg"
        filepath = SCREENSHOT_DIR / filename

        # 保存 JPEG
        img.save(str(filepath), "JPEG", quality=SCREENSHOT_QUALITY)
        return filename, str(filepath), is_duplicate
    finally:
        img.close()  # 确保 Image 被释放


def encode_image_to_base64(image_path: str) -> str:
    """将截图转为 base64 字符串，供 AI Vision API 使用"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def cleanup_screenshots(days: int):
    """清理超过保留天数的截图文件"""
    cutoff = time.mktime(
        (datetime.now() - timedelta(days=days)).timetuple()
    )
    for f in SCREENSHOT_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()


def get_screenshots_size_mb() -> float:
    """统计截图目录总大小（MB）"""
    total = 0
    for f in SCREENSHOT_DIR.iterdir():
        if f.is_file():
            total += f.stat().st_size
    return round(total / 1024 / 1024, 1)
