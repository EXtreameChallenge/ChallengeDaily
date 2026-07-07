from flask import Blueprint, jsonify, request, Response
from datetime import date

import db
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


@bp.route('/excel', methods=['GET'])
def export_excel():
    """导出Excel（CSV格式，多Sheet用分页符分隔）"""
    import csv
    import io
    target_date = request.args.get('date', date.today().isoformat())

    output = io.StringIO()
    output.write('\ufeff')  # BOM for Excel

    # Sheet1: 活动记录
    writer = csv.writer(output)
    writer.writerow(['时间', '应用', '窗口标题', '分类', '摘要', '时长(秒)'])
    activities = db.get_activities(target_date, target_date)
    for a in activities:
        writer.writerow([a.get('timestamp', ''), a.get('app_name', ''), a.get('window_title', ''),
                        a.get('category', ''), a.get('summary', ''), a.get('interval_sec', 60)])

    output.write('\n\n')
    # Sheet2: 应用统计
    writer = csv.writer(output)
    writer.writerow(['应用', '窗口标题', '时长(秒)'])
    usage = db.get_app_usage(target_date, target_date)
    for u in usage:
        writer.writerow([u.get('app_name', ''), u.get('window_title', ''), u.get('duration_sec', 0)])

    output.write('\n\n')
    # Sheet3: 番茄钟
    writer = csv.writer(output)
    writer.writerow(['开始时间', '结束时间', '时长(分)', '任务', '分类', '状态'])
    sessions = db.get_pomodoro_sessions(target_date)
    for s in sessions:
        writer.writerow([s.get('start_time', ''), s.get('end_time', ''), s.get('duration_min', 0),
                        s.get('task', ''), s.get('category', ''), s.get('status', '')])

    content = output.getvalue()
    output.close()

    return Response(
        content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename=ChallengeDaily_{target_date}.csv'}
    )


@bp.route('/json', methods=['GET'])
def export_json():
    """导出JSON全量数据"""
    from datetime import timedelta
    target_date = request.args.get('date', date.today().isoformat())

    data = {
        'date': target_date,
        'activities': db.get_activities(target_date, target_date),
        'app_usage': db.get_app_usage(target_date, target_date),
        'pomodoro_sessions': db.get_pomodoro_sessions(target_date),
        'diary': db.get_diary(target_date),
        'todos': db.get_todos(),
        'achievements': db.get_achievements(),
        'countdowns': db.get_countdowns(),
    }
    return jsonify(data)

