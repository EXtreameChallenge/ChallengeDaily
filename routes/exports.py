from flask import Blueprint, jsonify, request, Response
from datetime import date, datetime, timedelta
import csv
import io
import json
import logging

import db
from db import export_activities_csv, export_app_usage_csv
from routes.deps import check_token, validate_date, safe_error

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


# ═══════════════════════════════════════════════════════════════
# 一键导出中心：周报 / 月报 / 年度总结 / 全量数据
# ═══════════════════════════════════════════════════════════════

def _auth_check():
    """统一鉴权校验，返回 (通过, 错误响应)"""
    if not check_token(request):
        return False, (jsonify({"error": "未授权访问"}), 401)
    return True, None


def _week_dates(week_start: str):
    """根据周一起始日期返回 7 天日期列表"""
    start_d = datetime.strptime(week_start, "%Y-%m-%d").date()
    return [(start_d + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]


def _gather_week_data(week_start: str) -> dict:
    """汇总本周数据：任务 + 番茄 + 活动"""
    dates = _week_dates(week_start)
    # 任务：本周日任务 + 周任务
    week_tasks = db.get_week_tasks(week_start)
    # 番茄：遍历 7 天
    pomodoro_sessions = []
    for d in dates:
        pomodoro_sessions.extend(db.get_pomodoro_sessions(d))
    completed_pomodoros = [s for s in pomodoro_sessions if s.get("status") == "completed"]
    total_focus_min = sum(s.get("duration_min", 0) for s in completed_pomodoros)
    # 活动：本周所有活动
    activities = db.get_activities(dates[0], dates[6])
    # 分类分布
    cat_dist = {}
    for a in activities:
        cat = a.get("category", "其他")
        cat_dist[cat] = cat_dist.get(cat, 0) + 1
    # 日任务完成率
    day_tasks = []
    for d in dates:
        day_tasks.extend(week_tasks.get("day_tasks", {}).get(d, []))
    total_day = len(day_tasks)
    completed_day = sum(1 for t in day_tasks if t.get("status") == "completed")
    return {
        "week_start": week_start,
        "dates": dates,
        "week_tasks": week_tasks.get("week_tasks", []),
        "day_tasks": day_tasks,
        "total_day_tasks": total_day,
        "completed_day_tasks": completed_day,
        "completion_rate": int(completed_day / total_day * 100) if total_day > 0 else 0,
        "pomodoro_total": len(pomodoro_sessions),
        "pomodoro_completed": len(completed_pomodoros),
        "total_focus_min": total_focus_min,
        "activities_count": len(activities),
        "category_distribution": cat_dist,
        "pomodoro_sessions": pomodoro_sessions,
        "activities": activities,
    }


@bp.route('/api/exports/weekly-report', methods=['GET'])
def export_weekly_report():
    """导出周报：本周任务完成 + 番茄统计 + 活动汇总"""
    ok, err = _auth_check()
    if not ok:
        return err
    week_start = request.args.get("week_start", "")
    fmt = request.args.get("format", "markdown")
    if not week_start:
        # 默认本周一
        today = date.today()
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")
    if not validate_date(week_start):
        return jsonify({"error": "week_start 日期格式无效，应为 YYYY-MM-DD"}), 400
    if fmt not in ("markdown", "json", "csv"):
        return jsonify({"error": "format 仅支持 markdown / json / csv"}), 400

    try:
        data = _gather_week_data(week_start)
        if fmt == "json":
            content = json.dumps(data, ensure_ascii=False, indent=2)
            return Response(
                content.encode("utf-8"),
                mimetype="application/json",
                headers={"Content-Disposition": f'attachment; filename="weekly_report_{week_start}.json"'},
            )
        if fmt == "csv":
            output = io.StringIO()
            output.write('\ufeff')
            writer = csv.writer(output)
            writer.writerow(["日期", "任务标题", "分类", "状态", "预估番茄", "进度分钟", "目标分钟"])
            for t in data["day_tasks"]:
                writer.writerow([
                    _csv_escape(t.get("assigned_date", "")),
                    _csv_escape(t.get("title", "")),
                    _csv_escape(t.get("category", "")),
                    _csv_escape(t.get("status", "")),
                    _csv_escape(t.get("estimated_pomodoros", 0)),
                    _csv_escape(t.get("progress_min", 0)),
                    _csv_escape(t.get("target_min", 0)),
                ])
            content = output.getvalue()
            output.close()
            return Response(
                content.encode("utf-8-sig"),
                mimetype="text/csv",
                headers={"Content-Disposition": f'attachment; filename="weekly_report_{week_start}.csv"'},
            )
        # markdown
        lines = [
            f"# 📊 周报告 {data['week_start']} ~ {data['dates'][-1]}",
            "",
            "## 📝 任务完成情况",
            f"- 日任务总数：**{data['total_day_tasks']}**",
            f"- 已完成：**{data['completed_day_tasks']}**",
            f"- 完成率：**{data['completion_rate']}%**",
            "",
            "## 🍅 番茄钟统计",
            f"- 番茄钟总数：**{data['pomodoro_total']}**",
            f"- 已完成：**{data['pomodoro_completed']}**",
            f"- 累计专注：**{data['total_focus_min']} 分钟** ≈ {data['total_focus_min'] / 60:.1f} 小时",
            "",
            "## 💻 活动汇总",
            f"- 活动记录条数：**{data['activities_count']}**",
            "",
            "### 分类分布",
        ]
        if data["category_distribution"]:
            lines.append("| 分类 | 次数 |")
            lines.append("| --- | --- |")
            for cat, cnt in sorted(data["category_distribution"].items(), key=lambda x: -x[1]):
                lines.append(f"| {cat} | {cnt} |")
        else:
            lines.append("_本周无活动记录_")
        lines.append("")
        lines.append("### 周任务列表")
        if data["week_tasks"]:
            for t in data["week_tasks"]:
                status_icon = "✅" if t.get("status") == "completed" else "⬜"
                lines.append(f"- {status_icon} {t.get('title', '')} [{t.get('category', '')}]")
        else:
            lines.append("_本周无周级任务_")
        lines.append("")
        content = "\n".join(lines)
        return Response(
            content.encode("utf-8"),
            mimetype="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="weekly_report_{week_start}.md"'},
        )
    except Exception as e:
        logger.warning(f"export_weekly_report failed: {type(e).__name__}")
        return jsonify({"error": safe_error(e, "导出周报失败")}), 500


def _gather_month_data(month_key: str) -> dict:
    """汇总月数据：月目标 + 完成率 + 每日热力 + 分类分布"""
    # 月任务
    month_tasks = db.get_month_tasks(month_key)
    # 月统计
    stats = db.get_month_plan_stats(month_key)
    # 每日热力：番茄分钟
    daily_heat = []
    try:
        year, mon = month_key.split("-")
        import calendar as _cal
        days_in_month = _cal.monthrange(int(year), int(mon))[1]
        with db.get_conn() as conn:
            for d in range(1, days_in_month + 1):
                ds = f"{year}-{mon}-{d:02d}"
                row = conn.execute(
                    "SELECT COALESCE(SUM(duration_min),0) as total FROM pomodoro_sessions "
                    "WHERE date(start_time)=? AND status='completed'",
                    (ds,)
                ).fetchone()
                daily_heat.append({"date": ds, "focus_min": row["total"] or 0})
    except Exception:
        pass
    # 分类分布
    cat_dist = {}
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM activities "
                "WHERE strftime('%Y-%m', timestamp)=? GROUP BY category ORDER BY cnt DESC",
                (month_key,)
            ).fetchall()
            for r in rows:
                cat_dist[r["category"]] = r["cnt"]
    except Exception:
        pass
    return {
        "month_key": month_key,
        "month_tasks": month_tasks,
        "stats": stats,
        "daily_heatmap": daily_heat,
        "category_distribution": cat_dist,
    }


