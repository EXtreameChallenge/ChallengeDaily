from flask import Blueprint, jsonify, request
from datetime import date
import json
import logging

from report import generate_daily_report, generate_weekly_report, generate_monthly_report, get_report_files, enhance_report_with_ai_analysis
from db import get_reports, get_daily_summary, search_reports
import db
import config
from routes.deps import safe_error, validate_date

bp = Blueprint('reports', __name__)
logger = logging.getLogger(__name__)

# 模板白名单：防止任意字符串传入触发未预期分支或注入
_VALID_TEMPLATES = ('standard', 'simple', 'technical', 'okr', 'ai', 'deep')


def _get_pomodoro_summary_for_date(date_str: str) -> dict:
    """查询当日番茄会话汇总，供日报 AI 上下文与前端可视化使用。

    返回:
      {"total": int, "completed": int, "total_min": int, "distractions": int}
    任何异常都返回零值，确保日报生成不会因番茄查询失败而中断。
    """
    try:
        with db.get_conn() as conn:
            rows = conn.execute("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed,
                       SUM(duration_min) as total_min,
                       SUM(interrupted_count) as distractions
                FROM pomodoro_sessions
                WHERE date(start_time) = ?
            """, (date_str,)).fetchone()
            return {
                "total": rows[0] or 0,
                "completed": rows[1] or 0,
                "total_min": rows[2] or 0,
                "distractions": rows[3] or 0,
            }
    except Exception as e:
        logger.warning(f"查询番茄汇总失败: {e}")
        return {"total": 0, "completed": 0, "total_min": 0, "distractions": 0}


def _validate_template(template: str) -> str:
    """校验模板参数，非法值回退 standard"""
    return template if template in _VALID_TEMPLATES else 'standard'


@bp.route("/api/report/daily")
def report_daily():
    target_date = request.args.get("date", date.today().isoformat())
    template = _validate_template(request.args.get("template", "standard"))
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date format: {target_date}"}), 400
    try:
        content = generate_daily_report(target_date, template=template)
        content += _get_pomodoro_section(target_date)
        return jsonify({"date": target_date, "content": content, "template": template})
    except Exception as e:
        return jsonify({"error": safe_error(e, "日报生成失败")}), 500


@bp.route("/api/report/daily/content")
def report_daily_content():
    today = date.today().isoformat()
    reports = get_reports(today, today)
    if reports:
        return jsonify({"date": today, "content": reports[0]["content"], "template": "standard"})

    file_reports = get_report_files()
    if file_reports:
        latest = file_reports[0]
        try:
            with open(latest["path"], "r", encoding="utf-8") as f:
                file_content = f.read()
            return jsonify({"date": today, "content": file_content, "template": "standard"})
        except Exception:
            pass

    return jsonify({"date": today, "content": "", "template": "standard"})


@bp.route("/api/report")
def report_list():
    start = request.args.get("startDate", date.today().isoformat())
    end = request.args.get("endDate", date.today().isoformat())
    db_reports = get_reports(start, end)
    file_reports = get_report_files()
    return jsonify({
        "db_reports": db_reports,
        "file_reports": file_reports,
    })


@bp.route("/api/report/search")
def report_search():
    """P8-1：报告全文检索。

    GET /api/report/search?q=关键词&limit=20
    返回 [{id, report_date, content, created_at, snippet}]
    snippet 中匹配关键词用【】包裹高亮
    """
    q = request.args.get("q", "").strip()
    try:
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        limit = 20
    # 限制 limit 范围，防止恶意拉取
    limit = max(1, min(limit, 100))
    if not q:
        return jsonify({"results": [], "query": "", "count": 0})
    if len(q) > 100:
        return jsonify({"error": "关键词过长（最多 100 字符）"}), 400
    try:
        results = search_reports(q, limit=limit)
        return jsonify({
            "results": results,
            "query": q,
            "count": len(results),
        })
    except Exception as e:
        return jsonify({"error": safe_error(e, "检索失败")}), 500


@bp.route("/api/report/pomodoro-summary")
def report_pomodoro_summary():
    """返回当日番茄会话汇总（供 Report.tsx 番茄统计卡片渲染）"""
    target_date = request.args.get("date", date.today().isoformat())
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date format: {target_date}"}), 400
    return jsonify({"date": target_date, **_get_pomodoro_summary_for_date(target_date)})


@bp.route("/api/generate-report", methods=["POST"])
def generate_report():
    data = request.get_json(silent=True) or {}
    target_date = data.get("date") or request.args.get("date", date.today().isoformat())
    template = _validate_template(data.get("template") or request.args.get("template", "standard"))
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date format: {target_date}"}), 400
    try:
        content = generate_daily_report(target_date, template=template)
        return jsonify({"status": "ok", "date": target_date, "length": len(content), "template": template})
    except Exception as e:
        return jsonify({"error": safe_error(e, "日报生成失败")}), 500


@bp.route("/api/report/weekly")
def report_weekly():
    start_date = request.args.get("date", date.today().isoformat())
    if not validate_date(start_date):
        return jsonify({"error": f"Invalid date format: {start_date}"}), 400
    try:
        content = generate_weekly_report(start_date)
        # 附加周目标对比段落
        from datetime import datetime, timedelta
        d = datetime.strptime(start_date, "%Y-%m-%d").date()
        monday = d - timedelta(days=d.weekday())
        goal = _get_weekly_goal_comparison(monday.isoformat())
        if goal["total"] > 0:
            content += (
                f"\n\n## 周目标完成情况\n"
                f"- 本周待办总数：{goal['total']}\n"
                f"- 已完成：{goal['done']}\n"
                f"- 完成率：{goal['completion_rate']}%\n"
            )
        # P7-2: AI 深度分析
        from datetime import timedelta as _td
        week_end = (monday + _td(days=6)).isoformat()
        summary = get_daily_summary(monday.isoformat(), week_end)
        interval_min = config.SCREENSHOT_INTERVAL_SEC / 60
        cat_data = {k: v * interval_min for k, v in summary.get("categories", {}).items()}
        content = enhance_report_with_ai_analysis(content, "weekly", f"{monday.isoformat()}~{week_end}", cat_data)
        return jsonify({"date": start_date, "content": content, "type": "weekly"})
    except Exception as e:
        return jsonify({"error": safe_error(e, "周报生成失败")}), 500


@bp.route("/api/report/monthly")
def report_monthly():
    import re
    year_month = request.args.get("month", date.today().strftime("%Y-%m"))
    if not re.match(r"^\d{4}-\d{2}$", year_month):
        return jsonify({"error": f"Invalid month format: {year_month}, expected YYYY-MM"}), 400
    try:
        content = generate_monthly_report(year_month)
        # P7-2: AI 深度分析
        import calendar as _cal
        year, month = map(int, year_month.split("-"))
        last_day = _cal.monthrange(year, month)[1]
        month_start = f"{year_month}-01"
        month_end = f"{year_month}-{last_day:02d}"
        summary = get_daily_summary(month_start, month_end)
        interval_min = config.SCREENSHOT_INTERVAL_SEC / 60
        cat_data = {k: v * interval_min for k, v in summary.get("categories", {}).items()}
        content = enhance_report_with_ai_analysis(content, "monthly", year_month, cat_data)
        return jsonify({"month": year_month, "content": content, "type": "monthly"})
    except Exception as e:
        return jsonify({"error": safe_error(e, "月报生成失败")}), 500


@bp.route("/api/report/date/<string:d>")
def report_by_date(d):
    if not validate_date(d):
        return jsonify({"error": f"Invalid date format: {d}"}), 400
    reports = get_reports(d, d)
    if reports:
        return jsonify({"date": d, "content": reports[0]["content"], "template": "standard"})
    return jsonify({"date": d, "content": "", "template": "standard"})


def _get_pomodoro_section(target_date):
    """获取专注统计板块（专注+日报联动）"""
    sessions = db.get_pomodoro_sessions(target_date)
    completed = [s for s in sessions if s.get('status') == 'completed']
    total_min = sum(s.get('duration_min', 0) for s in completed)
    count = len(completed)
    if count == 0:
        return "\n\n## 专注统计\n今日暂无专注记录。"

    tasks = [s.get('task', '') for s in completed if s.get('task')]
    task_text = '、'.join(tasks[:5]) if tasks else '未指定任务'

    return f"""
## 专注统计
- 完成番茄钟：{count} 个
- 专注总时长：{total_min} 分钟
- 主要任务：{task_text}
- 平均专注时长：{total_min // count if count else 0} 分钟/个
"""


def _get_weekly_goal_comparison(week_start: str) -> dict:
    """周报目标对比：统计本周待办完成情况

    返回：{total, done, completion_rate}
    """
    try:
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as total, "
                "       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as done "
                "FROM todos WHERE week_start = ?",
                (week_start,),
            ).fetchone()
            total = row['total'] if row else 0
            done = row['done'] if row else 0
            return {
                'total': total,
                'done': done or 0,
                'completion_rate': round((done or 0) / total * 100, 1) if total > 0 else 0,
            }
    except Exception:
        return {'total': 0, 'done': 0, 'completion_rate': 0}


@bp.route("/api/report/weekly-goal")
def weekly_goal_comparison():
    """周报目标对比接口（供前端周报页展示）"""
    from datetime import datetime, timedelta
    start_date = request.args.get("date", date.today().isoformat())
    if not validate_date(start_date):
        return jsonify({"error": f"Invalid date format: {start_date}"}), 400
    # 转换为周一
    d = datetime.strptime(start_date, "%Y-%m-%d").date()
    monday = d - timedelta(days=d.weekday())
    week_start = monday.isoformat()
    return jsonify(_get_weekly_goal_comparison(week_start))


# ── 自定义日报模板管理（存储在 settings 表，key='report_templates'） ──

_REPORT_TEMPLATES_KEY = 'report_templates'


def _load_custom_templates(conn) -> list:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (_REPORT_TEMPLATES_KEY,)
    ).fetchone()
    if row and row[0]:
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _save_custom_templates(conn, templates: list):
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (_REPORT_TEMPLATES_KEY, json.dumps(templates, ensure_ascii=False)),
    )
    conn.commit()


@bp.route("/api/reports/templates", methods=["GET", "POST", "DELETE"])
def custom_templates():
    """自定义日报模板管理（GET 列表 / POST 新增 / DELETE 删除）"""
    try:
        with db.get_conn() as conn:
            if request.method == "GET":
                templates = _load_custom_templates(conn)
                return jsonify({"templates": templates})

            if request.method == "POST":
                data = request.get_json(silent=True) or {}
                name = (data.get("name") or "").strip()[:50]
                content = (data.get("content") or "").strip()[:5000]
                if not name or not content:
                    return jsonify({"error": "名称和内容不能为空"}), 400
                templates = _load_custom_templates(conn)
                new_id = (max((t.get("id", 0) for t in templates), default=0) + 1) if templates else 1
                templates.append({"id": new_id, "name": name, "content": content})
                _save_custom_templates(conn, templates)
                return jsonify({"status": "saved", "templates": templates})

            # DELETE
            tpl_id = request.args.get("id", type=int)
            templates = _load_custom_templates(conn)
            templates = [t for t in templates if t.get("id") != tpl_id]
            _save_custom_templates(conn, templates)
            return jsonify({"status": "deleted", "templates": templates})
    except Exception as e:
        logger.error(f"自定义模板操作失败: {e}", exc_info=True)
        return jsonify({"error": "操作失败"}), 500
