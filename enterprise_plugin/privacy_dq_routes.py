"""P381-P400: 隐私+数据血缘+元数据+数据质量路由"""
from flask import Blueprint, request, jsonify
from privacy_data_quality import (
    _pii, _redact, _anon, _dsr, _consent,
    _lineage, _lineage_viz, _impact, _catalog, _meta_version,
    _dq_rules, _dq_scorer, _dq_monitor, _pia,
)

bp = Blueprint("privacy_dq", __name__, url_prefix="/api/privacy-dq")


@bp.route("/pii/scan", methods=["POST"])
def pii_scan():
    data = request.get_json(silent=True) or {}
    return jsonify({"findings": _pii.scan(data.get("text", ""))})


@bp.route("/pii/scan-dict", methods=["POST"])
def pii_scan_dict():
    data = request.get_json(silent=True) or {}
    return jsonify(_pii.scan_dict(data.get("data", {})))


@bp.route("/redact", methods=["POST"])
def redact_text():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    findings = _pii.scan(text)
    return jsonify({"redacted": _redact.redact(text, findings),
                    "findings_count": len(findings)})


@bp.route("/anonymize", methods=["POST"])
def anonymize():
    data = request.get_json(silent=True) or {}
    method = data.get("method", "hash")
    value = data.get("value", "")
    if method == "hash":
        return jsonify({"result": _anon.hash_anonymize(value, data.get("salt", ""))})
    elif method == "generalize":
        return jsonify({"result": _anon.generalize(value, int(data.get("level", 1)))})
    elif method == "perturb":
        return jsonify({"result": _anon.perturb(float(value), float(data.get("noise", 0.1)))})
    return jsonify({"error": "未知方法"})


@bp.route("/dsr/create", methods=["POST"])
def dsr_create():
    data = request.get_json(silent=True) or {}
    return jsonify(_dsr.create(data.get("user_id", ""), data.get("type", "access"), data.get("details")))


@bp.route("/dsr/<request_id>/process", methods=["POST"])
def dsr_process(request_id: str):
    data = request.get_json(silent=True) or {}
    return jsonify(_dsr.process(request_id, data.get("status", "completed")))


@bp.route("/dsr/list", methods=["GET"])
def dsr_list():
    return jsonify({"requests": _dsr.list_requests(request.args.get("user_id"))})


@bp.route("/consent/grant", methods=["POST"])
def consent_grant():
    data = request.get_json(silent=True) or {}
    _consent.grant(data.get("user_id", ""), data.get("purpose", ""), data.get("basis", "consent"))
    return jsonify({"status": "ok"})


@bp.route("/consent/withdraw", methods=["POST"])
def consent_withdraw():
    data = request.get_json(silent=True) or {}
    return jsonify(_consent.withdraw(data.get("user_id", ""), data.get("purpose", "")))


@bp.route("/consent/check", methods=["GET"])
def consent_check():
    return jsonify({"granted": _consent.check(
        request.args.get("user_id", ""), request.args.get("purpose", ""))})


@bp.route("/consent/<user_id>", methods=["GET"])
def consent_list(user_id: str):
    return jsonify(_consent.list_consents(user_id))


@bp.route("/lineage/node", methods=["POST"])
def lineage_add_node():
    data = request.get_json(silent=True) or {}
    _lineage.add_node(data.get("node_id", ""), data.get("type", ""), data.get("metadata"))
    return jsonify({"status": "ok"})


@bp.route("/lineage/edge", methods=["POST"])
def lineage_add_edge():
    data = request.get_json(silent=True) or {}
    _lineage.add_edge(data.get("src", ""), data.get("dst", ""),
                      data.get("transformation", ""), data.get("metadata"))
    return jsonify({"status": "ok"})


@bp.route("/lineage/<node_id>", methods=["GET"])
def lineage_get(node_id: str):
    return jsonify(_lineage.get_full_lineage(node_id, request.args.get("direction", "both")))


@bp.route("/lineage/visualize", methods=["GET"])
def lineage_viz():
    fmt = request.args.get("format", "d3")
    if fmt == "dot":
        return jsonify({"dot": _lineage_viz.to_dot_format(_lineage)})
    return jsonify(_lineage_viz.to_d3_format(_lineage))


@bp.route("/impact/<node_id>", methods=["GET"])
def impact_analyze(node_id: str):
    return jsonify(_impact.analyze(_lineage, node_id))


@bp.route("/catalog/register", methods=["POST"])
def catalog_register():
    data = request.get_json(silent=True) or {}
    _catalog.register(data.get("asset_id", ""), data.get("name", ""),
                      data.get("type", ""), data.get("owner", ""),
                      data.get("description", ""), data.get("schema"), data.get("tags"))
    return jsonify({"status": "ok"})


@bp.route("/catalog/search", methods=["GET"])
def catalog_search():
    return jsonify({"results": _catalog.search(request.args.get("query", ""))})


@bp.route("/catalog/<asset_id>", methods=["GET"])
def catalog_get(asset_id: str):
    return jsonify(_catalog.get(asset_id) or {"error": "未找到"})


@bp.route("/metadata/version", methods=["POST"])
def meta_version_save():
    data = request.get_json(silent=True) or {}
    return jsonify(_meta_version.save_version(data.get("asset_id", ""), data.get("metadata", {})))


@bp.route("/metadata/version/<asset_id>", methods=["GET"])
def meta_version_history(asset_id: str):
    return jsonify({"history": _meta_version.get_history(asset_id)})


@bp.route("/dq/rules", methods=["GET"])
def dq_rules():
    return jsonify({"rules": _dq_rules.list_rules()})


@bp.route("/dq/score", methods=["POST"])
def dq_score():
    data = request.get_json(silent=True) or {}
    return jsonify(_dq_scorer.score(data.get("scores", {})))


@bp.route("/dq/monitor/record", methods=["POST"])
def dq_monitor_record():
    data = request.get_json(silent=True) or {}
    return jsonify(_dq_monitor.record(data.get("dataset", ""), data.get("scores", {})))


@bp.route("/dq/monitor/history", methods=["GET"])
def dq_monitor_history():
    return jsonify({"history": _dq_monitor.get_history(
        request.args.get("dataset"), int(request.args.get("limit", 50)))})


@bp.route("/dq/monitor/alerts", methods=["GET"])
def dq_monitor_alerts():
    return jsonify({"alerts": _dq_monitor.get_alerts()})


@bp.route("/dq/monitor/trend/<dataset>", methods=["GET"])
def dq_monitor_trend(dataset: str):
    return jsonify(_dq_monitor.get_trend(dataset, int(request.args.get("periods", 7))))


@bp.route("/pia/create", methods=["POST"])
def pia_create():
    data = request.get_json(silent=True) or {}
    return jsonify(_pia.create(
        data.get("project", ""), data.get("data_types", []),
        data.get("purposes", []), data.get("recipients", []),
        int(data.get("retention_days", 365))))


@bp.route("/pia/list", methods=["GET"])
def pia_list():
    return jsonify({"assessments": _pia.list_all()})
