"""周报/月报 AI 深度增强层（轮11 从 report.py 拆出）。"""
from __future__ import annotations

import logging

import config

logger = logging.getLogger(__name__)

def _generate_ai_deep_analysis(period_type: str, period_label: str,
                                 summary_text: str, categories_data: dict) -> str:
    """AI 深度分析：趋势检测 + 模式识别 + 对比基准

    period_type: "weekly" | "monthly"
    period_label: 如 "2026-W28" 或 "2026-07"
    summary_text: 已生成的模板报告内容摘要
    categories_data: {"开发": 1200, "会议": 300, ...} 分钟数据
    """
    # 构建分析上下文
    total_min = sum(categories_data.values())
    if total_min == 0:
        return ""

    # 行业基准数据（程序员/知识工作者）
    BENCHMARKS = {
        "deep_work_avg": 3.2 * 60,  # 程序员日均深度工作 3.2 小时
        "meeting_ratio_max": 0.25,   # 会议时间占比不超过 25%
        "distraction_ratio_max": 0.15,  # 摸鱼占比不超过 15%
    }

    deep_cats = ["开发", "测试", "设计", "文档", "数据分析"]
    deep_min = sum(categories_data.get(c, 0) for c in deep_cats)
    meeting_min = categories_data.get("会议", 0) + categories_data.get("沟通", 0)
    distraction_min = categories_data.get("生活", 0)

    days = 7 if period_type == "weekly" else 30
    avg_daily_deep = deep_min / days
    meeting_ratio = meeting_min / total_min if total_min else 0
    distraction_ratio = distraction_min / total_min if total_min else 0

    # 构建分析提示
    cat_summary = "、".join(f"{k}:{v:.0f}min" for k, v in sorted(categories_data.items(), key=lambda x: -x[1])[:6])

    prompt = (
        f"你是 ChallengeDaily 的 AI 行为分析师。请基于以下{period_label}的真实数据，生成一段深度分析报告。\n\n"
        f"## 数据概览\n"
        f"- 周期：{period_label}（{days}天）\n"
        f"- 总活跃时长：{total_min:.0f} 分钟（{total_min/60:.1f} 小时）\n"
        f"- 日均活跃：{total_min/days:.0f} 分钟\n"
        f"- 深度工作（开发/测试/设计/文档/数据分析）：{deep_min:.0f} 分钟，日均 {avg_daily_deep:.0f} 分钟\n"
        f"- 会议沟通：{meeting_min:.0f} 分钟（占比 {meeting_ratio*100:.0f}%）\n"
        f"- 生活摸鱼：{distraction_min:.0f} 分钟（占比 {distraction_ratio*100:.0f}%）\n"
        f"- 分类明细：{cat_summary}\n\n"
        f"## 行业基准（程序员/知识工作者）\n"
        f"- 日均深度工作：{BENCHMARKS['deep_work_avg']:.0f} 分钟\n"
        f"- 会议占比警戒线：{BENCHMARKS['meeting_ratio_max']*100:.0f}%\n"
        f"- 摸鱼占比警戒线：{BENCHMARKS['distraction_ratio_max']*100:.0f}%\n\n"
        f"## 分析要求\n"
        f"1. **趋势检测**：对比行业基准，指出用户处于什么水平（超过/低于/接近基准）\n"
        f"2. **模式识别**：从分类占比中识别用户的工作模式特征（如'会议密集型'、'深度专注型'、'多面手型'）\n"
        f"3. **可执行建议**：给出 2-3 条具体、可执行的建议，不要空泛\n"
        f"4. 语气：专业但有温度，像一个关心用户成长的导师\n"
        f"5. 总字数控制在 300 字以内\n"
    )

    # 尝试调用 AI
    if not config.AI_API_KEY:
        return _fallback_analysis(period_type, avg_daily_deep, meeting_ratio, distraction_ratio, BENCHMARKS)

    try:
        from ai_client import _cb_check, _rate_limit_check, _get_client, _cb_record_success, _cb_record_failure
        if not _cb_check():
            return _fallback_analysis(period_type, avg_daily_deep, meeting_ratio, distraction_ratio, BENCHMARKS)
        if not _rate_limit_check("text"):
            return _fallback_analysis(period_type, avg_daily_deep, meeting_ratio, distraction_ratio, BENCHMARKS)

        client = _get_client()
        response = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": "你是 ChallengeDaily AI 行为分析师，擅长从时间追踪数据中发现模式并给出可执行建议。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
            temperature=0.4,
        )
        text = response.choices[0].message.content.strip()
        _cb_record_success()
        return f"\n\n## AI 深度分析\n\n{text}\n"
    except Exception as e:
        logger.error(f"AI 深度分析失败: {e}")
        try:
            from ai_client import _cb_record_failure
            _cb_record_failure()
        except Exception:
            pass
        return _fallback_analysis(period_type, avg_daily_deep, meeting_ratio, distraction_ratio, BENCHMARKS)


