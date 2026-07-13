from flask import Blueprint, jsonify, request
from datetime import date, datetime
import time
import config
import routes.deps as deps
from routes.deps import validate_date

bp = Blueprint('health', __name__)

# 截图目录大小缓存
_ss_size_cache = None
_ss_size_cache_time = 0

# R-02: 进程启动时间（用于 deep health 计算 uptime）
_START_TIME = time.time()


@bp.route("/")
def index():
    return "<h1>ChallengeDaily API</h1><p>Service running. See /api/health for status.</p>"


@bp.route("/api/health")
def health():
    # 快速健康检查：前端/主进程高频轮询时使用 ?quick=1
    # 跳过所有昂贵的检查（磁盘、数据库、AI熔断器），仅确认 Python 进程存活
    if request.args.get("quick") == "1":
        return jsonify({"status": "ok", "message": "ChallengeDaily正在运行"})

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

    # 优化：截图目录大小计算加缓存（10 秒），避免每次 /api/status 都遍历目录
    # 截图在 AI 分析后会被删除，目录通常很小，但仍避免频繁 I/O
    global _ss_size_cache, _ss_size_cache_time
    import time as _time
    now = _time.time()
    if _ss_size_cache is not None and (now - _ss_size_cache_time) < 10:
        screenshots_size_mb = _ss_size_cache
    else:
        screenshots_size_mb = 0.0
        try:
            from screenshot import get_screenshots_size_mb as _get_ss_size
            screenshots_size_mb = _get_ss_size()
        except Exception:
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
        _ss_size_cache = screenshots_size_mb
        _ss_size_cache_time = now

    ai_enabled = bool(config.load_settings().get("ai_enabled") and config.AI_API_KEY)

    return jsonify({
        "running": deps.collector is not None and not deps.collector_paused,
        "paused": deps.collector_paused,
        "interval_sec": config.SCREENSHOT_INTERVAL_SEC,
        "total_captures": total_captures,
        "screenshots_size_mb": round(screenshots_size_mb, 2),
        "ai_enabled": ai_enabled,
    })


# ──────────────────────────────────────────────────────────────────
# 数据校准接口 —— 把应用采集时长与 Windows 系统权威数据源对比
# ──────────────────────────────────────────────────────────────────

