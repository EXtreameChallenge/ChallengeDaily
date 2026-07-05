import re

from flask import Blueprint, jsonify, request
from datetime import date

from config import CATEGORIES
import config
from db import get_activities, insert_manual_activity
from routes.deps import safe_error, validate_date

bp = Blueprint('activities', __name__)


@bp.route("/api/activities")
def activities():
    target_date = request.args.get("date", date.today().isoformat())
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date format: {target_date}"}), 400

    # 分页参数（安全解析）
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        return jsonify({"error": "page 参数必须是正整数"}), 400
    try:
        per_page = max(1, min(500, int(request.args.get("per_page", 200))))
    except (ValueError, TypeError):
        return jsonify({"error": "per_page 参数必须是正整数"}), 400

    rows = get_activities(target_date, target_date)

    from app_tracker import get_display_name as _gdn
    result = []
    for r in rows:
        raw_name = r.get("app_name", "")
        interval = r["interval_sec"] if "interval_sec" in r.keys() and r["interval_sec"] else config.SCREENSHOT_INTERVAL_SEC
        result.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "app_name": _gdn(raw_name),
            "app_name_raw": raw_name,
            "window_title": r.get("window_title", ""),
            "category": r.get("category", "其他"),
            "ai_summary": r.get("summary"),
            "ai_detail": r.get("ai_detail", ""),
            "duration_min": interval / 60,
        })

    total = len(result)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated = result[start_idx:end_idx]

    return jsonify({
        "activities": paginated,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_more": page < total_pages,
        }
    })


@bp.route("/api/activities", methods=["POST"])
def create_activity():
    data = request.get_json(force=True)

    timestamp = data.get("timestamp", "").strip()
    category = data.get("category", "").strip()
    summary = data.get("summary", "").strip()

    if not timestamp or not category:
        return jsonify({"error": "时间和分类为必填项"}), 400

    if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", timestamp):
        return jsonify({"error": "时间格式应为 YYYY-MM-DD HH:MM:SS"}), 400

    try:
        from datetime import datetime as _dt
        _dt.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return jsonify({"error": "时间值无效，请检查日期和时间是否正确"}), 400

    if category not in CATEGORIES:
        return jsonify({"error": f"无效分类: {category}，可选: {', '.join(CATEGORIES)}"}), 400

    app_name = data.get("app_name", "手动补录").strip()
    window_title = data.get("window_title", "").strip()
    duration_min = max(5, min(480, int(data.get("duration_min", 30))))

    if not summary:
        summary = f"[手动补录] {category}"

    try:
        new_id = insert_manual_activity(
            timestamp=timestamp,
            app_name=app_name,
            window_title=window_title,
            category=category,
            summary=summary,
            duration_min=duration_min,
        )
        return jsonify({"status": "ok", "id": new_id}), 201
    except Exception as e:
        error_str = str(e)
        if "UNIQUE constraint" in error_str or "unique" in error_str.lower():
            return jsonify({"error": "该时间点已有记录，请选择其他时间"}), 409
        return jsonify({"error": safe_error(e, "手动补录失败，请重试")}), 500


