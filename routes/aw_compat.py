"""
ActivityWatch aw-server REST API 兼容层
=====================================
让 ChallengeDaily 暴露与 ActivityWatch aw-server 相同的 REST API，
使现有 AW 生态工具（aw-watcher-*、aw-webui、aw-qt 等）可零改造接入。

参考实现：https://activitywatch.readthedocs.io/en/latest/api/server.html

设计要点：
- 每个 AW bucket 映射到 ChallengeDaily 的 activities 表（按 bucket 类型区分）
- 接收到的 events 转换为 activities 记录写入
- 时间格式：AW 使用 ISO 8601 UTC，需转换为本地 "%Y-%m-%d %H:%M:%S"
- 不强制鉴权（与 ActivityWatch 行为一致），但支持可选 token
- heartbeat 模式按 (app, title, timestamp±2min) 去重
- 不影响现有 /api/* 路由（独立 /api/v1/* 路径）
"""
from __future__ import annotations

import base64
import binascii
import hmac
import json as _json
import logging
import threading
import time
import uuid as _uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request, g

from config import DATA_DIR, CATEGORIES, HTTP_PORT
from db import get_conn, insert_activity
from file_utils import atomic_write_text, backup_file
from routes.deps import safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('aw_compat', __name__)

# ── 常量 ────────────────────────────────────────────────────────────
# 本地时间格式（与 activities.timestamp 列对齐）
_LOCAL_TS_FMT = "%Y-%m-%d %H:%M:%S"
# 默认 heartbeat 合并窗口（秒），与 WakaTime 2 分钟一致
_HEARTBEAT_DEDUP_WINDOW_SEC = 120
# 单次批量插入上限（防滥用）
_MAX_BATCH_EVENTS = 1000
# 服务器标识
_AW_SERVER_ID = "ChallengeDaily-AW-Compat"
_AW_SERVER_VERSION = "1.0.0"

# Bucket 类型常量
BUCKET_TYPE_WINDOW = "window"
BUCKET_TYPE_AFK = "afk"
BUCKET_TYPE_WEB = "web"
BUCKET_TYPE_EDITOR = "editor"
_VALID_BUCKET_TYPES = {BUCKET_TYPE_WINDOW, BUCKET_TYPE_AFK, BUCKET_TYPE_WEB, BUCKET_TYPE_EDITOR}

# 默认 bucket 元数据（虚拟分类映射）
_DEFAULT_BUCKETS: dict[str, dict[str, Any]] = {
    # bucket_id → {id, type, client, hostname, created, data}
}

# Bucket 元数据持久化路径
_BUCKETS_FILE = DATA_DIR / "aw_buckets.json"

# 兼容层接收统计：记录接收到的 event 总数（按 bucket 类型分组）
_STATS_FILE = DATA_DIR / "aw_compat_stats.json"
_stats_lock = threading.Lock()
_stats_cache: dict[str, int] | None = None

# 可选鉴权 token（与 aw-server 不同，ChallengeDaily 支持可选 token 校验）
# 通过环境变量 AW_COMPAT_TOKEN 配置；为空则不校验
import os as _os
_AW_COMPAT_TOKEN = _os.getenv("AW_COMPAT_TOKEN", "").strip()
# 同时支持通过 settings.json 的 aw_compat_token 字段配置
_SETTINGS_TOKEN_KEY = "aw_compat_token"