@bp.route('/api/exports/monthly-report', methods=['GET'])
def export_monthly_report():
    """导出月报：月目标 + 完成率 + 每日热力 + 分类分布"""
    ok, err = _auth_check()
    if not ok:
        return err
    month_key = request.args.get("month_key", "")
    fmt = request.args.get("format", "markdown")
    if not month_key:
        month_key = date.today().strftime("%Y-%m")
    # 校验 YYYY-MM
    try:
        datetime.strptime(month_key, "%Y-%m")
    except ValueError:
        return jsonify({"error": "month_key 格式无效，应为 YYYY-MM"}), 400
    if fmt not in ("markdown", "json"):
        return jsonify({"error": "format 仅支持 markdown / json"}), 400

    try:
        data = _gather_month_data(month_key)
        if fmt == "json":
            content = json.dumps(data, ensure_ascii=False, indent=2)
            return Response(
                content.encode("utf-8"),
                mimetype="application/json",
                headers={"Content-Disposition": f'attachment; filename="monthly_report_{month_key}.json"'},
            )
        # markdown
        stats = data["stats"]
        lines = [
            f"# 📈 月报告 {month_key}",
            "",
            "## 🎯 月目标",
        ]
        if data["month_tasks"]:
            for m in data["month_tasks"]:
                status_icon = "✅" if m.get("status") == "completed" else "⬜"
                pct = m.get("progress_pct", 0)
                lines.append(f"- {status_icon} **{m.get('title', '')}** [{m.get('category', '')}] 进度 {pct}%")
        else:
            lines.append("_本月无月级目标_")
        lines.extend([
            "",
            "## 📊 完成率统计",
            f"- 总专注分钟：**{stats.get('total_focus_min', 0)}** 分钟",
            f"- 深度专注分钟：**{stats.get('deep_focus_min', 0)}** 分钟",
            f"- 中断次数：**{stats.get('interrupt_count', 0)}**",
            f"- 日任务总数：**{stats.get('total_tasks', 0)}**",
            f"- 已完成：**{stats.get('completed_tasks', 0)}**",
            f"- 完成率：**{stats.get('completion_rate', 0)}%**",
            "",
            "## 🔥 每日热力图（专注分钟）",
        ])
        if data["daily_heatmap"]:
            for d in data["daily_heatmap"]:
                mins = d["focus_min"]
                bar = "█" * min(int(mins / 25) + (1 if mins > 0 else 0), 30)
                lines.append(f"- {d['date']}：{bar} {mins}min")
        else:
            lines.append("_本月无专注数据_")
        lines.extend([
            "",
            "## 🗂️ 分类分布",
        ])
        if data["category_distribution"]:
            lines.append("| 分类 | 次数 |")
            lines.append("| --- | --- |")
            for cat, cnt in data["category_distribution"].items():
                lines.append(f"| {cat} | {cnt} |")
        else:
            lines.append("_本月无活动分类数据_")
        lines.append("")
        content = "\n".join(lines)
        return Response(
            content.encode("utf-8"),
            mimetype="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="monthly_report_{month_key}.md"'},
        )
    except Exception as e:
        logger.warning(f"export_monthly_report failed: {type(e).__name__}")
        return jsonify({"error": safe_error(e, "导出月报失败")}), 500


