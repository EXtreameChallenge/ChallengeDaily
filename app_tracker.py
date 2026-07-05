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
OpenProcess = kernel32.OpenProcess
CloseHandle = kernel32.CloseHandle
QueryFullProcessImageNameW = kernel32.QueryFullProcessImageNameW

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _get_process_name(hwnd: int) -> str:
    """通过窗口句柄获取所属进程的可执行文件名"""
    pid = wintypes.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    h_process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not h_process:
        return "Unknown"

    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(260)
        if QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size)):
            full_path = buf.value
            # 只取文件名部分
            return full_path.split("\\")[-1]
        return "Unknown"
    finally:
        CloseHandle(h_process)


def get_foreground_app() -> dict:
    """
    获取当前前台应用信息。
    返回 {"app_name": "chrome.exe", "window_title": "GitHub - Google Chrome"}
    """
    hwnd = GetForegroundWindow()
    if not hwnd:
        return {"app_name": "Unknown", "window_title": ""}

    # 获取窗口标题
    length = GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    GetWindowTextW(hwnd, buf, length + 1)
    window_title = buf.value

    # 获取进程名
    app_name = _get_process_name(hwnd)

    return {
        "app_name": app_name,
        "window_title": window_title,
    }


# ── 应用名称映射表（可扩展）──
APP_NAME_MAP = {
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox",
    "Code.exe": "VS Code",
    "devenv.exe": "Visual Studio",
    "idea64.exe": "IntelliJ IDEA",
    "pycharm64.exe": "PyCharm",
    "WINWORD.EXE": "Word",
    "EXCEL.EXE": "Excel",
    "POWERPNT.EXE": "PowerPoint",
    "OUTLOOK.EXE": "Outlook",
    "Teams.exe": "Microsoft Teams",
    "WeChat.exe": "微信",
    "DingTalk.exe": "钉钉",
    "Feishu.exe": "飞书",
    "Telegram.exe": "Telegram",
    "Discord.exe": "Discord",
    "WindowsTerminal.exe": "终端",
    "cmd.exe": "命令提示符",
    "PowerShell.exe": "PowerShell",
    "explorer.exe": "文件资源管理器",
    "Navicat.exe": "Navicat",
    "DataGrip64.exe": "DataGrip",
    "postman.exe": "Postman",
}


def get_display_name(app_name: str) -> str:
    """将进程名转为友好显示名"""
    return APP_NAME_MAP.get(app_name, app_name.replace(".exe", ""))


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
