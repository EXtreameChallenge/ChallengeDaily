from flask import Blueprint, jsonify, request, Response
from datetime import date

from db import export_activities_csv, export_app_usage_csv
from routes.deps import validate_date

bp = Blueprint('exports', __name__)


@bp.route("/api/export/activities")
def export_activities():
    start_date = request.args.get("start", date.today().isoformat())
    end_date = request.args.get("end", date.today().isoformat())
    if not validate_date(start_date) or not validate_date(end_date):
        return jsonify({"error": "日期格式无效"}), 400
    csv_data = export_activities_csv(start_date, end_date)
    return Response(
        csv_data.encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=activities_{start_date}_{end_date}.csv"},
    )


@bp.route("/api/export/app-usage")
def export_app_usage_route():
    start_date = request.args.get("start", date.today().isoformat())
    end_date = request.args.get("end", date.today().isoformat())
    if not validate_date(start_date) or not validate_date(end_date):
        return jsonify({"error": "日期格式无效"}), 400
    csv_data = export_app_usage_csv(start_date, end_date)
    return Response(
        csv_data.encode("utf-8-sig"),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=app_usage_{start_date}_{end_date}.csv"},
    )