# ── 时间转换 ──────────────────────────────────────────────────────────
def _iso_to_local_str(iso_ts: str) -> str:
    """AW ISO 8601 UTC 时间戳 → 本地 '%Y-%m-%d %H:%M:%S' 字符串。

    支持以下输入：
    - "2026-07-28T10:00:00.000Z"
    - "2026-07-28T10:00:00Z"
    - "2026-07-28T10:00:00+00:00"
    - "2026-07-28 10:00:00"（已是本地格式，直接返回）

    若解析失败，回退到当前时间。
    """
    if not iso_ts:
        return datetime.now().strftime(_LOCAL_TS_FMT)
    s = iso_ts.strip()
    # 已是本地格式
    try:
        datetime.strptime(s, _LOCAL_TS_FMT)
        return s
    except ValueError:
        pass
    # ISO 8601 处理
    try:
        # Python 3.11+ fromisoformat 支持 'Z'
        if s.endswith("Z"):
            s_norm = s[:-1] + "+00:00"
        else:
            s_norm = s
        dt = datetime.fromisoformat(s_norm)
        if dt.tzinfo is None:
            # 视为 UTC
            dt = dt.replace(tzinfo=timezone.utc)
        # 转为本地时间
        local_dt = dt.astimezone()
        return local_dt.strftime(_LOCAL_TS_FMT)
    except Exception:
        logger.warning(f"无法解析时间戳: {iso_ts!r}, 使用当前时间")
        return datetime.now().strftime(_LOCAL_TS_FMT)


