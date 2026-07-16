"""P341-P350: 推荐+A/B测试路由"""
from flask import Blueprint, request, jsonify
from recommendation_ab import (
    _collab_filter, _content_rec, _hybrid_rec, _feedback,
    _ab_test, _grouper, _sig_test, _metrics_tracker, _mvt, _reporter,
)

bp = Blueprint("rec_ab", __name__, url_prefix="/api/rec-ab")


@bp.route("/rec/collab/interact", methods=["POST"])
def rec_collab_interact():
    data = request.get_json(silent=True) or {}
    _collab_filter.add_interaction(data.get("user_id", ""), data.get("item_id", ""))
    return jsonify({"status": "ok"})


@bp.route("/rec/collab/<user_id>", methods=["GET"])
def rec_collab(user_id: str):
    top_k = int(request.args.get("top_k", 10))
    return jsonify({"recommendations": _collab_filter.recommend(user_id, top_k)})


@bp.route("/rec/content/item", methods=["POST"])
def rec_content_item():
    data = request.get_json(silent=True) or {}
    _content_rec.add_item(data.get("item_id", ""), data.get("tags", []), data.get("metadata"))
    return jsonify({"status": "ok"})


@bp.route("/rec/content/preference", methods=["POST"])
def rec_content_pref():
    data = request.get_json(silent=True) or {}
    _content_rec.record_preference(data.get("user_id", ""), data.get("item_id", ""), data.get("weight", 1.0))
    return jsonify({"status": "ok"})


@bp.route("/rec/content/<user_id>", methods=["GET"])
def rec_content(user_id: str):
    return jsonify({"recommendations": _content_rec.recommend(user_id, int(request.args.get("top_k", 10)))})


@bp.route("/rec/hybrid/<user_id>", methods=["GET"])
def rec_hybrid(user_id: str):
    return jsonify({"recommendations": _hybrid_rec.recommend(user_id, int(request.args.get("top_k", 10)))})


@bp.route("/rec/feedback", methods=["POST"])
def rec_feedback():
    data = request.get_json(silent=True) or {}
    _feedback.record(data.get("user_id", ""), data.get("item_id", ""),
                     data.get("action", "click"), data.get("rating"))
    return jsonify({"status": "ok"})


@bp.route("/rec/feedback/stats", methods=["GET"])
def rec_feedback_stats():
    return jsonify(_feedback.get_stats())


@bp.route("/ab/create", methods=["POST"])
def ab_create():
    data = request.get_json(silent=True) or {}
    return jsonify(_ab_test.create(data.get("name", ""), data.get("variants", []), data.get("weights")))


@bp.route("/ab/assign", methods=["POST"])
def ab_assign():
    data = request.get_json(silent=True) or {}
    return jsonify(_ab_test.assign(data.get("experiment", ""), data.get("user_id", "")))


@bp.route("/ab/list", methods=["GET"])
def ab_list():
    return jsonify({"experiments": _ab_test.list_experiments()})


@bp.route("/ab/stop", methods=["POST"])
def ab_stop():
    data = request.get_json(silent=True) or {}
    return jsonify(_ab_test.stop(data.get("name", "")))


@bp.route("/grouper/assign", methods=["POST"])
def grouper_assign():
    data = request.get_json(silent=True) or {}
    group = _grouper.assign(data.get("experiment", ""), data.get("user_id", ""),
                            data.get("strategy", "hash"), int(data.get("num_groups", 2)))
    return jsonify({"group": group})


@bp.route("/grouper/<experiment>", methods=["GET"])
def grouper_get(experiment: str):
    return jsonify({"groups": _grouper.get_groups(experiment)})


@bp.route("/stats/z-test", methods=["POST"])
def stats_ztest():
    data = request.get_json(silent=True) or {}
    return jsonify(_sig_test.z_test(data.get("control", []), data.get("treatment", [])))


@bp.route("/stats/chi-square", methods=["POST"])
def stats_chi():
    data = request.get_json(silent=True) or {}
    return jsonify(_sig_test.chi_square(data.get("observed", [])))


@bp.route("/metrics/record", methods=["POST"])
def metrics_record():
    data = request.get_json(silent=True) or {}
    _metrics_tracker.record(data.get("experiment", ""), data.get("variant", ""), float(data.get("value", 0)))
    return jsonify({"status": "ok"})


@bp.route("/metrics/<experiment>", methods=["GET"])
def metrics_get(experiment: str):
    return jsonify(_metrics_tracker.get_stats(experiment))


@bp.route("/mvt/factor", methods=["POST"])
def mvt_factor():
    data = request.get_json(silent=True) or {}
    _mvt.add_factor(data.get("name", ""), data.get("levels", []))
    return jsonify({"status": "ok"})


@bp.route("/mvt/assign", methods=["POST"])
def mvt_assign():
    data = request.get_json(silent=True) or {}
    return jsonify(_mvt.assign(data.get("user_id", "")))


@bp.route("/mvt/result", methods=["POST"])
def mvt_result():
    data = request.get_json(silent=True) or {}
    _mvt.record_result(data.get("combination", ""), float(data.get("value", 0)))
    return jsonify({"status": "ok"})


@bp.route("/mvt/results", methods=["GET"])
def mvt_results():
    return jsonify(_mvt.get_results())


@bp.route("/report/<experiment>", methods=["GET"])
def report(experiment: str):
    return jsonify(_reporter.generate(experiment, _ab_test, _metrics_tracker))
