"""
ChallengeDaily Windows 版 — 前台应用追踪
使用 pywin32 (win32gui) 获取当前前台窗口信息
"""
import ctypes
from ctypes import wintypes
import logging

logger = logging.getLogger(__name__)

# ── Win32 API 声明 ──
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GetForegroundWindow = user32.GetForegroundWindow
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
GetWindowRect = user32.GetWindowRect
IsWindowVisible = user32.IsWindowVisible
IsIconic = user32.IsIconic
EnumWindows = user32.EnumWindows
IsWindow = user32.IsWindow
GetWindow = user32.GetWindow
GetParent = user32.GetParent
GetWindowLongW = user32.GetWindowLongW
OpenProcess = kernel32.OpenProcess
CloseHandle = kernel32.CloseHandle
QueryFullProcessImageNameW = kernel32.QueryFullProcessImageNameW
GetSystemMetrics = user32.GetSystemMetrics
GetSystemMetrics.argtypes = [ctypes.c_int]
GetSystemMetrics.restype = ctypes.c_int

GW_OWNER = 4
GWL_EXSTYLE = -20
GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SM_CXSCREEN = 0
SM_CYSCREEN = 1

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# 配置 API 签名
GetWindow.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT]
GetWindow.restype = ctypes.wintypes.HWND
GetParent.argtypes = [ctypes.wintypes.HWND]
GetParent.restype = ctypes.wintypes.HWND
IsWindow.argtypes = [ctypes.wintypes.HWND]
IsWindow.restype = ctypes.c_bool
GetWindowLongW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
GetWindowLongW.restype = ctypes.wintypes.LONG

# 多窗口追踪：忽略这些系统进程/无意义窗口
_IGNORED_WINDOW_CLASSES = {
    "Windows.UI.Core.CoreWindow",  # 系统弹窗/开始菜单
    "Shell_TrayWnd",               # 任务栏
    "Shell_SecondaryTrayWnd",      # 多显示器任务栏
    "Progman",                     # 桌面
    "WorkerW",                     # 桌面 Worker
    "Credential Broker",           # 凭据弹窗
    "XamlExplorerHostIslandWindow",# 系统浮层
    "SysShadow",                   # 阴影窗口
}
_IGNORED_PROCESS_NAMES = {
    "explorer.exe",                # 仅当窗口标题为空时忽略（下面会特殊处理）
    "TextInputHost.exe",
    "SearchHost.exe",
    "ShellExperienceHost.exe",
    "StartMenuExperienceHost.exe",
    "RuntimeBroker.exe",
    "SecurityHealthSystray.exe",
    "dllhost.exe",
    "ctfmon.exe",
}

# ─ 进程路径缓存（PID → path，避免每次 EnumWindows 都 OpenProcess/CloseHandle）──
# 优化：限制缓存大小，防止长期运行内存泄漏
_pid_path_cache: dict[int, str] = {}
_PID_CACHE_MAX_SIZE = 200  # 最多缓存 200 个进程路径


def _get_process_path_by_hwnd(hwnd: int) -> str:
    """通过窗口句柄获取所属进程的完整可执行文件路径（带 PID 缓存）"""
    pid = wintypes.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    pid_val = pid.value

    # 查缓存
    if pid_val in _pid_path_cache:
        return _pid_path_cache[pid_val]

    # 缓存大小控制：超过上限时清空旧条目
    if len(_pid_path_cache) >= _PID_CACHE_MAX_SIZE:
        _pid_path_cache.clear()

    h_process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid_val)
    if not h_process:
        _pid_path_cache[pid_val] = ""
        return ""

    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(260)
        if QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size)):
            path = buf.value
            _pid_path_cache[pid_val] = path
            return path
        _pid_path_cache[pid_val] = ""
        return ""
    finally:
        CloseHandle(h_process)


def _get_process_name(hwnd: int) -> str:
    """通过窗口句柄获取所属进程的可执行文件名"""
    full_path = _get_process_path_by_hwnd(hwnd)
    if full_path:
        return full_path.split("\\")[-1]
    return "Unknown"


