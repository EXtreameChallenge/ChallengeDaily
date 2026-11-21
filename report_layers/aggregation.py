"""日报数据聚合与洞察分析层（轮11 从 report.py 拆出）。"""
from __future__ import annotations

import json as _json
import logging
import socket
import urllib.error
import urllib.request
from collections import OrderedDict
from datetime import datetime, timedelta

import config
import db as _db
from db import get_daily_summary
from app_tracker import get_display_name

logger = logging.getLogger(__name__)

_weather_cache: OrderedDict = OrderedDict()
_WEEKDAYS_DEEP = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_CREATIVE_CATS = {"开发", "设计", "学习"}
_FOCUS_CATS_DEEP = {"开发", "设计", "文档", "测试", "数据分析", "学习"}
_MEETING_CATS_DEEP = {"会议", "沟通"}
_DEEP_WORK_THRESHOLD_MIN = 25

def _get_pomodoro_summary_line(target_date: str) -> str:
    """构造一行番茄统计文本，注入到 AI 日报 prompt 上下文中。

    复用 db.get_pomodoro_sessions 查询当日会话；失败时返回空串不影响日报生成。
    """
    try:
        sessions = _db.get_pomodoro_sessions(target_date)
        completed = [s for s in sessions if s.get('status') == 'completed']
        total_min = sum(s.get('duration_min', 0) for s in completed)
        distractions = sum(s.get('interrupted_count', 0) or 0 for s in sessions)
        if not sessions:
            return ""
        return (f"番茄统计：今日完成 {len(completed)} 个番茄"
                f"（{total_min}分钟），分心 {distractions} 次")
    except Exception as e:
        logger.debug(f"番茄统计行构造失败(非致命): {e}")
        return ""


def _format_duration(total_seconds: float) -> str:
    """将秒数格式化为可读时长"""
    if total_seconds < 60:
        return f"{max(int(total_seconds), 1)}s"
    minutes = total_seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}min"
    hours = minutes / 60
    return f"{hours:.1f}h"


def _estimate_focus_hours(activities: list, app_usage: list = None) -> str:
    """根据 app_usage 表的实际 duration_sec 聚合专注时长；
    若未传入 app_usage，回退到按活动条数估算。"""
    if app_usage:
        # app_usage 中 duration_min 已经是分钟，转回秒聚合
        total_seconds = sum((au.get("duration_min", 0) or 0) * 60 for au in app_usage)
        if total_seconds > 0:
            return _format_duration(total_seconds)
    # 回退：按活动条数 × 采样间隔估算
    if not activities:
        return "0s"
    total_seconds = len(activities) * config.SCREENSHOT_INTERVAL_SEC
    return _format_duration(total_seconds)


def _count_focus_sessions(activities: list) -> int:
    """统计专注次数（同一分类持续 >= 15min 算一次）"""
    if not activities:
        return 0
    # 确保按时间升序排列（get_activities 返回 DESC）
    sorted_acts = sorted(activities, key=lambda a: a.get("timestamp", ""))
    sessions = 0
    current_cat = None
    current_count = 0
    for act in sorted_acts:
        if act["category"] == current_cat:
            current_count += 1
        else:
            if current_count * config.SCREENSHOT_INTERVAL_SEC >= 900:
                sessions += 1
            current_cat = act["category"]
            current_count = 1
    if current_count * config.SCREENSHOT_INTERVAL_SEC >= 900:
        sessions += 1
    return sessions


def _group_into_blocks(activities: list) -> list[dict]:
    """
    将活动按"同分类连续"分组为工作段落（block）。
    每个 block 包含：
      - category: 分类名
      - start_time: 段落开始时间 (HH:MM)
      - end_time: 段落结束时间 (HH:MM)
      - duration_sec: 持续秒数
      - summaries: 该段落内各行 AI 摘要列表（去重）
      - apps: 涉及的应用集合（去重）
      - window_titles: 涉及的窗口标题集合（去重）
    """
    if not activities:
        return []

    # get_activities 返回 DESC；分段必须按时间升序，否则时段会出现 22:51-22:30
    activities = sorted(activities, key=lambda a: a.get("timestamp", ""))

    blocks = []
    cur_cat = None
    cur_summaries = []
    cur_apps = set()
    cur_titles = set()
    cur_start = None
    cur_count = 0
    prev_ts = None
    prev_ts_str = None
    # 同分类但中断超过 5 分钟，必须切段；否则会把 00:00 和 08:36 拼成一段
    gap_limit_sec = max(300, int(getattr(config, "SCREENSHOT_INTERVAL_SEC", 60)) * 2)

    for act in activities:
        cat = act["category"]
        ts = act["timestamp"]
        try:
            ts_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except Exception:
            ts_dt = prev_ts

        if cur_cat is not None:
            gap_sec = (ts_dt - prev_ts).total_seconds() if (ts_dt and prev_ts) else 0
            if cat != cur_cat or gap_sec > gap_limit_sec:
                blocks.append(_make_block(cur_cat, cur_start, prev_ts_str, cur_count,
                                          cur_summaries, cur_apps, cur_titles))
                cur_cat = None
                cur_start = None
                cur_summaries = []
                cur_apps = set()
                cur_titles = set()
                cur_count = 0

        if cur_cat is None:
            cur_cat = cat
            cur_start = ts

        cur_count += 1
        display_name = get_display_name(act["app_name"])
        cur_apps.add(display_name)
        win_title = act.get("window_title", "")
        if win_title:
            cur_titles.add(win_title)
        summary = act.get("summary", "")
        if summary and summary != "未配置AI":
            cur_summaries.append(summary)
        prev_ts = ts_dt
        prev_ts_str = ts

    # 最后一段
    if cur_cat is not None:
        blocks.append(_make_block(cur_cat, cur_start, prev_ts_str,
                                  cur_count, cur_summaries, cur_apps, cur_titles))

    return blocks


