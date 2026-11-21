from flask import Blueprint, jsonify, request
from datetime import date, timedelta
import logging
import re

import config
from db import get_activities, get_daily_summary, get_conn, get_app_usage
from routes.deps import validate_date

logger = logging.getLogger(__name__)

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


def _focus_grade(score: int) -> str:
    """专注分等级：与前端 FocusScoreCalendar 的阈值保持一致。"""
    if score >= 90:
        return "S"
    if score >= 75:
        return "A"
    if score >= 60:
        return "B"
    if score >= 40:
        return "C"
    return "D"


def _focus_session_score(status: str, interrupted_count: int) -> int:
    """单次番茄的专注质量分：完成 100 起评，中断每次 -10；中止 50 起评。"""
    base = 100 if status == "completed" else 50 if status == "interrupted" else 0
    return max(0, min(100, base - max(0, int(interrupted_count or 0)) * 10))


@bp.route("/api/stats/focus-score/calendar")
def focus_score_calendar():
    """按日聚合番茄专注质量分（FocusScoreCalendar 数据源）。

    数据来自 pomodoro_sessions 的真实记录，不做任何补零或模拟：
    - days: 有番茄记录的日期 -> 当日平均分 + 等级
    - month_stats: 按自然月汇总的均分/最佳/有效天数
    """
    try:
        months = int(request.args.get("months", "3"))
    except (TypeError, ValueError):
        months = 3
    months = max(1, min(12, months))

    today = date.today()
    year, month = today.year, today.month
    for _ in range(months - 1):
        month -= 1
        if month == 0:
            year -= 1
            month = 12
    window_start = f"{year:04d}-{month:02d}-01"

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date(start_time) AS day, status, interrupted_count "
            "FROM pomodoro_sessions WHERE date(start_time) >= ? "
            "ORDER BY start_time",
            (window_start,),
        ).fetchall()

    scores_by_day: dict[str, list[int]] = {}
    for row in rows:
        day = row["day"]
        if not day:
            continue
        scores_by_day.setdefault(day, []).append(
            _focus_session_score(row["status"], row["interrupted_count"])
        )

    days = []
    for day in sorted(scores_by_day):
        values = scores_by_day[day]
        avg = int(round(sum(values) / len(values)))
        days.append({"date": day, "score": avg, "grade": _focus_grade(avg)})

    month_buckets: dict[str, list[int]] = {}
    for item in days:
        month_buckets.setdefault(item["date"][:7], []).append(item["score"])
    month_stats = []
    for month_key in sorted(month_buckets):
        values = month_buckets[month_key]
        month_stats.append({
            "month": month_key,
            "avg_score": int(round(sum(values) / len(values))),
            "best_score": max(values),
            "days_count": len(values),
        })

    return jsonify({"days": days, "month_stats": month_stats})


_WORD_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "not", "you", "your", "our", "but", "all", "can",
    "工作", "记录", "总结", "今天", "今日", "进行", "完成", "一个", "一些", "没有",
}


def _wordcloud_tokens(text: str) -> list[str]:
    """把标题切成可读关键词：按空白/中英文标点切分，过滤停用词与纯数字。"""
    if not text:
        return []
    parts = re.split(r"[\s,，。、;；:：/\\|·（）()\[\]【】<>《》\-—_]+", text)
    tokens = []
    for part in parts:
        token = part.strip()
        if len(token) < 2 or len(token) > 20:
            continue
        if token.lower() in _WORD_STOPWORDS:
            continue
        if re.fullmatch(r"[0-9.:%+\-]+", token):
            continue
        tokens.append(token)
    return tokens


@bp.route("/api/stats/wordcloud")
def stats_wordcloud():
    """最近 30 天工作关键词词频（WordCloud 数据源）。

    优先使用 work_records（小黑抽取的真实工作记录），无数据时回退到
    activities.summary；返回 [{text, value}]，value 为出现次数。
    """
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    counts: dict[str, int] = {}
    source = "work_records"

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT title, app_name FROM work_records "
            "WHERE date >= ? ORDER BY id DESC LIMIT 500",
            (cutoff,),
        ).fetchall()
        if not rows:
            source = "activities"
            rows = conn.execute(
                "SELECT summary AS title, app_name FROM activities "
                "WHERE date(timestamp) >= ? AND summary IS NOT NULL AND summary != '' "
                "ORDER BY id DESC LIMIT 500",
                (cutoff,),
            ).fetchall()

    for row in rows:
        for token in _wordcloud_tokens(row["title"] or ""):
            counts[token] = counts.get(token, 0) + 1
        app_name = (row["app_name"] or "").strip()
        if len(app_name) >= 2 and app_name.lower() not in _WORD_STOPWORDS:
            counts[app_name] = counts.get(app_name, 0) + 1

    words = [
        {"text": text, "value": value}
        for text, value in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:40]
    ]
    return jsonify({"words": words, "source": source, "window_days": 30})


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


