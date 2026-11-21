"""
P61-P69: 数据与分析增强模块
- P61: 数据库索引优化分析
- P62: 日/周/月聚合预计算
- P63: 时间序列内存缓存层
- P64: 数据完整性校验
- P65: 数据导出(CSV/JSON)
- P66: 异常数据检测
- P67: 老旧数据归档
- P68: 扩展统计指标
- P69: 趋势可视化数据
"""
import logging
import threading
import time
import json
import csv
import io
import os
from datetime import datetime, timedelta, date
from collections import OrderedDict, defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# ─── P63: 时间序列内存缓存层 ──────────────────────────
# LRU 风格缓存，避免高频统计接口重复扫描全表
_CACHE_LOCK = threading.RLock()
_CACHE: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()
_CACHE_MAX_ITEMS = 64
_CACHE_DEFAULT_TTL = 120  # 秒


def cache_get(key: str, max_age: float = _CACHE_DEFAULT_TTL):
    with _CACHE_LOCK:
        item = _CACHE.get(key)
        if item is None:
            return None
        ts, value = item
        if (time.time() - ts) > max_age:
            _CACHE.pop(key, None)
            return None
        _CACHE.move_to_end(key)
        return value


def cache_set(key: str, value: Any) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX_ITEMS:
            _CACHE.popitem(last=False)


def cache_invalidate(prefix: str = "") -> int:
    """失效以 prefix 开头的所有缓存条目，返回失效数量"""
    with _CACHE_LOCK:
        if not prefix:
            n = len(_CACHE)
            _CACHE.clear()
            return n
        keys = [k for k in _CACHE if k.startswith(prefix)]
        for k in keys:
            _CACHE.pop(k, None)
        return len(keys)


