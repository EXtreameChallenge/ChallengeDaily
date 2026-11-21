"""六种日报模板层（轮11 从 report.py 拆出）。"""
from __future__ import annotations

import logging
import re as _re

import config
import db as _db
from app_tracker import get_display_name

from .aggregation import (
    _count_focus_sessions,
    _estimate_focus_hours,
    _format_duration,
    _get_pomodoro_summary_line,
    _group_into_blocks,
    _build_category_narrative,
    _natural_time_span,
    _natural_overview,
    _weekday_str_deep,
    _build_rich_data_context,
)

logger = logging.getLogger(__name__)

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

    # 注入幕布笔记作为额外上下文（失败不影响生成）
    try:
        from mubu_sync import build_mubu_context_for_ai
        mubu_ctx = build_mubu_context_for_ai(days=7, limit=20)
        if mubu_ctx:
            lines.extend(["", mubu_ctx])
    except Exception as me:
        logger.debug(f"幕布上下文注入失败(非致命): {me}")

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