def _gather_yearly_data(year: int) -> dict:
    """汇总全年数据：热力图 + 月度趋势 + 成就"""
    year_str = str(year)
    # 全年热力图：每日专注分钟
    daily_heat = []
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT date(start_time) as d, COALESCE(SUM(duration_min),0) as total "
                "FROM pomodoro_sessions "
                "WHERE strftime('%Y', start_time)=? AND status='completed' "
                "GROUP BY date(start_time) ORDER BY d",
                (year_str,)
            ).fetchall()
            for r in rows:
                daily_heat.append({"date": r["d"], "focus_min": r["total"] or 0})
    except Exception:
        pass
    # 月度趋势
    monthly_trend = []
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT strftime('%Y-%m', start_time) as m, COUNT(*) as cnt, COALESCE(SUM(duration_min),0) as total "
                "FROM pomodoro_sessions "
                "WHERE strftime('%Y', start_time)=? AND status='completed' "
                "GROUP BY strftime('%Y-%m', start_time) ORDER BY m",
                (year_str,)
            ).fetchall()
            for r in rows:
                monthly_trend.append({"month": r["m"], "count": r["cnt"], "total_min": r["total"] or 0})
    except Exception:
        pass
    # 成就
    achievements = db.get_achievements()
    # 年度统计
    total_focus = sum(d["focus_min"] for d in daily_heat)
    total_pomodoros = sum(m["count"] for m in monthly_trend)
    return {
        "year": year,
        "total_focus_min": total_focus,
        "total_pomodoros": total_pomodoros,
        "active_days": len(daily_heat),
        "daily_heatmap": daily_heat,
        "monthly_trend": monthly_trend,
        "achievements": achievements,
    }


