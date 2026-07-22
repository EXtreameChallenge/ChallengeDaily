"""
成长系统服务 — V35
经验值计算、等级管理、维度映射、生产力评分、精力曲线
"""
import json
import logging
from datetime import datetime, date, timedelta

import db

logger = logging.getLogger(__name__)

# ── 六维成长维度 ──
DIMENSION_MAP = {
    'deep_think': {'name': '深度思考', 'color': '#2f7cf6', 'emoji': '🧠', 'categories': ['编程', '写作', '设计'], 'base_rate': 70},
    'learning': {'name': '学习输入', 'color': '#34c759', 'emoji': '📚', 'categories': ['学习', '阅读'], 'base_rate': 60},
    'fitness': {'name': '身体能量', 'color': '#ff9500', 'emoji': '💪', 'categories': ['运动'], 'base_rate': 40},
    'social': {'name': '社交协作', 'color': '#af52de', 'emoji': '🤝', 'categories': ['会议', '沟通'], 'base_rate': 50},
    'creative': {'name': '创造输出', 'color': '#ff3b30', 'emoji': '🎨', 'categories': ['视频', '创作'], 'base_rate': 55},
    'recovery': {'name': '恢复充电', 'color': '#5ac8fa', 'emoji': '🧘', 'categories': ['娱乐', '生活', '休息'], 'base_rate': 15},
}

# 分类 → 维度 反向映射（用于自动推断）
_CATEGORY_TO_DIM = {}
for _dk, _dv in DIMENSION_MAP.items():
    for _cat in _dv['categories']:
        _CATEGORY_TO_DIM[_cat] = _dk


def infer_dimension_from_todo(todo_id) -> str:
    """根据 todo 的 category 推断成长维度"""
    try:
        with db.get_conn() as conn:
            row = conn.execute("SELECT category FROM todos WHERE id=?", (todo_id,)).fetchone()
        if row and row['category']:
            return _CATEGORY_TO_DIM.get(row['category'], 'deep_think')
    except Exception:
        pass
    return 'deep_think'


def map_habit_to_dimension(habit_name: str) -> str:
    """根据习惯名称推断维度"""
    name_lower = (habit_name or '').lower()
    if any(k in name_lower for k in ['运动', '跑步', '健身', '锻炼', '游泳', '骑行']):
        return 'fitness'
    if any(k in name_lower for k in ['阅读', '读书', '学习', '课程']):
        return 'learning'
    if any(k in name_lower for k in ['冥想', '休息', '早睡', '睡眠']):
        return 'recovery'
    if any(k in name_lower for k in ['写作', '画画', '创作', '视频']):
        return 'creative'
    if any(k in name_lower for k in ['社交', '沟通', '联系']):
        return 'social'
    return 'deep_think'


def calculate_exp(duration_min: int, dimension_key: str, interrupted_count: int = 0, streak_days: int = 0) -> int:
    """计算经验值
    公式: base_rate * (duration / 25) * quality_mult * streak_mult
    - quality_mult: 无中断=1.0, 每次中断-0.1, 最低0.5
    - streak_mult: 1 + min(streak_days, 30) * 0.02 (最高1.6)
    """
    dim = DIMENSION_MAP.get(dimension_key, DIMENSION_MAP['deep_think'])
    base_rate = dim['base_rate']
    # 时间系数（以25分钟为标准单位）
    time_factor = max(duration_min, 1) / 25.0
    # 质量系数（中断惩罚）
    quality_mult = max(1.0 - interrupted_count * 0.1, 0.5)
    # 连续天数加成
    streak_mult = 1.0 + min(streak_days, 30) * 0.02
    exp = int(base_rate * time_factor * quality_mult * streak_mult)
    return max(exp, 1)


def exp_to_next_level(level: int) -> int:
    """计算升到下一级所需经验"""
    return int(150 + level * 50 + level ** 1.5 * 10)


def get_streak_days() -> int:
    """获取当前连续天数"""
    try:
        with db.get_conn() as conn:
            row = conn.execute("SELECT streak_days FROM growth_profile WHERE id=1").fetchone()
        return row['streak_days'] if row else 0
    except Exception:
        return 0