def _get_process_path(app_name: str) -> str:
    """
    根据进程名（如 chrome.exe）反查一个正在运行的实例的完整路径。
    通过枚举顶层窗口实现，未找到则返回空字符串。
    """
    try:
        found = {"path": ""}

        def enum_callback(hwnd, _):
            if found["path"]:
                return True
            if not user32.IsWindowVisible(hwnd):
                return True
            name = _get_process_name(hwnd)
            if name.lower() == app_name.lower():
                found["path"] = _get_process_path_by_hwnd(hwnd)
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        user32.EnumWindows(EnumWindowsProc(enum_callback), 0)
        return found["path"]
    except Exception as e:
        logger.warning(f"Failed to get process path for {app_name}: {e}")
        return ""


def get_foreground_app() -> dict:
    """
    获取当前前台应用信息。
    返回 {"app_name": "chrome.exe", "window_title": "GitHub - Google Chrome", "exe_path": "C:\\...\\chrome.exe"}
    桌面空闲时返回 {"app_name": "Desktop", "window_title": "桌面", "exe_path": ""}
    """
    hwnd = GetForegroundWindow()
    if not hwnd:
        return {"app_name": "Unknown", "window_title": "", "exe_path": ""}

    # 获取窗口标题
    length = GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buf, length + 1)
    window_title = buf.value

    # 获取进程名和路径
    app_name = _get_process_name(hwnd)
    exe_path = _get_process_path_by_hwnd(hwnd)

    # 桌面空闲：explorer.exe 的 "Program Manager" 窗口就是桌面
    if app_name.lower() == "explorer.exe" and window_title in ("Program Manager", ""):
        return {"app_name": "Desktop", "window_title": "桌面", "exe_path": ""}

    return {
        "app_name": app_name,
        "window_title": window_title,
        "exe_path": exe_path,
    }


def _get_window_class(hwnd: int) -> str:
    """获取窗口类名"""
    try:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        return buf.value
    except Exception:
        return ""


def _get_window_bounds(hwnd: int) -> dict:
    """获取窗口矩形 {left, top, right, bottom, width, height}"""
    try:
        rect = ctypes.wintypes.RECT()
        GetWindowRect(hwnd, ctypes.byref(rect))
        return {
            "left": rect.left,
            "top": rect.top,
            "right": rect.right,
            "bottom": rect.bottom,
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top,
        }
    except Exception:
        return {"left": 0, "top": 0, "right": 0, "bottom": 0, "width": 0, "height": 0}


def _should_include_window(hwnd: int, title: str, app_name: str, bounds: dict,
                            window_class: str = "", is_owned: bool = False) -> bool:
    """判断一个窗口是否值得记录和分析"""
    # 必须有标题
    if not title:
        return False

    # 最小尺寸过滤（排除小弹窗、任务栏图标等）
    width = bounds.get("width", 0)
    height = bounds.get("height", 0)
    if width < 120 or height < 80:
        return False

    # 忽略特定系统窗口类
    if window_class in _IGNORED_WINDOW_CLASSES:
        return False

    # 被拥有的窗口通常是对话框/弹窗，其所有者已经会被记录；
    # 但如果是前台窗口则保留（用户可能正在操作它）
    if is_owned and hwnd != GetForegroundWindow():
        return False

    # explorer.exe 只保留有实际标题的文件资源管理器窗口
    if app_name.lower() == "explorer.exe":
        if title in ("Program Manager", ""):
            return False

    # 忽略特定系统进程
    if app_name.lower() in {p.lower() for p in _IGNORED_PROCESS_NAMES}:
        return False

    # ApplicationFrameHost 是 UWP 应用宿主，通常显示系统设置/通知等
    # 用户工作场景中一般不需要记录，直接忽略
    if app_name.lower() == "applicationframehost.exe":
        return False

    # 排除明显是悬浮/工具窗口的类
    lower_class = window_class.lower()
    if "tooltip" in lower_class or "popup" in lower_class or "shadow" in lower_class:
        return False

    return True


