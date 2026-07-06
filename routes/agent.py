import logging

from flask import Blueprint, jsonify, request

from routes.deps import safe_error
import routes.deps as deps
import config

logger = logging.getLogger(__name__)

bp = Blueprint('agent', __name__)

# ── 首页 AI 洞察缓存 ──
_overview_cache = {"text": "", "timestamp": 0.0}
_OVERVIEW_CACHE_TTL = 300  # 5 分钟缓存


@bp.route("/api/ai/overview-summary")
def overview_summary():
    """基于今日实际活动数据，生成首页 AI 洞察总结（2-3 句有价值的分析）"""
    import time as _time
    now = _time.time()
    if _overview_cache["text"] and (now - _overview_cache["timestamp"]) < _OVERVIEW_CACHE_TTL:
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
            f"以下是用户今天（{target_date}）的工作数据摘要，请用 2-3 句话给出有洞见的总结分析。\n"
            f"要求：不要罗列数据，不要说空话（如'加油''继续努力'），要基于数据给出真正的观察和建议。\n"
            f"比如：发现专注被频繁打断 → 建议关通知；发现某工具占用过多 → 提醒审视；发现分类分布不均 → 具体指出。\n"
            f"语气像最懂你的朋友，温暖但直说。\n\n"
            f"分类分布：{cat_summary}\n"
            f"工具使用：{app_summary}\n"
            f"注意力碎片化：{attention['fragmentation_index']}/100，专注效率：{attention['focus_efficiency']}/100\n"
            f"深度工作占比：{attention['deep_work_ratio']}%，平均会话：{attention['avg_session_min']}分钟\n"
            f"{focus_text}\n"
            f"近期活动详情：\n{detail_text}"
        )

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

        _overview_cache["text"] = text
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
