"""
P961-P1000: 安全加固/加密/审计 路由
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from security_advanced import (
    _crypto, _jwt, _oauth2, _rbac, _abac,
    _security_auditor, _vuln_scanner, _key_rotation, _compliance,
)

bp = Blueprint("security_advanced", __name__, url_prefix="/api/sec-adv")


def _json_body() -> dict:
    return request.get_json(silent=True) or {}


def _arg(name: str, default=None):
    return request.args.get(name, default)


# ═════════ 加密 + 签名 + JWT ═════════

@bp.route("/crypto/encrypt", methods=["POST"])
def crypto_encrypt():
    data = _json_body()
    return jsonify(_crypto.xor_encrypt(data.get("plaintext", ""), data.get("key", "")))


@bp.route("/crypto/decrypt", methods=["POST"])
def crypto_decrypt():
    data = _json_body()
    return jsonify(_crypto.xor_decrypt(data.get("ciphertext", ""), data.get("key", "")))


@bp.route("/crypto/hash", methods=["POST"])
def crypto_hash():
    data = _json_body()
    return jsonify(_crypto.hash_data(data.get("data", ""), data.get("algorithm", "sha256")))


@bp.route("/crypto/hmac/sign", methods=["POST"])
def crypto_hmac_sign():
    data = _json_body()
    return jsonify(_crypto.hmac_sign(
        data.get("data", ""), data.get("key", ""),
        data.get("algorithm", "sha256"),
    ))


@bp.route("/crypto/hmac/verify", methods=["POST"])
def crypto_hmac_verify():
    data = _json_body()
    return jsonify(_crypto.hmac_verify(
        data.get("data", ""), data.get("key", ""),
        data.get("signature", ""),
        data.get("algorithm", "sha256"),
    ))


@bp.route("/jwt/encode", methods=["POST"])
def jwt_encode():
    data = _json_body()
    return jsonify(_jwt.encode(
        data.get("payload", {}),
        int(data.get("expires_in_sec", 3600)),
    ))


@bp.route("/jwt/decode", methods=["POST"])
def jwt_decode():
    data = _json_body()
    return jsonify(_jwt.decode(data.get("token", "")))


@bp.route("/jwt/revoke", methods=["POST"])
def jwt_revoke():
    data = _json_body()
    return jsonify(_jwt.revoke(data.get("token", "")))


# ═════════ OAuth2 + RBAC + ABAC ═════════

@bp.route("/oauth2/clients", methods=["POST"])
def oauth2_register():
    data = _json_body()
    return jsonify(_oauth2.register_client(
        data.get("client_id", ""),
        data.get("client_secret", ""),
        data.get("redirect_uris"),
        data.get("scopes"),
    ))


@bp.route("/oauth2/authorize", methods=["POST"])
def oauth2_authorize():
    data = _json_body()
    return jsonify(_oauth2.authorize(
        data.get("client_id", ""),
        data.get("redirect_uri", ""),
        data.get("scope", "read"),
        data.get("state", ""),
    ))


@bp.route("/oauth2/token", methods=["POST"])
def oauth2_token():
    data = _json_body()
    return jsonify(_oauth2.token(
        data.get("code", ""),
        data.get("client_id", ""),
        data.get("client_secret", ""),
    ))


@bp.route("/oauth2/validate", methods=["GET"])
def oauth2_validate():
    return jsonify(_oauth2.validate(_arg("token", "")))


@bp.route("/rbac/roles", methods=["POST"])
def rbac_create_role():
    data = _json_body()
    return jsonify(_rbac.create_role(data.get("role", ""), data.get("permissions")))


@bp.route("/rbac/assign", methods=["POST"])
def rbac_assign():
    data = _json_body()
    return jsonify(_rbac.assign_role(data.get("user", ""), data.get("role", "")))


@bp.route("/rbac/check", methods=["GET"])
def rbac_check():
    return jsonify(_rbac.check_permission(_arg("user", ""), _arg("permission", "")))


@bp.route("/rbac/roles", methods=["GET"])
def rbac_list():
    return jsonify(_rbac.list_roles())


@bp.route("/rbac/users/<user>/roles", methods=["GET"])
def rbac_user_roles(user):
    return jsonify({"user": user, "roles": _rbac.list_user_roles(user)})


@bp.route("/abac/policies", methods=["POST"])
def abac_add_policy():
    data = _json_body()
    return jsonify(_abac.add_policy(
        name=data.get("name", ""),
        subject_attrs=data.get("subject", {}),
        resource_attrs=data.get("resource", {}),
        action=data.get("action", ""),
        effect=data.get("effect", "allow"),
    ))


@bp.route("/abac/check", methods=["POST"])
def abac_check():
    data = _json_body()
    return jsonify(_abac.check_access(
        data.get("subject", {}),
        data.get("resource", {}),
        data.get("action", ""),
    ))


@bp.route("/abac/policies", methods=["GET"])
def abac_list():
    return jsonify(_abac.list_policies())


# ═════════ 审计 + 漏洞扫描 ═════════

@bp.route("/audit/log", methods=["POST"])
def audit_log():
    data = _json_body()
    return jsonify(_security_auditor.log(
        event_type=data.get("type", ""),
        user=data.get("user", ""),
        resource=data.get("resource", ""),
        action=data.get("action", ""),
        result=data.get("result", "success"),
        metadata=data.get("metadata"),
    ))


@bp.route("/audit/search", methods=["GET"])
def audit_search():
    return jsonify(_security_auditor.search(
        event_type=_arg("type"),
        user=_arg("user"),
        result=_arg("result"),
        limit=int(_arg("limit", 50)),
    ))


@bp.route("/audit/stats", methods=["GET"])
def audit_stats():
    return jsonify(_security_auditor.stats())


@bp.route("/vuln/scan", methods=["POST"])
def vuln_scan():
    data = _json_body()
    return jsonify(_vuln_scanner.scan(data.get("content", "")))


@bp.route("/vuln/rules", methods=["GET"])
def vuln_rules():
    return jsonify(_vuln_scanner.list_rules())


# ═════════ 密钥轮换 + 合规 ═════════

@bp.route("/keys", methods=["POST"])
def keys_create():
    data = _json_body()
    return jsonify(_key_rotation.create_key(data.get("key_id", ""), data.get("value", "")))


@bp.route("/keys/<key_id>/rotate", methods=["POST"])
def keys_rotate(key_id):
    return jsonify(_key_rotation.rotate(key_id))


@bp.route("/keys/<key_id>/check", methods=["GET"])
def keys_check(key_id):
    return jsonify(_key_rotation.check_rotation_needed(key_id))


@bp.route("/keys", methods=["GET"])
def keys_list():
    return jsonify(_key_rotation.list_keys())


@bp.route("/keys/<key_id>/history", methods=["GET"])
def keys_history(key_id):
    return jsonify(_key_rotation.history(key_id))


@bp.route("/compliance/checks", methods=["POST"])
def compliance_register():
    data = _json_body()
    return jsonify(_compliance.register_check(
        data.get("name", ""),
        data.get("description", ""),
        data.get("severity", "medium"),
    ))


@bp.route("/compliance/checks/<name>/run", methods=["POST"])
def compliance_run(name):
    return jsonify(_compliance.run_check(name, _json_body()))


@bp.route("/compliance/checks", methods=["GET"])
def compliance_list():
    return jsonify(_compliance.list_checks())


@bp.route("/compliance/summary", methods=["GET"])
def compliance_summary():
    return jsonify(_compliance.compliance_summary())
