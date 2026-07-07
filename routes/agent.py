import logging
import re

from flask import Blueprint, jsonify, request

from routes.deps import safe_error
import routes.deps as deps
import config

logger = logging.getLogger(__name__)

bp = Blueprint('agent', __name__)

# ── 首页 AI 洞察缓存 ──
_overview_cache = {"text": "", "structured": None, "timestamp": 0.0}
_OVERVIEW_CACHE_TTL = 300  # 5 分钟缓存


def _parse_overview_json(raw: str) -> dict | None:
    """解析 AI 返回的结构化 JSON，失败返回 None"""
    import json as _json
    import re as _re
    text = raw.strip()
    if not text:
        return None
    # 去掉可能的 markdown 代码块
    if text.startswith("```"):
        text = _re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=_re.MULTILINE).strip()
    try:
        data = _json.loads(text)
    except Exception:
        # 尝试提取第一个 { ... }
        match = _re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None
        try:
            data = _json.loads(match.group(0))
        except Exception:
            return None
    if not isinstance(data, dict):
        return None
    # 校验必要字段
    if "headline" not in data:
        return None
    # 清理 tags / points
    tags = data.get("tags") or []
    tips = data.get("tips") or []
    if not isinstance(tags, list):
        tags = []
    if not isinstance(tips, list):
        tips = []
    valid_tag_types = {"mood", "care", "achievement", "reminder"}
    cleaned_tags = []
    for t in tags[:4]:
        if isinstance(t, dict) and t.get("text"):
            t_type = t.get("type", "mood")
            if t_type not in valid_tag_types:
                t_type = "mood"
            cleaned_tags.append({"type": t_type, "text": str(t["text"]).strip()})
    cleaned_tips = []
    for tip in tips[:2]:
        if isinstance(tip, str) and tip.strip():
            cleaned_tips.append(tip.strip())
    valid_moods = {"proud", "tired", "focused", "balanced", "scattered", "warm", "excited"}
    raw_mood = str(data.get("mood", "warm")).strip().lower()
    # AI 可能返回多个值用 |/、分隔，取第一个有效值
    mood = "warm"
    for m in re.split(r"[|\/、，, ]", raw_mood):
        if m in valid_moods:
            mood = m
            break
    return {
        "headline": str(data.get("headline", "")).strip(),
        "mood": mood,
        "story": str(data.get("story", "")).strip(),
        "tags": cleaned_tags,
        "tips": cleaned_tips,
    }