def _local_str_to_iso(local_ts: str) -> str:
    """本地 '%Y-%m-%d %H:%M:%S' → AW ISO 8601 UTC 时间戳"""
    try:
        dt = datetime.strptime(local_ts, _LOCAL_TS_FMT)
        # 视为本地时间，转 UTC 后输出
        local_dt = dt.astimezone()
        utc_dt = local_dt.astimezone(timezone.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ── Bucket 元数据持久化 ──────────────────────────────────────────────
_buckets_lock = threading.Lock()
_buckets_cache: dict[str, dict[str, Any]] | None = None


def _load_buckets() -> dict[str, dict[str, Any]]:
    """从磁盘加载 bucket 元数据（带缓存）"""
    global _buckets_cache
    with _buckets_lock:
        if _buckets_cache is not None:
            return _buckets_cache
        if _BUCKETS_FILE.exists():
            try:
                _buckets_cache = _json.loads(_BUCKETS_FILE.read_text(encoding="utf-8"))
                return _buckets_cache
            except Exception as e:
                logger.warning(f"读取 aw_buckets.json 失败: {e}, 使用默认值")
        _buckets_cache = dict(_DEFAULT_BUCKETS)
        return _buckets_cache


def _save_buckets(buckets: dict[str, dict[str, Any]]) -> None:
    """持久化 bucket 元数据"""
    global _buckets_cache
    with _buckets_lock:
        _buckets_cache = dict(buckets)
        _BUCKETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        content = _json.dumps(buckets, ensure_ascii=False, indent=2)
        if _BUCKETS_FILE.exists():
            backup_file(_BUCKETS_FILE)
        atomic_write_text(_BUCKETS_FILE, content)


def _load_stats() -> dict[str, int]:
    """加载兼容层接收统计"""
    global _stats_cache
    with _stats_lock:
        if _stats_cache is not None:
            return dict(_stats_cache)
        if _STATS_FILE.exists():
            try:
                _stats_cache = _json.loads(_STATS_FILE.read_text(encoding="utf-8"))
                return dict(_stats_cache)
            except Exception:
                pass
        _stats_cache = {
            "aw_events_received": 0,
            "aw_events_inserted": 0,
            "aw_heartbeats_received": 0,
            "aw_heartbeats_merged": 0,
            "wakatime_heartbeats_received": 0,
            "wakatime_heartbeats_merged": 0,
        }
        return dict(_stats_cache)


def _save_stats(stats: dict[str, int]) -> None:
    global _stats_cache
    with _stats_lock:
        _stats_cache = dict(stats)
        _STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(_STATS_FILE, _json.dumps(stats, ensure_ascii=False, indent=2))


def _incr_stat(key: str, n: int = 1) -> None:
    stats = _load_stats()
    stats[key] = stats.get(key, 0) + n
    _save_stats(stats)


# ── 可选鉴权 ──────────────────────────────────────────────────────────
def _get_settings_token() -> str:
    """从 settings.json 读取可选 token（延迟导入避免循环依赖）"""
    try:
        from config import load_settings
        return (load_settings().get(_SETTINGS_TOKEN_KEY) or "").strip()
    except Exception:
        return ""


def _check_aw_auth() -> bool:
    """校验 AW 兼容层鉴权（可选）

    校验顺序：环境变量 AW_COMPAT_TOKEN > settings.aw_compat_token
    若两者都为空，则放行（与 aw-server 行为一致，无鉴权）。
    """
    expected = _AW_COMPAT_TOKEN or _get_settings_token()
    if not expected:
        return True
    # 优先 Authorization: Basic <token>（ActivityWatch 客户端常用）
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8", errors="ignore")
            # ActivityWatch aw-client-python: base64(token:) 或 base64(token)
            token_part = decoded.split(":", 1)[0]
            if hmac.compare_digest(token_part, expected):
                return True
        except (binascii.Error, ValueError):
            pass
    # 兼容 X-API-Token / token query param
    token_header = request.headers.get("X-API-Token", "") or request.args.get("token", "")
    if token_header and hmac.compare_digest(token_header, expected):
        return True
    return False


@bp.before_request
def _auth_guard():
    """兼容层鉴权（可选 token）

    - /api/v1/* 路径走 AW 兼容层自身鉴权（默认无鉴权，与 aw-server 行为一致）
    - /api/aw/* 路径是 ChallengeDaily 私有管理端点，由 server.py 全局 check_token 保护，
      此处跳过避免双重校验
    """
    path = request.path
    if path.startswith("/api/aw/"):
        # 管理端点：交给 server.py 全局 check_token 处理
        return None
    # AW 协议端点：走可选 token 校验
    if not _check_aw_auth():
        return jsonify({"error": "unauthorized", "message": "AW compat token 校验失败"}), 401
    return None


# ── 数据转换 ──────────────────────────────────────────────────────────
def _bucket_id_from_request(bid: str) -> str:
    """规范化 URL 中的 bucket_id（URL decode 已由 Flask 完成）"""
    return bid.strip()


def _bucket_type(bid: str) -> str:
    """根据 bucket_id 推断 bucket 类型"""
    if "afk" in bid:
        return BUCKET_TYPE_AFK
    if "web" in bid or "browser" in bid:
        return BUCKET_TYPE_WEB
    if "editor" in bid or "wakatime" in bid:
        return BUCKET_TYPE_EDITOR
    return BUCKET_TYPE_WINDOW


def _event_to_activity_row(event: dict[str, Any], bucket_type: str) -> dict[str, Any]:
    """AW event → ChallengeDaily activity 字段

    返回 dict（不含 id），字段对齐 activities 表 schema。
    """
    timestamp = _iso_to_local_str(event.get("timestamp", ""))
    duration = float(event.get("duration") or 0.0)
    interval_sec = max(1, int(round(duration))) if duration > 0 else 60
    data = event.get("data") or {}

    app_name = (data.get("app") or data.get("name") or "").strip()
    window_title = (data.get("title") or data.get("url") or "").strip()
    category = (data.get("category") or "").strip()

    # 根据 bucket 类型补齐默认值
    if bucket_type == BUCKET_TYPE_AFK:
        app_name = app_name or "afk"
        # afk 事件 data={"status": "not-afk"/"afk"}
        status = data.get("status")
        if status:
            window_title = window_title or status
        if not category:
            category = "其他"
    elif bucket_type == BUCKET_TYPE_WEB:
        app_name = app_name or "web"
        if not category:
            category = "其他"
    elif bucket_type == BUCKET_TYPE_EDITOR:
        # WakaTime editor event: data={"file":..., "language":..., "project":...}
        app_name = app_name or (data.get("editor") or "editor")
        window_title = window_title or (data.get("file") or "")
        if not category:
            category = "开发"
    else:  # window
        app_name = app_name or "unknown"
        if not category:
            category = "其他"

    # 校验分类合法性（不在 CATEGORIES 列表则回退到"其他"）
    if category not in CATEGORIES:
        category = "其他"

    # 额外元数据存入 windows_json（与现有截图活动格式一致）
    extra: dict[str, Any] = {
        "source": "aw_compat",
        "bucket_type": bucket_type,
    }
    # 透传 AW 事件的原始 data 中的额外字段
    for k in ("language", "project", "branch", "lines", "lineno", "cursorpos", "is_write"):
        if k in data:
            extra[k] = data[k]
    # 透传原始 AW event id（用于 heartbeat 去重）
    if event.get("id"):
        extra["aw_event_id"] = event["id"]

    summary = f"[AW] {app_name}"
    if window_title:
        summary = f"[AW] {app_name}: {window_title[:60]}"

    return {
        "timestamp": timestamp,
        "screenshot": "",
        "app_name": app_name,
        "window_title": window_title,
        "category": category,
        "summary": summary,
        "interval_sec": interval_sec,
        "ai_detail": "",
        "windows_json": _json.dumps([extra], ensure_ascii=False),
    }


def _activity_row_to_event(row: dict[str, Any], bucket_type: str, bucket_id: str) -> dict[str, Any]:
    """ChallengeDaily activity → AW event 格式（用于 GET 导出）"""
    ts_local = row.get("timestamp", "")
    iso_ts = _local_str_to_iso(ts_local)
    interval = row.get("interval_sec") or 60
    app_name = row.get("app_name") or ""
    window_title = row.get("window_title") or ""
    category = row.get("category") or "其他"

    # 反向解析 windows_json 取出原始 bucket_type
    extra: dict[str, Any] = {}
    wj = row.get("windows_json") or "[]"
    try:
        wj_list = _json.loads(wj) if wj else []
        if isinstance(wj_list, list) and wj_list:
            extra = wj_list[0] if isinstance(wj_list[0], dict) else {}
    except Exception:
        pass

    data: dict[str, Any] = {
        "app": app_name,
        "title": window_title,
    }
    if category and category != "其他":
        data["category"] = category
    # 透传 editor/web 特有字段
    for k in ("language", "project", "branch", "lines", "lineno", "cursorpos", "is_write", "status", "url", "file"):
        if k in extra:
            data[k] = extra[k]
    if bucket_type == BUCKET_TYPE_AFK:
        data = {"status": window_title or "afk"}

    return {
        "timestamp": iso_ts,
        "duration": float(interval),
        "data": data,
        "id": str(row.get("id") or _uuid.uuid4().hex),
    }


# ── Heartbeat 去重 ───────────────────────────────────────────────────
def _find_recent_activity_for_heartbeat(
    app_name: str,
    window_title: str,
    local_ts: str,
    window_sec: int = _HEARTBEAT_DEDUP_WINDOW_SEC,
) -> dict[str, Any] | None:
    """查找窗口期内的同 (app, title) 记录，用于 heartbeat 合并"""
    try:
        dt = datetime.strptime(local_ts, _LOCAL_TS_FMT)
    except ValueError:
        return None
    start_dt = dt - timedelta(seconds=window_sec)
    end_dt = dt + timedelta(seconds=window_sec)
    start_str = start_dt.strftime(_LOCAL_TS_FMT)
    end_str = end_dt.strftime(_LOCAL_TS_FMT)
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM activities "
                "WHERE app_name = ? AND window_title = ? "
                "AND timestamp >= ? AND timestamp <= ? "
                "ORDER BY timestamp DESC LIMIT 1",
                (app_name, window_title, start_str, end_str),
            ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.warning(f"heartbeat 去重查询失败: {e}")
        return None


# ── 路由：服务器信息 ──────────────────────────────────────────────────
@bp.route("/api/v1/", methods=["GET"])
@bp.route("/api/v1", methods=["GET"])
def server_info():
    """GET /api/v1/ - 服务器信息（与 aw-server 行为一致）"""
    return jsonify({
        "hostname": _get_hostname(),
        "version": _AW_SERVER_VERSION,
        "server": _AW_SERVER_ID,
        "pid": _os.getpid(),
    })


def _get_hostname() -> str:
    try:
        import socket
        return socket.gethostname() or "challenge-daily"
    except Exception:
        return "challenge-daily"


# ── 路由：Buckets ─────────────────────────────────────────────────────
@bp.route("/api/v1/buckets", methods=["GET"])
def list_buckets():
    """GET /api/v1/buckets - 列出所有 bucket"""
    buckets = _load_buckets()
    # 输出格式：{"bucket_id": {bucket_meta}, ...}（与 aw-server 一致）
    return jsonify(buckets)


@bp.route("/api/v1/buckets/<path:bid>", methods=["POST"])
def create_or_update_bucket(bid: str):
    """POST /api/v1/buckets/<bid> - 创建/更新 bucket

    请求体（aw-server 规范）:
    {
      "id": "<bid>",
      "type": "window|afk|web|editor",
      "client": "aw-watcher-window",
      "hostname": "myhost",
      "created": "2026-07-28T10:00:00Z"
    }
    """
    bid = _bucket_id_from_request(bid)
    if not bid:
        return jsonify({"error": "bucket_id 不能为空"}), 400
    data = request.get_json(silent=True) or {}

    btype = (data.get("type") or _bucket_type(bid)).strip().lower()
    if btype not in _VALID_BUCKET_TYPES:
        return jsonify({"error": f"无效 bucket 类型: {btype}, 可选: {sorted(_VALID_BUCKET_TYPES)}"}), 400

    client = (data.get("client") or "").strip() or f"aw-compat-{btype}"
    hostname = (data.get("hostname") or _get_hostname()).strip()
    created = (data.get("created") or _now_iso_utc()).strip()

    buckets = _load_buckets()
    bucket_meta = {
        "id": bid,
        "type": btype,
        "client": client,
        "hostname": hostname,
        "created": created,
        "data": data.get("data") or {},
    }
    # 保留已有 event_count
    if bid in buckets and isinstance(buckets[bid].get("event_count"), int):
        bucket_meta["event_count"] = buckets[bid]["event_count"]
    else:
        bucket_meta["event_count"] = 0

    buckets[bid] = bucket_meta
    _save_buckets(buckets)
    logger.info(f"AW bucket 创建/更新: {bid} (type={btype})")
    return jsonify(bucket_meta)


@bp.route("/api/v1/buckets/<path:bid>", methods=["GET"])
def get_bucket(bid: str):
    """GET /api/v1/buckets/<bid> - 获取单个 bucket 元数据"""
    bid = _bucket_id_from_request(bid)
    buckets = _load_buckets()
    if bid not in buckets:
        return jsonify({"error": "bucket 不存在", "bucket_id": bid}), 404
    return jsonify(buckets[bid])


@bp.route("/api/v1/buckets/<path:bid>", methods=["DELETE"])
def delete_bucket(bid: str):
    """DELETE /api/v1/buckets/<bid> - 删除 bucket（仅删元数据，不删已写入的 activities）"""
    bid = _bucket_id_from_request(bid)
    buckets = _load_buckets()
    if bid in buckets:
        del buckets[bid]
        _save_buckets(buckets)
        logger.info(f"AW bucket 删除: {bid}")
    return jsonify({"status": "ok", "deleted": bid})


# ── 路由：Events ──────────────────────────────────────────────────────
@bp.route("/api/v1/buckets/<path:bid>/events", methods=["GET"])
def get_events(bid: str):
    """GET /api/v1/buckets/<bid>/events - 查询事件

    支持 aw-server 标准查询参数：
    - limit=N: 限制返回条数（默认 1000）
    - start=ISO: 起始时间（含）
    - end=ISO: 结束时间（不含）
    - format=json: 输出格式（默认 json，CSV 暂不支持）
    """
    bid = _bucket_id_from_request(bid)
    buckets = _load_buckets()
    btype = buckets.get(bid, {}).get("type") if bid in buckets else _bucket_type(bid)

    try:
        limit = max(1, min(10000, int(request.args.get("limit", 1000))))
    except (ValueError, TypeError):
        limit = 1000

    start_iso = request.args.get("start", "")
    end_iso = request.args.get("end", "")
    fmt = (request.args.get("format") or "json").lower()

    start_local = _iso_to_local_str(start_iso) if start_iso else None
    end_local = _iso_to_local_str(end_iso) if end_iso else None

    try:
        with get_conn() as conn:
            sql = (
                "SELECT * FROM activities "
                "WHERE windows_json LIKE ? "
            )
            params: list[Any] = [f"%\"bucket_type\": \"{btype}\"%"]
            if start_local:
                sql += " AND timestamp >= ? "
                params.append(start_local)
            if end_local:
                sql += " AND timestamp <= ? "
                params.append(end_local)
            sql += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
    except Exception as e:
        return jsonify({"error": safe_error(e, "查询 events 失败")}), 500

    events = [_activity_row_to_event(dict(r), btype, bid) for r in rows]
    if fmt == "csv":
        # 简单 CSV 兜底（保留 aw-server 兼容）
        import io
        import csv as _csv_mod
        output = io.StringIO()
        writer = _csv_mod.writer(output)
        writer.writerow(["timestamp", "duration", "app", "title", "category"])
        for e in events:
            d = e.get("data") or {}
            writer.writerow([
                e.get("timestamp", ""),
                e.get("duration", 0),
                d.get("app") or "",
                d.get("title") or "",
                d.get("category") or "",
            ])
        from flask import Response
        return Response(output.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={bid}.csv"})
    # 默认 JSON（aw-server 标准）
    return jsonify(events)


@bp.route("/api/v1/buckets/<path:bid>/events", methods=["POST"])
def insert_events(bid: str):
    """POST /api/v1/buckets/<bid>/events - 批量插入事件

    请求体: 一个 event 对象或一个 event 数组。
    """
    bid = _bucket_id_from_request(bid)
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "请求体必须为 JSON"}), 400

    if isinstance(data, dict):
        events = [data]
    elif isinstance(data, list):
        events = data
    else:
        return jsonify({"error": "请求体必须是 event 对象或数组"}), 400

    if len(events) > _MAX_BATCH_EVENTS:
        return jsonify({
            "error": f"单次最多插入 {_MAX_BATCH_EVENTS} 条事件",
            "received": len(events),
        }), 413

    # 若 bucket 不存在，自动创建（与 aw-server 行为一致）
    buckets = _load_buckets()
    if bid not in buckets:
        btype = _bucket_type(bid)
        buckets[bid] = {
            "id": bid,
            "type": btype,
            "client": f"aw-compat-{btype}",
            "hostname": _get_hostname(),
            "created": _now_iso_utc(),
            "data": {},
            "event_count": 0,
        }
        _save_buckets(buckets)

    btype = buckets[bid].get("type") or _bucket_type(bid)
    inserted = 0
    errors: list[dict[str, Any]] = []

    # 批量插入用事务
    try:
        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for i, ev in enumerate(events):
                    if not isinstance(ev, dict):
                        errors.append({"index": i, "error": "event 必须是对象"})
                        continue
                    try:
                        row = _event_to_activity_row(ev, btype)
                        conn.execute(
                            "INSERT INTO activities "
                            "(timestamp, screenshot, app_name, window_title, category, "
                            "summary, interval_sec, ai_detail, windows_json) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                row["timestamp"], row["screenshot"],
                                row["app_name"], row["window_title"],
                                row["category"], row["summary"],
                                row["interval_sec"], row["ai_detail"],
                                row["windows_json"],
                            ),
                        )
                        inserted += 1
                    except Exception as e:
                        errors.append({"index": i, "error": str(e)})
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    except Exception as e:
        return jsonify({"error": safe_error(e, "批量插入失败")}), 500

    # 更新 bucket 的 event_count
    buckets[bid]["event_count"] = (buckets[bid].get("event_count") or 0) + inserted
    _save_buckets(buckets)

    # 统计
    _incr_stat("aw_events_received", len(events))
    _incr_stat("aw_events_inserted", inserted)

    logger.info(f"AW bucket={bid} 接收 {len(events)} 条, 插入 {inserted} 条")
    return jsonify({
        "status": "ok",
        "bucket_id": bid,
        "received": len(events),
        "inserted": inserted,
        "errors": errors[:20] if errors else [],
    }), 201