@bp.route('/api/exports/yearly-summary', methods=['GET'])
def export_yearly_summary():
    """导出年度总结：全年热力图 + 月度趋势 + 成就"""
    ok, err = _auth_check()
    if not ok:
        return err
    year_str = request.args.get("year", "")
    if not year_str:
        year_str = str(date.today().year)
    fmt = request.args.get("format", "markdown")
    try:
        year = int(year_str)
    except ValueError:
        return jsonify({"error": "year 格式无效，应为 YYYY"}), 400
    if fmt not in ("markdown", "json"):
        return jsonify({"error": "format 仅支持 markdown / json"}), 400

    try:
        data = _gather_yearly_data(year)
        if fmt == "json":
            content = json.dumps(data, ensure_ascii=False, indent=2)
            return Response(
                content.encode("utf-8"),
                mimetype="application/json",
                headers={"Content-Disposition": f'attachment; filename="yearly_summary_{year}.json"'},
            )
        # markdown
        lines = [
            f"# 📅 年度总结 {year}",
            "",
            "## 🎉 年度概览",
            f"- 活跃天数：**{data['active_days']}** 天",
            f"- 番茄钟总数：**{data['total_pomodoros']}** 个",
            f"- 累计专注：**{data['total_focus_min']}** 分钟 ≈ {data['total_focus_min'] / 60:.1f} 小时",
            "",
            "## 📈 月度趋势",
        ]
        if data["monthly_trend"]:
            lines.append("| 月份 | 番茄数 | 专注分钟 |")
            lines.append("| --- | --- | --- |")
            for m in data["monthly_trend"]:
                lines.append(f"| {m['month']} | {m['count']} | {m['total_min']} |")
        else:
            lines.append("_本年无专注数据_")
        lines.extend([
            "",
            "## 🔥 全年热力图（每日专注分钟）",
        ])
        if data["daily_heatmap"]:
            for d in data["daily_heatmap"][:60]:  # 仅展示前 60 天避免过长
                mins = d["focus_min"]
                bar = "█" * min(int(mins / 25) + (1 if mins > 0 else 0), 30)
                lines.append(f"- {d['date']}：{bar} {mins}min")
            if len(data["daily_heatmap"]) > 60:
                lines.append(f"_... 共 {len(data['daily_heatmap'])} 天有专注记录，仅展示前 60 天_")
        else:
            lines.append("_本年无热力图数据_")
        lines.extend([
            "",
            "## 🏆 成就墙",
        ])
        if data["achievements"]:
            for a in data["achievements"]:
                lines.append(f"- {a.get('icon', '🏆')} **{a.get('name', '')}** — {a.get('description', '')}")
        else:
            lines.append("_本年尚未解锁成就_")
        lines.append("")
        content = "\n".join(lines)
        return Response(
            content.encode("utf-8"),
            mimetype="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="yearly_summary_{year}.md"'},
        )
    except Exception as e:
        logger.warning(f"export_yearly_summary failed: {type(e).__name__}")
        return jsonify({"error": safe_error(e, "导出年度总结失败")}), 500


