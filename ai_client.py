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


# ── 日志脱敏：过滤 Bearer token / api_key 等敏感串 ──
_BEARER_RE = re.compile(r"(Bearer\s+)[^\s]+")
_APIKEY_RE = re.compile(r"(sk-[A-Za-z0-9]{6})[A-Za-z0-9]*")


def _sanitize_log(msg) -> str:
    """对日志消息做脱敏：屏蔽 Bearer token 与疑似 API Key，防止密钥泄漏到日志文件"""
    try:
        s = str(msg)
        s = _BEARER_RE.sub(r"\1***", s)
        s = _APIKEY_RE.sub(r"\1******", s)
        return s
    except Exception:
        return "<sanitize failed>"


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


def analyze_screenshot(image_path: str, app_name: str = "", window_title: str = "",
                        recent_context: str = "", visible_windows: list[dict] | None = None) -> dict:
    """
    调用 AI Vision 分析截图，返回 {"category": ..., "summary": ..., "detail": ..., "windows": [...]}
    内置指数退避重试（3次）+ 熔断器
    recent_context: 近期活动的简短描述，供 AI 综合分析
    visible_windows: 当前屏幕上所有可见窗口的列表
    """
    if not config.AI_API_KEY:
        # 降级：使用窗口标题作为摘要，而非无意义占位符
        fallback_summary = f"{app_name} - {window_title}" if window_title else app_name or "未配置AI"
        return {"category": "生活", "summary": fallback_summary, "detail": "AI 未配置，请在设置中配置 API Key 以启用智能摘要", "windows": []}

    # 熔断器检查
    if not _cb_check():
        logger.info("Circuit breaker OPEN，跳过 AI 请求")
        fallback_summary = f"{app_name} - {window_title}" if window_title else app_name or "AI服务暂时不可用"
        return {"category": "生活", "summary": fallback_summary, "detail": "AI 服务暂时不可用，等待恢复中", "windows": []}

    # 预先将图片编码为 base64，避免重试时重复读取文件
    try:
        b64_image = encode_image_to_base64(image_path)
    except FileNotFoundError:
        logger.error(f"截图文件不存在: {image_path}")
        return {"category": "生活", "summary": "截图文件缺失", "detail": "截图已被清理或路径错误", "windows": []}

    user_text = build_user_prompt(app_name, window_title, recent_context, visible_windows)

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
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                max_tokens=800,
                temperature=0.2,
            )

            raw = response.choices[0].message.content.strip()

            # 尝试提取 JSON
            result = _parse_json_response(raw)
            if result:
                # 后校验：过滤 AI 幻觉
                result = _sanitize_analysis_result(result, app_name, visible_windows)
                _cb_record_success()
                return result

            # JSON 解析失败
            logger.warning(f"AI 返回非 JSON 格式: {raw[:100]}")
            _cb_record_failure()
            return {"category": "生活", "summary": "解析失败", "detail": raw[:50]}

        except Exception as e:
            wait = 1.0 * (2 ** attempt)  # 1s, 2s, 4s
            if attempt < max_retries - 1:
                logger.warning(_sanitize_log(f"AI 分析失败 (尝试 {attempt+1}/{max_retries})，{wait:.0f}s 后重试: {e}"))
                time.sleep(wait)
            else:
                logger.error(_sanitize_log(f"AI 分析最终失败 (已重试 {max_retries} 次): {e}"))
                _reset_client()
                _cb_record_failure()
                return {"category": "生活", "summary": "分析异常", "detail": str(e)[:50]}


# IDE/编辑器进程名列表
_IDE_PROCESSES = {"trae soolo cn.exe", "trae.exe", "code.exe", "cursor.exe", "idea64.exe", "pycharm64.exe", "webstorm64.exe", "clion64.exe", "goland64.exe", "rubymine64.exe", "phpstorm64.exe", "datagrip64.exe", "rider64.exe", "visualstudio.exe", "devenv.exe", "notepad++.exe", "sublime_text.exe", "atom.exe", "brackets.exe"}


def _is_ide_app(app_name: str) -> bool:
    return app_name.lower().replace(" ", "") in {p.replace(" ", "").replace(".exe", "") for p in _IDE_PROCESSES}


def _sanitize_analysis_result(result: dict, app_name: str, visible_windows: list[dict] | None) -> dict:
    """
    后校验 AI 返回结果，过滤幻觉：
    1. windows 数组里的 app_name 必须来自传入的 visible_windows
    2. 当前前台不是 IDE 时，summary/detail 不能出现具体代码相关元素
    """
    visible_apps = {w.get("app_name", "").lower() for w in (visible_windows or []) if w.get("app_name")}
    # 清理 windows 数组中的幻觉窗口
    windows = result.get("windows") or []
    cleaned_windows = []
    for w in windows:
        w_app = w.get("app_name", "").lower()
        if w_app in visible_apps:
            cleaned_windows.append(w)
        else:
            logger.warning(f"[AI sanitize] 过滤掉不在可见窗口列表中的应用: {w_app}")
    result["windows"] = cleaned_windows

    foreground_is_ide = _is_ide_app(app_name or "")
    if not foreground_is_ide:
        # 如果前台不是 IDE，但 detail/summary 出现典型代码元素，说明是幻觉
        code_signals = [".py", ".js", ".ts", ".java", ".go", ".cpp", ".c", ".h", ".rs", ".swift", ".kt",
                        "函数", "login", "auth", "token", "api", "接口", "调试", "bug", "报错", "编译",
                        "github", "gitlab", "commit", "pr", "merge", "仓库", "分支"]
        summary = result.get("summary", "")
        detail = result.get("detail", "")
        combined = f"{summary} {detail}".lower()
        if any(s in combined for s in code_signals):
            logger.warning("[AI sanitize] 前台非 IDE 但出现代码相关描述，判定为幻觉并回退")
            result["summary"] = f"使用 {app_name}"
            result["detail"] = f"当前前台应用为 {app_name}，截图中未显示代码或开发相关内容，无法判断具体工作内容。"
            result["category"] = "生活"
    return result


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