@bp.route("/api/activities/<int:act_id>", methods=["PUT"])
def update_activity(act_id):
    data = request.get_json(force=True)
    category = data.get("category")
    summary = data.get("summary")

    updates = []
    params: list = []
    if category is not None:
        if category not in CATEGORIES:
            return jsonify({"error": f"无效分类: {category}，可选: {', '.join(CATEGORIES)}"}), 400
        updates.append("category = ?")
        params.append(category)
    if summary is not None:
        updates.append("summary = ?")
        params.append(summary)

    if not updates:
        return jsonify({"error": "没有要更新的字段"}), 400

    params.append(act_id)
    from db import get_conn
    with get_conn() as conn:
        cursor = conn.execute(
            f"UPDATE activities SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"error": "记录不存在"}), 404

    return jsonify({"status": "ok", "id": act_id})


@bp.route("/api/activities/<int:act_id>", methods=["DELETE"])
def delete_activity(act_id):
    """软删除：将记录移到 activities_deleted 表，支持 undo"""
    from db import get_conn

    with get_conn() as conn:
        # 查找原始记录
        row = conn.execute("SELECT * FROM activities WHERE id = ?", (act_id,)).fetchone()
        if not row:
            return jsonify({"error": "记录不存在"}), 404

        # 创建 deleted 表（如不存在）— 使用与 activities 相同的结构 + 额外字段
        conn.execute("""
            CREATE TABLE IF NOT EXISTS activities_deleted (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                screenshot TEXT,
                app_name TEXT,
                window_title TEXT,
                category TEXT,
                summary TEXT,
                created_at TEXT,
                original_id INTEGER,
                deleted_at TEXT DEFAULT (datetime('now'))
            )
        """)

        # 只插入 deleted 表中存在的列 + original_id
        deleted_cols = {"id", "timestamp", "screenshot", "app_name", "window_title", "category", "summary", "created_at"}
        insert_cols = []
        insert_vals = []
        for k in row.keys():
            if k in deleted_cols:
                insert_cols.append(k)
                insert_vals.append(row[k])
        insert_cols.append("original_id")
        insert_vals.append(act_id)

        placeholders = ', '.join(['?'] * len(insert_cols))
        col_names = ', '.join(insert_cols)
        conn.execute(
            f"INSERT INTO activities_deleted ({col_names}) VALUES ({placeholders})",
            insert_vals,
        )

        # 从原表删除
        conn.execute("DELETE FROM activities WHERE id = ?", (act_id,))
        conn.commit()

    return jsonify({"status": "ok", "id": act_id, "deleted": True})


@bp.route("/api/activities/<int:act_id>/undo", methods=["POST"])
def undo_delete_activity(act_id):
    """撤销删除：从 activities_deleted 表恢复到 activities"""
    from db import get_conn

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM activities_deleted WHERE original_id = ?", (act_id,)).fetchone()
        if not row:
            return jsonify({"error": "删除记录不存在"}), 404

        # 恢复到 activities（排除 deleted_at 和 original_id）
        skip_cols = {"deleted_at", "original_id"}
        activities_cols = {k for k in row.keys() if k not in skip_cols}
        restore_cols = []
        restore_vals = []
        for k in row.keys():
            if k in activities_cols:
                restore_cols.append(k)
                restore_vals.append(row[k])

        placeholders = ', '.join(['?'] * len(restore_cols))
        col_names = ', '.join(restore_cols)
        conn.execute(
            f"INSERT OR IGNORE INTO activities ({col_names}) VALUES ({placeholders})",
            restore_vals,
        )

        # 从 deleted 表删除
        conn.execute("DELETE FROM activities_deleted WHERE original_id = ?", (act_id,))
        conn.commit()

    return jsonify({"status": "ok", "id": act_id, "restored": True})


@bp.route("/api/activities/search")
def search_activities():
    q = request.args.get("q", "").strip()
    target_date = request.args.get("date", date.today().isoformat())
    if not q:
        return jsonify({"activities": []})

    from db import get_conn
    safe_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM activities "
            "WHERE date(timestamp) = ? AND (window_title LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\') "
            "ORDER BY timestamp DESC",
            (target_date, f"%{safe_q}%", f"%{safe_q}%"),
        ).fetchall()

    from app_tracker import get_display_name as _gdn_s
    result = []
    for r in rows:
        interval = r["interval_sec"] if "interval_sec" in r.keys() and r["interval_sec"] else config.SCREENSHOT_INTERVAL_SEC
        result.append({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "app_name": _gdn_s(r["app_name"] if "app_name" in r.keys() else ""),
            "window_title": r["window_title"] if "window_title" in r.keys() else "",
            "category": r["category"] if "category" in r.keys() else "其他",
            "ai_summary": r["summary"] if "summary" in r.keys() else None,
            "ai_detail": r["ai_detail"] if "ai_detail" in r.keys() else "",
            "duration_min": interval / 60,
        })
    return jsonify({"activities": result})


@bp.route("/api/timeline")
def timeline():
    start = request.args.get("startDate", date.today().isoformat())
    end = request.args.get("endDate", date.today().isoformat())
    data = get_activities(start, end)
    return jsonify(data)


@bp.route("/api/app-usage")
def app_usage():
    target_date = request.args.get("date", request.args.get("startDate", date.today().isoformat()))
    end_date = request.args.get("endDate", target_date)
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date format: {target_date}"}), 400

    from db import get_app_usage
    apps = get_app_usage(target_date, end_date)
    total_min = sum(a["duration_min"] for a in apps)

    from db import get_conn
    with get_conn() as conn:
        app_cat_rows = conn.execute(
            "SELECT app_name, category, COUNT(*) as cnt FROM activities "
            "WHERE date(timestamp) = ? "
            "GROUP BY app_name, category",
            (target_date,),
        ).fetchall()

    app_primary_cat = {}
    cat_counts: dict[str, dict[str, int]] = {}
    for r in app_cat_rows:
        an = r["app_name"]
        cat = r["category"] or "其他"
        if an not in cat_counts:
            cat_counts[an] = {}
        cat_counts[an][cat] = (cat_counts[an].get(cat) or 0) + r["cnt"]
    for an, cats in cat_counts.items():
        app_primary_cat[an] = max(cats, key=cats.get)

    from app_tracker import get_display_name as _gdn3
    result = []
    for a in apps:
        raw_name = a["app_name"]
        result.append({
            "app_name": _gdn3(raw_name),
            "app_name_raw": raw_name,
            "category": app_primary_cat.get(raw_name, "其他"),
            "duration_min": a["duration_min"],
            "percentage": round(a["duration_min"] / total_min * 100, 1) if total_min > 0 else 0,
        })
    return jsonify({"apps": result})
