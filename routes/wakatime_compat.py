"""
WakaTime heartbeat API 兼容层
============================
让 ChallengeDaily 兼容 WakaTime 官方客户端（VS Code 插件、CLI 等），
使现有 WakaTime 用户可零迁移成本接入。

参考实现：
- https://wakatime.com/developers#heartbeats
- https://github.com/wakatime/wakatime/blob/master/README.md

设计要点：
- POST /api/heartbeat 单条心跳
- POST /api/v1/users/current/heartbeats 批量心跳
- 鉴权：Authorization: Basic <base64(api_key)> 或 X-API-Token
- 心跳去重：(entity, time±2min) 视为同一条记录
- 时间：WakaTime 使用 unix timestamp（秒），转换为本地 "%Y-%m-%d %H:%M:%S"
- 不影响现有 /api/* 路由（用 /api/heartbeat 独立路径，batch 走 /api/v1/users/current/heartbeats）
"""
from __future__ import annotations

import base64
import binascii
import hmac
import json as _json
import logging
import secrets
import threading
import time as _time_mod
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

from config import DATA_DIR, CATEGORIES
from db import get_conn, insert_activity
from file_utils import atomic_write_text, backup_file
from routes.deps import safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('wakatime_compat', __name__)

# ── 常量 ────────────────────────────────────────────────────────────
_LOCAL_TS_FMT = "%Y-%m-%d %H:%M:%S"
_HEARTBEAT_DEDUP_WINDOW_SEC = 120  # WakaTime 默认 2 分钟去重窗口
_MAX_BATCH_HEARTBEATS = 1000
_WAKATIME_API_VERSION = "1.0.0"

# WakaTime API Key 持久化路径（与 aw_buckets.json 同目录）
_WAKATIME_KEY_FILE = DATA_DIR / "wakatime_api_key.json"
_key_lock = threading.Lock()
_key_cache: str | None = None

# 默认 app_name（WakaTime 通常通过 editor 字段标识编辑器）
_DEFAULT_EDITOR_NAME = "VS Code"
# 默认 category（WakaTime 的 category=coding 通常对应开发）
_DEFAULT_CATEGORY = "开发"

# WakaTime category → ChallengeDaily CATEGORIES 映射
_WAKATIME_CATEGORY_MAP = {
    "coding": "开发",
    "browsing": "其他",
    "building": "运维",
    "code review": "开发",
    "debugging": "测试",
    "designing": "设计",
    "indexing": "其他",
    "learning": "学习",
    "planning": "管理",
    "researching": "学习",
    "testing": "测试",
    "writing docs": "文档",
    "writing tests": "测试",
    "communicating": "沟通",
    "meeting": "会议",
    "designing database": "设计",
}


# ── API Key 管理 ────────────────────────────────────────────────────
def _load_api_key() -> str:
    """加载（必要时生成）WakaTime 兼容 API Key"""
    global _key_cache
    with _key_lock:
        if _key_cache:
            return _key_cache
        if _WAKATIME_KEY_FILE.exists():
            try:
                data = _json.loads(_WAKATIME_KEY_FILE.read_text(encoding="utf-8"))
                key = (data.get("api_key") or "").strip()
                if key:
                    _key_cache = key
                    return key
            except Exception as e:
                logger.warning(f"读取 wakatime_api_key.json 失败: {e}")
        # 生成新的 API key（WakaTime 格式：40 位 hex）
        new_key = secrets.token_hex(20)
        _WAKATIME_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            _WAKATIME_KEY_FILE,
            _json.dumps({
                "api_key": new_key,
                "created_at": datetime.now().strftime(_LOCAL_TS_FMT),
                "label": "ChallengeDaily WakaTime Compat",
            }, ensure_ascii=False, indent=2),
        )
        _key_cache = new_key
        logger.info(f"已生成 WakaTime 兼容 API Key: {_WAKATIME_KEY_FILE}")
        return new_key


def _regenerate_api_key() -> str:
    """重新生成 API key（前端"重置 Key"按钮调用）"""
    global _key_cache
    with _key_lock:
        new_key = secrets.token_hex(20)
        _WAKATIME_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        backup_file(_WAKATIME_KEY_FILE) if _WAKATIME_KEY_FILE.exists() else None
        atomic_write_text(
            _WAKATIME_KEY_FILE,
            _json.dumps({
                "api_key": new_key,
                "created_at": datetime.now().strftime(_LOCAL_TS_FMT),
                "label": "ChallengeDaily WakaTime Compat",
            }, ensure_ascii=False, indent=2),
        )
        _key_cache = new_key
        logger.info("已重新生成 WakaTime 兼容 API Key")
        return new_key


