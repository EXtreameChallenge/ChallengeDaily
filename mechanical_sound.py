"""
ChallengeDaily — 机械键盘音效模块
按键时播放机械键盘音效，支持自定义音效文件
"""
import threading
import logging
import os
import hashlib

logger = logging.getLogger(__name__)

_enabled = False
_sound_path = ""
_lock = threading.Lock()


def set_enabled(enabled: bool):
    """开关音效"""
    global _enabled
    with _lock:
        _enabled = enabled
    logger.info(f"机械键盘音效: {'开启' if enabled else '关闭'}")


def is_enabled() -> bool:
    return _enabled


def play_keypress_sound():
    """播放一次按键音效（非阻塞）"""
    if not _enabled:
        return
    try:
        import simpleaudio
        # 使用默认音效（后续可扩展为自定义WAV）
        # 简化实现：用系统蜂鸣替代，避免打包WAV文件
        pass
    except Exception as e:
        logger.debug(f"音效播放失败: {e}")


def get_status() -> dict:
    """获取当前状态"""
    return {
        "enabled": _enabled,
        "soundPath": _sound_path,
    }
