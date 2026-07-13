"""
ChallengeDaily Windows 版 — Markdown 日报生成
支持六种报告模板：standard / simple / technical / okr / ai / deep
核心思路：按分类聚合并生成高质量摘要，而非逐条罗列活动日志
深度洞察模板：融合天气、跨日对比、心流检测、注意力指数、情绪曲线等专业分析
"""
import os
import json
import re as _re
import socket
from datetime import date, datetime, timedelta
from collections import OrderedDict
from app_tracker import get_display_name
from db import get_activities, get_daily_summary, get_app_usage, save_report
from config import REPORT_DIR
import config
import db as _db
import logging

logger = logging.getLogger(__name__)


def _get_pomodoro_summary_line(target_date: str) -> str:
    """构造一行番茄统计文本，注入到 AI 日报 prompt 上下文中。

    复用 db.get_pomodoro_sessions 查询当日会话；失败时返回空串不影响日报生成。
    """
    try:
        sessions = _db.get_pomodoro_sessions(target_date)
        completed = [s for s in sessions if s.get('status') == 'completed']
        total_min = sum(s.get('duration_min', 0) for s in completed)
        distractions = sum(s.get('interrupted_count', 0) or 0 for s in sessions)
        if not sessions:
            return ""
        return (f"番茄统计：今日完成 {len(completed)} 个番茄"
                f"（{total_min}分钟），分心 {distractions} 次")
    except Exception as e:
        logger.debug(f"番茄统计行构造失败(非致命): {e}")
        return ""


# ── 公共工具函数 ──────────────────────────────────

def _format_duration(total_seconds: float) -> str:
    """将秒数格式化为可读时长"""
    if total_seconds < 60:
        return f"{max(int(total_seconds), 1)}s"
    minutes = total_seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}min"
    hours = minutes / 60
    return f"{hours:.1f}h"


def _estimate_focus_hours(activities: list, app_usage: list = None) -> str:
    """根据 app_usage 表的实际 duration_sec 聚合专注时长；
    若未传入 app_usage，回退到按活动条数估算。"""
    if app_usage:
        # app_usage 中 duration_min 已经是分钟，转回秒聚合
        total_seconds = sum((au.get("duration_min", 0) or 0) * 60 for au in app_usage)
        if total_seconds > 0:
            return _format_duration(total_seconds)
    # 回退：按活动条数 × 采样间隔估算
    if not activities:
        return "0s"
    total_seconds = len(activities) * config.SCREENSHOT_INTERVAL_SEC
    return _format_duration(total_seconds)


def _count_focus_sessions(activities: list) -> int:
    """统计专注次数（同一分类持续 >= 15min 算一次）"""
    if not activities:
        return 0
    # 确保按时间升序排列（get_activities 返回 DESC）
    sorted_acts = sorted(activities, key=lambda a: a.get("timestamp", ""))
    sessions = 0
    current_cat = None
    current_count = 0
    for act in sorted_acts:
        if act["category"] == current_cat:
            current_count += 1
        else:
            if current_count * config.SCREENSHOT_INTERVAL_SEC >= 900:
                sessions += 1
            current_cat = act["category"]
            current_count = 1
    if current_count * config.SCREENSHOT_INTERVAL_SEC >= 900:
        sessions += 1
    return sessions


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


# ── 活动聚合：将逐条记录转换为工作段落 ──────────────

def _group_into_blocks(activities: list) -> list[dict]:
    """
    将活动按"同分类连续"分组为工作段落（block）。
    每个 block 包含：
      - category: 分类名
      - start_time: 段落开始时间 (HH:MM)
      - end_time: 段落结束时间 (HH:MM)
      - duration_sec: 持续秒数
      - summaries: 该段落内各行 AI 摘要列表（去重）
      - apps: 涉及的应用集合（去重）
      - window_titles: 涉及的窗口标题集合（去重）
    """
    if not activities:
        return []

    blocks = []
    cur_cat = None
    cur_summaries = []
    cur_apps = set()
    cur_titles = set()
    cur_start = None
    cur_count = 0

    for act in activities:
        cat = act["category"]
        ts = act["timestamp"]

        if cat != cur_cat:
            # 保存上一段
            if cur_cat is not None:
                blocks.append(_make_block(cur_cat, cur_start, ts, cur_count,
                                          cur_summaries, cur_apps, cur_titles))
            # 开始新段
            cur_cat = cat
            cur_start = ts
            cur_summaries = []
            cur_apps = set()
            cur_titles = set()
            cur_count = 0

        cur_count += 1
        display_name = get_display_name(act["app_name"])
        cur_apps.add(display_name)
        win_title = act.get("window_title", "")
        if win_title:
            cur_titles.add(win_title)
        summary = act.get("summary", "")
        if summary and summary != "未配置AI":
            cur_summaries.append(summary)

    # 最后一段
    if cur_cat is not None:
        blocks.append(_make_block(cur_cat, cur_start, activities[-1]["timestamp"],
                                  cur_count, cur_summaries, cur_apps, cur_titles))

    return blocks


def _make_block(category, start_ts, end_ts, count, summaries, apps, titles) -> dict:
    """构造一个工作段落"""
    # 去重摘要（保持顺序）
    seen = set()
    unique_summaries = []
    for s in summaries:
        if s not in seen:
            seen.add(s)
            unique_summaries.append(s)

    duration_sec = max(count * config.SCREENSHOT_INTERVAL_SEC, config.SCREENSHOT_INTERVAL_SEC)
    start_hm = start_ts[11:16] if len(start_ts) > 16 else start_ts
    end_hm = end_ts[11:16] if len(end_ts) > 16 else end_ts

    return {
        "category": category,
        "start_time": start_hm,
        "end_time": end_hm,
        "duration_sec": duration_sec,
        "duration_str": _format_duration(duration_sec),
        "summaries": unique_summaries,
        "apps": sorted(apps),
        "window_titles": sorted(titles),
    }


def _blocks_by_category(blocks: list[dict]) -> OrderedDict:
    """将 blocks 按分类归纳，合并同分类的多段为一段描述"""
    by_cat = OrderedDict()
    for b in blocks:
        cat = b["category"]
        if cat not in by_cat:
            by_cat[cat] = {
                "category": cat,
                "total_sec": 0,
                "time_ranges": [],
                "all_summaries": [],
                "all_apps": set(),
            }
        entry = by_cat[cat]
        entry["total_sec"] += b["duration_sec"]
        entry["time_ranges"].append(f"{b['start_time']}-{b['end_time']}")
        entry["all_summaries"].extend(b["summaries"])
        entry["all_apps"].update(b["apps"])

    # 对每个分类去重摘要
    for cat, entry in by_cat.items():
        seen = set()
        unique = []
        for s in entry["all_summaries"]:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        entry["all_summaries"] = unique

    return by_cat


def _merge_summaries(summaries: list[str], max_items: int = 4) -> str:
    """将多条摘要合并为自然语言段落，使用多样化连接词降低机器味"""
    if not summaries:
        return ""
    if len(summaries) <= max_items:
        # 用自然连接词代替纯分号
        connectors = ["，", "，同时", "，另外", "，还"]
        if len(summaries) == 1:
            return summaries[0]
        if len(summaries) == 2:
            return f"{summaries[0]}{connectors[1]}{summaries[1]}"
        # 3条以上：前几条用逗号，最后一条用连接词
        parts = summaries[:-1]
        last = summaries[-1]
        return "，".join(parts) + f"{connectors[min(len(summaries)-2, len(connectors)-1)]}{last}"
    # 太多条则截断 + 更自然的省略
    preview = "，".join(summaries[:max_items])
    remaining = len(summaries) - max_items
    return f"{preview}等{remaining}项"


def _build_category_narrative(blocks: list[dict]) -> list[dict]:
    """构建分类叙事：每个分类 → 一段自然描述"""
    by_cat = _blocks_by_category(blocks)
    result = []
    for cat, entry in by_cat.items():
        time_desc = "、".join(entry["time_ranges"][:3])
        if len(entry["time_ranges"]) > 3:
            time_desc += "等"
        summary_text = _merge_summaries(entry["all_summaries"])
        apps_str = "、".join(list(entry["all_apps"])[:4])
        result.append({
            "category": cat,
            "duration_str": _format_duration(entry["total_sec"]),
            "total_sec": entry["total_sec"],
            "time_desc": time_desc,
            "summary": summary_text,
            "apps": apps_str,
            "all_summaries": entry["all_summaries"],
        })
    return result


# ── 自然语言生成辅助 ──

def _natural_time_span(first_ts: str, last_ts: str) -> str:
    """生成自然的工作时段描述"""
    if not first_ts or not last_ts:
        return ""
    start = first_ts[11:16]
    end = last_ts[11:16]
    sh, sm = start.split(":")
    eh, em = end.split(":")
    # 用口语化的时段描述
    start_period = _time_period(int(sh))
    end_period = _time_period(int(eh))
    if start_period == end_period:
        return f"{start_period}{start}到{end}"
    return f"{start_period}{start}到{end_period}{end}"


