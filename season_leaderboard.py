"""赛季排行榜服务 — 基于匿名 benchmark 的群组对比

隐私优先设计：
- 所有"同行"用户由行业基准百分位数据合成，不含任何真实用户身份
- 群组成员仅展示匿名名（anonymous_id 前 8 位 + 群组内昵称）
- 排名基于本地数据 + 匿名 benchmark 数据，不上传用户真实数据到服务器
- 用户可选择是否参与匿名对比（submit_anonymous_score）
"""
import hashlib
import logging
import random
from datetime import date, datetime, timedelta
from typing import Optional

import benchmark
import db
import growth_service

logger = logging.getLogger(__name__)

# ── 匿名名生成池（用于合成同行用户）──
_ANON_ADJ = ['专注的', '高效的', '深邃的', '敏捷的', '稳健的', '灵动的', '坚定的', '沉静的',
             '活跃的', '睿智的', '勤奋的', '从容的', '炽热的', '清醒的', '执着的', '明朗的']
_ANON_NOUN = ['探索者', '行者', '匠人', '学者', '先锋', '守望者', '追梦人', '构建师',
              '旅人', '思考者', '实践者', '修行者', '攀登者', '航海家', '解码者', '炼金师']

# 分数区间（用于分布直方图）
_SCORE_BINS = [
    (0, 20, '0-20'),
    (20, 40, '20-40'),
    (40, 60, '40-60'),
    (60, 75, '60-75'),
    (75, 85, '75-85'),
    (85, 95, '85-95'),
    (95, 101, '95-100'),
]

# 合成同行数量（基于行业基准百分位，确保排行榜有足够参照系）
_PEER_COUNT = 49  # 合成 49 个 + 用户自己 = 50 人榜单池


def _parse_month(month: Optional[str]) -> tuple[str, date, date]:
    """解析 YYYYMM → (month_key, start_date, end_date)"""
    today = date.today()
    if not month:
        month = today.strftime('%Y%m')
    try:
        year = int(month[:4])
        m = int(month[4:6])
        start = date(year, m, 1)
        if m == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, m + 1, 1) - timedelta(days=1)
    except (ValueError, IndexError):
        month = today.strftime('%Y%m')
        start = today.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return month, start, end


def _compute_monthly_metrics(month_key: str, start: date, end: date) -> dict:
    """计算用户本月核心指标（基于本地数据）

    返回: {
        productivity: float,        # 月均生产力分数 (0-100)
        exp: int,                   # 本月获得经验值
        focus_min: int,             # 本月专注总分钟数
        habit_streak: int,          # 本月最长习惯连续天数
        deep_work_min: int,         # 本月深度工作分钟数
        learning_min: int,          # 本月学习分钟数
    }
    """
    result = {
        'productivity': 0.0, 'exp': 0, 'focus_min': 0,
        'habit_streak': 0, 'deep_work_min': 0, 'learning_min': 0,
    }
    try:
        start_str = start.isoformat()
        end_str = end.isoformat()
        with db.get_conn() as conn:
            # 1. 逐日生产力分数求平均
            rows = conn.execute(
                "SELECT score FROM productivity_scores WHERE date BETWEEN ? AND ?",
                (start_str, end_str),
            ).fetchall()
            if rows:
                avg_score = sum(r['score'] for r in rows) / len(rows)
                result['productivity'] = round(avg_score, 1)
            else:
                # 无记录时按 activities 实时计算最近几日
                cur = start
                scores = []
                today = date.today()
                while cur <= end and cur <= today:
                    try:
                        r = growth_service.compute_productivity_score(cur.isoformat())
                        scores.append(r.get('score', 0))
                    except Exception:
                        pass
                    cur += timedelta(days=1)
                if scores:
                    result['productivity'] = round(sum(scores) / len(scores), 1)

            # 2. 本月经验值（从 growth_log）
            exp_row = conn.execute(
                "SELECT COALESCE(SUM(exp_amount), 0) as total FROM growth_log "
                "WHERE date(created_at) BETWEEN ? AND ?",
                (start_str, end_str),
            ).fetchone()
            result['exp'] = int(exp_row['total']) if exp_row else 0

            # 3. 本月专注总分钟数 + 深度/学习分钟（从 pomodoro_sessions）
            pomo_row = conn.execute(
                "SELECT COALESCE(SUM(duration_min), 0) as focus, "
                "COALESCE(SUM(CASE WHEN category IN ('编程','写作','设计','开发','文档','测试') THEN duration_min ELSE 0 END), 0) as deep, "
                "COALESCE(SUM(CASE WHEN category IN ('学习','阅读') THEN duration_min ELSE 0 END), 0) as learning "
                "FROM pomodoro_sessions WHERE status='completed' AND date(start_time) BETWEEN ? AND ?",
                (start_str, end_str),
            ).fetchone()
            if pomo_row:
                result['focus_min'] = int(pomo_row['focus'] or 0)
                result['deep_work_min'] = int(pomo_row['deep'] or 0)
                result['learning_min'] = int(pomo_row['learning'] or 0)

            # 4. 本月最长习惯连续天数（从 habit_logs）
            #    简化：统计本月内打卡天数最多的习惯的连续天数
            habit_rows = conn.execute(
                "SELECT habit_id, date(log_date) as d FROM habit_logs "
                "WHERE date(log_date) BETWEEN ? AND ? ORDER BY habit_id, d",
                (start_str, end_str),
            ).fetchall()
            if habit_rows:
                # 按 habit_id 分组计算最长连续
                from collections import defaultdict
                by_habit = defaultdict(list)
                for r in habit_rows:
                    by_habit[r['habit_id']].append(r['d'])
                max_streak = 0
                for hid, days in by_habit.items():
                    days = sorted(set(days))
                    cur_streak = 1
                    for i in range(1, len(days)):
                        prev = datetime.strptime(days[i - 1], '%Y-%m-%d').date()
                        curr = datetime.strptime(days[i], '%Y-%m-%d').date()
                        if (curr - prev).days == 1:
                            cur_streak += 1
                        else:
                            max_streak = max(max_streak, cur_streak)
                            cur_streak = 1
                    max_streak = max(max_streak, cur_streak)
                result['habit_streak'] = max_streak
    except Exception as e:
        logger.warning(f"计算月度指标失败: {e}")
    return result


