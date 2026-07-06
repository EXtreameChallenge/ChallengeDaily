"""
ChallengeDaily Windows 版 — Markdown 日报生成
支持四种报告模板：standard（标准）/ simple（简洁）/ technical（技术）/ okr（OKR）
核心思路：按分类聚合并生成高质量摘要，而非逐条罗列活动日志
"""
import os
from datetime import date, datetime
from collections import OrderedDict
from app_tracker import get_display_name
from db import get_activities, get_daily_summary, get_app_usage, save_report
from config import REPORT_DIR
import config
import logging

logger = logging.getLogger(__name__)


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


def _estimate_focus_hours(activities: list) -> str:
    """根据活动数量粗略估算专注时长"""
    if not activities:
        return "0s"
    total_seconds = len(activities) * config.SCREENSHOT_INTERVAL_SEC
    return _format_duration(total_seconds)


def _count_focus_sessions(activities: list) -> int:
    """统计专注次数（同一分类持续 >= 15min 算一次）"""
    if not activities:
        return 0
    sessions = 0
    current_cat = None
    current_count = 0
    for act in activities:
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
    if aigc_label.strip() not in content and "*AI 辅助生成*" not in content:
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
    focus_hours = _estimate_focus_hours(activities)
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
    total_act_count = sum(summary_data["categories"].values())
    for cat, cnt in summary_data["categories"].items():
        total_seconds = cnt * config.SCREENSHOT_INTERVAL_SEC
        time_str = _format_duration(total_seconds)
        pct = f"{round(cnt / total_act_count * 100)}%" if total_act_count > 0 else "0%"
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
    focus_hours = _estimate_focus_hours(activities)
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
    focus_hours = _estimate_focus_hours(activities)
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
    focus_hours = _estimate_focus_hours(activities)
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
    total_act_count = sum(summary_data["categories"].values())
    for cat, cnt in summary_data["categories"].items():
        total_seconds = cnt * config.SCREENSHOT_INTERVAL_SEC
        time_str = _format_duration(total_seconds)
        pct = f"{round(cnt / total_act_count * 100)}%" if total_act_count > 0 else "0%"
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
# 全面重构：参考顶级日记产品（Day One / Stoic / Reflectly / 5-Minute Journal / Notion / Obsidian）
# 融合全部数据维度：截图分析、时间天气、位置、工作模式、心理状态、项目上下文
# 生成一份真正丰富、深度、有温度的个人日报

def _extract_projects_from_activities(activities: list) -> list[dict]:
    """从活动记录中提取项目/任务上下文"""
    import re as _re
    projects = {}
    for act in activities:
        detail = act.get("ai_detail", "")
        summary = act.get("summary", "")
        window_title = act.get("window_title", "")
        # 从窗口标题和AI分析中提取项目名（常见的项目标识模式）
        text = f"{detail} {summary} {window_title}"
        # 匹配常见项目名模式
        patterns = [
            r'([\w\-]+)\s*项目',
            r'项目[：:]\s*([\w\-]+)',
            r'在\s+([\w\-]+)\s*项目',
            r'([A-Z][a-zA-Z0-9\-]+)\s*(?:系统|平台|应用|工具|模块)',
        ]
        for pat in patterns:
            matches = _re.findall(pat, text)
            for m in matches:
                if len(m) > 2 and not m.lower() in ('这个', '那个', '一个', '当前', '正在'):
                    key = m.lower()
                    if key not in projects:
                        projects[key] = {"name": m, "activities": [], "categories": set(), "total_time": 0}
                    projects[key]["activities"].append(act)
                    projects[key]["categories"].add(act.get("category", ""))
    # 按活动数量排序
    result = sorted(projects.values(), key=lambda x: len(x["activities"]), reverse=True)
    for p in result:
        p["categories"] = list(p["categories"])
        p["count"] = len(p["activities"])
    return result[:5]  # 取前5个项目