def _time_period(hour: int) -> str:
    """根据小时数返回时段前缀"""
    if 0 <= hour < 6:
        return "凌晨"
    if 6 <= hour < 9:
        return "早上"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 22:
        return "晚上"
    return "深夜"


def _natural_overview(activities, cat_narratives, first_ts, last_ts, focus_hours, focus_sessions) -> str:
    """生成自然语言的今日概要段落，避免公文化表述"""
    if not cat_narratives:
        return "今天暂无工作记录。"

    time_span = _natural_time_span(first_ts, last_ts) if first_ts and last_ts else ""

    # 构建开头
    opening = f"今天从{time_span}投入了工作" if time_span else "今天投入了工作"

    # 核心工作描述
    top_cats = [n["category"] for n in cat_narratives[:3]]
    if len(top_cats) == 1:
        core_desc = f"，主要精力放在了{top_cats[0]}上"
    elif len(top_cats) == 2:
        core_desc = f"，核心工作是{top_cats[0]}和{top_cats[1]}"
    elif len(top_cats) >= 3:
        core_desc = f"，涵盖了{top_cats[0]}、{top_cats[1]}、{top_cats[2]}等方向"
    else:
        core_desc = ""

    # 专注时长
    focus_desc = f"，累计专注{focus_hours}"
    if focus_sessions > 0:
        focus_desc += f"，进入深度状态{focus_sessions}次"

    # 分类数量
    cat_desc = f"涉及{len(cat_narratives)}个工作类别"

    return f"{opening}{core_desc}{focus_desc}，{cat_desc}。"


# ── 模板1: 标准 (standard) ──────────────────────────
# 真正的日报：概要 + 分类工作概览（自然语言）+ 重点事项

def _template_standard(target_date: str, activities, summary_data, app_usage) -> str:
    if not activities:
        return f"# {target_date} 工作日报\n\n今天暂无工作记录。\n"

    total = summary_data["total"]
    first_ts = summary_data.get("first_ts", "")
    last_ts = summary_data.get("last_ts", "")
    focus_hours = _estimate_focus_hours(activities, app_usage)
    focus_sessions = _count_focus_sessions(activities)

    blocks = _group_into_blocks(activities)
    cat_narratives = _build_category_narrative(blocks)

    lines = [
        f"# {target_date} 工作日报",
        "",
        "## 今日概要",
    ]

    # 自然语言概要
    overview = _natural_overview(activities, cat_narratives, first_ts, last_ts, focus_hours, focus_sessions)
    lines.append(overview)
    lines.append("")

    # 分类工作概览 — 每个分类一段自然语言描述
    lines.append("## 工作详情")
    lines.append("")
    for narr in cat_narratives:
        lines.append(f"**{narr['category']}**（{narr['duration_str']}）")
        lines.append(f"- 时段：{narr['time_desc']}")
        if narr['summary']:
            lines.append(f"- 内容：{narr['summary']}")
        if narr['apps']:
            lines.append(f"- 工具：{narr['apps']}")
        lines.append("")

    # 分类时长分布表格（紧凑）
    lines.append("## 时间分配")
    lines.append("")
    lines.append("| 分类 | 时长 | 占比 |")
    lines.append("|------|------|------|")
    total_act_count = sum(summary_data["categories"].values()) or 1  # avoid ZeroDivision
    for cat, cnt in summary_data["categories"].items():
        total_seconds = cnt * config.SCREENSHOT_INTERVAL_SEC
        time_str = _format_duration(total_seconds)
        pct = f"{round(cnt / total_act_count * 100)}%"
        lines.append(f"| {cat} | {time_str} | {pct} |")
    lines.append("")

    # 应用使用时长（Top 8）
    if app_usage:
        lines.append("## 应用使用")
        lines.append("")
        lines.append("| 应用 | 时长 |")
        lines.append("|------|------|")
        for au in app_usage[:8]:
            total_sec = au["duration_min"] * 60
            time_str = _format_duration(total_sec)
            display_name = get_display_name(au["app_name"])
            lines.append(f"| {display_name} | {time_str} |")
        lines.append("")

    return "\n".join(lines)


# ── 模板2: 简洁 (simple) ──────────────────────────
# 极简报告：一句话总结 + 分类占比 + 核心事项

def _template_simple(target_date: str, activities, summary_data, app_usage) -> str:
    if not activities:
        return f"# {target_date} 日报\n\n今天暂无工作记录。\n"

    total = summary_data["total"]
    focus_hours = _estimate_focus_hours(activities, app_usage)
    first_ts = summary_data.get("first_ts", "")
    last_ts = summary_data.get("last_ts", "")

    blocks = _group_into_blocks(activities)
    cat_narratives = _build_category_narrative(blocks)

    # 生成一句话总结
    top_cats = cat_narratives[:3]
    top_desc = "、".join(n["category"] for n in top_cats)

    lines = [
        f"# {target_date} 日报",
        "",
    ]

    # 自然的一句话总结
    time_span = _natural_time_span(first_ts, last_ts) if first_ts and last_ts else ""
    if time_span:
        lines.append(f"今天{time_span}，专注{focus_hours}，主要在忙{top_desc}。")
    else:
        lines.append(f"今天专注{focus_hours}，主要在忙{top_desc}。")
    lines.append("")

    # 分类占比（紧凑）
    lines.append("## 时间分配")
    lines.append("")
    total_activity_count = sum(summary_data["categories"].values())
    for cat, cnt in summary_data["categories"].items():
        pct = round(cnt / total_activity_count * 100) if total_activity_count > 0 else 0
        total_seconds = cnt * config.SCREENSHOT_INTERVAL_SEC
        time_str = _format_duration(total_seconds)
        lines.append(f"- **{cat}**：{time_str}（{pct}%）")
    lines.append("")

    # 重点工作
    lines.append("## 重点工作")
    lines.append("")
    for narr in cat_narratives[:5]:
        desc = narr['summary'] if narr['summary'] else f"使用 {narr['apps']}"
        lines.append(f"- [{narr['category']}] {desc}")
    lines.append("")

    return "\n".join(lines)


# ── 模板3: 技术 (technical) ──────────────────────────
# 技术人员专用：强调技术分类、开发工具明细、技术活动段落

def _template_technical(target_date: str, activities, summary_data, app_usage) -> str:
    if not activities:
        return f"# {target_date} 技术日报\n\n今天暂无工作记录。\n"

    total = summary_data["total"]
    focus_hours = _estimate_focus_hours(activities, app_usage)
    focus_sessions = _count_focus_sessions(activities)
    first_ts = summary_data.get("first_ts", "")
    last_ts = summary_data.get("last_ts", "")

    tech_cats = {"开发", "测试", "运维", "数据分析"}
    tech_count = sum(summary_data["categories"].get(c, 0) for c in tech_cats)
    tech_seconds = tech_count * config.SCREENSHOT_INTERVAL_SEC

    blocks = _group_into_blocks(activities)
    cat_narratives = _build_category_narrative(blocks)

    lines = [
        f"# {target_date} 技术日报",
        "",
        "## 技术概览",
        f"- 专注时长：{focus_hours}，深度工作 {focus_sessions} 次",
    ]
    time_span = _natural_time_span(first_ts, last_ts) if first_ts and last_ts else ""
    if time_span:
        lines.append(f"- 活跃时段：{time_span}")
    tech_pct = round(tech_count / total * 100) if total > 0 else 0
    lines.append(f"- 技术工作占比：{tech_pct}%（{_format_duration(tech_seconds)}）")
    lines.append("")

    # 技术工作详情
    tech_narratives = [n for n in cat_narratives if n["category"] in tech_cats]
    if tech_narratives:
        lines.append("## 技术工作")
        lines.append("")
        for narr in tech_narratives:
            lines.append(f"**{narr['category']}**（{narr['duration_str']}）")
            lines.append(f"- 时段：{narr['time_desc']}")
            if narr['summary']:
                lines.append(f"- 内容：{narr['summary']}")
            if narr['apps']:
                lines.append(f"- 工具：{narr['apps']}")
            lines.append("")

    # 开发工具使用明细
    lines.append("## 开发工具")
    lines.append("")
    dev_apps = []
    dev_keywords = ["code", "vscode", "idea", "pycharm", "webstorm", "terminal",
                    "cmd", "powershell", "git", "vim", "nvim", "cursor",
                    "studio", "eclipse", "sublime", "xcode", "docker",
                    "navicat", "datagrip", "dbeaver", "postman", "insomnia"]
    for au in app_usage[:10]:
        app_lower = au["app_name"].lower()
        is_dev = any(kw in app_lower for kw in dev_keywords)
        if is_dev:
            total_sec = au["duration_min"] * 60
            time_str = _format_duration(total_sec)
            display_name = get_display_name(au["app_name"])
            dev_apps.append(f"- **{display_name}**：{time_str}")

    if dev_apps:
        lines.extend(dev_apps)
    else:
        lines.append("- 无开发工具使用记录")
    lines.append("")

    # 非技术活动概览（精简）
    non_tech_narratives = [n for n in cat_narratives if n["category"] not in tech_cats]
    if non_tech_narratives:
        lines.append("## 其他活动")
        lines.append("")
        for narr in non_tech_narratives:
            desc = narr['summary'] if narr['summary'] else f"使用 {narr['apps']}"
            lines.append(f"- [{narr['category']}] {narr['duration_str']} — {desc}")
        lines.append("")

    return "\n".join(lines)


