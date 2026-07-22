"""
日程调度服务 — V35
精力曲线分析、AI 日程生成、fallback 排程
"""
import json
import logging
from datetime import datetime, date, timedelta

import db

logger = logging.getLogger(__name__)


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


def fallback_schedule(tasks: list, energy: list) -> list:
    """按优先级排列任务，90分钟工作块+15分钟休息"""
    if not tasks:
        return []

    # 按优先级排序（数字越小优先级越高）
    sorted_tasks = sorted(tasks, key=lambda t: t.get('priority', 3))

    # 找出精力高峰时段（deep_ratio 最高的时段）
    peak_slots = sorted(energy, key=lambda s: s.get('deep_ratio', 0), reverse=True) if energy else []

    schedule = []
    # 默认工作时间从 9:00 开始
    start_minutes = 9 * 60  # 540 = 9:00

    for i, task in enumerate(sorted_tasks):
        # 每个任务分配 90 分钟工作块
        task_start = start_minutes + i * 105  # 90min work + 15min break
        task_end = task_start + 90

        start_str = f"{task_start // 60:02d}:{task_start % 60:02d}"
        end_str = f"{task_end // 60:02d}:{task_end % 60:02d}"

        # 判断是否在高精力时段
        slot_idx = (task_start // 60) // 2
        is_peak = False
        if peak_slots and slot_idx < len(peak_slots):
            is_peak = peak_slots[0].get('deep_ratio', 0) > 0.3 and slot_idx == int(peak_slots[0].get('slot', '00:00-02:00')[:2]) // 2

        schedule.append({
            'task_title': task.get('title', ''),
            'task_id': task.get('id'),
            'start': start_str,
            'end': end_str,
            'duration_min': 90,
            'is_peak_energy': is_peak,
            'type': 'deep_work' if task.get('priority', 3) <= 2 else 'normal',
        })

        # 添加休息块
        if i < len(sorted_tasks) - 1:
            break_start = task_end
            break_end = break_start + 15
            schedule.append({
                'task_title': '休息',
                'task_id': None,
                'start': f"{break_start // 60:02d}:{break_start % 60:02d}",
                'end': f"{break_end // 60:02d}:{break_end % 60:02d}",
                'duration_min': 15,
                'is_peak_energy': False,
                'type': 'break',
            })

    return schedule


def generate_schedule(target_date: str = None) -> dict:
    """生成日程安排：尝试 AI，失败用 fallback"""
    if not target_date:
        target_date = date.today().isoformat()

    result = {
        'date': target_date,
        'schedule': [],
        'energy_curve': [],
        'source': 'fallback',
    }

    # 获取精力曲线
    energy = compute_energy_curve(14)
    result['energy_curve'] = energy

    # 获取未完成任务
    tasks = []
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT id, title, priority, category, estimated_pomodoros, target_min "
                "FROM todos WHERE status != 'completed' AND status != 'deleted' "
                "ORDER BY priority ASC, created_at ASC LIMIT 10"
            ).fetchall()
            tasks = [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"获取任务列表失败: {e}")

    if not tasks:
        result['schedule'] = []
        result['message'] = '没有待完成的任务'
        return result

    # 尝试 AI 生成日程
    ai_schedule = _try_ai_schedule(tasks, energy, target_date)
    if ai_schedule:
        result['schedule'] = ai_schedule
        result['source'] = 'ai'
    else:
        # fallback
        result['schedule'] = fallback_schedule(tasks, energy)
        result['source'] = 'fallback'

    return result


def _try_ai_schedule(tasks: list, energy: list, target_date: str) -> list | None:
    """尝试调用 AI 生成日程，失败返回 None"""
    try:
        from ai_client import _cb_check, _rate_limit_check, _get_client, _cb_record_success, _cb_record_failure
        import config

        if not _cb_check():
            return None
        if not _rate_limit_check("text"):
            return None

        client = _get_client()

        # 构建 prompt
        task_desc = "\n".join([
            f"- {t['title']} (优先级:{t.get('priority', 3)}, 分类:{t.get('category', '开发')}, 预估:{t.get('estimated_pomodoros', 1)}个番茄)"
            for t in tasks
        ])
        energy_desc = "\n".join([
            f"- {s['slot']}: 深度工作占比 {s['deep_ratio']*100:.0f}%"
            for s in energy if s['total_min'] > 0
        ])

        prompt = (
            f"请为 {target_date} 生成一个高效的日程安排。\n\n"
            f"待完成任务：\n{task_desc}\n\n"
            f"历史精力曲线（深度工作占比）：\n{energy_desc}\n\n"
            f"要求：\n"
            f"1. 高优先级任务安排在精力高峰时段\n"
            f"2. 每个工作块90分钟，之间休息15分钟\n"
            f"3. 从9:00开始安排\n"
            f"4. 返回JSON数组，每项包含: task_title, start(HH:MM), end(HH:MM), duration_min, type(deep_work/normal/break)\n"
            f"只返回JSON数组，不要其他文字。"
        )

        response = client.chat.completions.create(
            model=getattr(config, 'AI_MODEL', 'gpt-3.5-turbo'),
            messages=[
                {"role": "system", "content": "你是一个高效时间管理助手，擅长根据精力曲线安排日程。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=2000,
        )

        _cb_record_success()

        content = response.choices[0].message.content.strip()
        # 提取 JSON
        if '```' in content:
            content = content.split('```')[1]
            if content.startswith('json'):
                content = content[4:]
        schedule = json.loads(content)
        if isinstance(schedule, list) and len(schedule) > 0:
            return schedule

    except ImportError:
        logger.debug("ai_client 不可用，使用 fallback 排程")
    except Exception as e:
        logger.warning(f"AI 日程生成失败，使用 fallback: {e}")
        try:
            from ai_client import _cb_record_failure
            _cb_record_failure()
        except Exception:
            pass

    return None