@bp.route('/api/stats/heatmap')
def heatmap_by_range():
    """热力图数据（支持周/月/年范围）

    query:
      range: week | month | year
      date: YYYY-MM-DD（年视图取年份、月视图取年月、周视图忽略）
    返回：{"data": [{"date","focus_min","level"}], "range": rng}
    level 分档：0/120/240/360/480 分钟（max 4）
    """
    rng = request.args.get('range', 'week')
    date_str = request.args.get('date', '') or date.today().isoformat()
    # 颜色等级阈值（分钟）：0/<120/<240/<360/<480 -> 0/1/2/3/4
    try:
        with get_conn() as conn:
            if rng == 'year':
                # 年度：按日聚合（activities.timestamp + interval_sec）
                # B35: 用半开区间让 idx_activities_ts 可命中；不要对列套 strftime
                year = date_str[:4]
                if not re.fullmatch(r'\d{4}', year):
                    year = date.today().strftime('%Y')
                year_start = f"{year}-01-01"
                year_end = f"{int(year) + 1}-01-01"
                rows = conn.execute(
                    "SELECT date(timestamp) AS d, "
                    "       COALESCE(SUM(CASE WHEN category != '生活' THEN interval_sec ELSE 0 END), 0) AS focus_sec "
                    "FROM activities "
                    "WHERE timestamp >= ? AND timestamp < ? "
                    "GROUP BY date(timestamp) ORDER BY d",
                    (year_start, year_end),
                ).fetchall()
                result = [{
                    "date": r["d"],
                    "focus_min": int(r["focus_sec"] // 60),
                    "level": min(4, int((r["focus_sec"] or 0) // 60 // 120)),
                } for r in rows]
            elif rng == 'month':
                # 月度：按日聚合；同样改成 [月初, 下月初) 范围查询
                try:
                    month_start = date.fromisoformat(date_str[:7] + '-01')
                except ValueError:
                    month_start = date.today().replace(day=1)
                month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
                rows = conn.execute(
                    "SELECT date(timestamp) AS d, "
                    "       COALESCE(SUM(CASE WHEN category != '生活' THEN interval_sec ELSE 0 END), 0) AS focus_sec "
                    "FROM activities "
                    "WHERE timestamp >= ? AND timestamp < ? "
                    "GROUP BY date(timestamp) ORDER BY d",
                    (month_start.isoformat(), month_end.isoformat()),
                ).fetchall()
                result = [{
                    "date": r["d"],
                    "focus_min": int(r["focus_sec"] // 60),
                    "level": min(4, int((r["focus_sec"] or 0) // 60 // 120)),
                } for r in rows]
            else:
                # 周度：复用现有 recent-heatmap 逻辑（按日聚合），范围同样走索引
                try:
                    week_end_day = date.fromisoformat(date_str)
                except ValueError:
                    week_end_day = date.today()
                week_start_day = week_end_day - timedelta(days=6)
                week_end_exclusive = week_end_day + timedelta(days=1)
                rows = conn.execute(
                    "SELECT date(timestamp) AS d, "
                    "       COALESCE(SUM(CASE WHEN category != '生活' THEN interval_sec ELSE 0 END), 0) AS focus_sec "
                    "FROM activities "
                    "WHERE timestamp >= ? AND timestamp < ? "
                    "GROUP BY date(timestamp) ORDER BY d",
                    (week_start_day.isoformat(), week_end_exclusive.isoformat()),
                ).fetchall()
                result = [{
                    "date": r["d"],
                    "focus_min": int(r["focus_sec"] // 60),
                    "level": min(4, int((r["focus_sec"] or 0) // 60 // 120)),
                } for r in rows]
            # P6-3: 年视图额外返回 GitHub 风格统计（连续天数、活跃天数、总时长）
            year_stats = None
            if rng == 'year' and result:
                active_days = [d for d in result if d["focus_min"] > 0]
                total_focus_min = sum(d["focus_min"] for d in result)
                # 计算连续天数：需要遍历全年日期（含无数据日）
                from datetime import datetime as _dt
                all_dates = {}
                for d in result:
                    all_dates[d["date"]] = d["focus_min"]
                # 当前连续：从今天往前数（仅当年份是当前年）
                from datetime import timedelta as _td
                current_streak = 0
                if str(date.today().year) == year:
                    cur = date.today()
                    while all_dates.get(cur.isoformat(), 0) > 0:
                        current_streak += 1
                        cur = cur - _td(days=1)
                # 最长连续：遍历所有活跃日按日期排序
                longest_streak = 0
                if active_days:
                    sorted_dates = sorted([d["date"] for d in active_days])
                    streak = 1
                    for i in range(1, len(sorted_dates)):
                        prev = _dt.strptime(sorted_dates[i - 1], "%Y-%m-%d").date()
                        curr = _dt.strptime(sorted_dates[i], "%Y-%m-%d").date()
                        if (curr - prev).days == 1:
                            streak += 1
                        else:
                            longest_streak = max(longest_streak, streak)
                            streak = 1
                    longest_streak = max(longest_streak, streak)
                year_stats = {
                    "total_active_days": len(active_days),
                    "total_focus_min": total_focus_min,
                    "total_focus_hour": round(total_focus_min / 60, 1),
                    "avg_daily_min": round(total_focus_min / 365, 1) if total_focus_min else 0,
                    "current_streak": current_streak,
                    "longest_streak": longest_streak,
                }
            return jsonify({"data": result, "range": rng, "stats": year_stats})
    except Exception as e:
        logger.error(f"热力图查询失败: {e}", exc_info=True)
        return jsonify({"error": "查询失败"}), 500


@bp.route('/api/stats/distraction-heatmap')
def distraction_heatmap():
    """分心热点图：24小时分心次数分布

    基于 activities 快照表（timestamp 列），统计 category='生活' 的记录按小时聚合。
    duration_min 由 count * SCREENSHOT_INTERVAL_SEC 估算（activities 无 end_time）。
    """
    days = request.args.get('days', 7, type=int)
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS hour, "
                "       COUNT(*) AS count "
                "FROM activities "
                "WHERE category = '生活' AND date(timestamp) >= date('now', ?) "
                "GROUP BY hour ORDER BY hour",
                (f'-{days} days',),
            ).fetchall()
            result = [{
                "hour": r["hour"],
                "count": r["count"],
                "duration_min": int(round(r["count"] * config.SCREENSHOT_INTERVAL_SEC / 60)),
            } for r in rows]
            return jsonify({"heatmap": result, "days": days})
    except Exception as e:
        logger.error(f"分心热点图查询失败: {e}", exc_info=True)
        return jsonify({"error": "查询失败"}), 500


@bp.route('/api/stats/sankey')
def sankey_flow():
    """P7-4: 桑基图 — 时间在不同分类间的流动

    按时段（上午/下午/晚间/夜间）→ 分类 的流动关系，展示一天的时间分配。
    返回: {"nodes": ["上午", "开发", ...], "links": [{"source":"上午","target":"开发","value":120}, ...]}
    """
    target_date = request.args.get('date', date.today().isoformat())
    if not validate_date(target_date):
        return jsonify({"error": "Invalid date format"}), 400
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS hour, "
                "       category, COUNT(*) AS cnt "
                "FROM activities WHERE date(timestamp) = ? GROUP BY hour, category",
                (target_date,),
            ).fetchall()

        # 时段定义
        def get_period(h):
            if 6 <= h < 12: return "上午"
            if 12 <= h < 14: return "中午"
            if 14 <= h < 18: return "下午"
            if 18 <= h < 22: return "晚间"
            if h >= 22 or h < 6: return "夜间"
            return "其他"

        interval_min = config.SCREENSHOT_INTERVAL_SEC / 60
        # 聚合：时段 → 分类
        flow = {}
        for r in rows:
            period = get_period(r["hour"])
            cat = r["category"] or "其他"
            key = (period, cat)
            flow[key] = flow.get(key, 0) + r["cnt"] * interval_min

        # 构建节点和链接
        periods_set = set()
        cats_set = set()
        links = []
        for (period, cat), val in flow.items():
            if val < 1: continue
            periods_set.add(period)
            cats_set.add(cat)
            links.append({"source": period, "target": cat, "value": round(val, 1)})

        # 节点顺序：时段在前，分类在后
        period_order = ["上午", "中午", "下午", "晚间", "夜间"]
        nodes = [p for p in period_order if p in periods_set] + sorted(cats_set)

        return jsonify({"nodes": nodes, "links": links})
    except Exception as e:
        logger.error(f"桑基图查询失败: {e}", exc_info=True)
        return jsonify({"error": "查询失败"}), 500


@bp.route('/api/stats/calendar')
def calendar_view():
    """P9-4：日历视图 — 月度每日分类热力

    query:
      month: YYYY-MM（默认当月）
    返回：{
      "month": "2026-07",
      "days": [
        {"date":"2026-07-01","total_min":120,"dominant_cat":"开发","cats":{"开发":90,"学习":30},"level":2},
        ...
      ],
      "category_totals": {"开发": 1200, "学习": 300, ...},
      "legend": [{"cat":"开发","color":"..."}, ...]
    }
    level 分档：0/<60/<120/<240/<360 分钟 -> 0/1/2/3/4
    """
    from collections import defaultdict
    month_str = request.args.get('month', '').strip()
    if not month_str:
        month_str = date.today().strftime('%Y-%m')
    # 校验 YYYY-MM
    try:
        y, m = month_str.split('-')
        year_i, month_i = int(y), int(m)
        if not (2020 <= year_i <= 2099 and 1 <= month_i <= 12):
            raise ValueError
    except ValueError:
        return jsonify({"error": "月份格式应为 YYYY-MM"}), 400
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT date(timestamp) AS d, category, "
                "       COALESCE(SUM(interval_sec), 0) AS sec "
                "FROM activities "
                "WHERE strftime('%Y-%m', timestamp) = ? "
                "GROUP BY date(timestamp), category "
                "ORDER BY d, sec DESC",
                (month_str,),
            ).fetchall()
        if not rows:
            return jsonify({"month": month_str, "days": [], "category_totals": {}, "legend": []})

        # 按天聚合
        day_map: dict[str, dict] = {}
        cat_totals: dict[str, int] = defaultdict(int)
        for r in rows:
            d = r["d"]
            cat = r["category"] or "其他"
            sec = int(r["sec"] or 0)
            min_v = sec // 60
            if d not in day_map:
                day_map[d] = {"date": d, "total_min": 0, "cats": {}}
            day_map[d]["cats"][cat] = day_map[d]["cats"].get(cat, 0) + min_v
            day_map[d]["total_min"] += min_v
            cat_totals[cat] += min_v

        days = []
        for d, info in sorted(day_map.items()):
            total = info["total_min"]
            # 主导分类（耗时最多的）
            dominant = max(info["cats"].items(), key=lambda x: x[1])[0] if info["cats"] else None
            level = min(4, total // 60) if total < 360 else 4
            # 更细的分档：<60=1, <120=2, <240=3, <360=4, >=360=4
            if total == 0:
                level = 0
            elif total < 60:
                level = 1
            elif total < 120:
                level = 2
            elif total < 240:
                level = 3
            else:
                level = 4
            days.append({
                "date": d,
                "total_min": total,
                "dominant_cat": dominant,
                "cats": info["cats"],
                "level": level,
            })

        # 图例：按总耗时排序的分类（最多 8 个）
        sorted_cats = sorted(cat_totals.items(), key=lambda x: -x[1])[:8]
        # 分类配色（与 CATEGORIES 对齐，兜底灰色）
        cat_colors = {
            "开发": "#7B68EE", "学习": "#22c55e", "生活": "#f59e0b",
            "娱乐": "#ec4899", "社交": "#06b6d4", "休息": "#a855f7",
            "其他": "#6b7280", "运动": "#ef4444", "阅读": "#3b82f6",
        }
        legend = [{"cat": c, "color": cat_colors.get(c, "#6b7280")} for c, _ in sorted_cats]

        return jsonify({
            "month": month_str,
            "days": days,
            "category_totals": dict(cat_totals),
            "legend": legend,
        })
    except Exception as e:
        logger.error(f"日历视图查询失败: {e}", exc_info=True)
        return jsonify({"error": "查询失败"}), 500
