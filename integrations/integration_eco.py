"""
P171-P179: 集成生态扩展
- P171: Webhook 适配器
- P172: Zapier/Make 风格 webhook
- P173: OAuth2 客户端
- P174: Slack 集成
- P175: Microsoft Teams 集成
- P176: Notion 集成
- P177: Trello 集成
- P178: Jira 集成
- P179: 通用 API 网关
"""
import logging
import threading
import time
import json
import hashlib
import hmac
import urllib.request
import urllib.error
from datetime import datetime
from collections import deque
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P171: Webhook 适配器 ──────────────────────────
class WebhookAdapter:
    """通用 webhook 适配器"""

    def __init__(self):
        self._endpoints: dict[str, dict] = {}
        self._delivery_log: deque = deque(maxlen=500)
        self._lock = threading.Lock()

    def register(self, name: str, url: str, secret: str = "",
                 headers: dict | None = None) -> None:
        with self._lock:
            self._endpoints[name] = {
                "url": url,
                "secret": secret,
                "headers": headers or {},
                "created_at": datetime.now().isoformat()
            }

    def send(self, name: str, payload: dict) -> dict:
        with self._lock:
            endpoint = self._endpoints.get(name)
        if not endpoint:
            return {"status": "error", "error": "未注册的端点"}

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", **endpoint["headers"]}

        # HMAC 签名
        if endpoint["secret"]:
            signature = hmac.new(
                endpoint["secret"].encode(),
                body,
                hashlib.sha256
            ).hexdigest()
            headers["X-Signature"] = signature

        try:
            req = urllib.request.Request(
                endpoint["url"], data=body, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                result = {"status": "ok", "http_status": status}
        except urllib.error.HTTPError as e:
            result = {"status": "error", "http_status": e.code, "error": str(e)}
        except Exception as e:
            result = {"status": "error", "error": str(e)}

        with self._lock:
            self._delivery_log.append({
                "endpoint": name,
                "payload_size": len(body),
                "result": result,
                "timestamp": datetime.now().isoformat()
            })
        return result

    def list_endpoints(self) -> dict:
        with self._lock:
            return {k: {"url": v["url"], "created_at": v["created_at"]}
                    for k, v in self._endpoints.items()}

    def get_delivery_log(self, limit: int = 50) -> list:
        with self._lock:
            logs = list(self._delivery_log)
        logs.reverse()
        return logs[:limit]


_webhook = WebhookAdapter()


# ─── P172: 触发器系统 ──────────────────────────
class TriggerSystem:
    """事件触发器(类似 Zapier)"""

    def __init__(self):
        self._triggers: list[dict] = []
        self._lock = threading.Lock()

    def register(self, name: str, event: str, condition: Callable,
                 action: Callable, enabled: bool = True) -> None:
        with self._lock:
            self._triggers.append({
                "name": name, "event": event,
                "condition": condition, "action": action,
                "enabled": enabled,
                "triggered_count": 0,
                "last_triggered": None
            })

    def fire(self, event: str, context: dict) -> list:
        results = []
        with self._lock:
            triggers = [t for t in self._triggers if t["enabled"] and t["event"] == event]
        for t in triggers:
            try:
                if t["condition"](context):
                    result = t["action"](context)
                    with self._lock:
                        t["triggered_count"] += 1
                        t["last_triggered"] = datetime.now().isoformat()
                    results.append({"trigger": t["name"], "result": result})
            except Exception as e:
                results.append({"trigger": t["name"], "error": str(e)})
        return results

    def list_triggers(self) -> list:
        with self._lock:
            return [
                {
                    "name": t["name"], "event": t["event"],
                    "enabled": t["enabled"],
                    "triggered_count": t["triggered_count"],
                    "last_triggered": t["last_triggered"]
                }
                for t in self._triggers
            ]

    def toggle(self, name: str, enabled: bool) -> bool:
        with self._lock:
            for t in self._triggers:
                if t["name"] == name:
                    t["enabled"] = enabled
                    return True
            return False


_triggers = TriggerSystem()


# ─── P173: OAuth2 客户端 ──────────────────────────
class OAuth2Client:
    """简化 OAuth2 客户端"""

    def __init__(self):
        self._providers: dict[str, dict] = {}

    def register_provider(self, name: str, auth_url: str,
                          token_url: str, client_id: str,
                          client_secret: str, scopes: list[str]) -> None:
        self._providers[name] = {
            "auth_url": auth_url,
            "token_url": token_url,
            "client_id": client_id,
            "client_secret": client_secret,
            "scopes": scopes,
            "tokens": {}
        }

    def get_auth_url(self, provider: str, redirect_uri: str,
                     state: str = "") -> str:
        p = self._providers.get(provider)
        if not p:
            return ""
        params = [
            f"client_id={p['client_id']}",
            f"redirect_uri={redirect_uri}",
            f"scope={' '.join(p['scopes'])}",
            "response_type=code",
            f"state={state}"
        ]
        return f"{p['auth_url']}?{'&'.join(params)}"

    def store_token(self, provider: str, token: dict) -> None:
        if provider in self._providers:
            token["stored_at"] = datetime.now().isoformat()
            self._providers[provider]["tokens"] = token

    def get_token(self, provider: str) -> dict | None:
        p = self._providers.get(provider)
        return p.get("tokens") if p else None

    def list_providers(self) -> list:
        return [
            {"name": k, "scopes": v["scopes"], "has_token": bool(v.get("tokens"))}
            for k, v in self._providers.items()
        ]


_oauth2 = OAuth2Client()


# ─── P174-P178: 第三方集成 ──────────────────────────
def _make_integration(name: str, send_fn: Callable) -> dict:
    """集成工厂"""
    return {
        "name": name,
        "send": send_fn,
        "stats": {"sent": 0, "failed": 0, "last_sent": None}
    }


def _slack_send(message: str, channel: str = "#general", webhook_url: str = "") -> dict:
    """P174: Slack 集成"""
    if not webhook_url:
        return {"status": "error", "error": "未配置 webhook"}
    try:
        payload = {"text": message, "channel": channel}
        body = json.dumps(payload).encode()
        req = urllib.request.Request(webhook_url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"status": "ok", "http_status": resp.status}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _teams_send(message: str, webhook_url: str = "") -> dict:
    """P175: Teams 集成"""
    if not webhook_url:
        return {"status": "error", "error": "未配置 webhook"}
    try:
        payload = {"text": message}
        body = json.dumps(payload).encode()
        req = urllib.request.Request(webhook_url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"status": "ok", "http_status": resp.status}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _notion_send(page_title: str, content: str, database_id: str = "",
                 token: str = "") -> dict:
    """P176: Notion 集成"""
    if not token:
        return {"status": "error", "error": "未配置 token"}
    return {"status": "ok", "title": page_title, "note": "Notion API 需要实现"}


def _trello_send(card_name: str, list_id: str = "", api_key: str = "",
                 token: str = "") -> dict:
    """P177: Trello 集成"""
    if not api_key:
        return {"status": "error", "error": "未配置 API key"}
    return {"status": "ok", "card": card_name, "note": "Trello API 需要实现"}


def _jira_send(summary: str, description: str = "", project: str = "",
               token: str = "") -> dict:
    """P178: Jira 集成"""
    if not token:
        return {"status": "error", "error": "未配置 token"}
    return {"status": "ok", "summary": summary, "note": "Jira API 需要实现"}


# ─── P179: API 网关 ──────────────────────────
class APIGateway:
    """通用 API 网关"""

    def __init__(self):
        self._routes: dict[str, dict] = {}
        self._rate_limits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def register_route(self, path: str, upstream: str,
                       rate_limit: int = 100, auth_required: bool = True) -> None:
        with self._lock:
            self._routes[path] = {
                "upstream": upstream,
                "rate_limit": rate_limit,
                "auth_required": auth_required
            }
            self._rate_limits[path] = deque(maxlen=rate_limit)

    def check_rate_limit(self, path: str, client_id: str = "default") -> dict:
        with self._lock:
            route = self._routes.get(path)
            if not route:
                return {"allowed": False, "error": "未知路由"}
            now = time.time()
            window = 60  # 60 秒
            limits = self._rate_limits[path]
            # 清理过期记录
            while limits and limits[0] < now - window:
                limits.popleft()
            if len(limits) >= route["rate_limit"]:
                return {"allowed": False, "error": "触发限流"}
            limits.append(now)
            return {
                "allowed": True,
                "remaining": route["rate_limit"] - len(limits),
                "limit": route["rate_limit"]
            }

    def list_routes(self) -> dict:
        with self._lock:
            return {
                path: {
                    "upstream": r["upstream"],
                    "rate_limit": r["rate_limit"],
                    "auth_required": r["auth_required"]
                }
                for path, r in self._routes.items()
            }


_gateway = APIGateway()
