"""日报质量4维评分引擎
维度1 完整度(Completeness)：是否覆盖"今日完成/明日计划/问题风险/关键指标"四大要素
维度2 数据支撑(Data-backed)：是否含具体数字、时长、百分比、计数等量化证据
维度3 行动性(Actionability)：是否含明确的下一步动作、决策项、阻塞点
维度4 可读性(Readability)：结构化程度（标题/列表/段落）、长度适中、无冗余

每维度 0-100 分，总分 = 加权平均（完整度30% + 数据25% + 行动25% + 可读20%）
等级：S(>=85) A(>=70) B(>=55) C(>=40) D(<40)
"""
import re
from typing import Dict, Any

# ── 维度1：完整度 ──
SECTION_PATTERNS = {
    'done': [r'今日完成|今日工作|完成事项|工作内容|今日进展|做了什么|completed|done'],
    'plan': [r'明日计划|下周计划|后续计划|下一步|计划事项|todo|plan|next'],
    'issue': [r'遇到问题|问题与风险|阻塞|风险|困难|卡点|issue|risk|blocker|problem'],
    'metric': [r'关键指标|数据指标|产出|成果|metrics|kpi|achievement|产出统计'],
}


def _score_completeness(text: str) -> Dict[str, Any]:
    """完整度评分：检查4大要素是否齐全"""
    hit = {}
    for key, patterns in SECTION_PATTERNS.items():
        hit[key] = any(re.search(p, text, re.IGNORECASE) for p in patterns)
    hit_count = sum(hit.values())
    # 4个全有=100, 3个=75, 2个=50, 1个=25, 0个=10
    score = {0: 10, 1: 25, 2: 50, 3: 75, 4: 100}.get(hit_count, 10)
    return {
        'score': score,
        'detail': {
            'has_done': hit['done'],
            'has_plan': hit['plan'],
            'has_issue': hit['issue'],
            'has_metric': hit['metric'],
        },
        'suggestion': _completeness_suggestion(hit),
    }


def _completeness_suggestion(hit: Dict[str, bool]) -> str:
    tips = []
    if not hit['done']:
        tips.append('缺少"今日完成"部分')
    if not hit['plan']:
        tips.append('缺少"明日计划"部分')
    if not hit['issue']:
        tips.append('建议补充"遇到的问题/风险"')
    if not hit['metric']:
        tips.append('建议补充"关键指标/产出数据"')
    return '；'.join(tips) if tips else '四大要素齐全，结构完整'


# ── 维度2：数据支撑 ──
NUMBER_PATTERN = re.compile(r'\d+\.?\d*')
TIME_PATTERN = re.compile(r'\d+\.?\d*\s*(小时|分钟|分|时|h|m|hour|min)')
PERCENT_PATTERN = re.compile(r'\d+\.?\d*\s*%|百分之\d+')
COUNT_PATTERN = re.compile(r'\d+\s*(个|次|项|条|篇|个番茄|pomodoro|commit|PR|bug|task)')


def _score_data_backed(text: str) -> Dict[str, Any]:
    """数据支撑评分：量化证据密度"""
    time_hits = len(TIME_PATTERN.findall(text))
    percent_hits = len(PERCENT_PATTERN.findall(text))
    count_hits = len(COUNT_PATTERN.findall(text))
    all_numbers = len(NUMBER_PATTERN.findall(text))

    # 时长数据权重最高（日报核心）
    score = min(100, time_hits * 25 + percent_hits * 20 + count_hits * 15 + all_numbers * 3)
    if all_numbers == 0:
        score = 5  # 一个数字都没有，极低分

    return {
        'score': score,
        'detail': {
            'time_refs': time_hits,
            'percent_refs': percent_hits,
            'count_refs': count_hits,
            'total_numbers': all_numbers,
        },
        'suggestion': (
            '数据支撑充分' if score >= 70
            else f'建议增加量化数据（当前{all_numbers}个数字，含{time_hits}处时长引用）'
        ),
    }


# ── 维度3：行动性 ──
ACTION_VERBS = re.compile(
    r'(完成|修复|实现|优化|重构|提交|部署|测试|评审|对接|推进|启动|搭建|编写|排查|迁移|发布|上线|跟进|确认|协调|安排|准备|更新|迭代|梳理|调研)'
)
NEXT_STEP_PATTERN = re.compile(r'(明日|下周|下一步|后续|计划|接下来|待办|TODO|todo|will|plan to|going to)')
BLOCKER_PATTERN = re.compile(r'(阻塞|卡住|等待|依赖|风险|问题|困难|需协调|待确认|blocked|waiting|depend)')


