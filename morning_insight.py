"""
P9-2：AI 主动洞察推送（每日晨报）

每天早上基于昨日数据生成 1-3 条洞察，推送到通知中心。

设计要点：
- 规则引擎优先：先用规则检测异常模式（会议过多/深度工作不足/作息异常等）
- AI 增强：若配置了 AI，则用 AI 生成自然语言洞察
- 失败安全：AI 不可用时回退到规则模板
- 每日一次：用 sentry 文件记录当天已推送，避免重复
- 早晨触发：仅在 7:00-11:00 之间首次调用时触发
"""
import os
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import config
import db
from db import get_daily_summary, get_activities, get_pomodoro_sessions

logger = logging.getLogger(__name__)

# 推送状态文件（记录每天是否已推送）
_STATE_DIR = os.path.join(os.path.dirname(config.DB_PATH), "insight_state")
os.makedirs(_STATE_DIR, exist_ok=True)

# 行业基准（与 P7-2 保持一致）
BENCH_DEEP_WORK_MIN = 192  # 3.2 小时
BENCH_DISTRACTION_RATIO_MAX = 0.15
BENCH_MEETING_RATIO_MAX = 0.25


def _state_file_path(day: str) -> str:
    return os.path.join(_STATE_DIR, f"morning_{day}.json")


def _is_already_pushed(day: str) -> bool:
    return os.path.exists(_state_file_path(day))


def _mark_pushed(day: str, insights: list) -> None:
    try:
        with open(_state_file_path(day), "w", encoding="utf-8") as f:
            json.dump({"day": day, "insights": insights, "ts": datetime.now().isoformat()}, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"写入晨报状态失败: {e}")


def _rule_based_insights(yesterday: str, summary: dict, activities: list, pomodoros: list) -> list:
    """规则引擎：基于昨日数据生成洞察（无需 AI）"""
    insights: list[dict] = []
    interval_min = config.SCREENSHOT_INTERVAL_SEC / 60
    cats = summary.get("categories", {})
    total_cnt = summary.get("total", 0)
    total_min = total_cnt * interval_min if total_cnt else 0

    # 1. 深度工作时长评估
    deep_cats = {"开发", "文档", "学习"}
    deep_min = sum(cats.get(c, 0) for c in deep_cats) * interval_min
    if total_min > 30:  # 有数据才评估
        if deep_min >= BENCH_DEEP_WORK_MIN:
            insights.append({
                "type": "positive",
                "title": "深度工作达标",
                "body": f"昨日深度工作 {deep_min / 60:.1f} 小时，超过程序员行业基准（3.2h），保持这个节奏！",
            })
        elif deep_min > 0:
            gap = (BENCH_DEEP_WORK_MIN - deep_min) / 60
            insights.append({
                "type": "suggestion",
                "title": "深度工作可提升",
                "body": f"昨日深度工作 {deep_min / 60:.1f} 小时，距行业基准还差 {gap:.1f} 小时，今天试试上午安排一段不被打扰的时段。",
            })

    # 2. 分心比例评估
    distraction_cats = {"生活", "社交"}
    distraction_min = sum(cats.get(c, 0) for c in distraction_cats) * interval_min
    if total_min > 60:
        ratio = distraction_min / total_min if total_min else 0
        if ratio > BENCH_DISTRACTION_RATIO_MAX:
            insights.append({
                "type": "warning",
                "title": "分心比例偏高",
                "body": f"昨日分心占比 {ratio * 100:.0f}%，超过健康阈值 15%。建议今天设置番茄钟约束摸鱼时段。",
            })

    # 3. 番茄钟完成情况
    completed = [s for s in pomodoros if s.get("status") == "completed"]
    if len(completed) >= 6:
        insights.append({
            "type": "positive",
            "title": "番茄丰收日",
            "body": f"昨日完成 {len(completed)} 个番茄钟，专注力满分！今天也继续保持。",
        })
    elif len(completed) == 0 and total_min > 60:
        insights.append({
            "type": "suggestion",
            "title": "试试番茄钟",
            "body": "昨日没有使用番茄钟。今天试着开启一个 25 分钟番茄钟，体验一下心流的感觉~",
        })

    # 4. 作息评估
    first_ts = summary.get("first_ts")
    last_ts = summary.get("last_ts")
    if first_ts and last_ts:
        try:
            first_h = int(first_ts[11:13])
            last_h = int(last_ts[11:13])
            if last_h >= 23:
                insights.append({
                    "type": "care",
                    "title": "熬夜了哦",
                    "body": f"昨日最后活动记录在 {last_ts[11:16]}，记得早点休息，身体是革命的本钱~",
                })
            elif first_h < 7 and total_min > 30:
                insights.append({
                    "type": "positive",
                    "title": "早起型选手",
                    "body": f"昨日 {first_h}:00 前就开始活动了，早起的鸟儿有虫吃~",
                })
        except (ValueError, IndexError):
            pass

    # 5. 多面手彩蛋
    if len(cats) >= 6 and total_min > 120:
        insights.append({
            "type": "fun",
            "title": "多面手",
            "body": f"昨日涉及 {len(cats)} 个不同分类，是个充实多样的日子！",
        })

    # 6. 连续打卡
    try:
        # 检查最近 7 天的活跃情况
        today = date.today()
        streak = 0
        for i in range(1, 8):
            d = (today - timedelta(days=i)).isoformat()
            s = get_daily_summary(d, d)
            if s.get("total", 0) > 0:
                streak += 1
            else:
                break
        if streak >= 5:
            insights.append({
                "type": "positive",
                "title": "连续打卡中",
                "body": f"已经连续 {streak} 天有活动记录，习惯正在养成，再接再厉！",
            })
    except Exception:
        pass

    # 限制最多 3 条，优先级：positive > suggestion > warning > care > fun
    priority = {"positive": 0, "suggestion": 1, "warning": 2, "care": 3, "fun": 4}
    insights.sort(key=lambda x: priority.get(x["type"], 99))
    return insights[:3]