def award_exp(exp_amount: int, dimension: str, source: str, source_id=None, note: str = '') -> dict:
    """奖励经验值，写入日志并更新 profile（含升级检查）"""
    today_str = date.today().isoformat()
    result = {'exp_awarded': exp_amount, 'leveled_up': False, 'new_level': 1}
    try:
        with db.get_conn() as conn:
            # 确保 profile 存在
            conn.execute(
                "INSERT OR IGNORE INTO growth_profile (id, total_exp, level, current_level_exp, dimensions_json, streak_days, longest_streak, initialized) "
                "VALUES (1, 0, 1, 0, '{}', 0, 0, 0)"
            )
            profile = conn.execute("SELECT * FROM growth_profile WHERE id=1").fetchone()
            streak_days = profile['streak_days'] if profile else 0
            streak_mult = 1.0 + min(streak_days, 30) * 0.02
            # 写入 growth_log
            conn.execute(
                "INSERT INTO growth_log (exp_amount, dimension, source, source_id, quality_mult, streak_mult, note) "
                "VALUES (?,?,?,?,1.0,?,?)",
                (exp_amount, dimension, source, source_id, streak_mult, note)
            )
            # 更新 profile
            total_exp = (profile['total_exp'] if profile else 0) + exp_amount
            current_level_exp = (profile['current_level_exp'] if profile else 0) + exp_amount
            level = profile['level'] if profile else 1
            # 升级检查
            leveled_up = False
            while current_level_exp >= exp_to_next_level(level):
                current_level_exp -= exp_to_next_level(level)
                level += 1
                leveled_up = True
            # 更新维度经验
            dims = json.loads(profile['dimensions_json']) if profile and profile['dimensions_json'] else {}
            dims[dimension] = dims.get(dimension, 0) + exp_amount
            # 更新 streak
            last_active = profile['last_active_date'] if profile else None
            streak = streak_days
            longest = profile['longest_streak'] if profile else 0
            if last_active != today_str:
                yesterday = (date.today() - timedelta(days=1)).isoformat()
                if last_active == yesterday:
                    streak += 1
                elif last_active is None or last_active != today_str:
                    streak = 1
                longest = max(longest, streak)
            conn.execute(
                "UPDATE growth_profile SET total_exp=?, level=?, current_level_exp=?, dimensions_json=?, "
                "streak_days=?, longest_streak=?, last_active_date=?, initialized=1, "
                "updated_at=datetime('now','localtime') WHERE id=1",
                (total_exp, level, current_level_exp, json.dumps(dims, ensure_ascii=False),
                 streak, longest, today_str)
            )
            conn.commit()
            result['leveled_up'] = leveled_up
            result['new_level'] = level
            result['total_exp'] = total_exp
    except Exception as e:
        logger.warning(f"award_exp 失败: {e}")
    return result


def get_profile() -> dict:
    """返回完整成长数据"""
    try:
        with db.get_conn() as conn:
            row = conn.execute("SELECT * FROM growth_profile WHERE id=1").fetchone()
        if not row:
            return {
                'total_exp': 0, 'level': 1, 'current_level_exp': 0,
                'exp_to_next': exp_to_next_level(1), 'dimensions': {},
                'streak_days': 0, 'longest_streak': 0, 'initialized': False,
                'dimension_map': DIMENSION_MAP,
            }
        dims = json.loads(row['dimensions_json'] or '{}')
        return {
            'total_exp': row['total_exp'],
            'level': row['level'],
            'current_level_exp': row['current_level_exp'],
            'exp_to_next': exp_to_next_level(row['level']),
            'dimensions': dims,
            'streak_days': row['streak_days'],
            'longest_streak': row['longest_streak'],
            'last_active_date': row['last_active_date'],
            'initialized': bool(row['initialized']),
            'dimension_map': DIMENSION_MAP,
        }
    except Exception as e:
        logger.warning(f"get_profile 失败: {e}")
        return {'total_exp': 0, 'level': 1, 'current_level_exp': 0,
                'exp_to_next': exp_to_next_level(1), 'dimensions': {},
                'streak_days': 0, 'longest_streak': 0, 'initialized': False,
                'dimension_map': DIMENSION_MAP}


def get_log(days: int = 7) -> list:
    """返回近期经验记录"""
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM growth_log WHERE created_at >= ? ORDER BY created_at DESC LIMIT 200",
                (cutoff,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"get_log 失败: {e}")
        return []


def compute_productivity_score(target_date: str = None) -> dict:
    """从 activities 表计算当日生产力分数"""
    if not target_date:
        target_date = date.today().isoformat()
    result = {
        'date': target_date, 'score': 0, 'deep_work_min': 0,
        'learning_min': 0, 'exercise_min': 0,
        'distraction_count': 0, 'total_active_min': 0,
    }
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT category, COALESCE(SUM(duration_min),0) as total "
                "FROM activities WHERE date(start_time)=? GROUP BY category",
                (target_date,)
            ).fetchall()
            cat_map = {r['category']: r['total'] for r in rows}
            deep_cats = ['编程', '写作', '设计', '开发']
            learn_cats = ['学习', '阅读']
            exercise_cats = ['运动']
            deep_min = sum(cat_map.get(c, 0) for c in deep_cats)
            learn_min = sum(cat_map.get(c, 0) for c in learn_cats)
            exercise_min = sum(cat_map.get(c, 0) for c in exercise_cats)
            total_min = sum(cat_map.values())
            distract_row = conn.execute(
                "SELECT COALESCE(SUM(interrupted_count),0) as cnt "
                "FROM pomodoro_sessions WHERE date(start_time)=?",
                (target_date,)
            ).fetchone()
            distraction_count = distract_row['cnt'] if distract_row else 0
            score = (
                min(deep_min / 240.0, 1.0) * 40 +
                min(learn_min / 120.0, 1.0) * 25 +
                min(exercise_min / 30.0, 1.0) * 15 +
                min(total_min / 480.0, 1.0) * 10 +
                max(10 - distraction_count * 1.5, 0)
            )
            score = round(min(max(score, 0), 100), 1)
            result.update({
                'score': score, 'deep_work_min': deep_min,
                'learning_min': learn_min, 'exercise_min': exercise_min,
                'distraction_count': distraction_count, 'total_active_min': total_min,
            })
            conn.execute(
                "INSERT OR REPLACE INTO productivity_scores (date, score, deep_work_min, learning_min, exercise_min, distraction_count, total_active_min) "
                "VALUES (?,?,?,?,?,?,?)",
                (target_date, score, deep_min, learn_min, exercise_min, distraction_count, total_min)
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"compute_productivity_score 失败: {e}")
    return result


