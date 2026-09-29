"""分类规则重跑 API — arbtt 风格

提供预览（dry_run）、执行、状态查询接口，所有接口必须 check_token 鉴权。
错误处理统一使用 safe_error 脱敏，避免泄露内部堆栈。
"""
import logging
import re

from flask import Blueprint, request, jsonify

from routes.deps import check_token, safe_error
from reclassify_service import (
    reclassify_batch,
    reclassify_app,
    get_reclassify_preview,
    reclassify_history,
    get_status,
)

logger = logging.getLogger(__name__)

bp = Blueprint('reclassify', __name__, url_prefix='/api/reclassify')

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _unauthorized():
    return jsonify({"error": "Unauthorized"}), 401


def _parse_body() -> dict:
    """安全解析 JSON body，非 dict 或异常时返回空 dict"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {}
    return data


def _validate_date(d: str | None) -> str | None:
    """校验 YYYY-MM-DD 格式，非法返回 None"""
    if not d:
        return None
    d = str(d).strip()
    return d if _DATE_RE.match(d) else None


@bp.route('/preview', methods=['POST'])
def preview_reclassify():
    """预览重分类结果（不写库）

    Body: {date?: 'YYYY-MM-DD', app_name?: str}
    返回: {total, would_change, changes: [...], truncated, by_category}
    """
    if not check_token(request):
        return _unauthorized()

    data = _parse_body()
    target_date = _validate_date(data.get("date"))
    app_name = (data.get("app_name") or "").strip() or None

    try:
        result = get_reclassify_preview(target_date=target_date, app_name=app_name)
        return jsonify(result)
    except Exception as e:
        logger.error("预览重分类失败: %s", e, exc_info=True)
        return jsonify({"error": safe_error(e, "预览失败，请稍后重试")}), 500


@bp.route('/execute', methods=['POST'])
def execute_reclassify():
    """执行重分类（写库）

    Body: {date?: str, app_name?: str, days?: int}
    - 优先级：date > app_name > days
    - 三者均为空时重分类全部 activities

    返回: {total, changed, by_category, dry_run: false}
    """
    if not check_token(request):
        return _unauthorized()

    data = _parse_body()
    target_date = _validate_date(data.get("date"))
    app_name = (data.get("app_name") or "").strip() or None

    # days 解析：非正整数视为未提供
    days_raw = data.get("days")
    days = None
    if days_raw is not None:
        try:
            days = int(days_raw)
            if days <= 0:
                days = None
        except (TypeError, ValueError):
            days = None

    try:
        if target_date or app_name:
            # 指定日期或应用时走 batch 分支
            result = reclassify_batch(
                target_date=target_date,
                app_name=app_name,
                dry_run=False,
            )
        elif days is not None:
            result = reclassify_history(days=days)
        else:
            # 全量重分类
            result = reclassify_batch(dry_run=False)
        return jsonify(result)
    except Exception as e:
        logger.error("执行重分类失败: %s", e, exc_info=True)
        return jsonify({"error": safe_error(e, "重分类执行失败，请稍后重试")}), 500


@bp.route('/app', methods=['POST'])
def execute_reclassify_app():
    """仅重分类指定应用的所有记录

    Body: {app_name: str, dry_run?: bool}
    """
    if not check_token(request):
        return _unauthorized()

    data = _parse_body()
    app_name = (data.get("app_name") or "").strip()
    if not app_name:
        return jsonify({"error": "app_name 不能为空"}), 400
    dry_run = bool(data.get("dry_run", False))

    try:
        result = reclassify_app(app_name=app_name, dry_run=dry_run)
        return jsonify(result)
    except Exception as e:
        logger.error("按应用重分类失败: %s", e, exc_info=True)
        return jsonify({"error": safe_error(e, "重分类失败，请稍后重试")}), 500


@bp.route('/status', methods=['GET'])
def reclassify_status():
    """返回分类规则统计

    - 各分类的记录数分布
    - 总记录数、独立应用数
    - 批处理参数（batch_size, preview_limit）
    """
    if not check_token(request):
        return _unauthorized()

    try:
        return jsonify(get_status())
    except Exception as e:
        logger.error("获取重分类状态失败: %s", e, exc_info=True)
        return jsonify({"error": safe_error(e, "状态查询失败")}), 500