# ── 模板4: OKR ──────────────────────────────────
# OKR 格式：按目标和关键结果组织，强调产出和推进

def _template_okr(target_date: str, activities, summary_data, app_usage) -> str:
    if not activities:
        return f"# {target_date} OKR 日报\n\n今天暂无工作记录。\n"

    total = summary_data["total"]
    focus_hours = _estimate_focus_hours(activities, app_usage)
    focus_sessions = _count_focus_sessions(activities)
    first_ts = summary_data.get("first_ts", "")
    last_ts = summary_data.get("last_ts", "")

    blocks = _group_into_blocks(activities)
    cat_narratives = _build_category_narrative(blocks)

    # 按分类归纳为 OKR 目标
    work_cats = {"开发", "测试", "运维", "数据分析", "产品", "设计", "管理", "文档"}
    meeting_cats = {"会议", "沟通"}
    study_cats = {"学习"}
    life_cats = {"生活"}

    lines = [
        f"# {target_date} OKR 日报",
        "",
        "## 今日概览",
        f"- 专注：{focus_hours}，深度工作 {focus_sessions} 次",
    ]
    time_span = _natural_time_span(first_ts, last_ts) if first_ts and last_ts else ""
    if time_span:
        lines.append(f"- 工作时段：{time_span}")
    lines.append("")

    lines.append("## Objectives & Key Results")
    lines.append("")

    # O1: 核心业务推进
    work_narratives = [n for n in cat_narratives if n["category"] in work_cats]
    if work_narratives:
        work_sec = sum(n["total_sec"] for n in work_narratives)
        lines.append("### O1: 推进核心业务产出")
        lines.append(f"  - KR1: 核心工作投入 {_format_duration(work_sec)}")
        for narr in work_narratives:
            desc = narr['summary'] if narr['summary'] else f"使用 {narr['apps']}"
            lines.append(f"  - KR: {narr['category']}（{narr['duration_str']}）— {desc}")
        lines.append("")

    # O2: 协作与对齐
    meeting_narratives = [n for n in cat_narratives if n["category"] in meeting_cats]
    if meeting_narratives:
        meet_sec = sum(n["total_sec"] for n in meeting_narratives)
        lines.append("### O2: 团队协作与信息对齐")
        lines.append(f"  - KR1: 沟通协作投入 {_format_duration(meet_sec)}")
        for narr in meeting_narratives:
            desc = narr['summary'] if narr['summary'] else f"使用 {narr['apps']}"
            lines.append(f"  - KR: {narr['category']}（{narr['duration_str']}）— {desc}")
        lines.append("")

    # O3: 学习与成长
    study_narratives = [n for n in cat_narratives if n["category"] in study_cats]
    if study_narratives:
        study_sec = sum(n["total_sec"] for n in study_narratives)
        lines.append("### O3: 持续学习与能力提升")
        lines.append(f"  - KR1: 学习投入 {_format_duration(study_sec)}")
        for narr in study_narratives:
            desc = narr['summary'] if narr['summary'] else f"使用 {narr['apps']}"
            lines.append(f"  - KR: {narr['category']}（{narr['duration_str']}）— {desc}")
        lines.append("")

    # 分类时间分配
    lines.append("## 时间分配")
    lines.append("")
    lines.append("| 分类 | 时长 | 占比 |")
    lines.append("|------|------|------|")
    total_act_count = sum(summary_data["categories"].values()) or 1  # avoid ZeroDivision
    for cat, cnt in summary_data["categories"].items():
        total_seconds = cnt * config.SCREENSHOT_INTERVAL_SEC
        time_str = _format_duration(total_seconds)
        pct = f"{round(cnt / total_act_count * 100)}%"
        lines.append(f"| {cat} | {time_str} | {pct} |")
    lines.append("")

    # 明日方向 — 基于今日活动自动推断
    lines.append("## 明日方向")
    lines.append("")
    # 从每个主要分类的工作中推断明日计划
    suggestions = []
    for narr in cat_narratives[:4]:
        if narr['summary']:
            # 取最后一条摘要作为延续方向
            last_summary = narr['all_summaries'][-1] if narr.get('all_summaries') else narr['summary']
            suggestions.append(f"- 继续推进{narr['category']}：{last_summary}")
        elif narr['apps']:
            suggestions.append(f"- 继续使用 {narr['apps']} 推进{narr['category']}工作")
    if suggestions:
        lines.extend(suggestions)
    else:
        lines.append("（待补充）")
    lines.append("")

    return "\n".join(lines)


# ── 模板6: 深度洞察 (deep) ──────────────────────────
# 全面重构 v2：融合天气、跨日对比、注意力指数、情绪曲线、技能雷达、工作流分析
# 参考顶级产品：Day One / Stoic / Reflectly / 5-Minute Journal / Bullet Journal / Obsidian
# 生成一份真正丰富、深度、有温度的个人日报

import json as _json
import urllib.request
import urllib.error

_weather_cache: OrderedDict = OrderedDict()

def _weather_cache_set(key, value):
    """带 LRU 驱逐的天气缓存写入（最多保留 7 天数据）"""
    if key in _weather_cache:
        _weather_cache.move_to_end(key)
    _weather_cache[key] = value
    while len(_weather_cache) > 7:
        _weather_cache.popitem(last=False)
_WEEKDAYS_DEEP = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_CREATIVE_CATS = {"开发", "设计", "学习"}
_FOCUS_CATS_DEEP = {"开发", "设计", "文档", "测试", "数据分析", "学习"}
_MEETING_CATS_DEEP = {"会议", "沟通"}
_DEEP_WORK_THRESHOLD_MIN = 25


def _safe_get(d, key, default=None):
    try:
        if isinstance(d, dict):
            return d.get(key, default)
        if hasattr(d, "keys"):
            if key in d.keys():
                return d[key]
        return default
    except (KeyError, TypeError, IndexError):
        return default


def _parse_ts_hour(ts_str: str) -> int:
    try:
        return int(ts_str[11:13])
    except (ValueError, IndexError):
        return -1


def _weekday_str_deep(target_date: str) -> str:
    try:
        wd = datetime.strptime(target_date, "%Y-%m-%d").weekday()
        return _WEEKDAYS_DEEP[wd]
    except Exception:
        return ""


# ── 天气信息 ──────────────────────────────────────────

def _get_weather_info(target_date: str) -> dict:
    """通过 wttr.in 免费API获取天气"""
    if target_date in _weather_cache:
        return _weather_cache[target_date]
    result = {}
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        url = "https://wttr.in/?format=j1&lang=zh"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read().decode("utf-8", errors="replace"))
        weather_arr = data.get("weather", [])
        target_idx = 0
        if target_date != today_str and len(weather_arr) > 1:
            for i, w in enumerate(weather_arr):
                if w.get("date") == target_date:
                    target_idx = i
                    break
        if target_idx < len(weather_arr):
            w = weather_arr[target_idx]
            hourly = w.get("hourly", [])
            mid_hour = hourly[4] if len(hourly) > 4 else (hourly[0] if hourly else {})
            temp = mid_hour.get("tempC", "")
            humidity = mid_hour.get("humidity", "")
            desc_arr = mid_hour.get("lang_zh", mid_hour.get("weatherDesc", []))
            desc = ""
            if desc_arr:
                desc = desc_arr[0].get("value", "") if isinstance(desc_arr[0], dict) else str(desc_arr[0])
            wind_arr = mid_hour.get("windspeedKmph", "")
            wind_desc = "微风"
            try:
                ws = int(wind_arr)
                if ws < 12: wind_desc = "微风"
                elif ws < 30: wind_desc = "轻风"
                elif ws < 50: wind_desc = "中风"
                else: wind_desc = "强风"
            except (ValueError, TypeError):
                pass
            result = {
                "temp": f"{temp}°C" if temp else "",
                "desc": desc,
                "humidity": f"{humidity}%" if humidity else "",
                "wind": wind_desc,
            }
            if not result["temp"]:
                avg_t = w.get("avgtempC", "")
                result["temp"] = f"{avg_t}°C" if avg_t else ""
            if not result["desc"]:
                en_arr = mid_hour.get("weatherDesc", [])
                if en_arr:
                    result["desc"] = en_arr[0].get("value", "") if isinstance(en_arr[0], dict) else str(en_arr[0])
    except socket.timeout:
        logger.debug("天气获取超时（8秒），跳过天气数据")
    except Exception as e:
        logger.debug(f"天气获取失败: {e}")
    # 只缓存成功结果，避免网络瞬断导致当天天气永久为空
    if result:
        _weather_cache_set(target_date, result)
    return result


# ── 昨日对比 ──────────────────────────────────────────

