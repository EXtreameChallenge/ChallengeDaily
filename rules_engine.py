"""
工作流规则引擎 — IF-THEN 场景触发

从"自动日报"升级到"主动教练"。
规则示例：
- IF 连续3天会议占比>40% → THEN 建议改异步沟通
- IF 检测到深度工作2h → THEN 自动生成日报草稿
- IF 周五17:00未完成周计划80% → THEN 弹窗告警
- IF 连续2天未写日记 → THEN 提醒
"""
import logging
import json
from datetime import datetime, date, timedelta
from typing import Callable
import db

logger = logging.getLogger(__name__)

# 规则触发器类型
TRIGGER_TYPES = {
    "time": "定时触发（cron 风格）",
    "pomodoro_complete": "番茄完成触发",
    "deep_work": "检测到深度工作触发",
    "streak_break": "连续打卡中断触发",
    "no_diary": "连续N天未写日记触发",
    "week_plan_behind": "周计划进度落后触发",
    "meeting_heavy": "会议占比过高触发",
    "idle_too_long": "闲置过久触发",
}

# 动作类型
ACTION_TYPES = {
    "notify": "桌面通知",
    "ai_advice": "AI 生成建议",
    "auto_report_draft": "自动生成日报草稿",
    "webhook": "Webhook 推送",
    "start_pomodoro": "自动启动番茄",
}


def evaluate_all_rules() -> list:
    """评估所有启用的规则，返回触发的动作列表

    Returns:
        [{"rule_id": 1, "rule_name": "...", "action": "notify", "params": {...}, "message": "..."}]
    """
    triggered = []
    try:
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM rules WHERE enabled=1"
            ).fetchall()
    except Exception:
        return triggered

    for rule in rows:
        try:
            result = _evaluate_rule(dict(rule))
            if result:
                triggered.append(result)
        except Exception as e:
            logger.error(f"规则评估失败 {rule.get('name', '?')}: {e}")

    return triggered