# ── 鉴权 ────────────────────────────────────────────────────────────
def _extract_api_key_from_request() -> str | None:
    """从请求中提取 API key（支持 Basic Auth 和 X-API-Token）"""
    # 1. X-API-Token header
    token_header = request.headers.get("X-API-Token", "").strip()
    if token_header:
        return token_header
    # 2. Authorization: Basic <base64(api_key)> 或 <base64(api_key:optional_secret)>
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode("utf-8", errors="ignore")
            # WakaTime 客户端: base64(api_key) 或 base64(api_key:)
            return decoded.split(":", 1)[0].strip() or None
        except (binascii.Error, ValueError):
            return None
    # 3. ?api_key= query param（兼容某些客户端）
    return (request.args.get("api_key") or "").strip() or None


def _check_wakatime_auth() -> tuple[bool, str | None]:
    """校验 WakaTime 鉴权

    返回 (ok, error_message)。
    """
    provided = _extract_api_key_from_request()
    if not provided:
        return False, "missing api key (Authorization: Basic <key> or X-API-Token)"
    expected = _load_api_key()
    if not hmac.compare_digest(provided, expected):
        return False, "invalid api key"
    return True, None


@bp.before_request
def _auth_guard():
    """所有 WakaTime 兼容路由都需要 API key 鉴权

    例外：/api/wakatime/status（前端面板查询状态）和 /api/wakatime/test
    使用 ChallengeDaily 自身的 X-API-Token（由 server.py 全局 check_token 完成）
    """
    path = request.path
    # 内部管理端点（前端面板用）走全局鉴权（X-API-Token），不在此处校验 WakaTime key
    if path.startswith("/api/wakatime/"):
        return None
    # heartbeat 端点走 WakaTime API key 鉴权
    ok, err = _check_wakatime_auth()
    if not ok:
        return jsonify({
            "error": "authentication_failed",
            "message": err or "auth failed",
        }), 401
    return None


# ── 时间转换 ────────────────────────────────────────────────────────
def _unix_to_local_str(unix_ts: float | int | str) -> str:
    """Unix timestamp（秒）→ 本地 '%Y-%m-%d %H:%M:%S' 字符串"""
    try:
        ts = float(unix_ts)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        local_dt = dt.astimezone()
        return local_dt.strftime(_LOCAL_TS_FMT)
    except (ValueError, TypeError):
        # 兜底：当前时间
        return datetime.now().strftime(_LOCAL_TS_FMT)


def _local_str_to_unix(local_ts: str) -> float:
    """本地时间字符串 → Unix timestamp（秒，UTC）"""
    try:
        dt = datetime.strptime(local_ts, _LOCAL_TS_FMT)
        local_dt = dt.astimezone()
        return local_dt.astimezone(timezone.utc).timestamp()
    except Exception:
        return datetime.now(timezone.utc).timestamp()


