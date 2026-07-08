from flask import Blueprint, jsonify, request, Response
from datetime import date, datetime, timedelta
import logging

import db
from db import export_activities_csv, export_app_usage_csv
from routes.deps import validate_date, safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('exports', __name__)

# 日期范围上限：防止一次性拉取超大数据导致内存/性能问题
_MAX_EXPORT_RANGE_DAYS = 90
# CSV 注入防护：以这些字符开头的单元格需要前置 ' 防止公式注入
_CSV_INJECTION_PREFIXES = ("=", "+", "-", "@")


def _csv_escape(value) -> str:
    """对单元格值做 CSV 注入防护：以 = + - @ 开头的单元格前置 ' 字符"""
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _CSV_INJECTION_PREFIXES:
        return "'" + s
    return s


def _validate_range(start_date: str, end_date: str):
    """校验日期范围：格式合法且跨度不超过上限"""
    if not validate_date(start_date) or not validate_date(end_date):
        return "日期格式无效"
    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d").date()
        ed = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return "日期格式无效"
    if sd > ed:
        return "起始日期不能晚于结束日期"
    if (ed - sd).days + 1 > _MAX_EXPORT_RANGE_DAYS:
        return f"日期范围不能超过 {_MAX_EXPORT_RANGE_DAYS} 天"
    return None


@bp.route("/api/export/activities")
def export_activities():
    start_date = request.args.get("start", date.today().isoformat())
    end_date = request.args.get("end", date.today().isoformat())
    err = _validate_range(start_date, end_date)
    if err:
        return jsonify({"error": err}), 400
    try:
        csv_data = export_activities_csv(start_date, end_date)
        return Response(
            csv_data.encode("utf-8-sig"),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=activities_{start_date}_{end_date}.csv"},
        )
    except Exception as e:
        logger.warning(f"export_activities failed: {type(e).__name__}")
        return jsonify({"error": safe_error(e, "导出失败")}), 500


@bp.route("/api/export/app-usage")
def export_app_usage_route():
    start_date = request.args.get("start", date.today().isoformat())
    end_date = request.args.get("end", date.today().isoformat())
    err = _validate_range(start_date, end_date)
    if err:
        return jsonify({"error": err}), 400
    try:
        csv_data = export_app_usage_csv(start_date, end_date)
        return Response(
            csv_data.encode("utf-8-sig"),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=app_usage_{start_date}_{end_date}.csv"},
        )
    except Exception as e:
        logger.warning(f"export_app_usage failed: {type(e).__name__}")
        return jsonify({"error": safe_error(e, "导出失败")}), 500


@bp.route('/api/exports/excel', methods=['GET'])
def export_excel():
    """导出Excel（CSV格式，多Sheet用分页符分隔）"""
    import csv
    import io
    target_date = request.args.get('date', date.today().isoformat())
    if not validate_date(target_date):
        return jsonify({"error": "日期格式无效"}), 400

    try:
        output = io.StringIO()
        output.write('\ufeff')  # BOM for Excel

        # Sheet1: 活动记录
        writer = csv.writer(output)
        writer.writerow(['时间', '应用', '窗口标题', '分类', '摘要', '时长(秒)'])
        activities = db.get_activities(target_date, target_date)
        for a in activities:
            writer.writerow([
                _csv_escape(a.get('timestamp', '')),
                _csv_escape(a.get('app_name', '')),
                _csv_escape(a.get('window_title', '')),
                _csv_escape(a.get('category', '')),
                _csv_escape(a.get('summary', '')),
                _csv_escape(a.get('interval_sec', 60)),
            ])

        output.write('\n\n')
        # Sheet2: 应用统计
        writer = csv.writer(output)
        writer.writerow(['应用', '窗口标题', '时长(秒)'])
        usage = db.get_app_usage(target_date, target_date)
        for u in usage:
            writer.writerow([
                _csv_escape(u.get('app_name', '')),
                _csv_escape(u.get('window_title', '')),
                _csv_escape(u.get('duration_sec', 0)),
            ])

        output.write('\n\n')
        # Sheet3: 番茄钟
        writer = csv.writer(output)
        writer.writerow(['开始时间', '结束时间', '时长(分)', '任务', '分类', '状态'])
        sessions = db.get_pomodoro_sessions(target_date)
        for s in sessions:
            writer.writerow([
                _csv_escape(s.get('start_time', '')),
                _csv_escape(s.get('end_time', '')),
                _csv_escape(s.get('duration_min', 0)),
                _csv_escape(s.get('task', '')),
                _csv_escape(s.get('category', '')),
                _csv_escape(s.get('status', '')),
            ])

        content = output.getvalue()
        output.close()

        return Response(
            content,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment;filename=ChallengeDaily_{target_date}.csv'}
        )
    except Exception as e:
        logger.warning(f"export_excel failed: {type(e).__name__}")
        return jsonify({"error": safe_error(e, "导出失败")}), 500


@bp.route('/api/exports/json', methods=['GET'])
def export_json():
    """导出JSON全量数据"""
    target_date = request.args.get('date', date.today().isoformat())
    if not validate_date(target_date):
        return jsonify({"error": "日期格式无效"}), 400
    try:
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
    except Exception as e:
        logger.warning(f"export_json failed: {type(e).__name__}")
        return jsonify({"error": safe_error(e, "导出失败")}), 500
