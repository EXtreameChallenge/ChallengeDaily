"""
ChallengeDaily Windows 版 — Flask HTTP API
企业级：token 鉴权、graceful shutdown、数据导出、AI 测试
"""
import logging

from flask import Flask, jsonify, request

from config import HTTP_PORT
from routes.deps import shutdown_event, check_token, save_token, TOKEN_PATH
import routes.deps as deps
from routes import ALL_BLUEPRINTS

logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── CORS ──

_ALLOWED_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "null",
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
        # 非浏览器请求（如 Electron ipcRenderer），允许
        response.headers["Access-Control-Allow-Origin"] = "*"
    # 未知 origin 不设置 CORS 头，浏览器会自动拒绝跨域请求
    return response


# ── 注入 collector ──

def set_collector(collector_instance):
    """注入主采集器实例，供 API 路由使用"""
    import routes.deps as deps
    deps.collector = collector_instance


# ── 鉴权中间件 ──

_PUBLIC_PATHS = {"/", "/api/health"}

@app.before_request
def auth_check():
    if request.path in _PUBLIC_PATHS or request.method == "OPTIONS":
        return None
    if not check_token(request):
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
    save_token()
    logger.info(f"API Token 已生成: {TOKEN_PATH}")
    app.run(host="127.0.0.1", port=HTTP_PORT, debug=False, threaded=True)
