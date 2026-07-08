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
        {"app_name": _gdn2(a["app_name"]), "app_name_raw": a["app_name"], "duration_min": a["duration_min"]}
        for a in apps[:15]
    ]

    # 当前活动：最近一条记录的摘要
    current_activity = None
    with get_conn() as conn:
        cur_row = conn.execute(
            "SELECT app_name, category, ai_detail FROM activities "
            "WHERE date(timestamp) = ? ORDER BY timestamp DESC LIMIT 1",
            (target_date,),
        ).fetchone()
    if cur_row:
        from app_tracker import get_display_name as _gdn3
        app_disp = _gdn3(cur_row["app_name"])
        cat_disp = cur_row["category"] or "其他"
        detail = cur_row["ai_detail"] or ""
        # 取 ai_detail 的首句作为简短描述
        short_detail = ""
        if detail:
            for sep in ["。", "，", "；", ".", ","]:
                idx = detail.find(sep)
                if idx > 0 and idx < 30:
                    short_detail = detail[:idx]
                    break
            if not short_detail:
                short_detail = detail[:25]
        current_activity = f"[{cat_disp}] {app_disp}" + (f" · {short_detail}" if short_detail else "")

    return jsonify({
        "date": target_date,
        "total_duration_min": round(total_duration_min, 1),
        "categories": categories,
        "top_apps": top_apps,
        "focus_sessions": focus_sessions,
        "longest_focus_min": longest_focus_min,
        "total_activities": len(act_rows) if act_rows else 0,
        "current_activity": current_activity,
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
    try:
        days = min(int(request.args.get("days", "7")), 30)
        if days < 1:
            days = 7
    except (ValueError, TypeError):
        days = 7
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

    periods = {
        "凌晨 (0-6)": 0,
        "早晨 (6-8)": 0,
        "上午 (8-11)": 0,
        "中午 (11-14)": 0,
        "下午 (14-19)": 0,
        "晚间 (19-22)": 0,
        "夜间 (22-24)": 0,
    }
    for r in rows:
        h = r["hour"]
        cnt = r["cnt"]
        if 6 <= h < 8:
            periods["早晨 (6-8)"] += cnt
        elif 8 <= h < 11:
            periods["上午 (8-11)"] += cnt
        elif 11 <= h < 14:
            periods["中午 (11-14)"] += cnt
        elif 14 <= h < 19:
            periods["下午 (14-19)"] += cnt
        elif 19 <= h < 22:
            periods["晚间 (19-22)"] += cnt
        elif 22 <= h < 24:
            periods["夜间 (22-24)"] += cnt
        else:
            periods["凌晨 (0-6)"] += cnt

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
    # 日期格式校验：防止非法字符串直接落库或导致 SQL 异常
    if not validate_date(start) or not validate_date(end):
        return jsonify({"error": "日期格式无效，需 YYYY-MM-DD"}), 400
    data = get_daily_summary(start, end)
    return jsonify(data)


@bp.route("/api/greeting")
def greeting():
    """生成结合近期数据的 AI 温馨导语"""
    from datetime import timedelta
    from ai_client import generate_greeting

    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()
    today_str = today.isoformat()

    # 今日数据
    today_summary = get_daily_summary(today_str, today_str)
    today_apps = get_app_usage(today_str, today_str)
    today_min = round(today_summary["total"] * config.SCREENSHOT_INTERVAL_SEC / 60, 1)

    # 昨日数据
    yesterday_summary = get_daily_summary(yesterday, yesterday)
    yesterday_min = round(yesterday_summary["total"] * config.SCREENSHOT_INTERVAL_SEC / 60, 1)

    # 最近三天数据
    recent3_total = 0
    recent3_categories: dict[str, int] = {}
    for offset in range(3):
        d = (today - timedelta(days=offset)).isoformat()
        s = get_daily_summary(d, d)
        recent3_total += s["total"]
        for cat, cnt in s["categories"].items():
            recent3_categories[cat] = recent3_categories.get(cat, 0) + cnt

    recent3_min = round(recent3_total * config.SCREENSHOT_INTERVAL_SEC / 60, 1)
    top_categories = sorted(recent3_categories.keys(), key=lambda c: recent3_categories[c], reverse=True)[:3]
    top_apps = [a["app_name"] for a in sorted(today_apps, key=lambda x: x["duration_min"], reverse=True)[:3]]

    from app_tracker import get_display_name as _gdn_greeting
    context = {
        "time": request.args.get("time", ""),
        "date": request.args.get("date", ""),
        "weekday": request.args.get("weekday", ""),
        "lunar": request.args.get("lunar", ""),
        "location": request.args.get("location", ""),
        "weather": request.args.get("weather", ""),
        "temp": request.args.get("temp", ""),
        "today_duration_min": today_min,
        "yesterday_duration_min": yesterday_min,
        "recent3_total_min": recent3_min,
        "top_apps": [_gdn_greeting(a) for a in top_apps],
        "top_categories": top_categories,
    }
    text = generate_greeting(context)
    return jsonify({"greeting": text})


@bp.route("/api/stats/recent-heatmap")
def recent_heatmap():
    """获取最近 N 天每小时热力图 + 每日摘要（总时长、峰值时段、主要应用）"""
    from datetime import timedelta
    days = min(int(request.args.get("days", "3")), 30)
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()

    with get_conn() as conn:
        # 每天每小时活动数
        hour_rows = conn.execute(
            "SELECT date(timestamp) AS d, "
            "       CAST(strftime('%H', timestamp) AS INTEGER) AS h, "
            "       COUNT(*) AS cnt "
            "FROM activities "
            "WHERE date(timestamp) >= ? "
            "GROUP BY d, h",
            (cutoff,),
        ).fetchall()

        # 每天主要应用
        app_rows = conn.execute(
            "SELECT date(timestamp) AS d, app_name, COUNT(*) AS cnt "
            "FROM activities "
            "WHERE date(timestamp) >= ? "
            "GROUP BY d, app_name "
            "ORDER BY d, cnt DESC",
            (cutoff,),
        ).fetchall()

    # 按日期聚合小时数据
    hour_map: dict[str, list[int]] = {}
    for r in hour_rows:
        d = r["d"]
        if d not in hour_map:
            hour_map[d] = [0] * 24
        hour_map[d][r["h"]] = r["cnt"]

    # 按日期聚合 top app
    top_app_map: dict[str, str] = {}
    for r in app_rows:
        d = r["d"]
        if d not in top_app_map:
            top_app_map[d] = r["app_name"]

    results = []
    for i in range(days - 1, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        hours = hour_map.get(d, [0] * 24)
        total_min = round(sum(hours) * config.SCREENSHOT_INTERVAL_SEC / 60, 1)
        peak_hour = hours.index(max(hours)) if max(hours) > 0 else -1
        results.append({
            "date": d,
            "hours": hours,
            "total_min": total_min,
            "peak_hour": peak_hour,
            "top_app": top_app_map.get(d, ""),
        })

    return jsonify({"days": days, "data": results})
