"""
P16-3: 主动智能建议引擎
基于 7-14 天历史数据，发现用户行为模式并生成可执行的个性化建议。

五类建议：
  1. 时段效率：发现高效/低效时段 → 建议任务安排
  2. 分类趋势：发现分类占比变化 → 建议调整
  3. 习惯连续性：发现中断风险 → 提醒坚持
  4. 番茄质量：发现最佳番茄时长/时段 → 建议优化
  5. 分心模式：发现高频分心源 → 建议屏蔽
"""
import logging
from datetime import date, timedelta
from collections import defaultdict
import db

logger = logging.getLogger(__name__)

# ── 建议优先级 ──
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"


def generate_suggestions() -> list:
    """生成主动智能建议列表

    返回: [{"type", "priority", "title", "detail", "action"}]
    """
    suggestions = []
    today = date.today()

    try:
        # 1. 时段效率分析（最近 14 天）
        suggestions.extend(_analyze_period_efficiency(today, 14))
    except Exception as e:
        logger.error(f"时段效率分析失败: {e}")

    try:
        # 2. 分类趋势分析（对比本周 vs 上周）
        suggestions.extend(_analyze_category_trend(today))
    except Exception as e:
        logger.error(f"分类趋势分析失败: {e}")

    try:
        # 3. 番茄钟质量分析
        suggestions.extend(_analyze_pomodoro_quality(today, 14))
    except Exception as e:
        logger.error(f"番茄钟质量分析失败: {e}")

    try:
        # 4. 分心源分析
        suggestions.extend(_analyze_distraction_sources(today, 7))
    except Exception as e:
        logger.error(f"分心源分析失败: {e}")

    try:
        # 5. 连续性分析
        suggestions.extend(_analyze_streak_risk(today))
    except Exception as e:
        logger.error(f"连续性分析失败: {e}")

    # 按优先级排序，最多返回 5 条
    priority_order = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 2}
    suggestions.sort(key=lambda s: priority_order.get(s.get("priority", PRIORITY_LOW), 2))
    return suggestions[:5]


