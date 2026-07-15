"""P12-4：桌面宠物情绪化
基于今日数据计算宠物情绪，让宠物真正"看懂"用户的状态：
- 专注时长 → 心流/专注情绪
- 摸鱼时长 → 摸鱼情绪
- 连续工作无休息 → 过劳情绪
- 夜深还在工作 → 困倦情绪
- 数据空窗 → 悠闲情绪
情绪文案活泼可爱温馨，禁止负面词。
"""
import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)


# 情绪 → 表情 + 气泡消息池（活泼可爱温馨，禁止"效率低"/"有点散"）
MOOD_POOLS = {
    "idle":       ["在吗？陪我发会儿呆~", "今天也要元气满满哦~", "我在这儿陪着你呀", "喵~", "要不要一起开启新的一天？"],
    "focused":    ["专注模式开启！", "加油加油，你超棒的~", "进展不错呢~", "保持节奏，稳稳的~", "效率满满，给你点赞！"],
    "flowing":    ["哇，你进入心流啦！", "不去打扰你，专注就好~", "这个状态太赞了！", "心流中的你最帅~", "深潜中，不打扰~"],
    "distracted": ["嗯…回来工作啦~", "我知道你有更好的选择~", "要不要试试番茄钟？", "摸鱼一时爽，专注更香哦~", "回来啦回来啦~"],
    "overworked": ["该休息啦！", "连续工作太久咯~", "喝杯水吧，身体要紧~", "歇会儿，更高效~", "心疼你三秒钟~"],
    "sleepy":     ["困了吗？", "小憩一下也不错~", "记得早点休息呀~", "熬夜伤身，乖，去睡~", "梦里也在专注呢~"],
    "milestone":  ["哇！达成里程碑啦！", "恭喜你，太厉害啦~", "这份坚持，值得庆祝！", "为你骄傲~", "干得漂亮，给自己鼓个掌！"],
}


def _today_focus_min() -> float:
    """今日累计专注分钟数（所有活动 interval_sec 汇总）"""
    try:
        import db
        today = date.today().isoformat()
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT SUM(interval_sec) AS s FROM activities WHERE date(timestamp) = ?",
                (today,),
            ).fetchone()
        return (row["s"] or 0) / 60
    except Exception:
        return 0


def _today_distraction_min() -> float:
    """今日摸鱼分类分钟数"""
    try:
        import db
        today = date.today().isoformat()
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT SUM(interval_sec) AS s FROM activities "
                "WHERE date(timestamp) = ? AND category IN ('生活', '娱乐', '摸鱼', '社交')",
                (today,),
            ).fetchone()
        return (row["s"] or 0) / 60
    except Exception:
        return 0


def _today_pomodoro_sessions() -> dict:
    """今日番茄会话统计"""
    try:
        import db
        today = date.today().isoformat()
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total, "
                "       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed, "
                "       SUM(interrupted_count) AS distracted "
                "FROM pomodoro_sessions WHERE date(start_time) = ?",
                (today,),
            ).fetchone()
        return {
            "total": row["total"] or 0,
            "completed": row["completed"] or 0,
            "distracted": row["distracted"] or 0,
        }
    except Exception:
        return {"total": 0, "completed": 0, "distracted": 0}


def _streak_days() -> int:
    """连续打卡天数"""
    try:
        import db
        today = date.today()
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT date(timestamp) AS d FROM activities "
                "WHERE date(timestamp) >= ? ORDER BY d DESC",
                ((today - timedelta(days=120)).isoformat(),),
            ).fetchall()
        date_set = {r["d"] for r in rows}
        streak = 0
        cur = today
        while cur.isoformat() in date_set:
            streak += 1
            cur -= timedelta(days=1)
        return streak
    except Exception:
        return 0


def _is_overwork() -> bool:
    """判断是否连续工作无休息（最近 2 小时内无'生活'类活动）"""
    try:
        import db
        now = datetime.now()
        cutoff = (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM activities "
                "WHERE timestamp >= ? AND category IN ('生活', '娱乐', '摸鱼')",
                (cutoff,),
            ).fetchone()
        work_row = conn.execute(
            "SELECT COUNT(*) AS c FROM activities WHERE timestamp >= ?",
            (cutoff,),
        ).fetchone()
        return (work_row["c"] or 0) > 0 and (row["c"] or 0) == 0
    except Exception:
        return False


def _pick(items: list[str]) -> str:
    if not items:
        return ""
    import time
    return items[int(time.time() * 1000) % len(items)]


def compute_pet_mood() -> dict:
    """计算今日宠物情绪
    返回:
      { mood, focus_min, focus_sessions, distraction_count, streak_days, message }
    mood ∈ idle | focused | flowing | distracted | overworked | sleepy | milestone
    """
    try:
        focus_min = _today_focus_min()
        distract_min = _today_distraction_min()
        pomo = _today_pomodoro_sessions()
        streak = _streak_days()

        # 里程碑优先级最高
        if streak in (7, 14, 30, 60, 100):
            mood = "milestone"
        # 夜深还在工作 → 困倦
        elif datetime.now().hour >= 23 or datetime.now().hour < 5:
            mood = "sleepy"
        # 连续工作无休息 → 过劳
        elif _is_overwork() and focus_min >= 120:
            mood = "overworked"
        # 摸鱼占比高 → 摸鱼
        elif distract_min >= 30 and distract_min > focus_min * 0.5:
            mood = "distracted"
        # 心流：专注 ≥ 90 分钟 且 番茄完成 ≥ 2
        elif focus_min >= 90 and pomo["completed"] >= 2:
            mood = "flowing"
        # 专注：专注 ≥ 25 分钟
        elif focus_min >= 25:
            mood = "focused"
        # 默认悠闲
        else:
            mood = "idle"

        message = _pick(MOOD_POOLS.get(mood, MOOD_POOLS["idle"]))
        return {
            "mood": mood,
            "focus_min": round(focus_min, 1),
            "focus_sessions": pomo["completed"],
            "distraction_count": pomo["distracted"],
            "streak_days": streak,
            "message": message,
        }
    except Exception as e:
        logger.error(f"宠物情绪计算失败: {e}", exc_info=True)
        return {
            "mood": "idle",
            "focus_min": 0,
            "focus_sessions": 0,
            "distraction_count": 0,
            "streak_days": 0,
            "message": _pick(MOOD_POOLS["idle"]),
        }
