from flask import Blueprint, jsonify, request
from datetime import date

from report import generate_daily_report, generate_weekly_report, generate_monthly_report, get_report_files
from db import get_reports
from routes.deps import safe_error, validate_date

bp = Blueprint('reports', __name__)


@bp.route("/api/report/daily")
def report_daily():
    target_date = request.args.get("date", date.today().isoformat())
    template = request.args.get("template", "standard")
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date format: {target_date}"}), 400
    try:
        content = generate_daily_report(target_date, template=template)
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
    template = data.get("template") or request.args.get("template", "standard")
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date format: {target_date}"}), 400
    content = generate_daily_report(target_date, template=template)
    return jsonify({"status": "ok", "date": target_date, "length": len(content), "template": template})


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
