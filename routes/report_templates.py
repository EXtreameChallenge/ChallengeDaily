"""P0-3：报告模板管理 API"""
import logging
from datetime import date

from flask import Blueprint, request, jsonify

import report_templates
from routes.deps import check_token, safe_error, validate_date

bp = Blueprint('report_templates', __name__, url_prefix='/api/report/templates')
logger = logging.getLogger(__name__)


@bp.route('', methods=['GET'])
def list_templates():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return jsonify({"templates": report_templates.get_templates()})
    except Exception as e:
        return jsonify({"error": safe_error(e, "获取模板列表失败")}), 500


@bp.route('', methods=['POST'])
def create_template():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    content_md = (data.get("content_md") or "").strip()
    if not name or not content_md:
        return jsonify({"error": "模板名称和内容不能为空"}), 400
    description = (data.get("description") or "").strip()
    is_default = bool(data.get("is_default", False))
    try:
        tid = report_templates.create_template(name, description, content_md, is_default)
        return jsonify({"status": "ok", "id": tid})
    except Exception as e:
        return jsonify({"error": safe_error(e, "创建模板失败")}), 500


@bp.route('/<int:tid>', methods=['PUT'])
def update_template(tid):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    content_md = (data.get("content_md") or "").strip()
    if not name or not content_md:
        return jsonify({"error": "模板名称和内容不能为空"}), 400
    description = (data.get("description") or "").strip()
    is_default = bool(data.get("is_default", False))
    try:
        ok = report_templates.update_template(tid, name, description, content_md, is_default)
        if not ok:
            return jsonify({"error": "模板不存在"}), 404
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": safe_error(e, "更新模板失败")}), 500


@bp.route('/<int:tid>', methods=['DELETE'])
def delete_template(tid):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        ok = report_templates.delete_template(tid)
        if not ok:
            return jsonify({"error": "模板不存在"}), 404
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": safe_error(e, "删除模板失败")}), 500


@bp.route('/<int:tid>/default', methods=['POST'])
def set_default_template(tid):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        ok = report_templates.set_default(tid)
        if not ok:
            return jsonify({"error": "模板不存在"}), 404
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": safe_error(e, "设为默认失败")}), 500


@bp.route('/preview', methods=['POST'])
def preview_template():
    """预览模板渲染结果：用今日数据填充占位符。

    入参: { content_md: str, date?: str }
    """
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    content_md = data.get("content_md", "")
    if not content_md:
        return jsonify({"error": "content_md 不能为空"}), 400
    target_date = (data.get("date") or date.today().isoformat()).strip()
    if not validate_date(target_date):
        return jsonify({"error": "date 格式无效，需 YYYY-MM-DD"}), 400
    try:
        from report import _build_template_context
        context = _build_template_context(target_date)
        rendered = report_templates.render_template(content_md, context)
        return jsonify({"status": "ok", "content": rendered})
    except Exception as e:
        return jsonify({"error": safe_error(e, "预览渲染失败")}), 500
