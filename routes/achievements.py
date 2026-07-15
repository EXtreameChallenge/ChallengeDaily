"""成就系统 API"""
from flask import Blueprint, jsonify, request
from datetime import date, datetime, timedelta
import logging
import db

logger = logging.getLogger(__name__)
bp = Blueprint('achievements', __name__, url_prefix='/api/achievements')


@bp.route('', methods=['GET'])
def list_achievements():
    achievements = db.get_achievements()
    return jsonify({"achievements": achievements})


@bp.route('/check', methods=['POST'])
def check_achievements():
    """检查并解锁新成就"""
    newly_unlocked = db.check_and_unlock_achievements()
    return jsonify({"unlocked": newly_unlocked})


@bp.route('/quote', methods=['GET'])
def get_quote():
    """获取随机格言"""
    return jsonify({"quote": db.get_random_quote()})


# ── P10-4：赛季成就系统 ──────────────────────────────────

# 赛季定义：每月一个赛季，key 格式 YYYYMM
SEASON_DEFINITIONS = [
    {
        "key": "season_streak_30",
        "name": "本月连续专注 30 天",
        "desc": "赛季内连续 30 天有番茄钟记录",
        "target": 30,
        "metric": "pomodoro_streak",
        "reward": "月度坚持王",
    },
    {
        "key": "season_focus_60h",
        "name": "本月专注 60 小时",
        "desc": "赛季内累计专注时长达到 60 小时",
        "target": 3600,
        "metric": "pomodoro_focus_min",
        "reward": "月度深度工作者",
    },
    {
        "key": "season_pomodoro_100",
        "name": "本月 100 个番茄",
        "desc": "赛季内完成 100 个番茄钟",
        "target": 100,
        "metric": "pomodoro_count",
        "reward": "月度番茄达人",
    },
    {
        "key": "season_quality_a",
        "name": "本月 20 个 A 级番茄",
        "desc": "赛季内获得 20 个 A 级及以上质量评分",
        "target": 20,
        "metric": "pomodoro_quality_a",
        "reward": "月度质量之星",
    },
]


def _get_or_create_season(conn, season_key: str) -> dict:
    """获取或创建赛季记录"""
    row = conn.execute(
        "SELECT * FROM achievement_seasons WHERE season_key=?", (season_key,)
    ).fetchone()
    if row:
        return dict(row)
    # 解析 YYYYMM → 月初/月末
    try:
        year = int(season_key[:4])
        month = int(season_key[4:6])
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(year, month + 1, 1) - timedelta(days=1)
    except Exception:
        # 兜底：本月
        today = date.today()
        start = today.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    conn.execute(
        "INSERT OR IGNORE INTO achievement_seasons (season_key, start_date, end_date) VALUES (?, ?, ?)",
        (season_key, start.isoformat(), end.isoformat()),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM achievement_seasons WHERE season_key=?", (season_key,)
    ).fetchone()
    return dict(row) if row else {"season_key": season_key, "start_date": start.isoformat(), "end_date": end.isoformat()}


