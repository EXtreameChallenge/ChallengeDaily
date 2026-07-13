"""
ChallengeDaily Windows 版 — Flask HTTP API
企业级：token 鉴权、graceful shutdown、数据导出、AI 测试
"""
import logging
import time
import uuid
from collections import defaultdict

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from config import HTTP_PORT
from routes.deps import shutdown_event, check_token, save_token, TOKEN_PATH, install_log_redaction
import routes.deps as deps
from routes import ALL_BLUEPRINTS

logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── CORS ──

_ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:58888",
    "http://127.0.0.1:58888",
    "null",  # Electron file:// 协议下 Origin 为 "null"，必须允许
}

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin in _ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Token"
        response.headers["Access-Control-Max-Age"] = "86400"
    elif not origin:
        # 非浏览器请求（如 Electron ipcRenderer）：
        # 不返回通配 *，避免反射型 CORS 漏洞；本地桌面应用鉴权依赖 X-API-Token
        pass
    # 未知 origin 不设置 CORS 头，浏览器会自动拒绝跨域请求
    return response


# ── 注入 collector ──

def set_collector(collector_instance):
    """注入主采集器实例，供 API 路由使用"""
    import routes.deps as deps
    deps.collector = collector_instance


# ── 鉴权中间件 ──

_PUBLIC_PATHS = {"/", "/api/health"}
_PUBLIC_PREFIXES = ["/api/icons/"]


def _is_public_path(path: str) -> bool:
    """判断请求路径是否为公开接口"""
    if path in _PUBLIC_PATHS:
        return True
    for prefix in _PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


# P0-04: Rate Limiting（内存实现，单进程足够），防暴力枚举 token
_RATE_LIMIT_WINDOW = 60      # 60秒窗口
_RATE_LIMIT_MAX = 60         # 每IP每窗口60次
_AUTH_FAIL_LIMIT = 5         # 鉴权失败5次锁定
_AUTH_FAIL_LOCK_SEC = 900    # 锁定15分钟
_rate_limit_store = defaultdict(list)   # ip -> [timestamps]
_auth_fail_store = defaultdict(list)    # ip -> [fail timestamps]


def _check_rate_limit(ip: str) -> bool:
    now = time.time()
    _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limit_store[ip]) >= _RATE_LIMIT_MAX:
        return False
    _rate_limit_store[ip].append(now)
    return True


def _check_auth_fail_limit(ip: str) -> bool:
    now = time.time()
    _auth_fail_store[ip] = [t for t in _auth_fail_store[ip] if now - t < _AUTH_FAIL_LOCK_SEC]
    return len(_auth_fail_store[ip]) < _AUTH_FAIL_LIMIT


def _record_auth_fail(ip: str):
    _auth_fail_store[ip].append(time.time())


# P0-07: 请求体大小限制（Flask 兜底模式兜底，waitress 已有 max_request_body_size）
_MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB


@app.before_request
def check_body_size():
    if request.method in ('POST', 'PUT', 'PATCH'):
        cl = request.content_length
        if cl and cl > _MAX_BODY_SIZE:
            return jsonify({"error": "请求体过大"}), 413


@app.before_request
def auth_check():
    client_ip = request.remote_addr or 'unknown'
    if not _check_rate_limit(client_ip):
        return jsonify({"error": "请求过于频繁"}), 429
    if _is_public_path(request.path) or request.method == "OPTIONS":
        return None
    if not _check_auth_fail_limit(client_ip):
        return jsonify({"error": "鉴权失败次数过多，请15分钟后重试"}), 429
    if not check_token(request):
        _record_auth_fail(client_ip)
        return jsonify({"error": "未授权访问，请通过客户端操作"}), 401


# ── Graceful Shutdown ──

def _signal_handler(signum, frame):
    logger.info("收到关闭信号，正在保存数据...")
    shutdown_event.set()
    if deps.collector:
        deps.collector.stop()

import signal
try:
    signal.signal(signal.SIGTERM, _signal_handler)
except (OSError, ValueError):
    pass


# ── 注册所有蓝图 ──

for bp in ALL_BLUEPRINTS:
    app.register_blueprint(bp)


# P0-05: 500 错误统一脱敏，避免堆栈信息泄露
@app.errorhandler(500)
def handle_500(e):
    trace_id = str(uuid.uuid4())[:8]
    logger.error(f"[trace:{trace_id}] Internal error: {e}", exc_info=True)
    return jsonify({"error": "服务器内部错误", "trace_id": trace_id}), 500


@app.errorhandler(Exception)
def handle_unexpected(e):
    trace_id = str(uuid.uuid4())[:8]
    logger.error(f"[trace:{trace_id}] Unexpected error: {e}", exc_info=True)
    if isinstance(e, HTTPException):
        return e
    return jsonify({"error": "服务器内部错误", "trace_id": trace_id}), 500


# ── Backward-compatible module attributes for main.py ──

def __getattr__(name):
    import routes.deps as deps
    if name == "_collector_paused":
        return deps.collector_paused
    if name == "_shutdown_event":
        return deps.shutdown_event
    if name == "check_auto_report":
        from routes.auto_report import check_auto_report as _check
        return _check
    raise AttributeError(f"module 'server' has no attribute {name!r}")


# ── 启动 ──

def start_server():
    install_log_redaction()  # P0-06: 安装日志脱敏过滤器
    save_token()
    logger.info(f"API Token 已生成: {TOKEN_PATH}")

    # 生产级 WSGI 服务器：waitress（比 Flask 内置服务器更稳定）
    # 参考：https://docs.pylonsproject.org/projects/waitress/en/stable/
    try:
        from waitress import serve as waitress_serve
        logger.info(f"使用 waitress 生产级 WSGI 服务器启动: http://127.0.0.1:{HTTP_PORT}")
        # waitress 的启动消息输出到 stderr，Electron 的 stdout 解析器无法捕获
        # 主动向 stdout 打印可识别的启动标记，让 Electron 立即知道后端已就绪
        print(f"HTTP API 已启动: http://127.0.0.1:{HTTP_PORT}", flush=True)
        # 4线程 + 增大队列：前端多个组件同时轮询时避免4092次"Task queue depth"警告
        # waitress 正确参数名: channel_request_lookahead (不是lookaback也不是lookback)
        # 增大backlog和connection_limit，避免请求被reject导致前端触发"后端断开"
        waitress_serve(
            app,
            host="127.0.0.1",
            port=HTTP_PORT,
            threads=4,
            connection_limit=100,       # 默认100，保持
            channel_request_lookahead=50,  # 默认4，正确拼写: lookahead
            channel_timeout=30,         # 空闲连接保持30秒（默认120秒过长，桌面应用无需）
            cleanup_interval=15,        # 每15秒清理过期空闲连接（默认30秒）
            max_request_body_size=10 * 1024 * 1024,  # 10MB，支持大请求体
        )
    except ImportError:
        logger.warning("waitress 未安装，回退到 Flask 开发服务器（本地场景可用）")
        # 本地桌面应用场景：Flask 开发服务器足够稳定
        # 关闭 reloader 和 debug 模式，避免双进程和内存泄漏
        app.run(
            host="127.0.0.1",
            port=HTTP_PORT,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
