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


def take_screenshot(monitor_index: int = 0, app_name: str = "") -> tuple[str, str, bool]:
    """
    截取屏幕，保存到 data/screenshots/，返回 (文件名, 绝对路径, 是否画面重复)。
    monitor_index:
      - 0 = 全部显示器的合集（虚拟桌面）
      - 1, 2, ... = 第1、2个显示器
    app_name: P17-3 前台应用名，用于截图质量分级
    P17-1: 保存时自动加密（如果 cryptography 可用）
    P17-3: 截图质量分级 — IDE/编辑器高质量，浏览器中等质量
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

        # P17-3: 截图质量分级 — IDE/编辑器用高质量保留代码细节
        quality = _get_screenshot_quality(app_name)
        max_width = _get_screenshot_max_width(app_name)

        # 等比缩放（使用 BILINEAR 替代 LANCZOS，截图缩放质量差异可忽略，
        # 但 CPU 开销显著降低）
        w, h = img.size
        if w > max_width:
            ratio = max_width / w
            new_h = int(h * ratio)
            resized = img.resize((max_width, new_h), Image.BILINEAR)
            img.close()  # 关闭原图
            img = resized

        # 生成文件名
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"screenshot_{ts}.jpg"
        filepath = SCREENSHOT_DIR / filename

        # P17-1: 加密保存（JPEG 字节先序列化到内存，加密后落盘）
        try:
            import io
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=quality)
            img_bytes = buf.getvalue()
            buf.close()
            from screenshot_crypto import save_encrypted_jpeg
            save_encrypted_jpeg(img_bytes, str(filepath))
        except Exception as e:
            # 降级为明文保存
            import logging
            logging.getLogger(__name__).warning(f"加密保存失败，降级明文: {e}")
            img.save(str(filepath), "JPEG", quality=quality)

        return filename, str(filepath), is_duplicate
    finally:
        img.close()  # 确保 Image 被释放


# ── P17-3: 截图质量分级 ──

# IDE/编辑器类应用：高质量保留代码细节
_HIGH_QUALITY_APPS = {
    'code.exe', 'cursor.exe', 'trae.exe', 'trae solo cn.exe', 'trae-solo-cn.exe',
    'devenv.exe', 'idea64.exe', 'pycharm64.exe', 'webstorm64.exe', 'goland64.exe',
    'clion64.exe', 'rider64.exe', 'studio64.exe', 'datagrip64.exe',
    'sublime_text.exe', 'atom.exe', 'notepad++.exe', 'vim.exe', 'gvim.exe',
}

# 浏览器类应用：中等质量即可
_MEDIUM_QUALITY_APPS = {
    'chrome.exe', 'msedge.exe', 'firefox.exe', 'opera.exe', 'brave.exe',
    'vivaldi.exe', 'arc.exe', 'safari.exe',
}


def _get_screenshot_quality(app_name: str) -> int:
    """P17-3: 根据应用类型返回截图质量"""
    if not app_name:
        return SCREENSHOT_QUALITY
    lower = app_name.lower()
    if lower in _HIGH_QUALITY_APPS:
        return min(95, SCREENSHOT_QUALITY + 20)  # IDE: 高质量
    if lower in _MEDIUM_QUALITY_APPS:
        return max(50, SCREENSHOT_QUALITY - 10)  # 浏览器: 中等
    return SCREENSHOT_QUALITY


def _get_screenshot_max_width(app_name: str) -> int:
    """P17-3: 根据应用类型返回最大宽度"""
    if not app_name:
        return SCREENSHOT_MAX_WIDTH
    lower = app_name.lower()
    if lower in _HIGH_QUALITY_APPS:
        # IDE 保留更大尺寸以看清代码
        return min(2560, SCREENSHOT_MAX_WIDTH + 640)
    return SCREENSHOT_MAX_WIDTH


def encode_image_to_base64(image_path: str) -> str:
    """将截图转为 base64 字符串，供 AI Vision API 使用
    P17-1: 自动解密加密文件
    """
    from screenshot_crypto import load_and_decrypt, is_encrypted_file
    try:
        if is_encrypted_file(image_path):
            # 加密文件：解密后转 base64
            img_bytes = load_and_decrypt(image_path)
            return base64.b64encode(img_bytes).decode("utf-8")
        else:
            # 明文文件：直接读取
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        # 兜底：直接读取
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
