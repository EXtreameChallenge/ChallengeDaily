"""长上下文管理器：分层摘要 + 结构化记忆

参考 MiMo Code 的分层记忆体系，适配 ChallengeDaily 场景：
- 每分钟有 detail 级数据 → 压缩为 hourly digest → 压缩为 daily profile → 汇总为 weekly context
- 用每天 1 次 ~3000 token 的 AI 调用，换取后续分析中都能理解用户长期工作模式
"""
import json
import logging
import time as _time
from datetime import date, timedelta

import config
from db import get_conn, get_activities, _flush_pending_commits, _execute_with_retry

logger = logging.getLogger(__name__)


# ── 小时级摘要（纯 SQL 聚合，不调 AI，免费） ──

def get_hourly_digest(target_date: str) -> list:
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT CAST(strftime('%H', timestamp) AS INTEGER) AS hour, "
            "  GROUP_CONCAT(DISTINCT category) AS categories, "
            "  COUNT(*) AS record_count, "
            "  GROUP_CONCAT(summary, ' | ') AS summaries "
            "FROM activities WHERE date(timestamp) = ? "
            "GROUP BY hour ORDER BY hour",
            (target_date,),
        ).fetchall()

    digest = []
    for r in rows:
        summaries = r["summaries"] or ""
        if len(summaries) > 500:
            summaries = summaries[:500] + "..."
        digest.append({
            "hour": r["hour"],
            "categories": (r["categories"] or "").split(","),
            "record_count": r["record_count"],
            "summaries": summaries,
        })
    return digest


# ── AI 生成日画像 ──

def generate_daily_profile(target_date: str) -> dict | None:
    """用 AI 为某天生成结构化日画像，失败时返回降级摘要"""
    activities = get_activities(target_date, target_date)
    if not activities:
        return None

    hourly_digest = get_hourly_digest(target_date)

    # 构建精简上下文（控制在 ~3000 token）
    data_desc = f"日期: {target_date}\n总记录数: {len(activities)}\n\n小时级摘要:\n"
    for h in hourly_digest:
        data_desc += f"  {h['hour']:02d}:00 - {h['record_count']}条, 分类: {','.join(h['categories'])}, 活动: {h['summaries'][:200]}\n"

    cat_counts = {}
    app_time = {}
    for a in activities:
        cat = a.get("category", "未知")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        app = a.get("app_name", "")
        app_time[app] = app_time.get(app, 0) + 1

    data_desc += f"\n分类分布: {json.dumps(cat_counts, ensure_ascii=False)}\n"
    data_desc += f"应用Top5: {json.dumps(dict(sorted(app_time.items(), key=lambda x: -x[1])[:5]), ensure_ascii=False)}\n"

    # 注入用户画像（如果有）
    user_ctx = get_user_profile_context()
    if user_ctx:
        data_desc += f"\n用户画像: {user_ctx}\n"

    prompt = (
        f"请分析用户这一天的工作数据，生成结构化的日画像。\n\n{data_desc}\n"
        f"请严格按以下JSON格式输出：\n"
        f'{{"daily_summary":"这一天工作内容的50-80字总结",'
        f'"work_patterns":["模式1:描述","模式2:描述"],'
        f'"top_apps":["应用1","应用2","应用3"],'
        f'"focus_hours":[10,11,14],'
        f'"productivity":"高/中/低",'
        f'"key_insights":["洞察1","洞察2"]}}'
    )

    if not config.AI_API_KEY:
        return _fallback_profile(activities, hourly_digest, cat_counts, app_time)

    try:
        from ai_client import _cb_check, _cb_record_success, _cb_record_failure
        if not _cb_check():
            return _fallback_profile(activities, hourly_digest, cat_counts, app_time)

        from openai import OpenAI
        import httpx
        client = OpenAI(
            api_key=config.AI_API_KEY,
            base_url=config.AI_BASE_URL,
            timeout=httpx.Timeout(15.0, connect=5.0),
        )
        response = client.chat.completions.create(
            model=config.AI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": "你是工作数据分析助手，根据用户活动数据生成结构化的日工作画像。只输出JSON，不要其他内容。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=600,
            temperature=0.2,
        )
        raw = response.choices[0].message.content.strip()
        # 尝试解析 JSON
        result = _parse_json_safe(raw)
        if result and "daily_summary" in result:
            _cb_record_success()
            result["hourly_digest"] = hourly_digest
            return result
    except Exception as e:
        logger.warning(f"generate_daily_profile AI failed: {e}")
        try:
            _cb_record_failure()
        except Exception:
            pass

    return _fallback_profile(activities, hourly_digest, cat_counts, app_time)


