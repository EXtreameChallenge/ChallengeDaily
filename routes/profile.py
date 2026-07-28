"""用户画像 + 每日画像 + 纠正记录 API"""
import logging

from flask import Blueprint, jsonify, request

from routes.deps import safe_error
import config

logger = logging.getLogger(__name__)

bp = Blueprint('profile', __name__)


@bp.route("/api/profile", methods=["GET"])
def get_profile():
    """获取用户画像"""
    from context_manager import get_user_profile, get_user_corrections
    profile = get_user_profile()
    corrections = get_user_corrections()
    return jsonify({"profile": profile, "corrections": corrections})


@bp.route("/api/profile", methods=["POST"])
def save_profile():
    """保存用户画像"""
    data = request.get_json(force=True) if request.is_json else {}
    if not data:
        return jsonify({"error": "No data provided"}), 400
    from context_manager import save_user_profile
    save_user_profile(data)
    return jsonify({"ok": True})


@bp.route("/api/profile/correction", methods=["POST"])
def add_correction():
    """添加一条分类纠正"""
    data = request.get_json(force=True) if request.is_json else {}
    app_name = data.get("app_name", "")
    if not app_name:
        return jsonify({"error": "app_name is required"}), 400
    from context_manager import add_user_correction
    add_user_correction(
        app_name=app_name,
        correct_category=data.get("correct_category", ""),
        correct_desc=data.get("correct_desc", ""),
        notes=data.get("notes", ""),
    )

    # 自进化：纠正自动转化为分类规则，下次不再犯同样的错
    correct_category = data.get("correct_category", "")
    if correct_category:
        try:
            from db import upsert_app_category_rule
            upsert_app_category_rule(
                app_name=app_name,
                primary_category=correct_category,
                tags=[correct_category],
                display_name=data.get("correct_desc", "") or app_name,
            )
            # 刷新分类器缓存
            from classifier import invalidate_rule_cache
            invalidate_rule_cache()
        except Exception as e:
            logger.warning(f"纠正自动写规则失败: {e}")

    return jsonify({"ok": True})


@bp.route("/api/profile/correction/<int:correction_id>", methods=["DELETE"])
def delete_correction(correction_id):
    """删除一条纠正"""
    from context_manager import delete_user_correction
    delete_user_correction(correction_id)
    return jsonify({"ok": True})


@bp.route("/api/profile/daily/<date_str>")
def get_daily_profile(date_str):
    """获取某天的日画像"""
    from context_manager import get_daily_profile as _get
    profile = _get(date_str)
    if not profile:
        return jsonify({"profile": None})
    return jsonify({"profile": profile})


@bp.route("/api/profile/daily/<date_str>/generate", methods=["POST"])
def generate_daily_profile(date_str):
    """手动触发生成某天的日画像"""
    from context_manager import generate_daily_profile as _gen, save_daily_profile as _save
    profile = _gen(date_str)
    if profile:
        _save(date_str, profile)
        return jsonify({"ok": True, "profile": profile})
    return jsonify({"ok": False, "error": "No data for this date"}), 404


@bp.route("/api/profile/weekly-context")
def get_weekly_context():
    """获取周上下文（供前端调试查看）"""
    days = request.args.get("days", 7, type=int)
    from context_manager import build_weekly_context
    context = build_weekly_context(days)
    return jsonify({"context": context})


@bp.route("/api/profile/distilled", methods=["GET"])
def get_distilled_profile_route():
    """返回聚合后的全周期用户画像（工作习惯、常用软件、工作内容、行为模式、效率趋势）"""
    from context_manager import get_distilled_profile
    return jsonify(get_distilled_profile())


# ─── AI 自我认知分析（累积理解系统） ─────────────────────────

@bp.route("/api/profile/analysis", methods=["GET"])
def get_all_analyses():
    """获取所有 AI 自我认知分析结果"""
    try:
        from db import get_all_profile_analyses
        analyses = get_all_profile_analyses()
        return jsonify({"analyses": analyses})
    except Exception as e:
        logger.error(f"获取分析结果失败: {e}")
        return jsonify({"analyses": [], "error": str(e)}), 500


@bp.route("/api/profile/analysis/<analysis_type>", methods=["GET"])
def get_analysis(analysis_type):
    """获取特定类型的 AI 自我认知分析结果"""
    try:
        from db import get_profile_analysis
        result = get_profile_analysis(analysis_type)
        if not result:
            return jsonify({"analysis": None})
        return jsonify({"analysis": result})
    except Exception as e:
        logger.error(f"获取分析结果失败: {e}")
        return jsonify({"analysis": None, "error": str(e)}), 500


@bp.route("/api/profile/analysis/trigger", methods=["POST"])
def trigger_analysis():
    """触发 AI 自我认知分析计算，将结果写入缓存表。
    
    分析类型：mbti_inference, jungian_functions, big_five, cognitive_style
    计算基于当日+近7天数据，结果持久化到 profile_analysis_cache 表。
    """
    import json
    from datetime import date as _date, timedelta
    from db import get_activities, _flush_pending_commits, upsert_profile_analysis
    import config

    data = request.get_json(force=True) if request.is_json else {}
    # 默认计算所有4种类型，也可指定单个
    target_types = data.get("types", ["mbti_inference", "jungian_functions", "big_five", "cognitive_style"])
    if isinstance(target_types, str):
        target_types = [target_types]

    try:
        _flush_pending_commits()

        # 获取近7天活动数据（更大数据量=更准确推断）
        today = _date.today()
        start = (today - timedelta(days=7)).isoformat()
        end = today.isoformat()
        activities = get_activities(start, end)

        if not activities:
            return jsonify({"ok": False, "error": "没有足够的数据进行分析", "results": {}})

        # 转为 dict 列表
        act_dicts = []
        for a in activities:
            act_dicts.append({
                "category": a.get("category", ""),
                "app_name": a.get("app_name", ""),
                "timestamp": a.get("timestamp", ""),
            })

        from deep_insight_engine import (
            compute_mbti_metrics, compute_jungian_metrics,
            compute_big_five_metrics, compute_cognitive_style_metrics,
        )

        interval_sec = config.SCREENSHOT_INTERVAL_SEC
        results = {}

        compute_map = {
            "mbti_inference": compute_mbti_metrics,
            "jungian_functions": compute_jungian_metrics,
            "big_five": compute_big_five_metrics,
            "cognitive_style": compute_cognitive_style_metrics,
        }

        for atype in target_types:
            fn = compute_map.get(atype)
            if not fn:
                continue
            try:
                if atype in ("mbti_inference", "jungian_functions", "big_five"):
                    # 传空列表作为 historical，避免用自身做历史导致 ZPD/MBTI 新元素检测失效
                    metrics = fn(act_dicts, interval_sec, [])
                else:
                    metrics = fn(act_dicts, interval_sec)

                # 提取置信度
                confidence = 0.0
                if atype == "mbti_inference":
                    confidence = metrics.get("confidence", 0.0)
                else:
                    # 其他类型按数据量估算
                    confidence = min(1.0, len(act_dicts) / 200)

                # 写入缓存
                upsert_profile_analysis(
                    analysis_type=atype,
                    result_json=metrics,
                    confidence=confidence,
                    data_points=len(act_dicts),
                )

                results[atype] = {
                    "metrics": metrics,
                    "confidence": confidence,
                    "data_points": len(act_dicts),
                }
            except Exception as e:
                logger.error(f"分析 {atype} 失败: {e}", exc_info=True)
                results[atype] = {"error": str(e)}

        return jsonify({"ok": True, "results": results})

    except Exception as e:
        logger.error(f"触发分析失败: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500
