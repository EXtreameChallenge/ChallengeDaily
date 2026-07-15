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
from observability import generate_trace_id, set_trace_id, get_trace_id, record_request, get_metrics, setup_structured_logging

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

_PUBLIC_PATHS = {"/", "/api/health", "/api/metrics"}
_PUBLIC_PREFIXES = ["/api/icons/"]
# SSE 端点：不能通过 header 传 token，改用 query param ?token=xxx，在 handler 内自行校验
_SSE_PATHS = {"/api/events/stream"}


def _is_public_path(path: str) -> bool:
    """判断请求路径是否为公开接口"""
    if path in _PUBLIC_PATHS:
        return True
    for prefix in _PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _is_sse_path(path: str) -> bool:
    """SSE 路径：跳过常规 header token 校验，改用 query param"""
    return path in _SSE_PATHS


# P0-04: Rate Limiting（内存实现，单进程足够），防暴力枚举 token
# 注意：本地桌面应用场景下，前端启动时会并发发起几十个请求（diaries/settings/status/ai-chat 等），
# 若限制过严会触发 429 雪崩（前端重试→更多请求→更多 429）。
# 因此对 localhost 豁免 rate limit（已有 token 鉴权 + auth_fail 锁定兜底安全），
# 仅对非 localhost IP 保留 rate limit，防止外部暴力枚举。
_RATE_LIMIT_WINDOW = 60      # 60秒窗口
_RATE_LIMIT_MAX = 300        # 每IP每窗口300次（对外部IP，localhost豁免）
_AUTH_FAIL_LIMIT = 5         # 鉴权失败5次锁定
_AUTH_FAIL_LOCK_SEC = 900    # 锁定15分钟
_rate_limit_store = defaultdict(list)   # ip -> [timestamps]
_auth_fail_store = defaultdict(list)    # ip -> [fail timestamps]


def _is_localhost(ip: str) -> bool:
    """判断是否为本机回环地址（本地桌面应用，豁免 rate limit）"""
    return ip in ('127.0.0.1', '::1', 'localhost', 'unknown')


def _check_rate_limit(ip: str) -> bool:
    # localhost 豁免：本地桌面应用已有 token 鉴权，无需 rate limit
    if _is_localhost(ip):
        return True
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
def add_trace_id():
    import time as _time
    request._start_time = _time.time()
    trace_id = request.headers.get('X-Request-ID') or generate_trace_id()
    set_trace_id(trace_id)


@app.after_request
def record_metrics(response):
    endpoint = request.endpoint or request.path
    duration = getattr(request, '_start_time', None)
    if duration:
        import time as _time
        record_request(endpoint, _time.time() - duration, error=response.status_code >= 500)
    response.headers['X-Request-ID'] = get_trace_id()
    return response