def _metric_value(metrics: dict, metric: str) -> float:
    """从 metrics 字典提取指定指标的归一化分数 (0-100)"""
    if metric == 'productivity':
        return float(metrics.get('productivity', 0))
    if metric == 'exp':
        # 经验值归一化：每月 5000 exp ≈ 满分
        return min(100.0, float(metrics.get('exp', 0)) / 50.0)
    if metric == 'habit_streak':
        # 连续 30 天 = 满分
        return min(100.0, float(metrics.get('habit_streak', 0)) / 30.0 * 100)
    if metric == 'focus_min':
        # 每月 60 小时 = 3600 分钟 = 满分
        return min(100.0, float(metrics.get('focus_min', 0)) / 36.0)
    return float(metrics.get('productivity', 0))


def _metric_label(metric: str) -> str:
    return {
        'productivity': '生产力分数',
        'exp': '经验值',
        'habit_streak': '习惯连续',
        'focus_min': '专注时长',
    }.get(metric, '生产力分数')


def _generate_anonymous_peers(occupation: str, metric: str, count: int = _PEER_COUNT) -> list[dict]:
    """基于行业基准百分位合成匿名同行用户

    隐私说明：这些用户并非真实用户，而是根据 benchmark.py 中行业基准数据
    （p25/p50/p75/p90）合成的虚拟参照点，确保排行榜始终有意义的对比群体。
    每个合成用户的 anonymous_name 和 avatar_seed 由确定性哈希生成，保持稳定。
    """
    bench = benchmark.BENCHMARKS.get(occupation, benchmark.BENCHMARKS['general'])
    # 根据 metric 选择基准数据
    if metric == 'focus_min':
        # 月度专注时长 ≈ 日均 * 30，再归一化到 0-100（36h=满格）
        pcts = bench['daily_focus_minutes']
        base_vals = {'p25': pcts['p25'] * 30 / 36, 'p50': pcts['p50'] * 30 / 36,
                     'p75': pcts['p75'] * 30 / 36, 'p90': pcts['p90'] * 30 / 36}
    elif metric == 'habit_streak':
        pcts = bench['streak_days']
        base_vals = {'p25': pcts['p25'] / 30 * 100, 'p50': pcts['p50'] / 30 * 100,
                     'p75': pcts['p75'] / 30 * 100, 'p90': pcts['p90'] / 30 * 100}
    elif metric == 'exp':
        base_vals = {'p25': 30, 'p50': 50, 'p75': 75, 'p90': 90}
    else:  # productivity
        base_vals = {'p25': 35, 'p50': 55, 'p75': 72, 'p90': 85}

    # 在百分位之间生成正态分布的分数
    rng = random.Random(hash(occupation + metric) & 0xFFFFFFFF)
    peers = []
    # 定义分段：每个百分位区间内生成一定数量的用户
    segments = [
        (0, base_vals['p25'], 0.25),        # 后 25%
        (base_vals['p25'], base_vals['p50'], 0.25),
        (base_vals['p50'], base_vals['p75'], 0.25),
        (base_vals['p75'], 100, 0.25),      # 前 25%
    ]
    for seg_idx, (lo, hi, ratio) in enumerate(segments):
        seg_count = max(1, int(count * ratio))
        for i in range(seg_count):
            # 在区间内均匀扰动
            mid = (lo + hi) / 2
            spread = (hi - lo) / 2 if hi > lo else 5
            score = mid + rng.uniform(-spread, spread) * 0.8
            score = max(0, min(100, score))
            # 确定性生成匿名名和头像种子
            seed_str = f"{occupation}:{metric}:{seg_idx}:{i}"
            h = hashlib.md5(seed_str.encode()).hexdigest()
            adj = _ANON_ADJ[int(h[:2], 16) % len(_ANON_ADJ)]
            noun = _ANON_NOUN[int(h[2:4], 16) % len(_ANON_NOUN)]
            peers.append({
                'score': round(score, 1),
                'anonymous_name': f"{adj}{noun}",
                'avatar_seed': h[:8],
                'is_me': False,
                'is_synthetic': True,
            })
    return peers


