"""分类规则重跑服务 — arbtt 风格

原始 activities 表保留 app_name + window_title，可按最新规则批量重分类。
设计参考 arbtt：原始日志永久保留，分类规则可重跑，永不丢失原始信号。

约束：
- dry_run=True 时只读不写，仅返回统计与变更预览
- 批量 UPDATE 必须在事务中执行（with db.get_conn() as conn: ... conn.commit()）
- 大批量数据分批处理，每 BATCH_SIZE 条 commit 一次，避免长事务阻塞写入
- 重分类基于 app_name + window_title 重新调用 classifier.classify()，
  不再使用历史 AI 结果（AI 结果未单独存储，且规则变更后旧 AI 结果已无意义）
"""
import logging
from datetime import datetime, timedelta

import db
from classifier import classify

logger = logging.getLogger(__name__)

# 每批 commit 一次，平衡性能与事务粒度
BATCH_SIZE = 500
# 预览返回的变更条目上限，避免响应体过大
PREVIEW_LIMIT = 200


def _build_query(target_date: str | None, app_name: str | None, days: int | None):
    """构造 SELECT 语句与参数

    - target_date: 'YYYY-MM-DD'，仅重分类该日（优先级高于 days）
    - app_name: 仅重分类指定应用（大小写不敏感精确匹配）
    - days: 重分类最近 N 天（target_date 为空时生效）
    """
    sql = "SELECT id, app_name, window_title, category FROM activities"
    conditions = []
    params: list = []

    if target_date:
        conditions.append("date(timestamp) = ?")
        params.append(target_date)
    elif days and days > 0:
        # 以本地日期计算最近 N 天
        try:
            end = datetime.now()
            start = end - timedelta(days=days)
            conditions.append("timestamp >= ?")
            params.append(start.strftime("%Y-%m-%d 00:00:00"))
        except Exception as e:
            logger.warning(f"days 参数解析失败，忽略该过滤: {e}")

    if app_name:
        # 大小写不敏感匹配（Windows 进程名大小写不稳定）
        conditions.append("LOWER(app_name) = LOWER(?)")
        params.append(app_name)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY id ASC"
    return sql, params


def reclassify_batch(target_date: str | None = None,
                     app_name: str | None = None,
                     dry_run: bool = False) -> dict:
    """批量重分类

    - target_date: 指定日期 (YYYY-MM-DD)，None=全部
    - app_name: 仅重分类指定应用，None=所有
    - dry_run: True=只返回统计不写库

    返回: {total, changed, by_category, dry_run}
    """
    sql, params = _build_query(target_date, app_name, days=None)

    with db.get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    total = len(rows)
    changed = 0
    by_category: dict[str, int] = {}
    pending: list[tuple[str, int]] = []  # (new_category, id)

    for r in rows:
        old_cat = r["category"] or ""
        # 重分类不传 ai_category：规则变更后旧 AI 结果不可信，
        # 仅依据 app_name + window_title 重新应用规则
        new_cat = classify(r["app_name"] or "", "", r["window_title"] or "")

        by_category[new_cat] = by_category.get(new_cat, 0) + 1

        if new_cat != old_cat:
            changed += 1
            if not dry_run:
                pending.append((new_cat, r["id"]))

        if not dry_run and len(pending) >= BATCH_SIZE:
            _flush_batch(pending)
            pending.clear()

    # 提交剩余批次
    if not dry_run and pending:
        _flush_batch(pending)

    logger.info(
        "reclassify_batch 完成: total=%d changed=%d dry_run=%s date=%s app=%s",
        total, changed, dry_run, target_date, app_name,
    )

    return {
        "total": total,
        "changed": changed,
        "by_category": by_category,
        "dry_run": dry_run,
    }


def _flush_batch(batch: list[tuple[str, int]]) -> None:
    """批量 UPDATE 一批记录（事务保护）"""
    if not batch:
        return
    with db.get_conn() as conn:
        try:
            conn.executemany(
                "UPDATE activities SET category=? WHERE id=?",
                batch,
            )
            conn.commit()
        except Exception:
            # 回滚当前批次，避免部分提交导致数据不一致
            conn.rollback()
            logger.error("批量更新失败，已回滚 %d 条记录", len(batch), exc_info=True)
            raise


