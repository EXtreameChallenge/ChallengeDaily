"""
ChallengeDaily — 小黑日报助手满血版 API 路由
对接 xiaohei_core.py 的真实业务逻辑，替换占位假数据。
"""
import json
import logging

from flask import Blueprint, jsonify, request

import xiaohei_core as xc

logger = logging.getLogger(__name__)
bp = Blueprint("xiaohei", __name__, url_prefix="/api/xiaohei")


# ── AI 工作记录 ────────────────────────────────────────────

@bp.route("/work-records", methods=["GET"])
def list_work_records():
    day = request.args.get("date")
    category = request.args.get("category")
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))
    records = xc.list_work_records(day=day, category=category, limit=limit, offset=offset)
    return jsonify({"items": records, "total": len(records)})


@bp.route("/work-records", methods=["POST"])
def create_work_record():
    data = request.get_json(silent=True) or {}
    return jsonify(xc.create_work_record(data))


@bp.route("/work-records/<int:rid>", methods=["PUT"])
def update_work_record(rid):
    data = request.get_json(silent=True) or {}
    return jsonify(xc.update_work_record(rid, data))


@bp.route("/work-records/<int:rid>", methods=["DELETE"])
def delete_work_record(rid):
    return jsonify(xc.delete_work_record(rid))


@bp.route("/work-records/daily-summary", methods=["GET"])
def work_records_daily_summary():
    day = request.args.get("date")
    return jsonify(xc.get_work_records_daily_summary(day))


@bp.route("/work-records/extract", methods=["POST"])
def extract_work_records():
    """从截图 activities 提取工作记录（一键生成）"""
    data = request.get_json(silent=True) or {}
    return jsonify(xc.extract_work_records_from_activities(data.get("date")))


@bp.route("/work-records/categories", methods=["GET"])
def work_record_categories():
    return jsonify({"categories": xc._WORK_RECORD_CATEGORIES})


# ── 积分计费 ───────────────────────────────────────────────

@bp.route("/points/balance", methods=["GET"])
def points_balance():
    return jsonify(xc.get_points_balance())


@bp.route("/points/consume", methods=["POST"])
def points_consume():
    data = request.get_json(silent=True) or {}
    return jsonify(xc.points_consume(data.get("item", ""), data.get("detail", "")))


@bp.route("/points/grant", methods=["POST"])
def points_grant():
    data = request.get_json(silent=True) or {}
    return jsonify(xc.points_grant(int(data.get("amount", 0)), data.get("item", ""), data.get("detail", "")))


@bp.route("/points/usage-records", methods=["GET"])
def points_usage_records():
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    return jsonify(xc.get_points_usage_records(page, page_size))


@bp.route("/points/pricing", methods=["GET"])
def points_pricing():
    return jsonify({"pricing": xc._FEATURE_PRICING})


# ── 徽章系统 ───────────────────────────────────────────────

@bp.route("/badges", methods=["GET"])
def badges_list():
    return jsonify({"badges": xc.get_badges()})


@bp.route("/badges/track", methods=["POST"])
def badges_track():
    data = request.get_json(silent=True) or {}
    return jsonify(xc.badge_track_progress(data.get("badge_id", ""), int(data.get("add", 1))))


# ── 排行榜 ─────────────────────────────────────────────────

@bp.route("/leaderboard", methods=["GET"])
def leaderboard_daily():
    day = request.args.get("date")
    return jsonify({"rankings": xc.get_leaderboard_daily(day)})


# ── 模板市场 ───────────────────────────────────────────────

@bp.route("/templates", methods=["GET"])
def templates_list():
    category = request.args.get("category")
    return jsonify({"templates": xc.list_templates(category)})


@bp.route("/templates", methods=["POST"])
def templates_create():
    data = request.get_json(silent=True) or {}
    return jsonify(xc.create_template(data))


@bp.route("/templates/<int:tid>/use", methods=["POST"])
def templates_use(tid):
    return jsonify(xc.use_template(tid))


@bp.route("/templates/<int:tid>/apply", methods=["POST"])
def templates_apply(tid):
    """B18：模板应用到当日日报"""
    data = request.get_json(silent=True) or {}
    return jsonify(xc.apply_template_to_daily_report(tid, data.get("date")))


@bp.route("/templates/<int:tid>", methods=["DELETE"])
def templates_delete(tid):
    return jsonify(xc.delete_template(tid))


# ── Token 使用统计 ─────────────────────────────────────────

@bp.route("/token-usage/summary", methods=["GET"])
def token_usage_summary():
    return jsonify(xc.get_token_usage_summary())


@bp.route("/token-usage", methods=["GET"])
def token_usage_list():
    limit = int(request.args.get("limit", 50))
    return jsonify({"records": xc.list_token_usage(limit)})


# ── 帧去重日志 ─────────────────────────────────────────────

@bp.route("/frame-dedup-log", methods=["GET"])
def frame_dedup_log():
    limit = int(request.args.get("limit", 100))
    return jsonify({"logs": xc.list_frame_dedup_log(limit)})


@bp.route("/frame-dedup-log", methods=["DELETE"])
def frame_dedup_log_clear():
    return jsonify(xc.clear_frame_dedup_log())


# ── 数据管理 ───────────────────────────────────────────────

@bp.route("/data/storage-stats", methods=["GET"])
def storage_stats():
    return jsonify(xc.get_storage_stats())


@bp.route("/data/export", methods=["POST"])
def data_export():
    data = request.get_json(silent=True) or {}
    return jsonify(xc.export_backup(data.get("target_dir")))


@bp.route("/data/preview-import", methods=["GET"])
def data_preview_import():
    src = request.args.get("src")
    return jsonify(xc.preview_import_backup(src))


@bp.route("/data/import", methods=["POST"])
def data_import():
    data = request.get_json(silent=True) or {}
    return jsonify(xc.import_backup(data.get("src")))


@bp.route("/data/clear", methods=["POST"])
def data_clear():
    return jsonify(xc.clear_all_data())


# ── 总览（一站式数据，供前端总览页使用）────────────────────

@bp.route("/overview", methods=["GET"])
def overview():
    """聚合总览：积分/徽章/记录数/Token/存储统计，一次拿全"""
    day = request.args.get("date")
    try:
        points = xc.get_points_balance()
        badges = xc.get_badges()
        wr_summary = xc.get_work_records_daily_summary(day)
        token_summary = xc.get_token_usage_summary()
        storage = xc.get_storage_stats()
        dedup = xc.list_frame_dedup_log(5)
        leaderboard = xc.get_leaderboard_daily(day)
        templates = xc.list_templates()
        return jsonify({
            "points": points,
            "badges": badges,
            "work_records_today": {
                "count": wr_summary["count"],
                "total_minutes": wr_summary["total_minutes"],
                "categories": wr_summary["categories"],
            },
            "token_usage": token_summary,
            "storage": storage,
            "recent_dedup_logs": dedup,
            "leaderboard": leaderboard,
            "templates_count": len(templates),
            "date": day or "",
        })
    except Exception as e:
        logger.exception("overview 聚合失败")
        return jsonify({"error": str(e)}), 500