def _evaluate_rule(rule: dict) -> dict | None:
    """评估单条规则"""
    trigger = rule.get("trigger_type", "")
    params = json.loads(rule.get("trigger_params", "{}"))

    fired = False
    message = rule.get("name", "")

    if trigger == "no_diary":
        days = params.get("days", 2)
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT MAX(diary_date) as last FROM diaries WHERE content != ''"
            ).fetchone()
        last = row["last"] if row and row["last"] else None
        if last:
            last_date = datetime.strptime(last, "%Y-%m-%d").date()
            if (date.today() - last_date).days >= days:
                fired = True
                message = f"已经 {days} 天没写日记了，记录一下今天吧"
        else:
            fired = True
            message = "还没有写过日记，开始记录第一天吧"

    elif trigger == "week_plan_behind":
        threshold = params.get("threshold", 0.8)  # 80%
        today = date.today()
        # 判断是否周五
        if today.weekday() == 4:  # 周五
            week_start = today - timedelta(days=today.weekday())
            with db.get_conn() as conn:
                total = conn.execute(
                    "SELECT COUNT(*) as c FROM todos WHERE week_start=?",
                    (week_start.isoformat(),)
                ).fetchone()["c"]
                done = conn.execute(
                    "SELECT COUNT(*) as c FROM todos WHERE week_start=? AND status='completed'",
                    (week_start.isoformat(),)
                ).fetchone()["c"]
            if total > 0:
                rate = done / total
                if rate < threshold:
                    fired = True
                    message = f"周五了，周计划仅完成 {rate*100:.0f}%，还有 {total-done} 项待完成"

    elif trigger == "meeting_heavy":
        days = params.get("days", 3)
        threshold = params.get("threshold", 0.4)  # 40%
        # 检查最近N天会议占比
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT date(start_time) as d, "
                "SUM(CASE WHEN category='会议' THEN duration_min ELSE 0 END) as meeting_min, "
                "SUM(duration_min) as total_min "
                "FROM pomodoro_sessions WHERE status='completed' "
                "AND start_time >= date('now',?) "
                "GROUP BY date(start_time)",
                (f"-{days} days",)
            ).fetchall()
        heavy_days = 0
        for r in rows:
            if r["total_min"] > 0 and r["meeting_min"] / r["total_min"] > threshold:
                heavy_days += 1
        if heavy_days >= days:
            fired = True
            message = f"最近 {days} 天有 {heavy_days} 天会议占比超过 {threshold*100:.0f}%，建议改异步沟通"

    elif trigger == "deep_work":
        hours = params.get("hours", 2)
        today = date.today().isoformat()
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(duration_min),0) as total FROM pomodoro_sessions "
                "WHERE status='completed' AND category='开发' "
                "AND (date(start_time)=? OR date(end_time)=?)",
                (today, today)
            ).fetchone()
        if row["total"] >= hours * 60:
            fired = True
            message = f"今天已完成 {hours} 小时深度工作，可以生成日报草稿了"

    elif trigger == "streak_break":
        # 检查习惯连续打卡是否中断
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT name, streak_count FROM habits WHERE enabled=1 AND streak_count > 0"
            ).fetchall()
        broken = [r["name"] for r in rows if not _habit_done_today(r["name"])]
        if broken:
            fired = True
            message = f"习惯 [{', '.join(broken)}] 今天还没打卡，别断了连续记录"

    elif trigger == "time":
        # 定时触发：检查当前时间是否匹配
        hour = params.get("hour")
        minute = params.get("minute", 0)
        now = datetime.now()
        if hour is not None and now.hour == hour and now.minute == minute:
            fired = True
            message = rule.get("name", "定时提醒")

    elif trigger == "pomodoro_complete":
        # V35: 番茄完成触发——检查最近N分钟内是否有完成的番茄钟
        window_min = params.get("window_min", 5)
        today = date.today().isoformat()
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM pomodoro_sessions "
                "WHERE status='completed' AND end_time >= datetime('now','localtime',?)",
                (f"-{window_min} minutes",)
            ).fetchone()
        if row and row["c"] > 0:
            fired = True
            count = row["c"]
            message = params.get("message", f"刚完成 {count} 个番茄钟，休息一下或继续下一个吧")

    elif trigger == "idle_too_long":
        # V35: 闲置过久触发——检查最近N分钟内是否无活动记录
        idle_min = params.get("idle_min", 30)
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT MAX(end_time) as last_active FROM activities "
                "WHERE end_time >= datetime('now','localtime',?)",
                (f"-{idle_min} minutes",)
            ).fetchone()
        if not row or not row["last_active"]:
            # 最近 idle_min 分钟内无活动
            fired = True
            message = params.get("message", f"已经闲置超过 {idle_min} 分钟了，要不要开始一个番茄钟？")

    if not fired:
        return None

    return {
        "rule_id": rule.get("id"),
        "rule_name": rule.get("name", ""),
        "action": rule.get("action_type", "notify"),
        "params": json.loads(rule.get("action_params", "{}")),
        "message": message,
        "triggered_at": datetime.now().isoformat(),
    }


def _habit_done_today(habit_name: str) -> bool:
    """检查习惯今天是否已打卡"""
    today = date.today().isoformat()
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM habit_logs WHERE habit_name=? AND log_date=?",
            (habit_name, today)
        ).fetchone()
    return row["c"] > 0 if row else False


def init_rules_table():
    """初始化规则表（如果不存在）"""
    with db.get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                trigger_type TEXT NOT NULL,
                trigger_params TEXT DEFAULT '{}',
                action_type TEXT NOT NULL DEFAULT 'notify',
                action_params TEXT DEFAULT '{}',
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                last_fired_at TEXT
            )
        """)
        # 插入默认规则（如果表为空）
        count = conn.execute("SELECT COUNT(*) as c FROM rules").fetchone()["c"]
        if count == 0:
            default_rules = [
                ("未写日记提醒", "连续2天未写日记时提醒", "no_diary", '{"days": 2}', "notify", '{}'),
                ("周计划落后告警", "周五周计划完成率<80%告警", "week_plan_behind", '{"threshold": 0.8}', "notify", '{}'),
                ("会议占比过高", "连续3天会议>40%建议异步", "meeting_heavy", '{"days": 3, "threshold": 0.4}', "ai_advice", '{}'),
                ("深度工作日报", "深度工作2h后生成日报草稿", "deep_work", '{"hours": 2}', "auto_report_draft", '{}'),
                ("习惯打卡提醒", "习惯连续记录将中断时提醒", "streak_break", '{}', "notify", '{}'),
            ]
            for name, desc, trig, tp, act, ap in default_rules:
                conn.execute(
                    "INSERT INTO rules (name, description, trigger_type, trigger_params, action_type, action_params) "
                    "VALUES (?,?,?,?,?,?)",
                    (name, desc, trig, tp, act, ap)
                )
        conn.commit()
