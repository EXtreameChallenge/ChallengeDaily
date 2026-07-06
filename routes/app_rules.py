"""
ChallengeDaily Windows 版 — 应用分类规则 API
支持单个应用多标签预设、窗口标题关键词规则、图标获取
"""
import logging
import threading

from flask import Blueprint, jsonify, request, send_from_directory

from config import CATEGORIES, DATA_DIR
from db import (
    get_app_category_rules,
    get_app_category_rule,
    upsert_app_category_rule,
    delete_app_category_rule,
    get_known_apps,
)
from classifier import invalidate_rule_cache, get_app_tags
from icon_extractor import (
    ICON_DIR, get_app_icon_path,
    preload_all_icons, refresh_outdated_icons,
)
from app_tracker import get_display_name

logger = logging.getLogger(__name__)

bp = Blueprint('app_rules', __name__)


@bp.route("/api/app-rules")
def list_rules():
    """获取所有应用分类规则"""
    rules = get_app_category_rules()
    return jsonify({"rules": rules})


@bp.route("/api/app-rules/known")
def list_known_apps():
    """获取所有已记录应用及其规则（用于管理界面）"""
    apps = get_known_apps()
    return jsonify({"apps": apps})


@bp.route("/api/app-rules/<string:app_name>")
def get_rule(app_name):
    """获取单个应用规则"""
    rule = get_app_category_rule(app_name)
    if not rule:
        return jsonify({"error": "规则不存在"}), 404
    return jsonify({"rule": rule})


@bp.route("/api/app-rules/<string:app_name>/tags")
def get_tags(app_name):
    """获取应用候选标签"""
    return jsonify({"app_name": app_name, "tags": get_app_tags(app_name)})


@bp.route("/api/app-rules", methods=["POST"])
def create_or_update_rule():
    """创建或更新应用分类规则"""
    data = request.get_json(force=True) or {}
    app_name = (data.get("app_name") or "").strip()
    if not app_name:
        return jsonify({"error": "应用名不能为空"}), 400

    primary_category = (data.get("primary_category") or "").strip()
    tags = data.get("tags") or []
    window_rules = data.get("window_rules") or {}
    display_name = (data.get("display_name") or "").strip() or get_display_name(app_name)

    # 校验分类合法性
    if primary_category and primary_category not in CATEGORIES:
        return jsonify({"error": f"无效主分类: {primary_category}"}), 400

    valid_tags = [t for t in tags if t in CATEGORIES]
    if primary_category and primary_category not in valid_tags:
        valid_tags = [primary_category] + valid_tags

    valid_window_rules = {}
    for kw, cat in window_rules.items():
        if cat in CATEGORIES:
            valid_window_rules[str(kw).strip()] = cat

    try:
        rule = upsert_app_category_rule(
            app_name=app_name,
            primary_category=primary_category,
            tags=valid_tags,
            window_rules=valid_window_rules,
            display_name=display_name,
        )
        invalidate_rule_cache()
        return jsonify({"status": "ok", "rule": rule})
    except Exception as e:
        logger.error(f"保存应用规则失败: {e}")
        return jsonify({"error": "保存失败"}), 500


@bp.route("/api/app-rules/<string:app_name>", methods=["DELETE"])
def remove_rule(app_name):
    """删除应用分类规则"""
    try:
        deleted = delete_app_category_rule(app_name)
        invalidate_rule_cache()
        return jsonify({"status": "ok", "deleted": deleted})
    except Exception as e:
        logger.error(f"删除应用规则失败: {e}")
        return jsonify({"error": "删除失败"}), 500


@bp.route("/api/icons/<string:app_name>")
def serve_icon(app_name):
    """获取应用图标 PNG（无需 token，图标不敏感）。
    若图标尚未缓存，立即返回项目默认图标，避免前端出现空白图标；
    同时在后台触发提取，下次请求即可命中真实图标缓存。"""
    default_icon = DATA_DIR.parent / "client" / "public" / "icon.png"
    try:
        path = get_app_icon_path(app_name)
        if path and path.exists():
            return send_from_directory(str(path.parent), path.name, mimetype="image/png")
        # 后台异步提取，下次请求即可命中缓存
        threading.Thread(
            target=get_app_icon_path,
            args=(app_name, ""),
            daemon=True,
        ).start()
    except Exception as e:
        logger.warning(f"获取图标失败 {app_name}: {e}")
    # 返回默认项目图标，确保前端永远有图可显
    if default_icon.exists():
        return send_from_directory(str(default_icon.parent), default_icon.name, mimetype="image/png")
    return jsonify({"error": "图标不存在"}), 404


# ── 图标预缓存与刷新 ──

@bp.route("/api/icons/preload", methods=["POST"])
def preload_icons():
    """批量预缓存所有应用图标（后台执行）"""
    data = request.get_json(silent=True) or {}
    force = data.get("force", False)
    # 后台执行，避免阻塞
    def _run():
        result = preload_all_icons(force=force)
        logger.info(f"预缓存结果: {result}")
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "message": "图标预缓存已开始，请稍后刷新查看"})


@bp.route("/api/icons/refresh", methods=["POST"])
def refresh_icons():
    """刷新过期图标缓存（每日扫描）"""
    def _run():
        result = refresh_outdated_icons(max_age_days=1)
        logger.info(f"刷新结果: {result}")
    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "message": "图标刷新已开始"})


@bp.route("/api/icons/status")
def icons_status():
    """获取图标缓存状态"""
    import os
    from pathlib import Path
    icon_files = list(ICON_DIR.glob("*.png"))
    total_size = sum(f.stat().st_size for f in icon_files if f.name != ".icon_version")
    # 检查版本文件
    ver_file = ICON_DIR / ".icon_version"
    ver = ver_file.read_text().strip() if ver_file.exists() else "1"
    return jsonify({
        "cached_count": len(icon_files),
        "total_size_kb": round(total_size / 1024, 1),
        "icon_version": int(ver) if ver.isdigit() else 1,
        "icon_dir": str(ICON_DIR),
    })