# ── 数据转换 ──────────────────────────────────────────────────────────
def _heartbeat_to_activity_fields(hb: dict[str, Any]) -> dict[str, Any]:
    """WakaTime heartbeat → ChallengeDaily activity 字段

    映射规则（按 task 要求）：
    - heartbeat → app_usage 记录（app_name="VS Code", window_title=entity, category="开发"）
    - 连续心跳（2分钟内同 entity）合并
    - 语言/项目信息存入 windows_json 的额外字段
    - 实际同时写入 activities 表（与 app_usage 保持一致），便于日报与统计
    """
    entity = (hb.get("entity") or "").strip()
    entity_type = (hb.get("type") or "file").strip().lower()
    category_raw = (hb.get("category") or "coding").strip().lower()
    language = (hb.get("language") or "").strip()
    project = (hb.get("project") or "").strip()
    branch = (hb.get("branch") or "").strip()
    lines = hb.get("lines")
    lineno = hb.get("lineno")
    cursorpos = hb.get("cursorpos")
    is_write = bool(hb.get("is_write"))
    time_unix = hb.get("time") or _time_mod.time()
    user_agent = (hb.get("user_agent") or "").strip()

    # 从 user_agent 提取编辑器名（如 "wakatime/2.1.0 (vscode/1.85.0)" → "VS Code"）
    editor_name = _DEFAULT_EDITOR_NAME
    ua_lower = user_agent.lower()
    if "vscode" in ua_lower or "vs-code" in ua_lower:
        editor_name = "VS Code"
    elif "jetbrains" in ua_lower or "intellij" in ua_lower or "pycharm" in ua_lower:
        editor_name = "JetBrains IDE"
    elif "vim" in ua_lower or "neovim" in ua_lower:
        editor_name = "Vim"
    elif "emacs" in ua_lower:
        editor_name = "Emacs"
    elif "sublime" in ua_lower:
        editor_name = "Sublime Text"
    elif "atom" in ua_lower:
        editor_name = "Atom"
    # heartbeat 中显式带 editor 字段（部分客户端会带）
    editor_field = (hb.get("editor") or "").strip()
    if editor_field:
        editor_name = editor_field

    # category 映射
    category = _WAKATIME_CATEGORY_MAP.get(category_raw, _DEFAULT_CATEGORY)
    if category not in CATEGORIES:
        category = _DEFAULT_CATEGORY

    # entity 处理：type=file 时取文件名作为 window_title；type=app 时取 app 本身
    if entity_type == "app":
        app_name = entity or editor_name
        window_title = ""
    else:
        app_name = editor_name
        window_title = entity
        # 取文件名（带扩展名）作为简洁标题
        if "/" in entity or "\\" in entity:
            window_title = entity.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or entity

    local_ts = _unix_to_local_str(time_unix)
    interval_sec = 60  # 单条心跳默认 60 秒（与 WakaTime 心跳间隔一致）

    # 额外元数据存入 windows_json
    extra: dict[str, Any] = {
        "source": "wakatime_compat",
        "entity": entity,
        "entity_type": entity_type,
        "category_raw": category_raw,
        "language": language,
        "project": project,
        "branch": branch,
        "is_write": is_write,
        "user_agent": user_agent,
    }
    # 仅在非空时添加数值字段
    if lines is not None:
        extra["lines"] = lines
    if lineno is not None:
        extra["lineno"] = lineno
    if cursorpos is not None:
        extra["cursorpos"] = cursorpos

    # summary：项目/语言信息
    summary_parts = ["[WakaTime]"]
    if project:
        summary_parts.append(project)
    if language:
        summary_parts.append(f"({language})")
    if entity:
        summary_parts.append(f"- {window_title or entity}")
    summary = " ".join(summary_parts)[:200]

    return {
        "timestamp": local_ts,
        "screenshot": "",
        "app_name": app_name,
        "window_title": window_title,
        "category": category,
        "summary": summary,
        "interval_sec": interval_sec,
        "ai_detail": "",
        "windows_json": _json.dumps([extra], ensure_ascii=False),
        # 同时生成 app_usage 字段（与 insert_manual_activity 行为一致）
        "_app_usage_app": app_name,
        "_app_usage_title": window_title,
        "_app_usage_start": local_ts,
        "_app_usage_end": local_ts,  # 后续心跳会更新
        "_app_usage_duration_sec": interval_sec,
        # 用于去重的 key
        "_dedup_key": (app_name, window_title, local_ts),
        "_time_unix": float(time_unix),
    }


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
                "AND windows_json LIKE ? "
                "AND timestamp >= ? AND timestamp <= ? "
                "ORDER BY timestamp DESC LIMIT 1",
                (app_name, window_title, '%wakatime_compat%',
                 start_str, end_str),
            ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.warning(f"wakatime heartbeat 去重查询失败: {e}")
        return None