def _analyze_emotional_journey(activities: list, patterns: dict) -> dict:
    """分析一天的情绪/心理状态变化曲线"""
    if not activities:
        return {}
    
    interval = config.SCREENSHOT_INTERVAL_SEC
    
    # 基于工作模式推断情绪状态
    emotional_states = []
    
    # 上午时段 (6-12)
    morning_acts = [a for a in activities if 6 <= int(a["timestamp"][11:13]) < 12]
    if morning_acts:
        morning_focus = len([a for a in morning_acts if a["category"] in ("开发", "设计", "文档", "测试")])
        morning_ratio = morning_focus / len(morning_acts) if morning_acts else 0
        if morning_ratio > 0.7:
            emotional_states.append({"period": "上午", "state": "专注投入", "score": 8, "desc": "一早就进入了工作状态，精力集中"})
        elif morning_ratio > 0.4:
            emotional_states.append({"period": "上午", "state": "平稳起步", "score": 6, "desc": "上午节奏适中，逐步进入状态"})
        else:
            emotional_states.append({"period": "上午", "state": "较为分散", "score": 4, "desc": "上午被各种事务打断，难以专注"})
    
    # 下午时段 (12-18)
    afternoon_acts = [a for a in activities if 12 <= int(a["timestamp"][11:13]) < 18]
    if afternoon_acts:
        afternoon_focus = len([a for a in afternoon_acts if a["category"] in ("开发", "设计", "文档", "测试")])
        afternoon_ratio = afternoon_focus / len(afternoon_acts) if afternoon_acts else 0
        switch_count = sum(1 for i in range(1, len(afternoon_acts)) if afternoon_acts[i]["category"] != afternoon_acts[i-1]["category"])
        if switch_count > len(afternoon_acts) * 0.5:
            emotional_states.append({"period": "下午", "state": "略显焦虑", "score": 5, "desc": "下午频繁切换任务，可能感到压力或被打断"})
        elif afternoon_ratio > 0.6:
            emotional_states.append({"period": "下午", "state": "持续专注", "score": 7, "desc": "下午保持了良好的工作状态"})
        else:
            emotional_states.append({"period": "下午", "state": "平稳过渡", "score": 6, "desc": "下午节奏平稳，有张有弛"})
    
    # 晚上时段 (18-24)
    evening_acts = [a for a in activities if 18 <= int(a["timestamp"][11:13]) < 24]
    if evening_acts:
        emotional_states.append({"period": "晚上", "state": "收尾整理", "score": 5, "desc": "晚上在做收尾工作，可能略显疲惫"})
    
    # 计算整体情绪得分
    avg_score = sum(s["score"] for s in emotional_states) / len(emotional_states) if emotional_states else 5
    
    # 推断主导情绪
    if patterns.get("interrupted_sessions", 0) > 3:
        dominant = "忙碌而略显疲惫"
    elif len(patterns.get("focus_sessions", [])) >= 3:
        dominant = "充实而有成就感"
    elif patterns.get("category_switches", 0) > 10:
        dominant = "事务繁杂，需要梳理"
    else:
        dominant = "平稳有序"
    
    return {
        "states": emotional_states,
        "average_score": round(avg_score, 1),
        "dominant_mood": dominant,
        "energy_curve": "高→中→低" if avg_score > 6 else "中→低→中" if avg_score > 4 else "低→中→低",
    }


def _build_work_narrative_blocks(activities: list) -> list[dict]:
    """将活动按时间线构建叙事段落（按工作场景而非分类）"""
    if not activities:
        return []
    
    # 按时间排序
    sorted_acts = sorted(activities, key=lambda x: x["timestamp"])
    
    blocks = []
    current_block = None
    
    for act in sorted_acts:
        cat = act["category"]
        ts = act["timestamp"][11:16] if len(act["timestamp"]) > 16 else act["timestamp"]
        detail = act.get("ai_detail", "")
        summary = act.get("summary", "")
        app = get_display_name(act["app_name"])
        
        # 判断是否应该开启新段落
        should_new_block = False
        if current_block is None:
            should_new_block = True
        elif cat != current_block["category"] and cat not in ("生活",):
            # 分类变化且不是生活类，开启新段落
            should_new_block = True
        elif current_block and (act["timestamp"][:13] != current_block["last_hour"]):
            # 跨小时且内容变化较大
            should_new_block = True
        
        if should_new_block:
            if current_block:
                blocks.append(current_block)
            current_block = {
                "category": cat,
                "start_time": ts,
                "end_time": ts,
                "activities": [],
                "apps": set(),
                "summaries": [],
                "details": [],
                "last_hour": act["timestamp"][:13],
            }
        
        current_block["end_time"] = ts
        current_block["activities"].append(act)
        current_block["apps"].add(app)
        if summary and summary != "未配置AI":
            current_block["summaries"].append(summary)
        if detail:
            current_block["details"].append(detail)
    
    if current_block:
        blocks.append(current_block)
    
    # 为每个段落生成叙事描述
    for block in blocks:
        block["duration_min"] = len(block["activities"]) * config.SCREENSHOT_INTERVAL_SEC / 60
        block["apps_str"] = "、".join(list(block["apps"])[:3])
        # 去重摘要
        seen = set()
        unique_summaries = []
        for s in block["summaries"]:
            if s not in seen:
                seen.add(s)
                unique_summaries.append(s)
        block["summaries"] = unique_summaries
        # 取最有信息量的detail
        block["key_details"] = [d for d in block["details"] if len(d) > 50][:3]
    
    return blocks


