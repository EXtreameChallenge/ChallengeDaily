"""
P211-P219: 多端跨平台支持
- P211: 平台检测器
- P212: 响应式布局
- P213: 触摸手势
- P214: 键盘快捷键
- P215: 剪贴板同步
- P216: 文件拖放
- P217: 系统通知
- P218: 深色模式同步
- P219: 设备能力检测
"""
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P211: 平台检测器 ──────────────────────────
class PlatformDetector:
    """平台/设备检测"""
    @staticmethod
    def detect(user_agent: str = "") -> dict:
        ua = user_agent.lower()
        if "windows" in ua:
            os = "windows"
        elif "mac" in ua or "darwin" in ua:
            os = "macos"
        elif "linux" in ua:
            os = "linux"
        elif "android" in ua:
            os = "android"
        elif "iphone" in ua or "ipad" in ua:
            os = "ios"
        else:
            os = "unknown"
        if "mobile" in ua:
            device = "mobile"
        elif "tablet" in ua or "ipad" in ua:
            device = "tablet"
        else:
            device = "desktop"
        if "electron" in ua:
            runtime = "electron"
        elif "chrome" in ua:
            runtime = "chrome"
        elif "firefox" in ua:
            runtime = "firefox"
        elif "safari" in ua:
            runtime = "safari"
        else:
            runtime = "unknown"
        return {"os": os, "device": device, "runtime": runtime, "ua": user_agent}

    @staticmethod
    def get_capabilities(platform: dict) -> dict:
        return {
            "touch": platform.get("device") in ("mobile", "tablet"),
            "offline": platform.get("runtime") == "electron",
            "notifications": True,
            "clipboard": True,
            "filesystem": platform.get("runtime") == "electron",
            "system_tray": platform.get("os") in ("windows", "macos", "linux"),
        }


_platform = PlatformDetector()


# ─── P212: 响应式布局 ──────────────────────────
class ResponsiveLayout:
    """响应式布局配置"""
    BREAKPOINTS = {
        "xs": 0, "sm": 640, "md": 768,
        "lg": 1024, "xl": 1280, "2xl": 1536
    }

    def __init__(self):
        self._layouts: dict[str, dict] = {}

    def configure(self, layout_id: str, breakpoints: dict = None) -> None:
        self._layouts[layout_id] = {
            "breakpoints": breakpoints or self.BREAKPOINTS,
            "columns": {"xs": 1, "sm": 2, "md": 4, "lg": 6, "xl": 8, "2xl": 12},
            "gutter": {"xs": 8, "sm": 12, "md": 16, "lg": 24, "xl": 32, "2xl": 40},
        }

    def get_layout(self, layout_id: str, width: int) -> dict:
        layout = self._layouts.get(layout_id)
        if not layout:
            return {"columns": 1, "gutter": 8, "breakpoint": "xs"}
        bp = "xs"
        for name, min_width in sorted(layout["breakpoints"].items(), key=lambda x: x[1]):
            if width >= min_width:
                bp = name
        return {
            "breakpoint": bp,
            "columns": layout["columns"].get(bp, 1),
            "gutter": layout["gutter"].get(bp, 8),
        }

    def list_breakpoints(self) -> dict:
        return self.BREAKPOINTS


_responsive = ResponsiveLayout()


# ─── P213: 触摸手势 ──────────────────────────
class TouchGesture:
    """触摸手势识别"""
    GESTURES = ["tap", "double_tap", "long_press", "swipe_left", "swipe_right",
                "swipe_up", "swipe_down", "pinch", "zoom"]

    def __init__(self):
        self._handlers: dict[str, Callable] = {}

    def register(self, gesture: str, handler: Callable) -> None:
        if gesture in self.GESTURES:
            self._handlers[gesture] = handler

    def recognize(self, events: list[dict]) -> list[str]:
        recognized = []
        if not events:
            return recognized
        first = events[0]
        last = events[-1]
        duration = last.get("t", 0) - first.get("t", 0)
        dx = last.get("x", 0) - first.get("x", 0)
        dy = last.get("y", 0) - first.get("y", 0)
        dist = (dx ** 2 + dy ** 2) ** 0.5

        if dist < 10 and duration < 200:
            recognized.append("tap")
        elif dist < 10 and duration > 500:
            recognized.append("long_press")
        elif abs(dx) > 50 and abs(dx) > abs(dy):
            recognized.append("swipe_left" if dx < 0 else "swipe_right")
        elif abs(dy) > 50 and abs(dy) > abs(dx):
            recognized.append("swipe_up" if dy < 0 else "swipe_down")
        return recognized

    def fire(self, gesture: str, data: dict = None) -> Any:
        handler = self._handlers.get(gesture)
        if handler:
            return handler(data or {})
        return None


_touch = TouchGesture()