def _get_yesterday_comparison(target_date: str) -> dict:
    result = {"yesterday_total": 0, "change_pct": 0, "yesterday_top_cat": "", "trend": "持平"}
    try:
        td = datetime.strptime(target_date, "%Y-%m-%d").date()
        yesterday = (td - timedelta(days=1)).isoformat()
        y_summary = get_daily_summary(yesterday, yesterday)
        t_summary = get_daily_summary(target_date, target_date)
        y_total = y_summary.get("total", 0) if y_summary else 0
        t_total = t_summary.get("total", 0) if t_summary else 0
        result["yesterday_total"] = y_total
        if y_total > 0:
            change = round((t_total - y_total) / y_total * 100, 1)
        elif t_total > 0:
            change = 100.0
        else:
            change = 0
        result["change_pct"] = change
        y_cats = y_summary.get("categories", {}) if y_summary else {}
        if y_cats:
            result["yesterday_top_cat"] = max(y_cats, key=y_cats.get)
        if change > 10: result["trend"] = "上升"
        elif change < -10: result["trend"] = "下降"
        else: result["trend"] = "持平"
    except Exception as e:
        logger.debug(f"昨日对比计算失败: {e}")
    return result


# ── 注意力指数 ────────────────────────────────────────

def _compute_attention_index(activities: list) -> dict:
    result = {
        "fragmentation_index": 0, "focus_efficiency": 0, "deep_work_ratio": 0.0,
        "avg_session_min": 0.0, "longest_streak_min": 0, "switch_frequency": 0.0,
    }
    if not activities:
        return result
    # 确保按时间升序（get_activities 返回 DESC）
    activities = sorted(activities, key=lambda a: a.get("timestamp", ""))
    interval = config.SCREENSHOT_INTERVAL_SEC
    total_records = len(activities)
    sessions = []
    cur_cat = activities[0]["category"]
    cur_count = 1
    for i in range(1, len(activities)):
        if activities[i]["category"] == cur_cat:
            cur_count += 1
        else:
            sessions.append((cur_cat, cur_count))
            cur_cat = activities[i]["category"]
            cur_count = 1
    sessions.append((cur_cat, cur_count))
    total_sessions = len(sessions)
    category_switches = max(total_sessions - 1, 0)
    hour_set = set()
    for act in activities:
        h = _parse_ts_hour(act["timestamp"])
        if 0 <= h <= 23: hour_set.add(h)
    active_hours = max(len(hour_set), 1)
    switch_frequency = round(category_switches / active_hours, 2)
    short_sessions = sum(1 for _, cnt in sessions if cnt * interval < 600)
    short_ratio = short_sessions / total_sessions if total_sessions > 0 else 0
    avg_session_len = sum(cnt * interval for _, cnt in sessions) / total_sessions if total_sessions > 0 else 0
    avg_session_min = round(avg_session_len / 60, 1)
    frag_switch = min(switch_frequency / 5.0, 1.0) * 40
    frag_short = short_ratio * 40
    frag_avg = min(1.0, 30.0 / max(avg_session_min, 1)) * 20
    fragmentation_index = min(100, round(frag_switch + frag_short + frag_avg))
    deep_sessions = sum(1 for _, cnt in sessions if cnt * interval >= _DEEP_WORK_THRESHOLD_MIN * 60)
    focus_efficiency = round(min(100, deep_sessions / max(total_sessions, 1) * 100 * 2))
    deep_records = sum(cnt for _, cnt in sessions if cnt * interval >= _DEEP_WORK_THRESHOLD_MIN * 60)
    deep_work_ratio = round(deep_records / total_records * 100, 1) if total_records > 0 else 0
    longest_cnt = max(cnt for _, cnt in sessions) if sessions else 0
    longest_streak_min = round(longest_cnt * interval / 60)
    result.update({
        "fragmentation_index": fragmentation_index, "focus_efficiency": focus_efficiency,
        "deep_work_ratio": deep_work_ratio, "avg_session_min": avg_session_min,
        "longest_streak_min": longest_streak_min, "switch_frequency": switch_frequency,
    })
    return result


# ── 情绪曲线 ──────────────────────────────────────────