def reclassify_app(app_name: str, dry_run: bool = False) -> dict:
    """重分类指定应用的所有记录"""
    if not app_name or not app_name.strip():
        return {
            "total": 0,
            "changed": 0,
            "by_category": {},
            "dry_run": dry_run,
            "error": "app_name 不能为空",
        }
    return reclassify_batch(app_name=app_name.strip(), dry_run=dry_run)


def get_reclassify_preview(target_date: str | None = None,
                           app_name: str | None = None) -> dict:
    """预览重分类结果（不写库）

    返回: {
        total, would_change,
        changes: [{id, app_name, old_category, new_category, window_title}],
        by_category: {new_category: count}
    }
    """
    sql, params = _build_query(target_date, app_name, days=None)

    with db.get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    total = len(rows)
    would_change = 0
    changes: list[dict] = []
    by_category: dict[str, int] = {}

    for r in rows:
        old_cat = r["category"] or ""
        new_cat = classify(r["app_name"] or "", "", r["window_title"] or "")
        by_category[new_cat] = by_category.get(new_cat, 0) + 1

        if new_cat != old_cat:
            would_change += 1
            # 限制返回条目数，避免响应体过大
            if len(changes) < PREVIEW_LIMIT:
                changes.append({
                    "id": r["id"],
                    "app_name": r["app_name"] or "",
                    "old_category": old_cat,
                    "new_category": new_cat,
                    "window_title": r["window_title"] or "",
                })

    return {
        "total": total,
        "would_change": would_change,
        "changes": changes,
        "truncated": would_change > len(changes),
        "by_category": by_category,
    }


def reclassify_history(days: int = 30) -> dict:
    """重分类最近 N 天的历史数据"""
    if days <= 0:
        days = 30
    # 通过 target_date=None + days 走 _build_query 的 days 分支
    sql, params = _build_query(target_date=None, app_name=None, days=days)

    with db.get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    total = len(rows)
    changed = 0
    by_category: dict[str, int] = {}
    pending: list[tuple[str, int]] = []

    for r in rows:
        old_cat = r["category"] or ""
        new_cat = classify(r["app_name"] or "", "", r["window_title"] or "")
        by_category[new_cat] = by_category.get(new_cat, 0) + 1

        if new_cat != old_cat:
            changed += 1
            pending.append((new_cat, r["id"]))

        if len(pending) >= BATCH_SIZE:
            _flush_batch(pending)
            pending.clear()

    if pending:
        _flush_batch(pending)

    logger.info("reclassify_history 完成: days=%d total=%d changed=%d", days, total, changed)

    return {
        "total": total,
        "changed": changed,
        "by_category": by_category,
        "days": days,
        "dry_run": False,
    }


def get_status() -> dict:
    """返回分类规则统计

    - 各分类的记录数分布
    - 总记录数
    - 规则覆盖情况（有多少 app_name 命中规则）
    """
    with db.get_conn() as conn:
        # 各分类分布
        cat_rows = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM activities "
            "GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
        total_row = conn.execute(
            "SELECT COUNT(*) as total FROM activities"
        ).fetchone()
        # 命中默认规则的应用数（粗略统计）
        app_rows = conn.execute(
            "SELECT COUNT(DISTINCT app_name) as cnt FROM activities "
            "WHERE app_name IS NOT NULL AND app_name != ''"
        ).fetchone()

    category_dist = {dict(r)["category"] or "(空)": dict(r)["cnt"] for r in cat_rows}
    total = dict(total_row)["total"] if total_row else 0
    distinct_apps = dict(app_rows)["cnt"] if app_rows else 0

    return {
        "total_activities": total,
        "distinct_apps": distinct_apps,
        "category_distribution": category_dist,
        "batch_size": BATCH_SIZE,
        "preview_limit": PREVIEW_LIMIT,
    }