def _make_block(category, start_ts, end_ts, count, summaries, apps, titles) -> dict:
    """构造一个工作段落"""
    # 去重摘要（保持顺序）
    seen = set()
    unique_summaries = []
    for s in summaries:
        if s not in seen:
            seen.add(s)
            unique_summaries.append(s)

    duration_sec = max(count * config.SCREENSHOT_INTERVAL_SEC, config.SCREENSHOT_INTERVAL_SEC)
    start_hm = start_ts[11:16] if len(start_ts) > 16 else start_ts
    end_hm = end_ts[11:16] if len(end_ts) > 16 else end_ts

    return {
        "category": category,
        "start_time": start_hm,
        "end_time": end_hm,
        "duration_sec": duration_sec,
        "duration_str": _format_duration(duration_sec),
        "summaries": unique_summaries,
        "apps": sorted(apps),
        "window_titles": sorted(titles),
    }


def _blocks_by_category(blocks: list[dict]) -> OrderedDict:
    """将 blocks 按分类归纳，合并同分类的多段为一段描述"""
    by_cat = OrderedDict()
    for b in blocks:
        cat = b["category"]
        if cat not in by_cat:
            by_cat[cat] = {
                "category": cat,
                "total_sec": 0,
                "time_ranges": [],
                "all_summaries": [],
                "all_apps": set(),
            }
        entry = by_cat[cat]
        entry["total_sec"] += b["duration_sec"]
        entry["time_ranges"].append(f"{b['start_time']}-{b['end_time']}")
        entry["all_summaries"].extend(b["summaries"])
        entry["all_apps"].update(b["apps"])

    # 对每个分类去重摘要
    for cat, entry in by_cat.items():
        seen = set()
        unique = []
        for s in entry["all_summaries"]:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        entry["all_summaries"] = unique

    return by_cat


def _merge_summaries(summaries: list[str], max_items: int = 4) -> str:
    """将多条摘要合并为自然语言段落，使用多样化连接词降低机器味"""
    if not summaries:
        return ""
    if len(summaries) <= max_items:
        # 用自然连接词代替纯分号
        connectors = ["，", "，同时", "，另外", "，还"]
        if len(summaries) == 1:
            return summaries[0]
        if len(summaries) == 2:
            return f"{summaries[0]}{connectors[1]}{summaries[1]}"
        # 3条以上：前几条用逗号，最后一条用连接词
        parts = summaries[:-1]
        last = summaries[-1]
        return "，".join(parts) + f"{connectors[min(len(summaries)-2, len(connectors)-1)]}{last}"
    # 太多条则截断 + 更自然的省略
    preview = "，".join(summaries[:max_items])
    remaining = len(summaries) - max_items
    return f"{preview}等{remaining}项"


def _build_category_narrative(blocks: list[dict]) -> list[dict]:
    """构建分类叙事：每个分类 → 一段自然描述"""
    by_cat = _blocks_by_category(blocks)
    result = []
    for cat, entry in by_cat.items():
        time_desc = "、".join(entry["time_ranges"][:3])
        if len(entry["time_ranges"]) > 3:
            time_desc += "等"
        summary_text = _merge_summaries(entry["all_summaries"])
        apps_str = "、".join(sorted(entry["all_apps"])[:4])
        result.append({
            "category": cat,
            "duration_str": _format_duration(entry["total_sec"]),
            "total_sec": entry["total_sec"],
            "time_desc": time_desc,
            "summary": summary_text,
            "apps": apps_str,
            "all_summaries": entry["all_summaries"],
        })
    return result


def _natural_time_span(first_ts: str, last_ts: str) -> str:
    """生成自然的工作时段描述"""
    if not first_ts or not last_ts:
        return ""
    start = first_ts[11:16]
    end = last_ts[11:16]
    sh, sm = start.split(":")
    eh, em = end.split(":")
    # 用口语化的时段描述
    start_period = _time_period(int(sh))
    end_period = _time_period(int(eh))
    if start_period == end_period:
        return f"{start_period}{start}到{end}"
    return f"{start_period}{start}到{end_period}{end}"


def _time_period(hour: int) -> str:
    """根据小时数返回时段前缀"""
    if 0 <= hour < 6:
        return "凌晨"
    if 6 <= hour < 9:
        return "早上"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 14:
        return "中午"
    if 14 <= hour < 18:
        return "下午"
    if 18 <= hour < 22:
        return "晚上"
    return "深夜"