def _analyze_period_efficiency(today: date, days: int) -> list:
    """分析各时段的效率，找出高效/低效时段"""
    suggestions = []
    start = (today - timedelta(days=days - 1)).isoformat()
    activities = db.get_activities(start, today.isoformat())

    if not activities or len(activities) < 50:
        return suggestions

    # 按 2 小时区间统计工作类活动占比
    period_work: dict[int, int] = defaultdict(int)  # hour_bin -> work count
    period_total: dict[int, int] = defaultdict(int)

    for act in activities:
        ts = act.get("timestamp", "")
        if len(ts) < 13:
            continue
        try:
            hour = int(ts[11:13])
        except ValueError:
            continue
        bin_hour = (hour // 2) * 2  # 2 小时区间
        cat = act.get("category", "其他")
        period_total[bin_hour] += 1
        if cat != "生活":
            period_work[bin_hour] += 1

    # 找出效率最高和最低的时段
    period_rates = {}
    for h in period_total:
        if period_total[h] >= 5:  # 至少 5 条记录才统计
            period_rates[h] = period_work[h] / period_total[h]

    if len(period_rates) < 3:
        return suggestions

    best_period = max(period_rates, key=period_rates.get)
    worst_period = min(period_rates, key=period_rates.get)

    period_names = {
        0: "凌晨 0-2点", 2: "深夜 2-4点", 4: "黎明 4-6点",
        6: "早晨 6-8点", 8: "上午 8-10点", 10: "上午 10-12点",
        12: "中午 12-14点", 14: "下午 14-16点", 16: "傍晚 16-18点",
        18: "晚间 18-20点", 20: "夜间 20-22点", 22: "深夜 22-24点",
    }

    best_name = period_names.get(best_period, f"{best_period}点")
    worst_name = period_names.get(worst_period, f"{worst_period}点")
    best_rate = round(period_rates[best_period] * 100)
    worst_rate = round(period_rates[worst_period] * 100)

    # 高效时段建议
    if best_rate >= 80 and best_period in (8, 10, 6):
        suggestions.append({
            "type": "peak_hours",
            "priority": PRIORITY_HIGH,
            "title": f"你的黄金时段是{best_name}",
            "detail": f"过去 {days} 天，你在{best_name}的工作类活动占比高达 {best_rate}%。建议把最重要的深度工作安排在这个时段。",
            "action": "把明天的核心任务安排在这个时段",
            "icon": "🎯",
        })

    # 低效时段建议
    if worst_rate < 50 and worst_period in (14, 16, 12) and worst_period != best_period:
        suggestions.append({
            "type": "low_efficiency",
            "priority": PRIORITY_MEDIUM,
            "title": f"{worst_name}是你的效率低谷",
            "detail": f"你在{worst_name}的工作占比仅 {worst_rate}%，容易分心。建议在这个时段安排沟通、会议等不需要深度专注的任务。",
            "action": "把低优先级任务挪到这个时段",
            "icon": "📉",
        })

    return suggestions


def _analyze_category_trend(today: date) -> list:
    """对比本周和上周的分类占比变化"""
    suggestions = []
    week_start = today - timedelta(days=today.weekday())
    last_week_start = week_start - timedelta(days=7)

    this_week = db.get_activities(week_start.isoformat(), today.isoformat())
    last_week = db.get_activities(last_week_start.isoformat(), (week_start - timedelta(days=1)).isoformat())

    if not this_week or not last_week:
        return suggestions

    def count_categories(acts):
        counts = defaultdict(int)
        for a in acts:
            counts[a.get("category", "其他")] += 1
        return counts

    this_cats = count_categories(this_week)
    last_cats = count_categories(last_week)
    this_total = sum(this_cats.values())
    last_total = sum(last_cats.values())

    if this_total < 20 or last_total < 20:
        return suggestions

    # 找出变化最大的分类
    all_cats = set(this_cats.keys()) | set(last_cats.keys())
    max_change_cat = None
    max_change_pct = 0
    for cat in all_cats:
        this_pct = this_cats.get(cat, 0) / this_total
        last_pct = last_cats.get(cat, 0) / last_total
        change = this_pct - last_pct
        if abs(change) > abs(max_change_pct):
            max_change_pct = change
            max_change_cat = cat

    if max_change_cat and abs(max_change_pct) > 0.1:
        pct_str = f"{abs(max_change_pct) * 100:.0f}%"
        if max_change_pct > 0:
            if max_change_cat == "生活":
                suggestions.append({
                    "type": "trend_increase_distraction",
                    "priority": PRIORITY_HIGH,
                    "title": f"本周「{max_change_cat}」时间增加了 {pct_str}",
                    "detail": f"相比上周，你本周在「{max_change_cat}」上多花了 {pct_str} 的时间。要注意控制哦，别让它吞噬你的专注力。",
                    "action": "查看分心来源并设置屏蔽",
                    "icon": "⚠️",
                })
            else:
                suggestions.append({
                    "type": "trend_increase",
                    "priority": PRIORITY_LOW,
                    "title": f"本周「{max_change_cat}」时间增加了 {pct_str}",
                    "detail": f"你在「{max_change_cat}」上的投入持续增长，这是个好趋势！",
                    "action": "继续保持这个节奏",
                    "icon": "📈",
                })
        else:
            if max_change_cat != "生活":
                suggestions.append({
                    "type": "trend_decrease",
                    "priority": PRIORITY_MEDIUM,
                    "title": f"本周「{max_change_cat}」时间减少了 {pct_str}",
                    "detail": f"你在「{max_change_cat}」上的时间比上周少了 {pct_str}。如果是主动调整没问题，如果是被动中断，建议找回节奏。",
                    "action": "回顾本周日程找出原因",
                    "icon": "📊",
                })

    return suggestions


def _analyze_pomodoro_quality(today: date, days: int) -> list:
    """分析番茄钟质量趋势"""
    suggestions = []
    start = (today - timedelta(days=days - 1)).isoformat()

    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT duration_min, status, interrupted_count, start_time "
                "FROM pomodoro_sessions WHERE date(start_time) >= ? ORDER BY start_time",
                (start,),
            ).fetchall()
    except Exception:
        return suggestions

    if not rows or len(rows) < 5:
        return suggestions

    total = len(rows)
    completed = sum(1 for r in rows if r["status"] == "completed")
    total_distractions = sum(r["interrupted_count"] or 0 for r in rows)
    completion_rate = completed / total if total else 0
    avg_distractions = total_distractions / total if total else 0

    # 按时长分组找最佳
    duration_stats: dict[int, list] = defaultdict(list)
    for r in rows:
        dur = r["duration_min"]
        if dur > 0:
            duration_stats[dur].append(1 if r["status"] == "completed" else 0)

    best_dur = None
    best_rate = -1
    for dur, results in duration_stats.items():
        if len(results) >= 3:
            rate = sum(results) / len(results)
            if rate > best_rate:
                best_rate = rate
                best_dur = dur

    if best_dur and best_rate >= 0.7 and best_dur != 25:
        suggestions.append({
            "type": "pomodoro_best_duration",
            "priority": PRIORITY_MEDIUM,
            "title": f"{best_dur} 分钟是你的黄金番茄时长",
            "detail": f"过去 {days} 天，你在 {best_dur} 分钟番茄下完成率高达 {best_rate * 100:.0f}%，比标准 25 分钟更适合你。",
            "action": f"下次专注试试 {best_dur} 分钟",
            "icon": "⏱️",
        })

    if avg_distractions > 2:
        suggestions.append({
            "type": "pomodoro_distraction",
            "priority": PRIORITY_HIGH,
            "title": f"平均每个番茄被打断 {avg_distractions:.1f} 次",
            "detail": f"过去 {days} 天，你的番茄钟平均被打断 {avg_distractions:.1f} 次。建议开启学霸模式或通知免打扰，保护专注力。",
            "action": "开启学霸硬锁机模式",
            "icon": "🔔",
        })

    return suggestions