def _score_actionability(text: str) -> Dict[str, Any]:
    """行动性评分：是否含明确动作、下一步、阻塞点"""
    action_hits = len(ACTION_VERBS.findall(text))
    next_hits = len(NEXT_STEP_PATTERN.findall(text))
    blocker_hits = len(BLOCKER_PATTERN.findall(text))

    # 动作词 + 下一步 + 阻塞点三要素
    score = min(100, action_hits * 12 + next_hits * 20 + blocker_hits * 15)
    if action_hits == 0 and next_hits == 0:
        score = 10  # 无任何行动性描述

    return {
        'score': score,
        'detail': {
            'action_verbs': action_hits,
            'next_step_refs': next_hits,
            'blocker_refs': blocker_hits,
        },
        'suggestion': (
            '行动性优秀' if score >= 70
            else f'建议增加动作描述和下一步计划（当前{action_hits}个动作词，{next_hits}处计划引用）'
        ),
    }


# ── 维度4：可读性 ──
HEADER_PATTERN = re.compile(r'^#{1,6}\s.+|^【.+】|^\d+[\.、]\s', re.MULTILINE)
LIST_PATTERN = re.compile(r'^[\-\*\+]\s|^\d+[\.、]\s', re.MULTILINE)
LONG_PARAGRAPH_PATTERN = re.compile(r'[^\n]{300,}')  # 超过300字的段落扣分


def _score_readability(text: str) -> Dict[str, Any]:
    """可读性评分：结构化程度 + 长度适中"""
    lines = text.strip().split('\n')
    non_empty = [l for l in lines if l.strip()]
    line_count = len(non_empty)
    header_hits = len(HEADER_PATTERN.findall(text))
    list_hits = len(LIST_PATTERN.findall(text))
    long_para_hits = len(LONG_PARAGRAPH_PATTERN.findall(text))
    char_count = len(text.replace('\n', '').replace(' ', ''))

    # 结构分（标题+列表）
    struct_score = min(50, header_hits * 10 + list_hits * 5)
    # 长度分（200-1500字最佳）
    if char_count < 50:
        length_score = 15
    elif char_count < 200:
        length_score = 35
    elif char_count <= 1500:
        length_score = 50
    elif char_count <= 2500:
        length_score = 35
    else:
        length_score = 20
    # 长段落扣分
    penalty = long_para_hits * 10

    score = max(0, struct_score + length_score - penalty)

    return {
        'score': score,
        'detail': {
            'headers': header_hits,
            'list_items': list_hits,
            'line_count': line_count,
            'char_count': char_count,
            'long_paragraphs': long_para_hits,
        },
        'suggestion': (
            '可读性优秀' if score >= 70
            else f'建议增加标题/列表结构化排版（当前{header_hits}个标题，{list_hits}个列表项）'
        ),
    }


def _grade(total: float) -> str:
    if total >= 85:
        return 'S'
    elif total >= 70:
        return 'A'
    elif total >= 55:
        return 'B'
    elif total >= 40:
        return 'C'
    else:
        return 'D'


def score_report_quality(text: str) -> Dict[str, Any]:
    """日报质量4维评分主函数
    返回：
    {
        'total': 0-100,
        'grade': 'S/A/B/C/D',
        'dimensions': {
            'completeness': {'score': 0-100, 'detail': {...}, 'suggestion': '...'},
            'data_backed': {...},
            'actionability': {...},
            'readability': {...},
        },
        'weights': {'completeness': 0.30, 'data_backed': 0.25, 'actionability': 0.25, 'readability': 0.20},
        'overall_suggestion': '...',
    }
    """
    if not text or not text.strip():
        return {
            'total': 0,
            'grade': 'D',
            'dimensions': {},
            'weights': {},
            'overall_suggestion': '日报内容为空，请先生成或填写日报',
        }

    completeness = _score_completeness(text)
    data_backed = _score_data_backed(text)
    actionability = _score_actionability(text)
    readability = _score_readability(text)

    weights = {'completeness': 0.30, 'data_backed': 0.25, 'actionability': 0.25, 'readability': 0.20}
    total = round(
        completeness['score'] * weights['completeness']
        + data_backed['score'] * weights['data_backed']
        + actionability['score'] * weights['actionability']
        + readability['score'] * weights['readability'],
        1,
    )

    # 综合建议：取最低分的维度建议
    dims = [
        ('完整度', completeness),
        ('数据支撑', data_backed),
        ('行动性', actionability),
        ('可读性', readability),
    ]
    lowest = min(dims, key=lambda x: x[1]['score'])
    overall = f"总分 {total} ({_grade(total)}级)。短板：{lowest[0]}（{lowest[1]['score']}分）— {lowest[1]['suggestion']}"

    return {
        'total': total,
        'grade': _grade(total),
        'dimensions': {
            'completeness': completeness,
            'data_backed': data_backed,
            'actionability': actionability,
            'readability': readability,
        },
        'weights': weights,
        'overall_suggestion': overall,
    }