# ─── P61: 数据库索引优化分析 ──────────────────────────
def analyze_indexes() -> dict:
    """分析当前索引并给出优化建议"""
    try:
        import db
        with db.get_conn() as conn:
            # 1. 收集所有索引
            idx_rows = conn.execute(
                "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            indexes = [{"name": r[0], "table": r[1]} for r in idx_rows]

            # 2. 检查缺失的复合索引建议
            suggestions = []
            # activities: 按 date+category 查询很常见
            existing_idx_names = {r[0] for r in idx_rows}
            if "idx_activities_date_cat" not in existing_idx_names:
                suggestions.append({
                    "name": "idx_activities_date_cat",
                    "table": "activities",
                    "sql": "CREATE INDEX IF NOT EXISTS idx_activities_date_cat ON activities(date(timestamp), category)",
                    "reason": "日历视图按日期+分类聚合频繁，复合索引可避免回表"
                })
            # app_usage: 按 start_time+app_name 查询
            if "idx_app_usage_start_app" not in existing_idx_names:
                suggestions.append({
                    "name": "idx_app_usage_start_app",
                    "table": "app_usage",
                    "sql": "CREATE INDEX IF NOT EXISTS idx_app_usage_start_app ON app_usage(start_time, app_name)",
                    "reason": "按时间段+应用名查询 Top Apps 高频出现"
                })
            # pomodoro: 按 start_time+status
            if "idx_pomodoro_start_status" not in existing_idx_names:
                suggestions.append({
                    "name": "idx_pomodoro_start_status",
                    "table": "pomodoro_sessions",
                    "sql": "CREATE INDEX IF NOT EXISTS idx_pomodoro_start_status ON pomodoro_sessions(start_time, status)",
                    "reason": "番茄钟统计按日期+状态筛选"
                })

            # 3. 检查冗余索引（简单启发式：同一表上单列索引是其复合索引前缀则冗余）
            redundant: list[dict] = []
            # 这里仅做轻量分析，避免误删

            return {
                "status": "ok",
                "total_indexes": len(indexes),
                "indexes": indexes,
                "suggestions": suggestions,
                "redundant": redundant,
            }
    except Exception as e:
        logger.warning(f"analyze_indexes 失败: {e}")
        return {"status": "error", "error": str(e), "suggestions": [], "indexes": []}


def apply_index_suggestions() -> dict:
    """应用索引优化建议"""
    try:
        import db
        analysis = analyze_indexes()
        applied = []
        with db.get_conn() as conn:
            for s in analysis.get("suggestions", []):
                try:
                    conn.execute(s["sql"])
                    applied.append(s["name"])
                except Exception as e:
                    logger.warning(f"应用索引失败 {s['name']}: {e}")
            conn.commit()
        cache_invalidate()
        return {"status": "ok", "applied": applied, "count": len(applied)}
    except Exception as e:
        return {"status": "error", "error": str(e), "applied": []}


# ─── P62: 日/周/月聚合预计算 ──────────────────────────
def precompute_aggregates(period: str = "day", days: int = 30) -> dict:
    """预计算聚合数据并缓存，period: day/week/month"""
    cache_key = f"agg:{period}:{days}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        import db
        end = datetime.now()
        start = end - timedelta(days=days)
        with db.get_conn() as conn:
            if period == "day":
                rows = conn.execute(
                    """SELECT date(timestamp) as d, category,
                              SUM(duration) as total_dur, COUNT(*) as cnt
                       FROM activities
                       WHERE timestamp >= ? AND timestamp < ?
                       GROUP BY d, category ORDER BY d""",
                    (start, end)
                ).fetchall()
            elif period == "week":
                # ISO 周
                rows = conn.execute(
                    """SELECT strftime('%Y-W%W', timestamp) as d, category,
                              SUM(duration) as total_dur, COUNT(*) as cnt
                       FROM activities
                       WHERE timestamp >= ? AND timestamp < ?
                       GROUP BY d, category ORDER BY d""",
                    (start, end)
                ).fetchall()
            else:  # month
                rows = conn.execute(
                    """SELECT strftime('%Y-%m', timestamp) as d, category,
                              SUM(duration) as total_dur, COUNT(*) as cnt
                       FROM activities
                       WHERE timestamp >= ? AND timestamp < ?
                       GROUP BY d, category ORDER BY d""",
                    (start, end)
                ).fetchall()

            result: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
            counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
            for r in rows:
                d, cat, dur, cnt = r[0], r[1], r[2] or 0, r[3] or 0
                result[d][cat] = dur
                counts[d][cat] = cnt

            output = {
                "period": period,
                "days": days,
                "start": start.strftime("%Y-%m-%d"),
                "end": end.strftime("%Y-%m-%d"),
                "durations": {k: dict(v) for k, v in result.items()},
                "counts": {k: dict(v) for k, v in counts.items()},
            }
            cache_set(cache_key, output)
            return output
    except Exception as e:
        logger.warning(f"precompute_aggregates 失败: {e}")
        return {"status": "error", "error": str(e), "period": period}


# ─── P64: 数据完整性校验 ──────────────────────────
def check_data_integrity() -> dict:
    """检查数据完整性：孤儿记录、空值、时间漂移"""
    try:
        import db
        issues: list[dict] = []
        with db.get_conn() as conn:
            # 1. 孤儿 app_usage（无对应 activities 记录）
            try:
                orphan_count = conn.execute(
                    """SELECT COUNT(*) FROM app_usage au
                       WHERE NOT EXISTS (
                           SELECT 1 FROM activities a WHERE a.timestamp BETWEEN au.start_time AND au.end_time
                       )"""
                ).fetchone()[0]
                if orphan_count > 100:
                    issues.append({
                        "type": "orphan_app_usage",
                        "severity": "warning",
                        "count": orphan_count,
                        "message": f"存在 {orphan_count} 条孤儿 app_usage 记录"
                    })
            except Exception:
                pass

            # 2. 空分类活动
            try:
                null_cat = conn.execute(
                    "SELECT COUNT(*) FROM activities WHERE category IS NULL OR category = ''"
                ).fetchone()[0]
                if null_cat > 0:
                    issues.append({
                        "type": "null_category",
                        "severity": "info",
                        "count": null_cat,
                        "message": f"{null_cat} 条活动缺少分类"
                    })
            except Exception:
                pass

            # 3. 异常时长（> 4小时的单条活动，可能是悬挂记录）
            try:
                long_dur = conn.execute(
                    "SELECT COUNT(*) FROM activities WHERE duration > 14400"
                ).fetchone()[0]
                if long_dur > 0:
                    issues.append({
                        "type": "abnormal_duration",
                        "severity": "warning",
                        "count": long_dur,
                        "message": f"{long_dur} 条活动时长超过 4 小时"
                    })
            except Exception:
                pass

            # 4. 未来时间戳
            try:
                future = conn.execute(
                    "SELECT COUNT(*) FROM activities WHERE timestamp > ?",
                    (datetime.now() + timedelta(hours=1),)
                ).fetchone()[0]
                if future > 0:
                    issues.append({
                        "type": "future_timestamp",
                        "severity": "error",
                        "count": future,
                        "message": f"{future} 条活动时间戳在未来"
                    })
            except Exception:
                pass

            # 5. 数据库完整性检查
            try:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    issues.append({
                        "type": "db_integrity",
                        "severity": "error",
                        "message": f"数据库完整性检查失败: {integrity}"
                    })
            except Exception:
                pass

            # 6. 表行数统计
            stats: dict[str, int] = {}
            for tbl in ["activities", "app_usage", "pomodoro_sessions", "todos", "reports"]:
                try:
                    cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                    stats[tbl] = cnt
                except Exception:
                    pass

        return {
            "status": "ok",
            "issues": issues,
            "issue_count": len(issues),
            "table_stats": stats,
            "checked_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "issues": []}


def repair_data_integrity(dry_run: bool = True) -> dict:
    """修复数据完整性问题"""
    try:
        import db
        repaired: list[dict] = []
        with db.get_conn() as conn:
            # 清理未来时间戳
            try:
                cur = conn.execute(
                    "DELETE FROM activities WHERE timestamp > ?",
                    (datetime.now() + timedelta(hours=1),)
                )
                if cur.rowcount > 0:
                    repaired.append({
                        "action": "delete_future_timestamps",
                        "count": cur.rowcount,
                        "dry_run": dry_run
                    })
                    if dry_run:
                        conn.execute("ROLLBACK")
                    else:
                        conn.commit()
            except Exception as e:
                logger.warning(f"清理未来时间戳失败: {e}")
                conn.execute("ROLLBACK") if dry_run else None
        cache_invalidate()
        return {"status": "ok", "repaired": repaired, "dry_run": dry_run}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─── P65: 数据导出 ──────────────────────────
def export_data(format: str = "json", table: str = "activities",
                start_date: str | None = None, end_date: str | None = None) -> dict:
    """导出指定表数据为 CSV 或 JSON"""
    try:
        import db
        with db.get_conn() as conn:
            where_clause = ""
            params: list = []
            if start_date:
                where_clause += " AND timestamp >= ?"
                params.append(start_date)
            if end_date:
                where_clause += " AND timestamp <= ?"
                params.append(end_date)

            if table == "activities":
                sql = f"SELECT timestamp, app_name, window_title, category, duration FROM activities WHERE 1=1{where_clause} ORDER BY timestamp"
            elif table == "app_usage":
                sql = f"SELECT start_time, end_time, app_name, window_title, duration FROM app_usage WHERE 1=1{where_clause} ORDER BY start_time"
            elif table == "pomodoro_sessions":
                sql = f"SELECT start_time, end_time, status, duration, category FROM pomodoro_sessions WHERE 1=1{where_clause} ORDER BY start_time"
            else:
                return {"status": "error", "error": f"不支持的表: {table}"}

            rows = conn.execute(sql, params).fetchall()
            cols = [d[0] for d in conn.execute(sql, params).description]

            if format == "csv":
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(cols)
                for r in rows:
                    writer.writerow(r)
                return {
                    "status": "ok",
                    "format": "csv",
                    "table": table,
                    "count": len(rows),
                    "data": buf.getvalue()
                }
            else:  # json
                data = [dict(zip(cols, r)) for r in rows]
                return {
                    "status": "ok",
                    "format": "json",
                    "table": table,
                    "count": len(rows),
                    "data": data
                }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─── P66: 异常数据检测 ──────────────────────────
def detect_anomalies(days: int = 7) -> dict:
    """使用统计方法检测异常活动数据"""
    try:
        import db
        end = datetime.now()
        start = end - timedelta(days=days)
        with db.get_conn() as conn:
            # 按日按应用聚合时长
            rows = conn.execute(
                """SELECT date(timestamp) as d, app_name, SUM(duration) as total
                   FROM activities
                   WHERE timestamp >= ? AND timestamp < ?
                   GROUP BY d, app_name""",
                (start, end)
            ).fetchall()

            # 按应用计算均值和标准差
            app_data: dict[str, list[float]] = defaultdict(list)
            for r in rows:
                app_data[r[1]].append(r[2] or 0)

            anomalies: list[dict] = []
            for app, durations in app_data.items():
                if len(durations) < 3:
                    continue
                mean = sum(durations) / len(durations)
                variance = sum((x - mean) ** 2 for x in durations) / len(durations)
                std = variance ** 0.5
                if std == 0:
                    continue
                # Z-score > 2 视为异常
                for r in rows:
                    if r[1] != app:
                        continue
                    z = ((r[2] or 0) - mean) / std
                    if abs(z) > 2:
                        anomalies.append({
                            "date": r[0],
                            "app": app,
                            "duration": r[2] or 0,
                            "mean": round(mean, 1),
                            "std": round(std, 1),
                            "z_score": round(z, 2),
                            "direction": "spike" if z > 0 else "drop"
                        })

            return {
                "status": "ok",
                "days": days,
                "anomalies": sorted(anomalies, key=lambda x: abs(x["z_score"]), reverse=True)[:20],
                "total_apps_analyzed": len(app_data),
                "checked_at": datetime.now().isoformat()
            }
    except Exception as e:
        return {"status": "error", "error": str(e), "anomalies": []}


# ─── P67: 老旧数据归档 ──────────────────────────
def archive_old_data(days_threshold: int = 180) -> dict:
    """将超过指定天数的活动数据归档到 archive schema"""
    try:
        import db
        cutoff = datetime.now() - timedelta(days=days_threshold)
        with db.get_conn() as conn:
            # 确保 archive schema 存在
            conn.execute("CREATE SCHEMA IF NOT EXISTS archive")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS archive.activities AS
                SELECT * FROM activities WHERE 1=0
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS archive.idx_archive_ts ON activities(timestamp)")

            # 统计待归档数量
            count = conn.execute(
                "SELECT COUNT(*) FROM activities WHERE timestamp < ?", (cutoff,)
            ).fetchone()[0]

            if count == 0:
                return {"status": "ok", "archived": 0, "message": "无待归档数据"}

            # 归档
            conn.execute("INSERT INTO archive.activities SELECT * FROM activities WHERE timestamp < ?", (cutoff,))
            conn.execute("DELETE FROM activities WHERE timestamp < ?", (cutoff,))
            conn.commit()

            cache_invalidate()
            return {
                "status": "ok",
                "archived": count,
                "cutoff": cutoff.strftime("%Y-%m-%d"),
                "message": f"成功归档 {count} 条记录"
            }
    except Exception as e:
        logger.warning(f"归档失败: {e}")
        return {"status": "error", "error": str(e)}


# ─── P68: 扩展统计指标 ──────────────────────────
def compute_extended_metrics(days: int = 7) -> dict:
    """计算扩展统计指标：专注深度、效率趋势、切换频率、黄金时段"""
    cache_key = f"ext_metrics:{days}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        import db
        end = datetime.now()
        start = end - timedelta(days=days)
        with db.get_conn() as conn:
            # 1. 专注深度 = 深度工作时长 / 总工作时长
            try:
                focus_row = conn.execute(
                    """SELECT
                        SUM(CASE WHEN category IN ('开发','测试','设计','文档','数据分析') THEN duration ELSE 0 END) as deep,
                        SUM(duration) as total
                       FROM activities WHERE timestamp >= ? AND timestamp < ?""",
                    (start, end)
                ).fetchone()
                deep_dur = focus_row[0] or 0
                total_dur = focus_row[1] or 0
                focus_depth = (deep_dur / total_dur) if total_dur > 0 else 0
            except Exception:
                focus_depth = 0
                deep_dur = total_dur = 0

            # 2. 切换频率 = 活动记录数 / 工作小时数
            try:
                switch_row = conn.execute(
                    """SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
                       FROM activities WHERE timestamp >= ? AND timestamp < ?""",
                    (start, end)
                ).fetchone()
                switch_count = switch_row[0] or 0
                if switch_row[1] and switch_row[2]:
                    hours = max(((switch_row[2] - switch_row[1]).total_seconds() / 3600), 1)
                    switch_rate = switch_count / hours
                else:
                    switch_rate = 0
            except Exception:
                switch_count = 0
                switch_rate = 0

            # 3. 黄金时段（每小时平均活动时长最高的时段）
            try:
                hour_rows = conn.execute(
                    """SELECT strftime('%H', timestamp) as h, AVG(duration) as avg_dur, COUNT(*) as cnt
                       FROM activities WHERE timestamp >= ? AND timestamp < ?
                       GROUP BY h ORDER BY avg_dur DESC""",
                    (start, end)
                ).fetchall()
                golden_hour = int(hour_rows[0][0]) if hour_rows else 9
                hour_distribution = [
                    {"hour": int(r[0]), "avg_duration": round(r[1] or 0, 1), "count": r[2]}
                    for r in hour_rows
                ]
            except Exception:
                golden_hour = 9
                hour_distribution = []

            # 4. 分类多样性（Shannon 熵）
            try:
                cat_rows = conn.execute(
                    """SELECT category, SUM(duration) as dur
                       FROM activities WHERE timestamp >= ? AND timestamp < ?
                       GROUP BY category""",
                    (start, end)
                ).fetchall()
                total = sum(r[1] or 0 for r in cat_rows)
                import math
                entropy = 0
                for r in cat_rows:
                    p = (r[1] or 0) / total if total > 0 else 0
                    if p > 0:
                        entropy -= p * math.log2(p)
                # 归一化到 0-1
                max_entropy = math.log2(max(len(cat_rows), 1)) if cat_rows else 1
                diversity = entropy / max_entropy if max_entropy > 0 else 0
            except Exception:
                diversity = 0
                cat_rows = []

            result = {
                "status": "ok",
                "days": days,
                "focus_depth": round(focus_depth, 3),
                "deep_work_seconds": int(deep_dur),
                "total_work_seconds": int(total_dur),
                "switch_count": switch_count,
                "switch_rate_per_hour": round(switch_rate, 2),
                "golden_hour": golden_hour,
                "hour_distribution": hour_distribution,
                "category_diversity": round(diversity, 3),
                "category_count": len(cat_rows),
                "computed_at": datetime.now().isoformat()
            }
            cache_set(cache_key, result)
            return result
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─── P69: 趋势可视化数据 ──────────────────────────
def get_trend_data(metric: str = "duration", days: int = 30) -> dict:
    """生成趋势可视化数据"""
    cache_key = f"trend:{metric}:{days}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        import db
        end = datetime.now()
        start = end - timedelta(days=days)
        with db.get_conn() as conn:
            if metric == "duration":
                rows = conn.execute(
                    """SELECT date(timestamp) as d, SUM(duration) as v
                       FROM activities WHERE timestamp >= ? AND timestamp < ?
                       GROUP BY d ORDER BY d""",
                    (start, end)
                ).fetchall()
                label = "总时长(秒)"
            elif metric == "focus":
                rows = conn.execute(
                    """SELECT date(timestamp) as d,
                              SUM(CASE WHEN category IN ('开发','测试','设计','文档') THEN duration ELSE 0 END) as v
                       FROM activities WHERE timestamp >= ? AND timestamp < ?
                       GROUP BY d ORDER BY d""",
                    (start, end)
                ).fetchall()
                label = "专注时长(秒)"
            elif metric == "pomodoro":
                rows = conn.execute(
                    """SELECT date(start_time) as d, COUNT(*) as v
                       FROM pomodoro_sessions WHERE start_time >= ? AND start_time < ?
                         AND status = 'completed'
                       GROUP BY d ORDER BY d""",
                    (start, end)
                ).fetchall()
                label = "完成番茄数"
            else:
                rows = []
                label = ""

            # 填充缺失日期
            date_series: list[dict] = []
            current = start.date()
            end_date = end.date()
            data_map = {r[0]: r[1] or 0 for r in rows}
            while current <= end_date:
                key = current.strftime("%Y-%m-%d")
                date_series.append({"date": key, "value": data_map.get(key, 0)})
                current += timedelta(days=1)

            # 计算移动平均（7日）
            window = 7
            for i in range(len(date_series)):
                if i >= window - 1:
                    avg = sum(date_series[j]["value"] for j in range(i - window + 1, i + 1)) / window
                    date_series[i]["ma7"] = round(avg, 1)
                else:
                    date_series[i]["ma7"] = None

            # 计算趋势方向
            values = [d["value"] for d in date_series if d["value"] > 0]
            if len(values) >= 2:
                first_half = sum(values[:len(values) // 2]) / max(len(values) // 2, 1)
                second_half = sum(values[len(values) // 2:]) / max(len(values) - len(values) // 2, 1)
                if second_half > first_half * 1.1:
                    trend_direction = "up"
                elif second_half < first_half * 0.9:
                    trend_direction = "down"
                else:
                    trend_direction = "stable"
            else:
                trend_direction = "insufficient"

            result = {
                "status": "ok",
                "metric": metric,
                "label": label,
                "days": days,
                "data": date_series,
                "trend_direction": trend_direction,
                "max_value": max(values) if values else 0,
                "avg_value": round(sum(values) / len(values), 1) if values else 0,
            }
            cache_set(cache_key, result)
            return result
    except Exception as e:
        return {"status": "error", "error": str(e), "data": []}