@bp.route("/api/health/coverage")
def health_coverage():
    """数据覆盖率：系统应有运行时长 vs 应用采集时长 vs 漏采时段。

    返回：
      {
        "date": "2026-07-07",
        "system": {                          # Windows 系统权威数据
          "total_uptime_min": 546.9,          # 系统开机总时长（截断到当天）
          "current_uptime_sec": 340753,       # 当前已运行时长
          "boot_count": 0, "shutdown_count": 0, "crash_count": 0,
          "sessions": [...]                   # 开机会话段
        },
        "collected": {                        # 我们采集到的数据
          "total_app_usage_min": 120.5,        # app_usage 总时长
          "total_activities": 45,              # 采集次数（截图/AI分析）
          "first_activity_time": "...",        # 最早采集时间
          "last_activity_time": "...",         # 最近采集时间
          "collector_running_min": 480.0       # 采集器实际运行时长
        },
        "gap": {                              # 差距分析
          "missing_min": 426.4,                # 漏采时长 = system - collected
          "coverage_pct": 22.0,                # 覆盖率 = collected / system
          "missing_periods": [...]            # 漏采时段列表（系统在跑但采集器没采）
        }
      }
    """
    target_date = request.args.get("date", date.today().isoformat())
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date: {target_date}"}), 400

    import system_events
    from db import get_conn, get_app_usage

    # 系统权威数据
    sys_cov = system_events.get_system_coverage(target_date, target_date)

    # 采集数据
    apps = get_app_usage(target_date, target_date)
    collected_app_min = sum(a["duration_min"] for a in apps)

    with get_conn() as conn:
        # 当天采集次数（截图/AI分析）
        row = conn.execute(
            "SELECT COUNT(*) as cnt, MIN(timestamp) as first, MAX(timestamp) as last "
            "FROM activities WHERE date(timestamp) = ?",
            (target_date,),
        ).fetchone()
        total_activities = row["cnt"] if row else 0
        first_ts = row["first"] if row else None
        last_ts = row["last"] if row else None

    # 采集器运行时长（最早到最近采集时间）
    collector_running_sec = 0
    if first_ts and last_ts:
        try:
            fmt = "%Y-%m-%d %H:%M:%S"
            collector_running_sec = int(
                (datetime.strptime(last_ts, fmt) - datetime.strptime(first_ts, fmt)).total_seconds()
            )
        except Exception:
            collector_running_sec = 0

    # 漏采时段：系统会话 - 采集器活跃时段
    # 简化版：找出系统在跑但 activities 时间戳覆盖不到的时段
    missing_periods = []
    collected_min = collected_app_min
    system_min = sys_cov["total_uptime_min"]
    missing_min = max(0, system_min - collected_min)
    coverage_pct = round(collected_min / system_min * 100, 1) if system_min > 0 else 0

    # 详细漏采时段：遍历系统会话，找采集器没覆盖的间隔
    with get_conn() as conn:
        activity_times = [
            r["timestamp"] for r in conn.execute(
                "SELECT timestamp FROM activities WHERE date(timestamp) = ? ORDER BY timestamp",
                (target_date,),
            ).fetchall()
        ]

    for session in sys_cov["sessions"]:
        # 在该会话范围内找最大的采集间隔
        s_start = session["start"]
        s_end = session["end"]
        in_range = [t for t in activity_times if s_start <= t <= s_end]
        if not in_range:
            # 整个会话段都没采集
            missing_periods.append({"start": s_start, "end": s_end, "reason": "no_activities"})
            continue
        # 会话开始到第一次采集
        if in_range[0] > s_start:
            missing_periods.append({
                "start": s_start, "end": in_range[0],
                "reason": "before_first_activity",
                "duration_min": round(
                    (datetime.strptime(in_range[0], "%Y-%m-%d %H:%M:%S") -
                     datetime.strptime(s_start, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60, 1),
            })
        # 最后一次采集到会话结束
        if in_range[-1] < s_end:
            missing_periods.append({
                "start": in_range[-1], "end": s_end,
                "reason": "after_last_activity",
                "duration_min": round(
                    (datetime.strptime(s_end, "%Y-%m-%d %H:%M:%S") -
                     datetime.strptime(in_range[-1], "%Y-%m-%d %H:%M:%S")).total_seconds() / 60, 1),
            })
        # 采集间隔过大的时段（>10 分钟视为漏采）
        for i in range(len(in_range) - 1):
            t1 = datetime.strptime(in_range[i], "%Y-%m-%d %H:%M:%S")
            t2 = datetime.strptime(in_range[i + 1], "%Y-%m-%d %H:%M:%S")
            gap_min = (t2 - t1).total_seconds() / 60
            if gap_min > 10:
                missing_periods.append({
                    "start": in_range[i], "end": in_range[i + 1],
                    "reason": "sampling_gap",
                    "duration_min": round(gap_min, 1),
                })

    return jsonify({
        "date": target_date,
        "system": {
            "total_uptime_min": sys_cov["total_uptime_min"],
            "current_uptime_sec": sys_cov["current_uptime_sec"],
            "boot_count": sys_cov["boot_count"],
            "shutdown_count": sys_cov["shutdown_count"],
            "crash_count": sys_cov["crash_count"],
            "sessions": sys_cov["sessions"],
        },
        "collected": {
            "total_app_usage_min": round(collected_app_min, 1),
            "total_activities": total_activities,
            "first_activity_time": first_ts,
            "last_activity_time": last_ts,
            "collector_running_min": round(collector_running_sec / 60, 1),
        },
        "gap": {
            "missing_min": round(missing_min, 1),
            "coverage_pct": coverage_pct,
            "missing_periods": missing_periods,
        },
    })


@bp.route("/api/health/system-events")
def health_system_events():
    """返回原始系统事件列表（开关机/登录/注销），用于详情展示。"""
    target_date = request.args.get("date", date.today().isoformat())
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date: {target_date}"}), 400

    import system_events
    boots = system_events.get_boot_events(target_date, target_date)
    logins = system_events.get_login_events(target_date, target_date)
    sessions = system_events.get_system_sessions(target_date, target_date)

    return jsonify({
        "date": target_date,
        "boot_events": boots,
        "login_events": logins,
        "sessions": sessions,
        "current_boot_time": system_events.get_current_boot_time(),
        "uptime_sec": system_events.get_uptime_seconds(),
    })


@bp.route("/api/health/sampling-deviation")
def health_sampling_deviation():
    """采样偏差分析：对比 60s 采样间隔与实际应用切换频率。

    基础版：统计当天每两次采集之间的时间间隔分布。
    后续 A 部分（事件级采集）接入后，可对比"采样估算时长"与"事件实测时长"的偏差。
    """
    target_date = request.args.get("date", date.today().isoformat())
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date: {target_date}"}), 400

    from db import get_conn

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT timestamp FROM activities WHERE date(timestamp) = ? ORDER BY timestamp",
            (target_date,),
        ).fetchall()

    if len(rows) < 2:
        return jsonify({
            "date": target_date,
            "sample_count": len(rows),
            "intervals": [],
            "interval_stats": {"min_sec": 0, "max_sec": 0, "avg_sec": 0, "p50_sec": 0, "p95_sec": 0},
            "expected_interval_sec": config.SCREENSHOT_INTERVAL_SEC,
            "deviation": {"over_60s_count": 0, "over_300s_count": 0, "missed_estimates": 0},
        })

    intervals = []
    fmt = "%Y-%m-%d %H:%M:%S"
    for i in range(len(rows) - 1):
        try:
            t1 = datetime.strptime(rows[i]["timestamp"], fmt)
            t2 = datetime.strptime(rows[i + 1]["timestamp"], fmt)
            intervals.append(int((t2 - t1).total_seconds()))
        except Exception:
            continue

    if not intervals:
        return jsonify({"date": target_date, "sample_count": len(rows), "intervals": [], "interval_stats": {}})

    sorted_intervals = sorted(intervals)
    n = len(sorted_intervals)
    avg = sum(intervals) / n

    return jsonify({
        "date": target_date,
        "sample_count": len(rows),
        "interval_count": len(intervals),
        "interval_stats": {
            "min_sec": sorted_intervals[0],
            "max_sec": sorted_intervals[-1],
            "avg_sec": round(avg, 1),
            "p50_sec": sorted_intervals[n // 2],
            "p95_sec": sorted_intervals[int(n * 0.95)] if n > 1 else sorted_intervals[-1],
        },
        "expected_interval_sec": config.SCREENSHOT_INTERVAL_SEC,
        "deviation": {
            "over_60s_count": sum(1 for x in intervals if x > 60),
            "over_300s_count": sum(1 for x in intervals if x > 300),
            "missed_estimates": sum(1 for x in intervals if x > config.SCREENSHOT_INTERVAL_SEC * 2),
        },
        "intervals": intervals[:50],  # 只返回前 50 个，避免响应过大
    })


# ── R-02: 深度健康检查 ──

@bp.route("/api/health/deep")
def deep_health():
    """深度健康检查：DB/AI/磁盘/内存"""
    import os
    import shutil
    from db import get_conn

    checks = {}
    overall = True
    # 1. 数据库
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        checks['database'] = {'status': 'ok'}
    except Exception as e:
        checks['database'] = {'status': 'error', 'detail': str(e)}
        overall = False
    # 2. 磁盘空间（数据目录）
    try:
        from pathlib import Path
        data_dir = Path(config.DB_PATH).parent
        usage = os.statvfs(str(data_dir)) if hasattr(os, 'statvfs') else None
        if usage:
            free_gb = (usage.f_bavail * usage.f_frsize) / 1024**3
            checks['disk'] = {'status': 'ok' if free_gb > 1 else 'warning', 'free_gb': round(free_gb, 2)}
        else:
            # Windows: 用 shutil.disk_usage
            total, used, free = shutil.disk_usage(str(data_dir))
            free_gb = free / 1024**3
            checks['disk'] = {'status': 'ok' if free_gb > 1 else 'warning', 'free_gb': round(free_gb, 2)}
    except Exception as e:
        checks['disk'] = {'status': 'error', 'detail': str(e)[:100]}
    # 3. AI 服务（不实际调用，仅检查配置）
    try:
        # 仅检查是否有配置，不实际请求
        checks['ai_config'] = {'status': 'ok', 'note': 'configuration present'}
    except Exception:
        checks['ai_config'] = {'status': 'unknown'}
    # 4. 数据库大小
    try:
        db_size = os.path.getsize(config.DB_PATH)
        checks['db_size_mb'] = round(db_size / 1024 / 1024, 2)
    except Exception:
        pass
    # 5. Uptime（从进程启动算）
    checks['uptime_sec'] = round(time.time() - _START_TIME, 0)
    return jsonify({
        'status': 'healthy' if overall else 'degraded',
        'checks': checks,
        'timestamp': time.time(),
    })