def _natural_overview(activities, cat_narratives, first_ts, last_ts, focus_hours, focus_sessions) -> str:
    """生成自然语言的今日概要段落，避免公文化表述"""
    if not cat_narratives:
        return "今天暂无工作记录。"

    time_span = _natural_time_span(first_ts, last_ts) if first_ts and last_ts else ""

    # 构建开头：这里描述的是“有记录的覆盖区间”，不是连续投入时长，避免把跨天空档写成连续工作。
    opening = f"今天的记录覆盖 {time_span}" if time_span else "今天有工作记录"

    # 核心工作描述
    top_cats = [n["category"] for n in cat_narratives[:3]]
    if len(top_cats) == 1:
        core_desc = f"，主要精力放在了{top_cats[0]}上"
    elif len(top_cats) == 2:
        core_desc = f"，核心工作是{top_cats[0]}和{top_cats[1]}"
    elif len(top_cats) >= 3:
        core_desc = f"，涵盖了{top_cats[0]}、{top_cats[1]}、{top_cats[2]}等方向"
    else:
        core_desc = ""

    # 应用窗口累计（多窗口时长可重叠，不等于墙钟专注时长）
    focus_desc = f"，应用窗口累计{focus_hours}"
    if focus_sessions > 0:
        focus_desc += f"，进入深度状态{focus_sessions}次"

    # 分类数量
    cat_desc = f"涉及{len(cat_narratives)}个工作类别"

    return f"{opening}{core_desc}{focus_desc}，{cat_desc}。"


def _weather_cache_set(key, value):
    """带 LRU 驱逐的天气缓存写入（最多保留 7 天数据）"""
    if key in _weather_cache:
        _weather_cache.move_to_end(key)
    _weather_cache[key] = value
    while len(_weather_cache) > 7:
        _weather_cache.popitem(last=False)


def _safe_get(d, key, default=None):
    try:
        if isinstance(d, dict):
            return d.get(key, default)
        if hasattr(d, "keys"):
            if key in d.keys():
                return d[key]
        return default
    except (KeyError, TypeError, IndexError):
        return default


def _parse_ts_hour(ts_str: str) -> int:
    try:
        return int(ts_str[11:13])
    except (ValueError, IndexError):
        return -1


def _weekday_str_deep(target_date: str) -> str:
    try:
        wd = datetime.strptime(target_date, "%Y-%m-%d").weekday()
        return _WEEKDAYS_DEEP[wd]
    except Exception:
        return ""


def _get_weather_info(target_date: str) -> dict:
    """通过 wttr.in 免费API获取天气"""
    if target_date in _weather_cache:
        return _weather_cache[target_date]
    result = {}
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        url = "https://wttr.in/?format=j1&lang=zh"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = _json.loads(resp.read().decode("utf-8", errors="replace"))
        weather_arr = data.get("weather", [])
        target_idx = 0
        if target_date != today_str and len(weather_arr) > 1:
            for i, w in enumerate(weather_arr):
                if w.get("date") == target_date:
                    target_idx = i
                    break
        if target_idx < len(weather_arr):
            w = weather_arr[target_idx]
            hourly = w.get("hourly", [])
            mid_hour = hourly[4] if len(hourly) > 4 else (hourly[0] if hourly else {})
            temp = mid_hour.get("tempC", "")
            humidity = mid_hour.get("humidity", "")
            desc_arr = mid_hour.get("lang_zh", mid_hour.get("weatherDesc", []))
            desc = ""
            if desc_arr:
                desc = desc_arr[0].get("value", "") if isinstance(desc_arr[0], dict) else str(desc_arr[0])
            wind_arr = mid_hour.get("windspeedKmph", "")
            wind_desc = "微风"
            try:
                ws = int(wind_arr)
                if ws < 12: wind_desc = "微风"
                elif ws < 30: wind_desc = "轻风"
                elif ws < 50: wind_desc = "中风"
                else: wind_desc = "强风"
            except (ValueError, TypeError):
                pass
            result = {
                "temp": f"{temp}°C" if temp else "",
                "desc": desc,
                "humidity": f"{humidity}%" if humidity else "",
                "wind": wind_desc,
            }
            if not result["temp"]:
                avg_t = w.get("avgtempC", "")
                result["temp"] = f"{avg_t}°C" if avg_t else ""
            if not result["desc"]:
                en_arr = mid_hour.get("weatherDesc", [])
                if en_arr:
                    result["desc"] = en_arr[0].get("value", "") if isinstance(en_arr[0], dict) else str(en_arr[0])
    except socket.timeout:
        logger.debug("天气获取超时（8秒），跳过天气数据")
    except Exception as e:
        logger.debug(f"天气获取失败: {e}")
    # 只缓存成功结果，避免网络瞬断导致当天天气永久为空
    if result:
        _weather_cache_set(target_date, result)
    return result


def _get_yesterday_comparison(target_date: str) -> dict:
    result = {"yesterday_total": 0, "change_pct": 0, "yesterday_top_cat": "", "trend": "持平"}
    try:
        td = datetime.strptime(target_date, "%Y-%m-%d").date()
        yesterday = (td - timedelta(days=1)).isoformat()
        y_summary = get_daily_summary(yesterday, yesterday)
        t_summary = get_daily_summary(target_date, target_date)
        y_total = y_summary.get("total", 0) if y_summary else 0
        t_total = t_summary.get("total", 0) if t_summary else 0
        result["yesterday_total"] = y_total
        if y_total > 0:
            change = round((t_total - y_total) / y_total * 100, 1)
        elif t_total > 0:
            change = 100.0
        else:
            change = 0
        result["change_pct"] = change
        y_cats = y_summary.get("categories", {}) if y_summary else {}
        if y_cats:
            result["yesterday_top_cat"] = max(y_cats, key=y_cats.get)
        if change > 10: result["trend"] = "上升"
        elif change < -10: result["trend"] = "下降"
        else: result["trend"] = "持平"
    except Exception as e:
        logger.debug(f"昨日对比计算失败: {e}")
    return result


