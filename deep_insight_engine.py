"""
DeepInsight Engine — 基于学术框架的深度分析引擎

从原始活动数据中计算出10大心理学/教育学/社会学框架的量化指标，
生成结构化分析报告供AI自然语言解读。

不是改提示词，而是建真正的分析引擎。
"""

import yaml
import math
import os
import json
import logging
from datetime import datetime, date, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

# ─── 加载知识库 ────────────────────────────────────────────────
_FRAMEWORKS = None
_CATEGORY_PROFILES = None
_REFERENCES = None

def _load_knowledge_base():
    global _FRAMEWORKS, _CATEGORY_PROFILES, _REFERENCES
    if _FRAMEWORKS is not None:
        return
    kb_path = os.path.join(os.path.dirname(__file__), 'deep_insight_frameworks.yaml')
    try:
        with open(kb_path, 'r', encoding='utf-8') as f:
            kb = yaml.safe_load(f)
        _FRAMEWORKS = {fw['id']: fw for fw in kb.get('frameworks', [])}
        _CATEGORY_PROFILES = kb.get('category_profiles', {})
        _REFERENCES = {r['id']: r['citation'] for r in kb.get('references', [])}
        logger.info(f"[DeepInsight] Loaded {len(_FRAMEWORKS)} frameworks, {len(_REFERENCES)} references")
    except Exception as e:
        logger.error(f"[DeepInsight] Failed to load knowledge base: {e}")
        _FRAMEWORKS = {}
        _CATEGORY_PROFILES = {}
        _REFERENCES = {}


def get_framework(id_):
    _load_knowledge_base()
    return _FRAMEWORKS.get(id_)

def get_category_profile(category):
    _load_knowledge_base()
    return _CATEGORY_PROFILES.get(category, _CATEGORY_PROFILES.get('生活', {}))

def get_reference(id_):
    _load_knowledge_base()
    return _REFERENCES.get(id_, '')


# ─── 分段分析：从活动列表中提取专注段 ──────────────────────
_FOCUS_GAP_MIN = 15  # 同类别活动间超过此分钟数则拆分为不同段

def _extract_focus_segments(activities, interval_sec=60):
    """
    将活动列表按时间和类别连续性分段。
    返回 [{"category": ..., "start": ..., "end": ..., "duration_min": ..., "app": ..., "apps_set": ...}]
    同类别活动间如果时间间隔超过 _FOCUS_GAP_MIN 分钟，则拆分为不同段。
    """
    if not activities:
        return []
    
    segments = []
    current = None
    
    for act in activities:
        cat = act.get('category', '其他')
        app = act.get('app_name', 'unknown')
        ts = act.get('timestamp', '')
        
        # 同类别 → 检查时间间隔是否超过阈值
        if current and current['category'] == cat:
            time_gap = _ts_diff_min(current['end'], ts)
            if time_gap > _FOCUS_GAP_MIN:
                # 间隔过大，结束当前段，开启新段
                segments.append(current)
                current = {
                    'category': cat,
                    'start': ts,
                    'end': ts,
                    'duration_min': interval_sec / 60,
                    'apps_set': {app},
                }
            else:
                # 连续 → 合并
                current['apps_set'].add(app)
                current['end'] = ts
                current['duration_min'] += max(interval_sec / 60, time_gap)
        else:
            if current:
                segments.append(current)
            current = {
                'category': cat,
                'start': ts,
                'end': ts,
                'duration_min': interval_sec / 60,
                'apps_set': {app},
            }
    
    if current:
        segments.append(current)
    
    return segments


def _ts_diff_min(ts1, ts2):
    """计算两个时间戳字符串之间的分钟差。失败返回 0。"""
    try:
        from datetime import datetime as _dt
        # 兼容 ISO 格式 (T 或空格)
        t1 = _dt.fromisoformat(ts1.replace('T', ' '))
        t2 = _dt.fromisoformat(ts2.replace('T', ' '))
        return abs((t2 - t1).total_seconds()) / 60
    except Exception:
        return 0


