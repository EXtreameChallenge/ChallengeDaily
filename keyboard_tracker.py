"""
ChallengeDaily — 键盘热力图采集模块
使用 keyboard 库全局监听按键，统计每个按键的按压次数
数据存储在 SQLite，前端渲染热力图
"""
import threading
import time
import logging
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)

# 按键映射表（键盘字符 -> 标准键位名）
_KEY_MAP = {
    'enter': 'Enter', 'tab': 'Tab', 'backspace': 'Backspace',
    'shift': 'Shift', 'ctrl': 'Ctrl', 'alt': 'Alt', 'caps lock': 'CapsLock',
    'escape': 'Esc', 'space': 'Space', 'delete': 'Delete',
    'up': 'ArrowUp', 'down': 'ArrowDown', 'left': 'ArrowLeft', 'right': 'ArrowRight',
    'page up': 'PageUp', 'page down': 'PageDown', 'home': 'Home', 'end': 'End',
    'f1': 'F1', 'f2': 'F2', 'f3': 'F3', 'f4': 'F4', 'f5': 'F5', 'f6': 'F6',
    'f7': 'F7', 'f8': 'F8', 'f9': 'F9', 'f10': 'F10', 'f11': 'F11', 'f12': 'F12',
}

# 内存中的按键统计（按日期聚合）
_key_stats: dict[str, int] = defaultdict(int)
_stats_lock = threading.Lock()
_listening = False
_listener_thread = None


def _normalize_key(key_name: str) -> str:
    """将 keyboard 库的按键名标准化为短名"""
    key_lower = key_name.lower().strip()
    if key_lower in _KEY_MAP:
        return _KEY_MAP[key_lower]
    # 单字符直接返回大写
    if len(key_name) == 1:
        return key_name.upper()
    return key_name


def _on_key_event(event):
    """按键事件回调"""
    try:
        key_name = event.name
        if not key_name:
            return
        normalized = _normalize_key(key_name)
        with _stats_lock:
            _key_stats[normalized] += 1
    except Exception as e:
        logger.debug(f"按键事件处理失败: {e}")


def start_listening():
    """启动全局按键监听"""
    global _listening, _listener_thread
    if _listening:
        return
    try:
        import keyboard
        keyboard.hook(_on_key_event)
        _listening = True
        logger.info("键盘热力图监听已启动")
    except Exception as e:
        logger.warning(f"键盘监听启动失败(需要管理员权限): {e}")


def stop_listening():
    """停止监听"""
    global _listening
    if not _listening:
        return
    try:
        import keyboard
        keyboard.unhook_all()
        _listening = False
        logger.info("键盘热力图监听已停止")
    except Exception as e:
        logger.debug(f"停止监听失败: {e}")


def get_stats() -> dict[str, int]:
    """获取当前按键统计"""
    with _stats_lock:
        return dict(_key_stats)


def get_hotkeys(limit: int = 20) -> list[dict]:
    """获取最热门的按键"""
    with _stats_lock:
        sorted_keys = sorted(_key_stats.items(), key=lambda x: x[1], reverse=True)
    return [{"key": k, "count": v} for k, v in sorted_keys[:limit]]


def reset_stats():
    """重置统计"""
    global _key_stats
    with _stats_lock:
        _key_stats.clear()