def _build_deep_report_prompt_v2(target_date: str, activities, summary_data, app_usage,
                                  patterns: dict, timeline_data: list[dict],
                                  emotional: dict, projects: list[dict],
                                  narrative_blocks: list[dict]) -> str:
    """构建超丰富的深度洞察日报 Prompt — 参考顶级日记产品的写作范式"""
    from datetime import datetime as _dt

    focus_hours = _estimate_focus_hours(activities)
    focus_sessions = _count_focus_sessions(activities)
    total = summary_data.get("total", 0)
    first_ts = summary_data.get("first_ts", "")
    last_ts = summary_data.get("last_ts", "")
    time_span = _natural_time_span(first_ts, last_ts) if first_ts and last_ts else ""

    # 星期几
    try:
        wd = _dt.strptime(target_date, "%Y-%m-%d").weekday()
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday_str = weekdays[wd]
    except Exception:
        weekday_str = ""

    lines = [
        f"# 角色设定",
        f"你是一位极具洞察力的私人生活记录师和职业教练。你的任务是根据用户全天的工作活动数据，写一份**极其丰富、深度、有温度**的个人日报。",
        f"",
        f"## 写作风格参考（必须严格遵守）",
        f"",
        f"参考以下顶级日记/工作日志产品的写作范式：",
        f"",
        f"**1. Day One Journal 风格** — 叙事性、场景感、情感共鸣",
        f"- 用具体场景开头：「早上 9 点，阳光透过窗帘...」",
        f"- 记录感官细节：屏幕上的代码、键盘的敲击声、窗外的天气",
        f"- 表达真实感受：疲惫、兴奋、困惑、成就感",
        f"",
        f"**2. Stoic Journal 风格** — 反思性、哲学深度、自我对话",
        f"- 追问自己：今天什么最重要？我做得怎么样？",
        f"- 从困难中学习：遇到什么挑战？如何克服？",
        f"- 感恩与欣赏：今天有什么值得感激的？",
        f"",
        f"**3. 5-Minute Journal 风格** — 结构化、积极心理学",
        f"- 我感激的三件事...",
        f"- 今天会让它变得精彩的三件事...",
        f"- 每日肯定语...",
        f"",
        f"**4. Notion 工作日志风格** — 项目导向、可执行、可追踪",
        f"- 今天推进了什么项目？",
        f"- 完成了哪些关键任务？",
        f"- 遇到了什么阻碍？",
        f"- 明天计划做什么？",
        f"",
        f"**5. 综合要求**：",
        f"- **字数**：正文至少 1500-2500 字，每个板块都要充实",
        f"- **结构**：10 个以上的丰富板块（见下方格式要求）",
        f"- **深度**：不要只描述行为，要分析动机、反思意义、推测心理状态",
        f"- **温度**：像一位最懂你的老朋友在帮你回顾这一天，有笑有泪有洞察",
        f"- **具体**：从 ai_detail 中提取具体细节，让内容有血有肉",
        f"",
        f"---",
        f"",
        f"## 输出格式（必须包含以下所有板块，每个板块都要充实）",
        f"",
        f"### 1. 今日扉页（100-150字）",
        f"- 日期、星期、天气（如果有数据）、心情基调",
        f"- 用一句诗意的话概括今天",
        f"- 像一本书的扉页，定下今天的基调",
        f"",
        f"### 2. 晨间序曲（200-300字）",
        f"- 早上开始工作时的状态",
        f"- 第一个工作内容是什么？",
        f"- 早上的精力水平如何？",
        f"- 用叙事性语言，有场景感",
        f"",
        f"### 3. 工作主线：项目与任务追踪（400-600字）",
        f"- 今天主要推进了哪些项目/任务？",
        f"- 每个项目：做了什么、进展如何、遇到什么困难、如何解决",
        f"- 从窗口标题和AI分析中提取具体文件名、函数名、页面名",
        f"- 用项目管理的视角分析进度",
        f"",
        f"### 4. 深度工作时刻（300-400字）",
        f"- 描述进入心流状态的时段",
        f"- 当时在做什么？持续了多久？",
        f"- 心流前后的状态对比",
        f"- 什么条件促成了心流？",
        f"",
        f"### 5. 协作与连接（200-300字）",
        f"- 今天与谁/什么工具协作？",
        f"- 沟通了什么内容？",
        f"- 协作效率如何？",
        f"- 从窗口分析中推断沟通对象和话题",
        f"",
        f"### 6. 挑战与突破（200-300字）",
        f"- 今天遇到什么困难或挫折？",
        f"- 如何解决的？",
        f"- 从中学到了什么？",
        f"- 用 Stoic 哲学的视角反思",
        f"",
        f"### 7. 午后时光（200-300字）",
        f"- 下午的工作状态变化",
        f"- 精力曲线：下午是否疲惫？如何调整？",
        f"- 下午茶/休息时间的记录",
        f"- 下午最有成就感的一刻",
        f"",
        f"### 8. 工具与数字足迹（200-300字）",
        f"- 今天主要使用了哪些工具？",
        f"- 每个工具的使用时长和用途",
        f"- 工具切换模式反映的工作风格",
        f"- 数字健康反思：屏幕时间、切换频率",
        f"",
        f"### 9. 情绪心电图（200-300字）",
        f"- 一天的情绪变化曲线",
        f"- 什么时刻最开心/最沮丧/最专注？",
        f"- 情绪变化的原因分析",
        f"- 用心理学视角解读情绪模式",
        f"",
        f"### 10. 感恩与欣赏（100-150字）",
        f"- 今天感谢的三件事",
        f"- 什么让你感到温暖或满足？",
        f"- 用 5-Minute Journal 的风格",
        f"",
        f"### 11. 洞察与反思（300-400字）",
        f"- 今天最大的收获是什么？",
        f"- 时间分配是否合理？",
        f"- 工作效率的自我评估",
        f"- 值得保持的好习惯",
        f"- 需要改进的地方",
        f"- 用教练的视角给出建议",
        f"",
        f"### 12. 明日展望（150-200字）",
        f"- 明天最想完成的三件事",
        f"- 今天的未完成项如何延续？",
        f"- 对明天的期待",
        f"- 用积极的语气结束",
        f"",
        f"### 13. 数据附录（表格形式）",
        f"- 时间分配表格",
        f"- 应用使用时长表格",
        f"- 专注会话统计",
        f"",
        f"---",
        f"",
        f"## 数据输入",
        f"",
        f"### 基础信息",
        f"- 日期：{target_date} {weekday_str}",
        f"- 活跃时段：{time_span}",
        f"- 总活动记录数：{total}",
        f"- 估算专注时长：{focus_hours}",
        f"- 深度工作会话数：{focus_sessions}",
        f"- 分类切换次数：{patterns.get('category_switches', 0)}",
        f"- 被打断的短专注段数：{patterns.get('interrupted_sessions', 0)}",
        f"",
    ]

    # 情绪分析数据
    if emotional:
        lines.append("### 情绪分析")
        lines.append(f"- 整体情绪得分：{emotional.get('average_score', 5)}/10")
        lines.append(f"- 主导情绪：{emotional.get('dominant_mood', '平稳')}")
        lines.append(f"- 能量曲线：{emotional.get('energy_curve', '未知')}")
        for s in emotional.get("states", []):
            lines.append(f"- {s['period']}：{s['state']}（{s['score']}/10）— {s['desc']}")
        lines.append("")

    # 项目追踪
    if projects:
        lines.append("### 项目追踪")
        for p in projects:
            lines.append(f"- **{p['name']}**：{p['count']} 条记录，涉及 {', '.join(p['categories'])}")
        lines.append("")

    # 叙事段落
    if narrative_blocks:
        lines.append("### 工作叙事段落（按时间线）")
        for i, block in enumerate(narrative_blocks[:12], 1):
            lines.append(f"**段落 {i}** [{block['category']}] {block['start_time']} - {block['end_time']}（{block['duration_min']:.0f}分钟）")
            lines.append(f"- 工具：{block['apps_str']}")
            if block['summaries']:
                lines.append(f"- 工作内容：{'；'.join(block['summaries'][:3])}")
            if block['key_details']:
                for d in block['key_details'][:2]:
                    lines.append(f"- 细节：{d[:100]}...")
            lines.append("")

    # 时间间隔
    gaps = patterns.get("time_gaps", [])
    if gaps:
        lines.append("### 时间间隔（休息/离开）")
        for g in gaps[:8]:
            lines.append(f"- {g['from']} → {g['to']}（间隔 {g['gap_min']} 分钟）")
        lines.append("")

    # 专注会话
    focus_ses = patterns.get("focus_sessions", [])
    if focus_ses:
        lines.append("### 深度专注会话")
        for fs in focus_ses:
            lines.append(f"- {fs['start']} 开始，{fs['category']}，持续 {fs['duration_min']} 分钟")
        lf = patterns.get("longest_focus")
        if lf:
            lines.append(f"- 最长专注：{lf['category']} {lf['duration_min']} 分钟")
        lines.append("")

    # 工作强度曲线
    curve = patterns.get("intensity_curve", [])
    if curve:
        lines.append("### 工作强度曲线")
        for c in curve:
            bar = "█" * min(c["count"], 20)
            lines.append(f"- {c['hour']} {bar} ({c['count']} 次)")
        lines.append("")

    # 分类统计
    lines.append("### 分类统计")
    for cat, cnt in (summary_data.get("categories") or {}).items():
        lines.append(f"- {cat}: {cnt} 次记录")
    lines.append("")

    # 完整活动时间线（精选）
    lines.append("### 精选活动时间线（含 AI 详细分析）")
    lines.append("以下是从全天记录中精选的关键时刻，每条包含 AI 的详细分析：")
    lines.append("")
    for i, item in enumerate(timeline_data[:40], 1):
        lines.append(f"**{i}. {item['time']}** [{item['category']}]")
        lines.append(f"- 应用：{item['app']}")
        lines.append(f"- 摘要：{item['summary']}")
        if item.get("detail"):
            lines.append(f"- 详细分析：{item['detail']}")
        if item.get("windows"):
            for w in item["windows"]:
                fg = "前台" if w.get("foreground") else "后台"
                lines.append(f"  - {w['app']} [{fg}]：{w.get('desc', '')}")
        lines.append("")

    # 应用使用时长
    if app_usage:
        lines.append("### 应用使用时长")
        for au in app_usage[:10]:
            total_sec = au["duration_min"] * 60
            time_str = _format_duration(total_sec)
            display_name = get_display_name(au["app_name"])
            lines.append(f"- {display_name}: {time_str}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 重要提示",
        "1. **字数要求**：正文部分至少 1500-2500 字，每个板块都要充分展开，不要简略",
        "2. **叙事优先**：用讲故事的方式写，不是列清单。有场景、有对话、有心理活动",
        "3. **深度分析**：不要只说做了什么，要说为什么、怎么做、感受如何、学到了什么",
        "4. **具体细节**：从 ai_detail 中提取具体的文件名、函数名、页面内容、错误信息",
        "5. **心理推测**：根据工作节奏、切换频率、时间间隔，推测用户的心理状态变化",
        "6. **温暖真诚**：像一位最懂你的朋友在帮你写回忆录，有笑有泪有洞察",
        "7. **结构完整**：必须包含所有 13 个板块，不能省略",
        "",
        "请直接输出 Markdown 内容，不要包含任何额外说明。",
    ])
    return "\n".join(lines)


