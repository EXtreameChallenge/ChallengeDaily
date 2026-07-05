import json as _json
import secrets
import logging

from flask import Blueprint, jsonify, request
from datetime import date

from config import BASE_DIR
from file_utils import atomic_write_text, backup_file
from routes.deps import safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('webhooks', __name__)

_WEBHOOK_PATH = BASE_DIR / "data" / "webhooks.json"

from concurrent.futures import ThreadPoolExecutor, as_completed
_webhook_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="wh_push")


def _load_webhooks() -> list:
    if _WEBHOOK_PATH.exists():
        try:
            return _json.loads(_WEBHOOK_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_webhooks(webhooks: list):
    _WEBHOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = _json.dumps(webhooks, ensure_ascii=False, indent=2)
    if _WEBHOOK_PATH.exists():
        backup_file(_WEBHOOK_PATH)
    atomic_write_text(_WEBHOOK_PATH, content)


def _validate_webhook_url(url: str) -> str | None:
    import ipaddress
    from urllib.parse import urlparse
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if not parsed.scheme or parsed.scheme not in ("http", "https"):
        return "Webhook URL 必须使用 http 或 https 协议"

    if hostname in ("localhost", "0.0.0.0"):
        return "不允许使用本地回环地址作为 Webhook"

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_loopback:
            return "不允许使用回环地址作为 Webhook"
        if ip.is_private:
            return "不允许使用内网地址作为 Webhook"
        if ip.is_link_local:
            return "不允许使用链路本地地址作为 Webhook"
        if ip.is_reserved:
            return "不允许使用保留地址作为 Webhook"
        if ip.is_multicast:
            return "不允许使用组播地址作为 Webhook"
        if isinstance(ip, ipaddress.IPv6Address) and ip.is_private:
            return "不允许使用 IPv6 内网地址作为 Webhook"
    except ValueError:
        if hostname.endswith(".local") or hostname.endswith(".localhost"):
            return "不允许使用本地域名作为 Webhook"

    return None


def _build_webhook_payload(wh_type: str, content: str, target_date: str) -> dict:
    safe_content = content[:3500]

    if wh_type == "feishu":
        card_content = _markdown_to_feishu_card(safe_content, target_date)
        return {
            "msg_type": "interactive",
            "card": card_content,
        }

    elif wh_type == "dingtalk":
        return {
            "msgtype": "actionCard",
            "actionCard": {
                "title": f"工作日报 {target_date}",
                "text": f"## 工作日报 {target_date}\n\n{safe_content}",
            },
        }

    elif wh_type == "wecom":
        return {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## 工作日报 {target_date}\n\n{safe_content}",
            },
        }

    else:
        return {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": f"工作日报 {target_date}"}},
                "elements": [{"tag": "markdown", "content": safe_content}],
            },
        }


def _markdown_to_feishu_card(content: str, target_date: str) -> dict:
    lines = content.split("\n")
    card_elements = []

    card_elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"📅 **{target_date} 工作日报**",
        },
    })
    card_elements.append({"tag": "hr"})

    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# ") or stripped.startswith("## "):
            title = stripped.lstrip("#").strip()
            card_elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**{title}**",
                },
            })
            in_table = False
            continue

        if stripped.startswith("|") and "---" in stripped:
            in_table = True
            continue

        if stripped.startswith("|") and in_table:
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            if len(cells) >= 2:
                card_elements.append({
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"- {' | '.join(cells)}",
                    },
                })
            continue

        if stripped.startswith("|") and not in_table:
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            if len(cells) >= 2:
                in_table = True
            continue

        if not stripped:
            in_table = False
            continue

        in_table = False
        card_elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": stripped,
            },
        })

    return {
        "header": {
            "title": {"tag": "plain_text", "content": f"📋 工作日报 {target_date}"},
            "template": "green",
        },
        "elements": card_elements,
    }