def _is_real_top_level_window(hwnd: int) -> bool:
    """判断是否为真正的顶层窗口（非子窗口、非工具窗口、非被拥有窗口）"""
    try:
        # 必须是有效窗口
        if not IsWindow(hwnd):
            return False
        # 必须有 WS_VISIBLE（IsWindowVisible 已检查）
        # 排除 WS_CHILD
        style = GetWindowLongW(hwnd, GWL_STYLE)
        if style & WS_CHILD:
            return False
        # 排除工具窗口（除非它是前台窗口）
        ex_style = GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex_style & WS_EX_TOOLWINDOW and hwnd != GetForegroundWindow():
            return False
        # 排除 WS_EX_NOACTIVATE 的不可激活窗口
        if ex_style & WS_EX_NOACTIVATE and hwnd != GetForegroundWindow():
            return False
        return True
    except Exception:
        return False


def get_visible_windows(min_width: int = 120, min_height: int = 80,
                        max_windows: int = 3) -> list[dict]:
    """
    枚举屏幕上所有可见的非最小化顶层窗口。
    只返回当前屏幕上实际可见的前 max_windows 个窗口（Z-Order 最前面的），
    避免返回大量后台被遮挡的窗口。
    返回按 Z-Order 排序的窗口列表（最前台在前），每个元素包含：
      {
        "app_name": "chrome.exe",
        "window_title": "GitHub - Google Chrome",
        "exe_path": "C:\\...\\chrome.exe",
        "bounds": {"left": 0, "top": 0, "width": 1920, "height": 1080},
        "is_foreground": true,
        "z_order": 0,
        "area_ratio": 0.5
      }
    """
    try:
        foreground_hwnd = GetForegroundWindow()
        screen_w = GetSystemMetrics(SM_CXSCREEN)
        screen_h = GetSystemMetrics(SM_CYSCREEN)
        screen_area = screen_w * screen_h if screen_w > 0 and screen_h > 0 else 1
        windows = []
        z_order = 0

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
        )

        def enum_callback(hwnd, _):
            nonlocal z_order
            # 可见且未最小化
            if not IsWindowVisible(hwnd) or IsIconic(hwnd):
                return True

            # 只保留真正的顶层窗口
            if not _is_real_top_level_window(hwnd):
                return True

            # 窗口标题
            length = GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()

            app_name = _get_process_name(hwnd)
            bounds = _get_window_bounds(hwnd)
            window_class = _get_window_class(hwnd)
            owner = GetWindow(hwnd, GW_OWNER)
            is_owned = bool(owner and IsWindow(owner))

            if bounds.get("width", 0) < min_width or bounds.get("height", 0) < min_height:
                return True

            if not _should_include_window(hwnd, title, app_name, bounds, window_class, is_owned):
                return True

            exe_path = _get_process_path_by_hwnd(hwnd)
            win_area = abs(bounds.get("width", 0) * bounds.get("height", 0))
            area_ratio = win_area / screen_area
            windows.append({
                "app_name": app_name,
                "window_title": title,
                "exe_path": exe_path,
                "bounds": bounds,
                "is_foreground": hwnd == foreground_hwnd,
                "z_order": z_order,
                "area_ratio": round(area_ratio, 4),
            })
            z_order += 1
            return True

        EnumWindows(EnumWindowsProc(enum_callback), 0)

        # 按 Z-Order（已经由 EnumWindows 保证）切片，但确保前台窗口一定在第一位
        if windows and not windows[0].get("is_foreground"):
            fg_idx = next((i for i, w in enumerate(windows) if w.get("is_foreground")), -1)
            if fg_idx > 0:
                fg_window = windows.pop(fg_idx)
                windows.insert(0, fg_window)

        return windows[:max_windows]
    except Exception as e:
        logger.warning(f"枚举可见窗口失败: {e}")
        return []


