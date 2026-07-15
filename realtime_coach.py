"""
P7-1: AI 行为教练 — 实时行为干预引擎
三层干预：
  1. 轻度提醒：连续摸鱼 15min → 桌面宠物气泡 + 通知
  2. 中度干预：连续摸鱼 30min → 弹窗提示卡
  3. 过劳保护：连续工作 2h 无休息 → 提醒休息
  4. 正念冲浪（Urge Surfing）：打开干扰应用 → 10s 延迟 + 正念语录
设计为无状态查询接口，由前端轮询调用（复用现有采集数据，不额外截图）
"""
import logging
import random
from datetime import datetime, date, timedelta
from typing import Optional
import db
from config import SCREENSHOT_INTERVAL_SEC

logger = logging.getLogger(__name__)

# ── 阈值配置（分钟）──
DISTRACTION_LIGHT_THRESHOLD = 15   # 轻度提醒：连续摸鱼 15 分钟
DISTRACTION_HEAVY_THRESHOLD = 30   # 中度干预：连续摸鱼 30 分钟
OVERWORK_THRESHOLD = 120           # 过劳保护：连续工作 2 小时
FLOW_PROTECT_THRESHOLD = 25        # 心流保护：连续同分类 25 分钟时不打断

# ── 正念语录（Urge Surfing）──
MINDFULNESS_QUOTES = [
    "冲动只是一阵浪，它来了也会走。等 10 秒，它可能就消退了。",
    "你不需要立刻行动。观察一下这个冲动，它在你身体的哪个位置？",
    "每次你选择不立刻屈服于冲动，你就削弱了它的力量。",
    "想象冲动是云朵，你是天空。云飘过来，又飘走了。",
    "深呼吸三次。吸气，呼气，再吸气，再呼气。冲动还在吗？",
    "此刻的你，和 10 秒前的你，已经不同了。",
    "你不需要打败冲动，只需要不和它对抗。让它自然流过。",
    "回想上一次你屈服后的感受。这一次，试试不一样的选择。",
    "10 秒钟，什么都不做。就 10 秒。",
    "你的注意力是你最宝贵的资源。这一刻，你选择把它放在哪里？",
]

# ── 过劳提醒语 ──
OVERWORK_MESSAGES = [
    "你已经连续工作 2 小时了，大脑需要休息才能保持高效。站起来走走？",
    "连续工作太久效率会下降。建议休息 5-10 分钟，喝水、伸展。",
    "研究表明，每 90 分钟休息一次能大幅提升创造力。现在是时候了。",
    "你的身体在提醒你：该休息了。即使只是闭眼 2 分钟也有帮助。",
]

# ── 摸鱼提醒语 ──
DISTRACTION_MESSAGES = [
    "我注意到你已经在「{category}」上花了 {minutes} 分钟了。需要我帮你回到正轨吗？",
    "嗯…你已经摸鱼 {minutes} 分钟啦。要不要深呼吸一下，回到工作？",
    "嘿，{category} 确实很有趣，但你的目标还在等你呢！",
    "已经 {minutes} 分钟了哦。试试番茄钟？25 分钟专注，然后奖励自己。",
]