def _compute_attention_index(activities: list) -> dict:
    result = {
        "fragmentation_index": 0, "focus_efficiency": 0, "deep_work_ratio": 0.0,
        "avg_session_min": 0.0, "longest_streak_min": 0, "switch_frequency": 0.0,
    }
    if not activities:
        return result
    # 确保按时间升序（get_activities 返回 DESC）
    activities = sorted(activities, key=lambda a: a.get("timestamp", ""))
    interval = config.SCREENSHOT_INTERVAL_SEC
    total_records = len(activities)
    sessions = []
    cur_cat = activities[0]["category"]
    cur_count = 1
    for i in range(1, len(activities)):
        if activities[i]["category"] == cur_cat:
            cur_count += 1
        else:
            sessions.append((cur_cat, cur_count))
            cur_cat = activities[i]["category"]
            cur_count = 1
    sessions.append((cur_cat, cur_count))
    total_sessions = len(sessions)
    category_switches = max(total_sessions - 1, 0)
    hour_set = set()
    for act in activities:
        h = _parse_ts_hour(act["timestamp"])
        if 0 <= h <= 23: hour_set.add(h)
    active_hours = max(len(hour_set), 1)
    switch_frequency = round(category_switches / active_hours, 2)
    short_sessions = sum(1 for _, cnt in sessions if cnt * interval < 600)
    short_ratio = short_sessions / total_sessions if total_sessions > 0 else 0
    avg_session_len = sum(cnt * interval for _, cnt in sessions) / total_sessions if total_sessions > 0 else 0
    avg_session_min = round(avg_session_len / 60, 1)
    frag_switch = min(switch_frequency / 5.0, 1.0) * 40
    frag_short = short_ratio * 40
    frag_avg = min(1.0, 30.0 / max(avg_session_min, 1)) * 20
    fragmentation_index = min(100, round(frag_switch + frag_short + frag_avg))
    deep_sessions = sum(1 for _, cnt in sessions if cnt * interval >= _DEEP_WORK_THRESHOLD_MIN * 60)
    focus_efficiency = round(min(100, deep_sessions / max(total_sessions, 1) * 100 * 2))
    deep_records = sum(cnt for _, cnt in sessions if cnt * interval >= _DEEP_WORK_THRESHOLD_MIN * 60)
    deep_work_ratio = round(deep_records / total_records * 100, 1) if total_records > 0 else 0
    longest_cnt = max(cnt for _, cnt in sessions) if sessions else 0
    longest_streak_min = round(longest_cnt * interval / 60)
    result.update({
        "fragmentation_index": fragmentation_index, "focus_efficiency": focus_efficiency,
        "deep_work_ratio": deep_work_ratio, "avg_session_min": avg_session_min,
        "longest_streak_min": longest_streak_min, "switch_frequency": switch_frequency,
    })
    return result