def _fallback_profile(activities, hourly_digest, cat_counts, app_time):
    """降级：不调 AI 的纯统计摘要"""
    return {
        "daily_summary": f"共{len(activities)}条记录，主要集中在{','.join(list(cat_counts.keys())[:3])}",
        "work_patterns": [],
        "top_apps": list(dict(sorted(app_time.items(), key=lambda x: -x[1])[:5]).keys()),
        "focus_hours": [h["hour"] for h in hourly_digest if h["record_count"] > 3],
        "productivity": "未知",
        "key_insights": [],
        "hourly_digest": hourly_digest,
    }


def _parse_json_safe(text: str) -> dict | None:
    """安全解析可能包含 markdown 代码块的 JSON"""
    import re
    # 去除 markdown 代码块
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ── 持久化日画像 ──

def save_daily_profile(target_date: str, profile: dict):
    with get_conn() as conn:
        _execute_with_retry(conn,
            "INSERT INTO daily_profiles (date, hourly_digest, daily_summary, work_patterns, top_apps, focus_hours, productivity, key_insights) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(date) DO UPDATE SET "
            "hourly_digest=excluded.hourly_digest, daily_summary=excluded.daily_summary, "
            "work_patterns=excluded.work_patterns, top_apps=excluded.top_apps, "
            "focus_hours=excluded.focus_hours, productivity=excluded.productivity, "
            "key_insights=excluded.key_insights, generated_at=datetime('now','localtime')",
            (
                target_date,
                json.dumps(profile.get("hourly_digest", []), ensure_ascii=False),
                profile.get("daily_summary", ""),
                json.dumps(profile.get("work_patterns", []), ensure_ascii=False),
                json.dumps(profile.get("top_apps", []), ensure_ascii=False),
                json.dumps(profile.get("focus_hours", []), ensure_ascii=False),
                profile.get("productivity", "未知"),
                json.dumps(profile.get("key_insights", []), ensure_ascii=False),
            ),
        )
        conn.commit()