def _fallback_analysis(period_type: str, avg_daily_deep: float,
                        meeting_ratio: float, distraction_ratio: float, benchmarks: dict) -> str:
    """AI 不可用时的规则引擎兜底分析"""
    lines = ["\n\n## AI 深度分析\n"]
    deep_benchmark = benchmarks["deep_work_avg"]
    deep_status = "超过行业基准" if avg_daily_deep > deep_benchmark else "低于行业基准" if avg_daily_deep < deep_benchmark * 0.7 else "接近行业基准"

    lines.append(f"**深度工作**：日均 {avg_daily_deep:.0f} 分钟，{deep_status}（{deep_benchmark:.0f}min）。\n")

    if meeting_ratio > benchmarks["meeting_ratio_max"]:
        lines.append(f"**会议占比偏高**：{meeting_ratio*100:.0f}%，建议审视会议必要性，超过 {benchmarks['meeting_ratio_max']*100:.0f}% 会挤压深度工作时间。\n")
    else:
        lines.append(f"**会议占比健康**：{meeting_ratio*100:.0f}%，在合理范围内。\n")

    if distraction_ratio > benchmarks["distraction_ratio_max"]:
        lines.append(f"**摸鱼占比偏高**：{distraction_ratio*100:.0f}%，建议设置番茄钟限制分心时段。\n")
    else:
        lines.append(f"**摸鱼控制良好**：{distraction_ratio*100:.0f}%，专注力不错。\n")

    lines.append("\n**建议**：")
    if avg_daily_deep < deep_benchmark * 0.7:
        lines.append("- 尝试每天安排 2 个不受打扰的深度工作时段（上午 9-11 点、下午 14-16 点）")
    if meeting_ratio > benchmarks["meeting_ratio_max"]:
        lines.append("- 将部分会议转为异步沟通（文档/评论），保留同步会议给真正需要讨论的话题")
    if distraction_ratio > benchmarks["distraction_ratio_max"]:
        lines.append("- 启用专注模式屏蔽干扰应用，或设置'摸鱼预算'（每天不超过 X 分钟）")
    if not (avg_daily_deep < deep_benchmark * 0.7 or meeting_ratio > benchmarks["meeting_ratio_max"]
            or distraction_ratio > benchmarks["distraction_ratio_max"]):
        lines.append("- 保持当前节奏！可尝试挑战更高的深度工作目标，或引入学习时段提升技能")

    return "\n".join(lines) + "\n"


def enhance_report_with_ai_analysis(content: str, period_type: str,
                                     period_label: str, categories_data: dict) -> str:
    """在已生成的报告末尾追加 AI 深度分析段落"""
    try:
        analysis = _generate_ai_deep_analysis(period_type, period_label, content, categories_data)
        return content + analysis
    except Exception as e:
        logger.error(f"增强报告AI分析失败: {e}")
        return content