def get_coaching_status() -> dict:
    """获取当前行为教练状态（前端每 30s 轮询一次）

    返回：
    {
        "distraction_minutes": float,      # 当前连续摸鱼分钟
        "work_minutes": float,             # 当前连续工作分钟
        "current_category": str,           # 当前分类
        "flow_minutes": float,             # 当前心流（连续同分类）分钟
        "alerts": [                        # 待触发的告警列表
            {"type": "distraction_light|distraction_heavy|overwork|flow_protect",
             "message": str, "minutes": float, "category": str}
        ],
        "urge_surfing": {"quote": str} | None,  # 正念冲浪语录（如果需要）
    }
    """
    today_str = date.today().isoformat()
    activities = db.get_activities(today_str, today_str)
    interval_min = SCREENSHOT_INTERVAL_SEC / 60

    if not activities:
        return {
            "distraction_minutes": 0,
            "work_minutes": 0,
            "current_category": "",
            "flow_minutes": 0,
            "alerts": [],
            "urge_surfing": None,
        }

    # 按时间倒序分析最近的连续段
    sorted_acts = sorted(activities, key=lambda a: a["timestamp"], reverse=True)
    latest_cat = sorted_acts[0].get("category", "其他")

    # 计算当前连续段（从最新记录往前，直到分类变化）
    current_streak_cat = latest_cat
    current_streak_count = 0
    for act in sorted_acts:
        if act.get("category", "其他") == current_streak_cat:
            current_streak_count += 1
        else:
            break

    streak_minutes = round(current_streak_count * interval_min, 1)

    # 判断是否在摸鱼（生活类）
    is_distraction = latest_cat == "生活"
    distraction_minutes = streak_minutes if is_distraction else 0

    # 判断是否在连续工作（非生活类）
    work_minutes = streak_minutes if not is_distraction and latest_cat else 0

    # 心流时长（连续同一工作分类）
    flow_minutes = streak_minutes if not is_distraction else 0

    alerts = []

    # 摸鱼告警
    if is_distraction and distraction_minutes >= DISTRACTION_LIGHT_THRESHOLD:
        if distraction_minutes >= DISTRACTION_HEAVY_THRESHOLD:
            alerts.append({
                "type": "distraction_heavy",
                "message": random.choice(DISTRACTION_MESSAGES).format(
                    category=latest_cat, minutes=int(distraction_minutes)
                ),
                "minutes": distraction_minutes,
                "category": latest_cat,
            })
        else:
            alerts.append({
                "type": "distraction_light",
                "message": f"你已经「{latest_cat}」{int(distraction_minutes)}分钟了，要回来工作吗？",
                "minutes": distraction_minutes,
                "category": latest_cat,
            })

    # 过劳告警（连续工作超过 2 小时）
    if work_minutes >= OVERWORK_THRESHOLD:
        alerts.append({
            "type": "overwork",
            "message": random.choice(OVERWORK_MESSAGES),
            "minutes": work_minutes,
            "category": latest_cat,
        })

    # 心流保护（正在心流中，不触发任何打扰）— 仅返回状态，不产生告警
    in_flow = flow_minutes >= FLOW_PROTECT_THRESHOLD and not is_distraction

    # 正念冲浪：当检测到从工作切换到生活类时触发
    urge_surfing = None
    if is_distraction and current_streak_count <= 2:
        # 刚开始摸鱼（1-2 条记录），检查前一条是否是工作
        urge_surfing = {"quote": random.choice(MINDFULNESS_QUOTES)}

    return {
        "distraction_minutes": distraction_minutes,
        "work_minutes": work_minutes,
        "current_category": latest_cat,
        "flow_minutes": flow_minutes,
        "in_flow": in_flow,
        "alerts": alerts,
        "urge_surfing": urge_surfing,
    }


def trigger_alert_notification(alert: dict) -> None:
    """将告警推送到通知系统"""
    try:
        from routes.notifications import add_notification
        ntype_map = {
            "distraction_light": "warning",
            "distraction_heavy": "warning",
            "overwork": "info",
            "flow_protect": "info",
        }
        add_notification(
            title="行为教练提醒",
            body=alert["message"],
            ntype=ntype_map.get(alert["type"], "info"),
        )
    except Exception as e:
        logger.error(f"推送教练通知失败: {e}")


def get_daily_coaching_summary() -> dict:
    """今日行为教练汇总（供日报引用）"""
    today_str = date.today().isoformat()
    activities = db.get_activities(today_str, today_str)
    interval_min = SCREENSHOT_INTERVAL_SEC / 60

    if not activities:
        return {"distraction_count": 0, "longest_focus_min": 0, "flow_sessions": 0}

    sorted_acts = sorted(activities, key=lambda a: a["timestamp"])
    distraction_count = 0
    longest_focus_count = 0
    current_focus_count = 0
    flow_sessions = 0
    prev_cat = None

    for act in sorted_acts:
        cat = act.get("category", "其他")
        if cat == "生活":
            if prev_cat and prev_cat != "生活":
                distraction_count += 1
            current_focus_count = 0
        else:
            current_focus_count += 1
            if current_focus_count > longest_focus_count:
                longest_focus_count = current_focus_count
            # 心流判定：连续 ≥25 分钟（约 25 条记录 if 60s 间隔）
            flow_threshold = int(FLOW_PROTECT_THRESHOLD / interval_min)
            if current_focus_count == flow_threshold:
                flow_sessions += 1
        prev_cat = cat

    return {
        "distraction_count": distraction_count,
        "longest_focus_min": round(longest_focus_count * interval_min, 1),
        "flow_sessions": flow_sessions,
        "total_distraction_min": round(
            sum(1 for a in sorted_acts if a.get("category") == "生活") * interval_min, 1
        ),
    }
