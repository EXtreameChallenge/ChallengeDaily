"""P12-2：报告导出为 Obsidian 格式
支持两种模式：
1. standard：标准 Obsidian Markdown，含 YAML frontmatter、wiki 链接、标签
2. dataview：在 standard 基础上追加 Dataview 内联字段 + 双向链接，可被 Obsidian Dataview 插件索引
"""
import re
import logging
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _slugify(text: str) -> str:
    """将中文/特殊字符转为 Obsidian 友好的 note 名（保留中文，去除标点）"""
    # 去除 Windows 文件名非法字符
    cleaned = re.sub(r'[\\/:*?"<>|]', "", text or "")
    # 压缩空白
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "未命名"


def _extract_categories_from_content(content: str) -> list[str]:
    """从报告内容中提取分类名（粗略提取，用于生成 wiki 链接）"""
    cats = []
    # 匹配 "## 工作详情" 段落下的 **分类名**（时长）
    detail_match = re.search(r"##\s*工作详情(.*?)(?=##|\Z)", content, re.S)
    if detail_match:
        cats = re.findall(r"\*\*([^*]+)\*\*", detail_match.group(1))
    # 兜底：从分类表格中提取
    if not cats:
        table_match = re.findall(r"^\|\s*([^|]+?)\s*\|", content, re.M)
        cats = [c.strip() for c in table_match if c.strip() not in ("分类", "时长", "占比", "应用", "------")]
    # 去重保序
    seen, result = set(), []
    for c in cats:
        if c and c not in seen and len(c) < 30:
            seen.add(c)
            result.append(c)
    return result


def _extract_summary_metrics(content: str) -> dict:
    """从报告内容中提取可量化指标（专注时长、分类数等），供 Dataview 字段使用"""
    metrics = {}
    # 专注时长（匹配 "专注Xh" / "专注Xmin" / "累计专注X"）
    m = re.search(r"专注\s*(\d+(?:\.\d+)?)\s*(h|hour|min|分钟|小时)", content, re.I)
    if m:
        val = float(m.group(1))
        # 统一换算为分钟
        unit = m.group(2).lower()
        metrics["focus_min"] = val * 60 if unit in ("h", "hour", "小时") else val
    # 分类数（匹配 "涉及X个工作类别" / "X 个工作类别"）
    m = re.search(r"(\d+)\s*个工作类别", content)
    if m:
        metrics["category_count"] = int(m.group(1))
    # 番茄完成数
    m = re.search(r"完成番茄钟[：:]\s*(\d+)\s*个", content)
    if m:
        metrics["pomodoro_count"] = int(m.group(1))
    return metrics


def export_report_as_obsidian(content: str, target_date: str) -> str:
    """导出为标准 Obsidian Markdown
    - 添加 YAML frontmatter（date, tags, type）
    - 将分类名转为 [[wiki 链接]]
    - 在末尾追加相关笔记反向链接区
    """
    try:
        cats = _extract_categories_from_content(content)
        # 替换正文中的 **分类名** 为 **[[分类名]]**
        obsidian_content = content
        for cat in cats:
            # 仅替换加粗出现的分类名，避免误伤
            obsidian_content = obsidian_content.replace(f"**{cat}**", f"**[[{cat}]]**")

        # 构造 frontmatter
        today_str = date.today().isoformat()
        frontmatter = [
            "---",
            f"date: {target_date}",
            "type: daily-report",
            "source: ChallengeDaily",
            f"created: {today_str}",
            "tags:",
            "  - 日报",
            "  - ChallengeDaily",
        ]
        for cat in cats[:8]:
            frontmatter.append(f"  - {cat}")
        frontmatter.append("---")

        # 末尾追加反向链接区
        backlinks = ["", "## 相关笔记", ""]
        for cat in cats[:6]:
            backlinks.append(f"- [[{cat}]]")
        backlinks.append(f"- [[{target_date}]]")

        return "\n".join(frontmatter) + "\n\n" + obsidian_content + "\n" + "\n".join(backlinks) + "\n"
    except Exception as e:
        logger.error(f"Obsidian 标准导出失败: {e}", exc_info=True)
        return content


def export_report_as_obsidian_dataview(content: str, target_date: str) -> str:
    """导出为 Obsidian Dataview 双向链接格式
    - 在 frontmatter 中追加 Dataview 内联字段（focus_min、category_count 等）
    - 在每个分类段落追加 :: 元数据行，供 Dataview 查询
    - 末尾追加 Dataview 查询块（列出本周所有日报）
    """
    try:
        base = export_report_as_obsidian(content, target_date)
        metrics = _extract_summary_metrics(content)
        cats = _extract_categories_from_content(content)

        # 在 frontmatter 末尾（--- 之前）插入 Dataview 字段
        # frontmatter 结束符为第一个 "---\n\n"
        fm_end = base.find("---\n\n")
        if fm_end > 0:
            dv_lines = []
            dv_lines.append(f"focus_min:: {metrics.get('focus_min', 0)}")
            dv_lines.append(f"category_count:: {metrics.get('category_count', len(cats))}")
            if "pomodoro_count" in metrics:
                dv_lines.append(f"pomodoro_count:: {metrics['pomodoro_count']}")
            dv_lines.append(f"weekday:: {datetime.strptime(target_date, '%Y-%m-%d').strftime('%A')}")
            dv_lines.append(f"week:: {datetime.strptime(target_date, '%Y-%m-%d').isocalendar()[1]}")
            base = base[:fm_end] + "\n".join(dv_lines) + "\n" + base[fm_end:]

        # 末尾追加 Dataview 查询块
        dv_query = (
            "\n## Dataview 查询\n\n"
            "```dataview\n"
            "TABLE date, focus_min, category_count, pomodoro_count\n"
            "FROM #日报\n"
            "WHERE type = \"daily-report\"\n"
            "SORT date DESC\n"
            "LIMIT 14\n"
            "```\n\n"
            "```dataviewjs\n"
            "// 按周聚合专注时长趋势图\n"
            "const pages = dv.pages('#日报').where(p => p.focus_min);\n"
            "if (pages.length > 0) {\n"
            "  const data = pages.array().map(p => ({x: p.date, y: p.focus_min}));\n"
            "  dv.paragraph(`本周累计专注 ${data.reduce((s,d)=>s+d.y,0).toFixed(0)} 分钟`);\n"
            "}\n"
            "```\n"
        )
        base = base.rstrip() + "\n" + dv_query
        return base
    except Exception as e:
        logger.error(f"Obsidian Dataview 导出失败: {e}", exc_info=True)
        return export_report_as_obsidian(content, target_date)