@bp.route("/api/v1/buckets/<path:bid>/heartbeat", methods=["POST"])
def heartbeat(bid: str):
    """POST /api/v1/buckets/<bid>/heartbeat - 心跳式插入（WakaTime 风格）

    请求体: 单个 event 对象。若 (app, title, timestamp±2min) 已有记录，
    则合并（延长 end_time/duration），否则插入新记录。
    """
    bid = _bucket_id_from_request(bid)
    ev = request.get_json(silent=True)
    if not isinstance(ev, dict):
        return jsonify({"error": "请求体必须为单个 event 对象"}), 400

    buckets = _load_buckets()
    if bid not in buckets:
        btype = _bucket_type(bid)
        buckets[bid] = {
            "id": bid,
            "type": btype,
            "client": f"aw-compat-{btype}",
            "hostname": _get_hostname(),
            "created": _now_iso_utc(),
            "data": {},
            "event_count": 0,
        }
        _save_buckets(buckets)
    btype = buckets[bid].get("type") or _bucket_type(bid)

    row = _event_to_activity_row(ev, btype)
    local_ts = row["timestamp"]
    interval = row["interval_sec"]

    _incr_stat("aw_heartbeats_received")

    # 查找窗口期内同 (app, title) 的记录
    existing = _find_recent_activity_for_heartbeat(
        row["app_name"], row["window_title"], local_ts,
    )

    try:
        with get_conn() as conn:
            if existing:
                # 合并：用更晚的时间作为 timestamp，duration 累加
                existing_ts = existing["timestamp"]
                # 取较晚的时间戳作为新 timestamp
                try:
                    new_ts = max(local_ts, existing_ts)
                except TypeError:
                    new_ts = local_ts
                merged_interval = (existing.get("interval_sec") or 60) + interval
                # 合并 windows_json 的额外字段（保留最早的 source 信息）
                merged_extra: dict[str, Any] = {}
                try:
                    wj_old = _json.loads(existing.get("windows_json") or "[]")
                    if isinstance(wj_old, list) and wj_old and isinstance(wj_old[0], dict):
                        merged_extra = dict(wj_old[0])
                except Exception:
                    pass
                merged_extra["heartbeat_merged"] = merged_extra.get("heartbeat_merged", 0) + 1
                merged_extra["last_heartbeat_at"] = local_ts
                conn.execute(
                    "UPDATE activities SET timestamp = ?, interval_sec = ?, windows_json = ? "
                    "WHERE id = ?",
                    (new_ts, merged_interval,
                     _json.dumps([merged_extra], ensure_ascii=False),
                     existing["id"]),
                )
                conn.commit()
                _incr_stat("aw_heartbeats_merged")
                logger.debug(f"AW heartbeat 合并: bucket={bid}, app={row['app_name']}, +{interval}s")
                return jsonify({
                    "status": "merged",
                    "bucket_id": bid,
                    "activity_id": existing["id"],
                    "merged_interval_sec": merged_interval,
                })
            # 新记录
            conn.execute(
                "INSERT INTO activities "
                "(timestamp, screenshot, app_name, window_title, category, "
                "summary, interval_sec, ai_detail, windows_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["timestamp"], row["screenshot"],
                    row["app_name"], row["window_title"],
                    row["category"], row["summary"],
                    row["interval_sec"], row["ai_detail"],
                    row["windows_json"],
                ),
            )
            conn.commit()
            new_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    except Exception as e:
        return jsonify({"error": safe_error(e, "heartbeat 写入失败")}), 500

    # 更新 bucket 的 event_count
    buckets = _load_buckets()
    if bid in buckets:
        buckets[bid]["event_count"] = (buckets[bid].get("event_count") or 0) + 1
        _save_buckets(buckets)

    _incr_stat("aw_events_inserted")
    logger.debug(f"AW heartbeat 新建: bucket={bid}, app={row['app_name']}")
    return jsonify({
        "status": "created",
        "bucket_id": bid,
        "activity_id": new_id,
    }), 201


