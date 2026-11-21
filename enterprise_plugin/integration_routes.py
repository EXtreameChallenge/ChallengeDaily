"""P171-P179: 集成生态扩展 API 路由"""
from flask import Blueprint, jsonify, request
from routes.deps import check_token
import integration_eco

bp = Blueprint('integration', __name__)


@bp.route("/api/integration/webhooks")
def webhooks_list():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"endpoints": integration_eco._webhook.list_endpoints()})


@bp.route("/api/integration/webhooks/register", methods=["POST"])
def webhooks_register():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    integration_eco._webhook.register(
        data.get("name", ""), data.get("url", ""),
        data.get("secret", ""), data.get("headers")
    )
    return jsonify({"status": "ok"})


@bp.route("/api/integration/webhooks/send", methods=["POST"])
def webhooks_send():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    return jsonify(integration_eco._webhook.send(data.get("name", ""), data.get("payload", {})))


@bp.route("/api/integration/webhooks/log")
def webhooks_log():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"logs": integration_eco._webhook.get_delivery_log()})


@bp.route("/api/integration/triggers")
def triggers_list():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"triggers": integration_eco._triggers.list_triggers()})


@bp.route("/api/integration/triggers/fire", methods=["POST"])
def triggers_fire():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    return jsonify({"results": integration_eco._triggers.fire(data.get("event", ""), data.get("context", {}))})


@bp.route("/api/integration/triggers/toggle", methods=["POST"])
def triggers_toggle():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    ok = integration_eco._triggers.toggle(data.get("name", ""), data.get("enabled", True))
    return jsonify({"status": "ok" if ok else "not_found"})


@bp.route("/api/integration/oauth2/providers")
def oauth2_providers():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"providers": integration_eco._oauth2.list_providers()})


@bp.route("/api/integration/oauth2/auth-url")
def oauth2_auth_url():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    provider = request.args.get("provider", "")
    redirect_uri = request.args.get("redirect_uri", "")
    state = request.args.get("state", "")
    return jsonify({"url": integration_eco._oauth2.get_auth_url(provider, redirect_uri, state)})


@bp.route("/api/integration/oauth2/register", methods=["POST"])
def oauth2_register():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    integration_eco._oauth2.register_provider(
        data.get("name", ""), data.get("auth_url", ""),
        data.get("token_url", ""), data.get("client_id", ""),
        data.get("client_secret", ""), data.get("scopes", [])
    )
    return jsonify({"status": "ok"})


@bp.route("/api/integration/send", methods=["POST"])
def integration_send():
    """统一发送: slack/teams/notion/trello/jira"""
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    target = data.get("target", "")
    msg = data.get("message", "")
    if target == "slack":
        return jsonify(integration_eco._slack_send(msg, data.get("channel", "#general"), data.get("webhook_url", "")))
    elif target == "teams":
        return jsonify(integration_eco._teams_send(msg, data.get("webhook_url", "")))
    elif target == "notion":
        return jsonify(integration_eco._notion_send(data.get("title", ""), msg, data.get("database_id", ""), data.get("token", "")))
    elif target == "trello":
        return jsonify(integration_eco._trello_send(data.get("card", ""), data.get("list_id", ""), data.get("api_key", ""), data.get("token", "")))
    elif target == "jira":
        return jsonify(integration_eco._jira_send(data.get("summary", ""), msg, data.get("project", ""), data.get("token", "")))
    return jsonify({"status": "error", "error": "未知目标"})


@bp.route("/api/integration/gateway/routes")
def gateway_routes():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"routes": integration_eco._gateway.list_routes()})


@bp.route("/api/integration/gateway/register", methods=["POST"])
def gateway_register():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(force=True, silent=True) or {}
    integration_eco._gateway.register_route(
        data.get("path", ""), data.get("upstream", ""),
        data.get("rate_limit", 100), data.get("auth_required", True)
    )
    return jsonify({"status": "ok"})


@bp.route("/api/integration/gateway/rate-check")
def gateway_rate_check():
    if not check_token(request):
        return jsonify({"error": "Unauthorized"}), 401
    path = request.args.get("path", "")
    return jsonify(integration_eco._gateway.check_rate_limit(path))