def _write_heartbeat(hb: dict[str, Any]) -> dict[str, Any]:
    """处理单条 heartbeat：去重合并或新建

    返回 {status, activity_id, action: 'created'|'merged'}
    """
    fields = _heartbeat_to_activity_fields(hb)
    local_ts = fields["timestamp"]
    app_name = fields["app_name"]
    window_title = fields["window_title"]
    interval = fields["interval_sec"]

    # 查找窗口期内同 (app, title) 的 wakatime 心跳记录
    existing = _find_recent_activity_for_heartbeat(app_name, window_title, local_ts)

    try:
        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                if existing:
                    # 合并：duration 累加，timestamp 取较晚者
                    existing_ts = existing["timestamp"]
                    try:
                        new_ts = max(local_ts, existing_ts)
                    except TypeError:
                        new_ts = local_ts
                    merged_interval = (existing.get("interval_sec") or 60) + interval

                    # 合并 windows_json：保留原有字段，更新 last_heartbeat_at
                    merged_extra: dict[str, Any] = {}
                    try:
                        wj_old = _json.loads(existing.get("windows_json") or "[]")
                        if isinstance(wj_old, list) and wj_old and isinstance(wj_old[0], dict):
                            merged_extra = dict(wj_old[0])
                    except Exception:
                        pass
                    merged_extra["heartbeat_merged"] = merged_extra.get("heartbeat_merged", 0) + 1
                    merged_extra["last_heartbeat_at"] = local_ts
                    # 保留最早创建时间
                    if not merged_extra.get("first_heartbeat_at"):
                        merged_extra["first_heartbeat_at"] = existing_ts

                    conn.execute(
                        "UPDATE activities SET timestamp = ?, interval_sec = ?, windows_json = ? "
                        "WHERE id = ?",
                        (new_ts, merged_interval,
                         _json.dumps([merged_extra], ensure_ascii=False),
                         existing["id"]),
                    )
                    # 同步更新 app_usage 表（如存在）
                    try:
                        conn.execute(
                            "UPDATE app_usage SET end_time = ?, duration_sec = ? "
                            "WHERE app_name = ? AND window_title = ? AND start_time = ?",
                            (new_ts, merged_interval, app_name, window_title,
                             existing_ts),
                        )
                    except Exception:
                        pass  # app_usage 表更新失败不影响主流程
                    conn.commit()
                    return {
                        "status": "merged",
                        "action": "merged",
                        "activity_id": existing["id"],
                        "merged_interval_sec": merged_interval,
                    }
                # 新记录
                cur = conn.execute(
                    "INSERT INTO activities "
                    "(timestamp, screenshot, app_name, window_title, category, "
                    "summary, interval_sec, ai_detail, windows_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        fields["timestamp"], fields["screenshot"],
                        app_name, window_title,
                        fields["category"], fields["summary"],
                        interval, fields["ai_detail"],
                        fields["windows_json"],
                    ),
                )
                new_id = cur.lastrowid
                # 同步写入 app_usage 表
                try:
                    conn.execute(
                        "INSERT INTO app_usage "
                        "(app_name, window_title, start_time, end_time, duration_sec) "
                        "VALUES (?, ?, ?, ?, ?) "
                        "ON CONFLICT(app_name, window_title, start_time) DO UPDATE SET "
                        "end_time=excluded.end_time, duration_sec=excluded.duration_sec",
                        (app_name, window_title, local_ts, local_ts, interval),
                    )
                except Exception as e:
                    logger.warning(f"app_usage 同步写入失败（不影响主流程）: {e}")
                conn.commit()
                return {
                    "status": "created",
                    "action": "created",
                    "activity_id": new_id,
                }
            except Exception:
                conn.rollback()
                raise
    except Exception as e:
        raise RuntimeError(safe_error(e, "heartbeat 写入失败"))


# ── 路由 ─────────────────────────────────────────────────────────────
@bp.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    """POST /api/heartbeat - 单条心跳

    WakaTime 客户端主要调用此端点。请求体见任务说明。
    返回 WakaTime 官方兼容格式。
    """
    hb = request.get_json(silent=True)
    if not isinstance(hb, dict):
        return jsonify({
            "error": "invalid_request",
            "message": "请求体必须是 JSON 对象",
        }), 400

    # 字段校验
    if not hb.get("entity"):
        return jsonify({
            "error": "invalid_request",
            "message": "entity 字段必填",
        }), 400

    # 更新统计
    try:
        from routes.aw_compat import _incr_stat
        _incr_stat("wakatime_heartbeats_received")
    except Exception:
        pass

    try:
        result = _write_heartbeat(hb)
    except Exception as e:
        return jsonify({
            "error": "internal_error",
            "message": str(e),
        }), 500

    # 更新合并统计
    if result.get("action") == "merged":
        try:
            from routes.aw_compat import _incr_stat
            _incr_stat("wakatime_heartbeats_merged")
        except Exception:
            pass
    else:
        try:
            from routes.aw_compat import _incr_stat
            _incr_stat("aw_events_inserted")
        except Exception:
            pass

    # WakaTime 官方响应格式
    response_data = {
        "data": {
            "id": str(result["activity_id"]),
            "activity_id": result["activity_id"],
        },
        "status": result["status"],
    }
    return jsonify(response_data), 201


