"""P18-3: 匿名群组对比 API 路由"""
import logging
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import benchmark
from db import get_recent_activities
from datetime import date, timedelta

logger = logging.getLogger(__name__)
bp = Blueprint('benchmark', __name__)


def _compute_user_metrics(days: int = 7) -> dict:
    """从数据库计算用户近 N 天的核心指标"""
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)
        activities = get_recent_activities(days + 1)

        if not activities:
            return {
                "daily_focus_minutes": 0,
                "deep_work_ratio": 0,
                "meeting_ratio": 0,
                "distraction_ratio": 0,
                "streak_days": 0,
            }

        # 按日聚合
        daily_focus = {}
        daily_cats: dict[str, dict[str, float]] = {}
        for act in activities:
            ts = act.get("timestamp", "")
            if not ts:
                continue
            day_key = ts[:10]
            cat = act.get("category", "其他")
            duration = act.get("duration_sec", 0) or 0

            daily_focus[day_key] = daily_focus.get(day_key, 0) + duration / 60
            daily_cats.setdefault(day_key, {})
            daily_cats[day_key][cat] = daily_cats[day_key].get(cat, 0) + duration

        if not daily_focus:
            return {
                "daily_focus_minutes": 0, "deep_work_ratio": 0,
                "meeting_ratio": 0, "distraction_ratio": 0, "streak_days": 0,
            }

        avg_focus = sum(daily_focus.values()) / len(daily_focus)
        # 计算各类占比均值
        deep_cats = {"开发", "文档", "设计", "学习", "数据分析"}
        meeting_cats = {"会议", "沟通", "管理"}
        distraction_cats = {"生活"}  # 生活类视为分心

        deep_ratio_avg = 0
        meeting_ratio_avg = 0
        distraction_ratio_avg = 0
        for day, cats in daily_cats.items():
            total = sum(cats.values()) or 1
            deep_ratio_avg += sum(v for k, v in cats.items() if k in deep_cats) / total
            meeting_ratio_avg += sum(v for k, v in cats.items() if k in meeting_cats) / total
            distraction_ratio_avg += sum(v for k, v in cats.items() if k in distraction_cats) / total
        n = len(daily_cats)
        deep_ratio_avg = deep_ratio_avg / n if n else 0
        meeting_ratio_avg = meeting_ratio_avg / n if n else 0
        distraction_ratio_avg = distraction_ratio_avg / n if n else 0

        # 连续打卡天数：从今天向前数
        streak = 0
        cur = end_date
        while cur.isoformat() in daily_focus:
            streak += 1
            cur -= timedelta(days=1)

        return {
            "daily_focus_minutes": round(avg_focus, 1),
            "deep_work_ratio": round(deep_ratio_avg, 3),
            "meeting_ratio": round(meeting_ratio_avg, 3),
            "distraction_ratio": round(distraction_ratio_avg, 3),
            "streak_days": streak,
        }
    except Exception as e:
        logger.warning(f"计算用户指标失败: {e}")
        return {
            "daily_focus_minutes": 0, "deep_work_ratio": 0,
            "meeting_ratio": 0, "distraction_ratio": 0, "streak_days": 0,
        }


@bp.route("/api/benchmark/occupations")
def occupations():
    """列出所有可选职业类型"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify({"occupations": benchmark.list_occupations()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/benchmark/profile", methods=["GET"])
def get_profile():
    """获取用户基准配置"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify(benchmark.get_profile())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/benchmark/profile", methods=["PUT"])
def update_profile():
    """更新用户基准配置（职业类型 + 群组代码）"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        profile = benchmark.update_profile(
            occupation=data.get("occupation", ""),
            group_code=data.get("group_code", ""),
        )
        return jsonify(profile)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/benchmark/compare")
def compare():
    """对比用户指标与行业基准（参数 days: 近 N 天，默认 7）"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        days = request.args.get("days", "7", type=int)
        days = max(1, min(days, 90))
        metrics = _compute_user_metrics(days)
        profile = benchmark.get_profile()
        occupation = profile.get("occupation", "general")
        result = benchmark.compare_with_benchmark(metrics, occupation)
        result["days"] = days
        result["user_metrics"] = metrics
        # 顺便更新自己在群组中的指标
        try:
            benchmark.update_my_metrics_in_group(metrics)
        except Exception:
            pass
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/benchmark/groups", methods=["GET"])
def list_groups():
    """列出所有本地群组"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify({"groups": benchmark.list_groups()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/benchmark/groups", methods=["POST"])
def create_group():
    """创建一个新群组"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "我的专注小组").strip()
        group = benchmark.create_group(name)
        return jsonify({"group": group}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/benchmark/groups/<code>/join", methods=["POST"])
def join_group(code: str):
    """加入一个群组"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        name = data.get("name", "")
        group = benchmark.join_group(code, name=name)
        return jsonify({"group": group})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/benchmark/groups/<code>/leave", methods=["POST"])
def leave_group(code: str):
    """离开群组"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        ok = benchmark.leave_group(code)
        return jsonify({"ok": ok})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/benchmark/groups/<code>/leaderboard")
def group_leaderboard(code: str):
    """获取群组排行榜"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        result = benchmark.get_group_leaderboard(code)
        if result is None:
            return jsonify({"error": "群组不存在"}), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/benchmark/export")
def export_metrics():
    """导出自己的匿名指标包"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        pack = benchmark.export_my_metrics()
        metrics = _compute_user_metrics(7)
        pack["last_metrics"] = {
            "updated_at": pack["exported_at"],
            **metrics,
        }
        return jsonify(pack)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/benchmark/groups/<code>/import", methods=["POST"])
def import_member(code: str):
    """导入他人分享的指标包到群组"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        pack = request.get_json(silent=True) or {}
        ok = benchmark.import_member_metrics(code, pack)
        if not ok:
            return jsonify({"error": "群组不存在或导入失败"}), 404
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
