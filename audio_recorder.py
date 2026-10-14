"""
ChallengeDaily — 录音器 & 音频转写模块
使用 sounddevice 录音，Whisper API 转写
"""
import threading
import time
import logging
import os
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)

_recording = False
_record_thread = None
_frames = []
_sample_rate = 16000
_recording_start_time = 0


def start_recording() -> dict:
    """开始录音"""
    global _recording, _record_thread, _frames, _recording_start_time
    if _recording:
        return {"ok": False, "error": "已在录音中"}
    try:
        import sounddevice as sd
        _frames = []
        _recording = True
        _recording_start_time = time.time()

        def _callback(indata, frames_count, time_info, status):
            if _recording:
                _frames.append(indata.copy())

        _stream = sd.InputStream(samplerate=_sample_rate, channels=1, callback=_callback)
        _stream.start()
        logger.info("录音开始")
        return {"ok": True, "sampleRate": _sample_rate}
    except ImportError:
        return {"ok": False, "error": "sounddevice未安装，请pip install sounddevice"}
    except Exception as e:
        logger.error(f"录音启动失败: {e}")
        return {"ok": False, "error": str(e)}


def stop_recording() -> dict:
    """停止录音并保存"""
    global _recording
    if not _recording:
        return {"ok": False, "error": "未在录音"}
    _recording = False
    duration = time.time() - _recording_start_time

    try:
        import sounddevice as sd
        import numpy as np
        from scipy.io.wavfile import write as wav_write

        audio_data = np.concatenate(_frames, axis=0)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(tempfile.gettempdir(), f"recording_{ts}.wav")
        wav_write(filepath, _sample_rate, audio_data)

        logger.info(f"录音保存: {filepath}, 时长: {duration:.1f}s")
        return {
            "ok": True,
            "filepath": filepath,
            "duration": round(duration, 1),
            "sampleRate": _sample_rate,
        }
    except Exception as e:
        logger.error(f"录音保存失败: {e}")
        return {"ok": False, "error": str(e)}


def get_status() -> dict:
    """获取录音状态"""
    return {
        "recording": _recording,
        "duration": round(time.time() - _recording_start_time, 1) if _recording else 0,
    }


def transcribe_audio(filepath: str, api_key: str = "") -> dict:
    """调用Whisper API转写音频"""
    try:
        import requests
        # 简化实现：调用OpenAI Whisper API
        # 实际使用时替换为你的API endpoint
        logger.info(f"转写音频: {filepath}")
        return {
            "ok": True,
            "text": "[转写结果占位] 音频转写功能需要配置Whisper API Key",
            "duration": 0,
        }
    except Exception as e:
        logger.error(f"转写失败: {e}")
        return {"ok": False, "error": str(e)}