def get_daily_profile(target_date: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM daily_profiles WHERE date = ?", (target_date,)).fetchone()
    return dict(row) if row else None


# ── 周上下文构建（注入所有 AI 调用） ──

def build_weekly_context(days: int = 7) -> str:
    """构建近 N 天的上下文摘要，供 AI 分析时注入 system prompt

    返回结构：精简到 ~2000 token，覆盖一周的工作模式
    """
    profiles = []
    for i in range(days - 1, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM daily_profiles WHERE date = ?", (d,)).fetchone()
        if row:
            profiles.append(dict(row))

    if not profiles:
        return _build_fallback_context(days)

    context_parts = ["=== 近期工作上下文 ==="]
    for p in profiles:
        d = p["date"]
        summary = p.get("daily_summary", "无记录")
        patterns = p.get("work_patterns", "[]")
        apps = p.get("top_apps", "[]")
        try:
            patterns_list = json.loads(patterns) if isinstance(patterns, str) else patterns
            apps_list = json.loads(apps) if isinstance(apps, str) else apps
        except:
            patterns_list, apps_list = [], []
        context_parts.append(f"[{d}] {summary}")
        if patterns_list:
            context_parts.append(f"  模式: {'; '.join(patterns_list[:3])}")
        if apps_list:
            context_parts.append(f"  主用: {', '.join(str(a) for a in apps_list[:5])}")

    return "\n".join(context_parts)


def _build_fallback_context(days: int) -> str:
    """无 daily_profiles 时的降级上下文（纯 SQL 聚合，免费）"""
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    _flush_pending_commits()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT date(timestamp) AS d, COUNT(*) AS cnt, "
            "GROUP_CONCAT(DISTINCT category) AS cats "
            "FROM activities WHERE date(timestamp) >= ? "
            "GROUP BY date(timestamp) ORDER BY d",
            (cutoff,),
        ).fetchall()

    parts = ["=== 近期工作上下文（聚合模式）==="]
    for r in rows:
        parts.append(f"[{r['d']}] {r['cnt']}条记录, 分类: {r['cats']}")
    return "\n".join(parts)


# ── 用户画像 ──

def get_user_profile() -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM user_profile WHERE id = 1").fetchone()
    if row:
        return dict(row)
    return {
        "role_desc": "",
        "work_style": "",
        "habits": "{}",
        "app_overrides": "{}",
        "custom_rules": "[]",
        "updated_at": "",
    }


def save_user_profile(data: dict):
    with get_conn() as conn:
        _execute_with_retry(conn,
            "INSERT INTO user_profile (id, role_desc, work_style, habits, app_overrides, custom_rules, updated_at) "
            "VALUES (1, ?, ?, ?, ?, ?, datetime('now','localtime')) "
            "ON CONFLICT(id) DO UPDATE SET "
            "role_desc=excluded.role_desc, work_style=excluded.work_style, "
            "habits=excluded.habits, app_overrides=excluded.app_overrides, "
            "custom_rules=excluded.custom_rules, updated_at=datetime('now','localtime')",
            (
                data.get("role_desc", ""),
                data.get("work_style", ""),
                json.dumps(data.get("habits", {}), ensure_ascii=False),
                json.dumps(data.get("app_overrides", {}), ensure_ascii=False),
                json.dumps(data.get("custom_rules", []), ensure_ascii=False),
            ),
        )
        conn.commit()


def get_user_profile_context() -> str:
    """生成供 AI 注入的用户画像摘要"""
    profile = get_user_profile()
    parts = []
    if profile.get("role_desc"):
        parts.append(f"角色: {profile['role_desc']}")
    if profile.get("work_style"):
        parts.append(f"工作风格: {profile['work_style']}")

    try:
        habits = json.loads(profile.get("habits", "{}")) if isinstance(profile.get("habits"), str) else profile.get("habits", {})
        if habits:
            parts.append(f"习惯: {json.dumps(habits, ensure_ascii=False)}")
    except:
        pass

    try:
        overrides = json.loads(profile.get("app_overrides", "{}")) if isinstance(profile.get("app_overrides"), str) else profile.get("app_overrides", {})
        if overrides:
            parts.append(f"应用用途说明: {json.dumps(overrides, ensure_ascii=False)}")
    except:
        pass

    try:
        rules = json.loads(profile.get("custom_rules", "[]")) if isinstance(profile.get("custom_rules"), str) else profile.get("custom_rules", [])
        if rules:
            parts.append(f"自定义规则: {json.dumps(rules, ensure_ascii=False)}")
    except:
        pass

    # 加入用户纠正
    corrections = get_user_corrections()
    if corrections:
        corr_parts = [f"{c['app_name']}→{c['correct_category']}" for c in corrections[:10]]
        parts.append(f"分类纠正: {', '.join(corr_parts)}")

    return "; ".join(parts) if parts else ""


# ── 用户纠正记录 ──

def add_user_correction(app_name: str, correct_category: str = "", correct_desc: str = "", notes: str = ""):
    with get_conn() as conn:
        _execute_with_retry(conn,
            "INSERT INTO user_corrections (app_name, correct_category, correct_desc, notes) VALUES (?, ?, ?, ?)",
            (app_name, correct_category, correct_desc, notes),
        )
        conn.commit()


def get_user_corrections() -> list:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM user_corrections ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_user_correction(correction_id: int):
    with get_conn() as conn:
        _execute_with_retry(conn, "DELETE FROM user_corrections WHERE id = ?", (correction_id,))
        conn.commit()


# ── 自动每日画像生成（凌晨触发） ──

_auto_profile_running = False

def auto_generate_yesterday_profile():
    """生成昨天的日画像"""
    global _auto_profile_running
    if _auto_profile_running:
        return
    _auto_profile_running = True
    try:
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        # 仅在尚未生成时才生成
        existing = get_daily_profile(yesterday)
        if existing:
            return
        profile = generate_daily_profile(yesterday)
        if profile:
            save_daily_profile(yesterday, profile)
            logger.info(f"Auto-generated daily profile for {yesterday}")
    except Exception as e:
        logger.error(f"Auto profile generation failed: {e}")
    finally:
        _auto_profile_running = False


def auto_generate_today_profile_if_needed():
    """当天有足够数据时也生成/更新画像（用于首页洞察）"""
    try:
        today = date.today().isoformat()
        existing = get_daily_profile(today)
        # 如果今天还没画像，且有超过30条记录，则生成
        if not existing:
            activities = get_activities(today, today)
            if len(activities) >= 30:
                profile = generate_daily_profile(today)
                if profile:
                    save_daily_profile(today, profile)
                    logger.info(f"Auto-generated daily profile for {today}")
    except Exception as e:
        logger.error(f"Auto today profile generation failed: {e}")
