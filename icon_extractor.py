"""
ChallengeDaily Windows 版 — 应用图标提取
通过可执行文件路径提取图标，缓存为 PNG 供前端展示
"""
import ctypes
import ctypes.wintypes
import logging
import threading
import time
from pathlib import Path

from PIL import Image
from config import DATA_DIR

logger = logging.getLogger(__name__)

ICON_DIR = DATA_DIR / "icons"
ICON_DIR.mkdir(parents=True, exist_ok=True)

# 失败查找缓存：避免反复对不存在/找不到路径的应用做耗时搜索
_ICON_MISS_CACHE: dict[str, float] = {}
_ICON_MISS_TTL_SEC = 300


def _is_recent_miss(app_name: str) -> bool:
    last = _ICON_MISS_CACHE.get(app_name.lower())
    return last is not None and (time.monotonic() - last) < _ICON_MISS_TTL_SEC


def _record_miss(app_name: str):
    _ICON_MISS_CACHE[app_name.lower()] = time.monotonic()

# ── Windows API 常量 ──
SHGFI_ICON = 0x000000100
SHGFI_LARGEICON = 0x000000000
SHGFI_SMALLICON = 0x000000001
SHGFI_USEFILEATTRIBUTES = 0x000000010


class SHFILEINFO(ctypes.Structure):
    _fields_ = [
        ("hIcon", ctypes.wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", ctypes.wintypes.DWORD),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80),
    ]


_shell32 = ctypes.windll.shell32
_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32


def _get_shell_icon(exe_path: str, large: bool = True) -> int:
    """使用 SHGetFileInfo 获取图标句柄，返回 0 表示失败"""
    shinfo = SHFILEINFO()
    flags = SHGFI_ICON | (SHGFI_LARGEICON if large else SHGFI_SMALLICON)
    try:
        ret = _shell32.SHGetFileInfoW(
            exe_path,
            0,
            ctypes.byref(shinfo),
            ctypes.sizeof(shinfo),
            flags,
        )
        if ret == 0:
            return 0
        return shinfo.hIcon
    except Exception as e:
        logger.warning(f"SHGetFileInfo failed for {exe_path}: {e}")
        return 0


def _icon_to_image(hicon: int, size: int = 64) -> Image.Image | None:
    """将 HICON 转换为 PIL Image"""
    try:
        # 创建兼容位图
        hdc = _user32.GetDC(0)
        hdc_mem = _gdi32.CreateCompatibleDC(hdc)

        # BITMAPINFO 用于 32-bit DIB
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.wintypes.DWORD),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", ctypes.wintypes.WORD),
                ("biBitCount", ctypes.wintypes.WORD),
                ("biCompression", ctypes.wintypes.DWORD),
                ("biSizeImage", ctypes.wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", ctypes.wintypes.DWORD),
                ("biClrImportant", ctypes.wintypes.DWORD),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = size
        bmi.biHeight = -size  # 负值：自顶向下
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0  # BI_RGB

        bits = ctypes.c_void_p()
        hbitmap = _gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        old = _gdi32.SelectObject(hdc_mem, hbitmap)

        # 绘制图标到内存 DC
        _user32.DrawIconEx(hdc_mem, 0, 0, hicon, size, size, 0, None, 3)

        # 读取像素数据
        total_pixels = size * size
        buf = (ctypes.c_ubyte * (total_pixels * 4)).from_address(bits.value)
        img = Image.frombuffer("RGBA", (size, size), buf, "raw", "BGRA", 0, 1)
        img = img.copy()  # 脱离底层内存

        # 清理
        _gdi32.SelectObject(hdc_mem, old)
        _gdi32.DeleteObject(hbitmap)
        _gdi32.DeleteDC(hdc_mem)
        _user32.ReleaseDC(0, hdc)

        return img
    except Exception as e:
        logger.warning(f"Icon to image failed: {e}")
        return None


def _destroy_icon(hicon: int):
    if hicon:
        _user32.DestroyIcon(hicon)


def extract_icon(exe_path: str, size: int = 64) -> Image.Image | None:
    """从可执行文件路径提取图标，返回 PIL Image"""
    if not exe_path or not Path(exe_path).exists():
        return None
    hicon = _get_shell_icon(exe_path, large=True)
    if not hicon:
        return None
    try:
        return _icon_to_image(hicon, size)
    finally:
        _destroy_icon(hicon)


def _find_exe_in_registry(app_name: str) -> str:
    """通过 Windows 注册表 App Paths 查找可执行文件路径（行业惯例，快速准确）"""
    try:
        import winreg
    except ImportError:
        return ""

    keys = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
    ]
    for hive, key_path in keys:
        try:
            with winreg.OpenKey(hive, key_path) as root_key:
                with winreg.OpenKey(root_key, app_name) as app_key:
                    path, _ = winreg.QueryValueEx(app_key, None)
                    if path and Path(path).exists():
                        return path
        except FileNotFoundError:
            continue
        except Exception as e:
            logger.debug(f"注册表查找 {app_name} 失败: {e}")
    return ""