@bp.route('/api/exports/all-data', methods=['GET'])
def export_all_data():
    """导出全部数据：activities + todos + pomodoro_sessions + diaries"""
    ok, err = _auth_check()
    if not ok:
        return err
    fmt = request.args.get("format", "json")
    if fmt not in ("json", "csv"):
        return jsonify({"error": "format 仅支持 json / csv"}), 400

    try:
        # 拉取全量数据
        diaries = db.get_diaries(limit=10000)
        todos = db.get_todos()
        # 番茄钟全量：最近 1000 条
        pomodoro_sessions = db.get_pomodoro_sessions()
        # 活动记录：最近 90 天
        today = date.today()
        start_90 = (today - timedelta(days=89)).isoformat()
        activities = db.get_activities(start_90, today.isoformat())

        if fmt == "json":
            payload = {
                "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "activities": activities,
                "todos": todos,
                "pomodoro_sessions": pomodoro_sessions,
                "diaries": diaries,
            }
            content = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            return Response(
                content.encode("utf-8"),
                mimetype="application/json",
                headers={"Content-Disposition": f'attachment; filename="all_data_{today.isoformat()}.json"'},
            )
        # csv：4 个 sheet 用空行分隔
        output = io.StringIO()
        output.write('\ufeff')
        # Sheet1: 活动记录
        writer = csv.writer(output)
        writer.writerow(["── 活动记录 ──"])
        writer.writerow(["时间", "应用", "窗口标题", "分类", "摘要", "时长(秒)"])
        for a in activities:
            writer.writerow([
                _csv_escape(a.get("timestamp", "")),
                _csv_escape(a.get("app_name", "")),
                _csv_escape(a.get("window_title", "")),
                _csv_escape(a.get("category", "")),
                _csv_escape(a.get("summary", "")),
                _csv_escape(a.get("interval_sec", 60)),
            ])
        output.write("\n\n")
        # Sheet2: 待办
        writer = csv.writer(output)
        writer.writerow(["── 待办事项 ──"])
        writer.writerow(["ID", "标题", "分类", "层级", "状态", "预估番茄", "进度分钟", "目标分钟", "分配日期"])
        for t in todos:
            writer.writerow([
                _csv_escape(t.get("id", "")),
                _csv_escape(t.get("title", "")),
                _csv_escape(t.get("category", "")),
                _csv_escape(t.get("task_level", "")),
                _csv_escape(t.get("status", "")),
                _csv_escape(t.get("estimated_pomodoros", 0)),
                _csv_escape(t.get("progress_min", 0)),
                _csv_escape(t.get("target_min", 0)),
                _csv_escape(t.get("assigned_date", "")),
            ])
        output.write("\n\n")
        # Sheet3: 番茄钟
        writer = csv.writer(output)
        writer.writerow(["── 番茄钟会话 ──"])
        writer.writerow(["开始时间", "结束时间", "时长(分)", "任务", "分类", "状态", "中断次数"])
        for s in pomodoro_sessions:
            writer.writerow([
                _csv_escape(s.get("start_time", "")),
                _csv_escape(s.get("end_time", "")),
                _csv_escape(s.get("duration_min", 0)),
                _csv_escape(s.get("task", "")),
                _csv_escape(s.get("category", "")),
                _csv_escape(s.get("status", "")),
                _csv_escape(s.get("interrupted_count", 0)),
            ])
        output.write("\n\n")
        # Sheet4: 日记
        writer = csv.writer(output)
        writer.writerow(["── 日记 ──"])
        writer.writerow(["日期", "心情", "天气", "内容", "标签", "亮点", "感恩"])
        for d in diaries:
            writer.writerow([
                _csv_escape(d.get("diary_date", "")),
                _csv_escape(d.get("mood", "")),
                _csv_escape(d.get("weather", "")),
                _csv_escape(d.get("content", "")),
                _csv_escape(d.get("tags", "")),
                _csv_escape(d.get("highlights", "")),
                _csv_escape(d.get("gratitude", "")),
            ])
        content = output.getvalue()
        output.close()
        return Response(
            content.encode("utf-8-sig"),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="all_data_{today.isoformat()}.csv"'},
        )
    except Exception as e:
        logger.warning(f"export_all_data failed: {type(e).__name__}")
        return jsonify({"error": safe_error(e, "导出全量数据失败")}), 500


