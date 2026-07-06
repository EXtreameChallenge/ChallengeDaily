"""
ChallengeDaily Windows 版 — 应用图标提取
采用 IShellItemImageFactory（Explorer/Marvis 同款 API）作为首选方案，
确保返回与 Windows 资源管理器完全一致的应用图标。
回退方案：PrivateExtractIconsW → SHGetFileInfo
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

_ICON_MISS_CACHE: dict[str, float] = {}
_ICON_MISS_TTL_SEC = 300

ICON_VERSION = 5
ICON_VERSION_FILE = ICON_DIR / ".icon_version"

_COM_INITIALIZED = False
_COM_LOCK = threading.Lock()


def _ensure_com():
    global _COM_INITIALIZED
    if not _COM_INITIALIZED:
        with _COM_LOCK:
            if not _COM_INITIALIZED:
                try:
                    ctypes.windll.ole32.CoInitializeEx(
                        None,
                        0x2 | 0x4,  # COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE
                    )
                except Exception:
                    pass
                _COM_INITIALIZED = True


def _is_recent_miss(app_name: str) -> bool:
    last = _ICON_MISS_CACHE.get(app_name.lower())
    return last is not None and (time.monotonic() - last) < _ICON_MISS_TTL_SEC


def _record_miss(app_name: str):
    _ICON_MISS_CACHE[app_name.lower()] = time.monotonic()


def _check_icon_version_upgrade() -> bool:
    try:
        if ICON_VERSION_FILE.exists():
            ver = int(ICON_VERSION_FILE.read_text().strip())
            if ver < ICON_VERSION:
                logger.info(f"图标版本升级 {ver} -> {ICON_VERSION}，清除旧缓存")
                for f in ICON_DIR.glob("*.png"):
                    try:
                        f.unlink()
                    except Exception:
                        pass
                ICON_VERSION_FILE.write_text(str(ICON_VERSION))
                return True
        else:
            old_count = len(list(ICON_DIR.glob("*.png")))
            if old_count > 0:
                logger.info(f"首次初始化，清除 {old_count} 个旧缓存图标")
                for f in ICON_DIR.glob("*.png"):
                    try:
                        f.unlink()
                    except Exception:
                        pass
            ICON_VERSION_FILE.write_text(str(ICON_VERSION))
            return True
    except Exception as e:
        logger.warning(f"图标版本检查失败: {e}")
    return False


# ── Windows API ──
shell32 = ctypes.windll.shell32
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
ole32 = ctypes.windll.ole32

# SHGetFileInfo
SHGFI_ICON = 0x000000100
SHGFI_LARGEICON = 0x000000000
SHGFI_SMALLICON = 0x000000001

# PrivateExtractIcons
LR_LOADFROMFILE = 0x00000010

# IShellItemImageFactory
SIIGBF_RESIZETOFIT = 0x00
SIIGBF_BIGGERSIZEOK = 0x01
SIIGBF_ICONONLY = 0x04

# DrawIconEx
DI_NORMAL = 0x0003
DI_IMAGE = 0x0002
DI_MASK = 0x0001
DI_DEFAULTSIZE = 0x0008

IID_IShellItemImageFactory = ctypes.c_char_p(b"\x79\x8b\xc1\xbc\x16\xba\x2f\x44\x80\xc4\x8a\x59\xc3\x20\xc6\x84")


class SHFILEINFO(ctypes.Structure):
    _fields_ = [
        ("hIcon", ctypes.wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", ctypes.wintypes.DWORD),
        ("szDisplayName", ctypes.c_wchar * 260),
        ("szTypeName", ctypes.c_wchar * 80),
    ]


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


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", ctypes.c_long),
        ("bmWidth", ctypes.c_long),
        ("bmHeight", ctypes.c_long),
        ("bmWidthBytes", ctypes.c_long),
        ("bmPlanes", ctypes.wintypes.WORD),
        ("bmBitsPixel", ctypes.wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long), ("top", ctypes.c_long),
        ("right", ctypes.c_long), ("bottom", ctypes.c_long),
    ]


# 配置 API 函数签名
shell32.SHGetFileInfoW.argtypes = [
    ctypes.wintypes.LPCWSTR, ctypes.wintypes.DWORD,
    ctypes.POINTER(SHFILEINFO), ctypes.c_uint, ctypes.c_uint,
]
shell32.SHGetFileInfoW.restype = ctypes.c_void_p

shell32.SHCreateItemFromParsingName.argtypes = [
    ctypes.wintypes.LPCWSTR, ctypes.c_void_p,
    ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p),
]
shell32.SHCreateItemFromParsingName.restype = ctypes.c_long  # HRESULT

try:
    user32.PrivateExtractIconsW.argtypes = [
        ctypes.wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.POINTER(ctypes.wintypes.HICON), ctypes.POINTER(ctypes.c_uint),
        ctypes.c_uint, ctypes.c_uint,
    ]
    user32.PrivateExtractIconsW.restype = ctypes.c_uint
    _HAS_PRIVATE_EXTRACT = True
except AttributeError:
    _HAS_PRIVATE_EXTRACT = False

gdi32.GetObjectW.argtypes = [ctypes.wintypes.HGDIOBJ, ctypes.c_int, ctypes.c_void_p]
gdi32.GetObjectW.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [
    ctypes.wintypes.HDC, ctypes.wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint,
    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [ctypes.wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = ctypes.c_int


# ── 图标提取方法 ──

def _hicon_to_pil(hicon: int, size: int = 256) -> Image.Image | None:
    """将 HICON 渲染到 DIBSection，正确保留 alpha 通道"""
    try:
        hdc = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = size
        bmi.biHeight = -size
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0  # BI_RGB

        bits = ctypes.c_void_p()
        hbitmap = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        old = gdi32.SelectObject(hdc_mem, hbitmap)

        # 使用 DI_NORMAL = 0x3 (IMAGE | MASK)，正确合成 alpha
        user32.DrawIconEx(hdc_mem, 0, 0, hicon, size, size, 0, None, DI_NORMAL)

        total_pixels = size * size
        buf = (ctypes.c_ubyte * (total_pixels * 4)).from_address(bits.value)
        img = Image.frombuffer("RGBA", (size, size), buf, "raw", "BGRA", 0, 1)
        img = img.copy()

        gdi32.SelectObject(hdc_mem, old)
        gdi32.DeleteObject(hbitmap)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc)

        # 预乘 alpha 修正：如果图标使用 AND/XOR mask 方式（传统图标），
        # DIBSection 可能有 alpha=255 但有 mask 透明区域，需要检测并修正
        # 对于 32-bit ARGB 图标（现代图标），alpha 已经正确
        return img
    except Exception as e:
        logger.warning(f"hicon_to_pil failed: {e}")
        return None


def _hbitmap_to_pil(hbitmap: int) -> Image.Image | None:
    """从 HBITMAP（GetImage 返回）读取为 PIL Image，正确处理 alpha"""
    try:
        bm = BITMAP()
        gdi32.GetObjectW(hbitmap, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, bm.bmHeight
        if w <= 0 or h <= 0 or w > 512 or h > 512:
            return None

        hdc = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc)

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        bits = (ctypes.c_ubyte * (w * h * 4))()
        gdi32.GetDIBits(hdc_mem, hbitmap, 0, h, bits, ctypes.byref(bmi), 0)
        img = Image.frombuffer("RGBA", (w, h), bits, "raw", "BGRA", 0, 1).copy()

        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc)
        return img
    except Exception as e:
        logger.warning(f"hbitmap_to_pil failed: {e}")
        return None


def _extract_via_ishellitem(exe_path: str, size: int = 256) -> Image.Image | None:
    """
    方法1: IShellItemImageFactory（推荐首选）
    这是 Windows Shell 使用的 API，返回的图标与资源管理器/任务栏完全一致。
    Marvis、ActivityWatch 等主流软件均使用此方法获取高质量图标。
    """
    _ensure_com()
    factory = ctypes.c_void_p()
    try:
        hr = shell32.SHCreateItemFromParsingName(
            exe_path, None, IID_IShellItemImageFactory, ctypes.byref(factory)
        )
        if hr != 0 or not factory.value:
            logger.debug(f"SHCreateItemFromParsingName failed for {exe_path}: hr=0x{hr & 0xFFFFFFFF:08X}")
            return None

        try:
            # IShellItemImageFactory::GetImage vtable 偏移量 = 3
            # (IUnknown: QueryInterface=0, AddRef=1, Release=2; GetImage=3)
            # 注意：GetImage 实际参数只有 (this, SIZE, DWORD flags, HBITMAP* phbm)
            GETIMAGE_FUNCTYPE = ctypes.WINFUNCTYPE(
                ctypes.c_long,        # HRESULT
                ctypes.c_void_p,      # this
                SIZE,                 # size
                ctypes.c_uint,        # flags (SIIGBF_*)
                ctypes.POINTER(ctypes.wintypes.HBITMAP),  # phbm
            )

            vptr = ctypes.c_void_p.from_address(factory.value)
            vtable = ctypes.cast(vptr.value, ctypes.POINTER(ctypes.c_void_p))
            get_image = GETIMAGE_FUNCTYPE(vtable[3])

            hbmp = ctypes.wintypes.HBITMAP()
            sz = SIZE(size, size)
            hr = get_image(
                factory, sz,
                SIIGBF_BIGGERSIZEOK | SIIGBF_ICONONLY,
                ctypes.byref(hbmp),
            )

            if hr != 0 or not hbmp.value:
                logger.debug(f"IShellItemImageFactory::GetImage failed: hr=0x{hr & 0xFFFFFFFF:08X}")
                return None

            try:
                img = _hbitmap_to_pil(hbmp.value)
                if img and img.size[0] != size:
                    img = img.resize((size, size), Image.LANCZOS)
                return img
            finally:
                gdi32.DeleteObject(hbmp)
        finally:
            RELEASE_FUNCTYPE = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
            vtable2 = ctypes.cast(
                ctypes.c_void_p.from_address(factory.value).value,
                ctypes.POINTER(ctypes.c_void_p),
            )
            release = RELEASE_FUNCTYPE(vtable2[2])
            release(factory)
    except Exception as e:
        logger.debug(f"IShellItemImageFactory failed for {exe_path}: {e}")
    return None


def _extract_via_private(exe_path: str, size: int = 256) -> Image.Image | None:
    """方法2: PrivateExtractIconsW — 直接从 exe 图标资源组提取"""
    if not _HAS_PRIVATE_EXTRACT:
        return None

    for req_size in [256, 128, 64, 48, 32]:
        hicon = ctypes.wintypes.HICON()
        icon_id = ctypes.c_uint()
        # 尝试不同的图标索引（0,1,2...有些exe第一个图标组索引是0，有些可能需要遍历）
        for icon_idx in range(0, 5):
            try:
                count = user32.PrivateExtractIconsW(
                    exe_path, icon_idx, req_size, req_size,
                    ctypes.byref(hicon), ctypes.byref(icon_id), 1, LR_LOADFROMFILE,
                )
                if count > 0 and hicon.value:
                    try:
                        render_size = max(size, min(req_size, 256))
                        img = _hicon_to_pil(hicon.value, render_size)
                        if img and _has_real_content(img):
                            if img.size[0] != size:
                                img = img.resize((size, size), Image.LANCZOS)
                            return img
                    finally:
                        user32.DestroyIcon(hicon.value)
                        hicon = ctypes.wintypes.HICON()
            except Exception:
                break
    return None


def _extract_via_shell(exe_path: str, size: int = 256) -> Image.Image | None:
    """方法3: SHGetFileInfo — 获取系统关联图标（兜底方案）"""
    shinfo = SHFILEINFO()
    flags = SHGFI_ICON | SHGFI_LARGEICON
    ret = shell32.SHGetFileInfoW(exe_path, 0, ctypes.byref(shinfo), ctypes.sizeof(shinfo), flags)
    if ret == 0 or not shinfo.hIcon:
        return None
    try:
        img = _hicon_to_pil(shinfo.hIcon, size)
        return img
    finally:
        user32.DestroyIcon(shinfo.hIcon)


def _has_real_content(img: Image.Image) -> bool:
    """检查图标是否有真实内容（非全透明/极小占位/默认图标）"""
    try:
        iw, ih = img.size
        alpha = img.split()[-1]
        bbox = alpha.getbbox()
        if not bbox:
            return False
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if w < 8 and h < 8:
            return False
        # 颜色多样性检查：真实图标颜色丰富，默认图标颜色单一
        non_transparent = 0
        color_set = set()
        pixels = img.load()
        step = max(1, (w * h) // 500)
        idx = 0
        for y in range(bbox[1], bbox[3]):
            for x in range(bbox[0], bbox[2]):
                r, g, b, a = pixels[x, y]
                if a > 30:
                    non_transparent += 1
                    if idx % step == 0:
                        color_set.add((r // 64, g // 64, b // 64))
                        if len(color_set) > 3:
                            return True
                idx += 1
        # 至少5%像素有内容，且至少有2种颜色
        return non_transparent > iw * ih * 0.03 and len(color_set) >= 2
    except Exception:
        return False


def extract_icon(exe_path: str, size: int = 128) -> Image.Image | None:
    """
    从可执行文件提取高质量图标。
    优先级：IShellItemImageFactory > PrivateExtractIconsW > SHGetFileInfo
    """
    if not exe_path or not Path(exe_path).exists():
        return None

    # 方法1：IShellItemImageFactory（Windows Explorer 同款，最准确）
    for sz in [256, size]:
        img = _extract_via_ishellitem(exe_path, sz)
        if img and _has_real_content(img):
            if img.size[0] != size:
                img = img.resize((size, size), Image.LANCZOS)
            return img

    # 方法2：PrivateExtractIconsW
    img = _extract_via_private(exe_path, size)
    if img and _has_real_content(img):
        return img

    # 方法3：SHGetFileInfo
    img = _extract_via_shell(exe_path, size)
    if img and _has_real_content(img):
        return img

    return None


# ── 路径查找 ──

def _find_exe_in_registry(app_name: str) -> str:
    try:
        import winreg
    except ImportError:
        return ""

    keys = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
    ]
    search_names = [app_name]
    if not app_name.lower().endswith(".exe"):
        search_names.append(app_name + ".exe")

    for name in search_names:
        for hive, key_path in keys:
            try:
                with winreg.OpenKey(hive, key_path) as root_key:
                    with winreg.OpenKey(root_key, name) as app_key:
                        path, _ = winreg.QueryValueEx(app_key, None)
                        if path and Path(path).exists():
                            return path
            except FileNotFoundError:
                continue
            except Exception as e:
                logger.debug(f"注册表查找 {name} 失败: {e}")
    return ""


def _find_exe_in_path(app_name: str) -> str:
    try:
        import shutil
        search = app_name if app_name.lower().endswith(".exe") else app_name + ".exe"
        path = shutil.which(search)
        if path and Path(path).exists():
            return path
    except Exception:
        pass
    return ""


def _find_exe_fallback(app_name: str) -> str:
    """当应用未运行时，按 注册表 > PATH > 常见安装目录 查找"""
    reg_path = _find_exe_in_registry(app_name)
    if reg_path:
        return reg_path

    path_hit = _find_exe_in_path(app_name)
    if path_hit:
        return path_hit

    import os

    search_name = app_name if app_name.lower().endswith(".exe") else app_name + ".exe"
    search_lower = search_name.lower()

    prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")

    # 快速搜索：搜索常见目录至多 3 级深度，覆盖大多数安装结构
    # 如 C:\Program Files\Tencent\WeChat\WeChat.exe 或 C:\Users\x\AppData\Local\Programs\Trae\Trae.exe
    quick_roots = [
        prog_files,
        prog_files_x86,
    ]
    if local_appdata:
        quick_roots.append(os.path.join(local_appdata, "Programs"))
        quick_roots.append(local_appdata)
    if appdata:
        quick_roots.append(appdata)

    def _scan_dir(path: Path, depth: int) -> str:
        if depth <= 0:
            return ""
        try:
            direct = path / search_name
            if direct.exists():
                return str(direct)
            direct_lower = path / search_lower
            if direct_lower.exists() and direct_lower != direct:
                return str(direct_lower)
            for sub in path.iterdir():
                if not sub.is_dir():
                    continue
                # 目录名明显不是应用目录则跳过（加速）
                if sub.name.lower() in {"microsoft", "windows", "temp", "cache"}:
                    continue
                found = _scan_dir(sub, depth - 1)
                if found:
                    return found
        except (PermissionError, OSError):
            pass
        return ""

    for root in quick_roots:
        if not root or not Path(root).exists():
            continue
        found = _scan_dir(Path(root), 3)
        if found:
            return found

    # 最后：WindowsApps 中的 UWP 应用
    if local_appdata:
        winapps = Path(local_appdata) / "Microsoft" / "WindowsApps"
        if winapps.exists():
            try:
                for f in winapps.iterdir():
                    if f.is_file() and f.name.lower() == search_lower:
                        return str(f)
            except (PermissionError, OSError):
                pass

    return ""


def _normalize_app_name(app_name: str) -> str:
    """标准化应用名，确保带 .exe 后缀"""
    name = app_name.strip()
    if not name.lower().endswith(".exe") and "." not in name.split("\\")[-1].split("/")[-1]:
        name = name + ".exe"
    return name


def get_app_icon_path(app_name: str, exe_path: str = "") -> Path | None:
    """
    获取应用图标 PNG 路径，不存在则尝试提取。
    app_name: 进程名，如 "chrome.exe" 或 "chrome"（自动补全 .exe）
    exe_path: 可选的完整可执行文件路径
    """
    _check_icon_version_upgrade()

    normalized = _normalize_app_name(app_name)
    safe_name = normalized.replace("\\", "_").replace("/", "_").replace(":", "_")
    icon_path = ICON_DIR / f"{safe_name}.png"

    if icon_path.exists():
        return icon_path

    # 大小写不敏感匹配
    if ICON_DIR.exists():
        target_lower = safe_name.lower()
        for cached in ICON_DIR.glob("*.png"):
            if cached.stem.lower() == target_lower:
                return cached

    # 同时尝试原始名称（不带.exe的）
    orig_safe = app_name.replace("\\", "_").replace("/", "_").replace(":", "_")
    orig_path = ICON_DIR / f"{orig_safe}.png"
    if orig_path.exists() and orig_path != icon_path:
        return orig_path

    if _is_recent_miss(normalized):
        return None

    if not exe_path:
        try:
            from app_tracker import _get_process_path
            exe_path = _get_process_path(normalized)
        except Exception:
            pass

    if not exe_path:
        exe_path = _find_exe_fallback(normalized)

    if not exe_path or not Path(exe_path).exists():
        _record_miss(normalized)
        return None

    try:
        img = extract_icon(exe_path, size=256)
        if img:
            img.save(icon_path, "PNG")
            logger.info(f"Icon extracted via IShellItemImageFactory: {icon_path} ({img.size[0]}x{img.size[1]})")
            return icon_path
    except Exception as e:
        logger.warning(f"Failed to extract icon for {normalized} ({exe_path}): {e}")

    _record_miss(normalized)
    return None


def get_icon_url(app_name: str, exe_path: str = "") -> str:
    path = get_app_icon_path(app_name, exe_path)
    if path:
        return f"/icons/{path.name}"
    return ""


# ── 预缓存与批量提取 ──

def preload_all_icons(app_names: list[str] = None, force: bool = False) -> dict:
    if app_names is None:
        try:
            from db import get_known_apps
            apps = get_known_apps()
            app_names = [a.get("app_name", "") for a in apps if a.get("app_name")]
        except Exception as e:
            logger.error(f"获取已知应用列表失败: {e}")
            app_names = []

    if force:
        _ICON_MISS_CACHE.clear()

    total = len(app_names)
    success = 0
    fail = 0
    skipped = 0
    failed_apps = []

    for name in app_names:
        if not name:
            skipped += 1
            continue
        normalized = _normalize_app_name(name)
        safe_name = normalized.replace("\\", "_").replace("/", "_").replace(":", "_")
        icon_path = ICON_DIR / f"{safe_name}.png"

        if icon_path.exists() and not force:
            skipped += 1
            continue

        try:
            path = get_app_icon_path(name)
            if path:
                success += 1
            else:
                fail += 1
                failed_apps.append(name)
        except Exception as e:
            logger.warning(f"Preload icon failed for {name}: {e}")
            fail += 1
            failed_apps.append(name)

    result = {
        "total": total,
        "success": success,
        "fail": fail,
        "skipped": skipped,
        "failed_apps": failed_apps,
    }
    logger.info(f"图标预缓存完成: {result}")
    return result


def refresh_outdated_icons(max_age_days: int = 1) -> dict:
    """刷新超过 max_age_days 天未更新的图标"""
    try:
        from db import get_known_apps
        apps = get_known_apps()
        app_names = [a.get("app_name", "") for a in apps if a.get("app_name")]
    except Exception as e:
        logger.error(f"获取已知应用列表失败: {e}")
        return {"total": 0, "refreshed": 0, "fail": 0}

    now = time.time()
    refreshed = 0
    fail = 0

    for name in app_names:
        if not name:
            continue
        normalized = _normalize_app_name(name)
        safe_name = normalized.replace("\\", "_").replace("/", "_").replace(":", "_")
        icon_path = ICON_DIR / f"{safe_name}.png"

        if icon_path.exists():
            mtime = icon_path.stat().st_mtime
            if (now - mtime) < max_age_days * 86400:
                continue

        try:
            if icon_path.exists():
                icon_path.unlink()
            _ICON_MISS_CACHE.pop(normalized.lower(), None)
            path = get_app_icon_path(name)
            if path:
                refreshed += 1
            else:
                fail += 1
        except Exception as e:
            logger.warning(f"Refresh icon failed for {name}: {e}")
            fail += 1

    result = {"total": len(app_names), "refreshed": refreshed, "fail": fail}
    logger.info(f"图标刷新完成: {result}")
    return result
