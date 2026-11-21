"""
P20-2: 窗口切换事件驱动采样
通过 SetWinEventHook 监听 EVENT_SYSTEM_FOREGROUND 事件，
窗口切换时立即触发回调（节流到 5s 内仅一次），实现"事件驱动采样"。

设计要点：
1. SetWinEventHook 必须在拥有消息循环的线程中调用，否则回调不会触发。
   由于 collector 主循环已在自己的线程中运行，本模块提供 start() / stop() 接口，
   由 collector 在主循环线程内调用以注册 hook，并通过 PeekMessageW 抽取消息触发回调。
2. 节流：5 秒内仅触发一次回调，避免快速切窗口导致采样风暴。
3. 线程安全：hook 注册/反注册通过 threading.Lock 保护。
"""
import ctypes
from ctypes import wintypes
import threading
import time
import logging

logger = logging.getLogger(__name__)

# Win32 常量
EVENT_SYSTEM_FOREGROUND = 0x0003  # 前台窗口改变
WINEVENT_OUTOFCONTEXT = 0x0000   # 不注入目标进程，回调在调用方线程触发
WINEVENT_SKIPOWNPROCESS = 0x0002  # 跳过本进程事件

# 节流间隔（秒）：5 秒内最多触发一次
_THROTTLE_SEC = 5.0

# Win32 API 声明
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# SetWinEventHook 签名
WinEventProcType = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE,   # hWinEventHook
    wintypes.DWORD,    # event
    wintypes.HWND,     # hwnd
    wintypes.LONG,     # idObject
    wintypes.LONG,     # idChild
    wintypes.DWORD,    # dwEventThread
    wintypes.DWORD,    # dwmsEventTime
)

user32.SetWinEventHook.argtypes = [
    wintypes.UINT, wintypes.UINT,   # eventMin, eventMax
    wintypes.HMODULE,                # hmodWinEventProc
    WinEventProcType,                # pfnWinEventProc
    wintypes.DWORD, wintypes.DWORD,  # idProcess, idThread
    wintypes.UINT,                   # dwFlags
]
user32.SetWinEventHook.restype = wintypes.HANDLE

user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
user32.UnhookWinEvent.restype = wintypes.BOOL

# PeekMessageW 用于在当前线程消息队列中抽取事件消息（触发回调）
user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG),  # lpMsg
    wintypes.HWND,                  # hWnd
    wintypes.UINT, wintypes.UINT,   # wMsgFilterMin, wMsgFilterMax
    wintypes.UINT,                  # wRemoveMsg
]
user32.PeekMessageW.restype = wintypes.BOOL

PM_REMOVE = 0x0001


class WinEventHook:
    """窗口切换事件钩子（线程相关，必须在目标线程内 start/stop）"""

    def __init__(self, on_switch_callback):
        self._callback = on_switch_callback
        self._hook_handle = None
        self._lock = threading.Lock()
        self._last_trigger_ts = 0.0
        # 必须保持对回调函数的强引用，否则 GC 后 ctypes 回调会崩溃
        self._proc_ref = None

    def _event_callback(self, hWinEventHook, event, hwnd, idObject, idChild, dwEventThread, dwmsEventTime):
        """SetWinEventHook 的回调函数（节流后触发用户回调）"""
        try:
            now = time.time()
            if now - self._last_trigger_ts < _THROTTLE_SEC:
                return
            self._last_trigger_ts = now
            # 异步触发用户回调（不阻塞 Win32 消息循环）
            try:
                self._callback()
            except Exception as e:
                logger.warning(f"WinEvent 用户回调异常: {e}")
        except Exception as e:
            logger.warning(f"WinEvent 回调处理异常: {e}")

    def start(self) -> bool:
        """注册钩子（必须在目标线程内调用）。返回是否成功。"""
        with self._lock:
            if self._hook_handle:
                return True  # 已注册
            # 创建 ctypes 回调函数引用（防止 GC）
            self._proc_ref = WinEventProcType(self._event_callback)
            try:
                handle = user32.SetWinEventHook(
                    EVENT_SYSTEM_FOREGROUND,
                    EVENT_SYSTEM_FOREGROUND,
                    None,
                    self._proc_ref,
                    0,  # 所有进程
                    0,  # 所有线程
                    WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
                )
                if not handle:
                    logger.warning("SetWinEventHook 返回 NULL，窗口切换事件驱动采样未启用")
                    return False
                self._hook_handle = handle
                logger.info("窗口切换事件钩子已注册（事件驱动采样启用）")
                return True
            except Exception as e:
                logger.warning(f"SetWinEventHook 失败: {e}")
                self._proc_ref = None
                return False

    def stop(self):
        """反注册钩子（必须在注册的同一个线程内调用）"""
        with self._lock:
            if self._hook_handle:
                try:
                    user32.UnhookWinEvent(self._hook_handle)
                    logger.info("窗口切换事件钩子已反注册")
                except Exception as e:
                    logger.warning(f"UnhookWinEvent 失败: {e}")
                self._hook_handle = None
                self._proc_ref = None

    def pump_messages(self, max_iterations: int = 10):
        """
        在当前线程消息队列中抽取事件消息（触发已注册的回调）。
        应在 collector 主循环的每个周期内调用，让 Win32 有机会投递事件回调。
        max_iterations: 单次最多处理的消息数，避免长时间阻塞。
        """
        if not self._hook_handle:
            return
        msg = wintypes.MSG()
        for _ in range(max_iterations):
            # PM_REMOVE: 取出并移除消息；不阻塞
            if not user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                break
            # WinEvent 回调由 SetWinEventHook 内部机制在 PeekMessage 时触发，
            # 无需手动 TranslateMessage/DispatchMessage


# 模块级单例（懒加载）
_global_hook: WinEventHook | None = None
_global_lock = threading.Lock()


def install(on_switch_callback) -> WinEventHook | None:
    """
    安装全局窗口切换钩子（必须在 collector 主循环线程内调用）。
    on_switch_callback: 窗口切换时触发的无参回调（已节流）。
    返回 WinEventHook 实例，失败返回 None。
    """
    global _global_hook
    with _global_lock:
        if _global_hook is not None:
            return _global_hook
        hook = WinEventHook(on_switch_callback)
        if hook.start():
            _global_hook = hook
            return hook
        return None


def uninstall():
    """卸载全局钩子"""
    global _global_hook
    with _global_lock:
        if _global_hook is not None:
            _global_hook.stop()
            _global_hook = None


def pump():
    """抽取消息触发回调（collector 主循环每周期调用一次）"""
    global _global_hook
    if _global_hook is not None:
        _global_hook.pump_messages()
