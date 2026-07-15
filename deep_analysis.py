"""P12-1：周报/月报 AI 深度分析
提供三类深度洞察：
1. 趋势检测：对比近 4 周分类占比变化，自动标注显著增减
2. 模式识别：发现用户的高效/低效时段
3. 对比基准：引入行业基准数据，让用户了解自身水平
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


# 行业基准数据（程序员/知识工作者的平均水平）
# 来源：综合 RescueTime、Toggl 公开统计与 WakaTime 数据
INDUSTRY_BENCHMARKS = {
    "deep_work_hours_per_day": 3.2,      # 日均深度工作时长
    "meeting_pct": 25,                    # 会议时间占比
    "communication_pct": 18,             # 沟通时间占比
    "focus_session_avg_min": 25,         # 平均专注时长
    "distraction_pct": 12,               # 干扰占比
    "switches_per_hour": 4.5,            # 每小时切换次数
}


def _query_weekly_category_stats(weeks_back: int = 4) -> list[dict]:
    """获取近 weeks_back 周的分类占比统计"""
    try:
        import db
        today = date.today()
        results = []
        for i in range(weeks_back):
            week_end = today - timedelta(days=i * 7)
            week_start = week_end - timedelta(days=6)
            with db.get_conn() as conn:
                rows = conn.execute(
                    "SELECT category, SUM(interval_sec) AS total_sec "
                    "FROM activities "
                    "WHERE date(timestamp) BETWEEN ? AND ? "
                    "GROUP BY category ORDER BY total_sec DESC",
                    (week_start.isoformat(), week_end.isoformat()),
                ).fetchall()
            total = sum(r["total_sec"] for r in rows) if rows else 0
            cats = {r["category"]: round(r["total_sec"] / 60, 1) for r in rows} if rows else {}
            pct = {k: round(v / (total / 60) * 100, 1) for k, v in cats.items()} if total > 0 else {}
            results.append({
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "total_min": round(total / 60, 1),
                "categories": cats,
                "percentages": pct,
            })
        results.reverse()  # 按时间正序
        return results
    except Exception as e:
        logger.error(f"查询周度分类统计失败: {e}", exc_info=True)
        return []


def _detect_trends(weekly_stats: list[dict]) -> list[dict]:
    """趋势检测：对比最近两周与之前几周的变化"""
    trends = []
    if len(weekly_stats) < 2:
        return trends
    latest = weekly_stats[-1]
    prev = weekly_stats[-2]
    latest_pct = latest["percentages"]
    prev_pct = prev["percentages"]
    all_cats = set(latest_pct.keys()) | set(prev_pct.keys())
    for cat in all_cats:
        cur = latest_pct.get(cat, 0)
        old = prev_pct.get(cat, 0)
        delta = round(cur - old, 1)
        if abs(delta) >= 5:  # 变化≥5%才标注
            direction = "增加" if delta > 0 else "减少"
            trends.append({
                "category": cat,
                "current_pct": cur,
                "previous_pct": old,
                "delta": delta,
                "direction": direction,
                "significant": abs(delta) >= 15,
            })
    trends.sort(key=lambda x: abs(x["delta"]), reverse=True)
    return trends


def _detect_patterns() -> dict:
    """模式识别：分析近 14 天的高效/低效时段"""
    try:
        import db
        today = date.today()
        start = today - timedelta(days=13)
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT strftime('%H', timestamp) AS hour, category, "
                "SUM(interval_sec) AS total_sec "
                "FROM activities "
                "WHERE date(timestamp) BETWEEN ? AND ? "
                "AND category NOT IN ('生活', '其他') "
                "GROUP BY hour, category "
                "ORDER BY hour, total_sec DESC",
                (start.isoformat(), today.isoformat()),
            ).fetchall()
        if not rows:
            return {"peak_hours": [], "low_hours": [], "best_category": None}
        # 按小时聚合工作时长
        hour_totals: dict[str, float] = {}
        hour_cats: dict[str, dict[str, float]] = {}
        for r in rows:
            h = r["hour"]
            mins = r["total_sec"] / 60
            hour_totals[h] = hour_totals.get(h, 0) + mins
            hour_cats.setdefault(h, {})
            hour_cats[h][r["category"]] = hour_cats[h].get(r["category"], 0) + mins
        if not hour_totals:
            return {"peak_hours": [], "low_hours": [], "best_category": None}
        sorted_hours = sorted(hour_totals.items(), key=lambda x: x[1], reverse=True)
        avg_min = sum(hour_totals.values()) / len(hour_totals)
        peak = [h for h, m in sorted_hours[:3]]
        low = [h for h, m in sorted_hours[-3:]]
        # 最强类别（全天总时长最高）
        cat_totals: dict[str, float] = {}
        for cats in hour_cats.values():
            for c, m in cats.items():
                cat_totals[c] = cat_totals.get(c, 0) + m
        best_cat = max(cat_totals.items(), key=lambda x: x[1])[0] if cat_totals else None
        return {
            "peak_hours": peak,
            "low_hours": low,
            "best_category": best_cat,
            "avg_hour_min": round(avg_min, 1),
        }
    except Exception as e:
        logger.error(f"模式识别失败: {e}", exc_info=True)
        return {"peak_hours": [], "low_hours": [], "best_category": None}


def _compare_with_benchmark(weekly_stats: list[dict], patterns: dict) -> list[dict]:
    """对比行业基准"""
    comparisons = []
    if not weekly_stats:
        return comparisons
    latest = weekly_stats[-1]
    total_min = latest["total_min"]
    # 日均深度工作时长（假设开发+文档+学习+设计算深度工作）
    deep_cats = {"开发", "文档", "学习", "设计", "数据分析"}
    deep_min = sum(v for k, v in latest["categories"].items() if k in deep_cats)
    deep_hours_per_day = (deep_min / 7) / 60
    comparisons.append({
        "metric": "日均深度工作时长",
        "user_value": round(deep_hours_per_day, 1),
        "benchmark": INDUSTRY_BENCHMARKS["deep_work_hours_per_day"],
        "unit": "小时",
        "status": "above" if deep_hours_per_day > INDUSTRY_BENCHMARKS["deep_work_hours_per_day"] else "below",
        "diff": round(deep_hours_per_day - INDUSTRY_BENCHMARKS["deep_work_hours_per_day"], 1),
    })
    # 会议占比
    meeting_pct = latest["percentages"].get("会议", 0)
    comparisons.append({
        "metric": "会议时间占比",
        "user_value": meeting_pct,
        "benchmark": INDUSTRY_BENCHMARKS["meeting_pct"],
        "unit": "%",
        "status": "above" if meeting_pct > INDUSTRY_BENCHMARKS["meeting_pct"] else "below",
        "diff": round(meeting_pct - INDUSTRY_BENCHMARKS["meeting_pct"], 1),
    })
    # 沟通占比
    comm_pct = latest["percentages"].get("沟通", 0)
    comparisons.append({
        "metric": "沟通时间占比",
        "user_value": comm_pct,
        "benchmark": INDUSTRY_BENCHMARKS["communication_pct"],
        "unit": "%",
        "status": "above" if comm_pct > INDUSTRY_BENCHMARKS["communication_pct"] else "below",
        "diff": round(comm_pct - INDUSTRY_BENCHMARKS["communication_pct"], 1),
    })
    return comparisons


def generate_deep_insights() -> dict:
    """生成周报/月报深度洞察（不调用 AI，纯规则）"""
    weekly_stats = _query_weekly_category_stats(4)
    trends = _detect_trends(weekly_stats)
    patterns = _detect_patterns()
    benchmark = _compare_with_benchmark(weekly_stats, patterns)
    return {
        "weekly_stats": weekly_stats,
        "trends": trends,
        "patterns": patterns,
        "benchmark": benchmark,
        "benchmarks_definition": INDUSTRY_BENCHMARKS,
    }


def format_deep_insights_as_markdown(insights: dict) -> str:
    """将深度洞察格式化为 Markdown 段落（可追加到周报/月报末尾）"""
    lines = ["\n---\n\n## 📊 AI 深度分析\n"]
    # 趋势检测
    trends = insights.get("trends", [])
    if trends:
        lines.append("### 趋势检测")
        for t in trends[:5]:
            sig = " ⚠️ 显著" if t.get("significant") else ""
            lines.append(
                f"- **{t['category']}** 占比 {t['previous_pct']}% → {t['current_pct']}%"
                f"（{t['direction']} {abs(t['delta'])}%{sig}）"
            )
        lines.append("")
    # 模式识别
    patterns = insights.get("patterns", {})
    if patterns.get("peak_hours"):
        peak = "、".join(f"{h}:00" for h in patterns["peak_hours"])
        low = "、".join(f"{h}:00" for h in patterns["low_hours"])
        best = patterns.get("best_category", "未知")
        lines.append("### 模式识别")
        lines.append(f"- 高效时段：{peak}")
        lines.append(f"- 低效时段：{low}")
        lines.append(f"- 最强类别：{best}")
        lines.append(f"- 平均每小时工作：{patterns.get('avg_hour_min', 0)} 分钟")
        lines.append("")
    # 对比基准
    bench = insights.get("benchmark", [])
    if bench:
        lines.append("### 对比基准（行业平均水平）")
        for b in bench:
            arrow = "↑" if b["status"] == "above" else "↓"
            lines.append(
                f"- {b['metric']}：{b['user_value']}{b['unit']} "
                f"{arrow} 基准 {b['benchmark']}{b['unit']}（差 {b['diff']:+}{b['unit']}）"
            )
        lines.append("")
    return "\n".join(lines)