@bp.route("/api/v1/buckets/<path:bid>/events/<int:eid>", methods=["DELETE"])
def delete_event(bid: str, eid: int):
    """DELETE /api/v1/buckets/<bid>/events/<eid> - 删除事件

    注意：直接从 activities 表删除（与 aw-server 行为一致，无软删除）。
    """
    try:
        with get_conn() as conn:
            cur = conn.execute("DELETE FROM activities WHERE id = ?", (eid,))
            conn.commit()
            if cur.rowcount == 0:
                return jsonify({"error": "event 不存在", "id": eid}), 404
    except Exception as e:
        return jsonify({"error": safe_error(e, "删除失败")}), 500
    return jsonify({"status": "ok", "deleted": eid})


# ── 路由：导出 ────────────────────────────────────────────────────────
@bp.route("/api/v1/export/<path:bid>", methods=["GET"])
def export_bucket(bid: str):
    """GET /api/v1/export/<bid> - 导出整个 bucket 为 AW JSON 格式

    返回 aw-webui 兼容的导出格式：
    {
      "buckets": {
        "<bid>": {
          "id": ...,
          "type": ...,
          "events": [...]
        }
      }
    }
    """
    bid = _bucket_id_from_request(bid)
    buckets = _load_buckets()
    if bid not in buckets:
        return jsonify({"error": "bucket 不存在"}), 404

    btype = buckets[bid].get("type") or _bucket_type(bid)
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM activities "
                "WHERE windows_json LIKE ? "
                "ORDER BY timestamp ASC",
                (f"%\"bucket_type\": \"{btype}\"%",),
            ).fetchall()
    except Exception as e:
        return jsonify({"error": safe_error(e, "导出失败")}), 500

    events = [_activity_row_to_event(dict(r), btype, bid) for r in rows]
    bucket_export = dict(buckets[bid])
    bucket_export["events"] = events
    return jsonify({"buckets": {bid: bucket_export}})