def _build_distribution(scores: list[float], my_score: float) -> list[dict]:
    """构建分数分布直方图"""
    distribution = []
    for lo, hi, label in _SCORE_BINS:
        count = sum(1 for s in scores if lo <= s < hi)
        distribution.append({
            'range': label,
            'count': count,
            'is_mine': lo <= my_score < hi,
        })
    return distribution


def _get_season_goals_progress(month_key: str) -> list[dict]:
    """获取赛季成就进度（复用 achievements 模块）"""
    try:
        # 懒加载：避免 routes 包循环导入
        from routes.achievements import _get_or_create_season, _compute_season_progress
        with db.get_conn() as conn:
            season = _get_or_create_season(conn, month_key)
            achs = _compute_season_progress(
                conn, month_key, season['start_date'], season['end_date']
            )
        return [{
            'key': a['key'],
            'name': a['name'],
            'my_progress': a['current'],
            'target': a['target'],
            'completed': a['unlocked'],
        } for a in achs]
    except Exception as e:
        logger.warning(f"获取赛季成就进度失败: {e}")
        return []


def get_season_leaderboard(month: Optional[str] = None, metric: str = 'productivity') -> dict:
    """获取赛季排行榜

    - month: YYYYMM，默认当月
    - metric: productivity/exp/habit_streak/focus_min
    返回: {
      my_rank: int,
      my_score: float,
      total_users: int,
      percentile: float,
      top_users: [{rank, score, anonymous_name, avatar_seed, is_me}],
      my_history: [{month, rank, score}],
      distribution: [{range, count, is_mine}],
      season_goals: [{key, name, my_progress, target, completed}],
    }
    """
    month_key, start, end = _parse_month(month)

    # 1. 计算用户本月指标
    my_metrics = _compute_monthly_metrics(month_key, start, end)
    my_score = _metric_value(my_metrics, metric)

    # 2. 获取用户职业配置
    try:
        profile = benchmark.get_profile()
        occupation = profile.get('occupation', 'general')
    except Exception:
        occupation = 'general'

    # 3. 合成匿名同行
    peers = _generate_anonymous_peers(occupation, metric)

    # 4. 尝试加入群组成员的真实匿名分数（如果有群组）
    group_entries = []
    try:
        gp = benchmark.get_profile()
        group_code = gp.get('group_code', '')
        anon_id = gp.get('anonymous_id', '')
        if group_code:
            lb = benchmark.get_group_leaderboard(group_code)
            if lb and lb.get('leaderboard'):
                for m in lb['leaderboard']:
                    if m.get('anonymous_id') == anon_id[:8]:
                        continue  # 跳过自己
                    # 群组成员分数映射到当前 metric
                    m_score = _metric_value({
                        'productivity': m.get('daily_focus_minutes', 0) / 4.8,  # 粗略映射
                        'focus_min': m.get('daily_focus_minutes', 0) * 30,
                        'habit_streak': m.get('streak_days', 0),
                        'exp': m.get('score', 0),
                    }, metric)
                    group_entries.append({
                        'score': round(m_score, 1),
                        'anonymous_name': m.get('name', '匿名')[:12],
                        'avatar_seed': m.get('anonymous_id', '00000000')[:8],
                        'is_me': False,
                        'is_synthetic': False,
                    })
    except Exception as e:
        logger.debug(f"群组成员分数获取失败（可忽略）: {e}")

    # 5. 合并所有用户（自己 + 群组成员 + 合成同行）
    all_users = peers + group_entries
    my_entry = {
        'score': my_score,
        'anonymous_name': '我',
        'avatar_seed': 'me',
        'is_me': True,
        'is_synthetic': False,
    }
    all_users.append(my_entry)

    # 6. 排序并计算排名
    all_users.sort(key=lambda x: x['score'], reverse=True)
    total_users = len(all_users)
    my_rank = next((i + 1 for i, u in enumerate(all_users) if u['is_me']), total_users)
    percentile = round((1 - my_rank / total_users) * 100, 1) if total_users > 0 else 0

    # 7. Top 10（含我自己若在前 10）
    top_users = []
    for i, u in enumerate(all_users[:10]):
        top_users.append({
            'rank': i + 1,
            'score': u['score'],
            'anonymous_name': u['anonymous_name'],
            'avatar_seed': u['avatar_seed'],
            'is_me': u['is_me'],
        })
    # 如果我不在前 10，追加我的位置
    if my_rank > 10:
        top_users.append({
            'rank': my_rank,
            'score': my_score,
            'anonymous_name': '我',
            'avatar_seed': 'me',
            'is_me': True,
        })

    # 8. 分数分布
    all_scores = [u['score'] for u in all_users]
    distribution = _build_distribution(all_scores, my_score)

    # 9. 赛季成就进度
    season_goals = _get_season_goals_progress(month_key)

    # 10. 我的历史排名
    my_history = get_my_season_history(months=6)

    return {
        'month': month_key,
        'metric': metric,
        'metric_label': _metric_label(metric),
        'my_rank': my_rank,
        'my_score': round(my_score, 1),
        'total_users': total_users,
        'percentile': percentile,
        'top_users': top_users,
        'my_history': my_history,
        'distribution': distribution,
        'season_goals': season_goals,
        'occupation': occupation,
        # 隐私声明
        'privacy_note': '排行榜中的同行由行业基准数据合成，不含真实用户身份。群组成员仅展示匿名昵称。',
    }