def _compute_emotion_curve(activities: list, patterns: dict) -> dict:
    result = {"hourly_scores": [], "peak_hour": -1, "valley_hour": -1, "overall_trend": "平稳", "energy_pattern": "均匀型"}
    if not activities:
        return result
    hourly_buckets = {}
    for act in activities:
        h = _parse_ts_hour(act["timestamp"])
        if 0 <= h <= 23:
            if h not in hourly_buckets: hourly_buckets[h] = []
            hourly_buckets[h].append(act)
    hourly_scores = []
    for h in sorted(hourly_buckets.keys()):
        acts = hourly_buckets[h]
        n = len(acts)
        focus_count = sum(1 for a in acts if a["category"] in _FOCUS_CATS_DEEP)
        creative_count = sum(1 for a in acts if a["category"] in _CREATIVE_CATS)
        meeting_count = sum(1 for a in acts if a["category"] in _MEETING_CATS_DEEP)
        focus_ratio = focus_count / n if n > 0 else 0
        creative_ratio = creative_count / n if n > 0 else 0
        meeting_ratio = meeting_count / n if n > 0 else 0
        cats = [a["category"] for a in acts]
        switches = sum(1 for i in range(1, len(cats)) if cats[i] != cats[i - 1])
        switch_freq = switches / max(n, 1)
        score = 5.0 + focus_ratio * 3.0 + creative_ratio * 1.5 - switch_freq * 2.0
        if meeting_ratio > 0.5: score -= meeting_ratio * 1.5
        score = max(1, min(10, round(score, 1)))
        dominant_cat = max(set(cats), key=cats.count) if cats else ""
        hourly_scores.append({"hour": h, "score": score, "dominant_category": dominant_cat, "activity_count": n})
    result["hourly_scores"] = hourly_scores
    if hourly_scores:
        best = max(hourly_scores, key=lambda x: x["score"])
        worst = min(hourly_scores, key=lambda x: x["score"])
        result["peak_hour"] = best["hour"]
        result["valley_hour"] = worst["hour"]
    if len(hourly_scores) >= 3:
        first_half_avg = sum(s["score"] for s in hourly_scores[:len(hourly_scores) // 2]) / (len(hourly_scores) // 2)
        second_half_avg = sum(s["score"] for s in hourly_scores[len(hourly_scores) // 2:]) / (len(hourly_scores) - len(hourly_scores) // 2)
        diffs = [hourly_scores[i + 1]["score"] - hourly_scores[i]["score"] for i in range(len(hourly_scores) - 1)]
        avg_abs_diff = sum(abs(d) for d in diffs) / len(diffs) if diffs else 0
        if avg_abs_diff > 1.5: result["overall_trend"] = "波动"
        elif first_half_avg - second_half_avg > 1.0: result["overall_trend"] = "下降"
        elif second_half_avg - first_half_avg > 1.0: result["overall_trend"] = "上升"
        else: result["overall_trend"] = "平稳"
    if hourly_scores:
        morning = [s for s in hourly_scores if 6 <= s["hour"] < 12]
        afternoon = [s for s in hourly_scores if 12 <= s["hour"] < 18]
        evening = [s for s in hourly_scores if s["hour"] >= 18]
        morning_avg = sum(s["score"] for s in morning) / len(morning) if morning else 0
        afternoon_avg = sum(s["score"] for s in afternoon) / len(afternoon) if afternoon else 0
        evening_avg = sum(s["score"] for s in evening) / len(evening) if evening else 0
        avgs = {"晨型": morning_avg, "午后型": afternoon_avg, "夜型": evening_avg}
        best_pattern = max(avgs, key=avgs.get)
        if avgs[best_pattern] > 0 and all(avgs[best_pattern] - v < 0.8 for v in avgs.values() if v > 0):
            result["energy_pattern"] = "均匀型"
        else:
            result["energy_pattern"] = best_pattern
    return result


def _compute_skill_radar(activities: list) -> dict:
    result = {"dimensions": {}, "top_skill": "", "growth_areas": []}
    if not activities:
        return result
    interval = config.SCREENSHOT_INTERVAL_SEC
    cat_hours = {}
    for act in activities:
        cat = act["category"]
        cat_hours[cat] = cat_hours.get(cat, 0) + interval
    for cat, sec in cat_hours.items():
        cat_hours[cat] = sec / 3600.0
    skill_map = {
        "编码": ["开发"], "沟通": ["沟通", "会议"], "创作": ["设计", "文档"],
        "分析": ["数据分析"], "运维": ["运维"], "学习": ["学习"],
        "管理": ["管理", "产品"], "测试": ["测试"],
    }
    dimensions = {}
    for skill, cats in skill_map.items():
        dimensions[skill] = round(sum(cat_hours.get(c, 0) for c in cats), 2)
    result["dimensions"] = dimensions
    if dimensions:
        result["top_skill"] = max(dimensions, key=dimensions.get)
        active_vals = [v for v in dimensions.values() if v > 0]
        if active_vals:
            avg_val = sum(active_vals) / len(active_vals)
            result["growth_areas"] = sorted([k for k, v in dimensions.items() if 0 < v < avg_val], key=lambda k: dimensions[k])
        else:
            result["growth_areas"] = list(dimensions.keys())
    return result


def _compute_workflow_analysis(activities: list) -> list:
    if not activities:
        return []
    interval = config.SCREENSHOT_INTERVAL_SEC
    sorted_acts = sorted(activities, key=lambda x: x["timestamp"])
    scenes = []
    cur_scene = None
    CONTEXT_GAP_MIN = 15
    for act in sorted_acts:
        cat = act["category"]
        ts_str = act["timestamp"]
        try:
            ts = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        should_new = False
        if cur_scene is None:
            should_new = True
        else:
            gap_min = (ts - cur_scene["last_ts"]).total_seconds() / 60
            if gap_min > CONTEXT_GAP_MIN: should_new = True
            elif cat in _MEETING_CATS_DEEP and cur_scene["last_cat"] not in _MEETING_CATS_DEEP: should_new = True
            elif cat in _FOCUS_CATS_DEEP and cur_scene["last_cat"] in _MEETING_CATS_DEEP: should_new = True
        if should_new:
            if cur_scene is not None:
                scenes.append(_finalize_workflow_scene(cur_scene, interval))
            cur_scene = {"start_ts": ts, "last_ts": ts, "last_cat": cat, "categories": [cat], "apps": [], "summaries": [], "count": 1}
        else:
            cur_scene["last_ts"] = ts
            cur_scene["last_cat"] = cat
            if cat not in cur_scene["categories"]: cur_scene["categories"].append(cat)
            cur_scene["count"] += 1
        app_dn = get_display_name(act["app_name"])
        if app_dn not in cur_scene["apps"]: cur_scene["apps"].append(app_dn)
        summary = _safe_get(act, "summary", "")
        if summary and summary != "未配置AI": cur_scene["summaries"].append(summary)
    if cur_scene is not None:
        scenes.append(_finalize_workflow_scene(cur_scene, interval))
    return scenes


def _finalize_workflow_scene(scene: dict, interval: int) -> dict:
    duration_min = round(scene["count"] * interval / 60, 1)
    start_hm = scene["start_ts"].strftime("%H:%M")
    end_hm = scene["last_ts"].strftime("%H:%M")
    seen = set()
    unique_summaries = []
    for s in scene["summaries"]:
        if s not in seen: seen.add(s); unique_summaries.append(s)
    cats = scene["categories"]
    apps = scene["apps"][:5]
    description = _infer_scene_description(cats, unique_summaries, duration_min)
    return {
        "scene": description[:30], "time_range": f"{start_hm}-{end_hm}",
        "categories": cats, "apps": apps, "duration_min": duration_min, "description": description,
    }


def _infer_scene_description(cats: list, summaries: list, duration_min: float) -> str:
    cat_set = set(cats)
    if "会议" in cat_set and len(cat_set) > 1: return f"会议后推进执行，涵盖{'、'.join(cats[:3])}"
    if "沟通" in cat_set and "开发" in cat_set: return "沟通反馈后编码实现"
    if "沟通" in cat_set and "文档" in cat_set: return "沟通后整理文档归档"
    if cat_set <= {"开发"}: return "深度编码会话" if duration_min >= 60 else "编码开发"
    if cat_set <= {"设计"}: return "设计创作"
    if cat_set <= {"会议", "沟通"}: return "密集沟通协作" if duration_min >= 60 else "沟通协作"
    if cat_set <= {"学习"}: return "专注学习"
    if cat_set <= {"测试"}: return "测试验证"
    if len(cats) >= 4: return "多线程切换，事务繁杂"
    if summaries: return summaries[0][:50]
    return "、".join(cats[:3]) + f"（{duration_min:.0f}分钟）"


def _smart_sample_timeline(timeline_data: list, max_items: int = 40) -> list:
    if len(timeline_data) <= max_items:
        return timeline_data
    head, tail = 5, 5
    mid = max_items - head - tail
    sampled = list(timeline_data[:head])
    seen_cats = set()
    mid_pool = []
    for item in timeline_data[head:-tail]:
        priority = (2 if item.get("detail") else 0) + (1 if item.get("category") not in seen_cats else 0)
        mid_pool.append((priority, item))
        seen_cats.add(item.get("category", ""))
    mid_pool.sort(key=lambda x: -x[0])
    sampled.extend(item for _, item in mid_pool[:mid])
    sampled.extend(timeline_data[-tail:])
    sampled.sort(key=lambda x: x["time"])
    seen_times = set()
    deduped = []
    for item in sampled:
        if item["time"] not in seen_times:
            deduped.append(item)
            seen_times.add(item["time"])
    return deduped[:max_items]


def _build_rich_data_context(target_date, summary_data, app_usage, activities) -> str:
    wd_str = _weekday_str_deep(target_date)
    weather = _get_weather_info(target_date)
    yesterday = _get_yesterday_comparison(target_date)
    attention = _compute_attention_index(activities)
    patterns = _analyze_work_patterns(activities)
    emotion = _compute_emotion_curve(activities, patterns)
    skill = _compute_skill_radar(activities)
    workflows = _compute_workflow_analysis(activities)
    timeline_data = _build_activity_timeline_data(activities)

    total = summary_data.get("total", 0) if summary_data else 0
    first_ts = summary_data.get("first_ts", "") if summary_data else ""
    last_ts = summary_data.get("last_ts", "") if summary_data else ""
    time_span = _natural_time_span(first_ts, last_ts) if first_ts and last_ts else ""
    focus_hours = _estimate_focus_hours(activities, app_usage)
    focus_sessions = _count_focus_sessions(activities)

    lines = []

    # 日期与天气
    lines.append("═══ 日期与天气 ═══")
    lines.append(f"日期：{target_date} {wd_str}")
    lines.append(f"活跃时段：{time_span}")
    if weather:
        parts = []
        if weather.get("temp"): parts.append(f"气温 {weather['temp']}")
        if weather.get("desc"): parts.append(weather["desc"])
        if weather.get("humidity"): parts.append(f"湿度 {weather['humidity']}")
        if weather.get("wind"): parts.append(weather["wind"])
        if parts: lines.append("天气：" + "，".join(parts))
    lines.append("")

    # 昨日对比
    lines.append("═══ 昨日对比 ═══")
    lines.append(f"昨日活动数：{yesterday['yesterday_total']}")
    lines.append(f"变化幅度：{yesterday['change_pct']:+.1f}%")
    lines.append(f"趋势：{yesterday['trend']}")
    if yesterday["yesterday_top_cat"]:
        lines.append(f"昨日主力分类：{yesterday['yesterday_top_cat']}")
    lines.append("")

    # 核心指标
    lines.append("═══ 核心指标 ═══")
    lines.append(f"注意力碎片化指数：{attention['fragmentation_index']}/100（越高越碎片）")
    lines.append(f"专注效率：{attention['focus_efficiency']}/100")
    lines.append(f"深度工作占比：{attention['deep_work_ratio']}%")
    lines.append(f"平均会话时长：{attention['avg_session_min']} 分钟")
    lines.append(f"最长连续同分类：{attention['longest_streak_min']} 分钟")
    lines.append(f"每小时切换次数：{attention['switch_frequency']}")
    lines.append(f"应用累计时长：{focus_hours}，深度会话 {focus_sessions} 次")
    lines.append("")

    # 注入番茄统计（一行，不超过 100 字符，不影响 prompt 预算）
    pomo_line = _get_pomodoro_summary_line(target_date)
    if pomo_line:
        lines.append(pomo_line)
        lines.append("")

    # 心流与专注
    lines.append("═══ 心流与专注 ═══")
    focus_ses = patterns.get("focus_sessions", [])
    if focus_ses:
        for fs in focus_ses:
            lines.append(f"- {fs['start']} 开始，{fs['category']}，持续 {fs['duration_min']} 分钟")
    lf = patterns.get("longest_focus")
    if lf:
        lines.append(f"最长专注：{lf['category']}，{lf['duration_min']} 分钟")
    deep_count = sum(1 for fs in focus_ses if fs["duration_min"] >= _DEEP_WORK_THRESHOLD_MIN)
    lines.append(f"深度工作（≥{_DEEP_WORK_THRESHOLD_MIN}分钟）次数：{deep_count}")
    lines.append("")

    # 工作场景流
    lines.append("═══ 工作场景流 ═══")
    for wf in workflows:
        lines.append(f"- [{wf['time_range']}] {wf['scene']}（{wf['duration_min']:.0f}分钟）")
        lines.append(f"  分类：{'、'.join(wf['categories'])}，工具：{'、'.join(wf['apps'])}")
        if wf["description"] and wf["description"] != wf["scene"]:
            lines.append(f"  详情：{wf['description']}")
    lines.append("")

    # 叙事时间线
    lines.append("═══ 叙事时间线 ═══")
    sampled_timeline = _smart_sample_timeline(timeline_data, max_items=40)
    for i, item in enumerate(sampled_timeline, 1):
        lines.append(f"{i}. {item['time']} [{item['category']}] {item['app']}")
        if item.get("summary"):
            lines.append(f"   摘要：{item['summary']}")
        if item.get("detail"):
            lines.append(f"   详情：{item['detail'][:150]}")
        if item.get("windows"):
            for w in item["windows"]:
                fg = "前台" if w.get("foreground") else "后台"
                lines.append(f"   窗口 {fg}：{w['app']} — {w.get('desc', '')}")
    lines.append("")

    # 工作强度曲线
    lines.append("═══ 工作强度曲线 ═══")
    curve = patterns.get("intensity_curve", [])
    for c in curve:
        bar = "█" * min(c["count"], 20)
        lines.append(f"- {c['hour']} {bar} ({c['count']}次)")
    lines.append("")

    # 时间间隔与休息
    lines.append("═══ 时间间隔与休息 ═══")
    gaps = patterns.get("time_gaps", [])
    if gaps:
        total_gap_min = sum(g["gap_min"] for g in gaps)
        lines.append(f"共 {len(gaps)} 次离开，累计 {total_gap_min} 分钟")
        for g in gaps[:10]:
            lines.append(f"- {g['from']} → {g['to']}（{g['gap_min']}分钟）")
    else:
        lines.append("全天无长时间中断")
    lines.append("")

    # 情绪曲线
    lines.append("═══ 情绪曲线 ═══")
    for hs in emotion.get("hourly_scores", []):
        bar_len = int(hs["score"])
        bar = "●" * bar_len + "○" * (10 - bar_len)
        lines.append(f"- {hs['hour']:02d}:00 {bar} {hs['score']}/10（{hs['dominant_category']}，{hs['activity_count']}条）")
    lines.append(f"峰值时段：{emotion['peak_hour']:02d}:00")
    lines.append(f"低谷时段：{emotion['valley_hour']:02d}:00")
    lines.append(f"整体趋势：{emotion['overall_trend']}")
    lines.append(f"能量模式：{emotion['energy_pattern']}")
    lines.append("")

    # 技能雷达
    lines.append("═══ 技能雷达 ═══")
    for sk, hrs in skill.get("dimensions", {}).items():
        if hrs > 0:
            bar_len = min(int(hrs * 2), 20)
            lines.append(f"- {sk}：{hrs:.1f}h {'▓' * bar_len}")
    lines.append(f"最强技能：{skill.get('top_skill', '无')}")
    if skill.get("growth_areas"):
        lines.append(f"成长空间：{'、'.join(skill['growth_areas'])}")
    lines.append("")

    # 分类与工具统计
    lines.append("═══ 分类与工具统计 ═══")
    cats = summary_data.get("categories", {}) if summary_data else {}
    total_act_count = sum(cats.values()) if cats else 1  # avoid ZeroDivision
    for cat, cnt in cats.items():
        total_seconds = cnt * config.SCREENSHOT_INTERVAL_SEC
        lines.append(f"- {cat}：{_format_duration(total_seconds)}（{round(cnt / total_act_count * 100)}%）")
    if app_usage:
        lines.append("")
        lines.append("工具使用：")
        for au in app_usage[:10]:
            lines.append(f"- {get_display_name(au['app_name'])}：{_format_duration(au['duration_min'] * 60)}")

    # 按小时合并的时间段摘要（供数据附录直接引用）
    lines.append("")
    lines.append("═══ 按小时时间段摘要（数据附录表格请直接照此输出，不得省略任何一行）═══")
    hour_blocks = {}
    for act in activities:
        try:
            h = int(act["timestamp"][11:13])
        except (ValueError, IndexError):
            continue
        if h not in hour_blocks:
            hour_blocks[h] = {"cats": set(), "apps": set(), "count": 0}
        hour_blocks[h]["cats"].add(act["category"])
        hour_blocks[h]["apps"].add(get_display_name(act["app_name"]))
        hour_blocks[h]["count"] += 1
    # 找出每个小时的起止时间
    hour_ranges = {}
    for act in activities:
        try:
            hm = act["timestamp"][11:16]
            h = int(hm[:2])
        except (ValueError, IndexError):
            continue
        if h not in hour_ranges:
            hour_ranges[h] = {"start": hm, "end": hm}
        else:
            hour_ranges[h]["end"] = hm
    for h in sorted(hour_blocks.keys()):
        blk = hour_blocks[h]
        rng = hour_ranges.get(h, {})
        cat_str = "、".join(sorted(blk["cats"]))
        app_str = "、".join(sorted(blk["apps"]))
        dur_min = blk["count"] * config.SCREENSHOT_INTERVAL_SEC / 60
        start = rng.get("start", f"{h:02d}:00")
        end = rng.get("end", f"{h:02d}:59")
        lines.append(f"| {start}-{end} | {cat_str} | {app_str} | {dur_min:.0f}分钟 |")

    # ── 注入用户画像 + 周级上下文（长记忆，防注入过滤） ──
    try:
        from context_manager import get_user_profile_context, build_weekly_context
        from prompt import _sanitize_user_input
        user_ctx = get_user_profile_context()
        if user_ctx:
            lines.append("")
            lines.append("═══ 用户画像 ═══")
            lines.append(_sanitize_user_input(user_ctx, 1500))
        weekly_ctx = build_weekly_context(7)
        if weekly_ctx and len(weekly_ctx) > 50:
            lines.append("")
            lines.append("═══ 近一周工作上下文 ═══")
            lines.append(_sanitize_user_input(weekly_ctx, 3000))
    except Exception:
        pass

    # ── 注入 DeepInsight 学术框架分析 ──
    try:
        from deep_insight_engine import build_deep_insight_context
        di_ctx = build_deep_insight_context(activities, interval_sec=config.SCREENSHOT_INTERVAL_SEC)
        if di_ctx:
            lines.append("")
            lines.append(di_ctx)
    except Exception as di_err:
        logger.debug(f"DeepInsight context 注入失败(非致命): {di_err}")

    # ── 注入幕布笔记作为额外上下文（失败不影响生成）──
    try:
        from mubu_sync import build_mubu_context_for_ai
        mubu_ctx = build_mubu_context_for_ai(days=7, limit=20)
        if mubu_ctx:
            lines.append("")
            lines.append(mubu_ctx)
    except Exception as mubu_err:
        logger.debug(f"幕布上下文注入失败(非致命): {mubu_err}")

    return "\n".join(lines)


def _analyze_work_patterns(activities: list) -> dict:
    """分析工作模式：时间分布、专注节奏、上下文切换频率、工作强度变化"""
    if not activities:
        return {}

    # 确保按时间升序（get_activities 返回 DESC）
    activities = sorted(activities, key=lambda a: a.get("timestamp", ""))

    interval = config.SCREENSHOT_INTERVAL_SEC
    patterns = {
        "time_gaps": [],           # 时间间隔异常（>5min 无记录 = 休息/离开）
        "category_switches": 0,    # 分类切换次数
        "focus_sessions": [],      # 深度专注会话（同分类持续>=15min）
        "intensity_curve": [],     # 工作强度曲线（每小时活动密度）
        "longest_focus": None,     # 最长专注段
        "interrupted_sessions": 0, # 被打断的专注段（<10min 就切换）
    }

    from datetime import datetime as _dt

    # 分析时间间隔和分类切换
    prev_ts = None
    prev_cat = None
    cur_focus_start = None
    cur_focus_cat = None
    cur_focus_count = 0

    for act in activities:
        ts_str = act["timestamp"]
        cat = act["category"]
        try:
            ts = _dt.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                ts = _dt.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

        # 时间间隔分析
        if prev_ts:
            gap_sec = (ts - prev_ts).total_seconds()
            if gap_sec > interval * 3:  # 超过3个间隔 = 有间断
                patterns["time_gaps"].append({
                    "from": prev_ts.strftime("%H:%M"),
                    "to": ts.strftime("%H:%M"),
                    "gap_min": round(gap_sec / 60),
                })

        # 分类切换分析
        if prev_cat and cat != prev_cat:
            patterns["category_switches"] += 1
            # 检查是否是被打断的短专注
            if cur_focus_count > 0 and cur_focus_count * interval < 600:  # <10min
                patterns["interrupted_sessions"] += 1
            # 保存上一段专注
            if cur_focus_count * interval >= 900:  # >=15min
                patterns["focus_sessions"].append({
                    "category": cur_focus_cat,
                    "start": cur_focus_start.strftime("%H:%M"),
                    "duration_min": round(cur_focus_count * interval / 60),
                })
            cur_focus_start = ts
            cur_focus_cat = cat
            cur_focus_count = 1
        else:
            if cur_focus_start is None:
                cur_focus_start = ts
                cur_focus_cat = cat
            cur_focus_count += 1

        prev_ts = ts
        prev_cat = cat

    # 最后一段
    if cur_focus_count * interval >= 900:
        patterns["focus_sessions"].append({
            "category": cur_focus_cat,
            "start": cur_focus_start.strftime("%H:%M"),
            "duration_min": round(cur_focus_count * interval / 60),
        })

    # 最长专注段
    if patterns["focus_sessions"]:
        patterns["longest_focus"] = max(patterns["focus_sessions"], key=lambda x: x["duration_min"])

    # 工作强度曲线（按小时聚合）
    hour_counts = {}
    for act in activities:
        try:
            h = int(act["timestamp"][11:13])
            hour_counts[h] = hour_counts.get(h, 0) + 1
        except (ValueError, IndexError):
            pass
    for h in sorted(hour_counts.keys()):
        patterns["intensity_curve"].append({
            "hour": f"{h:02d}:00",
            "count": hour_counts[h],
            "level": "high" if hour_counts[h] >= 10 else ("medium" if hour_counts[h] >= 5 else "low"),
        })

    return patterns


def _build_activity_timeline_data(activities: list) -> list[dict]:
    """构建包含 ai_detail 和 windows_json 的完整时间线数据（用于深度分析）"""
    import json as _json
    timeline = []
    for act in activities:
        item = {
            "time": act["timestamp"][11:16] if len(act["timestamp"]) > 16 else act["timestamp"],
            "category": act["category"],
            "app": get_display_name(act["app_name"]),
            "summary": act.get("summary", ""),
            "detail": act.get("ai_detail", ""),
        }
        # 解析 windows_json 获取多窗口信息
        win_json = act.get("windows_json", "[]")
        try:
            windows = _json.loads(win_json) if win_json else []
            if windows:
                item["windows"] = [
                    {
                        "app": w.get("app_name", ""),
                        "title": w.get("window_title", ""),
                        "foreground": w.get("is_foreground", False),
                        "desc": w.get("description", ""),
                    }
                    for w in windows
                ]
        except Exception:
            pass
        timeline.append(item)
    return timeline