def _template_deep(target_date: str, activities, summary_data, app_usage) -> str:
    """深度洞察日报 v2：全面重构，13个丰富板块，参考顶级日记产品"""
    if not activities:
        return f"# {target_date} 日记\n\n今天没有工作记录，也许是一个休息日。\n\n好好休息，也是一种充电。明天见。\n"

    if not config.AI_API_KEY:
        base = _template_standard(target_date, activities, summary_data, app_usage)
        return base.replace(
            f"# {target_date} 工作日报",
            f"# {target_date} 工作日报\n\n> ⚠️ 深度洞察模板需要 AI 支持。未配置 API Key，已使用标准模板生成。\n"
        )

    # 全面数据分析
    patterns = _analyze_work_patterns(activities)
    timeline_data = _build_activity_timeline_data(activities)
    emotional = _analyze_emotional_journey(activities, patterns)
    projects = _extract_projects_from_activities(activities)
    narrative_blocks = _build_work_narrative_blocks(activities)

    # 智能采样：如果记录太多，精选关键记录
    MAX_ITEMS = 50
    if len(timeline_data) > MAX_ITEMS:
        # 保留：首末各5条 + 每个项目的关键记录 + 情绪变化点 + 高强度时段
        sampled = timeline_data[:5]
        seen = set()
        for item in timeline_data[5:-5]:
            key = f"{item['category']}_{item['time'][:2]}"
            if key not in seen or len(sampled) < MAX_ITEMS - 5:
                if item.get("detail") and len(item["detail"]) > 50:
                    sampled.append(item)
                    seen.add(key)
        sampled.extend(timeline_data[-5:])
        timeline_data = sampled[:MAX_ITEMS]

    prompt = _build_deep_report_prompt_v2(
        target_date, activities, summary_data, app_usage,
        patterns, timeline_data, emotional, projects, narrative_blocks
    )

    try:
        from openai import OpenAI
        import httpx
        client = OpenAI(
            api_key=config.AI_API_KEY,
            base_url=config.AI_BASE_URL,
            timeout=httpx.Timeout(180.0, connect=10.0),  # 3分钟，更长的内容需要更多时间
        )
        response = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": (
                    "你是一位极具洞察力的私人生活记录师和职业教练。"
                    "你擅长将碎片化的工作数据还原成完整、丰富、有温度的一天。"
                    "你的文字既有文学性又有洞察力，像一位最懂用户的老朋友。"
                    "你参考 Day One、Stoic Journal、5-Minute Journal 等顶级日记产品的写作风格。"
                    "你写的内容要极其丰富、深度、具体，每个板块都要充分展开。"
                )},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,  # 更多字数，支持 2500+ 字的正文
            temperature=0.75,  # 稍高温度增加创意和叙事性
        )
        content = response.choices[0].message.content.strip()
        # 去除可能的代码块包裹
        import re as _re
        _md_fence = _re.match(r"^```(?:markdown|md)?\s*\n(.+?)\n```\s*$", content, _re.DOTALL)
        if _md_fence:
            content = _md_fence.group(1).strip()
        content = _re.sub(r"^```(?:markdown|md)?\s*\n", "", content).rstrip("`").strip()
        # AIGC 标记
        aigc_label = "\n\n---\n*本日记由 ChallengeDaily AI 深度分析生成，内容仅供参考*"
        if aigc_label.strip() not in content and "*AI 辅助生成*" not in content:
            content = content.rstrip() + aigc_label
        return content
    except Exception as e:
        logger.error(f"深度洞察日报生成失败: {e}")
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


