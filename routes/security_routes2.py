"""P131-P139: 企业安全 API"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import enterprise_security as es

bp = Blueprint('security_routes2', __name__)


@bp.route("/api/security/audit-logs")
def security_audit_logs():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    action = request.args.get("action", "")
    limit = int(request.args.get("limit", "100"))
    return jsonify({"logs": es.get_audit_logs(action, limit=limit)})


@bp.route("/api/security/audit-logs/verify")
def security_audit_verify():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(es.verify_audit_integrity())


@bp.route("/api/security/roles")
def security_roles():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"roles": es.list_roles()})


@bp.route("/api/security/roles/assign", methods=["POST"])
def security_assign_role():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    ok = es.assign_role(data.get("user", ""), data.get("role", ""))
    return jsonify({"status": "ok" if ok else "failed"})


@bp.route("/api/security/permissions/<user>")
def security_permissions(user):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"user": user, "permissions": list(es.get_user_permissions(user))})


@bp.route("/api/security/classify", methods=["POST"])
def security_classify():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    level = es.classify_data(data.get("type", ""), data.get("content", ""))
    return jsonify({"level": level, "info": es.get_classification_info(level)})


@bp.route("/api/security/discover", methods=["POST"])
def security_discover():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    findings = es.discover_sensitive_data(data.get("text", ""))
    return jsonify({"findings": findings, "count": len(findings)})


@bp.route("/api/security/redact", methods=["POST"])
def security_redact():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    pipeline = es.RedactionPipeline()
    return jsonify(pipeline.process(data.get("text", "")))


@bp.route("/api/security/compliance/check")
def security_compliance():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(es.run_compliance_check())


@bp.route("/api/security/baseline")
def security_baseline():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(es.security_baseline_check())


@bp.route("/api/security/keys/status")
def security_keys_status():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify(es.get_key_status())


@bp.route("/api/security/keys/rotate", methods=["POST"])
def security_keys_rotate():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    key_name = data.get("name", "")
    new_key = es.rotate_key(key_name)
    return jsonify({"status": "ok", "rotated": True, "preview": new_key[:8] + "..."})


@bp.route("/api/security/incidents")
def security_incidents():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    status = request.args.get("status", "")
    return jsonify({"incidents": es.get_incidents(status)})


@bp.route("/api/security/incidents", methods=["POST"])
def security_report_incident():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    inc_id = es.report_incident(
        data.get("type", ""),
        data.get("severity", "high"),
        data.get("description", ""),
        data.get("context")
    )
    return jsonify({"id": inc_id})


@bp.route("/api/security/incidents/<int:iid>/resolve", methods=["POST"])
def security_resolve_incident(iid):
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    ok = es.resolve_incident(f"inc_{iid}", data.get("resolution", ""))
    return jsonify({"status": "ok" if ok else "not_found"})
