"""
P16-1: 生物钟检测 + 个性化问候
基于 14 天活动历史，检测用户的昼夜节律类型（早起鸟 / 夜猫子 / 中间型），
生成个性化问候语和黄金时段建议。

三种类型：
  - early_bird  早起鸟：首次活动常在 7:00 前，上午效率最高
  - night_owl   夜猫子：末次活动常在 23:00 后，晚间效率最高
  - intermediate 中间型：常规作息 8:00-22:00

检测算法：
  1. 取最近 14 天有效活动日（有 ≥10 条记录的日期）
  2. 统计每天的首次活动时间和末次活动时间
  3. 计算首次活动中位数和末次活动中位数
  4. 首次中位数 < 7:00 → 早起鸟
     末次中位数 > 23:00 → 夜猫子
     否则 → 中间型
  5. 同时按各时段的专注时长占比找出"黄金时段"
"""
import logging
from datetime import date, timedelta
from collections import defaultdict
from typing import Optional
import db

logger = logging.getLogger(__name__)

# ── 个性化问候语模板 ──
GREETINGS = {
    "early_bird": {
        "morning": [  # 5-11
            "早起的鸟儿有虫吃！趁着大脑最清醒的黄金时段，把最重要的任务拿下吧~",
            "清晨的专注力是一天中最宝贵的。你已经比别人多赢了两个小时啦！",
            "日出而作的你，上午就是你的主场。冲鸭！",
        ],
        "afternoon": [  # 12-18
            "下午对你来说可能会有些困倦，建议把沟通类任务安排在这个时段。",
            "你的高效期在上午，下午可以处理一些不需要深度思考的事务。",
            "午后的阳光正好，适合做些轻松的整理工作，为明天的冲刺做准备。",
        ],
        "evening": [  # 19-23
            "作为早起型选手，晚上该让大脑休息了。早点睡，明天的黄金时段在等你！",
            "夜晚的你会比上午慢半拍，别硬撑，听听音乐放松一下吧。",
            "今天的战斗力已经用完啦，养精蓄锐，明天继续发光！",
        ],
        "night": [  # 23-5
            "这么晚了还不睡？你是早起鸟体质，熬夜会透支明天的效率哦。快去睡吧！",
        ],
    },
    "night_owl": {
        "morning": [
            "早啊~ 作为夜猫子体质，上午慢慢热身就好，不用给自己太大压力。",
            "你的引擎还在预热中，先处理些轻松的任务，下午才是你的主场。",
            "别急，你的黄金时段在后面。上午做些规划，下午再全力冲刺。",
        ],
        "afternoon": [
            "下午开始进入状态了吧？你的效率曲线正在爬升，保持势头！",
            "午后是你渐入佳境的时候，把需要创造力的任务安排在这里。",
            "你的引擎已经热好了，现在是输出的好时机！",
        ],
        "evening": [
            "晚间是你的黄金时段！大脑最活跃的时候，把最难的任务放在这里就对了。",
            "夜幕降临，你的战斗力才刚刚上线。专注模式全开！",
            "别人犯困的时候你正精神，这就是夜猫子的超能力。尽情发挥吧！",
        ],
        "night": [
            "深夜是你的主场，但也要注意身体哦。再专注一会儿就收工吧~",
            "夜猫子的灵感往往在深夜迸发，但别忘了一定要保证 6 小时睡眠。",
            "夜深了，你的创造力还在巅峰。给自己设个终点线，别通宵哦。",
        ],
    },
    "intermediate": {
        "morning": [
            "早上好！新的一天开始了，精力满格，冲就完事了！",
            "清晨的大脑最清晰，把需要深度思考的任务安排在上午吧。",
            "元气满满的一天从现在开始，今天也要加油鸭！",
        ],
        "afternoon": [
            "午后时光，稍微伸展一下，继续保持节奏~",
            "下午适合处理执行类任务，保持稳定输出就好。",
            "午后容易犯困，喝杯水，走两步，再继续！",
        ],
        "evening": [
            "一天的工作接近尾声，做个收尾和复盘，给自己点个赞。",
            "晚上的时间适合放松和学习，别太拼了。",
            "今天的任务完成得怎么样？无论结果如何，你已经很棒了。",
        ],
        "night": [
            "该休息啦！熬夜对身体不好，明天的效率取决于今晚的睡眠。",
            "夜深了，大脑需要关机重启。快去睡吧，明天见！",
        ],
    },
}

CHRONOTYPE_LABELS = {
    "early_bird": "早起鸟",
    "night_owl": "夜猫子",
    "intermediate": "均衡型",
}

CHRONOTYPE_ICONS = {
    "early_bird": "🐦",
    "night_owl": "🦉",
    "intermediate": "☀️",
}


def _get_time_period(hour: int) -> str:
    """根据小时返回时段名"""
    if 5 <= hour < 12:
        return "morning"
    elif 12 <= hour < 18:
        return "afternoon"
    elif 18 <= hour < 23:
        return "evening"
    else:
        return "night"


