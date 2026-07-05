from flask import Blueprint, jsonify, request
from datetime import date

import config
from db import get_activities, get_daily_summary, get_conn, get_app_usage
from routes.deps import validate_date

bp = Blueprint('stats', __name__)


@bp.route("/api/stats/today")
def stats_today():
    today = date.today().isoformat()
    return _build_stats(today)


@bp.route("/api/stats/date/<string:d>")
def stats_date(d):
    if not validate_date(d):
        return jsonify({"error": f"Invalid date format: {d}, expected YYYY-MM-DD"}), 400
    return _build_stats(d)


def _build_stats(target_date: str):
    summary = get_daily_summary(target_date, target_date)
    apps = get_app_usage(target_date, target_date)
    with get_conn() as conn:
        cat_rows = conn.execute(
            "SELECT category, COUNT(*) as cnt FROM activities "
            "WHERE date(timestamp) = ? "
            "GROUP BY category ORDER BY cnt DESC",
            (target_date,),
        ).fetchall()

    categories = {}
    total_duration_min = 0
    for r in cat_rows:
        cat = r["category"] or "其他"
        dur_min = round(r["cnt"] * config.SCREENSHOT_INTERVAL_SEC / 60, 1)
        categories[cat] = dur_min
        total_duration_min += dur_min

    focus_sessions = 0
    longest_focus_min = 0
    act_rows = get_activities(target_date, target_date)
    if act_rows:
        current_cat = None
        current_count = 0
        max_count = 0
        for act in act_rows:
            if act["category"] == current_cat:
                current_count += 1
            else:
                if current_count * config.SCREENSHOT_INTERVAL_SEC >= 900:
                    focus_sessions += 1
                current_cat = act["category"]
                current_count = 1
            max_count = max(max_count, current_count)
        if current_count * config.SCREENSHOT_INTERVAL_SEC >= 900:
            focus_sessions += 1
        longest_focus_min = round(max_count * config.SCREENSHOT_INTERVAL_SEC / 60, 1)

    from app_tracker import get_display_name as _gdn2
    top_apps = [
        {"app_name": _gdn2(a["app_name"]), "duration_min": a["duration_min"]}
        for a in apps[:5]
    ]

    return jsonify({
        "date": target_date,
        "total_duration_min": round(total_duration_min, 1),
        "categories": categories,
        "top_apps": top_apps,
        "focus_sessions": focus_sessions,
        "longest_focus_min": longest_focus_min,
    })


@bp.route("/api/stats/hourly")
def stats_hourly():
    target_date = request.args.get("date", date.today().isoformat())
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date format: {target_date}"}), 400
    from db import get_hourly_activity
    data = get_hourly_activity(target_date)
    return jsonify({"date": target_date, "hours": data})


@bp.route("/api/stats/trend")
def stats_trend():
    days = min(int(request.args.get("days", "7")), 30)
    from db import get_multi_day_stats
    data = get_multi_day_stats(days)
    for item in data:
        item["duration_min"] = round(item["count"] * config.SCREENSHOT_INTERVAL_SEC / 60, 1)
    return jsonify({"days": days, "trend": data})


@bp.route("/api/stats/rhythm")
def stats_rhythm():
    target_date = request.args.get("date", date.today().isoformat())
    if not validate_date(target_date):
        return jsonify({"error": f"Invalid date format: {target_date}"}), 400
    from db import get_conn
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS hour, COUNT(*) as cnt "
            "FROM activities WHERE date(timestamp) = ? GROUP BY hour",
            (target_date,),
        ).fetchall()

    periods = {"早晨 (6-12)": 0, "下午 (12-18)": 0, "晚间 (18-22)": 0, "夜间 (22-6)": 0}
    for r in rows:
        h = r["hour"]
        cnt = r["cnt"]
        if 6 <= h < 12:
            periods["早晨 (6-12)"] += cnt
        elif 12 <= h < 18:
            periods["下午 (12-18)"] += cnt
        elif 18 <= h < 22:
            periods["晚间 (18-22)"] += cnt
        else:
            periods["夜间 (22-6)"] += cnt

    total = sum(periods.values()) or 1
    result = [
        {"period": k, "count": v, "percentage": round(v / total * 100, 1),
         "duration_min": round(v * config.SCREENSHOT_INTERVAL_SEC / 60, 1)}
        for k, v in periods.items()
    ]
    peak = max(result, key=lambda x: x["count"])
    return jsonify({"date": target_date, "periods": result, "peak_period": peak["period"]})


@bp.route("/api/daily-summary")
def daily_summary():
    start = request.args.get("startDate", date.today().isoformat())
    end = request.args.get("endDate", date.today().isoformat())
    data = get_daily_summary(start, end)
    return jsonify(data)