# ── P8-4：CSV/Excel 原始数据导出增强 ──────────────────────────────────

@bp.route('/api/exports/reports', methods=['GET'])
def export_reports():
    """P8-4：导出全部历史报告（CSV / JSON）

    GET /api/exports/reports?format=csv|json&start=YYYY-MM-DD&end=YYYY-MM-DD
    - CSV：报告日期、创建时间、内容（含换行）、字符数
    - JSON：完整 reports 列表
    """
    ok, err = _auth_check()
    if not ok:
        return err
    fmt = request.args.get("format", "csv")
    if fmt not in ("csv", "json"):
        return jsonify({"error": "format 仅支持 csv / json"}), 400
    today = date.today()
    start_date = request.args.get("start", (today - timedelta(days=89)).isoformat())
    end_date = request.args.get("end", today.isoformat())
    err_msg = _validate_range(start_date, end_date)
    if err_msg:
        return jsonify({"error": err_msg}), 400
    try:
        reports = db.get_reports(start_date, end_date)
        if fmt == "json":
            payload = {
                "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "range": {"start": start_date, "end": end_date},
                "count": len(reports),
                "reports": reports,
            }
            content = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            return Response(
                content.encode("utf-8"),
                mimetype="application/json",
                headers={"Content-Disposition": f'attachment; filename="reports_{start_date}_{end_date}.json"'},
            )
        # CSV
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(["报告日期", "创建时间", "字符数", "内容"])
        for r in reports:
            writer.writerow([
                _csv_escape(r.get("report_date", "")),
                _csv_escape(r.get("created_at", "")),
                _csv_escape(len(r.get("content", "") or "")),
                _csv_escape(r.get("content", "")),
            ])
        content = output.getvalue()
        output.close()
        return Response(
            content.encode("utf-8-sig"),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="reports_{start_date}_{end_date}.csv"'},
        )
    except Exception as e:
        logger.warning(f"export_reports failed: {type(e).__name__}")
        return jsonify({"error": safe_error(e, "导出报告失败")}), 500


@bp.route('/api/exports/activities-detail', methods=['GET'])
def export_activities_detail():
    """P8-4：活动明细聚合导出（多日期范围，CSV）

    GET /api/exports/activities-detail?start=YYYY-MM-DD&end=YYYY-MM-DD
    导出范围内所有活动记录，按时间排序，含分类、应用、窗口标题、摘要、时长、AI 详情。
    支持最长 90 天范围，避免内存爆炸。
    """
    ok, err = _auth_check()
    if not ok:
        return err
    today = date.today()
    start_date = request.args.get("start", (today - timedelta(days=6)).isoformat())
    end_date = request.args.get("end", today.isoformat())
    err_msg = _validate_range(start_date, end_date)
    if err_msg:
        return jsonify({"error": err_msg}), 400
    try:
        activities = db.get_activities(start_date, end_date)
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow([
            "时间", "应用", "窗口标题", "分类", "摘要",
            "时长(秒)", "AI 详情", "可见窗口(JSON)",
        ])
        for a in activities:
            writer.writerow([
                _csv_escape(a.get("timestamp", "")),
                _csv_escape(a.get("app_name", "")),
                _csv_escape(a.get("window_title", "")),
                _csv_escape(a.get("category", "")),
                _csv_escape(a.get("summary", "")),
                _csv_escape(a.get("interval_sec", 60)),
                _csv_escape(a.get("ai_detail", "")),
                _csv_escape(a.get("windows", "[]")),
            ])
        content = output.getvalue()
        output.close()
        return Response(
            content.encode("utf-8-sig"),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="activities_detail_{start_date}_{end_date}.csv"'},
        )
    except Exception as e:
        logger.warning(f"export_activities_detail failed: {type(e).__name__}")
        return jsonify({"error": safe_error(e, "导出活动明细失败")}), 500


