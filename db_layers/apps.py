"""ChallengeDaily db layer — 应用分类规则、导出 CSV 与已知应用。"""
from db import *  # noqa: F401,F403
from db import _execute_with_retry  # noqa: F401
from db_layers.activities import get_activities, get_app_usage  # noqa: F401

def _sanitize_csv_cell(val):
    """防止 CSV 公式注入：以 = + - @ 开头的单元格加单引号前缀"""
    s = str(val) if val is not None else ""
    if s and s[0] in ('=', '+', '-', '@'):
        return "'" + s
    return s


def export_activities_csv(start_date: str, end_date: str) -> str:
    """导出活动记录为 CSV 格式"""
    import csv
    import io
    rows = get_activities(start_date, end_date)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["timestamp", "app_name", "window_title", "category", "summary"])
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "timestamp": _sanitize_csv_cell(r.get("timestamp", "")),
            "app_name": _sanitize_csv_cell(r.get("app_name", "")),
            "window_title": _sanitize_csv_cell(r.get("window_title", "")),
            "category": _sanitize_csv_cell(r.get("category", "")),
            "summary": _sanitize_csv_cell(r.get("summary", "")),
        })
    return output.getvalue()


def export_app_usage_csv(start_date: str, end_date: str) -> str:
    """导出应用使用时长为 CSV 格式"""
    import csv
    import io
    rows = get_app_usage(start_date, end_date)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["app_name", "duration_min"])
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "app_name": _sanitize_csv_cell(r.get("app_name", "")),
            "duration_min": _sanitize_csv_cell(r.get("duration_min", "")),
        })
    return output.getvalue()


# ── 应用分类规则 ──

def _serialize_json(value) -> str:
    """将 Python 对象序列化为 JSON 字符串"""
    import json
    return json.dumps(value, ensure_ascii=False)


def _parse_json(text: str, default):
    """安全解析 JSON 字符串"""
    import json
    try:
        return json.loads(text) if text else default
    except Exception:
        return default


def get_app_category_rules() -> list[dict]:
    """获取所有应用分类规则"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM app_category_rules ORDER BY updated_at DESC"
        ).fetchall()
    result = []
    for r in rows:
        item = dict(r)
        item["tags"] = _parse_json(item.get("tags"), [])
        item["window_rules"] = _parse_json(item.get("window_rules"), {})
        result.append(item)
    return result


def get_app_category_rule(app_name: str) -> dict | None:
    """获取单个应用的分类规则"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM app_category_rules WHERE app_name = ?",
            (app_name,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["tags"] = _parse_json(item.get("tags"), [])
    item["window_rules"] = _parse_json(item.get("window_rules"), {})
    return item


def upsert_app_category_rule(
    app_name: str,
    primary_category: str = "",
    tags: list[str] | None = None,
    window_rules: dict | None = None,
    display_name: str = "",
) -> dict:
    """创建或更新应用分类规则"""
    tags = tags or []
    window_rules = window_rules or {}
    # 确保主标签在候选标签里
    if primary_category and primary_category not in tags:
        tags = [primary_category] + tags
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO app_category_rules
                (app_name, display_name, primary_category, tags, window_rules, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(app_name) DO UPDATE SET
                display_name=excluded.display_name,
                primary_category=excluded.primary_category,
                tags=excluded.tags,
                window_rules=excluded.window_rules,
                updated_at=excluded.updated_at
            """,
            (
                app_name,
                display_name,
                primary_category,
                _serialize_json(tags),
                _serialize_json(window_rules),
            ),
        )
        conn.commit()
    return get_app_category_rule(app_name)


def delete_app_category_rule(app_name: str) -> bool:
    """删除应用分类规则"""
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM app_category_rules WHERE app_name = ?",
            (app_name,),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_known_apps() -> list[dict]:
    """获取所有出现过应用名（来自 app_usage）及其规则"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT app_name FROM app_usage ORDER BY app_name"
        ).fetchall()
    rules = {r["app_name"]: r for r in get_app_category_rules()}
    result = []
    for r in rows:
        name = r["app_name"]
        result.append({
            "app_name": name,
            "rule": rules.get(name),
        })
    return result


# ── 番茄钟 ──

