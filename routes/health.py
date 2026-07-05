from flask import Blueprint, jsonify
import config
import routes.deps as deps

bp = Blueprint('health', __name__)


@bp.route("/")
def index():
    return "<h1>ChallengeDaily API</h1><p>Service running. See /api/health for status.</p>"


@bp.route("/api/health")
def health():
    import shutil
    from ai_client import get_circuit_breaker_status

    cb = get_circuit_breaker_status()

    disk_usage = shutil.disk_usage(str(config.BASE_DIR))
    disk_free_gb = round(disk_usage.free / (1024 ** 3), 2)

    db_ok = True
    try:
        from db import get_conn
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:
        db_ok = False

    ai_status = "disabled"
    if config.AI_API_KEY:
        if cb["state"] == "closed":
            ai_status = "available"
        elif cb["state"] == "half_open":
            ai_status = "degraded"
        else:
            ai_status = "circuit_open"

    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "message": "ChallengeDaily正在运行",
        "ai_circuit_breaker": cb,
        "ai_status": ai_status,
        "disk_free_gb": disk_free_gb,
        "db_ok": db_ok,
    })


@bp.route("/api/status")
def status():
    import os
    from db import get_conn

    with get_conn() as conn:
        total_captures = conn.execute("SELECT COUNT(*) as cnt FROM activities").fetchone()["cnt"]

    screenshots_size_mb = 0.0
    # 使用 screenshot 模块的标准方法，避免路径拼接错误
    try:
        from screenshot import get_screenshots_size_mb as _get_ss_size
        screenshots_size_mb = _get_ss_size()
    except Exception:
        # 回退：使用 config.SCREENSHOT_DIR
        ss_dir = str(config.SCREENSHOT_DIR)
        if os.path.isdir(ss_dir):
            for f in os.listdir(ss_dir):
                fp = os.path.join(ss_dir, f)
                if os.path.isfile(fp):
                    try:
                        screenshots_size_mb += os.path.getsize(fp)
                    except OSError:
                        pass
            screenshots_size_mb = screenshots_size_mb / (1024 * 1024)

    ai_enabled = bool(config.AI_API_KEY)

    return jsonify({
        "running": deps.collector is not None and not deps.collector_paused,
        "paused": deps.collector_paused,
        "interval_sec": config.SCREENSHOT_INTERVAL_SEC,
        "total_captures": total_captures,
        "screenshots_size_mb": round(screenshots_size_mb, 2),
        "ai_enabled": ai_enabled,
    })
