"""P181-P189: 数据可视化引擎 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import viz_engine

bp = Blueprint('viz', __name__)


@bp.route("/api/viz/chart-types")
def chart_types():
    return jsonify({"types": viz_engine.ChartRegistry.list_types()})


@bp.route("/api/viz/chart-validate")
def chart_validate():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    ct = request.args.get("type", "")
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(viz_engine.ChartRegistry.validate(ct, data))


@bp.route("/api/viz/series", methods=["GET", "POST"])
def series_manage():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        viz_engine._series_mgr.add_series(
            data.get("name", ""), data.get("data", []),
            data.get("color", ""), data.get("type", "line")
        )
        return jsonify({"status": "ok"})
    return jsonify({"series": viz_engine._series_mgr.get_all()})


@bp.route("/api/viz/series/toggle", methods=["POST"])
def series_toggle():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    visible = viz_engine._series_mgr.toggle_visibility(data.get("name", ""))
    return jsonify({"visible": visible})


@bp.route("/api/viz/axis/configure", methods=["POST"])
def axis_configure():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    viz_engine._axis_config.configure(
        data.get("id", ""), data.get("type", "linear"),
        data.get("label", ""), data.get("min"),
        data.get("max"), data.get("ticks", 5), data.get("format", "{}")
    )
    return jsonify({"status": "ok"})


@bp.route("/api/viz/axis/ticks")
def axis_ticks():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    axis_id = request.args.get("id", "")
    return jsonify({"ticks": viz_engine._axis_config.generate_ticks(axis_id)})


@bp.route("/api/viz/palettes")
def palettes():
    return jsonify({"palettes": {k: v for k, v in viz_engine.ColorMapper._palettes.items()}})


@bp.route("/api/viz/color-map")
def color_map():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    val = float(request.args.get("value", 0))
    vmin = float(request.args.get("min", 0))
    vmax = float(request.args.get("max", 100))
    palette = request.args.get("palette", "diverging")
    return jsonify({"color": viz_engine.ColorMapper.map_value(val, vmin, vmax, palette)})


@bp.route("/api/viz/aggregate", methods=["POST"])
def aggregate():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    result = viz_engine._data_agg.aggregate(
        data.get("data", []), data.get("group_key", ""),
        data.get("value_key", ""), data.get("func", "sum")
    )
    return jsonify({"result": result})


@bp.route("/api/viz/bucketize", methods=["POST"])
def bucketize():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    result = viz_engine._data_agg.bucketize(data.get("data", []), data.get("buckets", 10))
    return jsonify({"result": result})


@bp.route("/api/viz/export")
def export_chart():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    ct = request.args.get("type", "bar")
    fmt = request.args.get("format", "svg")
    data = request.get_json(force=True, silent=True) or {}
    if fmt == "svg":
        from flask import Response
        svg = viz_engine._export_renderer.to_svg(ct, data)
        return Response(svg, mimetype="image/svg+xml")
    elif fmt == "csv":
        from flask import Response
        csv = viz_engine._export_renderer.to_csv(data.get("series", []))
        return Response(csv, mimetype="text/csv")
    return jsonify({"data": viz_engine._export_renderer.to_json(data)})