def _push_webhook_sync(wh: dict, content: str, target_date: str) -> bool:
    try:
        import urllib.request
        wh_type = wh.get("type", "custom")
        payload = _build_webhook_payload(wh_type, content, target_date)
        data = _json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(wh["url"], data=data, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception:
        logger.warning(f"Webhook push failed for {wh.get('name', wh.get('id'))}")
        return False


def push_all_webhooks(content: str, target_date: str) -> int:
    webhooks = _load_webhooks()
    targets = []
    for wh in webhooks:
        if not wh.get("enabled", True):
            continue
        if "daily_report" not in wh.get("events", ["daily_report"]):
            continue
        if _validate_webhook_url(wh["url"]):
            continue
        targets.append(wh)

    if not targets:
        return 0

    pushed = 0
    futures = {_webhook_executor.submit(_push_webhook_sync, wh, content, target_date): wh for wh in targets}
    for future in as_completed(futures, timeout=len(targets) * 12):
        try:
            if future.result():
                pushed += 1
        except Exception:
            pass
    return pushed


def _build_test_payload(wh_type: str) -> dict:
    if wh_type == "feishu":
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "ChallengeDaily 测试"},
                    "template": "green",
                },
                "elements": [{
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": "✅ Webhook 连接成功！"},
                }],
            },
        }
    elif wh_type == "dingtalk":
        return {
            "msgtype": "actionCard",
            "actionCard": {
                "title": "ChallengeDaily 测试",
                "text": "✅ ChallengeDaily Webhook 连接成功！",
            },
        }
    elif wh_type == "wecom":
        return {
            "msgtype": "markdown",
            "markdown": {
                "content": "✅ ChallengeDaily Webhook 连接成功！",
            },
        }
    else:
        return {
            "msg_type": "text",
            "content": {"text": "ChallengeDaily Webhook 测试 - 连接成功!"},
        }


@bp.route("/api/webhooks", methods=["GET"])
def get_webhooks():
    return jsonify({"webhooks": _load_webhooks()})


@bp.route("/api/webhooks", methods=["POST"])
def add_webhook():
    data = request.get_json(force=True)
    url = data.get("url", "").strip()
    name = data.get("name", "").strip()
    wh_type = data.get("type", "custom")
    events = data.get("events", ["daily_report"])

    if not url:
        return jsonify({"error": "Webhook URL 不能为空"}), 400

    ssrf_error = _validate_webhook_url(url)
    if ssrf_error:
        return jsonify({"error": ssrf_error}), 400

    webhooks = _load_webhooks()
    wh_id = secrets.token_hex(4)
    webhooks.append({
        "id": wh_id,
        "name": name or f"Webhook {len(webhooks) + 1}",
        "url": url,
        "type": wh_type,
        "events": events,
        "enabled": True,
        "created_at": date.today().isoformat(),
    })
    _save_webhooks(webhooks)
    return jsonify({"status": "ok", "webhook": webhooks[-1]})


@bp.route("/api/webhooks/<wh_id>", methods=["DELETE"])
def delete_webhook(wh_id):
    webhooks = _load_webhooks()
    webhooks = [w for w in webhooks if w["id"] != wh_id]
    _save_webhooks(webhooks)
    return jsonify({"status": "ok"})


@bp.route("/api/webhooks/<wh_id>/test", methods=["POST"])
def test_webhook(wh_id):
    webhooks = _load_webhooks()
    wh = next((w for w in webhooks if w["id"] == wh_id), None)
    if not wh:
        return jsonify({"error": "Webhook 不存在"}), 404

    ssrf_error = _validate_webhook_url(wh["url"])
    if ssrf_error:
        return jsonify({"ok": False, "message": ssrf_error}), 400

    import urllib.request
    import urllib.error
    try:
        wh_type = wh.get("type", "custom")
        test_payload = _build_test_payload(wh_type)
        data = _json.dumps(test_payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            wh["url"],
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return jsonify({"ok": True, "message": f"推送成功，HTTP {resp.status}"})
    except urllib.error.HTTPError as e:
        return jsonify({"ok": False, "message": f"推送失败，HTTP {e.code}"})
    except Exception as e:
        logger.error(f"Webhook test push failed: {e}")
        return jsonify({"ok": False, "message": "推送失败，请检查 Webhook 地址"})


@bp.route("/api/webhooks/<wh_id>/toggle", methods=["POST"])
def toggle_webhook(wh_id):
    webhooks = _load_webhooks()
    for w in webhooks:
        if w["id"] == wh_id:
            w["enabled"] = not w.get("enabled", True)
            _save_webhooks(webhooks)
            return jsonify({"status": "ok", "enabled": w["enabled"]})
    return jsonify({"error": "Webhook 不存在"}), 404