@bp.route("/api/ai/overview-summary")
def overview_summary():
    """基于今日实际活动数据，生成首页 AI 洞察总结（2-3 句有价值的分析）"""
    import time as _time
    now = _time.time()
    if _overview_cache["text"] and (now - _overview_cache["timestamp"]) < _OVERVIEW_CACHE_TTL:
        if _overview_cache.get("structured"):
            return jsonify({
                "summary": _overview_cache["structured"].get("headline", ""),
                "structured": _overview_cache["structured"],
            })
        return jsonify({"summary": _overview_cache["text"]})

    if not config.AI_API_KEY:
        return jsonify({"summary": ""})

    # 熔断器检查
    try:
        from ai_client import _cb_check
        if not _cb_check():
            return jsonify({"summary": ""})
    except Exception:
        pass

    try:
        from db import get_activities, get_daily_summary, get_app_usage, _flush_pending_commits
        from datetime import date as _date
        target_date = request.args.get("date", _date.today().isoformat())
        _flush_pending_commits()
        activities = get_activities(target_date, target_date)
        if not activities:
            return jsonify({"summary": ""})

        # 取最近 15 条有 ai_detail 的活动
        detailed = [a for a in activities if a.get("ai_detail")][:15]
        summary_data = get_daily_summary(target_date, target_date)
        app_usage = get_app_usage(target_date, target_date)

        # 构建简洁的数据上下文
        from report import _compute_attention_index, _analyze_work_patterns
        acts_sorted = sorted(activities, key=lambda a: a.get("timestamp", ""))
        attention = _compute_attention_index(activities)
        patterns = _analyze_work_patterns(activities)

        cats = summary_data.get("categories", {}) if summary_data else {}
        top_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:4]
        cat_summary = "、".join(f"{k}{v}条" for k, v in top_cats) if top_cats else "无"

        top_apps = [(a["app_name"], a["duration_min"]) for a in (app_usage or [])][:5]
        from app_tracker import get_display_name
        app_summary = "、".join(f"{get_display_name(n)}{round(d)}分钟" for n, d in top_apps) if top_apps else "无"

        detail_lines = []
        for a in detailed[:8]:
            t = a["timestamp"][11:16] if len(a["timestamp"]) > 16 else ""
            detail_lines.append(f"- {t} [{a['category']}] {a.get('app_name','')}: {a.get('ai_detail','')[:80]}")
        detail_text = "\n".join(detail_lines)

        focus_ses = patterns.get("focus_sessions", [])
        focus_text = ""
        if focus_ses:
            longest = patterns.get("longest_focus", {})
            focus_text = f"最长专注：{longest.get('category','')} {longest.get('duration_min',0)}分钟"

        # 计算更丰富的今日数据
        total_min = sum(a.get("duration_min", 0) for a in activities)
        total_h = round(total_min / 60, 1)
        first_ts = acts_sorted[0].get("timestamp", "") if acts_sorted else ""
        first_time = first_ts[11:16] if len(first_ts) > 16 else "--:--"
        top_cat = top_cats[0][0] if top_cats else "无"
        top_cat_pct = round(top_cats[0][1] / sum(cats.values()) * 100) if top_cats and cats else 0
        top_app = top_apps[0] if top_apps else ("无", 0)
        top_app_name = get_display_name(top_app[0]) if top_apps else "无"
        top_app_min = round(top_app[1])
        top_app_pct = round(top_app[1] / total_min * 100) if total_min else 0
        dev_pct = round(cats.get("开发", 0) / sum(cats.values()) * 100) if cats else 0

        prompt = (
            f"以下是用户今天（{target_date}）的工作数据摘要，请你扮演一个活泼可爱、温暖贴心的朋友，跟用户聊聊今天的工作状态。\n"
            f"要求：\n"
            f"1. 称呼用\"你\"，绝对不要用\"宝贝/亲爱的/好孩子/宝宝\"等肉麻称呼。\n"
            f"2. 语气活泼、可爱、温馨，像知心朋友在分享日常，可以适当带 emoji。\n"
            f"3. story 要写 4-6 句完整的话，深度结合下面所有数据，有小作文感，不要泛泛而谈。\n"
            f"4. 每个观察都要落在具体数据上：总时长、主力应用、分类占比、专注时段、碎片化程度、和昨天/平时的对比等。\n"
            f"5. 基于数据给出 1 条贴心的小建议（tips），活泼自然，不要说教。\n"
            f"6. 配 2-4 个可爱的标签（tags），让用户一眼抓住情绪关键词。\n"
            f"7. mood 只能选其中一个：proud（成就感）、tired（累了）、focused（专注）、balanced（平衡）、scattered（有点散）、warm（温暖）、excited（兴奋）。\n"
            f"8. 必须按下面 JSON 格式输出，不要输出其他内容：\n"
            f"{{\n"
            f"  \"headline\": \"一句活泼温馨的总结（20字以内，可带 emoji）\"，\n"
            f"  \"mood\": \"proud|tired|focused|balanced|scattered|warm|excited\"，\n"
            f"  \"story\": \"4-6 句活泼可爱、深度结合数据的完整文字\"，\n"
            f"  \"tags\": [\n"
            f"    {{\"type\": \"mood|care|achievement|reminder\"，\"text\": \"带 emoji 的可爱标签\"}}，\n"
            f"    ...（2-4个）\n"
            f"  ]，\n"
            f"  \"tips\": [\"一条活泼贴心的小建议\"]\n"
            f"}}\n"
            f"9. tag type 说明：mood 是心情（粉紫色），care 是关怀（暖橙色），achievement 是成就（草绿色），reminder 是提醒（浅蓝色）。\n"
            f"10. 如果数据很少，不要硬夸，轻松地说\"今天比较清闲呢，给自己放个假也超棒的～\"\n\n"
            f"今日总时长：{total_h}小时（{total_min}分钟）\n"
            f"最早开始工作：{first_time}\n"
            f"分类分布：{cat_summary}\n"
            f"主要分类：{top_cat}（占比{top_cat_pct}%），开发类占比{dev_pct}%\n"
            f"工具使用：{app_summary}\n"
            f"主力应用：{top_app_name} {top_app_min}分钟（占今天{top_app_pct}%）\n"
            f"注意力碎片化：{attention['fragmentation_index']}/100，专注效率：{attention['focus_efficiency']}/100\n"
            f"深度工作占比：{attention['deep_work_ratio']}%，平均会话：{attention['avg_session_min']}分钟\n"
            f"{focus_text}\n"
            f"近期活动详情：\n{detail_text}"
        )

        # ── 注入用户画像 + 周级上下文（长记忆） ──
        try:
            from context_manager import get_user_profile_context, build_weekly_context
            user_ctx = get_user_profile_context()
            if user_ctx:
                prompt += f"\n\n用户画像：{user_ctx}"
            weekly_ctx = build_weekly_context(7)
            if weekly_ctx and len(weekly_ctx) > 50:
                prompt += f"\n\n近一周上下文：\n{weekly_ctx}"
        except Exception:
            pass

        # ── 注入 DeepInsight 学术框架分析 ──
        try:
            from deep_insight_engine import build_deep_insight_context
            act_dicts = [
                {"category": a["category"] if isinstance(a, dict) else a["category"],
                 "app_name": a["app_name"] if isinstance(a, dict) else a["app_name"],
                 "timestamp": a["timestamp"] if isinstance(a, dict) else a["timestamp"]}
                for a in activities
            ]
            import config as _cfg
            di_ctx = build_deep_insight_context(act_dicts, interval_sec=_cfg.SCREENSHOT_INTERVAL_SEC)
            if di_ctx:
                prompt += f"\n\n{di_ctx}"
        except Exception:
            pass

        from openai import OpenAI
        import httpx
        client = OpenAI(
            api_key=config.AI_API_KEY,
            base_url=config.AI_BASE_URL,
            timeout=httpx.Timeout(15.0, connect=5.0),
        )
        response = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.72,
        )
        text = response.choices[0].message.content.strip().strip('"')

        # 记录熔断器
        try:
            from ai_client import _cb_record_success
            _cb_record_success()
        except Exception:
            pass

        # 尝试解析结构化 JSON
        structured = _parse_overview_json(text)
        if structured:
            _overview_cache["text"] = text
            _overview_cache["structured"] = structured
            _overview_cache["timestamp"] = now
            return jsonify({
                "summary": structured.get("headline", ""),
                "structured": structured,
            })

        # fallback：把整段文字当作 summary
        _overview_cache["text"] = text
        _overview_cache["structured"] = None
        _overview_cache["timestamp"] = now
        return jsonify({"summary": text})

    except Exception as e:
        logger.warning(f"overview-summary 生成失败: {e}")
        try:
            from ai_client import _cb_record_failure
            _cb_record_failure()
        except Exception:
            pass
        return jsonify({"summary": ""})