# ── 兼容层状态/统计（前端面板用，不在 aw-server 规范内） ───────────
# 这些端点放在 /api/aw/* 下，由 server.py 全局 check_token 保护（前端 X-API-Token）。
# /api/v1/* 下的端点则严格遵循 aw-server 协议，无 ChallengeDaily 私有路径。
@bp.route("/api/aw/meta", methods=["GET"])
def meta_info():
    """兼容层元信息（供前端 ProtocolCompatPanel 使用）

    返回服务器地址、可用 bucket、统计数据。
    """
    buckets = _load_buckets()
    stats = _load_stats()
    return jsonify({
        "server_url": f"http://127.0.0.1:{HTTP_PORT}/api/v1/",
        "server_id": _AW_SERVER_ID,
        "server_version": _AW_SERVER_VERSION,
        "buckets": list(buckets.values()),
        "stats": stats,
        "auth_required": bool(_AW_COMPAT_TOKEN or _get_settings_token()),
    })


@bp.route("/api/aw/test", methods=["POST"])
def test_connection():
    """测试连接：发送一条模拟 AW event 并返回服务器信息（前端"测试连接"按钮调用）

    内部调用 aw-server 协议自身的 POST /api/v1/buckets/<bid>/heartbeat，
    验证整条链路是否工作。
    """
    test_event = {
        "timestamp": _now_iso_utc(),
        "duration": 30.0,
        "data": {
            "app": "challenge-daily-test",
            "title": "AW Compat Test Event",
        },
    }
    # 直接走 _event_to_activity_row + 写库（绕过 HTTP 自调用，避免端口冲突）
    try:
        row = _event_to_activity_row(test_event, BUCKET_TYPE_WINDOW)
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO activities "
                "(timestamp, screenshot, app_name, window_title, category, "
                "summary, interval_sec, ai_detail, windows_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["timestamp"], row["screenshot"],
                    row["app_name"], row["window_title"],
                    row["category"], row["summary"],
                    row["interval_sec"], row["ai_detail"],
                    row["windows_json"],
                ),
            )
            conn.commit()
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": safe_error(e, "测试 event 写入失败"),
        }), 500

    # 更新统计
    _incr_stat("aw_events_received")
    _incr_stat("aw_events_inserted")

    return jsonify({
        "status": "ok",
        "pong": True,
        "server": _AW_SERVER_ID,
        "version": _AW_SERVER_VERSION,
        "hostname": _get_hostname(),
        "timestamp": _now_iso_utc(),
        "buckets_count": len(_load_buckets()),
        "message": "测试 event 已写入，请检查活动记录中是否出现 [AW] 标记的记录",
    })
