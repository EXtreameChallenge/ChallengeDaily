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