def _compute_season_progress(conn, season_key: str, start_date: str, end_date: str) -> list[dict]:
    """计算赛季内各项成就进度"""
    results = []
    # 番茄数据
    rows = conn.execute(
        "SELECT status, duration_min, interrupted_count, start_time "
        "FROM pomodoro_sessions "
        "WHERE date(start_time) BETWEEN ? AND ?",
        (start_date, end_date),
    ).fetchall()

    completed = [r for r in rows if r["status"] == "completed"]
    total_min = sum(r["duration_min"] for r in completed)
    # 质量A：completed 且 interrupted_count == 0
    quality_a = sum(1 for r in completed if (r["interrupted_count"] or 0) == 0)

    # 连续天数（按天集合计算）
    active_days = set()
    for r in completed:
        try:
            active_days.add(r["start_time"][:10])
        except Exception:
            pass
    # 计算最长连续
    sorted_days = sorted(active_days)
    longest_streak = 0
    if sorted_days:
        cur = 1
        for i in range(1, len(sorted_days)):
            prev = datetime.strptime(sorted_days[i - 1], "%Y-%m-%d").date()
            curr = datetime.strptime(sorted_days[i], "%Y-%m-%d").date()
            if (curr - prev).days == 1:
                cur += 1
            else:
                longest_streak = max(longest_streak, cur)
                cur = 1
        longest_streak = max(longest_streak, cur)

    metrics = {
        "pomodoro_streak": longest_streak,
        "pomodoro_focus_min": total_min,
        "pomodoro_count": len(completed),
        "pomodoro_quality_a": quality_a,
    }

    for defn in SEASON_DEFINITIONS:
        cur_val = metrics.get(defn["metric"], 0)
        target = defn["target"]
        pct = min(100, int((cur_val / target) * 100)) if target > 0 else 0
        unlocked = cur_val >= target

        # 同步到 season_achievements
        existing = conn.execute(
            "SELECT id, unlocked_at FROM season_achievements WHERE season_key=? AND achievement_key=?",
            (season_key, defn["key"]),
        ).fetchone()
        if existing:
            if unlocked and not existing["unlocked_at"]:
                conn.execute(
                    "UPDATE season_achievements SET progress=?, unlocked_at=? WHERE id=?",
                    (cur_val, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), existing["id"]),
                )
            else:
                conn.execute(
                    "UPDATE season_achievements SET progress=? WHERE id=?",
                    (cur_val, existing["id"]),
                )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO season_achievements (season_key, achievement_key, progress, unlocked_at) "
                "VALUES (?, ?, ?, ?)",
                (season_key, defn["key"], cur_val,
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S') if unlocked else None),
            )
        conn.commit()

        results.append({
            **defn,
            "current": cur_val,
            "target": target,
            "progress_pct": pct,
            "unlocked": unlocked,
        })
    return results


@bp.route('/season', methods=['GET'])
def get_season():
    """获取当月赛季成就进度

    query: month=YYYYMM（默认当月）
    """
    month_param = request.args.get('month', '').strip()
    if not month_param:
        month_param = date.today().strftime('%Y%m')
    # 校验
    if not (len(month_param) == 6 and month_param.isdigit()):
        return jsonify({"error": "月份格式应为 YYYYMM（如 202607）"}), 400
    try:
        with db.get_conn() as conn:
            season = _get_or_create_season(conn, month_param)
            achievements = _compute_season_progress(conn, month_param, season["start_date"], season["end_date"])
        unlocked_count = sum(1 for a in achievements if a["unlocked"])
        return jsonify({
            "season_key": month_param,
            "start_date": season["start_date"],
            "end_date": season["end_date"],
            "achievements": achievements,
            "unlocked_count": unlocked_count,
            "total_count": len(achievements),
        })
    except Exception as e:
        logger.error(f"赛季查询失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500


@bp.route('/season/history', methods=['GET'])
def season_history():
    """获取最近 N 个月的赛季历史"""
    try:
        months = int(request.args.get('months', '6'))
        months = max(1, min(months, 24))
        from datetime import date as _date
        today = _date.today()
        keys = []
        for i in range(months):
            d = today - timedelta(days=i * 30)
            keys.append(d.strftime('%Y%m'))
        keys.reverse()
        with db.get_conn() as conn:
            results = []
            for k in keys:
                season = _get_or_create_season(conn, k)
                achs = _compute_season_progress(conn, k, season["start_date"], season["end_date"])
                unlocked = sum(1 for a in achs if a["unlocked"])
                results.append({
                    "season_key": k,
                    "unlocked_count": unlocked,
                    "total_count": len(achs),
                    "achievements": [{"key": a["key"], "name": a["name"], "unlocked": a["unlocked"], "current": a["current"], "target": a["target"]} for a in achs],
                })
        return jsonify({"history": results})
    except Exception as e:
        logger.error(f"赛季历史查询失败: {e}", exc_info=True)
        return jsonify({"error": str(e)[:80]}), 500

