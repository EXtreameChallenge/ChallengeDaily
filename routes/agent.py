import logging

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
    points = data.get("points") or []
    if not isinstance(tags, list):
        tags = []
    if not isinstance(points, list):
        points = []
    valid_tag_types = {"achievement", "warning", "insight", "suggestion"}
    valid_point_types = {"observation", "suggestion"}
    cleaned_tags = []
    for t in tags[:4]:
        if isinstance(t, dict) and t.get("text"):
            t_type = t.get("type", "insight")
            if t_type not in valid_tag_types:
                t_type = "insight"
            cleaned_tags.append({"type": t_type, "text": str(t["text"]).strip()})
    cleaned_points = []
    for p in points[:3]:
        if isinstance(p, dict) and p.get("text"):
            p_type = p.get("type", "observation")
            if p_type not in valid_point_types:
                p_type = "observation"
            cleaned_points.append({"type": p_type, "text": str(p["text"]).strip()})
    return {
        "headline": str(data.get("headline", "")).strip(),
        "tags": cleaned_tags,
        "points": cleaned_points,
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

        prompt = (
            f"以下是用户今天（{target_date}）的工作数据摘要，请给出有洞见的总结分析。\n"
            f"要求：\n"
            f"1. 不要罗列数据，不要说空话（如'加油''继续努力'），要基于数据给出真正的观察和建议。\n"
            f"2. 必须按下面 JSON 格式输出，不要输出其他内容：\n"
            f"{{\n"
            f"  \"headline\": \"一句话核心结论（25字以内）\"，\n"
            f"  \"tags\": [\n"
            f"    {{\"type\": \"achievement|warning|insight|suggestion\"，\"text\": \"3-6字标签\"}}，\n"
            f"    ...（2-4个标签）\n"
            f"  ]，\n"
            f"  \"points\": [\n"
            f"    {{\"type\": \"observation|suggestion\"，\"text\": \"具体观察或建议（40字以内）\"}}，\n"
            f"    ...（2-3条）\n"
            f"  ]\n"
            f"}}\n"
            f"3. type 说明：achievement 表示积极发现（绿色），warning 表示需要注意（橙色），insight 表示洞察（蓝色），suggestion 表示建议（紫色）。\n"
            f"4. 如果某类标签没有，不要硬凑。\n\n"
            f"分类分布：{cat_summary}\n"
            f"工具使用：{app_summary}\n"
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
            max_tokens=300,
            temperature=0.7,
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
