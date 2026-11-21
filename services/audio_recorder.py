"""
ChallengeDaily — 录音器 & 音频转写模块
Wave2-B07：录音流句柄改为模块级持有，stop 真正关闭 InputStream；
Wave2-B08：转写接真实 OpenAI 兼容 Whisper 接口，未配置凭证时如实返回 unsupported，
不再返回"[转写结果占位]"的假文本。
"""
import threading
import time
import logging
import os
import tempfile
from datetime import datetime

logger = logging.getLogger(__name__)

_recording = False
_stream = None
_frames = []
_sample_rate = 16000
_recording_start_time = 0
_lock = threading.Lock()

DEFAULT_WHISPER_BASE = os.environ.get("CHALLENGEDAILY_WHISPER_BASE", "https://api.openai.com/v1")
DEFAULT_WHISPER_MODEL = os.environ.get("CHALLENGEDAILY_WHISPER_MODEL", "whisper-1")


def start_recording() -> dict:
    """开始录音"""
    global _recording, _stream, _frames, _recording_start_time
    with _lock:
        if _recording:
            return {"ok": False, "error": "已在录音中"}
    try:
        import sounddevice as sd
    except ImportError:
        return {"ok": False, "error": "sounddevice 未安装，请 pip install sounddevice",
                "hint": "同时需要 numpy 与 scipy 用于保存音频"}
    try:
        with _lock:
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
    except Exception as e:
        logger.error(f"录音启动失败: {e}")
        with _lock:
            _recording = False
            _stream = None
        return {"ok": False, "error": str(e), "hint": "请确认已连接麦克风且未被其它应用独占"}


def stop_recording() -> dict:
    """停止录音并保存为 WAV"""
    global _recording, _stream
    with _lock:
        if not _recording:
            return {"ok": False, "error": "未在录音"}
        _recording = False
        duration = time.time() - _recording_start_time
        stream = _stream
        _stream = None

    try:
        if stream is not None:
            try:
                stream.stop()
            finally:
                stream.close()
    except Exception as e:
        logger.debug(f"关闭录音流失败（忽略）: {e}")

    if not _frames:
        return {"ok": False, "error": "没有采集到音频数据（麦克风可能被静音或权限被拒）"}

    try:
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


def _resolve_api_key(api_key: str) -> str:
    return (api_key or os.environ.get("OPENAI_API_KEY", "") or "").strip()


def transcribe_audio(filepath: str, api_key: str = "") -> dict:
    """调用 OpenAI 兼容 Whisper 接口转写音频。

    未配置凭证 / 文件缺失时返回 unsupported 明确原因，绝不返回占位文本。
    """
    if not filepath or not os.path.exists(filepath):
        return {"ok": False, "error": "音频文件不存在", "filepath": filepath}

    key = _resolve_api_key(api_key)
    if not key:
        return {
            "ok": False,
            "unsupported": True,
            "error": "未配置语音转写凭证（需设置 OPENAI_API_KEY 或传入 api_key）",
            "hint": f"接口: {DEFAULT_WHISPER_BASE}/audio/transcriptions，模型 {DEFAULT_WHISPER_MODEL}",
        }

    try:
        import requests
        with open(filepath, 'rb') as f:
            resp = requests.post(
                f"{DEFAULT_WHISPER_BASE.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files={"file": (os.path.basename(filepath), f, "audio/wav")},
                data={"model": DEFAULT_WHISPER_MODEL, "language": "zh"},
                timeout=120,
            )
        if resp.status_code != 200:
            logger.warning(f"转写接口返回 {resp.status_code}: {resp.text[:200]}")
            return {"ok": False, "error": f"转写接口返回 {resp.status_code}",
                    "detail": resp.text[:200]}
        payload = resp.json()
        text = (payload.get("text") or "").strip()
        if not text:
            return {"ok": False, "error": "转写返回为空"}
        logger.info(f"转写成功: {filepath} ({len(text)} 字)")
        return {"ok": True, "text": text, "duration": payload.get("duration", 0)}
    except Exception as e:
        logger.error(f"转写失败: {e}")
        return {"ok": False, "error": str(e)}