def submit_anonymous_score(month: Optional[str] = None) -> dict:
    """提交匿名分数到 benchmark 服务（更新群组中的自己指标）

    隐私说明：仅上传脱敏聚合数据（月均生产力分数、专注时长等），不含活动内容、应用名、窗口标题。
    """
    month_key, start, end = _parse_month(month)
    metrics = _compute_monthly_metrics(month_key, start, end)

    # 构造匿名指标包（与 benchmark 模块格式兼容）
    anon_metrics = {
        'updated_at': datetime.now().isoformat(),
        'daily_focus_minutes': round(metrics['focus_min'] / 30.0, 1),  # 月均→日均
        'deep_work_ratio': round(metrics['deep_work_min'] / max(metrics['focus_min'], 1), 3),
        'meeting_ratio': 0.0,
        'distraction_ratio': 0.0,
        'streak_days': metrics['habit_streak'],
        'monthly_productivity': metrics['productivity'],
        'monthly_exp': metrics['exp'],
        'month': month_key,
    }

    try:
        benchmark.update_my_metrics_in_group(anon_metrics)
    except Exception as e:
        logger.warning(f"提交匿名分数到群组失败: {e}")

    return {
        'ok': True,
        'month': month_key,
        'submitted_metrics': anon_metrics,
        'message': '已提交匿名分数到群组（仅含脱敏聚合数据）',
    }


def get_my_season_history(months: int = 6) -> list[dict]:
    """获取最近 N 个月赛季历史排名"""
    months = max(1, min(months, 24))
    today = date.today()
    history = []
    try:
        profile = benchmark.get_profile()
        occupation = profile.get('occupation', 'general')
    except Exception:
        occupation = 'general'

    for i in range(months):
        # 从当月向前推
        d = today - timedelta(days=i * 30)
        month_key = d.strftime('%Y%m')
        m, start, end = _parse_month(month_key)
        my_metrics = _compute_monthly_metrics(month_key, start, end)
        my_score = _metric_value(my_metrics, 'productivity')
        # 用合成同行的分数估算历史排名
        peers = _generate_anonymous_peers(occupation, 'productivity', 29)
        all_scores = [p['score'] for p in peers] + [my_score]
        all_scores.sort(reverse=True)
        rank = next((i + 1 for i, s in enumerate(all_scores) if abs(s - my_score) < 0.01), len(all_scores))
        history.append({
            'month': month_key,
            'rank': rank,
            'score': round(my_score, 1),
            'total_users': len(all_scores),
        })
    history.reverse()
    return history