def _build_deep_report_prompt(target_date: str, activities, summary_data, app_usage,
                               patterns: dict, timeline_data: list[dict]) -> str:
    """构建深度洞察日报的 AI Prompt — 充分利用 ai_detail、窗口分析、工作模式等全量数据"""
    from datetime import datetime as _dt

    focus_hours = _estimate_focus_hours(activities)
    focus_sessions = _count_focus_sessions(activities)
    total = summary_data.get("total", 0)
    first_ts = summary_data.get("first_ts", "")
    last_ts = summary_data.get("last_ts", "")
    time_span = _natural_time_span(first_ts, last_ts) if first_ts and last_ts else ""

    # 星期几
    try:
        wd = _dt.strptime(target_date, "%Y-%m-%d").weekday()
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday_str = weekdays[wd]
    except Exception:
        weekday_str = ""

    lines = [
        f"你是用户的私人 AI 日记助手。请根据以下 {target_date}（{weekday_str}）的全天工作活动记录，",
        "写一份有温度、有洞察的个人日记式日报。",
        "",
        "## 写作要求（极其重要，必须严格遵守）",
        "1. **叙事性写作**：像写日记一样，用自然流畅的语言把一天串联起来，而不是列清单。",
        "   - 用时间线叙事：「早上 9 点开始...」「到了下午...」「临近下班时...」",
        "   - 把同类工作合并描述，不要逐条罗列活动记录",
        "   - 每段要有起承转合，不是干巴巴的陈述",
        "2. **深度分析**：不要只描述做了什么，要分析为什么这样做、解决了什么问题、取得了什么进展",
        "   - 从 ai_detail 字段中提取具体细节，让内容有血有肉",
        "   - 从 windows 分析中推断用户的多任务处理模式",
        "3. **心理状态推测**：根据工作节奏、切换频率、时间间隔，推测用户一天的心理状态：",
        "   - 上午是否精力充沛？下午是否疲惫？",
        "   - 频繁切换是否暗示焦虑或被打断？",
        "   - 长时间专注是否说明进入了心流？",
        "   - 时间间隔（gap）可能是在休息、上厕所、走动、思考",
        "4. **洞察与反思**：在日记末尾提供 2-3 条洞察，例如：",
        "   - 工作效率的高低及其原因",
        "   - 时间分配是否合理",
        "   - 值得保持的好习惯或需要改进的地方",
        "5. **格式**：使用 Markdown，结构为：",
        "   - # 标题（含日期和星期）",
        "   - 开头一段 50-100 字的「今日概览」，像日记开头一样定下基调",
        "   - ## 一天回顾（叙事正文，800-1200 字，可分子标题）",
        "   - ## 心理画像（100-200 字，分析一天的心理状态变化）",
        "   - ## 洞察与反思（2-3 条具体洞察）",
        "   - ## 时间分配（表格形式）",
        "6. **语言风格**：温暖、真诚、像在和自己对话。避免公文化的套话，避免「进行了」「完成了」等机械用语。",
        "7. 如果活动记录很少或为空，也要写一段简短的日记，说明今天可能休息或外出。",
        "",
        "---",
        "",
        f"## 基础数据",
        f"- 日期：{target_date} {weekday_str}",
        f"- 活跃时段：{time_span}",
        f"- 总活动记录数：{total}",
        f"- 估算专注时长：{focus_hours}",
        f"- 深度工作会话数：{focus_sessions}",
        f"- 分类切换次数：{patterns.get('category_switches', 0)}",
        f"- 被打断的短专注段数：{patterns.get('interrupted_sessions', 0)}",
        "",
    ]

    # 时间间隔（休息/离开）
    gaps = patterns.get("time_gaps", [])
    if gaps:
        lines.append("## 时间间隔（可能休息/离开/处理私事）")
        for g in gaps[:10]:
            lines.append(f"- {g['from']} → {g['to']}（间隔 {g['gap_min']} 分钟）")
        lines.append("")

    # 专注会话
    focus_ses = patterns.get("focus_sessions", [])
    if focus_ses:
        lines.append("## 深度专注会话（同分类持续≥15分钟）")
        for fs in focus_ses:
            lines.append(f"- {fs['start']} 开始，{fs['category']}，持续 {fs['duration_min']} 分钟")
        lf = patterns.get("longest_focus")
        if lf:
            lines.append(f"- 最长一次专注：{lf['category']}，{lf['duration_min']} 分钟")
        lines.append("")

    # 工作强度曲线
    curve = patterns.get("intensity_curve", [])
    if curve:
        lines.append("## 工作强度曲线（按小时）")
        for c in curve:
            bar = "█" * min(c["count"], 30)
            lines.append(f"- {c['hour']} [{c['level']}] {bar} ({c['count']} 次记录)")
        lines.append("")

    # 分类统计
    lines.append("## 分类统计")
    for cat, cnt in (summary_data.get("categories") or {}).items():
        lines.append(f"- {cat}: {cnt} 次记录")
    lines.append("")

    # 完整活动时间线（含 ai_detail — 这是核心数据！）
    lines.append("## 完整活动时间线（含 AI 详细分析）")
    lines.append("以下每条记录包含：时间、分类、应用、一句话摘要、AI 详细分析（120-180字）、窗口信息")
    lines.append("")
    for i, item in enumerate(timeline_data, 1):
        lines.append(f"### 记录 {i} — {item['time']} [{item['category']}]")
        lines.append(f"- 应用：{item['app']}")
        lines.append(f"- 摘要：{item['summary']}")
        if item.get("detail"):
            lines.append(f"- AI 详细分析：{item['detail']}")
        if item.get("windows"):
            for w in item["windows"]:
                fg = "[前台]" if w.get("foreground") else "[后台]"
                lines.append(f"  - 窗口：{w['app']} {fg} — {w.get('desc', '')}")
        lines.append("")

    # 应用使用时长
    if app_usage:
        lines.append("## 应用使用时长")
        for au in app_usage[:10]:
            total_sec = au["duration_min"] * 60
            time_str = _format_duration(total_sec)
            display_name = get_display_name(au["app_name"])
            lines.append(f"- {display_name}: {time_str}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "请直接输出 Markdown 日记内容，不要包含任何额外说明或解释。",
        "记住：这是一份个人日记，不是工作汇报。要有温度、有洞察、有自我对话。",
    ])
    return "\n".join(lines)


