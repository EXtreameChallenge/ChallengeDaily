"""
P11-3：AI 调用审计链
记录所有 AI 调用的输入/输出/耗时/状态，便于追溯与问题排查。
所有日志脱敏后写入 audit_log 表，保留 30 天。
"""
import json
import logging
import threading
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 审计日志保留天数
_AUDIT_RETENTION_DAYS = 30

# 写入锁（防止并发写入冲突）
_audit_lock = threading.Lock()


def _safe_str(val, max_len: int = 500) -> str:
    """安全转字符串并截断"""
    try:
        s = str(val) if val is not None else ""
        return s[:max_len]
    except Exception:
        return ""


def _sanitize_metadata(meta: dict) -> dict:
    """脱敏元数据：屏蔽 API Key、Bearer token、长字符串"""
    if not isinstance(meta, dict):
        return {}
    SENSITIVE_KEYS = {"api_key", "apikey", "token", "authorization", "password", "secret"}
    cleaned = {}
    for k, v in meta.items():
        k_lower = str(k).lower()
        if any(s in k_lower for s in SENSITIVE_KEYS):
            cleaned[k] = "***"
        elif isinstance(v, str) and len(v) > 200:
            cleaned[k] = v[:200] + "...(truncated)"
        elif isinstance(v, (dict, list)):
            cleaned[k] = _sanitize_metadata(v) if isinstance(v, dict) else [_safe_str(i, 100) for i in v[:5]]
        else:
            cleaned[k] = v
    return cleaned


def log_audit(
    category: str,
    action: str,
    status: str,
    detail: str = "",
    duration_ms: int | None = None,
    metadata: dict | None = None,
) -> None:
    """写入一条审计日志

    Args:
        category: 分类，如 "ai_vision" / "ai_text" / "ai_greeting" / "offline_fallback"
        action: 具体动作，如 "analyze_screenshot" / "generate_greeting" / "retry_queue_drain"
        status: "success" / "failure" / "skipped" / "fallback"
        detail: 详细说明（脱敏后截断到 500 字符）
        duration_ms: 耗时（毫秒）
        metadata: 额外元数据（自动脱敏）
    """
    try:
        import db
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        meta_str = json.dumps(_sanitize_metadata(metadata or {}), ensure_ascii=False) if metadata else None
        with _audit_lock, db.get_conn() as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, category, action, status, detail, duration_ms, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, category, action, status, _safe_str(detail, 500), duration_ms, meta_str),
            )
            conn.commit()
    except Exception as e:
        logger.debug(f"审计日志写入失败（不影响主流程）: {e}")


def cleanup_old_audit_logs() -> int:
    """清理超过保留天数的审计日志，返回删除条数"""
    try:
        import db
        cutoff = (datetime.now() - timedelta(days=_AUDIT_RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        with _audit_lock, db.get_conn() as conn:
            cur = conn.execute("DELETE FROM audit_log WHERE ts < ?", (cutoff,))
            conn.commit()
            return cur.rowcount or 0
    except Exception as e:
        logger.debug(f"清理审计日志失败: {e}")
        return 0


def query_audit_logs(
    category: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """查询审计日志（供前端审计页面展示）"""
    try:
        import db
        sql = "SELECT * FROM audit_log"
        conditions = []
        params: list = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY ts DESC LIMIT ? OFFSET ?"
        params.extend([max(1, min(limit, 500)), max(0, offset)])
        with db.get_conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.debug(f"查询审计日志失败: {e}")
        return []


def get_audit_stats() -> dict:
    """获取审计日志统计（供健康检查/仪表盘展示）"""
    try:
        import db
        with db.get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM audit_log").fetchone()
            by_status = conn.execute(
                "SELECT status, COUNT(*) AS c FROM audit_log GROUP BY status"
            ).fetchall()
            by_category = conn.execute(
                "SELECT category, COUNT(*) AS c FROM audit_log GROUP BY category ORDER BY c DESC"
            ).fetchall()
            # 最近 24 小时失败数
            cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            recent_failures = conn.execute(
                "SELECT COUNT(*) AS c FROM audit_log WHERE ts > ? AND status = 'failure'",
                (cutoff,),
            ).fetchone()
        return {
            "total": total["c"] if total else 0,
            "by_status": {r["status"]: r["c"] for r in by_status},
            "by_category": {r["category"]: r["c"] for r in by_category},
            "recent_24h_failures": recent_failures["c"] if recent_failures else 0,
        }
    except Exception as e:
        logger.debug(f"获取审计统计失败: {e}")
        return {"total": 0, "by_status": {}, "by_category": {}, "recent_24h_failures": 0}