# ─── P214: 键盘快捷键 ──────────────────────────
class KeyboardShortcut:
    """键盘快捷键管理"""
    def __init__(self):
        self._shortcuts: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register(self, key_combo: str, action: Callable,
                 description: str = "", scope: str = "global") -> None:
        with self._lock:
            self._shortcuts[key_combo] = {
                "action": action, "description": description,
                "scope": scope, "triggered": 0
            }

    def unregister(self, key_combo: str) -> bool:
        with self._lock:
            return self._shortcuts.pop(key_combo, None) is not None

    def trigger(self, key_combo: str) -> dict:
        with self._lock:
            shortcut = self._shortcuts.get(key_combo)
        if not shortcut:
            return {"status": "not_found"}
        try:
            result = shortcut["action"]()
            with self._lock:
                shortcut["triggered"] += 1
            return {"status": "ok", "result": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def list_shortcuts(self) -> list[dict]:
        with self._lock:
            return [{"combo": k, "description": v["description"],
                     "scope": v["scope"], "triggered": v["triggered"]}
                    for k, v in self._shortcuts.items()]


_keyboard = KeyboardShortcut()


# ─── P215: 剪贴板同步 ──────────────────────────
class ClipboardSync:
    """剪贴板历史与同步"""
    def __init__(self):
        self._history: deque = deque(maxlen=100)
        self._lock = threading.Lock()

    def push(self, content: str, content_type: str = "text") -> None:
        with self._lock:
            self._history.append({
                "content": content[:1000],  # 限制大小
                "type": content_type,
                "timestamp": datetime.now().isoformat(),
                "size": len(content)
            })

    def get_recent(self, limit: int = 10) -> list[dict]:
        with self._lock:
            items = list(self._history)
        items.reverse()
        return items[:limit]

    def clear(self) -> None:
        with self._lock:
            self._history.clear()

    def search(self, query: str) -> list[dict]:
        with self._lock:
            return [item for item in self._history
                    if query.lower() in item["content"].lower()]


_clipboard = ClipboardSync()


# ─── P216: 文件拖放 ──────────────────────────
class FileDropHandler:
    """文件拖放处理"""
    def __init__(self):
        self._handlers: dict[str, Callable] = {}
        self._drop_history: deque = deque(maxlen=100)

    def register_handler(self, file_type: str, handler: Callable) -> None:
        self._handlers[file_type] = handler

    def handle_drop(self, files: list[dict]) -> list[dict]:
        results = []
        for f in files:
            ext = f.get("name", "").rsplit(".", 1)[-1].lower() if "." in f.get("name", "") else ""
            handler = self._handlers.get(ext) or self._handlers.get("*")
            if handler:
                try:
                    result = handler(f)
                    results.append({"file": f["name"], "status": "ok", "result": result})
                except Exception as e:
                    results.append({"file": f["name"], "status": "error", "error": str(e)})
            else:
                results.append({"file": f.get("name", ""), "status": "no_handler"})
            self._drop_history.append({
                "file": f.get("name", ""), "size": f.get("size", 0),
                "timestamp": datetime.now().isoformat()
            })
        return results

    def get_history(self, limit: int = 20) -> list[dict]:
        items = list(self._drop_history)
        items.reverse()
        return items[:limit]


_file_drop = FileDropHandler()


# ─── P217: 系统通知 ──────────────────────────
class SystemNotifier:
    """系统通知管理"""
    def __init__(self):
        self._notifications: deque = deque(maxlen=500)
        self._lock = threading.Lock()

    def notify(self, title: str, body: str = "",
               priority: str = "normal", category: str = "default") -> dict:
        notif = {
            "id": len(self._notifications) + 1,
            "title": title, "body": body,
            "priority": priority, "category": category,
            "timestamp": datetime.now().isoformat(),
            "read": False
        }
        with self._lock:
            self._notifications.append(notif)
        return notif

    def mark_read(self, notif_id: int) -> None:
        with self._lock:
            for n in self._notifications:
                if n["id"] == notif_id:
                    n["read"] = True
                    break

    def get_unread(self) -> list[dict]:
        with self._lock:
            return [n for n in self._notifications if not n["read"]]

    def get_all(self, limit: int = 50) -> list[dict]:
        with self._lock:
            items = list(self._notifications)
        items.reverse()
        return items[:limit]

    def clear_all(self) -> None:
        with self._lock:
            self._notifications.clear()


_notifier = SystemNotifier()


# ─── P218: 深色模式同步 ──────────────────────────
class ThemeSync:
    """主题与系统深色模式同步"""
    def __init__(self):
        self._theme: str = "light"
        self._listeners: list[Callable] = []
        self._auto_sync: bool = True

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        for listener in self._listeners:
            try:
                listener(theme)
            except Exception:
                pass

    def get_theme(self) -> str:
        return self._theme

    def on_change(self, listener: Callable) -> None:
        self._listeners.append(listener)

    def sync_with_system(self, system_prefers_dark: bool) -> None:
        if self._auto_sync:
            self.set_theme("dark" if system_prefers_dark else "light")

    def set_auto_sync(self, enabled: bool) -> None:
        self._auto_sync = enabled


_theme_sync = ThemeSync()


# ─── P219: 设备能力检测 ──────────────────────────
class DeviceCapability:
    """设备能力检测与注册"""
    def __init__(self):
        self._capabilities: dict[str, bool] = {
            "webgl": True, "websocket": True, "webrtc": True,
            "service_worker": True, "web_worker": True,
            "indexed_db": True, "local_storage": True,
            "canvas": True, "svg": True, "audio": True,
            "video": True, "geolocation": False, "bluetooth": False,
        }

    def check(self, capability: str) -> bool:
        return self._capabilities.get(capability, False)

    def set(self, capability: str, available: bool) -> None:
        self._capabilities[capability] = available

    def get_all(self) -> dict:
        return dict(self._capabilities)

    def get_available(self) -> list[str]:
        return [k for k, v in self._capabilities.items() if v]


_device_cap = DeviceCapability()