def _analyze_distraction_sources(today: date, days: int) -> list:
    """分析高频分心源"""
    suggestions = []
    start = (today - timedelta(days=days - 1)).isoformat()
    activities = db.get_activities(start, today.isoformat())

    if not activities or len(activities) < 30:
        return suggestions

    # 统计生活类应用出现次数
    distraction_apps: dict[str, int] = defaultdict(int)
    for act in activities:
        if act.get("category") == "生活":
            app = act.get("app_name", "Unknown")
            distraction_apps[app] += 1

    if not distraction_apps:
        return suggestions

    top_distraction = max(distraction_apps, key=distraction_apps.get)
    top_count = distraction_apps[top_distraction]
    total_distraction = sum(distraction_apps.values())

    if top_count >= 10 and top_count / total_distraction > 0.4:
        # 获取友好名称
        try:
            from app_tracker import get_display_name
            display_name = get_display_name(top_distraction)
        except Exception:
            display_name = top_distraction.replace(".exe", "")

        suggestions.append({
            "type": "distraction_source",
            "priority": PRIORITY_HIGH,
            "title": f"「{display_name}」是你最大的分心源",
            "detail": f"过去 {days} 天，你在「{display_name}」上花了 {top_count} 次活动记录，占分心时间的 {top_count / total_distraction * 100:.0f}%。",
            "action": "在专注模式中屏蔽此应用",
            "icon": "🚫",
        })

    return suggestions


def _analyze_streak_risk(today: date) -> list:
    """分析习惯连续性风险"""
    suggestions = []
    today_str = today.isoformat()
    yesterday = (today - timedelta(days=1)).isoformat()

    try:
        with db.get_conn() as conn:
            # 检查今日是否有活动
            today_count = conn.execute(
                "SELECT COUNT(*) as c FROM activities WHERE date(timestamp) = ?",
                (today_str,),
            ).fetchone()
            # 检查昨日活动量
            yesterday_count = conn.execute(
                "SELECT COUNT(*) as c FROM activities WHERE date(timestamp) = ?",
                (yesterday,),
            ).fetchone()
            # 检查连续活动天数
            recent = conn.execute(
                "SELECT DISTINCT date(timestamp) as d FROM activities "
                "WHERE date(timestamp) >= ? ORDER BY d DESC",
                ((today - timedelta(days=7)).isoformat(),),
            ).fetchall()
    except Exception:
        return suggestions

    active_days = len(recent)
    today_acts = today_count["c"] if today_count else 0
    yesterday_acts = yesterday_count["c"] if yesterday_count else 0

    # 如果已经连续 5+ 天活跃，但今天还没开始
    if active_days >= 5 and today_acts < 3:
        suggestions.append({
            "type": "streak_risk",
            "priority": PRIORITY_HIGH,
            "title": f"你已经连续活跃 {active_days} 天了",
            "detail": f"今天才记录了 {today_acts} 条活动。别让连续纪录断在这里，打开电脑开始工作吧！",
            "action": "开始一个番茄钟",
            "icon": "🔥",
        })

    return suggestions