@bp.route("/api/ai/test", methods=["POST"])
def test_ai_connection():
    data = request.get_json(force=True) if request.is_json else {}
    api_key = data.get("api_key", "")
    base_url = data.get("base_url", "https://open.bigmodel.cn/api/paas/v4")
    model = data.get("model", "glm-4v-flash")

    # 若前端未传 key（已配置状态下测试），回退到本地加密存储的 key
    if not api_key:
        import config
        api_key = config.AI_API_KEY

    if not api_key:
        return jsonify({"ok": False, "message": "请先填写 API Key"})

    try:
        from openai import OpenAI
        import httpx
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(15.0, connect=5.0),
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "你好"}],
            max_tokens=10,
        )
        reply = response.choices[0].message.content.strip()
        return jsonify({"ok": True, "message": f"连接成功，模型回复：{reply}"})
    except Exception as e:
        logger.error(f"AI connection test failed: {e}")
        error_str = str(e)
        if "401" in error_str or "Unauthorized" in error_str:
            error_msg = "API Key 无效或已过期，请检查后重试"
        elif "404" in error_str:
            error_msg = f"模型 {model} 不存在，请检查模型名称"
        elif "Connection" in error_str or "timeout" in error_str.lower():
            error_msg = "网络连接失败，请检查 Base URL 和网络"
        else:
            error_msg = "AI 服务连接失败，请检查配置"
        return jsonify({"ok": False, "message": error_msg})


@bp.route("/api/capture", methods=["POST"])
def manual_capture():
    if deps.collector is None:
        return jsonify({"status": "error", "message": "采集器未启动"}), 503
    if not deps.collector_lock.acquire(blocking=False):
        return jsonify({"status": "error", "message": "采集器正在工作中，请稍后再试"}), 429
    try:
        result = deps.collector.capture_once()
        if result is None:
            return jsonify({"status": "error", "message": "采集器正在工作中，请稍后再试"}), 429
        return jsonify({"status": "ok", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": safe_error(e, "截图采集失败")}), 500
    finally:
        deps.collector_lock.release()
