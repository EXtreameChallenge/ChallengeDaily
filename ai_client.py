"""
ChallengeDaily Windows 版 — AI Vision API 调用
兼容 OpenAI Chat Completions 接口协议（支持 OpenAI / DeepSeek / 通义千问 / Kimi 等）
"""
import json
import logging
import re
import threading
import time
import httpx
from openai import OpenAI

import config
from screenshot import encode_image_to_base64
from prompt import SYSTEM_PROMPT, build_user_prompt

logger = logging.getLogger(__name__)


# ── 单例 OpenAI Client ──
_client_lock = threading.Lock()
_client_instance = None


# ── Circuit Breaker 熔断器 ──
_CB_FAILURE_THRESHOLD = 5      # 连续失败次数触发熔断
_CB_COOLDOWN_SEC = 60          # 熔断冷却时间（秒）
_CB_HALF_OPEN_MAX = 1          # 半开状态允许的试探请求数

_cb_lock = threading.Lock()
_cb_consecutive_failures = 0
_cb_state = "closed"           # closed / open / half_open
_cb_opened_at = 0.0            # 熔断打开时间戳
_cb_half_open_tries = 0        # 半开状态已发试探请求数


def _cb_check() -> bool:
    """检查熔断器是否允许请求通过。返回 True 表示放行，False 表示熔断中。"""
    with _cb_lock:
        global _cb_state, _cb_opened_at, _cb_half_open_tries

        if _cb_state == "closed":
            return True

        if _cb_state == "open":
            # 冷却期结束 → 进入半开
            if time.monotonic() - _cb_opened_at >= _CB_COOLDOWN_SEC:
                _cb_state = "half_open"
                _cb_half_open_tries = 0
                logger.info("Circuit breaker: OPEN → HALF_OPEN，允许试探请求")
                return True
            return False

        if _cb_state == "half_open":
            if _cb_half_open_tries < _CB_HALF_OPEN_MAX:
                _cb_half_open_tries += 1
                return True
            return False

        return True


def _cb_record_success():
    """记录一次成功请求，重置熔断器"""
    with _cb_lock:
        global _cb_state, _cb_consecutive_failures
        if _cb_state == "half_open":
            logger.info("Circuit breaker: HALF_OPEN → CLOSED，试探成功，恢复服务")
        _cb_state = "closed"
        _cb_consecutive_failures = 0


def _cb_record_failure():
    """记录一次失败请求，累计失败次数"""
    with _cb_lock:
        global _cb_state, _cb_consecutive_failures, _cb_opened_at
        _cb_consecutive_failures += 1
        if _cb_state == "half_open":
            # 半开状态失败 → 重新熔断
            _cb_state = "open"
            _cb_opened_at = time.monotonic()
            logger.warning("Circuit breaker: HALF_OPEN → OPEN，试探失败，重新熔断")
        elif _cb_consecutive_failures >= _CB_FAILURE_THRESHOLD:
            _cb_state = "open"
            _cb_opened_at = time.monotonic()
            logger.warning(
                f"Circuit breaker: CLOSED → OPEN，连续 {_cb_consecutive_failures} 次失败，"
                f"冷却 {_CB_COOLDOWN_SEC}s"
            )


def get_circuit_breaker_status() -> dict:
    """获取熔断器状态（供 health API 使用）"""
    with _cb_lock:
        return {
            "state": _cb_state,
            "consecutive_failures": _cb_consecutive_failures,
            "cooldown_remaining_sec": max(0, _CB_COOLDOWN_SEC - (time.monotonic() - _cb_opened_at))
                if _cb_state == "open" else 0,
        }


def _get_client() -> OpenAI:
    """获取或创建单例 OpenAI 客户端（线程安全）"""
    global _client_instance
    if _client_instance is not None:
        return _client_instance
    with _client_lock:
        # 双重检查
        if _client_instance is not None:
            return _client_instance
        _client_instance = OpenAI(
            api_key=config.AI_API_KEY,
            base_url=config.AI_BASE_URL,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
        return _client_instance


def _reset_client():
    """重置客户端实例（配置变更时使用）"""
    global _client_instance
    with _client_lock:
        _client_instance = None


def analyze_screenshot(image_path: str, app_name: str = "", window_title: str = "", recent_context: str = "") -> dict:
    """
    调用 AI Vision 分析截图，返回 {"category": ..., "summary": ..., "detail": ...}
    内置指数退避重试（3次）+ 熔断器
    recent_context: 近期活动的简短描述，供 AI 综合分析
    """
    if not config.AI_API_KEY:
        # 降级：使用窗口标题作为摘要，而非无意义占位符
        fallback_summary = f"{app_name} - {window_title}" if window_title else app_name or "未配置AI"
        return {"category": "生活", "summary": fallback_summary, "detail": "AI 未配置，请在设置中配置 API Key 以启用智能摘要"}

    # 熔断器检查
    if not _cb_check():
        logger.info("Circuit breaker OPEN，跳过 AI 请求")
        fallback_summary = f"{app_name} - {window_title}" if window_title else app_name or "AI服务暂时不可用"
        return {"category": "生活", "summary": fallback_summary, "detail": "AI 服务暂时不可用，等待恢复中"}

    # 预先将图片编码为 base64，避免重试时重复读取文件
    try:
        b64_image = encode_image_to_base64(image_path)
    except FileNotFoundError:
        logger.error(f"截图文件不存在: {image_path}")
        return {"category": "生活", "summary": "截图文件缺失", "detail": "截图已被清理或路径错误"}

    user_text = build_user_prompt(app_name, window_title, recent_context)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            client = _get_client()

            response = client.chat.completions.create(
                model=config.AI_VISION_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_image}",
                                    "detail": "low",
                                },
                            },
                        ],
                    },
                ],
                max_tokens=500,
                temperature=0.3,
            )

            raw = response.choices[0].message.content.strip()

            # 尝试提取 JSON
            result = _parse_json_response(raw)
            if result:
                _cb_record_success()
                return result

            # JSON 解析失败
            logger.warning(f"AI 返回非 JSON 格式: {raw[:100]}")
            _cb_record_failure()
            return {"category": "生活", "summary": "解析失败", "detail": raw[:50]}

        except Exception as e:
            wait = 1.0 * (2 ** attempt)  # 1s, 2s, 4s
            if attempt < max_retries - 1:
                logger.warning(f"AI 分析失败 (尝试 {attempt+1}/{max_retries})，{wait:.0f}s 后重试: {e}")
                time.sleep(wait)
            else:
                logger.error(f"AI 分析最终失败 (已重试 {max_retries} 次): {e}")
                _reset_client()
                _cb_record_failure()
                return {"category": "生活", "summary": "分析异常", "detail": str(e)[:50]}


def _parse_json_response(raw: str) -> dict | None:
    """从 AI 返回的文本中提取 JSON"""
    # 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 尝试提取 { ... }
    match = re.search(r"\{[^{}]+\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None