def detect_chronotype(days: int = 14) -> dict:
    """检测用户生物钟类型

    返回:
    {
        "type": "early_bird|night_owl|intermediate",
        "label": "早起鸟|夜猫子|均衡型",
        "icon": "🐦|🦉|☀️",
        "first_active_hour": float,    # 首次活动中位数（小时，如 7.5 = 7:30）
        "last_active_hour": float,     # 末次活动中位数（小时）
        "golden_hours": str,           # 黄金时段描述
        "peak_period": str,            # 最高效时段
        "greeting": str,               # 当前时段的个性化问候
        "valid_days": int,             # 有效分析天数
    }
    """
    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    activities = db.get_activities(start, today.isoformat())

    if not activities or len(activities) < 10:
        return _default_chronotype()

    # 按日期分组，统计每天的首末活动时间
    daily_first: dict[str, float] = {}  # date -> hour (float)
    daily_last: dict[str, float] = {}
    # 各时段专注时长（按活动条数 × 间隔估算）
    period_counts: dict[str, int] = defaultdict(int)

    for act in activities:
        ts = act.get("timestamp", "")
        if not ts or len(ts) < 16:
            continue
        try:
            d = ts[:10]
            hour = int(ts[11:13])
            minute = int(ts[14:16]) if len(ts) >= 16 else 0
            hour_float = hour + minute / 60.0
        except (ValueError, IndexError):
            continue

        if d not in daily_first or hour_float < daily_first[d]:
            daily_first[d] = hour_float
        if d not in daily_last or hour_float > daily_last[d]:
            daily_last[d] = hour_float

        cat = act.get("category", "其他")
        if cat != "生活":
            period = _get_time_period(hour)
            period_counts[period] += 1

    valid_days = len(daily_first)
    if valid_days < 3:
        return _default_chronotype()

    # 计算中位数
    first_hours = sorted(daily_first.values())
    last_hours = sorted(daily_last.values())

    def median(arr: list) -> float:
        n = len(arr)
        if n == 0:
            return 0.0
        if n % 2 == 1:
            return arr[n // 2]
        return (arr[n // 2 - 1] + arr[n // 2]) / 2

    first_med = median(first_hours)
    last_med = median(last_hours)

    # 判定类型
    if first_med < 7.0:
        chrono_type = "early_bird"
    elif last_med >= 23.0:
        chrono_type = "night_owl"
    elif first_med < 7.5 and last_med >= 22.5:
        # 首次早 + 末次晚 → 精力旺盛型，归为均衡
        chrono_type = "intermediate"
    else:
        chrono_type = "intermediate"

    # 找出黄金时段（活动条数最多的时段）
    period_labels = {
        "morning": "上午 (8-12)",
        "afternoon": "下午 (12-18)",
        "evening": "晚间 (18-23)",
        "night": "夜间 (23-5)",
    }
    period_short = {
        "morning": "上午",
        "afternoon": "下午",
        "evening": "晚间",
        "night": "夜间",
    }
    best_period = max(period_counts, key=period_counts.get, default="morning")
    peak_period = period_labels.get(best_period, "上午")

    # 生成黄金时段描述
    golden_hours = f"{first_med:.1f} - {last_med:.1f}"

    # 生成个性化问候
    now_hour = date.today()
    import datetime as _dt
    current_hour = _dt.datetime.now().hour
    period = _get_time_period(current_hour)
    greetings_list = GREETINGS.get(chrono_type, GREETINGS["intermediate"]).get(period, [])
    import random
    greeting = random.choice(greetings_list) if greetings_list else "今天也要加油哦！"

    return {
        "type": chrono_type,
        "label": CHRONOTYPE_LABELS.get(chrono_type, "均衡型"),
        "icon": CHRONOTYPE_ICONS.get(chrono_type, "☀️"),
        "first_active_hour": round(first_med, 1),
        "last_active_hour": round(last_med, 1),
        "golden_hours": golden_hours,
        "peak_period": peak_period,
        "peak_period_short": period_short.get(best_period, "上午"),
        "greeting": greeting,
        "valid_days": valid_days,
        "analysis_days": days,
    }


def _default_chronotype() -> dict:
    """数据不足时的默认返回"""
    import datetime as _dt
    current_hour = _dt.datetime.now().hour
    period = _get_time_period(current_hour)
    greetings_list = GREETINGS["intermediate"].get(period, [])
    import random
    return {
        "type": "intermediate",
        "label": "均衡型",
        "icon": "☀️",
        "first_active_hour": 8.0,
        "last_active_hour": 22.0,
        "golden_hours": "8.0 - 22.0",
        "peak_period": "上午 (8-12)",
        "peak_period_short": "上午",
        "greeting": random.choice(greetings_list) if greetings_list else "今天也要加油哦！",
        "valid_days": 0,
        "analysis_days": 14,
    }
