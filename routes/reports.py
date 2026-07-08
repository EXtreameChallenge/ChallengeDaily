from flask import Blueprint, jsonify, request
from datetime import date

from report import generate_daily_report, generate_weekly_report, generate_monthly_report, get_report_files
from db import get_reports
import db
from routes.deps import safe_error, validate_date

bp = Blueprint('reports', __name__)

# 模板白名单：防止任意字符串传入触发未预期分支或注入
_VALID_TEMPLATES = ('standard', 'simple', 'technical', 'okr', 'ai', 'deep')


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
