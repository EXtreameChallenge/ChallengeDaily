"""
P18-4: 本地小模型降级 — Ollama HTTP API 集成
- 当云端 AI（OpenAI 兼容协议）不可用时自动降级到本地 Ollama
- 支持 Qwen2-VL / LLaVA 等多模态模型做截图分类
- 支持纯文本模型（qwen2.5、llama3.1 等）做日报生成
- 自动检测 Ollama 可用性、列出已安装模型
- 降级策略：API 失败 → 熔断 → 尝试本地模型 → 本地失败 → 用规则引擎兜底
- 隐私优先：所有请求仅发往 127.0.0.1，不外传任何数据
"""
import json
import logging
import os
import base64
import threading
import time
import urllib.request
import urllib.parse
from typing import Optional

import config

logger = logging.getLogger(__name__)

# ── Ollama 配置 ──
_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
_HEALTH_CHECK_CACHE: dict[str, tuple[bool, float]] = {}  # key -> (ok, timestamp)
_HEALTH_CHECK_TTL = 60  # 60 秒缓存
_HEALTH_LOCK = threading.Lock()

# 本地模型默认配置（可在 settings.json 中覆盖）
_DEFAULT_LOCAL_CONFIG = {
    "enabled": False,
    "base_url": "http://127.0.0.1:11434",
    "vision_model": "llava",          # 默认视觉模型（用户可换成 qwen2-vl）
    "text_model": "qwen2.5:7b",       # 默认文本模型
    "fallback_to_rules": True,        # 本地模型也失败时用规则引擎兜底
    "auto_fallback": True,            # 云端失败时自动降级
    "timeout_sec": 60,                # 本地推理超时
}

_CONFIG_LOCK = threading.Lock()


def get_local_model_config() -> dict:
    """从 settings 读取本地模型配置"""
    try:
        settings = config.load_settings()
        local_cfg = settings.get("local_model", {})
        result = dict(_DEFAULT_LOCAL_CONFIG)
        result.update(local_cfg)
        return result
    except Exception:
        return dict(_DEFAULT_LOCAL_CONFIG)


def update_local_model_config(**kwargs) -> dict:
    """更新本地模型配置"""
    with _CONFIG_LOCK:
        settings = config.load_settings()
        local_cfg = settings.get("local_model", {})
        for k, v in kwargs.items():
            if k in _DEFAULT_LOCAL_CONFIG:
                local_cfg[k] = v
        settings["local_model"] = local_cfg
        config.save_settings(settings)
        result = dict(_DEFAULT_LOCAL_CONFIG)
        result.update(local_cfg)
        return result


# ── Ollama HTTP 调用 ──

def _ollama_request(endpoint: str, payload: dict, timeout: int = 60) -> dict:
    """调用 Ollama HTTP API"""
    cfg = get_local_model_config()
    base_url = cfg.get("base_url", _OLLAMA_BASE_URL).rstrip("/")
    url = f"{base_url}{endpoint}"

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        # Ollama 支持 stream 和 non-stream 模式
        content = resp.read().decode("utf-8")
        # 非流式：直接是单个 JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # 流式：每行一个 JSON，需要拼接
            result = {}
            for line in content.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    if "response" in chunk:
                        result.setdefault("response", "")
                        result["response"] += chunk["response"]
                    if chunk.get("done"):
                        result.update({k: v for k, v in chunk.items() if k != "response"})
                except Exception:
                    continue
            return result


