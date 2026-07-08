import logging
import re

from flask import Blueprint, jsonify, request

from routes.deps import safe_error
import routes.deps as deps
import config

logger = logging.getLogger(__name__)

bp = Blueprint('agent', __name__)

# ── 首页 AI 洞察缓存（按日期隔离，避免跨天数据被错误复用）──
# 缓存 key 为 (target_date,)，value 为 {"text","structured","timestamp"}
_overview_cache: dict[tuple, dict] = {}
_OVERVIEW_CACHE_TTL = 300  # 5 分钟缓存


def _parse_overview_json(raw: str) -> dict | None:
    """解析 AI 返回的结构化 JSON，失败返回 None"""
    import json as _json
    import re as _re
    import unicodedata as _ucd

    def _is_emoji(ch: str) -> bool:
        """判断单个字符是否为 emoji（覆盖常用 emoji Unicode 区块）"""
        cp = ord(ch)
        if 0x2300 <= cp <= 0x23FF:
            return True
        if 0x2600 <= cp <= 0x27BF:
            return True
        if 0x2B00 <= cp <= 0x2BFF:
            return True
        if 0x1F000 <= cp <= 0x1F9FF:
            return True
        if 0x1FA00 <= cp <= 0x1FAFF:
            return True
        if 0xFE00 <= cp <= 0xFE0F:
            return True  # variation selectors
        cat = _ucd.category(ch)
        return cat == "So"  # other symbols

    def _clean_tag_text(text: str, tag_type: str = "mood") -> str | None:
        """清理标签：保留 1 个前导 emoji，确保有文字；若无 emoji 则按类型补默认 emoji"""
        default_emojis = {
            "mood": "🌸",
            "care": "🧡",
            "achievement": "🌿",
            "reminder": "💡",
        }
        chars = list(text.strip())
        # 去掉前导空白
        while chars and chars[0].isspace():
            chars.pop(0)
        # 提取 1 个前导 emoji（如有多个只取第一个）
        leading_emoji = ""
        if chars and _is_emoji(chars[0]):
            leading_emoji = chars.pop(0)
            # 跳过紧跟的额外 emoji/空白
            while chars and (_is_emoji(chars[0]) or chars[0].isspace()):
                chars.pop(0)
        # 去掉尾部 emoji/空白
        while chars and (_is_emoji(chars[-1]) or chars[-1].isspace()):
            chars.pop()
        cleaned = "".join(chars).strip()
        # 必须包含至少一个文字/数字字符
        if not cleaned or not any(c.isalnum() or _ucd.category(c).startswith("C") for c in cleaned):
            return None
        # 没有前导 emoji 时按类型补一个
        if not leading_emoji:
            leading_emoji = default_emojis.get(tag_type, "✨")
        return f"{leading_emoji}{cleaned}"
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
            cleaned_text = _clean_tag_text(str(t["text"]), tag_type=t_type)
            if cleaned_text:
                cleaned_tags.append({"type": t_type, "text": cleaned_text})
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
    """基于今日实际活动数据，生成首页 AI 洞察总结（5-8 句朋友式小作文）"""
    import time as _time
    from datetime import date as _date
    now = _time.time()
    target_date = request.args.get("date", _date.today().isoformat())
    # 缓存按日期隔离：key 为 (target_date,)，避免跨天数据被错误复用
    cache_key = (target_date,)
    cached = _overview_cache.get(cache_key)
    force_refresh = request.args.get("refresh", "") == "1"
    if (not force_refresh and cached and cached.get("text")
            and (now - cached.get("timestamp", 0.0)) < _OVERVIEW_CACHE_TTL):
        if cached.get("structured"):
            return jsonify({
                "summary": cached["structured"].get("headline", ""),
                "structured": cached["structured"],
            })
        return jsonify({"summary": cached["text"]})

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
        from datetime import datetime as _datetime, time as _time
        _flush_pending_commits()
        activities = get_activities(target_date, target_date)
        if not activities:
            return jsonify({"summary": ""})

        # ── 时间进度感知 ──
        now = _datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        day_progress_pct = round((current_hour * 60 + current_minute) / (24 * 60) * 100)

        # 判断当前时段（用户自定义 7 段划分）
        if 6 <= current_hour < 8:
            time_period = "早晨"
            is_early = True
            time_context = f"现在是{time_period}{current_hour:02d}:{current_minute:02d}，一天才刚开始{day_progress_pct}%，大部分工作时间还在后面。"
        elif 8 <= current_hour < 11:
            time_period = "上午"
            is_early = True
            time_context = f"现在是{time_period}{current_hour:02d}:{current_minute:02d}，一天刚过{day_progress_pct}%，才刚开始进入工作状态。"
        elif 11 <= current_hour < 14:
            time_period = "中午"
            is_early = current_hour < 12
            time_context = f"现在是{time_period}{current_hour:02d}:{current_minute:02d}，一天过了{day_progress_pct}%，到午休时间了。"
        elif 14 <= current_hour < 19:
            time_period = "下午"
            is_early = False
            time_context = f"现在是{time_period}{current_hour:02d}:{current_minute:02d}，一天过了{day_progress_pct}%，正是工作黄金时段。"
        elif 19 <= current_hour < 22:
            time_period = "晚间"
            is_early = False
            time_context = f"现在是{time_period}{current_hour:02d}:{current_minute:02d}，一天过了{day_progress_pct}%，该收尾或者继续冲刺了。"
        elif 22 <= current_hour < 24:
            time_period = "夜间"
            is_early = False
            time_context = f"现在是{time_period}{current_hour:02d}:{current_minute:02d}，一天快结束了，可以做个总结了。"
        else:  # 00:00-06:00
            time_period = "凌晨"
            is_early = True
            time_context = f"现在是{time_period}{current_hour:02d}:{current_minute:02d}，属于前一天的夜间时段，不要评判效率。"

        # ── 凌晨数据处理（00:00-06:00 的活动属于前一天夜间，不算入"今天刚开始"的数据）──
        # 如果当前时间 >= 06:00，标记凌晨数据为熬夜时段，不以此评判今天效率
        has_overnight_data = False
        if current_hour >= 6:
            morning_cutoff = f"{target_date} 06:00:00"
            original_count = len(activities)
            overnight_acts = [a for a in activities if a.get("timestamp", "") < morning_cutoff]
            daytime_acts = [a for a in activities if a.get("timestamp", "") >= morning_cutoff]
            has_overnight_data = len(overnight_acts) > 0
            logger.info(f"凌晨00:00-06:00数据：{len(overnight_acts)}条，白天数据：{len(daytime_acts)}条")
            # 如果白天数据足够（>=5条或总时长>=10分钟），只用白天数据；否则保留全部但标注
            daytime_total_min = round(sum(a.get("interval_sec", 60) for a in daytime_acts) / 60)
            if len(daytime_acts) >= 5 or daytime_total_min >= 10:
                activities = daytime_acts
            else:
                # 白天数据太少，保留全部，但在prompt里说明凌晨是前一天熬夜
                has_overnight_data = True
            if not activities:
                return jsonify({"summary": ""})

        # 取最近 15 条有 ai_detail 的活动
        detailed = [a for a in activities if a.get("ai_detail")][:15]

        # 构建简洁的数据上下文
        from report import _compute_attention_index, _analyze_work_patterns
        from collections import defaultdict
        acts_sorted = sorted(activities, key=lambda a: a.get("timestamp", ""))
        attention = _compute_attention_index(activities)
        patterns = _analyze_work_patterns(activities)

        # ── 基于过滤后的 activities 重新计算分类和应用统计（保证数据一致性）──
        cats = defaultdict(int)
        app_durations = defaultdict(float)
        for a in activities:
            cat = a.get("category", "其他")
            cats[cat] += 1
            app_name = a.get("app_name", "")
            if app_name:
                app_durations[app_name] += a.get("interval_sec", 60) / 60

        cats = dict(cats)
        top_cats = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:4]
        cat_summary = "、".join(f"{k}{v}条" for k, v in top_cats) if top_cats else "无"

        top_apps = sorted(app_durations.items(), key=lambda x: x[1], reverse=True)[:5]
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

        # 计算更丰富的今日数据（activities 里是 interval_sec，表示单次采样时长）
        total_min = round(sum(a.get("interval_sec", 60) for a in activities) / 60)
        total_h = round(total_min / 60, 1)
        first_ts = acts_sorted[0].get("timestamp", "") if acts_sorted else ""
        first_time = first_ts[11:16] if len(first_ts) > 16 else "--:--"
        last_ts = acts_sorted[-1].get("timestamp", "") if acts_sorted else ""
        last_time = last_ts[11:16] if len(last_ts) > 16 else "--:--"
        top_cat = top_cats[0][0] if top_cats else "无"
        top_cat_pct = round(top_cats[0][1] / sum(cats.values()) * 100) if top_cats and cats else 0
        top_app = top_apps[0] if top_apps else ("无", 0)
        top_app_name = get_display_name(top_app[0]) if top_apps else "无"
        top_app_min = round(top_app[1])
        top_app_pct = round(top_app[1] / total_min * 100) if total_min else 0
        dev_pct = round(cats.get("开发", 0) / sum(cats.values()) * 100) if cats else 0
        app_count = len(app_durations)

        # 每小时分布，找峰值时段
        hour_minutes = defaultdict(int)
        for a in activities:
            ts = a.get("timestamp", "")
            if len(ts) > 13:
                try:
                    h = int(ts[11:13])
                    hour_minutes[h] += a.get("interval_sec", 60) / 60
                except ValueError:
                    pass
        peak_hour = max(hour_minutes.items(), key=lambda x: x[1])[0] if hour_minutes else None
        peak_hour_text = f"{peak_hour:02d}:00-{peak_hour + 1:02d}:00" if peak_hour is not None else "暂无"

        # ── 早期时段特殊语气规则 ──
        early_time_rules = ""
        writing_rule_3 = ""
        overnight_note = ""
        if is_early:
            early_time_rules = (
                f"\n【⚠️ 重要：现在才{time_period}，一天才刚开始！】\n"
                f"- {time_context}\n"
                f'- 绝对禁止说"效率低""效率差""有点散""没进入状态"这类评判全天效率的话！\n'
                f'- headline 必须是鼓励/早安/刚开始的语气，比如"🌱 早上好呀，新的一天开始啦""☕ 刚开工，慢慢来""✨ 今天起步不错哦"。\n'
                f'- story 开头必须提到"现在才{time_period}{current_hour:02d}点多""一天才刚开始"，不要把当前少量数据当成全天总结。\n'
                f'- 可以说"已经工作了{total_min}分钟啦""开局不错""先活动活动"，不要吐槽时长短。\n'
                f'- mood 优先选 warm 或 excited，绝对不要选 scattered 或 tired。\n'
                f'- tags 要以 care 和 achievement 为主，比如"🧡 慢慢来不着急""🌿 开局不错"。\n'
            )
            writing_rule_3 = f"现在是{time_period}，不要做全天效率评判，不要说效率低、有点散，多鼓励，聊到目前为止的进度即可"
        else:
            writing_rule_3 = "数据多就多聊几句；如果总时长很短，可以说今天比较清闲、今天没咋干活，但要结合时间判断"

        if has_overnight_data:
            overnight_note = (
                f'\n【⚠️ 注意：00:00-06:00有{len(overnight_acts)}条活动记录，属于前一天夜间熬夜/晚睡时段】\n'
                f'- 不要把凌晨时段的工作算成"今天的工作效率"来评判！\n'
                f'- 可以关心一句"昨晚熬到挺晚呀"或者"凌晨还在忙，注意休息"，但不要说"今天效率低"。\n'
                f'- 今天的工作从06:00之后才算正式开始。\n'
            )

        prompt = (
            f'下面是你朋友今天（{target_date}）到目前为止的工作数据，请你用"你"来跟TA聊天，像最好的朋友一样。\n'
            f'{early_time_rules}\n'
            f'{overnight_note}\n'
            f'【绝对禁止】\n'
            f'- 不准叫"宝贝/亲爱的/宝宝/好孩子/乖乖/小可爱/宝"等任何肉麻或油腻称呼，统一用"你"。\n'
            f'- 不准说空话、鸡汤、煽情、模板感句子（如"你真的很棒""又是充满希望的一天""加油哦"）。\n'
            f'- 不准泛泛而谈，每个观察必须带上具体数据，但不要列清单。\n'
            f'- 不准自相矛盾：碎片化指数高就不能说"很专注"；总时长短且是晚上才能说"效率一般"。\n'
            f'\n'
            f'【语气要求】\n'
            f'- 活泼、可爱、温馨，像一个会吐槽也会关心你的朋友，自然一点，像微信聊天。\n'
            f'- 可以带 emoji，但不要满屏都是；标签必须同时有文字和 emoji，emoji 只放 1 个且在文字最前面（如"🍃有点散"）。\n'
            f'- 多用口语化表达，"啦/呢/呀/吧/嘛"都可以，不要像在写年终总结。\n'
            f'- 温馨不等于肉麻：可以关心累不累、提醒喝水，但别说教、别油腻。\n'
            f'\n'
            f'【输出格式】必须且只输出下面的 JSON（注意使用英文逗号和英文冒号）：\n'
            f'{{\n'
            f'  "headline": "一句朋友式的总结，20字以内，必须带1个emoji",\n'
            f'  "mood": "proud|tired|focused|balanced|scattered|warm|excited",\n'
            f'  "story": "8-12 句完整的话，像微信聊天一样絮絮叨叨，把小作文写够，深度结合所有数据",\n'
            f'  "tags": [\n'
            f'    {{"type": "mood|care|achievement|reminder", "text": "🍃带1个emoji的可爱标签"}}\n'
            f'  ],\n'
            f'  "tips": ["1 条轻松的小建议，像朋友随口一提，不要说教"]\n'
            f'}}\n'
            f'\n'
            f'mood 只能选一个：proud（成就感）、tired（累了）、focused（专注）、balanced（平衡）、scattered（有点散）、warm（温暖）、excited（兴奋）。\n'
            f'tags 2-4 个即可，必须覆盖至少两种 type（不要全是 mood）。type 含义：mood 心情（粉紫）、care 关怀（暖橙）、achievement 成就（草绿）、reminder 提醒（浅蓝）。\n'
            f'每个标签的 emoji 要和类型匹配，不要用同一个 emoji 敷衍：mood 用心情类 emoji（如 🌸/😴/🎯），care 用关怀类 emoji（如 🧡/🍵），achievement 用成就类 emoji（如 🌿/🌟），reminder 用提醒类 emoji（如 💡/⏰）。\n'
            f'\n'
            f'【小作文写作要求】\n'
            f'1. 必须覆盖下面全部数据点，并自然嵌入句子：总时长、最早/最晚工作、峰值时段、使用应用数量、主力应用、分类占比、开发占比、专注效率、碎片化指数、深度工作占比、平均会话时长。\n'
            f'2. 句子之间要有衔接，像朋友在连续说话，不要变成"1. 2. 3."列表式总结。\n'
            f'3. {writing_rule_3}\n'
            f'4. 可以有一点小吐槽或小感叹，但要基于数据，不要凭空想象。只根据下方提供的活动详情描述，不要编造未出现的应用或行为。\n'
            f'5. 把数字、百分比、时长用口语化方式说出来，例如"{total_h}小时""{top_app_pct}%""{peak_hour_text}"，让读者一眼能看到重点。\n'
            f'6. 【个性化】如果系统提示中包含了用户画像（角色、工作风格、习惯、应用用途说明、自定义规则），你必须在 story 中自然地引用这些信息。\n'
            f'\n'
            f'【当前时间】{time_period} {current_hour:02d}:{current_minute:02d}，一天进度 {day_progress_pct}%\n'
            f'【今日到目前为止的数据】\n'
            f'总时长：{total_h}小时（{total_min}分钟）\n'
            f'最早开始：{first_time}，最晚记录：{last_time}\n'
            f'峰值时段：{peak_hour_text}\n'
            f'共用到 {app_count} 个应用\n'
            f'主力应用：{top_app_name} {top_app_min}分钟（占{top_app_pct}%）\n'
            f'分类分布：{cat_summary}\n'
            f'主要分类：{top_cat}（占比{top_cat_pct}%），开发类占比{dev_pct}%\n'
            f'工具使用：{app_summary}\n'
            f'注意力碎片化：{attention["fragmentation_index"]}/100，专注效率：{attention["focus_efficiency"]}/100\n'
            f'深度工作占比：{attention["deep_work_ratio"]}%，平均会话：{attention["avg_session_min"]}分钟\n'
            f'{focus_text}\n'
            f'近期活动详情：\n{detail_text}'
        )

        # ── 注入用户画像 + 周级上下文（长记忆）到 system prompt ──
        system_content = "你是工作数据分析助手，根据用户活动数据生成结构化的首页洞察总结。只输出要求的 JSON，不要其他内容。"
        try:
            from context_manager import get_user_profile_context, build_weekly_context
            user_ctx = get_user_profile_context()
            weekly_ctx = build_weekly_context(7)
            parts = []
            if user_ctx:
                parts.append(f"用户画像：{user_ctx}")
            if weekly_ctx and len(weekly_ctx) > 50:
                parts.append(f"近一周上下文：\n{weekly_ctx}")
            if parts:
                system_content += "\n\n" + "\n\n".join(parts)
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
            timeout=httpx.Timeout(30.0, connect=5.0),
        )
        response = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
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
            _overview_cache[cache_key] = {
                "text": text, "structured": structured, "timestamp": now,
            }
            return jsonify({
                "summary": structured.get("headline", ""),
                "structured": structured,
            })

        # fallback：把整段文字当作 summary
        _overview_cache[cache_key] = {
            "text": text, "structured": None, "timestamp": now,
        }
        return jsonify({"summary": text})

    except Exception as e:
        # 异常日志脱敏：只记录异常类型，避免把可能含密钥/敏感上下文的错误串直接落盘
        logger.warning(f"overview-summary 生成失败: {type(e).__name__}")
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
        # 异常日志脱敏：仅记录异常类型，避免把可能含 api_key 的错误串直接落盘
        logger.error(f"AI connection test failed: {type(e).__name__}")
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
