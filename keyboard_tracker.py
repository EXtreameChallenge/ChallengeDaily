"""
ChallengeDaily — 键盘热力图采集模块
使用 keyboard 库全局监听按键，统计每个按键的按压次数
数据按日持久化到 SQLite（keyboard_stats_daily），前端渲染热力图
"""
import threading
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

_key_stats: dict[str, int] = defaultdict(int)
_persisted: dict[str, int] = {}       # 已落库的计数快照（用于算增量）
_stats_lock = threading.Lock()
_listening = False
_flush_stop = threading.Event()
_flush_thread: threading.Thread | None = None
_FLUSH_INTERVAL_SEC = 60


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _normalize_key(key_name: str) -> str:
    key_lower = key_name.lower().strip()
    if key_lower in _KEY_MAP:
        return _KEY_MAP[key_lower]
    if len(key_name) == 1:
        return key_name.upper()
    return key_name


def _on_key_event(event):
    try:
        key_name = event.name
        if not key_name:
            return
        # keyboard.hook 同时抛 down/up 事件，只统计按下，避免一次按键记两次
        if getattr(event, "event_type", "down") != "down":
            return
        normalized = _normalize_key(key_name)
        with _stats_lock:
            _key_stats[normalized] += 1
        try:  # B12：真实机械音效（可用时）
            from mechanical_sound import play_keypress_sound
            play_keypress_sound()
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"按键事件处理失败: {e}")


def check_availability() -> dict:
    """检查全局键盘监听是否可用（keyboard 库缺失/无权限时如实返回）。"""
    try:
        import keyboard  # noqa: F401
        return {"ok": True, "reason": ""}
    except Exception as e:
        return {"ok": False, "reason": f"keyboard 库不可用: {e}"}


def _load_persisted():
    """把今日已落库计数加载进内存，保证重启后热力图连续。"""
    try:
        from db import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT key_name, count FROM keyboard_stats_daily WHERE stat_date = ?",
                (_today(),),
            ).fetchall()
        with _stats_lock:
            for r in rows:
                name, cnt = r[0], int(r[1] or 0)
                _key_stats[name] = max(_key_stats[name], cnt)
                _persisted[name] = cnt
    except Exception as e:
        logger.debug(f"键盘统计加载失败（首次运行可忽略）: {e}")


def flush_stats() -> int:
    """把内存增量写入 SQLite，返回本次写入的键数。"""
    today = _today()
    with _stats_lock:
        delta = {k: v - _persisted.get(k, 0) for k, v in _key_stats.items()
                 if v > _persisted.get(k, 0)}
    if not delta:
        return 0
    try:
        from db import get_conn
        with get_conn() as conn:
            for key, d in delta.items():
                conn.execute(
                    "INSERT INTO keyboard_stats_daily (stat_date, key_name, count) VALUES (?, ?, ?) "
                    "ON CONFLICT(stat_date, key_name) DO UPDATE SET "
                    "count = count + excluded.count, updated_at = datetime('now','localtime')",
                    (today, key, int(d)),
                )
            conn.commit()
        with _stats_lock:
            for key, d in delta.items():
                _persisted[key] = _persisted.get(key, 0) + d
        return len(delta)
    except Exception as e:
        logger.warning(f"键盘统计落库失败: {e}")
        return 0


def _flush_loop():
    while not _flush_stop.wait(_FLUSH_INTERVAL_SEC):
        flush_stats()


def start_listening() -> dict:
    """启动全局按键监听，返回真实结果（不做假成功）。"""
    global _listening, _flush_thread
    if _listening:
        return {"ok": True, "message": "键盘监听已在运行"}
    avail = check_availability()
    if not avail["ok"]:
        logger.warning(f"键盘监听不可用: {avail['reason']}")
        return {"ok": False, "error": avail["reason"],
                "hint": "安装依赖 pip install keyboard，并以管理员权限运行"}
    try:
        import keyboard
        _load_persisted()
        keyboard.hook(_on_key_event)
        _listening = True
        _flush_stop.clear()
        _flush_thread = threading.Thread(target=_flush_loop, daemon=True, name="kb-flush")
        _flush_thread.start()
        logger.info("键盘热力图监听已启动")
        return {"ok": True, "message": "键盘监听已启动"}
    except Exception as e:
        logger.warning(f"键盘监听启动失败(需要管理员权限): {e}")
        return {"ok": False, "error": str(e), "hint": "请以管理员权限运行应用"}


def stop_listening() -> dict:
    global _listening
    if not _listening:
        return {"ok": True, "message": "键盘监听未在运行"}
    try:
        import keyboard
        keyboard.unhook_all()
        _flush_stop.set()
        _listening = False
        flush_stats()
        logger.info("键盘热力图监听已停止")
        return {"ok": True, "message": "键盘监听已停止"}
    except Exception as e:
        logger.debug(f"停止监听失败: {e}")
        return {"ok": False, "error": str(e)}


def is_listening() -> bool:
    return _listening


def get_stats() -> dict[str, int]:
    with _stats_lock:
        return dict(_key_stats)


def get_hotkeys(limit: int = 20) -> list[dict]:
    with _stats_lock:
        sorted_keys = sorted(_key_stats.items(), key=lambda x: x[1], reverse=True)
    return [{"key": k, "count": v} for k, v in sorted_keys[:limit]]


def reset_stats() -> dict:
    """重置统计：清内存 + 删今日持久化行（真实生效）。"""
    global _key_stats
    with _stats_lock:
        _key_stats.clear()
        _persisted.clear()
    try:
        from db import get_conn
        with get_conn() as conn:
            cur = conn.execute("DELETE FROM keyboard_stats_daily WHERE stat_date = ?", (_today(),))
            conn.commit()
            deleted = cur.rowcount
        return {"ok": True, "deleted": deleted}
    except Exception as e:
        return {"ok": False, "error": str(e)}
