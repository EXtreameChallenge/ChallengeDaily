"""P12-3：情感化设计
1. 低谷关怀：当用户连续多天效率偏低时，推送温暖关怀而非指责
2. 里程碑庆祝：当用户达成重要里程碑（连续打卡/单日深度工作）时，生成庆祝文案
3. 时段问候：根据当前时段（早/中/晚）选择不同语气
"""
import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)


# ── 时段问候语（活泼可爱温馨，不肉麻） ──
_GREETING_BY_PERIOD = {
    "morning":   ["新的一天开始啦~", "早安，今天也加油哦！", "阳光正好，状态在线~"],
    "forenoon":  ["上午专注模式开启~", "趁精神好，把难活儿先啃下来~", "上午的你最有效率~"],
    "noon":      ["中午记得吃饭哦~", "下午茶时间~ 休息一下", "眯一会儿，下午更带劲~"],
    "afternoon": ["下午继续冲鸭~", "下午时光也要元气满满~", "再坚持一下，胜利在望~"],
    "evening":   ["辛苦一天啦~", "晚上别太拼哦~", "今天表现不错，给自己鼓个掌~"],
    "night":     ["夜深了，注意休息~", "熬夜伤身，早点睡哦~", "今天已经够棒了，明天再继续~"],
}


def _current_period() -> str:
    """根据当前小时返回时段标识"""
    h = datetime.now().hour
    if 5 <= h < 9:   return "morning"
    if 9 <= h < 12:  return "forenoon"
    if 12 <= h < 14: return "noon"
    if 14 <= h < 18: return "afternoon"
    if 18 <= h < 23: return "evening"
    return "night"


def _pick(items: list[str]) -> str:
    """安全随机选择（避免 random 在并发场景下的状态问题）"""
    if not items:
        return ""
    import time
    # 用时间戳做简单随机，足够用于文案
    idx = int(time.time() * 1000) % len(items)
    return items[idx]


def _query_recent_efficiency(days: int = 7) -> dict:
    """查询近 N 天的效率指标
    返回: {avg_focus_min, low_days, streak_days, has_data}
    """
    try:
        import db
        today = date.today()
        start = today - timedelta(days=days - 1)
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT date(timestamp) AS d, SUM(interval_sec) AS total_sec "
                "FROM activities "
                "WHERE date(timestamp) BETWEEN ? AND ? "
                "GROUP BY d ORDER BY d",
                (start.isoformat(), today.isoformat()),
            ).fetchall()
        if not rows:
            return {"avg_focus_min": 0, "low_days": 0, "streak_days": 0, "has_data": False}
        # 每日专注分钟数
        daily_min = [(r["total_sec"] or 0) / 60 for r in rows]
        avg_min = sum(daily_min) / len(daily_min) if daily_min else 0
        # 低效日：当日 < 平均的 50%
        low_threshold = max(avg_min * 0.5, 30)
        low_days = sum(1 for m in daily_min if m < low_threshold)
        # 连续打卡天数（从今天向前数）
        streak = 0
        date_set = {r["d"] for r in rows}
        cur = today
        while cur.isoformat() in date_set:
            streak += 1
            cur -= timedelta(days=1)
        return {
            "avg_focus_min": round(avg_min, 1),
            "low_days": low_days,
            "streak_days": streak,
            "has_data": True,
        }
    except Exception as e:
        logger.warning(f"查询近期效率失败(非致命): {e}")
        return {"avg_focus_min": 0, "low_days": 0, "streak_days": 0, "has_data": False}


def build_care_message(report_type: str = "weekly") -> str:
    """构造低谷关怀文案
    - 当近 7 天低效日 ≥ 3 天时触发
    - 文案温暖、鼓励，禁止"效率低"/"有点散"等负面词
    返回 Markdown 段落；无触发条件时返回空串
    """
    try:
        data = _query_recent_efficiency(7)
        if not data["has_data"] or data["streak_days"] < 2:
            return ""
        if data["low_days"] < 3:
            return ""
        period = _current_period()
        greeting = _pick(_GREETING_BY_PERIOD.get(period, ["~"]))
        # 文字堆砌式温暖文案（符合用户偏好）
        msg = (
            "\n---\n\n## 💝 来自 ChallengeDaily 的悄悄话\n\n"
            f"> {greeting}\n"
            "> \n"
            f"> 已经陪你走过 **{data['streak_days']} 天**啦，每一天的相伴都很珍贵。\n"
            "> \n"
            "> 这段时间也许节奏有些起伏，没关系，每个人都有自己的节拍。\n"
            "> \n"
            "> 风会停，雨会歇，明天又是崭新的一天，重新出发就好。\n"
            "> \n"
            "> 无论高峰还是低谷，我都在这里，陪你一起，慢慢变好。 🌱\n"
        )
        return msg
    except Exception as e:
        logger.warning(f"关怀文案生成失败(非致命): {e}")
        return ""


def build_milestone_celebration() -> str:
    """构造里程碑庆祝文案
    触发条件（任一）：
    - 连续打卡 7/14/30/60/100 天
    - 单日深度工作 ≥ 6 小时（仅日报场景）
    返回 Markdown 段落；无触发条件时返回空串
    """
    try:
        data = _query_recent_efficiency(60)
        if not data["has_data"]:
            return ""
        streak = data["streak_days"]
        # 里程碑关卡
        milestones = {7: "一周打卡达成！", 14: "两周坚持达成！", 30: "月度打卡达成！",
                      60: "双月坚持达成！", 100: "百日百天达成！"}
        if streak in milestones:
            title = milestones[streak]
            msg = (
                "\n---\n\n## 🎉 里程碑达成\n\n"
                f"> **{title}**\n"
                "> \n"
                f"> 连续 **{streak} 天** 与 ChallengeDaily 并肩作战，\n"
                "> 这不是简单的数字，而是你对自己承诺的兑现。\n"
                "> \n"
                "> 每一次打开应用、每一份日报、每一段专注时光，\n"
                "> 都在悄悄塑造着更好的你。\n"
                "> \n"
                "> 这份坚持，值得被看见，值得被庆祝。 ✨\n"
            )
            return msg
        # 单日深度工作 ≥ 6 小时
        if data["avg_focus_min"] >= 360:
            msg = (
                "\n---\n\n## 🎉 里程碑达成\n\n"
                "> **深度工作达人**\n"
                "> \n"
                f"> 平均每日专注 **{data['avg_focus_min']:.0f} 分钟**，\n"
                "> 已经超越大多数知识工作者的平均水平。\n"
                "> \n"
                "> 保持这份心流状态，你正在成为更好的自己。 💪\n"
            )
            return msg
        return ""
    except Exception as e:
        logger.warning(f"里程碑文案生成失败(非致命): {e}")
        return ""