# ── 应用名称映射表（可扩展）──
APP_NAME_MAP = {
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox",
    "Code.exe": "VS Code",
    "devenv.exe": "Visual Studio",
    "idea64.exe": "IntelliJ IDEA",
    "pycharm64.exe": "PyCharm",
    "webstorm64.exe": "WebStorm",
    "goland64.exe": "GoLand",
    "clion64.exe": "CLion",
    "rider64.exe": "Rider",
    "studio64.exe": "Android Studio",
    "WINWORD.EXE": "Word",
    "EXCEL.EXE": "Excel",
    "POWERPNT.EXE": "PowerPoint",
    "OUTLOOK.EXE": "Outlook",
    "Teams.exe": "Microsoft Teams",
    "WeChat.exe": "微信",
    "Weixin.exe": "微信",
    "DingTalk.exe": "钉钉",
    "Feishu.exe": "飞书",
    "Telegram.exe": "Telegram",
    "Discord.exe": "Discord",
    "WindowsTerminal.exe": "终端",
    "cmd.exe": "命令提示符",
    "PowerShell.exe": "PowerShell",
    "explorer.exe": "文件资源管理器",
    "Desktop": "桌面",
    "Navicat.exe": "Navicat",
    "DataGrip64.exe": "DataGrip",
    "postman.exe": "Postman",
    "Cursor.exe": "Cursor",
    "Trae.exe": "TRAE SOLO CN",
    "Trae Solo CN.exe": "TRAE SOLO CN",
    "Trae-Solo-CN.exe": "TRAE SOLO CN",
    "Electron.exe": "Electron",
    "docker.exe": "Docker Desktop",
    "Figma.exe": "Figma",
    "Notion.exe": "Notion",
    "Obsidian.exe": "Obsidian",
    "TickTick.exe": "滴答清单",
    "Todoist.exe": "Todoist",
    "qq.exe": "QQ",
    "QQ.exe": "QQ",
    "WXWork.exe": "企业微信",
    "Marvis.exe": "Marvis",
    "ApplicationFrameHost.exe": "UWP 应用",
}

# ── O(1) 显示名查找表（启动时构建，避免每次线性扫描）──
_APP_NAME_MAP_LOWER: dict[str, str] = {k.lower(): v for k, v in APP_NAME_MAP.items()}


def get_display_name(app_name: str) -> str:
    """将进程名转为友好显示名（大小写不敏感，O(1) 查找）"""
    return _APP_NAME_MAP_LOWER.get(app_name.lower(), app_name.replace(".exe", ""))


# ── 闲置检测 ──
def get_idle_seconds() -> int:
    """
    获取用户闲置时间（秒）。
    使用 Win32 GetLastInputInfo 检测键盘/鼠标最后活动时间。
    使用 GetTickCount64 避免 32 位溢出问题（系统运行 >49.7 天）。
    """
    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if user32.GetLastInputInfo(ctypes.byref(lii)):
        # 使用 GetTickCount64（Windows Vista+）避免 49.7 天溢出
        try:
            kernel64 = ctypes.windll.kernel32
            kernel64.GetTickCount64.restype = ctypes.c_uint64
            current_tick = kernel64.GetTickCount64()
        except Exception:
            # 回退到 32 位版本
            current_tick = kernel32.GetTickCount()
        # GetLastInputInfo.dwTime 是 32-bit DWORD，在系统运行 >49.7 天后会溢出回绕
        # 需要显式处理回绕：将 current_tick 也截断到 32-bit 做计算
        low32_current = current_tick & 0xFFFFFFFF
        low32_last_input = lii.dwTime & 0xFFFFFFFF  # 确保 32-bit
        if low32_current >= low32_last_input:
            idle_ms = low32_current - low32_last_input
        else:
            # dwTime 回绕了：比如 current_tick=0x100000100, dwTime=0xFFFFFF00
            # 实际空闲 = (0x100000000 - 0xFFFFFF00) + 0x100 = 0x200
            idle_ms = (0x100000000 - low32_last_input) + low32_current
        return max(0, idle_ms // 1000)
    return 0
