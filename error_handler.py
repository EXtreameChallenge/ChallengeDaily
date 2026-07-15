"""P54+P55: 统一错误处理 — 安全错误响应 + 错误分类

确保所有 API 端点使用一致的错误处理模式：
1. 内部错误不暴露给用户（脱敏）
2. 业务错误返回有意义的消息
3. 基础设施错误触发告警
"""
import logging
import traceback
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 不应暴露给用户的错误关键词
_SENSITIVE_ERROR_KEYWORDS = [
    "password", "secret", "token", "key", "credential",
    "sql", "query", "database", "sqlite", "connection",
    "path", "file", "directory", "permission",
    "stack", "traceback", "exception",
]


def safe_error_message(err: Exception, fallback: str = "操作失败，请稍后重试") -> str:
    """P55: 生成安全的错误消息（脱敏敏感信息）"""
    err_str = str(err)
    err_lower = err_lower = err_str.lower()
    for kw in _SENSITIVE_ERROR_KEYWORDS:
        if kw in err_lower:
            return fallback
    # 截断过长的错误消息
    if len(err_str) > 200:
        return err_str[:200] + "..."
    return err_str


def is_infra_error(err: Exception) -> bool:
    """P55: 判断是否为基础设施错误（网络/数据库/系统级）"""
    err_str = str(err).lower()
    infra_keywords = [
        "timeout", "timed out", "connection", "refused", "reset",
        "dns", "resolve", "unreachable", "broken pipe",
        "sqlite", "operationalerror", "databerror",
        "out of memory", "disk full", "no space",
        "permission denied", "access denied",
    ]
    for kw in infra_keywords:
        if kw in err_str:
            return True
    return False


def is_business_error(err: Exception) -> bool:
    """P55: 判断是否为业务逻辑错误（非基础设施）"""
    return not is_infra_error(err)


def api_error_handler(f: Callable) -> Callable:
    """P54: API 错误处理装饰器 — 统一 try/except 模式

    用法：
        @bp.route('/api/something')
        @api_error_handler
        def handler():
            ...
    """
    @wraps(f)
    def wrapped(*args, **kwargs):
        from flask import jsonify
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            # 业务验证错误
            logger.info(f"业务验证失败: {e}")
            return jsonify({"error": safe_error_message(e, "参数错误")}), 400
        except PermissionError as e:
            logger.warning(f"权限错误: {e}")
            return jsonify({"error": "权限不足"}), 403
        except FileNotFoundError as e:
            logger.info(f"文件未找到: {e}")
            return jsonify({"error": "资源不存在"}), 404
        except Exception as e:
            # 未知错误：记录完整堆栈，返回安全消息
            logger.error(f"API 未预期错误: {e}\n{traceback.format_exc()}")
            if is_infra_error(e):
                return jsonify({"error": "服务暂时不可用，请稍后重试"}), 503
            return jsonify({"error": safe_error_message(e)}), 500
    return wrapped


def log_error_with_context(
    err: Exception,
    context: dict[str, Any],
    operation: str = "",
    logger_name: str = __name__,
):
    """P56: 带上下文的错误日志记录"""
    log = logging.getLogger(logger_name)
    context_str = ", ".join(f"{k}={v}" for k, v in context.items() if v is not None)
    log.error(
        f"[{operation}] 错误: {type(err).__name__}: {safe_error_message(err)} | "
        f"上下文: {context_str}"
    )
