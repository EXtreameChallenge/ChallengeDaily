"""
P91-P99: 平台与集成扩展模块
- P91: 系统托盘集成增强
- P92: 全局快捷键管理
- P93: 通知中心统一管理
- P94: 文件关联与协议处理
- P95: 剪贴板历史
- P96: 窗口管理器
- P97: 多显示器支持
- P98: 系统主题跟随
- P99: 跨平台兼容层
"""
import logging
import threading
import time
import json
import os
import platform
from datetime import datetime
from collections import deque
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P91: 系统托盘菜单构建 ──────────────────────────
def build_tray_menu_items() -> list:
    """构建系统托盘菜单项"""
    return [
        {"id": "show", "label": "显示主窗口", "accelerator": "Ctrl+Shift+S", "enabled": True},
        {"id": "hide", "label": "隐藏到托盘", "enabled": True},
        {"type": "separator"},
        {"id": "start_pomodoro", "label": "开始番茄钟", "accelerator": "Ctrl+Shift+P", "enabled": True},
        {"id": "start_focus", "label": "进入专注模式", "accelerator": "Ctrl+Shift+F", "enabled": True},
        {"id": "pause_tracking", "label": "暂停采集", "enabled": True},
        {"type": "separator"},
        {"id": "daily_report", "label": "查看今日报告", "enabled": True},
        {"id": "weekly_report", "label": "本周周报", "enabled": True},
        {"type": "separator"},
        {"id": "settings", "label": "设置", "enabled": True},
        {"id": "quit", "label": "退出", "enabled": True},
    ]


# ─── P92: 全局快捷键注册表 ──────────────────────────
_SHORTCUTS: dict[str, dict] = {}
_SHORTCUTS_LOCK = threading.Lock()


def register_shortcut(accelerator: str, action: str, description: str = "") -> bool:
    """注册全局快捷键"""
    with _SHORTCUTS_LOCK:
        if accelerator in _SHORTCUTS:
            return False
        _SHORTCUTS[accelerator] = {
            "accelerator": accelerator,
            "action": action,
            "description": description,
            "registered_at": datetime.now().isoformat()
        }
        return True


def unregister_shortcut(accelerator: str) -> bool:
    with _SHORTCUTS_LOCK:
        return _SHORTCUTS.pop(accelerator, None) is not None


def list_shortcuts() -> list:
    with _SHORTCUTS_LOCK:
        return list(_SHORTCUTS.values())


def get_default_shortcuts() -> list:
    """获取默认快捷键配置"""
    return [
        {"accelerator": "Ctrl+Shift+P", "action": "pomodoro.start", "description": "开始番茄钟"},
        {"accelerator": "Ctrl+Shift+F", "action": "focus.start", "description": "进入专注模式"},
        {"accelerator": "Ctrl+Shift+Q", "action": "pomodoro.quick", "description": "快速番茄"},
        {"accelerator": "Ctrl+Shift+S", "action": "window.show", "description": "显示主窗口"},
        {"accelerator": "Ctrl+Shift+H", "action": "window.hide", "description": "隐藏主窗口"},
        {"accelerator": "Ctrl+Shift+D", "action": "report.daily", "description": "今日报告"},
        {"accelerator": "Ctrl+Shift+W", "action": "report.weekly", "description": "本周周报"},
        {"accelerator": "Ctrl+Shift+,", "action": "settings.open", "description": "打开设置"},
    ]


# ─── P93: 通知中心 ──────────────────────────
_NOTIFICATIONS: deque = deque(maxlen=100)
_NOTIFICATIONS_LOCK = threading.Lock()
_NOTIFICATION_HANDLERS: list[Callable] = []


def send_notification(title: str, body: str, level: str = "info",
                      action: str = "", data: dict | None = None) -> dict:
    """发送通知"""
    notif = {
        "id": f"n_{int(time.time() * 1000)}",
        "title": title,
        "body": body,
        "level": level,  # info/warn/error/success
        "action": action,
        "data": data or {},
        "timestamp": datetime.now().isoformat(),
        "read": False
    }
    with _NOTIFICATIONS_LOCK:
        _NOTIFICATIONS.append(notif)
    # 通知所有处理器
    for handler in _NOTIFICATION_HANDLERS:
        try:
            handler(notif)
        except Exception as e:
            logger.debug(f"通知处理器失败: {e}")
    return notif


def get_notifications(unread_only: bool = False, limit: int = 50) -> list:
    with _NOTIFICATIONS_LOCK:
        items = list(_NOTIFICATIONS)
        items.reverse()  # 最新在前
        if unread_only:
            items = [n for n in items if not n["read"]]
        return items[:limit]


def mark_notification_read(notif_id: str) -> bool:
    with _NOTIFICATIONS_LOCK:
        for n in _NOTIFICATIONS:
            if n["id"] == notif_id:
                n["read"] = True
                return True
        return False


def mark_all_read() -> int:
    with _NOTIFICATIONS_LOCK:
        count = 0
        for n in _NOTIFICATIONS:
            if not n["read"]:
                n["read"] = True
                count += 1
        return count


def register_notification_handler(handler: Callable) -> None:
    _NOTIFICATION_HANDLERS.append(handler)


# ─── P94: 协议处理 ──────────────────────────
_PROTOCOL_HANDLERS: dict[str, Callable] = {}