def _format_min_greeting(minutes: float) -> str:
    """把分钟数格式化为中文可读时长"""
    if minutes >= 60:
        h = int(minutes // 60)
        m = round(minutes % 60)
        return f"{h}小时{m}分" if m else f"{h}小时"
    return f"{round(minutes)}分钟"


def _greeting_word_by_hour(hour: int) -> str:
    if 5 <= hour < 11:
        return "早上好"
    if 11 <= hour < 13:
        return "中午好"
    if 13 <= hour < 18:
        return "下午好"
    if 18 <= hour < 23:
        return "晚上好"
    return "夜深了"


def _build_greeting_draft(context: dict) -> str:
    """基于真实数据生成一段信息完整的导语草稿（AI 失败时直接返回）"""
    time_str = context.get("time", "")
    date_str = context.get("date", "")
    weekday = context.get("weekday", "")
    lunar = context.get("lunar", "")
    location = context.get("location", "")
    weather = context.get("weather", "")
    temp = context.get("temp", "")

    hour = 0
    if time_str and ":" in time_str:
        try:
            hour = int(time_str.split(":")[0])
        except ValueError:
            pass

    env_parts = []
    if location:
        env_parts.append(location)
    if weather:
        env_parts.append(weather)
    if temp:
        env_parts.append(f"{temp}°C")
    env = "，".join(env_parts)

    today_str = _format_min_greeting(context.get("today_duration_min", 0))
    yesterday_str = _format_min_greeting(context.get("yesterday_duration_min", 0))
    recent3_str = _format_min_greeting(context.get("recent3_total_min", 0))
    top_apps = context.get("top_apps", [])
    top_categories = context.get("top_categories", [])

    draft = (
        f"{_greeting_word_by_hour(hour)}！"
        f"现在是 {date_str} {weekday} {time_str}"
        f"{'，' + lunar if lunar else ''}"
        f"{'（' + env + '）' if env else ''}"
        f"。今天已工作 {today_str}，昨天 {yesterday_str}，最近三天累计 {recent3_str}"
        f"。主要投入在 {', '.join(top_apps[:3]) if top_apps else '暂无记录'}"
        f"，集中在 {', '.join(top_categories[:3]) if top_categories else '暂无记录'}。"
        f"保持节奏，继续加油！"
    )
    return draft


def generate_greeting(context: dict) -> str:
    """
    根据用户近期工作数据生成温馨早安导语。
    先让 AI 基于真实数据草稿润色；AI 不可用或失败时返回草稿本身，保证信息不丢失。
    """
    draft = _build_greeting_draft(context)

    time_str = context.get("time", "")
    hour = 0
    if time_str and ":" in time_str:
        try:
            hour = int(time_str.split(":")[0])
        except ValueError:
            pass
    greeting_word = _greeting_word_by_hour(hour)

    if not config.AI_API_KEY:
        return draft

    if not _cb_check():
        return draft

    prompt = (
        "请把下面这段基于用户真实数据的早安导语改写成 2-3 句温馨、有画面感的中文问候。\n"
        "要求：\n"
        "1. 必须保留所有真实信息：当前时间、日期、星期、农历、地点、天气、温度、今天/昨天/近三天工作时长、主要应用、主要分类。\n"
        "2. 不要删减数据，不要编造不存在的信息。\n"
        "3. 语气温暖自然，像朋友在窗边聊天，总字数控制在 90 字以内。\n"
        f"4. 当前时间是 {time_str}，必须直接以问候语‘{greeting_word}’开头，不允许改成早安/清晨好/晚上好等其他问候。\n\n"
        f"原文：{draft}"
    )

    max_retries = 2
    for attempt in range(max_retries):
        try:
            client = _get_client()
            response = client.chat.completions.create(
                model=config.AI_TEXT_MODEL,
                messages=[
                    {"role": "system", "content": "你是 ChallengeDaily，一个温暖贴心的工作效率助手。请基于用户真实数据写简短温馨的问候导语，不编造、不遗漏，并且严格按要求使用指定问候语开头。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=220,
                temperature=0.3,
            )
            text = response.choices[0].message.content.strip()
            _cb_record_success()
            # 如果 AI 仍然乱改问候语，直接回退到带真实数据的草稿
            if text and text.startswith(greeting_word):
                return text
            return draft
        except Exception as e:
            wait = 1.0 * (2 ** attempt)
            if attempt < max_retries - 1:
                logger.warning(_sanitize_log(f"AI 导语生成失败 (尝试 {attempt+1}/{max_retries})，{wait:.0f}s 后重试: {e}"))
                time.sleep(wait)
            else:
                logger.error(_sanitize_log(f"AI 导语生成最终失败: {e}"))
                _reset_client()
                _cb_record_failure()
                return draft