def _template_deep(target_date: str, activities, summary_data, app_usage) -> str:
    """深度洞察日报：融合全量数据，生成叙事性日记 + 心理推测 + 洞察反思"""
    if not activities:
        return f"# {target_date} 日记\n\n今天没有工作记录，也许是一个休息日。\n\n好好休息，也是一种充电。明天见。\n"

    if not config.AI_API_KEY:
        # 未配置 AI 时回退到标准模板
        base = _template_standard(target_date, activities, summary_data, app_usage)
        return base.replace(
            f"# {target_date} 工作日报",
            f"# {target_date} 工作日报\n\n> ⚠️ 深度洞察模板需要 AI 支持。未配置 API Key，已使用标准模板生成。\n"
        )

    # 分析工作模式
    patterns = _analyze_work_patterns(activities)
    # 构建完整时间线数据（含 ai_detail）
    timeline_data = _build_activity_timeline_data(activities)

    # 分批处理：如果活动记录太多，取关键记录（首末 + 各分类代表 + 高强度时段）
    MAX_TIMELINE_ITEMS = 60  # 控制 prompt 长度
    if len(timeline_data) > MAX_TIMELINE_ITEMS:
        # 智能采样：保留首末记录、每个分类的前2条、高强度时段记录
        sampled = []
        seen_cats = set()
        for i, item in enumerate(timeline_data):
            if i < 5 or i >= len(timeline_data) - 5:  # 首末各5条
                sampled.append(item)
            elif item["category"] not in seen_cats or len(sampled) < MAX_TIMELINE_ITEMS // 2:
                if item.get("detail"):  # 优先保留有详细分析的
                    sampled.append(item)
                    seen_cats.add(item["category"])
        timeline_data = sampled[:MAX_TIMELINE_ITEMS]

    prompt = _build_deep_report_prompt(target_date, activities, summary_data, app_usage,
                                        patterns, timeline_data)

    try:
        from openai import OpenAI
        import httpx
        client = OpenAI(
            api_key=config.AI_API_KEY,
            base_url=config.AI_BASE_URL,
            timeout=httpx.Timeout(120.0, connect=10.0),  # 深度分析需要更长时间
        )
        response = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": (
                    "你是一位温暖、睿智的私人 AI 日记助手。"
                    "你擅长从碎片化的工作活动记录中，还原一个人完整的一天，"
                    "用叙事性的语言写出有温度的日记，同时提供深度的心理洞察和反思。"
                    "你的文字应该像一位懂你的老朋友在帮你回顾这一天。"
                )},
                {"role": "user", "content": prompt},
            ],
            max_tokens=3000,  # 深度日报需要更多字数
            temperature=0.7,  # 稍高温度增加叙事性
        )
        content = response.choices[0].message.content.strip()
        # 去除可能的代码块包裹
        import re as _re
        _md_fence = _re.match(r"^```(?:markdown|md)?\s*\n(.+?)\n```\s*$", content, _re.DOTALL)
        if _md_fence:
            content = _md_fence.group(1).strip()
        content = _re.sub(r"^```(?:markdown|md)?\s*\n", "", content).rstrip("`").strip()
        # AIGC 标记
        aigc_label = "\n\n---\n*本日记由 ChallengeDaily AI 深度分析生成，内容仅供参考*"
        if aigc_label.strip() not in content and "*AI 辅助生成*" not in content:
            content = content.rstrip() + aigc_label
        return content
    except Exception as e:
        logger.error(f"深度洞察日报生成失败: {e}")
        return _template_standard(target_date, activities, summary_data, app_usage)