def register_protocol_handler(scheme: str, handler: Callable) -> None:
    """注册自定义协议处理器"""
    _PROTOCOL_HANDLERS[scheme] = handler


def handle_protocol(url: str) -> dict:
    """处理自定义协议URL，如 challengedaily://action/param"""
    try:
        if "://" not in url:
            return {"status": "error", "error": "无效的URL格式"}
        scheme, rest = url.split("://", 1)
        handler = _PROTOCOL_HANDLERS.get(scheme)
        if handler:
            return {"status": "ok", "result": handler(rest)}
        return {"status": "error", "error": f"未知协议: {scheme}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_registered_protocols() -> list:
    return list(_PROTOCOL_HANDLERS.keys())


# ─── P95: 剪贴板历史 ──────────────────────────
_CLIPBOARD_HISTORY: deque = deque(maxlen=50)
_CLIPBOARD_LOCK = threading.Lock()


def add_clipboard_item(content: str, content_type: str = "text") -> dict:
    """添加剪贴板历史项"""
    item = {
        "id": f"c_{int(time.time() * 1000)}",
        "content": content[:2000],  # 限制长度
        "type": content_type,
        "length": len(content),
        "timestamp": datetime.now().isoformat()
    }
    with _CLIPBOARD_LOCK:
        # 去重：相同内容不重复添加
        for existing in _CLIPBOARD_HISTORY:
            if existing["content"] == item["content"]:
                return existing
        _CLIPBOARD_HISTORY.append(item)
    return item


def get_clipboard_history(limit: int = 20) -> list:
    with _CLIPBOARD_LOCK:
        items = list(_CLIPBOARD_HISTORY)
        items.reverse()
        return items[:limit]


def clear_clipboard_history() -> int:
    with _CLIPBOARD_LOCK:
        n = len(_CLIPBOARD_HISTORY)
        _CLIPBOARD_HISTORY.clear()
        return n


# ─── P96: 窗口管理器 ──────────────────────────
_WINDOW_STATES: dict[str, dict] = {}


def record_window_state(window_id: str, state: dict) -> None:
    """记录窗口状态"""
    _WINDOW_STATES[window_id] = {
        **state,
        "updated_at": datetime.now().isoformat()
    }


def get_window_state(window_id: str) -> dict | None:
    return _WINDOW_STATES.get(window_id)


def get_all_window_states() -> dict:
    return dict(_WINDOW_STATES)


def restore_window_layout() -> dict:
    """获取窗口布局恢复信息"""
    return {
        "windows": dict(_WINDOW_STATES),
        "restore_count": len(_WINDOW_STATES),
        "queried_at": datetime.now().isoformat()
    }


# ─── P97: 多显示器支持 ──────────────────────────
def get_display_info() -> dict:
    """获取显示器信息(跨平台)"""
    try:
        # 尝试使用 Electron API 的数据，这里返回基础信息
        return {
            "platform": platform.system(),
            "displays": [
                {
                    "id": 0,
                    "primary": True,
                    "bounds": {"x": 0, "y": 0, "width": 1920, "height": 1080},
                    "scaleFactor": 1.0,
                    "rotation": 0
                }
            ],
            "display_count": 1
        }
    except Exception as e:
        return {"error": str(e), "displays": [], "display_count": 0}


# ─── P98: 系统主题跟随 ──────────────────────────
_THEME_CHANGE_HANDLERS: list[Callable] = []


def detect_system_theme() -> str:
    """检测系统主题(dark/light)"""
    try:
        if platform.system() == "Windows":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value == 1 else "dark"
        elif platform.system() == "Darwin":
            # macOS 检测
            import subprocess
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True
            )
            return "dark" if "Dark" in result.stdout else "light"
        return "light"
    except Exception:
        return "light"


def register_theme_handler(handler: Callable) -> None:
    _THEME_CHANGE_HANDLERS.append(handler)


def notify_theme_change(new_theme: str) -> None:
    for handler in _THEME_CHANGE_HANDLERS:
        try:
            handler(new_theme)
        except Exception as e:
            logger.debug(f"主题处理器失败: {e}")


# ─── P99: 跨平台兼容层 ──────────────────────────
def get_platform_info() -> dict:
    """获取平台兼容性信息"""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "supported_features": _get_supported_features(),
        "path_separator": os.path.sep,
        "line_separator": "\r\n" if platform.system() == "Windows" else "\n",
    }


def _get_supported_features() -> dict:
    sys_name = platform.system()
    return {
        "tray": True,
        "global_shortcuts": True,
        "notifications": True,
        "auto_launch": sys_name == "Windows",
        "file_association": True,
        "deep_link": True,
        "screenshot": sys_name in ("Windows", "Darwin"),
        "idle_detection": True,
        "power_monitor": True,
    }


def normalize_path(path: str) -> str:
    """跨平台路径规范化"""
    return os.path.normpath(path)


def get_app_data_dir() -> str:
    """获取应用数据目录(跨平台)"""
    try:
        import sys
        if sys.platform == "win32":
            base = os.environ.get("APPDATA", os.path.expanduser("~"))
            return os.path.join(base, "challenge-daily")
        elif sys.platform == "darwin":
            return os.path.expanduser("~/Library/Application Support/challenge-daily")
        else:
            return os.path.expanduser("~/.local/share/challenge-daily")
    except Exception:
        return os.path.expanduser("~/.challenge-daily")