@app.before_request
def auth_check():
    client_ip = request.remote_addr or 'unknown'
    if not _check_rate_limit(client_ip):
        return jsonify({"error": "请求过于频繁"}), 429
    if _is_public_path(request.path) or request.method == "OPTIONS":
        return None
    # SSE 端点：跳过 header token 校验（在 handler 内用 query param 校验）
    if _is_sse_path(request.path):
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
    setup_structured_logging(json_output=False)  # O-01: 结构化日志（先保持文本格式，避免破坏现有日志解析）
    install_log_redaction()  # P0-06: 安装日志脱敏过滤器
    save_token()
    logger.info(f"API Token 已生成: {TOKEN_PATH}")

    # 本地桌面应用场景：使用 Flask 内置 threaded 服务器
    # 原因：waitress 不支持 SSE 流式响应（/api/events/stream），会返回 500
    # Flask threaded 服务器支持 streaming generator，且对单用户桌面应用足够稳定
    # 参考：项目约束"本地桌面应用场景：Flask 开发服务器足够稳定"
    logger.info(f"使用 Flask threaded 服务器启动: http://127.0.0.1:{HTTP_PORT}")
    print(f"HTTP API 已启动: http://127.0.0.1:{HTTP_PORT}", flush=True)
    app.run(
        host="127.0.0.1",
        port=HTTP_PORT,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


# ── O-02: 指标端点 ──

@app.route('/api/metrics')
def metrics_endpoint():
    from observability import get_metrics
    return jsonify(get_metrics())


# ── P10-2：健康检查端点 ──

@app.route('/api/health')
def health_check():
    """系统健康检查（供监控/自动重启使用）

    返回各子系统状态：数据库 / AI / 采集 / 重试队列 / 磁盘
    status: ok / degraded / down
    """
    import os
    import shutil
    from datetime import datetime
    checks = {}
    overall = "ok"

    # 1. 数据库
    try:
        import db
        with db.get_conn() as conn:
            cnt = conn.execute("SELECT COUNT(*) AS c FROM activities").fetchone()
        checks["database"] = {"status": "ok", "activities": cnt["c"] if cnt else 0}
    except Exception as e:
        checks["database"] = {"status": "down", "error": str(e)[:80]}
        overall = "down"

    # 2. AI 在线状态
    try:
        from offline_ai import is_online, get_queue_size
        checks["ai"] = {"status": "online" if is_online() else "offline", "queue_size": get_queue_size()}
        if not is_online():
            overall = "degraded" if overall == "ok" else overall
    except Exception as e:
        checks["ai"] = {"status": "unknown", "error": str(e)[:80]}

    # 3. 采集器状态（通过最近活动时间判断）
    try:
        import db
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT MAX(timestamp) AS latest FROM activities"
            ).fetchone()
        latest = row["latest"] if row and row["latest"] else None
        stale = True
        if latest:
            try:
                latest_dt = datetime.strptime(latest, "%Y-%m-%d %H:%M:%S")
                # 10 分钟内有采集视为正常
                stale = (datetime.now() - latest_dt).total_seconds() > 600
            except Exception:
                pass
        checks["collector"] = {"status": "stale" if stale else "ok", "last_activity": latest}
        if stale:
            overall = "degraded" if overall == "ok" else overall
    except Exception as e:
        checks["collector"] = {"status": "unknown", "error": str(e)[:80]}

    # 4. 磁盘
    try:
        from config import DATA_DIR
        usage = shutil.disk_usage(str(DATA_DIR))
        free_pct = (usage.free / usage.total) * 100
        checks["disk"] = {
            "status": "ok" if free_pct > 10 else "warn",
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "free_pct": round(free_pct, 1),
        }
        if free_pct < 10:
            overall = "degraded" if overall == "ok" else overall
    except Exception as e:
        checks["disk"] = {"status": "unknown", "error": str(e)[:80]}

    # 5. P11-4：进程内存
    try:
        from collector import _get_process_rss_mb
        rss = _get_process_rss_mb()
        checks["memory"] = {
            "status": "ok" if rss < 400 else ("warn" if rss < 600 else "critical"),
            "rss_mb": round(rss, 1),
        }
        if rss >= 600:
            overall = "degraded" if overall == "ok" else overall
    except Exception as e:
        checks["memory"] = {"status": "unknown", "error": str(e)[:80]}

    # 6. P11-3：审计日志统计
    try:
        from audit_logger import get_audit_stats
        audit_stats = get_audit_stats()
        checks["audit"] = {
            "status": "ok",
            "total_logs": audit_stats.get("total", 0),
            "recent_24h_failures": audit_stats.get("recent_24h_failures", 0),
        }
    except Exception as e:
        checks["audit"] = {"status": "unknown", "error": str(e)[:80]}

    return jsonify({
        "status": overall,
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "checks": checks,
    })


# ── SSE 事件流 ──

@app.route('/api/events/stream')
def event_stream():
    """SSE 事件流（token 通过 query param ?token=xxx 传递）

    返回 text/event-stream，每 30s 发送心跳防止连接超时。
    """
    import hmac
    from flask import Response
    from event_bus import subscribe, unsubscribe
    from routes.deps import LOCAL_TOKEN

    # 校验 query param token
    token = request.args.get('token', '')
    if not hmac.compare_digest(token, LOCAL_TOKEN):
        return jsonify({"error": "未授权访问"}), 401

    q = subscribe()

    def generate():
        import json as _json
        import queue as _queue
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"
                except _queue.Empty:
                    # 心跳，防止连接超时
                    yield ": ping\n\n"
        finally:
            unsubscribe(q)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        },
    )
