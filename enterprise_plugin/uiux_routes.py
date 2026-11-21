"""P151-P159: UI/UX API"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import advanced_uiux as ui

bp = Blueprint('uiux_routes', __name__)


@bp.route("/api/uiux/easings")
def uiux_easings():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"easings": ui.EASING_FUNCTIONS})


@bp.route("/api/uiux/hierarchy")
def uiux_hierarchy():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"hierarchy": ui.VISUAL_HIERARCHY})


@bp.route("/api/uiux/breakpoints")
def uiux_breakpoints():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"breakpoints": ui.BREAKPOINTS})


@bp.route("/api/uiux/responsive-grid")
def uiux_responsive_grid():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    width = int(request.args.get("width", "1280"))
    return jsonify(ui.responsive_grid(width))


@bp.route("/api/uiux/palette/<color>")
def uiux_palette(color):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"palette": ui.generate_palette(color)})


@bp.route("/api/uiux/complementary/<color>")
def uiux_complementary(color):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"colors": ui.generate_complementary(color)})


@bp.route("/api/uiux/typography")
def uiux_typography():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"scale": ui.typography_scale()})


@bp.route("/api/uiux/spacing")
def uiux_spacing():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"spacing": ui.SPACING})


@bp.route("/api/uiux/shadows")
def uiux_shadows():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"shadows": ui.SHADOWS})


@bp.route("/api/uiux/icons/<name>")
def uiux_icon(name):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(ui.get_icon_semantic(name))


@bp.route("/api/uiux/icons")
def uiux_icons():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    category = request.args.get("category", "")
    if category:
        return jsonify({"icons": ui.get_icons_by_category(category)})
    return jsonify({"icons": [{"name": k, **v} for k, v in ui.ICON_SEMANTICS.items()]})