def check_ollama_available() -> dict:
    """检测 Ollama 是否可用（带缓存）"""
    cfg = get_local_model_config()
    base_url = cfg.get("base_url", _OLLAMA_BASE_URL).rstrip("/")
    cache_key = base_url

    with _HEALTH_LOCK:
        cached = _HEALTH_CHECK_CACHE.get(cache_key)
        if cached and (time.time() - cached[1]) < _HEALTH_CHECK_TTL:
            return {"available": cached[0], "cached": True, "base_url": base_url}

    try:
        req = urllib.request.Request(f"{base_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            ok = True
            with _HEALTH_LOCK:
                _HEALTH_CHECK_CACHE[cache_key] = (ok, time.time())
            return {
                "available": True,
                "base_url": base_url,
                "models": models,
                "model_count": len(models),
            }
    except Exception as e:
        with _HEALTH_LOCK:
            _HEALTH_CHECK_CACHE[cache_key] = (False, time.time())
        return {
            "available": False,
            "base_url": base_url,
            "error": str(e)[:200],
        }


def list_ollama_models() -> list[dict]:
    """列出 Ollama 已安装的模型"""
    try:
        cfg = get_local_model_config()
        base_url = cfg.get("base_url", _OLLAMA_BASE_URL).rstrip("/")
        req = urllib.request.Request(f"{base_url}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [
                {
                    "name": m.get("name", ""),
                    "size_mb": round(m.get("size", 0) / (1024 * 1024), 1),
                    "modified_at": m.get("modified_at", ""),
                }
                for m in data.get("models", [])
            ]
    except Exception as e:
        logger.warning(f"列出 Ollama 模型失败: {e}")
        return []


def _detect_model_capabilities(model_name: str) -> dict:
    """根据模型名推断能力（视觉/文本）"""
    name_lower = model_name.lower()
    vision_keywords = ("llava", "qwen2-vl", "qwen2.5-vl", "vl-", "-vl", "vision", "bakllava", "moondream")
    is_vision = any(k in name_lower for k in vision_keywords)
    return {
        "vision": is_vision,
        "text": True,  # 所有模型都支持文本
    }


# ── 本地视觉模型：截图分类 ──

def local_vision_classify(image_base64: str, prompt: str) -> dict:
    """用本地视觉模型做截图分类

    Args:
        image_base64: base64 编码的图片（不带 data:image/ 前缀）
        prompt: 提示词

    Returns: {category, summary, detail, raw_response}
    """
    cfg = get_local_model_config()
    vision_model = cfg.get("vision_model", "llava")
    timeout = cfg.get("timeout_sec", 60)

    payload = {
        "model": vision_model,
        "prompt": prompt,
        "images": [image_base64],
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 500,
        },
    }

    try:
        result = _ollama_request("/api/generate", payload, timeout=timeout)
        raw = result.get("response", "").strip()

        # 尝试从响应中解析 JSON
        parsed = _parse_ai_json(raw)
        if parsed and "category" in parsed:
            return {
                "category": parsed.get("category", "其他"),
                "summary": parsed.get("summary", raw[:100]),
                "detail": parsed.get("detail", ""),
                "raw_response": raw,
                "model": vision_model,
                "source": "local",
            }

        # 解析失败：用关键词规则从原文推断分类
        category = _infer_category_from_text(raw)
        return {
            "category": category,
            "summary": raw[:100] if raw else "本地模型未返回内容",
            "detail": raw,
            "raw_response": raw,
            "model": vision_model,
            "source": "local",
        }
    except Exception as e:
        logger.warning(f"本地视觉模型分类失败: {e}")
        return {
            "category": "其他",
            "summary": f"本地模型错误: {str(e)[:100]}",
            "detail": "",
            "raw_response": "",
            "model": vision_model,
            "source": "local_error",
            "error": str(e)[:200],
        }


# ── 本地文本模型：日报生成/对话 ──

def local_text_complete(prompt: str, system_prompt: str = "") -> dict:
    """用本地文本模型做补全

    Returns: {text, model, source}
    """
    cfg = get_local_model_config()
    text_model = cfg.get("text_model", "qwen2.5:7b")
    timeout = cfg.get("timeout_sec", 60)

    payload = {
        "model": text_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.6,
            "num_predict": 1500,
        },
    }
    if system_prompt:
        payload["system"] = system_prompt

    try:
        result = _ollama_request("/api/generate", payload, timeout=timeout)
        text = result.get("response", "").strip()
        return {
            "text": text,
            "model": text_model,
            "source": "local",
            "raw": result,
        }
    except Exception as e:
        logger.warning(f"本地文本模型调用失败: {e}")
        return {
            "text": "",
            "model": text_model,
            "source": "local_error",
            "error": str(e)[:200],
        }


# ── 降级策略 ──

def should_fallback_to_local(cloud_error: Optional[Exception] = None) -> bool:
    """判断是否应该降级到本地模型"""
    cfg = get_local_model_config()
    if not cfg.get("auto_fallback", True):
        return False
    if not cfg.get("enabled", False):
        return False
    # 检查 Ollama 是否可用
    health = check_ollama_available()
    return health.get("available", False)


def fallback_classify_with_local(image_base64: str, prompt: str) -> dict:
    """云端失败后的本地降级分类"""
    result = local_vision_classify(image_base64, prompt)
    if result.get("source") == "local_error":
        cfg = get_local_model_config()
        if cfg.get("fallback_to_rules", True):
            # 用规则引擎兜底
            return _rules_engine_fallback(prompt)
    return result