def _find_exe_in_path(app_name: str) -> str:
    """在 PATH 环境变量中查找可执行文件"""
    try:
        import shutil
        path = shutil.which(app_name)
        if path and Path(path).exists():
            return path
    except Exception:
        pass
    return ""


def _find_exe_fallback(app_name: str) -> str:
    """当应用未运行时，按 注册表 > PATH > 常见安装目录 的顺序查找 exe"""
    # 1. 注册表（最快，覆盖绝大多数安装版应用）
    reg_path = _find_exe_in_registry(app_name)
    if reg_path:
        return reg_path

    # 2. PATH（覆盖开发工具、便携应用）
    path_hit = _find_exe_in_path(app_name)
    if path_hit:
        return path_hit

    # 3. 兜底：常见安装目录，但限制深度避免全盘递归导致超时
    import os
    import glob

    candidates = []
    prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA", "")

    search_roots = [
        prog_files,
        prog_files_x86,
        os.path.join(local_appdata, "Programs"),
        os.path.join(local_appdata, "Microsoft", "WindowsApps"),
    ]

    for root in search_roots:
        if not root or not Path(root).exists():
            continue
        for pattern in [
            os.path.join(root, "**", app_name),
            os.path.join(root, "**", app_name.lower()),
        ]:
            try:
                matches = glob.glob(pattern, recursive=True)
                if matches:
                    candidates.extend(matches)
                    break
            except Exception:
                pass

    for p in candidates:
        if Path(p).exists() and "WindowsApps" not in p:
            return p
    for p in candidates:
        if Path(p).exists():
            return p
    return ""


def get_app_icon_path(app_name: str, exe_path: str = "") -> Path | None:
    """
    获取应用图标 PNG 路径，不存在则尝试提取。
    app_name: 进程名，如 chrome.exe
    exe_path: 可选的完整可执行文件路径
    """
    safe_name = app_name.replace("\\", "_").replace("/", "_").replace(":", "_")
    icon_path = ICON_DIR / f"{safe_name}.png"

    if icon_path.exists():
        return icon_path

    # 大小写不敏感匹配已缓存的图标（如 TRAE.exe ↔ Trae.exe ↔ trae.exe）
    if ICON_DIR.exists():
        target_lower = safe_name.lower()
        for cached in ICON_DIR.glob("*.png"):
            if cached.stem.lower() == target_lower:
                return cached

    # 近期查找失败的应用直接跳过，避免反复超时
    if _is_recent_miss(app_name):
        return None

    if not exe_path:
        # 尝试从 app_tracker 查找正在运行的实例
        try:
            from app_tracker import _get_process_path
            exe_path = _get_process_path(app_name)
        except Exception:
            pass

    if not exe_path:
        # 未运行则尝试注册表 / PATH / 安装目录查找
        exe_path = _find_exe_fallback(app_name)

    if not exe_path or not Path(exe_path).exists():
        _record_miss(app_name)
        return None

    try:
        img = extract_icon(exe_path)
        if img:
            img.save(icon_path, "PNG")
            logger.info(f"Icon extracted: {icon_path}")
            return icon_path
    except Exception as e:
        logger.warning(f"Failed to extract icon for {app_name}: {e}")

    _record_miss(app_name)
    return None


def get_icon_url(app_name: str, exe_path: str = "") -> str:
    """返回图标可访问的相对路径或空字符串"""
    path = get_app_icon_path(app_name, exe_path)
    if path:
        return f"/icons/{path.name}"
    return ""