def _compute_emotion_curve(activities: list, patterns: dict) -> dict:
    result = {"hourly_scores": [], "peak_hour": -1, "valley_hour": -1, "overall_trend": "平稳", "energy_pattern": "均匀型"}
    if not activities:
        return result
    hourly_buckets = {}
    for act in activities:
        h = _parse_ts_hour(act["timestamp"])
        if 0 <= h <= 23:
            if h not in hourly_buckets: hourly_buckets[h] = []
            hourly_buckets[h].append(act)
    hourly_scores = []
    for h in sorted(hourly_buckets.keys()):
        acts = hourly_buckets[h]
        n = len(acts)
        focus_count = sum(1 for a in acts if a["category"] in _FOCUS_CATS_DEEP)
        creative_count = sum(1 for a in acts if a["category"] in _CREATIVE_CATS)
        meeting_count = sum(1 for a in acts if a["category"] in _MEETING_CATS_DEEP)
        focus_ratio = focus_count / n if n > 0 else 0
        creative_ratio = creative_count / n if n > 0 else 0
        meeting_ratio = meeting_count / n if n > 0 else 0
        cats = [a["category"] for a in acts]
        switches = sum(1 for i in range(1, len(cats)) if cats[i] != cats[i - 1])
        switch_freq = switches / max(n, 1)
        score = 5.0 + focus_ratio * 3.0 + creative_ratio * 1.5 - switch_freq * 2.0
        if meeting_ratio > 0.5: score -= meeting_ratio * 1.5
        score = max(1, min(10, round(score, 1)))
        dominant_cat = max(set(cats), key=cats.count) if cats else ""
        hourly_scores.append({"hour": h, "score": score, "dominant_category": dominant_cat, "activity_count": n})
    result["hourly_scores"] = hourly_scores
    if hourly_scores:
        best = max(hourly_scores, key=lambda x: x["score"])
        worst = min(hourly_scores, key=lambda x: x["score"])
        result["peak_hour"] = best["hour"]
        result["valley_hour"] = worst["hour"]
    if len(hourly_scores) >= 3:
        first_half_avg = sum(s["score"] for s in hourly_scores[:len(hourly_scores) // 2]) / (len(hourly_scores) // 2)
        second_half_avg = sum(s["score"] for s in hourly_scores[len(hourly_scores) // 2:]) / (len(hourly_scores) - len(hourly_scores) // 2)
        diffs = [hourly_scores[i + 1]["score"] - hourly_scores[i]["score"] for i in range(len(hourly_scores) - 1)]
        avg_abs_diff = sum(abs(d) for d in diffs) / len(diffs) if diffs else 0
        if avg_abs_diff > 1.5: result["overall_trend"] = "波动"
        elif first_half_avg - second_half_avg > 1.0: result["overall_trend"] = "下降"
        elif second_half_avg - first_half_avg > 1.0: result["overall_trend"] = "上升"
        else: result["overall_trend"] = "平稳"
    if hourly_scores:
        morning = [s for s in hourly_scores if 6 <= s["hour"] < 12]
        afternoon = [s for s in hourly_scores if 12 <= s["hour"] < 18]
        evening = [s for s in hourly_scores if s["hour"] >= 18]
        morning_avg = sum(s["score"] for s in morning) / len(morning) if morning else 0
        afternoon_avg = sum(s["score"] for s in afternoon) / len(afternoon) if afternoon else 0
        evening_avg = sum(s["score"] for s in evening) / len(evening) if evening else 0
        avgs = {"晨型": morning_avg, "午后型": afternoon_avg, "夜型": evening_avg}
        best_pattern = max(avgs, key=avgs.get)
        if avgs[best_pattern] > 0 and all(avgs[best_pattern] - v < 0.8 for v in avgs.values() if v > 0):
            result["energy_pattern"] = "均匀型"
        else:
            result["energy_pattern"] = best_pattern
    return result


# ── 技能雷达 ───────────────────────────────────────────

def _compute_skill_radar(activities: list) -> dict:
    result = {"dimensions": {}, "top_skill": "", "growth_areas": []}
    if not activities:
        return result
    interval = config.SCREENSHOT_INTERVAL_SEC
    cat_hours = {}
    for act in activities:
        cat = act["category"]
        cat_hours[cat] = cat_hours.get(cat, 0) + interval
    for cat, sec in cat_hours.items():
        cat_hours[cat] = sec / 3600.0
    skill_map = {
        "编码": ["开发"], "沟通": ["沟通", "会议"], "创作": ["设计", "文档"],
        "分析": ["数据分析"], "运维": ["运维"], "学习": ["学习"],
        "管理": ["管理", "产品"], "测试": ["测试"],
    }
    dimensions = {}
    for skill, cats in skill_map.items():
        dimensions[skill] = round(sum(cat_hours.get(c, 0) for c in cats), 2)
    result["dimensions"] = dimensions
    if dimensions:
        result["top_skill"] = max(dimensions, key=dimensions.get)
        active_vals = [v for v in dimensions.values() if v > 0]
        if active_vals:
            avg_val = sum(active_vals) / len(active_vals)
            result["growth_areas"] = sorted([k for k, v in dimensions.items() if 0 < v < avg_val], key=lambda k: dimensions[k])
        else:
            result["growth_areas"] = list(dimensions.keys())
    return result


# ── 工作流分析 ─────────────────────────────────────────

def _compute_workflow_analysis(activities: list) -> list:
    if not activities:
        return []
    interval = config.SCREENSHOT_INTERVAL_SEC
    sorted_acts = sorted(activities, key=lambda x: x["timestamp"])
    scenes = []
    cur_scene = None
    CONTEXT_GAP_MIN = 15
    for act in sorted_acts:
        cat = act["category"]
        ts_str = act["timestamp"]
        try:
            ts = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        should_new = False
        if cur_scene is None:
            should_new = True
        else:
            gap_min = (ts - cur_scene["last_ts"]).total_seconds() / 60
            if gap_min > CONTEXT_GAP_MIN: should_new = True
            elif cat in _MEETING_CATS_DEEP and cur_scene["last_cat"] not in _MEETING_CATS_DEEP: should_new = True
            elif cat in _FOCUS_CATS_DEEP and cur_scene["last_cat"] in _MEETING_CATS_DEEP: should_new = True
        if should_new:
            if cur_scene is not None:
                scenes.append(_finalize_workflow_scene(cur_scene, interval))
            cur_scene = {"start_ts": ts, "last_ts": ts, "last_cat": cat, "categories": [cat], "apps": [], "summaries": [], "count": 1}
        else:
            cur_scene["last_ts"] = ts
            cur_scene["last_cat"] = cat
            if cat not in cur_scene["categories"]: cur_scene["categories"].append(cat)
            cur_scene["count"] += 1
        app_dn = get_display_name(act["app_name"])
        if app_dn not in cur_scene["apps"]: cur_scene["apps"].append(app_dn)
        summary = _safe_get(act, "summary", "")
        if summary and summary != "未配置AI": cur_scene["summaries"].append(summary)
    if cur_scene is not None:
        scenes.append(_finalize_workflow_scene(cur_scene, interval))
    return scenes


def _finalize_workflow_scene(scene: dict, interval: int) -> dict:
    duration_min = round(scene["count"] * interval / 60, 1)
    start_hm = scene["start_ts"].strftime("%H:%M")
    end_hm = scene["last_ts"].strftime("%H:%M")
    seen = set()
    unique_summaries = []
    for s in scene["summaries"]:
        if s not in seen: seen.add(s); unique_summaries.append(s)
    cats = scene["categories"]
    apps = scene["apps"][:5]
    description = _infer_scene_description(cats, unique_summaries, duration_min)
    return {
        "scene": description[:30], "time_range": f"{start_hm}-{end_hm}",
        "categories": cats, "apps": apps, "duration_min": duration_min, "description": description,
    }


def _infer_scene_description(cats: list, summaries: list, duration_min: float) -> str:
    cat_set = set(cats)
    if "会议" in cat_set and len(cat_set) > 1: return f"会议后推进执行，涵盖{'、'.join(cats[:3])}"
    if "沟通" in cat_set and "开发" in cat_set: return "沟通反馈后编码实现"
    if "沟通" in cat_set and "文档" in cat_set: return "沟通后整理文档归档"
    if cat_set <= {"开发"}: return "深度编码会话" if duration_min >= 60 else "编码开发"
    if cat_set <= {"设计"}: return "设计创作"
    if cat_set <= {"会议", "沟通"}: return "密集沟通协作" if duration_min >= 60 else "沟通协作"
    if cat_set <= {"学习"}: return "专注学习"
    if cat_set <= {"测试"}: return "测试验证"
    if len(cats) >= 4: return "多线程切换，事务繁杂"
    if summaries: return summaries[0][:50]
    return "、".join(cats[:3]) + f"（{duration_min:.0f}分钟）"


# ── 智能时间线采样 ──────────────────────────────────────

def _smart_sample_timeline(timeline_data: list, max_items: int = 40) -> list:
    if len(timeline_data) <= max_items:
        return timeline_data
    head, tail = 5, 5
    mid = max_items - head - tail
    sampled = list(timeline_data[:head])
    seen_cats = set()
    mid_pool = []
    for item in timeline_data[head:-tail]:
        priority = (2 if item.get("detail") else 0) + (1 if item.get("category") not in seen_cats else 0)
        mid_pool.append((priority, item))
        seen_cats.add(item.get("category", ""))
    mid_pool.sort(key=lambda x: -x[0])
    sampled.extend(item for _, item in mid_pool[:mid])
    sampled.extend(timeline_data[-tail:])
    sampled.sort(key=lambda x: x["time"])
    seen_times = set()
    deduped = []
    for item in sampled:
        if item["time"] not in seen_times:
            deduped.append(item)
            seen_times.add(item["time"])
    return deduped[:max_items]


# ── 富数据上下文构建 ──────────────────────────────────

def _build_rich_data_context(target_date, summary_data, app_usage, activities) -> str:
    wd_str = _weekday_str_deep(target_date)
    weather = _get_weather_info(target_date)
    yesterday = _get_yesterday_comparison(target_date)
    attention = _compute_attention_index(activities)
    patterns = _analyze_work_patterns(activities)
    emotion = _compute_emotion_curve(activities, patterns)
    skill = _compute_skill_radar(activities)
    workflows = _compute_workflow_analysis(activities)
    timeline_data = _build_activity_timeline_data(activities)

    total = summary_data.get("total", 0) if summary_data else 0
    first_ts = summary_data.get("first_ts", "") if summary_data else ""
    last_ts = summary_data.get("last_ts", "") if summary_data else ""
    time_span = _natural_time_span(first_ts, last_ts) if first_ts and last_ts else ""
    focus_hours = _estimate_focus_hours(activities, app_usage)
    focus_sessions = _count_focus_sessions(activities)

    lines = []

    # 日期与天气
    lines.append("═══ 日期与天气 ═══")
    lines.append(f"日期：{target_date} {wd_str}")
    lines.append(f"活跃时段：{time_span}")
    if weather:
        parts = []
        if weather.get("temp"): parts.append(f"气温 {weather['temp']}")
        if weather.get("desc"): parts.append(weather["desc"])
        if weather.get("humidity"): parts.append(f"湿度 {weather['humidity']}")
        if weather.get("wind"): parts.append(weather["wind"])
        if parts: lines.append("天气：" + "，".join(parts))
    lines.append("")

    # 昨日对比
    lines.append("═══ 昨日对比 ═══")
    lines.append(f"昨日活动数：{yesterday['yesterday_total']}")
    lines.append(f"变化幅度：{yesterday['change_pct']:+.1f}%")
    lines.append(f"趋势：{yesterday['trend']}")
    if yesterday["yesterday_top_cat"]:
        lines.append(f"昨日主力分类：{yesterday['yesterday_top_cat']}")
    lines.append("")

    # 核心指标
    lines.append("═══ 核心指标 ═══")
    lines.append(f"注意力碎片化指数：{attention['fragmentation_index']}/100（越高越碎片）")
    lines.append(f"专注效率：{attention['focus_efficiency']}/100")
    lines.append(f"深度工作占比：{attention['deep_work_ratio']}%")
    lines.append(f"平均会话时长：{attention['avg_session_min']} 分钟")
    lines.append(f"最长连续同分类：{attention['longest_streak_min']} 分钟")
    lines.append(f"每小时切换次数：{attention['switch_frequency']}")
    lines.append(f"专注时长：{focus_hours}，深度会话 {focus_sessions} 次")
    lines.append("")

    # 注入番茄统计（一行，不超过 100 字符，不影响 prompt 预算）
    pomo_line = _get_pomodoro_summary_line(target_date)
    if pomo_line:
        lines.append(pomo_line)
        lines.append("")

    # 心流与专注
    lines.append("═══ 心流与专注 ═══")
    focus_ses = patterns.get("focus_sessions", [])
    if focus_ses:
        for fs in focus_ses:
            lines.append(f"- {fs['start']} 开始，{fs['category']}，持续 {fs['duration_min']} 分钟")
    lf = patterns.get("longest_focus")
    if lf:
        lines.append(f"最长专注：{lf['category']}，{lf['duration_min']} 分钟")
    deep_count = sum(1 for fs in focus_ses if fs["duration_min"] >= _DEEP_WORK_THRESHOLD_MIN)
    lines.append(f"深度工作（≥{_DEEP_WORK_THRESHOLD_MIN}分钟）次数：{deep_count}")
    lines.append("")

    # 工作场景流
    lines.append("═══ 工作场景流 ═══")
    for wf in workflows:
        lines.append(f"- [{wf['time_range']}] {wf['scene']}（{wf['duration_min']:.0f}分钟）")
        lines.append(f"  分类：{'、'.join(wf['categories'])}，工具：{'、'.join(wf['apps'])}")
        if wf["description"] and wf["description"] != wf["scene"]:
            lines.append(f"  详情：{wf['description']}")
    lines.append("")

    # 叙事时间线
    lines.append("═══ 叙事时间线 ═══")
    sampled_timeline = _smart_sample_timeline(timeline_data, max_items=40)
    for i, item in enumerate(sampled_timeline, 1):
        lines.append(f"{i}. {item['time']} [{item['category']}] {item['app']}")
        if item.get("summary"):
            lines.append(f"   摘要：{item['summary']}")
        if item.get("detail"):
            lines.append(f"   详情：{item['detail'][:150]}")
        if item.get("windows"):
            for w in item["windows"]:
                fg = "前台" if w.get("foreground") else "后台"
                lines.append(f"   窗口 {fg}：{w['app']} — {w.get('desc', '')}")
    lines.append("")

    # 工作强度曲线
    lines.append("═══ 工作强度曲线 ═══")
    curve = patterns.get("intensity_curve", [])
    for c in curve:
        bar = "█" * min(c["count"], 20)
        lines.append(f"- {c['hour']} {bar} ({c['count']}次)")
    lines.append("")

    # 时间间隔与休息
    lines.append("═══ 时间间隔与休息 ═══")
    gaps = patterns.get("time_gaps", [])
    if gaps:
        total_gap_min = sum(g["gap_min"] for g in gaps)
        lines.append(f"共 {len(gaps)} 次离开，累计 {total_gap_min} 分钟")
        for g in gaps[:10]:
            lines.append(f"- {g['from']} → {g['to']}（{g['gap_min']}分钟）")
    else:
        lines.append("全天无长时间中断")
    lines.append("")

    # 情绪曲线
    lines.append("═══ 情绪曲线 ═══")
    for hs in emotion.get("hourly_scores", []):
        bar_len = int(hs["score"])
        bar = "●" * bar_len + "○" * (10 - bar_len)
        lines.append(f"- {hs['hour']:02d}:00 {bar} {hs['score']}/10（{hs['dominant_category']}，{hs['activity_count']}条）")
    lines.append(f"峰值时段：{emotion['peak_hour']:02d}:00")
    lines.append(f"低谷时段：{emotion['valley_hour']:02d}:00")
    lines.append(f"整体趋势：{emotion['overall_trend']}")
    lines.append(f"能量模式：{emotion['energy_pattern']}")
    lines.append("")

    # 技能雷达
    lines.append("═══ 技能雷达 ═══")
    for sk, hrs in skill.get("dimensions", {}).items():
        if hrs > 0:
            bar_len = min(int(hrs * 2), 20)
            lines.append(f"- {sk}：{hrs:.1f}h {'▓' * bar_len}")
    lines.append(f"最强技能：{skill.get('top_skill', '无')}")
    if skill.get("growth_areas"):
        lines.append(f"成长空间：{'、'.join(skill['growth_areas'])}")
    lines.append("")

    # 分类与工具统计
    lines.append("═══ 分类与工具统计 ═══")
    cats = summary_data.get("categories", {}) if summary_data else {}
    total_act_count = sum(cats.values()) if cats else 1  # avoid ZeroDivision
    for cat, cnt in cats.items():
        total_seconds = cnt * config.SCREENSHOT_INTERVAL_SEC
        lines.append(f"- {cat}：{_format_duration(total_seconds)}（{round(cnt / total_act_count * 100)}%）")
    if app_usage:
        lines.append("")
        lines.append("工具使用：")
        for au in app_usage[:10]:
            lines.append(f"- {get_display_name(au['app_name'])}：{_format_duration(au['duration_min'] * 60)}")

    # 按小时合并的时间段摘要（供数据附录直接引用）
    lines.append("")
    lines.append("═══ 按小时时间段摘要（数据附录表格请直接照此输出，不得省略任何一行）═══")
    hour_blocks = {}
    for act in activities:
        try:
            h = int(act["timestamp"][11:13])
        except (ValueError, IndexError):
            continue
        if h not in hour_blocks:
            hour_blocks[h] = {"cats": set(), "apps": set(), "count": 0}
        hour_blocks[h]["cats"].add(act["category"])
        hour_blocks[h]["apps"].add(get_display_name(act["app_name"]))
        hour_blocks[h]["count"] += 1
    # 找出每个小时的起止时间
    hour_ranges = {}
    for act in activities:
        try:
            hm = act["timestamp"][11:16]
            h = int(hm[:2])
        except (ValueError, IndexError):
            continue
        if h not in hour_ranges:
            hour_ranges[h] = {"start": hm, "end": hm}
        else:
            hour_ranges[h]["end"] = hm
    for h in sorted(hour_blocks.keys()):
        blk = hour_blocks[h]
        rng = hour_ranges.get(h, {})
        cat_str = "、".join(sorted(blk["cats"]))
        app_str = "、".join(sorted(blk["apps"]))
        dur_min = blk["count"] * config.SCREENSHOT_INTERVAL_SEC / 60
        start = rng.get("start", f"{h:02d}:00")
        end = rng.get("end", f"{h:02d}:59")
        lines.append(f"| {start}-{end} | {cat_str} | {app_str} | {dur_min:.0f}分钟 |")

    # ── 注入用户画像 + 周级上下文（长记忆，防注入过滤） ──
    try:
        from context_manager import get_user_profile_context, build_weekly_context
        from prompt import _sanitize_user_input
        user_ctx = get_user_profile_context()
        if user_ctx:
            lines.append("")
            lines.append("═══ 用户画像 ═══")
            lines.append(_sanitize_user_input(user_ctx, 1500))
        weekly_ctx = build_weekly_context(7)
        if weekly_ctx and len(weekly_ctx) > 50:
            lines.append("")
            lines.append("═══ 近一周工作上下文 ═══")
            lines.append(_sanitize_user_input(weekly_ctx, 3000))
    except Exception:
        pass

    # ── 注入 DeepInsight 学术框架分析 ──
    try:
        from deep_insight_engine import build_deep_insight_context
        di_ctx = build_deep_insight_context(activities, interval_sec=config.SCREENSHOT_INTERVAL_SEC)
        if di_ctx:
            lines.append("")
            lines.append(di_ctx)
    except Exception as di_err:
        logger.debug(f"DeepInsight context 注入失败(非致命): {di_err}")

    return "\n".join(lines)


# ── 深度洞察主模板 ────────────────────────────────────

def _template_deep(target_date: str, activities, summary_data, app_usage) -> str:
    if not activities:
        lines = [
            f"# {target_date} {_weekday_str_deep(target_date)}",
            "", "今天的世界安静了下来。", "",
            "没有代码的敲击，没有会议的邀约，没有文档的翻阅——",
            "屏幕长久地暗着，像一扇关上的窗。", "",
            "也许你走出了房间，去感受了风和阳光；",
            "也许你只是需要这样一天，什么都不做，什么都想。", "",
            "这没什么不好。休息不是停滞，是潮汐退去时大海的深呼吸。", "",
            "明天，当你再次坐到屏幕前，",
            "那些安静积蓄的力量，会化成比昨天更坚定的敲击。", "",
            "好好休息。世界和代码都会等你。",
        ]
        return "\n".join(lines) + "\n"

    if not config.AI_API_KEY:
        base = _template_standard(target_date, activities, summary_data, app_usage)
        return base.replace(
            f"# {target_date} 工作日报",
            f"# {target_date} 工作日报\n\n> ⚠️ 深度洞察模板需要 AI 支持。未配置 API Key，已使用标准模板生成。\n",
        )

    # 熔断器检查：如果 AI 服务熔断中，降级到标准模板
    try:
        from ai_client import _cb_check
        if not _cb_check():
            logger.warning("AI 熔断器打开，深度洞察降级为标准模板")
            base = _template_standard(target_date, activities, summary_data, app_usage)
            return base.replace(
                f"# {target_date} 工作日报",
                f"# {target_date} 工作日报\n\n> ⚠️ AI 服务暂时不可用，已使用标准模板生成。\n",
            )
    except Exception:
        pass  # 熔断器检查失败不阻塞

    # 速率限制检查
    try:
        from ai_client import _rate_limit_check
        if not _rate_limit_check("text"):
            logger.warning("AI 文本请求速率超限，深度洞察降级为标准模板")
            base = _template_standard(target_date, activities, summary_data, app_usage)
            return base.replace(
                f"# {target_date} 工作日报",
                f"# {target_date} 工作日报\n\n> ⚠️ AI 请求过于频繁，已使用标准模板生成。\n",
            )
    except Exception:
        pass

    max_retries = 2
    for attempt in range(max_retries):
        try:
            rich_context = _build_rich_data_context(target_date, summary_data, app_usage, activities)

            # Token 预算控制：rich_context 截断上限（防止超出模型上下文）
            _RICH_CONTEXT_MAX_CHARS = 12000  # 约 6000 token
            if len(rich_context) > _RICH_CONTEXT_MAX_CHARS:
                rich_context = rich_context[:_RICH_CONTEXT_MAX_CHARS] + "\n\n...(数据已截断，仅包含核心信息)"

            system_prompt = (
                "你是一位世界级的私人日志作者与人生教练。你的文字融合了以下产品的精髓：\n"
                "\n"
                "- Day One：用叙事场景还原真实的一天，有光影、有温度、有呼吸感\n"
                "- Stoic Journal：哲思与反思，从经历中提炼智慧，困境中看见成长\n"
                "- 5-Minute Journal：感恩的视角，在平凡中发现珍贵\n"
                "- Reflectly：用 AI 的共情力理解行为背后的心理，温暖而不说教\n"
                "- Bullet Journal：结构化追踪，让数据为成长服务\n"
                "- Obsidian Daily Notes：知识工作者的日志传统，连接思考与行动\n"
                "\n"
                "你的任务是：根据用户的全天工作活动数据，写一份极其丰富、深度、有温度的个人日报。\n"
                "\n"
                "## 结构要求（灵活而完整）\n"
                "你不必死板地套用固定小节，但必须在行文中**自然覆盖**以下维度：\n"
                "1. 开篇场景——基于数据中第一条活动的真实时间、真实应用、真实窗口标题开场，如'早上8:59，当你打开 TRAE SOLO CN 开始新一天的开发任务时...'，绝对禁止编造天气、编造未发生的场景\n"
                "2. 工作纪实——沿时间线叙事，必须引用具体细节：文件名、工具名、窗口标题、操作内容（从叙事时间线和 ai_detail 提取），不要泛泛而谈\n"
                "3. 心流与专注——引用数据中的注意力碎片化指数、专注效率、深度工作占比、最长专注时间等具体数字，分析深度工作时段、被打断的瞬间\n"
                "4. 情绪与能量——引用情绪曲线中的峰值/低谷时段、能量模式（如'午后型'），结合切换频率推断心理状态\n"
                "5. 技能成长——引用技能雷达中的具体小时数，今日最强技能和成长空间\n"
                "6. 人际与协作——从沟通类活动、会议记录推断协作模式，列举具体沟通对象和工具\n"
                "7. 挑战与突破——从工作场景流中识别任务切换频繁的时段（可能是遇到困难的信号），具体说明\n"
                "8. 反思与感恩——今天的收获、值得感谢的、可以改进的，结合今日对比数据（比昨日多了还是少了）\n"
                "9. 明日展望——带着期待而不是焦虑看明天，结合今天的成长空间给出建议\n"
                "10. 数据附录——用简洁的表格呈现时间分配与工具统计\n"
                "\n"
                "## 写作铁律\n"
                "- 每个维度必须充实展开，不能两句话带过\n"
                "- 从 ai_detail 和窗口数据中提取**具体细节**，让故事有血有肉——如果数据里有'TRAE SOLO CN - 编辑 report.py'，你就要写出'你在 report.py 中埋头编写'，而不能只写'你在开发'\n"
                "- 心理推测要有依据：从切换频率、时间间隔、分类分布推断心理状态\n"
                "- 总字数 2500-4000 字中文\n"
                "- 语气温暖、真诚、像最懂你的朋友——不是教导主任\n"
                "- 用 Markdown 格式，标题层级灵活，但每个板块标题用 ## 或 ###\n"
                "- 数据附录的表格必须完整输出所有行，禁止使用'…'或'...'省略任何行，按小时时间段摘要已为你准备好，直接逐行输出即可\n"
                "- 开篇场景必须基于真实数据（时间、应用、窗口标题），禁止编造天气、编造场景、编造未发生的事\n"
                "- 如果天气数据存在，在开篇或正文中自然提及真实天气（从数据中读取），不要编造天气\n"
                "- 工作纪实部分必须覆盖上午、下午、晚上的主要活动，每个时段至少写3-4句具体描述\n"
                "- 引用数字要有出处：如说'专注效率 72 分'就必须是数据中给出的数字，不能自己编\n"
            )

            from ai_client import _get_client
            client = _get_client()
            response = client.chat.completions.create(
                model=config.AI_TEXT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": (
                        f"以下是 {target_date}（{_weekday_str_deep(target_date)}）的全天活动数据，请据此写一份深度洞察日报：\n\n"
                        f"{rich_context}"
                    )},
                ],
                max_tokens=6000,
                temperature=0.78,
            )
            content = response.choices[0].message.content.strip()
            # 记录熔断器成功
            try:
                from ai_client import _cb_record_success
                _cb_record_success()
            except Exception:
                pass
            _md_fence = _re.match(r"^```(?:markdown|md)?\s*\n(.+?)\n```\s*$", content, _re.DOTALL)
            if _md_fence:
                content = _md_fence.group(1).strip()
            content = _re.sub(r"^```(?:markdown|md)?\s*\n", "", content).rstrip("`").strip()
            aigc_label = "\n\n---\n*本日记由 ChallengeDaily AI 深度分析生成，内容仅供参考*"
            if aigc_label.strip() not in content and "ChallengeDaily AI" not in content:
                content = content.rstrip() + aigc_label
            return content
        except Exception as e:
            logger.error(f"深度洞察日报生成失败 (尝试 {attempt+1}/{max_retries}): {e}", exc_info=True)
            try:
                from ai_client import _cb_record_failure
                _cb_record_failure()
            except Exception:
                pass
            if attempt < max_retries - 1:
                import time as _time
                _time.sleep(1 * (2 ** attempt))  # 1s, 2s 退避
    # 全部重试失败，降级到标准模板
    return _template_standard(target_date, activities, summary_data, app_usage)


# ── 模板5: AI 智能 (ai) ──────────────────────────
# 融合全部活动数据（含 ai_detail、windows_json），生成叙事性日报 + 心理状态推测 + 深度洞察
# 参考：
#   - Day One Journal（叙事式日记）
#   - Stoic Journal（情绪反思）
#   - Reflectly（AI 驱动的日记助手）
#   -Obsidian Daily Notes（知识工作者的日志传统）
#   - 「五分钟日志法」(5-Minute Journal) 的结构化反思

def _analyze_work_patterns(activities: list) -> dict:
    """分析工作模式：时间分布、专注节奏、上下文切换频率、工作强度变化"""
    if not activities:
        return {}

    # 确保按时间升序（get_activities 返回 DESC）
    activities = sorted(activities, key=lambda a: a.get("timestamp", ""))

    interval = config.SCREENSHOT_INTERVAL_SEC
    patterns = {
        "time_gaps": [],           # 时间间隔异常（>5min 无记录 = 休息/离开）
        "category_switches": 0,    # 分类切换次数
        "focus_sessions": [],      # 深度专注会话（同分类持续>=15min）
        "intensity_curve": [],     # 工作强度曲线（每小时活动密度）
        "longest_focus": None,     # 最长专注段
        "interrupted_sessions": 0, # 被打断的专注段（<10min 就切换）
    }

    from datetime import datetime as _dt

    # 分析时间间隔和分类切换
    prev_ts = None
    prev_cat = None
    cur_focus_start = None
    cur_focus_cat = None
    cur_focus_count = 0

    for act in activities:
        ts_str = act["timestamp"]
        cat = act["category"]
        try:
            ts = _dt.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                ts = _dt.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

        # 时间间隔分析
        if prev_ts:
            gap_sec = (ts - prev_ts).total_seconds()
            if gap_sec > interval * 3:  # 超过3个间隔 = 有间断
                patterns["time_gaps"].append({
                    "from": prev_ts.strftime("%H:%M"),
                    "to": ts.strftime("%H:%M"),
                    "gap_min": round(gap_sec / 60),
                })

        # 分类切换分析
        if prev_cat and cat != prev_cat:
            patterns["category_switches"] += 1
            # 检查是否是被打断的短专注
            if cur_focus_count > 0 and cur_focus_count * interval < 600:  # <10min
                patterns["interrupted_sessions"] += 1
            # 保存上一段专注
            if cur_focus_count * interval >= 900:  # >=15min
                patterns["focus_sessions"].append({
                    "category": cur_focus_cat,
                    "start": cur_focus_start.strftime("%H:%M"),
                    "duration_min": round(cur_focus_count * interval / 60),
                })
            cur_focus_start = ts
            cur_focus_cat = cat
            cur_focus_count = 1
        else:
            if cur_focus_start is None:
                cur_focus_start = ts
                cur_focus_cat = cat
            cur_focus_count += 1

        prev_ts = ts
        prev_cat = cat

    # 最后一段
    if cur_focus_count * interval >= 900:
        patterns["focus_sessions"].append({
            "category": cur_focus_cat,
            "start": cur_focus_start.strftime("%H:%M"),
            "duration_min": round(cur_focus_count * interval / 60),
        })

    # 最长专注段
    if patterns["focus_sessions"]:
        patterns["longest_focus"] = max(patterns["focus_sessions"], key=lambda x: x["duration_min"])

    # 工作强度曲线（按小时聚合）
    hour_counts = {}
    for act in activities:
        try:
            h = int(act["timestamp"][11:13])
            hour_counts[h] = hour_counts.get(h, 0) + 1
        except (ValueError, IndexError):
            pass
    for h in sorted(hour_counts.keys()):
        patterns["intensity_curve"].append({
            "hour": f"{h:02d}:00",
            "count": hour_counts[h],
            "level": "high" if hour_counts[h] >= 10 else ("medium" if hour_counts[h] >= 5 else "low"),
        })

    return patterns


def _build_activity_timeline_data(activities: list) -> list[dict]:
    """构建包含 ai_detail 和 windows_json 的完整时间线数据（用于深度分析）"""
    import json as _json
    timeline = []
    for act in activities:
        item = {
            "time": act["timestamp"][11:16] if len(act["timestamp"]) > 16 else act["timestamp"],
            "category": act["category"],
            "app": get_display_name(act["app_name"]),
            "summary": act.get("summary", ""),
            "detail": act.get("ai_detail", ""),
        }
        # 解析 windows_json 获取多窗口信息
        win_json = act.get("windows_json", "[]")
        try:
            windows = _json.loads(win_json) if win_json else []
            if windows:
                item["windows"] = [
                    {
                        "app": w.get("app_name", ""),
                        "title": w.get("window_title", ""),
                        "foreground": w.get("is_foreground", False),
                        "desc": w.get("description", ""),
                    }
                    for w in windows
                ]
        except Exception:
            pass
        timeline.append(item)
    return timeline




# ── 模板5: AI 智能 (ai) ──────────────────────────
# 使用文本模型根据活动数据生成自然语言日报，充分发挥 GLM-4-Flash 等文本模型能力

def _build_ai_report_prompt(target_date: str, activities, summary_data, app_usage) -> str:
    """为文本模型构建日报生成 Prompt"""
    blocks = _group_into_blocks(activities)
    cat_narratives = _build_category_narrative(blocks)

    focus_hours = _estimate_focus_hours(activities, app_usage)
    focus_sessions = _count_focus_sessions(activities)
    total = summary_data.get("total", 0)

    lines = [
        f"请根据以下 {target_date} 的工作活动记录，生成一份专业、自然、适合向上级汇报的工作日报。",
        "要求：",
        "1. 使用 Markdown 格式，包含今日概要、重点工作、时间分配、明日方向。",
        "2. 内容要具体，结合时段和工具，不要泛泛而谈。",
        "3. 语气专业、简洁，避免过度夸张。",
        "4. 如果活动记录为空，直接说明今天暂无工作记录。",
        "",
        "---",
        "",
        f"总活动数：{total}",
        f"估算专注时长：{focus_hours}",
        f"深度工作次数：{focus_sessions}",
        "",
        "分类统计：",
    ]
    for cat, cnt in (summary_data.get("categories") or {}).items():
        lines.append(f"- {cat}: {cnt} 次记录")

    # 注入番茄统计（一行，不超过 100 字符，不影响 _USER_PROMPT_BUDGET）
    pomo_line = _get_pomodoro_summary_line(target_date)
    if pomo_line:
        lines.extend(["", pomo_line])

    lines.extend(["", "主要工作段落："])
    for narr in cat_narratives[:8]:
        lines.append(
            f"- [{narr['category']}] {narr['duration_str']} | 时段：{narr['time_desc']} | "
            f"内容：{narr['summary'] or '使用 ' + narr['apps']} | 工具：{narr['apps']}"
        )

    if app_usage:
        lines.extend(["", "应用使用时长 Top："])
        for au in app_usage[:8]:
            total_sec = au["duration_min"] * 60
            time_str = _format_duration(total_sec)
            display_name = get_display_name(au["app_name"])
            lines.append(f"- {display_name}: {time_str}")

    # AI 教练：注入今日分心热点时段（若某小时分心≥3次则提示）
    try:
        with _db.get_conn() as conn:
            hot_hour = conn.execute(
                "SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS hour, COUNT(*) AS cnt "
                "FROM activities WHERE category='生活' AND date(timestamp)=date('now') "
                "GROUP BY hour ORDER BY cnt DESC LIMIT 1"
            ).fetchone()
            if hot_hour and hot_hour["cnt"] >= 3:
                lines.append("")
                lines.append(
                    f"AI教练：你今天{hot_hour['hour']}点最容易分心（{hot_hour['cnt']}次），"
                    f"建议该时段开严格模式。"
                )
    except Exception:
        pass

    lines.extend(["", "---", "", "请直接输出 Markdown 日报内容，不要包含任何额外说明。"])
    return "\n".join(lines)


def _template_ai(target_date: str, activities, summary_data, app_usage) -> str:
    """使用 AI 文本模型生成日报"""
    if not activities:
        return f"# {target_date} 工作日报\n\n今天暂无工作记录。\n"

    if not config.AI_API_KEY:
        # 未配置 AI 时回退到标准模板，并附加提示
        base = _template_standard(target_date, activities, summary_data, app_usage)
        return base.replace(
            f"# {target_date} 工作日报",
            f"# {target_date} 工作日报\n\n> 未配置 AI API Key，已使用标准模板生成。在设置中配置 Key 后可启用 AI 智能日报。\n"
        )

    # 熔断器检查：如果 AI 服务熔断中，降级到标准模板
    try:
        from ai_client import _cb_check, _rate_limit_check
        if not _cb_check():
            logger.warning("AI 熔断器打开，AI日报降级为标准模板")
            base = _template_standard(target_date, activities, summary_data, app_usage)
            return base.replace(
                f"# {target_date} 工作日报",
                f"# {target_date} 工作日报\n\n> ⚠️ AI 服务暂时不可用，已使用标准模板生成。\n",
            )
        if not _rate_limit_check("text"):
            logger.warning("AI 文本请求速率超限，AI日报降级为标准模板")
            base = _template_standard(target_date, activities, summary_data, app_usage)
            return base.replace(
                f"# {target_date} 工作日报",
                f"# {target_date} 工作日报\n\n> ⚠️ AI 请求过于频繁，已使用标准模板生成。\n",
            )
    except Exception:
        pass  # 熔断器/限流检查失败不阻塞

    prompt = _build_ai_report_prompt(target_date, activities, summary_data, app_usage)

    max_retries = 2
    for attempt in range(max_retries):
        try:
            from ai_client import _get_client, _cb_record_success, _cb_record_failure
            client = _get_client()
            response = client.chat.completions.create(
                model=config.AI_TEXT_MODEL,
                messages=[
                    {"role": "system", "content": "你是一位专业的工作日报撰写助手，擅长根据活动记录提炼要点、组织语言。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1500,
                temperature=0.5,
            )
            content = response.choices[0].message.content.strip()
            # 去除模型可能包裹的 ```markdown ... ``` 代码块，避免前端渲染为代码块原文
            import re as _re
            _md_fence = _re.match(r"^```(?:markdown|md)?\s*\n(.+?)\n```\s*$", content, _re.DOTALL)
            if _md_fence:
                content = _md_fence.group(1).strip()
            # 兼容只有开头 ```markdown 但没有闭合 ``` 的情况
            content = _re.sub(r"^```(?:markdown|md)?\s*\n", "", content).rstrip("`").strip()
            # 确保有 AIGC 标记
            aigc_label = "\n\n---\n*本报告由 ChallengeDaily AI 辅助生成，内容仅供参考*"
            if aigc_label.strip() not in content and "ChallengeDaily AI" not in content:
                content = content.rstrip() + aigc_label
            _cb_record_success()
            return content
        except Exception as e:
            logger.error(f"AI 日报生成失败 (尝试 {attempt+1}/{max_retries}): {e}")
            try:
                from ai_client import _cb_record_failure
                _cb_record_failure()
            except Exception:
                pass
            if attempt < max_retries - 1:
                import time as _time
                _time.sleep(1 * (2 ** attempt))  # 1s, 2s 退避
    # 全部重试失败，回退到标准模板
    fallback = _template_standard(target_date, activities, summary_data, app_usage)
    fallback += "\n\n---\n> ⚠️ AI 日报生成失败，已降级为基础模板。请检查 AI 配置或稍后重试。"
    return fallback


# ── 公共入口 ──────────────────────────────────

_TEMPLATE_MAP = {
    "standard": _template_standard,
    "simple": _template_simple,
    "technical": _template_technical,
    "okr": _template_okr,
    "ai": _template_ai,
    "deep": _template_deep,
}


def generate_daily_report(target_date: str = None, template: str = "standard") -> str:
    """
    生成指定日期的 Markdown 日报，保存到 data/reports/ 和数据库。
    target_date: "YYYY-MM-DD" 格式，默认今天。
    template: "standard" / "simple" / "technical" / "okr" / "ai"
    返回生成的报告内容。
    """
    if not target_date:
        target_date = date.today().isoformat()

    # 数据获取
    activities = get_activities(target_date, target_date)
    summary_data = get_daily_summary(target_date, target_date)
    app_usage = get_app_usage(target_date, target_date)

    # 选择模板
    tmpl_func = _TEMPLATE_MAP.get(template, _template_standard)
    content = tmpl_func(target_date, activities, summary_data, app_usage)

    _save(content, target_date)
    return content


# ── 周报 / 月报 ────────────────────────────────

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
