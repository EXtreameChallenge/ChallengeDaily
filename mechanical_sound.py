"""
ChallengeDaily — 机械键盘音效模块
Wave2-B12：用 winsound 播放合成按键音（Windows 内置，无第三方依赖）；
不可用时如实返回 available:false 并拒绝开启，不做静默假成功。
"""
import threading
import logging
import os
import math
import random
import struct
import tempfile
import time

logger = logging.getLogger(__name__)

_enabled = False
_sound_path = ""
_lock = threading.Lock()
_last_play_ts = 0.0
_MIN_PLAY_GAP_SEC = 0.02


def _winsound_available() -> tuple[bool, str]:
    try:
        import winsound  # noqa: F401
        return True, ""
    except Exception as e:
        return False, f"winsound 不可用（仅 Windows 支持）: {e}"


def _ensure_sample() -> str:
    """生成一段短促的机械键击音（衰减噪声），缓存到临时目录。"""
    global _sound_path
    if _sound_path and os.path.exists(_sound_path):
        return _sound_path
    rate = 44100
    duration = 0.018
    n = int(rate * duration)
    path = os.path.join(tempfile.gettempdir(), "challenge_daily_keyclick.wav")
    frames = bytearray()
    for i in range(n):
        t = i / rate
        env = math.exp(-t * 170)
        amp = int(18000 * env * random.uniform(-1, 1))
        amp = max(-32768, min(32767, amp))
        frames += struct.pack('<h', amp)
    import wave
    with wave.open(path, 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(bytes(frames))
    _sound_path = path
    return path


def set_enabled(enabled: bool) -> dict:
    """开关音效，返回真实结果。"""
    global _enabled
    if enabled:
        ok, reason = _winsound_available()
        if not ok:
            with _lock:
                _enabled = False
            return {"ok": False, "enabled": False, "error": reason}
    with _lock:
        _enabled = bool(enabled)
    logger.info(f"机械键盘音效: {'开启' if enabled else '关闭'}")
    return {"ok": True, "enabled": _enabled}


def is_enabled() -> bool:
    return _enabled


def play_keypress_sound():
    """播放一次按键音效（非阻塞，节流 20ms）。"""
    global _last_play_ts
    if not _enabled:
        return
    now = time.time()
    if now - _last_play_ts < _MIN_PLAY_GAP_SEC:
        return
    _last_play_ts = now
    try:
        import winsound
        path = _ensure_sample()
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception as e:
        logger.debug(f"音效播放失败: {e}")


def get_status() -> dict:
    ok, reason = _winsound_available()
    return {
        "enabled": _enabled,
        "available": ok,
        "reason": reason,
        "soundPath": _sound_path,
    }
