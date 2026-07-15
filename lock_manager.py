"""
番茄钟学霸硬锁机模块 — 三档严格度
L1 软提醒（弹窗）  L2 硬拦截（关闭分心应用进程）  L3 锁屏（全屏蒙层）

通过 Win32 API 检测前台应用，命中黑名单则：
- L2: TerminateProcess 关闭分心进程
- L3: 置顶番茄窗口 + 全屏蒙层遮挡

白名单：VSCode/Word/飞书等工作应用放行
"""
import logging
import ctypes
import ctypes.wintypes
import subprocess
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 分心应用黑名单（进程名小写）
DISTRACTION_BLACKLIST = {
    # 社交娱乐
    "wechat.exe", "qq.exe", "douyin.exe", "kuaishou.exe",
    "bilibili.exe", "weibo.exe", "zhihu.exe", "xiaohongshu.exe",
    # 游戏
    "steam.exe", "epicgameslauncher.exe", "wegame.exe", "lol.exe",
    # 视频
    "iqiyi.exe", "youku.exe", "tencentmeeting.exe",
    # 浏览器（可选，默认放行）
    # "chrome.exe", "msedge.exe", "firefox.exe",
}

# 工作应用白名单（永远放行）
WORK_WHITELIST = {
    "code.exe", "cursor.exe", "trae.exe", "trae solo cn.exe",
    "idea64.exe", "pycharm64.exe", "webstorm64.exe",
    "winword.exe", "excel.exe", "powerpnt.exe", "outlook.exe",
    "feishu.exe", "dingtalk.exe", "wxwork.exe",
    "notepad.exe", "notepad++.exe", "sublime_text.exe",
    "terminal.exe", "powershell.exe", "cmd.exe",
    "windowsterminal.exe", "wt.exe",
}

# Win32 API 定义
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_TERMINATE = 0x0001


def get_foreground_window_info() -> dict:
    """获取前台窗口信息：进程名 + 窗口标题"""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return {"app_name": "", "window_title": ""}

        # 窗口标题
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value

        # 进程名
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = pid.value

        proc_name = ""
        try:
            import psutil
            proc = psutil.Process(pid_val)
            proc_name = proc.name().lower()
        except Exception:
            pass

        return {"app_name": proc_name, "window_title": title, "pid": pid_val}
    except Exception as e:
        logger.error(f"获取前台窗口失败: {e}")
        return {"app_name": "", "window_title": ""}


def is_distraction(app_name: str, custom_blacklist: Optional[set] = None) -> bool:
    """判断是否为分心应用"""
    if not app_name:
        return False
    if app_name in WORK_WHITELIST:
        return False
    blacklist = DISTRACTION_BLACKLIST | (custom_blacklist or set())
    return app_name.lower() in blacklist


def terminate_process(pid: int) -> bool:
    """关闭指定进程（L2 硬拦截）"""
    try:
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if not handle:
            return False
        result = kernel32.TerminateProcess(handle, 1)
        kernel32.CloseHandle(handle)
        if result:
            logger.info(f"硬锁机已关闭分心进程 PID={pid}")
        return bool(result)
    except Exception as e:
        logger.error(f"关闭进程失败 PID={pid}: {e}")
        return False


def bring_window_to_front(window_title_keyword: str = "ChallengeDaily") -> bool:
    """置顶指定窗口（L3 锁屏前置）"""
    try:
        result = []
        def enum_proc(hwnd, _):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if window_title_keyword.lower() in buf.value.lower():
                    result.append(hwnd)
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        user32.EnumWindows(EnumWindowsProc(enum_proc), 0)

        if result:
            hwnd = result[0]
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
            return True
    except Exception as e:
        logger.error(f"置顶窗口失败: {e}")
    return False


class LockManager:
    """番茄硬锁机管理器"""

    def __init__(self):
        self.active_level = 0  # 0=未启用 1=L1软提醒 2=L2硬拦截 3=L3锁屏
        self.session_id = None
        self.custom_blacklist: set = set()
        self.distraction_log: list = []

    def activate(self, level: int, session_id: int = None, custom_blacklist: Optional[set] = None):
        """激活锁机"""
        self.active_level = level
        self.session_id = session_id
        self.custom_blacklist = custom_blacklist or set()
        self.distraction_log = []
        logger.info(f"硬锁机激活 L{level}, session={session_id}")

    def deactivate(self):
        """关闭锁机"""
        logger.info(f"硬锁机关闭, 共拦截 {len(self.distraction_log)} 次分心")
        self.active_level = 0
        self.session_id = None
        self.distraction_log = []

    def check_and_enforce(self) -> dict:
        """检测并执行拦截（番茄运行中由前端定时调用）

        返回:
            {
                "is_distraction": bool,
                "app_name": str,
                "action": "warn" | "killed" | "locked",
                "distraction_count": int,
            }
        """
        if self.active_level == 0:
            return {"is_distraction": False, "app_name": "", "action": "none", "distraction_count": 0}

        info = get_foreground_window_info()
        app_name = info.get("app_name", "")

        if not is_distraction(app_name, self.custom_blacklist):
            return {"is_distraction": False, "app_name": app_name, "action": "none", "distraction_count": len(self.distraction_log)}

        # 命中分心应用
        self.distraction_log.append({
            "app": app_name,
            "title": info.get("window_title", "")[:100],
            "time": time.strftime("%H:%M:%S"),
        })

        action = "warn"
        if self.active_level >= 2:
            # L2: 关闭进程
            pid = info.get("pid")
            if pid:
                terminate_process(pid)
                action = "killed"
        if self.active_level >= 3:
            # L3: 置顶番茄窗口（前端会渲染全屏蒙层）
            bring_window_to_front("ChallengeDaily")
            action = "locked"

        logger.warning(f"分心拦截 L{self.active_level}: {app_name} → {action}")
        return {
            "is_distraction": True,
            "app_name": app_name,
            "action": action,
            "distraction_count": len(self.distraction_log),
        }


# 全局单例
lock_manager = LockManager()
