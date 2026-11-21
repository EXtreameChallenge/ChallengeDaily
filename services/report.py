"""ChallengeDaily Windows 版 — Markdown 日报生成（门面层）。

轮11 B33：报表逻辑拆到 report_layers/aggregation.py、templates.py、ai_enhance.py。
本模块保留对外的生成入口与兼容导出，行为与拆分前逐字节一致。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

import config
import db as _db
from app_tracker import get_display_name
from config import REPORT_DIR
from db import get_activities, get_daily_summary, get_app_usage, save_report

from report_layers.aggregation import (
    _format_duration,
    _estimate_focus_hours,
    _count_focus_sessions,
    _group_into_blocks,
    _build_category_narrative,
    _natural_time_span,
    _weekday_str_deep,
    _build_rich_data_context,
    _compute_attention_index,
    _compute_emotion_curve,
    _compute_skill_radar,
    _analyze_work_patterns,
    _build_activity_timeline_data,
    _get_weather_info,
    _get_yesterday_comparison,
    _weather_cache_set,
    _safe_get,
    _parse_ts_hour,
    _smart_sample_timeline,
)
from report_layers.templates import (
    _template_standard,
    _template_simple,
    _template_technical,
    _template_okr,
    _template_deep,
    _template_ai,
    _build_ai_report_prompt,
)
from report_layers.ai_enhance import (
    _generate_ai_deep_analysis,
    _fallback_analysis,
    enhance_report_with_ai_analysis,
)

logger = logging.getLogger(__name__)

_TEMPLATE_MAP = {
    "standard": _template_standard,
    "simple": _template_simple,
    "technical": _template_technical,
    "okr": _template_okr,
    "ai": _template_ai,
    "deep": _template_deep,
}

def _save(content: str, target_date: str):
    """同时存到文件和数据库，自动添加 AIGC 标记"""
    # 检测是否已有 AIGC 标记，避免重复添加
    aigc_label = "\n\n---\n*本报告由 ChallengeDaily AI 辅助生成，内容仅供参考*"
    if aigc_label.strip() not in content and "ChallengeDaily AI" not in content:
        content = content.rstrip() + aigc_label
    report_path = REPORT_DIR / f"report_{target_date}.md"
    report_path.write_text(content, encoding="utf-8")
    save_report(target_date, content)


def get_report_files() -> list:
    """列出所有已生成的报告文件"""
    reports = []
    for f in sorted(REPORT_DIR.glob("report_*.md"), reverse=True):
        date_str = f.stem.replace("report_", "")
        reports.append({"date": date_str, "path": str(f)})
    return reports


def _build_template_context(target_date: str) -> dict:
    """为自定义 Markdown 模板构建占位符 context。

    返回的 dict 包含 report_templates.SUPPORTED_PLACEHOLDERS 中定义的全部 key，
    所有值均为字符串，供 render_template 用 str.replace 替换。
    任何子查询失败都不阻断主流程，对应字段回退为友好空值。
    """
    ctx = {k: "" for k in (
        "date", "activities", "todos_completed", "todos_pending",
        "pomodoro_count", "focus_minutes", "apps_top5",
        "user_name", "user_role",
    )}
    ctx["date"] = target_date

    # ── 活动摘要（文本列表）+ Top5 应用 ──
    try:
        activities = get_activities(target_date, target_date)
        app_usage = get_app_usage(target_date, target_date)
        if activities:
            blocks = _group_into_blocks(activities)
            narratives = _build_category_narrative(blocks)
            lines = []
            for narr in narratives:
                line = f"- **{narr['category']}**（{narr['duration_str']}）：{narr['time_desc']}"
                if narr.get("summary"):
                    line += f"，{narr['summary']}"
                lines.append(line)
            ctx["activities"] = "\n".join(lines) if lines else "今日暂无活动记录。"
        else:
            ctx["activities"] = "今日暂无活动记录。"

        if app_usage:
            app_lines = []
            for au in app_usage[:5]:
                tsec = (au.get("duration_min", 0) or 0) * 60
                app_lines.append(f"- {get_display_name(au['app_name'])}：{_format_duration(tsec)}")
            ctx["apps_top5"] = "\n".join(app_lines)
    except Exception as e:
        logger.warning(f"构建活动/应用上下文失败(非致命): {e}")

    # ── 待办完成情况 ──
    try:
        all_todos = _db.get_todos()
        done = [t for t in all_todos if (t.get("status") or "").lower() == "completed"]
        pending = [t for t in all_todos if (t.get("status") or "").lower() != "completed"]
        ctx["todos_completed"] = ("\n".join(f"- [x] {t.get('title', '')}" for t in done)
                                  if done else "（无已完成待办）")
        ctx["todos_pending"] = ("\n".join(f"- [ ] {t.get('title', '')}" for t in pending)
                                if pending else "（无待处理待办）")
    except Exception as e:
        logger.warning(f"构建待办上下文失败(非致命): {e}")

    # ── 番茄钟 / 专注时长 ──
    try:
        sessions = _db.get_pomodoro_sessions(target_date)
        completed = [s for s in sessions if (s.get("status") or "") == "completed"]
        ctx["pomodoro_count"] = str(len(completed))
        ctx["focus_minutes"] = str(int(sum(s.get("duration_min", 0) or 0 for s in completed)))
    except Exception as e:
        logger.warning(f"构建番茄上下文失败(非致命): {e}")

    # ── 用户画像 ──
    try:
        from user_profile import get_profile
        profile = get_profile() or {}
        ctx["user_name"] = profile.get("nickname", "") or ""
        ctx["user_role"] = profile.get("role", "") or ""
    except Exception as e:
        logger.warning(f"构建用户画像上下文失败(非致命): {e}")

    return ctx


def _work_records_section(target_date: str) -> str:
    """B18：日报消费小黑 work_records — 把当日工作记录摘要追加进日报。"""
    try:
        import xiaohei_core as xc
        records = xc.list_work_records(target_date, limit=50)
        if not records:
            return ""
        summary = xc.get_work_records_daily_summary(target_date)
        lines = ["", "## 工作记录（小黑）",
                 f"- 共 {summary.get('count', len(records))} 条，累计 {summary.get('total_minutes', 0)} 分钟"]
        for r in records[:8]:
            mins = int((r.get("duration_sec") or 0) // 60)
            title = (r.get("title") or "未命名")[:40]
            cat = r.get("category") or "其他"
            lines.append(f"- **{title}**（{cat}，{mins} 分钟）")
        if len(records) > 8:
            lines.append(f"- …其余 {len(records) - 8} 条见小黑工作记录")
        return "\n".join(lines)
    except Exception as e:
        logger.debug(f"日报追加工作记录失败（忽略）: {e}")
        return ""


def _mark_first_report_badge():
    """B18：生成首份日报后解锁「初出茅庐」徽章（幂等，已解锁则无副作用）。"""
    try:
        import xiaohei_core as xc
        xc.badge_track_progress("first_report", 1)
    except Exception:
        pass


def generate_daily_report(target_date: str = None, template: str = "standard",
                          template_id: int = None) -> str:
    """
    生成指定日期的 Markdown 日报，保存到 data/reports/ 和数据库。
    target_date: "YYYY-MM-DD" 格式，默认今天。
    template: "standard" / "simple" / "technical" / "okr" / "ai"（内置模板函数）
    template_id: 若指定，则使用 report_templates 表中的自定义 Markdown 模板渲染；
                 为 None 或模板不存在/渲染失败时，回退到 template 参数对应的内置模板逻辑。
    返回生成的报告内容。
    """
    if not target_date:
        target_date = date.today().isoformat()

    # 自定义 Markdown 模板渲染
    if template_id is not None:
        try:
            import report_templates as _rt
            tpl = _rt.get_template(int(template_id))
            if tpl:
                context = _build_template_context(target_date)
                content = _rt.render_template(tpl["content_md"], context)
                content += _work_records_section(target_date)
                _save(content, target_date)
                _mark_first_report_badge()
                return content
            logger.warning(f"template_id={template_id} 不存在，回退内置模板")
        except Exception as e:
            logger.error(f"自定义模板渲染失败，回退内置模板: {e}")

    # 数据获取
    activities = get_activities(target_date, target_date)
    summary_data = get_daily_summary(target_date, target_date)
    app_usage = get_app_usage(target_date, target_date)

    # 选择模板
    tmpl_func = _TEMPLATE_MAP.get(template, _template_standard)
    content = tmpl_func(target_date, activities, summary_data, app_usage)
    content += _work_records_section(target_date)

    _save(content, target_date)
    _mark_first_report_badge()
    return content


def generate_weekly_report(start_date: str = None, template: str = "standard") -> str:
    """
    生成周报：聚合从 start_date 起往前7天的数据。
    start_date: "YYYY-MM-DD"，默认今天（即今天往前7天）。
    """
    if not start_date:
        start_date = date.today().isoformat()
    from datetime import timedelta
    sd = datetime.strptime(start_date, "%Y-%m-%d").date()
    week_start = (sd - timedelta(days=sd.weekday()))  # 本周一
    # 周报范围：本周一到本周日（共 7 天）
    start_date = week_start.isoformat()
    end_date = (week_start + timedelta(days=6)).isoformat()

    # 聚合多日数据
    activities = get_activities(start_date, end_date)
    summary_data = get_daily_summary(start_date, end_date)
    app_usage = get_app_usage(start_date, end_date)

    # 按天分组
    days_data = {}
    for act in activities:
        ds = act["timestamp"][:10]
        if ds not in days_data:
            days_data[ds] = []
        days_data[ds].append(act)

    total = summary_data["total"]
    if total == 0:
        return f"# {start_date} ~ {end_date} 周报\n\n本周无工作记录。\n"

    # 按分类聚合
    blocks = _group_into_blocks(activities)
    cat_narratives = _build_category_narrative(blocks)
    focus_hours = _estimate_focus_hours(activities, app_usage)
    focus_sessions = _count_focus_sessions(activities)
    total_act_count = sum(summary_data["categories"].values()) or 1  # avoid ZeroDivision

    lines = [
        f"# {start_date} ~ {end_date} 周报",
        "",
        "## 本周概览",
        f"- 工作天数：{len(days_data)} 天",
        f"- 总专注时长：{focus_hours}",
        f"- 深度工作：{focus_sessions} 次",
        f"- 工作类别：{len(cat_narratives)} 个",
        "",
    ]

    # 每日概览
    lines.append("## 每日概览")
    lines.append("")
    for ds in sorted(days_data.keys()):
        day_acts = days_data[ds]
        day_cats = {}
        for a in day_acts:
            c = a["category"]
            day_cats[c] = day_cats.get(c, 0) + 1
        top_cat = max(day_cats, key=day_cats.get) if day_cats else ""
        day_hours = _format_duration(len(day_acts) * config.SCREENSHOT_INTERVAL_SEC)
        lines.append(f"- **{ds}**：{day_hours}，主要 {top_cat}")
    lines.append("")

    # 分类工作概览
    lines.append("## 本周工作概览")
    lines.append("")
    for narr in cat_narratives:
        lines.append(f"**{narr['category']}**（{narr['duration_str']}）")
        if narr['summary']:
            lines.append(f"- 内容：{narr['summary']}")
        if narr['apps']:
            lines.append(f"- 工具：{narr['apps']}")
        lines.append("")

    # 时间分配
    lines.append("## 时间分配")
    lines.append("")
    lines.append("| 分类 | 时长 | 占比 |")
    lines.append("|------|------|------|")
    for cat, cnt in summary_data["categories"].items():
        total_seconds = cnt * config.SCREENSHOT_INTERVAL_SEC
        time_str = _format_duration(total_seconds)
        pct = f"{round(cnt / total_act_count * 100)}%"
        lines.append(f"| {cat} | {time_str} | {pct} |")
    lines.append("")

    # 应用使用 Top 8
    if app_usage:
        lines.append("## 应用使用 Top 8")
        lines.append("")
        lines.append("| 应用 | 时长 |")
        lines.append("|------|------|")
        for au in app_usage[:8]:
            total_sec = au["duration_min"] * 60
            time_str = _format_duration(total_sec)
            display_name = get_display_name(au["app_name"])
            lines.append(f"| {display_name} | {time_str} |")
        lines.append("")

    content = "\n".join(lines)
    report_path = REPORT_DIR / f"reportweekly_{start_date}_{end_date}.md"
    report_path.write_text(content, encoding="utf-8")
    # 同步存入数据库（以便历史报告页展示）
    save_report(f"weekly_{start_date}_{end_date}", content)
    return content


def generate_monthly_report(year_month: str = None, template: str = "standard") -> str:
    """
    生成月报：聚合指定月份的数据。
    year_month: "YYYY-MM"，默认当前月。
    """
    if not year_month:
        year_month = date.today().strftime("%Y-%m")

    import calendar
    y, m = int(year_month[:4]), int(year_month[5:7])
    _, last_day = calendar.monthrange(y, m)
    start_date = f"{year_month}-01"
    end_date = f"{year_month}-{last_day:02d}"

    # 聚合多日数据
    activities = get_activities(start_date, end_date)
    summary_data = get_daily_summary(start_date, end_date)
    app_usage = get_app_usage(start_date, end_date)

    # 按天分组
    days_data = {}
    for act in activities:
        ds = act["timestamp"][:10]
        if ds not in days_data:
            days_data[ds] = []
        days_data[ds].append(act)

    total = summary_data["total"]
    if total == 0:
        return f"# {year_month} 月报\n\n本月无工作记录。\n"

    blocks = _group_into_blocks(activities)
    cat_narratives = _build_category_narrative(blocks)
    focus_hours = _estimate_focus_hours(activities, app_usage)
    focus_sessions = _count_focus_sessions(activities)
    total_act_count = sum(summary_data["categories"].values()) or 1  # avoid ZeroDivision

    lines = [
        f"# {year_month} 月报",
        "",
        "## 本月概览",
        f"- 工作天数：{len(days_data)} 天",
        f"- 总专注时长：{focus_hours}",
        f"- 深度工作：{focus_sessions} 次",
        f"- 工作类别：{len(cat_narratives)} 个",
        "",
    ]

    # 按周拆分概览
    lines.append("## 每周概览")
    lines.append("")
    sorted_days = sorted(days_data.keys())
    from datetime import timedelta
    current_week = []
    week_num = 1
    for ds in sorted_days:
        current_week.append(ds)
        d = datetime.strptime(ds, "%Y-%m-%d").date()
        if d.weekday() == 6 or ds == sorted_days[-1]:  # Sunday or last day
            week_hours = _format_duration(
                sum(len(days_data[d]) for d in current_week) * config.SCREENSHOT_INTERVAL_SEC
            )
            lines.append(f"- **第{week_num}周**（{current_week[0]} ~ {current_week[-1]}）：{week_hours}")
            week_num += 1
            current_week = []
    lines.append("")

    # 分类工作概览
    lines.append("## 本月工作概览")
    lines.append("")
    for narr in cat_narratives:
        lines.append(f"**{narr['category']}**（{narr['duration_str']}）")
        if narr['summary']:
            lines.append(f"- 内容：{narr['summary']}")
        if narr['apps']:
            lines.append(f"- 工具：{narr['apps']}")
        lines.append("")

    # 时间分配
    lines.append("## 时间分配")
    lines.append("")
    lines.append("| 分类 | 时长 | 占比 |")
    lines.append("|------|------|------|")
    for cat, cnt in summary_data["categories"].items():
        total_seconds = cnt * config.SCREENSHOT_INTERVAL_SEC
        time_str = _format_duration(total_seconds)
        pct = f"{round(cnt / total_act_count * 100)}%"
        lines.append(f"| {cat} | {time_str} | {pct} |")
    lines.append("")

    content = "\n".join(lines)
    report_path = REPORT_DIR / f"reportmonthly_{year_month}.md"
    report_path.write_text(content, encoding="utf-8")
    # 同步存入数据库
    save_report(f"monthly_{year_month}", content)
    return content