@bp.route("/api/v1/users/current/heartbeats", methods=["POST"])
def heartbeats_bulk():
    """POST /api/v1/users/current/heartbeats - 批量心跳

    请求体：heartbeat 数组（与单条 heartbeat 格式相同）
    返回：每个 heartbeat 的处理结果数组
    """
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({
            "error": "invalid_request",
            "message": "请求体必须为 JSON",
        }), 400

    if isinstance(payload, dict):
        # 单条也支持
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        return jsonify({
            "error": "invalid_request",
            "message": "请求体必须是数组或对象",
        }), 400

    if len(items) > _MAX_BATCH_HEARTBEATS:
        return jsonify({
            "error": "too_many_heartbeats",
            "message": f"单次最多 {_MAX_BATCH_HEARTBEATS} 条心跳",
            "received": len(items),
        }), 413

    results: list[dict[str, Any]] = []
    received_count = 0
    merged_count = 0
    created_count = 0

    for i, hb in enumerate(items):
        if not isinstance(hb, dict):
            results.append({
                "index": i,
                "error": "heartbeat 必须是对象",
            })
            continue
        if not hb.get("entity"):
            results.append({
                "index": i,
                "error": "entity 字段必填",
            })
            continue
        received_count += 1
        try:
            r = _write_heartbeat(hb)
            results.append({
                "index": i,
                "status": r["status"],
                "activity_id": r["activity_id"],
            })
            if r["action"] == "merged":
                merged_count += 1
            else:
                created_count += 1
        except Exception as e:
            results.append({
                "index": i,
                "error": str(e),
            })

    # 更新统计
    try:
        from routes.aw_compat import _incr_stat
        _incr_stat("wakatime_heartbeats_received", received_count)
        _incr_stat("wakatime_heartbeats_merged", merged_count)
        _incr_stat("aw_events_inserted", created_count)
    except Exception:
        pass

    # WakaTime 批量响应格式
    return jsonify({
        "responses": results,
        "summary": {
            "received": received_count,
            "created": created_count,
            "merged": merged_count,
        },
    }), 201


# ── 前端管理端点（不在 WakaTime 官方协议内） ───────────────────────
@bp.route("/api/wakatime/status", methods=["GET"])
def status():
    """WakaTime 兼容层状态（前端 ProtocolCompatPanel 调用）

    返回 API key（部分掩码）、配置说明、统计数据。
    """
    api_key = _load_api_key()
    # 掩码：只显示前 4 位和后 4 位
    if len(api_key) > 8:
        masked = f"{api_key[:4]}...{api_key[-4:]}"
    else:
        masked = "***"

    # 加载统计
    try:
        from routes.aw_compat import _load_stats
        stats = _load_stats()
    except Exception:
        stats = {}

    return jsonify({
        "enabled": True,
        "api_key_masked": masked,
        "api_key_length": len(api_key),
        "endpoints": {
            "single": "POST /api/heartbeat",
            "bulk": "POST /api/v1/users/current/heartbeats",
        },
        "auth_methods": [
            "Authorization: Basic <base64(api_key)>",
            "X-API-Token: <api_key>",
        ],
        "config_instructions": {
            "vscode": {
                "title": "VS Code WakaTime 插件配置",
                "steps": [
                    "安装 WakaTime 插件（VS Code Extensions 搜索 'WakaTime'）",
                    f"打开 ~/.wakatime.cfg，设置 api_key = {masked}",
                    "设置 api_url = http://127.0.0.1:58888/api (ChallengeDaily 本地服务)",
                    "重启 VS Code，开始 coding 即可自动上报",
                ],
            },
            "cli": {
                "title": "WakaTime CLI 配置",
                "steps": [
                    "pip install wakatime",
                    f"配置 ~/.wakatime.cfg: api_key = {masked}",
                    "设置 api_url = http://127.0.0.1:58888/api",
                ],
            },
        },
        "stats": stats,
        "version": _WAKATIME_API_VERSION,
    })


@bp.route("/api/wakatime/key", methods=["GET"])
def get_api_key():
    """获取完整 API key（前端"显示完整 Key"按钮调用）"""
    # 此端点由 server.py 全局 check_token 保护
    return jsonify({"api_key": _load_api_key()})


@bp.route("/api/wakatime/key", methods=["POST"])
def regenerate_api_key():
    """重新生成 API key（前端"重置 Key"按钮调用）"""
    new_key = _regenerate_api_key()
    return jsonify({
        "status": "ok",
        "api_key": new_key,
        "message": "API key 已重置，请在 WakaTime 客户端更新配置",
    })


@bp.route("/api/wakatime/test", methods=["POST"])
def test_heartbeat():
    """测试心跳：发送一条模拟 heartbeat（前端"测试心跳"按钮调用）

    此端点由 server.py 全局 check_token 保护，不消耗 WakaTime API key。
    """
    test_hb = {
        "entity": "/test/challenge-daily-wakatime-test.py",
        "type": "file",
        "category": "coding",
        "language": "Python",
        "project": "challenge-daily-test",
        "branch": "main",
        "lines": 42,
        "lineno": 10,
        "cursorpos": 5,
        "is_write": False,
        "time": _time_mod.time(),
        "user_agent": "challenge-daily-test/1.0",
    }
    try:
        result = _write_heartbeat(test_hb)
        return jsonify({
            "status": "ok",
            "result": result,
            "message": "测试心跳已发送，请检查活动记录中是否出现 [WakaTime] 标记的记录",
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
        }), 500