def _ai_enhance_insights(yesterday: str, summary: dict, activities: list, rule_insights: list) -> list:
    """用 AI 增强洞察文案（可选）"""
    if not config.AI_API_KEY:
        return rule_insights
    try:
        from ai_client import _get_client, _cb_check, _rate_limit_check
        if not _cb_check() or not _rate_limit_check("text"):
            return rule_insights
        client = _get_client()
        interval_min = config.SCREENSHOT_INTERVAL_SEC / 60
        cats = {k: round(v * interval_min) for k, v in summary.get("categories", {}).items()}
        rule_text = "\n".join(f"- [{i['type']}] {i['title']}: {i['body']}" for i in rule_insights)
        prompt = f"""请基于以下昨日数据，生成 1-3 条温暖、活泼、可爱（但不肉麻）的晨间洞察。
要求：
1. 上午时段必须用鼓励性语气，绝不出现"效率低"、"有点散"等负面词汇
2. 每条洞察 50-80 字，融入具体数据
3. 输出 JSON 数组，每项包含 title 和 body 字段
4. 风格参考：文字堆砌式，温馨可爱，像朋友间的鼓励

昨日日期：{yesterday}
分类时长（分钟）：{cats}
规则引擎已检测到的模式：
{rule_text or '（无）'}

请输出 JSON 数组："""
        response = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": "你是一个温馨可爱的工作洞察助手，擅长用活泼的语气鼓励用户。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
            temperature=0.7,
        )
        raw = response.choices[0].message.content.strip()
        # 尝试解析 JSON
        import re
        json_match = re.search(r'\[.*\]', raw, re.DOTALL)
        if json_match:
            ai_insights = json.loads(json_match.group())
            if isinstance(ai_insights, list) and ai_insights:
                # P20-7: 审计日志覆盖
                try:
                    from audit_logger import log_audit
                    log_audit("ai_insight", "morning_insight", "success",
                              detail=f"生成 {len(ai_insights[:3])} 条洞察",
                              metadata={"yesterday": yesterday})
                except Exception:
                    pass
                # 用 AI 文案替换规则文案，保留 type
                result = []
                for i, ai in enumerate(ai_insights[:3]):
                    rule_i = rule_insights[i] if i < len(rule_insights) else {}
                    result.append({
                        "type": rule_i.get("type", "positive"),
                        "title": ai.get("title", rule_i.get("title", "今日洞察")),
                        "body": ai.get("body", rule_i.get("body", "")),
                    })
                return result
    except Exception as e:
        logger.debug(f"AI 增强洞察失败，回退规则: {e}")
    return rule_insights


def generate_morning_insights(force: bool = False) -> list:
    """生成今日晨报洞察

    Args:
        force: 强制重新生成（忽略当天已推送状态）

    Returns:
        洞察列表 [{type, title, body}]，若已推送且非 force 则返回空
    """
    today = date.today().isoformat()
    if _is_already_pushed(today) and not force:
        return []

    # 仅在 7:00-11:00 之间自动触发（force 模式不受限制）
    now_h = datetime.now().hour
    if not force and (now_h < 7 or now_h >= 11):
        return []

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    try:
        summary = get_daily_summary(yesterday, yesterday)
        activities = get_activities(yesterday, yesterday)
        pomodoros = get_pomodoro_sessions(yesterday)
    except Exception as e:
        logger.error(f"获取昨日数据失败: {e}")
        return []

    # 若昨日无数据，不生成洞察
    if summary.get("total", 0) == 0 and not pomodoros:
        return []

    # 规则引擎
    rule_insights = _rule_based_insights(yesterday, summary, activities, pomodoros)
    if not rule_insights:
        return []

    # AI 增强
    final_insights = _ai_enhance_insights(yesterday, summary, activities, rule_insights)

    # 标记已推送
    _mark_pushed(today, final_insights)
    return final_insights


def push_morning_insights_if_due() -> int:
    """检查并推送晨报洞察（供主循环定时调用）

    Returns:
        推送的洞察数量
    """
    try:
        insights = generate_morning_insights()
        if not insights:
            return 0
        from routes.notifications import add_notification
        for ins in insights:
            ntype_map = {
                "positive": "success",
                "suggestion": "info",
                "warning": "warning",
                "care": "info",
                "fun": "info",
            }
            add_notification(
                title=f"🌅 晨报 · {ins['title']}",
                body=ins["body"],
                ntype=ntype_map.get(ins["type"], "info"),
            )
        logger.info(f"已推送 {len(insights)} 条晨报洞察")
        return len(insights)
    except Exception as e:
        logger.error(f"推送晨报洞察失败: {e}")
        return 0