def compute_energy_curve(days: int = 14) -> list:
    """从 activities 统计12时段（每2小时一段）深度工作占比"""
    curve = []
    try:
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT strftime('%H', start_time) as hour, category, "
                "COALESCE(SUM(duration_min),0) as total "
                "FROM activities WHERE date(start_time) >= ? "
                "GROUP BY hour, category",
                (cutoff,)
            ).fetchall()
        deep_cats = {'编程', '写作', '设计', '开发'}
        slots = {}
        for r in rows:
            try:
                h = int(r['hour'])
            except (TypeError, ValueError):
                continue
            slot_idx = h // 2
            if slot_idx not in slots:
                slots[slot_idx] = {'deep': 0, 'total': 0}
            slots[slot_idx]['total'] += r['total']
            if r['category'] in deep_cats:
                slots[slot_idx]['deep'] += r['total']
        for i in range(12):
            start_h = (i * 2) % 24
            end_h = (start_h + 2) % 24
            s = slots.get(i, {'deep': 0, 'total': 0})
            ratio = round(s['deep'] / s['total'], 2) if s['total'] > 0 else 0
            curve.append({
                'slot': f"{start_h:02d}:00-{end_h:02d}:00",
                'deep_ratio': ratio,
                'total_min': s['total'],
            })
    except Exception as e:
        logger.warning(f"compute_energy_curve 失败: {e}")
    return curve


def initialize_from_history() -> dict:
    """冷启动：回溯 pomodoro_sessions 计算初始等级"""
    result = {'initialized': True, 'total_exp': 0, 'level': 1}
    try:
        with db.get_conn() as conn:
            profile = conn.execute("SELECT initialized FROM growth_profile WHERE id=1").fetchone()
            if profile and profile['initialized']:
                return {'initialized': True, 'skipped': True, 'message': '已初始化'}
            rows = conn.execute(
                "SELECT duration_min, category, interrupted_count FROM pomodoro_sessions WHERE status='completed'"
            ).fetchall()
            total_exp = 0
            dims = {}
            for r in rows:
                dim_key = _CATEGORY_TO_DIM.get(r['category'], 'deep_think')
                exp = calculate_exp(r['duration_min'] or 25, dim_key, r['interrupted_count'] or 0, 0)
                total_exp += exp
                dims[dim_key] = dims.get(dim_key, 0) + exp
            level = 1
            remaining = total_exp
            while remaining >= exp_to_next_level(level):
                remaining -= exp_to_next_level(level)
                level += 1
            conn.execute(
                "INSERT OR REPLACE INTO growth_profile (id, total_exp, level, current_level_exp, dimensions_json, "
                "streak_days, longest_streak, last_active_date, initialized, updated_at) "
                "VALUES (1, ?, ?, ?, ?, 0, 0, ?, 1, datetime('now','localtime'))",
                (total_exp, level, remaining, json.dumps(dims, ensure_ascii=False), date.today().isoformat())
            )
            conn.commit()
            result['total_exp'] = total_exp
            result['level'] = level
    except Exception as e:
        logger.warning(f"initialize_from_history 失败: {e}")
        result['error'] = str(e)
    return result


def update_streak() -> int:
    """检查并更新连续天数"""
    today_str = date.today().isoformat()
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    try:
        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO growth_profile (id, total_exp, level, current_level_exp, dimensions_json, streak_days, longest_streak, initialized) "
                "VALUES (1, 0, 1, 0, '{}', 0, 0, 0)"
            )
            profile = conn.execute("SELECT streak_days, longest_streak, last_active_date FROM growth_profile WHERE id=1").fetchone()
            last_active = profile['last_active_date']
            streak = profile['streak_days']
            longest = profile['longest_streak']
            if last_active == today_str:
                return streak
            if last_active == yesterday_str:
                streak += 1
            else:
                streak = 1
            longest = max(longest, streak)
            conn.execute(
                "UPDATE growth_profile SET streak_days=?, longest_streak=?, last_active_date=?, "
                "updated_at=datetime('now','localtime') WHERE id=1",
                (streak, longest, today_str)
            )
            conn.commit()
            return streak
    except Exception as e:
        logger.warning(f"update_streak 失败: {e}")
        return 0