def get_season_summary(month: Optional[str] = None) -> dict:
    """赛季总结

    - 本月排名变化（vs 上月）
    - 超越的用户百分比
    - 各维度得分对比（vs 群组平均）
    - 赛季成就完成情况
    """
    month_key, start, end = _parse_month(month)
    lb = get_season_leaderboard(month_key, 'productivity')

    # 上月排名
    prev_month_date = start - timedelta(days=1)
    prev_month_key = prev_month_date.strftime('%Y%m')
    prev_lb = get_season_leaderboard(prev_month_key, 'productivity')

    rank_change = prev_lb['my_rank'] - lb['my_rank']  # 正数=进步

    # 各维度得分对比（vs 行业基准 p50）
    my_metrics = _compute_monthly_metrics(month_key, start, end)
    try:
        occupation = benchmark.get_profile().get('occupation', 'general')
    except Exception:
        occupation = 'general'
    bench = benchmark.BENCHMARKS.get(occupation, benchmark.BENCHMARKS['general'])

    # 六维对比：深度工作、学习、专注时长、习惯连续、生产力、经验
    dimensions = [
        {
            'key': 'deep_work',
            'label': '深度工作',
            'my_value': round(my_metrics['deep_work_min'] / 60.0, 1),  # 小时
            'unit': '小时',
            'group_avg': round(bench['daily_focus_minutes']['p50'] * bench['deep_work_ratio']['p50'] * 30 / 60, 1),
        },
        {
            'key': 'learning',
            'label': '学习输入',
            'my_value': round(my_metrics['learning_min'] / 60.0, 1),
            'unit': '小时',
            'group_avg': round(bench['daily_focus_minutes']['p50'] * 0.15 * 30 / 60, 1),
        },
        {
            'key': 'focus',
            'label': '专注时长',
            'my_value': round(my_metrics['focus_min'] / 60.0, 1),
            'unit': '小时',
            'group_avg': round(bench['daily_focus_minutes']['p50'] * 30 / 60, 1),
        },
        {
            'key': 'habit_streak',
            'label': '习惯连续',
            'my_value': my_metrics['habit_streak'],
            'unit': '天',
            'group_avg': bench['streak_days']['p50'],
        },
        {
            'key': 'productivity',
            'label': '生产力',
            'my_value': my_metrics['productivity'],
            'unit': '分',
            'group_avg': 55,
        },
        {
            'key': 'exp',
            'label': '经验值',
            'my_value': my_metrics['exp'],
            'unit': 'XP',
            'group_avg': 2500,
        },
    ]

    # 赛季成就完成情况
    goals_completed = sum(1 for g in lb['season_goals'] if g['completed'])
    goals_total = len(lb['season_goals'])

    return {
        'month': month_key,
        'my_rank': lb['my_rank'],
        'my_score': lb['my_score'],
        'total_users': lb['total_users'],
        'percentile': lb['percentile'],
        'rank_change': rank_change,  # 正数=排名上升
        'prev_rank': prev_lb['my_rank'],
        'beaten_percent': lb['percentile'],
        'dimensions': dimensions,
        'goals_completed': goals_completed,
        'goals_total': goals_total,
        'season_goals': lb['season_goals'],
        'occupation': occupation,
        'summary_text': _build_summary_text(lb, rank_change, goals_completed, goals_total),
    }


def _build_summary_text(lb: dict, rank_change: int, goals_completed: int, goals_total: int) -> str:
    """生成赛季总结文字"""
    parts = []
    if lb['percentile'] >= 75:
        parts.append(f"本月表现优异，超过了 {lb['percentile']:.0f}% 的同行")
    elif lb['percentile'] >= 50:
        parts.append(f"本月处于中上游，超过了 {lb['percentile']:.0f}% 的同行")
    else:
        parts.append(f"本月仍有提升空间，超过了 {lb['percentile']:.0f}% 的同行")

    if rank_change > 0:
        parts.append(f"排名较上月上升 {rank_change} 位")
    elif rank_change < 0:
        parts.append(f"排名较上月下降 {abs(rank_change)} 位")
    else:
        parts.append("排名与上月持平")

    if goals_completed > 0:
        parts.append(f"完成 {goals_completed}/{goals_total} 项赛季目标")

    return "，".join(parts) + "。"