def _derive_hour(ts_str):
    """从 timestamp 字符串提取小时，失败返回 None（调用方需过滤）"""
    try:
        h = int(ts_str.split('T')[-1].split(' ')[-1].split(':')[0])
        return h if 0 <= h <= 23 else None
    except (ValueError, IndexError, AttributeError):
        return None
    except (ValueError, IndexError):
        return -1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 框架1: 心流理论 — 计算 Flow Index
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_flow_metrics(activities, interval_sec=60):
    segments = _extract_focus_segments(activities, interval_sec)
    if not segments:
        return {'flow_index': 0, 'focus_continuity': 0, 'context_switch_cost': 0,
                'flow_minutes': 0, 'switch_count': 0, 'longest_focus_min': 0}
    
    total_duration = sum(s['duration_min'] for s in segments)
    switch_count = len(segments) - 1
    
    # 心流候选段：连续同一类别>25分钟
    flow_segments = [s for s in segments if s['duration_min'] >= 25 and get_category_profile(s['category']).get('flow_relevant', False)]
    flow_minutes = sum(s['duration_min'] for s in flow_segments)
    longest_focus = max(s['duration_min'] for s in segments)
    
    # Flow Index = 连续专注时长 / sqrt(切换次数+1) * 归一化
    raw_flow = flow_minutes / math.sqrt(switch_count + 1)
    flow_index = min(round(raw_flow / total_duration * 60 if total_duration > 0 else 0, 1), 100)
    
    focus_continuity = round(longest_focus / total_duration if total_duration > 0 else 0, 3)
    
    # 上下文切换代价 (Mark et al. 2008: 23分钟恢复)
    switch_cost = round(switch_count * 23 / (total_duration + 1), 3)
    
    return {
        'flow_index': flow_index,
        'focus_continuity': focus_continuity,
        'context_switch_cost': min(switch_cost, 1.0),
        'flow_minutes': round(flow_minutes, 1),
        'switch_count': switch_count,
        'longest_focus_min': round(longest_focus, 1),
        'flow_segments_detail': [
            {'category': s['category'], 'duration_min': round(s['duration_min'], 1), 'apps': list(s['apps_set'])}
            for s in flow_segments
        ]
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 框架2: 刻意练习 — 计算 Deliberate Ratio
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_deliberate_practice_metrics(activities, interval_sec=60, history_activities=None):
    segments = _extract_focus_segments(activities, interval_sec)
    if not segments:
        return {'deliberate_ratio': 0, 'comfort_zone_ratio': 0, 'skill_accumulation_hours': 0}
    
    total_duration = sum(s['duration_min'] for s in segments)
    
    learning_zone_min = 0
    comfort_zone_min = 0
    
    for seg in segments:
        profile = get_category_profile(seg['category'])
        zone = profile.get('deliberate_practice_zone', 'comfort')
        # 多工具 = 新元素 → 学习区信号
        apps_count = len(seg['apps_set'])
        is_learning = (zone == 'learning') or (zone == 'learning' and apps_count >= 2)
        
        # 学习分类始终算学习区
        if seg['category'] == '学习':
            is_learning = True
        
        if is_learning:
            learning_zone_min += seg['duration_min']
        else:
            comfort_zone_min += seg['duration_min']
    
    # 技能累积：从历史数据中估算
    skill_hours = 0
    if history_activities is not None:
        try:
            skill_hours = round(len(history_activities) * interval_sec / 3600, 1)
        except (TypeError, ValueError, ZeroDivisionError):
            skill_hours = 0
    
    deliberate_ratio = round(learning_zone_min / total_duration if total_duration > 0 else 0, 3)
    comfort_ratio = round(comfort_zone_min / total_duration if total_duration > 0 else 0, 3)
    
    return {
        'deliberate_ratio': deliberate_ratio,
        'comfort_zone_ratio': comfort_ratio,
        'learning_zone_min': round(learning_zone_min, 1),
        'comfort_zone_min': round(comfort_zone_min, 1),
        'skill_accumulation_hours': skill_hours,
        'years_to_expert': round(max(0, 10000 - skill_hours) / max(skill_hours * 365 / max(len(history_activities or []) * interval_sec / 86400, 1), 0.01), 1) if skill_hours > 0 and history_activities and len(history_activities) > 0 else None,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 框架3: 布鲁姆认知分类 — 计算 Cognitive Depth
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_bloom_metrics(activities, interval_sec=60):
    _load_knowledge_base()
    if not activities:
        return {'cognitive_depth': 0, 'higher_order_ratio': 0, 'bloom_distribution': {}}
    
    total_duration = 0
    level_durations = defaultdict(float)  # level -> minutes
    
    for act in activities:
        cat = act.get('category', '其他')
        dur = interval_sec / 60
        total_duration += dur
        
        profile = get_category_profile(cat)
        bloom_levels = profile.get('bloom_levels', [1, 2])
        # 均分到两个主层级
        for level in bloom_levels:
            level_durations[level] += dur / len(bloom_levels)
    
    if total_duration == 0:
        return {'cognitive_depth': 0, 'higher_order_ratio': 0, 'bloom_distribution': {}}
    
    # 加权认知深度：L1=1, L2=1.5, ..., L6=5，加权平均后再映射到 1-6
    bloom_weights = {1: 1.0, 2: 1.5, 3: 2.0, 4: 3.0, 5: 4.0, 6: 5.0}
    weighted_sum = sum(level_durations[l] * bloom_weights.get(l, l) for l in range(1, 7))
    raw_depth = weighted_sum / total_duration  # 范围 [1.0, 5.0]
    
    # 归一化到 1-6：raw_depth 1.0→1, 5.0→6，线性映射
    cognitive_depth = round(1 + (raw_depth - 1.0) / (5.0 - 1.0) * 5, 1)
    cognitive_depth = max(1.0, min(6.0, cognitive_depth))
    
    higher_order_min = sum(level_durations[l] for l in [4, 5, 6])
    higher_order_ratio = round(higher_order_min / total_duration, 3)
    
    bloom_distribution = {f"L{l}": round(level_durations[l], 1) for l in range(1, 7) if level_durations[l] > 0}
    
    # 找主导层级
    dominant_level = max(level_durations, key=level_durations.get) if level_durations else 1
    level_names = {1: '记忆', 2: '理解', 3: '应用', 4: '分析', 5: '评价', 6: '创造'}
    
    return {
        'cognitive_depth': cognitive_depth,
        'higher_order_ratio': higher_order_ratio,
        'bloom_distribution': bloom_distribution,
        'dominant_level': dominant_level,
        'dominant_level_name': level_names.get(dominant_level, '未知'),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 框架4: 自我决定理论 — 计算 SDT Scores
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_sdt_metrics(activities, interval_sec=60):
    segments = _extract_focus_segments(activities, interval_sec)
    if not segments:
        return {'autonomy_score': 50, 'competence_score': 50, 'relatedness_score': 50, 'intrinsic_motivation_index': 50}
    
    total_duration = sum(s['duration_min'] for s in segments)
    
    # 自主性：主动发起 vs 被动响应
    autonomous_cats = {'开发', '设计', '学习', '数据分析', '产品'}
    reactive_cats = {'会议', '沟通', '管理'}
    autonomous_min = sum(s['duration_min'] for s in segments if s['category'] in autonomous_cats)
    reactive_min = sum(s['duration_min'] for s in segments if s['category'] in reactive_cats)
    autonomy_score = round(min(100, (autonomous_min / total_duration * 100 if total_duration > 0 else 50)), 0)
    
    # 胜任感：专注完成 vs 中断未恢复
    completed_segments = [s for s in segments if s['duration_min'] >= 15]
    completion_rate = len(completed_segments) / len(segments) if segments else 0
    competence_score = round(min(100, completion_rate * 80 + autonomy_score * 0.2), 0)
    
    # 归属感：协作活动占比
    social_cats = {'会议', '沟通'}
    social_min = sum(s['duration_min'] for s in segments if s['category'] in social_cats)
    social_ratio = social_min / total_duration if total_duration > 0 else 0
    # 理想比例约15-25%，过多或过少都扣分
    relatedness_raw = 100 - abs(social_ratio - 0.20) * 300
    relatedness_score = round(max(20, min(100, relatedness_raw)), 0)
    
    # 内在动机指数
    imi = round(autonomy_score * 0.4 + competence_score * 0.35 + relatedness_score * 0.25, 0)
    
    return {
        'autonomy_score': int(autonomy_score),
        'competence_score': int(competence_score),
        'relatedness_score': int(relatedness_score),
        'intrinsic_motivation_index': int(imi),
        'autonomous_min': round(autonomous_min, 1),
        'reactive_min': round(reactive_min, 1),
        'social_min': round(social_min, 1),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 框架5: 超日节律 — 计算 Rhythm Alignment
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_ultradian_metrics(activities, interval_sec=60):
    if not activities:
        return {'rhythm_alignment': 0, 'rest_adequacy': 0, 'afternoon_crash_risk': 0,
                'longest_streak_min': 0, 'rest_periods': 0}
    
    # 按小时统计
    hour_minutes = defaultdict(float)
    for act in activities:
        h = _derive_hour(act.get('timestamp', ''))
        if h is not None:
            hour_minutes[h] += interval_sec / 60
    
    # 检测连续工作段(无休息)
    work_hours = sorted([h for h in hour_minutes if hour_minutes[h] > 5])
    streaks = []
    current_streak = []
    for h in work_hours:
        if current_streak and h - current_streak[-1] > 1:
            streaks.append(current_streak)
            current_streak = [h]
        else:
            current_streak.append(h)
    if current_streak:
        streaks.append(current_streak)
    
    longest_streak_hours = max(len(s) for s in streaks) if streaks else 0
    longest_streak_min = longest_streak_hours * 60
    
    # 休息充足度：理想是每90分钟休息一次
    total_work_min = sum(hour_minutes.values())
    ideal_rest_periods = max(1, int(total_work_min / 90))
    actual_rest_periods = max(1, len(streaks))  # 段数-1 = 休息次数
    rest_adequacy = round(min(1.0, actual_rest_periods / ideal_rest_periods), 3)
    
    # 下午崩溃风险
    afternoon_hours = [13, 14, 15]  # 午后1-3点
    morning_hours = [9, 10, 11]
    afternoon_work = sum(hour_minutes.get(h, 0) for h in afternoon_hours)
    morning_work = sum(hour_minutes.get(h, 0) for h in morning_hours)
    lunch_break = max(0, 12 - max([h for h in work_hours if h < 12], default=11))  # 12点是否休息
    
    crash_risk = 0
    if afternoon_work > 0:
        crash_risk = min(100, round(afternoon_work / max(morning_work, 1) * 50 + (longest_streak_hours - 1) * 15))
    
    # 节律对齐度
    rhythm_alignment = round(rest_adequacy * 0.6 + (1 - min(crash_risk / 100, 1)) * 0.4, 3)
    
    return {
        'rhythm_alignment': rhythm_alignment,
        'rest_adequacy': rest_adequacy,
        'afternoon_crash_risk': int(crash_risk),
        'longest_streak_min': longest_streak_min,
        'rest_periods': len(streaks) - 1 if len(streaks) > 1 else 0,
        'ideal_rest_periods': ideal_rest_periods,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 框架6: 深度工作 — 计算 Deep Work Ratio
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_deep_work_metrics(activities, interval_sec=60):
    segments = _extract_focus_segments(activities, interval_sec)
    if not segments:
        return {'deep_work_ratio': 0, 'shallow_work_ratio': 0}
    
    total_duration = sum(s['duration_min'] for s in segments)
    
    deep_min = 0
    shallow_min = 0
    for seg in segments:
        profile = get_category_profile(seg['category'])
        is_deep_eligible = profile.get('deep_work_eligible', False)
        # 深度工作 = 高认知类别 + 持续>30分钟
        if is_deep_eligible and seg['duration_min'] >= 30:
            deep_min += seg['duration_min']
        else:
            shallow_min += seg['duration_min']
    
    return {
        'deep_work_ratio': round(deep_min / total_duration if total_duration > 0 else 0, 3),
        'shallow_work_ratio': round(shallow_min / total_duration if total_duration > 0 else 0, 3),
        'deep_work_min': round(deep_min, 1),
        'shallow_work_min': round(shallow_min, 1),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 框架7: 结构洞/社会资本 — 计算 Diversity & Bridging
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_structural_holes_metrics(activities, interval_sec=60):
    if not activities:
        return {'tool_diversity': 0, 'cross_domain_index': 0, 'knowledge_bridging': 0}
    
    # 工具使用分布
    app_durations = defaultdict(float)
    cat_durations = defaultdict(float)
    for act in activities:
        app = act.get('app_name', 'unknown')
        cat = act.get('category', '其他')
        dur = interval_sec / 60
        app_durations[app] += dur
        cat_durations[cat] += dur
    
    total = sum(app_durations.values())
    
    # Shannon 多样性指数
    diversity = 0
    for dur in app_durations.values():
        p = dur / total if total > 0 else 0
        if p > 0:
            diversity -= p * math.log(p)
    
    # 跨域指数
    all_categories = set(_CATEGORY_PROFILES.keys()) if _CATEGORY_PROFILES else set()
    used_categories = set(cat_durations.keys())
    cross_domain = round(len(used_categories) / max(len(all_categories), 1), 3)
    
    # 知识桥接度
    segments = _extract_focus_segments(activities, interval_sec)
    cross_switches = 0
    for i in range(1, len(segments)):
        if segments[i]['category'] != segments[i-1]['category']:
            cross_switches += 1
    bridging = round(cross_switches * diversity, 1)
    
    # top tool concentration
    top_app = max(app_durations, key=app_durations.get) if app_durations else ''
    top_pct = round(app_durations[top_app] / total * 100 if total > 0 else 0, 1)
    
    return {
        'tool_diversity': round(diversity, 2),
        'cross_domain_index': cross_domain,
        'knowledge_bridging': bridging,
        'unique_apps': len(app_durations),
        'unique_categories': len(cat_durations),
        'top_app': top_app,
        'top_app_pct': top_pct,
        'category_distribution': {k: round(v, 1) for k, v in sorted(cat_durations.items(), key=lambda x: -x[1])},
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 框架8: 最近发展区 — 计算 ZPD Alignment
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_zpd_metrics(activities, interval_sec=60, history_activities=None):
    segments = _extract_focus_segments(activities, interval_sec)
    if not segments:
        return {'challenge_match_ratio': 0, 'zpd_alignment': 50}
    
    total_duration = sum(s['duration_min'] for s in segments)
    
    # 判断是否有新元素（对比历史）
    historical_apps = set()
    if history_activities:
        for act in history_activities:
            historical_apps.add(act.get('app_name', ''))
    
    zpd_min = 0
    for seg in segments:
        profile = get_category_profile(seg['category'])
        zone = profile.get('deliberate_practice_zone', 'comfort')
        has_new = any(app not in historical_apps for app in seg['apps_set']) if historical_apps else len(seg['apps_set']) > 1
        
        if zone == 'learning' and has_new:
            # ZPD内：已知领域 + 新元素
            zpd_min += seg['duration_min']
        elif seg['category'] == '学习':
            zpd_min += seg['duration_min'] * 0.7  # 学习活动部分在ZPD
    
    challenge_match = round(zpd_min / total_duration if total_duration > 0 else 0, 3)
    zpd_alignment = round(min(100, challenge_match * 200 + 30), 0)  # 基线30分
    
    return {
        'challenge_match_ratio': challenge_match,
        'zpd_alignment': int(zpd_alignment),
        'zpd_min': round(zpd_min, 1),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 框架9: 习惯回路 — 计算 Habit Consistency
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_habit_metrics(activities, interval_sec=60, daily_summaries=None):
    if not activities:
        return {'habit_consistency': 0, 'routine_stability': 0, 'detected_patterns': []}
    
    # 检测时间-类别模式
    hour_cat = defaultdict(lambda: defaultdict(float))
    for act in activities:
        h = _derive_hour(act.get('timestamp', ''))
        cat = act.get('category', '其他')
        if h is not None:
            hour_cat[h][cat] += interval_sec / 60
    
    # 找到每个小时的 dominant category
    patterns = []
    for h in sorted(hour_cat.keys()):
        if hour_cat[h]:
            dominant_cat = max(hour_cat[h], key=lambda c: hour_cat[h][c])
            if hour_cat[h][dominant_cat] >= 15:  # 至少15分钟才算模式
                patterns.append({
                    'hour': h,
                    'category': dominant_cat,
                    'duration_min': round(hour_cat[h][dominant_cat], 1),
                })
    
    # 习惯一致性（如果有 daily_summaries 可算连续天数）
    consistency = 0
    consecutive_days = 0
    if daily_summaries:
        for ds in daily_summaries:
            if ds.get('total_duration_min', 0) > 30:
                consecutive_days += 1
            else:
                break
        consistency = round(consecutive_days / 66 * 100, 0)  # 66天=研究中位数
    
    # 常规稳定性
    if patterns:
        routine_stability = round(len(patterns) / 12, 3)  # 12小时工作日
    else:
        routine_stability = 0
    
    return {
        'habit_consistency': int(consistency),
        'routine_stability': routine_stability,
        'consecutive_days': consecutive_days,
        'detected_patterns': patterns,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 框架10: 心理资本 (PsyCap) — 计算 HERO Scores
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def compute_psycap_metrics(activities, interval_sec=60):
    # 依赖之前计算的部分指标
    sdt = compute_sdt_metrics(activities, interval_sec)
    flow = compute_flow_metrics(activities, interval_sec)
    segments = _extract_focus_segments(activities, interval_sec)
    
    if not segments:
        return {'hope_score': 50, 'efficacy_score': 50, 'resilience_score': 50,
                'optimism_score': 50, 'psycap_index': 50}
    
    total_duration = sum(s['duration_min'] for s in segments)
    
    # 希望(Hope)：目标+路径
    # 代理：多工具切换后回到主线 = 有路径
    hope_score = round(min(100, sdt['autonomy_score'] * 0.6 + 
                           min(flow['flow_index'], 50) * 0.4), 0)
    
    # 自我效能(Efficacy)：完成度
    completed = [s for s in segments if s['duration_min'] >= 10]
    efficacy_score = round(min(100, len(completed) / len(segments) * 80 + 
                               sdt['competence_score'] * 0.2), 0) if segments else 50
    
    # 韧性(Resilience)：中断后恢复
    # 检测短段(可能中断)后是否有长段(恢复)
    resilient_count = 0
    for i in range(1, len(segments)):
        if segments[i-1]['duration_min'] < 5 and segments[i]['duration_min'] >= 15:
            resilient_count += 1
    resilience_score = round(max(0, min(100, 50 + resilient_count * 20 - 
                                      max(0, flow['switch_count'] - 5) * 3)), 0)
    
    # 乐观(Optimism)：高能时段使用率
    productive_hours = [9, 10, 11, 14, 15, 16]  # 高能时段
    productive_min = 0
    for act in activities:
        h = _derive_hour(act.get('timestamp', ''))
        if h is not None and h in productive_hours:
            productive_min += interval_sec / 60
    productive_ratio = productive_min / total_duration if total_duration > 0 else 0
    optimism_score = round(min(100, productive_ratio * 150 + 25), 0)
    
    psycap = round((hope_score + efficacy_score + resilience_score + optimism_score) / 4, 0)
    
    return {
        'hope_score': int(hope_score),
        'efficacy_score': int(efficacy_score),
        'resilience_score': int(resilience_score),
        'optimism_score': int(optimism_score),
        'psycap_index': int(psycap),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 综合分析入口 — 一键生成全维度报告
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def generate_deep_insight_report(activities, interval_sec=60, history_activities=None, daily_summaries=None):
    """
    从活动数据生成完整的深度洞察报告。
    返回结构化的分析结果，供 AI 自然语言解读。
    """
    _load_knowledge_base()
    
    if not activities:
        return {
            'status': 'no_data',
            'message': '没有足够的数据进行分析',
            'frameworks': {},
        }
    
    report = {
        'status': 'ok',
        'generated_at': datetime.now().isoformat(),
        'data_points': len(activities),
        'frameworks': {},
    }
    
    try:
        report['frameworks']['flow_theory'] = {
            'name': '心流理论',
            'scholar': 'Csikszentmihalyi (1990)',
            'metrics': compute_flow_metrics(activities, interval_sec),
        }
    except Exception as e:
        logger.warning(f"[DeepInsight] flow_theory failed: {e}")
    
    try:
        report['frameworks']['deliberate_practice'] = {
            'name': '刻意练习',
            'scholar': 'Ericsson (1993)',
            'metrics': compute_deliberate_practice_metrics(activities, interval_sec, history_activities),
        }
    except Exception as e:
        logger.warning(f"[DeepInsight] deliberate_practice failed: {e}")
    
    try:
        report['frameworks']['bloom_taxonomy'] = {
            'name': '布鲁姆认知分类',
            'scholar': 'Bloom/Anderson (2001)',
            'metrics': compute_bloom_metrics(activities, interval_sec),
        }
    except Exception as e:
        logger.warning(f"[DeepInsight] bloom_taxonomy failed: {e}")
    
    try:
        report['frameworks']['self_determination'] = {
            'name': '自我决定理论',
            'scholar': 'Deci & Ryan (1985)',
            'metrics': compute_sdt_metrics(activities, interval_sec),
        }
    except Exception as e:
        logger.warning(f"[DeepInsight] self_determination failed: {e}")
    
    try:
        report['frameworks']['ultradian_rhythm'] = {
            'name': '超日节律',
            'scholar': 'Rossi (1991)',
            'metrics': compute_ultradian_metrics(activities, interval_sec),
        }
    except Exception as e:
        logger.warning(f"[DeepInsight] ultradian_rhythm failed: {e}")
    
    try:
        report['frameworks']['deep_work'] = {
            'name': '深度工作',
            'scholar': 'Newport (2016)',
            'metrics': compute_deep_work_metrics(activities, interval_sec),
        }
    except Exception as e:
        logger.warning(f"[DeepInsight] deep_work failed: {e}")
    
    try:
        report['frameworks']['structural_holes'] = {
            'name': '结构洞与社会资本',
            'scholar': 'Burt (1992)',
            'metrics': compute_structural_holes_metrics(activities, interval_sec),
        }
    except Exception as e:
        logger.warning(f"[DeepInsight] structural_holes failed: {e}")
    
    try:
        report['frameworks']['zpd'] = {
            'name': '最近发展区',
            'scholar': 'Vygotsky (1978)',
            'metrics': compute_zpd_metrics(activities, interval_sec, history_activities),
        }
    except Exception as e:
        logger.warning(f"[DeepInsight] zpd failed: {e}")
    
    try:
        report['frameworks']['habit_loop'] = {
            'name': '习惯回路',
            'scholar': 'Duhigg/Fogg/Clear',
            'metrics': compute_habit_metrics(activities, interval_sec, daily_summaries),
        }
    except Exception as e:
        logger.warning(f"[DeepInsight] habit_loop failed: {e}")
    
    try:
        report['frameworks']['psychological_capital'] = {
            'name': '心理资本',
            'scholar': 'Luthans (2007)',
            'metrics': compute_psycap_metrics(activities, interval_sec),
        }
    except Exception as e:
        logger.warning(f"[DeepInsight] psychological_capital failed: {e}")
    
    # ─── 生成综合摘要 ────────────────────────────────────────
    report['summary'] = _generate_summary(report['frameworks'])
    
    return report


def _generate_summary(frameworks):
    """从各框架指标中提取关键发现，生成结构化摘要"""
    findings = []
    
    # 心流
    flow = frameworks.get('flow_theory', {}).get('metrics', {})
    if flow.get('flow_index', 0) >= 60:
        findings.append({'dimension': '心流', 'verdict': 'positive', 'detail': f"心流指数{flow['flow_index']}，{flow['flow_minutes']}分钟深度沉浸"})
    elif flow.get('switch_count', 0) > 8:
        findings.append({'dimension': '心流', 'verdict': 'negative', 'detail': f"切换{flow['switch_count']}次，注意力碎片化"})
    
    # 布鲁姆
    bloom = frameworks.get('bloom_taxonomy', {}).get('metrics', {})
    if bloom.get('cognitive_depth', 0) >= 4:
        findings.append({'dimension': '认知深度', 'verdict': 'positive', 'detail': f"认知深度{bloom['cognitive_depth']}/6，高阶思维{bloom.get('higher_order_ratio',0):.0%}"})
    elif bloom.get('cognitive_depth', 0) < 2.5:
        findings.append({'dimension': '认知深度', 'verdict': 'negative', 'detail': f"认知深度{bloom['cognitive_depth']}/6，停留在{bloom.get('dominant_level_name','低阶')}"})
    
    # 深度工作
    dw = frameworks.get('deep_work', {}).get('metrics', {})
    if dw.get('deep_work_ratio', 0) >= 0.5:
        findings.append({'dimension': '深度工作', 'verdict': 'positive', 'detail': f"深度工作比{dw['deep_work_ratio']:.0%}"})
    elif dw.get('shallow_work_ratio', 0) > 0.6:
        findings.append({'dimension': '深度工作', 'verdict': 'negative', 'detail': f"浅层工作占{dw['shallow_work_ratio']:.0%}"})
    
    # 刻意练习
    dp = frameworks.get('deliberate_practice', {}).get('metrics', {})
    if dp.get('deliberate_ratio', 0) >= 0.3:
        findings.append({'dimension': '刻意练习', 'verdict': 'positive', 'detail': f"学习区占比{dp['deliberate_ratio']:.0%}"})
    elif dp.get('comfort_zone_ratio', 0) > 0.7:
        findings.append({'dimension': '刻意练习', 'verdict': 'negative', 'detail': f"舒适区占比{dp['comfort_zone_ratio']:.0%}，成长受限"})
    
    # 心理资本
    psycap = frameworks.get('psychological_capital', {}).get('metrics', {})
    if psycap.get('psycap_index', 0) >= 70:
        findings.append({'dimension': '心理资本', 'verdict': 'positive', 'detail': f"PsyCap指数{psycap['psycap_index']}"})
    
    # 内在动机
    sdt = frameworks.get('self_determination', {}).get('metrics', {})
    if sdt.get('intrinsic_motivation_index', 0) >= 70:
        findings.append({'dimension': '内在动机', 'verdict': 'positive', 'detail': f"内在动机指数{sdt['intrinsic_motivation_index']}"})
    elif sdt.get('autonomy_score', 0) < 40:
        findings.append({'dimension': '内在动机', 'verdict': 'negative', 'detail': f"自主性仅{sdt['autonomy_score']}，外部驱动为主"})
    
    # 如果没发现特别的，给中性总结
    if not findings:
        findings.append({'dimension': '综合', 'verdict': 'neutral', 'detail': '数据量不足或模式均匀，无法提取显著特征'})
    
    positive = sum(1 for f in findings if f['verdict'] == 'positive')
    negative = sum(1 for f in findings if f['verdict'] == 'negative')
    
    return {
        'findings': findings,
        'positive_count': positive,
        'negative_count': negative,
        'overall': 'positive' if positive > negative else ('negative' if negative > positive else 'balanced'),
    }


# ─── 生成 AI 提示词中的结构化知识注入 ────────────────────────
def build_deep_insight_context(activities, interval_sec=60, history_activities=None):
    """
    生成结构化的深度洞察上下文，注入到 AI 提示词中。
    这不是改提示词——而是把量化计算的结果以结构化方式传达给AI。
    """
    report = generate_deep_insight_report(activities, interval_sec, history_activities)
    
    if report.get('status') != 'ok':
        return ""
    
    # 格式化为结构化文本
    lines = ["\n━━━ DeepInsight 学术框架分析 ━━━", ""]
    
    for fw_id, fw_data in report.get('frameworks', {}).items():
        fw_name = fw_data.get('name', fw_id)
        scholar = fw_data.get('scholar', '')
        metrics = fw_data.get('metrics', {})
        
        lines.append(f"【{fw_name}】({scholar})")
        
        for key, value in metrics.items():
            if isinstance(value, dict):
                continue  # 跳过嵌套详情
            if isinstance(value, list) and len(value) > 3:
                continue  # 跳过长列表
            if isinstance(value, float):
                lines.append(f"  {key}: {value:.2f}")
            else:
                lines.append(f"  {key}: {value}")
        lines.append("")
    
    # 摘要
    summary = report.get('summary', {})
    if summary:
        lines.append("━━━ 综合发现 ━━━")
        for finding in summary.get('findings', []):
            icon = '+' if finding['verdict'] == 'positive' else '-' if finding['verdict'] == 'negative' else '='
            lines.append(f"  [{icon}] {finding['dimension']}: {finding['detail']}")
    
    lines.append("")
    lines.append("要求：以上为基于学术框架的量化分析结果，请在解读时引用对应理论和学者，给出有深度的洞见和建议。不要泛泛而谈，要结合具体数据。")
    
    return "\n".join(lines)