def fallback_text_with_local(prompt: str, system_prompt: str = "") -> dict:
    """云端失败后的本地降级文本生成"""
    result = local_text_complete(prompt, system_prompt)
    if not result.get("text"):
        cfg = get_local_model_config()
        if cfg.get("fallback_to_rules", True):
            return {
                "text": _rules_engine_text_fallback(prompt),
                "source": "rules",
                "model": "rules-engine",
            }
    return result


# ── 规则引擎兜底 ──

def _rules_engine_fallback(prompt: str) -> dict:
    """纯规则兜底：从 prompt 中提取关键词推断分类"""
    prompt_lower = prompt.lower()
    # 从 prompt 中的窗口标题/应用名推断分类
    category_map = [
        (["vscode", "code.exe", "pycharm", "idea", "intellij"], "开发"),
        (["chrome", "edge", "firefox", "浏览器"], "学习"),
        (["wechat", "微信", "dingtalk", "飞书", "feishu", "teams"], "沟通"),
        (["word", "excel", "powerpoint", "wps", "文档"], "文档"),
        (["figma", "sketch", "photoshop", "ps", "ai"], "设计"),
        (["terminal", "powershell", "cmd", "shell"], "运维"),
        (["outlook", "邮箱", "mail"], "沟通"),
        (["meeting", "会议", "zoom", "腾讯会议"], "会议"),
        (["游戏", "game", "steam"], "生活"),
        (["bilibili", "youtube", "抖音", "tiktok", "video"], "生活"),
    ]
    for keywords, cat in category_map:
        if any(k in prompt_lower for k in keywords):
            return {
                "category": cat,
                "summary": f"规则引擎识别：{cat}（云端与本地模型均不可用）",
                "detail": "",
                "raw_response": "",
                "model": "rules-engine",
                "source": "rules",
            }
    return {
        "category": "其他",
        "summary": "规则引擎无法识别（云端与本地模型均不可用）",
        "detail": "",
        "raw_response": "",
        "model": "rules-engine",
        "source": "rules",
    }


def _rules_engine_text_fallback(prompt: str) -> str:
    """纯规则文本兜底：生成简化的日报/对话回复"""
    if "日报" in prompt or "今日总结" in prompt:
        return (
            "【本地规则引擎生成的简化日报】\n\n"
            "由于云端 AI 与本地模型均不可用，本次日报由规则引擎生成。\n"
            "建议稍后网络或模型恢复后重新生成完整日报。\n\n"
            "今日活动概览：\n"
            "- 详细数据请查看活动列表与统计图表\n"
            "- 各分类时长请查看 Dashboard 上的占比图\n"
        )
    if "建议" in prompt:
        return (
            "【本地规则引擎建议】\n\n"
            "1. 检查 AI 配置是否正确（API Key、Base URL）\n"
            "2. 若网络不稳定，可启用本地模型降级（设置 → AI → 本地模型）\n"
            "3. 检查 Ollama 服务是否正常运行\n"
        )
    return (
        "【本地规则引擎】云端 AI 与本地模型均不可用，无法生成详细回复。"
        "请检查 AI 配置或网络连接后重试。"
    )


# ── JSON 解析工具 ──

def _parse_ai_json(text: str) -> Optional[dict]:
    """尝试从 AI 输出文本中提取 JSON 对象"""
    if not text:
        return None
    # 直接尝试
    try:
        return json.loads(text)
    except Exception:
        pass
    # 提取 ```json ... ``` 代码块
    import re
    m = re.search(r"```(?:json)?\s*\n?(.+?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 提取第一个 { ... } 块
    m = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    return None


def _infer_category_from_text(text: str) -> str:
    """从 AI 响应文本中推断分类"""
    if not text:
        return "其他"
    text_lower = text.lower()
    category_keywords = {
        "开发": ["代码", "编程", "code", "开发", "ide", "git", "调试", "编程语言"],
        "会议": ["会议", "meeting", "讨论", "call", "视频会议"],
        "沟通": ["聊天", "微信", "邮件", "chat", "message"],
        "文档": ["文档", "word", "excel", "ppt", "doc"],
        "设计": ["设计", "design", "figma", "画图"],
        "学习": ["学习", "阅读", "read", "教程", "文档"],
        "测试": ["测试", "test", "qa", "bug"],
        "运维": ["运维", "deploy", "服务器", "shell"],
        "管理": ["管理", "项目", "任务", "task"],
        "数据分析": ["数据", "分析", "报表", "chart"],
        "生活": ["休息", "游戏", "视频", "购物"],
    }
    for cat, keywords in category_keywords.items():
        if any(k in text_lower for k in keywords):
            return cat
    return "其他"