# ── 模板5: AI 智能 (ai) ──────────────────────────
# 使用文本模型根据活动数据生成自然语言日报，充分发挥 GLM-4-Flash 等文本模型能力

def _build_ai_report_prompt(target_date: str, activities, summary_data, app_usage) -> str:
    """为文本模型构建日报生成 Prompt"""
    blocks = _group_into_blocks(activities)
    cat_narratives = _build_category_narrative(blocks)

    focus_hours = _estimate_focus_hours(activities)
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

    prompt = _build_ai_report_prompt(target_date, activities, summary_data, app_usage)

    try:
        from openai import OpenAI
        import httpx
        client = OpenAI(
            api_key=config.AI_API_KEY,
            base_url=config.AI_BASE_URL,
            timeout=httpx.Timeout(60.0, connect=10.0),
        )
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
        if aigc_label.strip() not in content and "*AI 辅助生成*" not in content:
            content = content.rstrip() + aigc_label
        return content
    except Exception as e:
        logger.error(f"AI 日报生成失败: {e}")
        # 回退到标准模板
        return _template_standard(target_date, activities, summary_data, app_usage)


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
    end_date = start_date
    from datetime import timedelta
    sd = datetime.strptime(start_date, "%Y-%m-%d").date()
    week_start = (sd - timedelta(days=sd.weekday())).isoformat()  # 本周一
    # 如果 start_date 是周末，week_start 取上周一
    start_date = week_start

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
    focus_hours = _estimate_focus_hours(activities)
    focus_sessions = _count_focus_sessions(activities)
    total_act_count = sum(summary_data["categories"].values())

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
        pct = f"{round(cnt / total_act_count * 100)}%" if total_act_count > 0 else "0%"
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
    focus_hours = _estimate_focus_hours(activities)
    focus_sessions = _count_focus_sessions(activities)
    total_act_count = sum(summary_data["categories"].values())

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
        pct = f"{round(cnt / total_act_count * 100)}%" if total_act_count > 0 else "0%"
        lines.append(f"| {cat} | {time_str} | {pct} |")
    lines.append("")

    content = "\n".join(lines)
    report_path = REPORT_DIR / f"reportmonthly_{year_month}.md"
    report_path.write_text(content, encoding="utf-8")
    # 同步存入数据库
    save_report(f"monthly_{year_month}", content)
    return content
