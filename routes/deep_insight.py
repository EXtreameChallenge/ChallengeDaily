"""
DeepInsight API — 基于学术框架的深度分析接口
提供 10 大心理学/教育学/社会学框架的量化指标
"""
import logging

from flask import Blueprint, jsonify, request

from routes.deps import safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('deep_insight', __name__)

# ── 缓存：同一日 5 分钟内不重复计算 ──
_insight_cache = {"date": "", "data": None, "timestamp": 0.0}
_CACHE_TTL = 300  # 5 分钟


@bp.route("/api/deep-insight")
def get_deep_insight():
    """获取指定日期的深度洞察分析（10大框架全量指标）"""
    import time as _time
    from datetime import date as _date
    from db import get_activities, _flush_pending_commits

    target_date = request.args.get("date", _date.today().isoformat())

    # 缓存检查
    now = _time.time()
    if _insight_cache["date"] == target_date and _insight_cache["data"] and (now - _insight_cache["timestamp"]) < _CACHE_TTL:
        return jsonify(_insight_cache["data"])

    try:
        _flush_pending_commits()
        activities = get_activities(target_date, target_date)

        if not activities:
            return jsonify({
                "status": "no_data",
                "message": f"{target_date} 暂无活动数据",
                "frameworks": {},
            })

        # 转换为 dict 列表供 deep_insight_engine 使用
        act_dicts = []
        for a in activities:
            act_dicts.append({
                "category": a["category"] if isinstance(a, dict) else a["category"],
                "app_name": a["app_name"] if isinstance(a, dict) else a["app_name"],
                "timestamp": a["timestamp"] if isinstance(a, dict) else a["timestamp"],
            })

        from deep_insight_engine import generate_deep_insight_report
        import config

        report = generate_deep_insight_report(
            act_dicts,
            interval_sec=config.SCREENSHOT_INTERVAL_SEC,
        )

        result = {
            "status": "ok",
            "date": target_date,
            "data_points": len(act_dicts),
            "frameworks": report.get("frameworks", {}),
            "summary": report.get("summary", {}),
        }

        # 更新缓存
        _insight_cache["date"] = target_date
        _insight_cache["data"] = result
        _insight_cache["timestamp"] = now

        return jsonify(result)

    except Exception as e:
        logger.error(f"DeepInsight 计算失败: {e}", exc_info=True)
        return jsonify({"status": "error", "message": safe_error(e, "深度洞察计算失败")}), 500


@bp.route("/api/deep-insight/frameworks")
def get_frameworks_info():
    """获取10大学术框架的元信息（名称、学者、简介、文献引用）"""
    try:
        from deep_insight_engine import _load_knowledge_base, _FRAMEWORKS, _REFERENCES
        _load_knowledge_base()

        frameworks_info = []
        for fw_id, fw in _FRAMEWORKS.items():
            frameworks_info.append({
                "id": fw_id,
                "name": fw.get("name", fw_id),
                "scholar": fw.get("scholar", ""),
                "description": fw.get("description", ""),
                "year": fw.get("year", ""),
                "metrics": [
                    {"key": m.get("key", ""), "name": m.get("name", ""), "range": m.get("range", ""), "interpretation": m.get("interpretation", "")}
                    for m in fw.get("metrics", [])
                ],
                "reference": fw.get("reference", ""),
            })

        references = []
        for ref_id, citation in _REFERENCES.items():
            references.append({"id": ref_id, "citation": citation})

        return jsonify({
            "frameworks": frameworks_info,
            "references": references,
            "total": len(frameworks_info),
        })

    except Exception as e:
        logger.error(f"获取框架信息失败: {e}", exc_info=True)
        return jsonify({"frameworks": [], "references": [], "total": 0})


@bp.route("/api/deep-insight/context")
def get_deep_insight_context():
    """获取结构化的深度洞察上下文（用于 AI Prompt 注入的文本格式）"""
    from datetime import date as _date
    from db import get_activities, _flush_pending_commits

    target_date = request.args.get("date", _date.today().isoformat())

    try:
        _flush_pending_commits()
        activities = get_activities(target_date, target_date)

        if not activities:
            return jsonify({"context": ""})

        act_dicts = [
            {
                "category": a["category"] if isinstance(a, dict) else a["category"],
                "app_name": a["app_name"] if isinstance(a, dict) else a["app_name"],
                "timestamp": a["timestamp"] if isinstance(a, dict) else a["timestamp"],
            }
            for a in activities
        ]

        from deep_insight_engine import build_deep_insight_context
        import config

        context = build_deep_insight_context(
            act_dicts,
            interval_sec=config.SCREENSHOT_INTERVAL_SEC,
        )

        return jsonify({"context": context, "date": target_date})

    except Exception as e:
        logger.error(f"DeepInsight context 生成失败: {e}", exc_info=True)
        return jsonify({"context": "", "date": target_date})