# P15-3：数据自毁（永久删除所有用户数据，不可恢复）
# 删除范围：数据库所有业务表 + 截图文件 + 报告文件
# 保留：settings.json（保留 AI 配置、避免重新登录）、schema_version（保留迁移记录）
_WIPEABLE_TABLES = [
    "activities", "app_usage", "app_usage_v3", "app_usage_v9",
    "app_category_rules", "daily_profiles", "user_profile", "user_corrections",
    "pomodoro_sessions", "todos", "diaries", "achievements", "countdowns",
    "chat_history", "habits", "habit_logs", "plan_meta", "profile_analysis_cache",
    "goals", "ai_retry_queue", "achievement_seasons", "season_achievements",
    "audit_log", "user_preferences", "reports",
]


# 白名单校验：仅允许 DELETE 操作已知的业务表
_WIPEABLE_TABLE_SET = frozenset(_WIPEABLE_TABLES)


def _validate_wipeable_table(table: str) -> bool:
    """校验表名是否在白名单内，防止 SQL 注入"""
    return table in _WIPEABLE_TABLE_SET


@bp.route("/api/exports/wipe", methods=["POST"])
def wipe_all_data():
    """永久删除所有用户数据（不可恢复）
    要求二次确认：请求体需包含 confirm=true 且 confirm_text="DELETE"
    """
    ok, err = _auth_check()
    if not ok:
        return err
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("confirm"):
        return jsonify({"error": "请确认删除操作"}), 400
    if data.get("confirm_text") != "DELETE":
        return jsonify({"error": "确认文本不正确，请输入 DELETE"}), 400
    try:
        import shutil
        from config import SCREENSHOT_DIR, REPORT_DIR
        from db import get_conn
        deleted_counts = {}
        # 1. 清空业务表
        with get_conn() as conn:
            for table in _WIPEABLE_TABLES:
                if not _validate_wipeable_table(table):
                    continue
                try:
                    cur = conn.execute(f"DELETE FROM {table}")
                    deleted_counts[table] = cur.rowcount
                except Exception:
                    # 表可能不存在（旧版本），跳过
                    deleted_counts[table] = -1
            conn.commit()
            # VACUUM 回收磁盘空间
            try:
                conn.execute("VACUUM")
            except Exception:
                pass
        # 2. 删除截图文件
        screenshots_removed = 0
        try:
            if SCREENSHOT_DIR.exists():
                for f in SCREENSHOT_DIR.iterdir():
                    if f.is_file():
                        try:
                            f.unlink()
                            screenshots_removed += 1
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"删除截图目录失败: {e}")
        # 3. 删除报告文件
        reports_removed = 0
        try:
            if REPORT_DIR.exists():
                for f in REPORT_DIR.iterdir():
                    if f.is_file():
                        try:
                            f.unlink()
                            reports_removed += 1
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"删除报告目录失败: {e}")
        logger.warning(f"用户触发了数据自毁：DB表={deleted_counts}, 截图={screenshots_removed}, 报告={reports_removed}")
        return jsonify({
            "status": "ok",
            "message": "所有用户数据已永久删除",
            "deleted": {
                "db_tables": deleted_counts,
                "screenshots": screenshots_removed,
                "reports": reports_removed,
            },
        })
    except Exception as e:
        logger.error(f"数据自毁失败: {e}", exc_info=True)
        return jsonify({"error": safe_error(e, "数据删除失败")}), 500
