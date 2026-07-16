"""
P961-P1000: 安全加固+加密+签名+JWT+OAuth2+RBAC+ABAC+审计+漏洞扫描+合规+渗透测试+密钥轮换(40轮)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

logger = __import__("logging").getLogger(__name__)


# ═════════ P961-P970: 加密 + 签名 + JWT ═════════

class CryptoSuite:
    """加密套件(对称/非对称/哈希/HMAC)"""

    # 对称加密(简化版XOR流，实际生产应使用AES)
    @staticmethod
    def xor_encrypt(plaintext: str, key: str) -> dict:
        if not key:
            return {"status": "error", "error": "密钥不能为空"}
        key_bytes = key.encode("utf-8")
        text_bytes = plaintext.encode("utf-8")
        cipher = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(text_bytes))
        return {"status": "ok", "ciphertext": base64.b64encode(cipher).hex(),
                "algorithm": "XOR"}

    @staticmethod
    def xor_decrypt(cipher_hex: str, key: str) -> dict:
        try:
            cipher = bytes.fromhex(cipher_hex)
            key_bytes = key.encode("utf-8")
            plain = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(cipher))
            return {"status": "ok", "plaintext": plain.decode("utf-8", errors="replace"),
                    "algorithm": "XOR"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    def hash_data(data: str, algorithm: str = "sha256") -> dict:
        try:
            h = hashlib.new(algorithm)
            h.update(data.encode("utf-8"))
            return {"status": "ok", "hash": h.hexdigest(), "algorithm": algorithm}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    def hmac_sign(data: str, key: str, algorithm: str = "sha256") -> dict:
        try:
            mac = hmac.new(key.encode("utf-8"), data.encode("utf-8"), algorithm)
            return {"status": "ok", "signature": mac.hexdigest(),
                    "algorithm": f"HMAC-{algorithm}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    def hmac_verify(data: str, key: str, signature: str,
                    algorithm: str = "sha256") -> dict:
        expected = hmac.new(key.encode("utf-8"), data.encode("utf-8"), algorithm).hexdigest()
        return {"valid": hmac.compare_digest(expected, signature)}


class JWTManager:
    """JWT管理器"""

    def __init__(self, secret: str = "default_secret_change_me"):
        self.secret = secret
        self._revoked: set = set()
        self._lock = threading.Lock()

    def encode(self, payload: dict, expires_in_sec: int = 3600) -> dict:
        header = {"alg": "HS256", "typ": "JWT"}
        now = time.time()
        payload_with_exp = {
            **payload,
            "iat": int(now),
            "exp": int(now + expires_in_sec),
        }
        header_b = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
        payload_b = base64.urlsafe_b64encode(json.dumps(payload_with_exp).encode()).rstrip(b"=").decode()
        signing_input = f"{header_b}.{payload_b}"
        sig = hmac.new(self.secret.encode(), signing_input.encode(), hashlib.sha256).hexdigest()
        return {"token": f"{signing_input}.{sig}", "expires_at": payload_with_exp["exp"]}

    def decode(self, token: str) -> dict:
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return {"valid": False, "error": "格式错误"}
            header_b, payload_b, sig = parts
            signing_input = f"{header_b}.{payload_b}"
            expected_sig = hmac.new(self.secret.encode(), signing_input.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected_sig, sig):
                return {"valid": False, "error": "签名无效"}
            # 添加padding
            pad = 4 - len(payload_b) % 4
            if pad != 4:
                payload_b += "=" * pad
            payload = json.loads(base64.urlsafe_b64decode(payload_b))
            if payload.get("exp", 0) < time.time():
                return {"valid": False, "error": "token已过期", "payload": payload}
            with self._lock:
                if token in self._revoked:
                    return {"valid": False, "error": "token已撤销"}
            return {"valid": True, "payload": payload}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def revoke(self, token: str) -> dict:
        with self._lock:
            self._revoked.add(token)
            return {"status": "ok"}


_crypto = CryptoSuite()
_jwt = JWTManager()


# ═════════ P971-P980: OAuth2 + RBAC + ABAC ═════════

class OAuth2Simulator:
    """OAuth2模拟器"""

    def __init__(self):
        self._clients: dict[str, dict] = {}
        self._auth_codes: dict[str, dict] = {}
        self._tokens: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register_client(self, client_id: str, client_secret: str,
                        redirect_uris: list[str] | None = None,
                        scopes: list[str] | None = None) -> dict:
        with self._lock:
            self._clients[client_id] = {
                "secret": client_secret,
                "redirect_uris": redirect_uris or [],
                "scopes": scopes or ["read", "write"],
            }
            return {"status": "ok"}

    def authorize(self, client_id: str, redirect_uri: str,
                  scope: str = "read", state: str = "") -> dict:
        with self._lock:
            client = self._clients.get(client_id)
            if not client:
                return {"status": "error", "error": "客户端不存在"}
            if redirect_uri not in client["redirect_uris"]:
                return {"status": "error", "error": "redirect_uri未注册"}
            code = secrets.token_urlsafe(16)
            self._auth_codes[code] = {
                "client_id": client_id,
                "scope": scope,
                "redirect_uri": redirect_uri,
                "expires_at": time.time() + 600,  # 10分钟
            }
            return {"status": "ok", "code": code, "state": state,
                    "redirect": f"{redirect_uri}?code={code}&state={state}"}

    def token(self, code: str, client_id: str, client_secret: str) -> dict:
        with self._lock:
            auth = self._auth_codes.pop(code, None)
            if not auth:
                return {"status": "error", "error": "授权码无效或已使用"}
            if auth["expires_at"] < time.time():
                return {"status": "error", "error": "授权码已过期"}
            client = self._clients.get(client_id)
            if not client or client["secret"] != client_secret:
                return {"status": "error", "error": "客户端认证失败"}
            access_token = secrets.token_urlsafe(32)
            refresh_token = secrets.token_urlsafe(32)
            self._tokens[access_token] = {
                "client_id": client_id,
                "scope": auth["scope"],
                "refresh_token": refresh_token,
                "expires_at": time.time() + 3600,
            }
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": auth["scope"],
            }

    def validate(self, access_token: str) -> dict:
        with self._lock:
            token_info = self._tokens.get(access_token)
            if not token_info:
                return {"valid": False, "error": "token无效"}
            if token_info["expires_at"] < time.time():
                return {"valid": False, "error": "token已过期"}
            return {"valid": True, **token_info}


class RBACManager:
    """RBAC角色权限管理"""

    def __init__(self):
        self._roles: dict[str, set] = {}  # role -> permissions
        self._user_roles: dict[str, set] = {}  # user -> roles
        self._lock = threading.Lock()

    def create_role(self, role: str, permissions: list[str] | None = None) -> dict:
        with self._lock:
            self._roles[role] = set(permissions or [])
            return {"status": "ok"}

    def assign_role(self, user: str, role: str) -> dict:
        with self._lock:
            if role not in self._roles:
                return {"status": "error", "error": "角色不存在"}
            self._user_roles.setdefault(user, set()).add(role)
            return {"status": "ok"}

    def check_permission(self, user: str, permission: str) -> dict:
        with self._lock:
            roles = self._user_roles.get(user, set())
            for role in roles:
                if permission in self._roles.get(role, set()):
                    return {"allowed": True, "role": role}
            return {"allowed": False, "user": user, "permission": permission}

    def list_roles(self) -> dict:
        with self._lock:
            return {k: sorted(v) for k, v in self._roles.items()}

    def list_user_roles(self, user: str) -> list[str]:
        with self._lock:
            return sorted(self._user_roles.get(user, set()))


class ABACManager:
    """ABAC属性权限管理"""

    def __init__(self):
        self._policies: list[dict] = []
        self._lock = threading.Lock()

    def add_policy(self, name: str, subject_attrs: dict,
                   resource_attrs: dict, action: str,
                   effect: str = "allow") -> dict:
        with self._lock:
            self._policies.append({
                "name": name,
                "subject": subject_attrs,
                "resource": resource_attrs,
                "action": action,
                "effect": effect,
            })
            return {"status": "ok"}

    def check_access(self, subject: dict, resource: dict,
                     action: str) -> dict:
        with self._lock:
            policies = list(self._policies)
        for p in policies:
            if p["action"] != action:
                continue
            # 简化匹配: 所有subject属性需匹配
            s_match = all(subject.get(k) == v for k, v in p["subject"].items())
            r_match = all(resource.get(k) == v for k, v in p["resource"].items())
            if s_match and r_match:
                return {"allowed": p["effect"] == "allow",
                        "policy": p["name"], "effect": p["effect"]}
        return {"allowed": False, "reason": "no_matching_policy"}

    def list_policies(self) -> list[dict]:
        with self._lock:
            return list(self._policies)


_oauth2 = OAuth2Simulator()
_rbac = RBACManager()
_abac = ABACManager()


# ═════════ P981-P990: 审计 + 漏洞扫描 ═════════

class SecurityAuditor:
    """安全审计"""

    def __init__(self):
        self._events: deque = deque(maxlen=5000)
        self._lock = threading.Lock()

    def log(self, event_type: str, user: str = "", resource: str = "",
            action: str = "", result: str = "success",
            metadata: dict | None = None) -> dict:
        with self._lock:
            event = {
                "event_id": secrets.token_hex(8),
                "type": event_type,
                "user": user,
                "resource": resource,
                "action": action,
                "result": result,
                "metadata": metadata or {},
                "timestamp": datetime.now().isoformat(),
            }
            self._events.append(event)
            return {"status": "ok", "event_id": event["event_id"]}

    def search(self, event_type: str | None = None, user: str | None = None,
               result: str | None = None, limit: int = 50) -> list[dict]:
        with self._lock:
            events = list(self._events)
        filtered = events
        if event_type:
            filtered = [e for e in filtered if e["type"] == event_type]
        if user:
            filtered = [e for e in filtered if e["user"] == user]
        if result:
            filtered = [e for e in filtered if e["result"] == result]
        filtered.reverse()
        return filtered[:limit]

    def stats(self) -> dict:
        with self._lock:
            events = list(self._events)
        return {
            "total": len(events),
            "by_type": dict(Counter(e["type"] for e in events)),
            "by_result": dict(Counter(e["result"] for e in events)),
            "failed_count": sum(1 for e in events if e["result"] == "failure"),
        }


class VulnerabilityScanner:
    """漏洞扫描器"""

    RULES = {
        "weak_password": {
            "pattern": r"^(password|123456|admin|qwerty|letmein)$",
            "severity": "high",
            "description": "弱密码",
        },
        "sensitive_in_url": {
            "pattern": r"(?i)(password|token|secret|api_key)=[^&\s]+",
            "severity": "medium",
            "description": "URL中包含敏感信息",
        },
        "http_used": {
            "pattern": r"http://(?!localhost|127\.0\.0\.1)",
            "severity": "low",
            "description": "使用HTTP而非HTTPS",
        },
        "hardcoded_secret": {
            "pattern": r"(?i)(api[_-]?key|secret|password|token)\s*[=:]\s*['\"][^'\"]+['\"]",
            "severity": "critical",
            "description": "硬编码密钥",
        },
        "sql_injection_risk": {
            "pattern": r"(?i)(SELECT|INSERT|UPDATE|DELETE)\s+.*\+\s*\w+",
            "severity": "high",
            "description": "SQL字符串拼接风险",
        },
        "xss_risk": {
            "pattern": r"(?i)innerHTML\s*=|document\.write\(",
            "severity": "high",
            "description": "XSS风险代码",
        },
        "open_redirect": {
            "pattern": r"(?i)redirect\s*\(\s*request\.\w+\s*\)",
            "severity": "medium",
            "description": "开放重定向风险",
        },
    }

    @classmethod
    def scan(cls, content: str) -> dict:
        findings = []
        for rule_name, rule in cls.RULES.items():
            matches = re.findall(rule["pattern"], content)
            if matches:
                findings.append({
                    "rule": rule_name,
                    "severity": rule["severity"],
                    "description": rule["description"],
                    "match_count": len(matches),
                    "sample": matches[:3],
                })
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        findings.sort(key=lambda x: severity_order.get(x["severity"], 4))
        return {
            "total_findings": len(findings),
            "by_severity": dict(Counter(f["severity"] for f in findings)),
            "findings": findings,
            "risk_score": sum({"critical": 10, "high": 5, "medium": 2, "low": 1}.get(f["severity"], 0) for f in findings),
        }

    @classmethod
    def list_rules(cls) -> dict:
        return {k: {"severity": v["severity"], "description": v["description"]}
                for k, v in cls.RULES.items()}


_security_auditor = SecurityAuditor()
_vuln_scanner = VulnerabilityScanner()


# ═════════ P991-P1000: 密钥轮换 + 合规检查 ═════════

class KeyRotationManager:
    """密钥轮换管理"""

    def __init__(self, rotation_interval_days: int = 90):
        self.rotation_interval_days = rotation_interval_days
        self._keys: dict[str, dict] = {}  # key_id -> {value, created, version, status}
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=10))
        self._lock = threading.Lock()

    def create_key(self, key_id: str, value: str = "") -> dict:
        with self._lock:
            self._keys[key_id] = {
                "value": value or secrets.token_urlsafe(32),
                "created_at": datetime.now().isoformat(),
                "version": 1,
                "status": "active",
            }
            self._history[key_id].append({"version": 1, "action": "created",
                                          "at": datetime.now().isoformat()})
            return {"status": "ok", "key_id": key_id, "version": 1}

    def rotate(self, key_id: str) -> dict:
        with self._lock:
            key = self._keys.get(key_id)
            if not key:
                return {"status": "error", "error": "密钥不存在"}
            key["status"] = "rotated"
            new_version = key["version"] + 1
            self._keys[key_id] = {
                "value": secrets.token_urlsafe(32),
                "created_at": datetime.now().isoformat(),
                "version": new_version,
                "status": "active",
            }
            self._history[key_id].append({"version": new_version, "action": "rotated",
                                          "at": datetime.now().isoformat()})
            return {"status": "ok", "key_id": key_id, "new_version": new_version}

    def check_rotation_needed(self, key_id: str) -> dict:
        with self._lock:
            key = self._keys.get(key_id)
            if not key:
                return {"status": "error", "error": "密钥不存在"}
            created = datetime.fromisoformat(key["created_at"])
            age_days = (datetime.now() - created).days
            return {
                "key_id": key_id,
                "version": key["version"],
                "age_days": age_days,
                "rotation_interval": self.rotation_interval_days,
                "needs_rotation": age_days >= self.rotation_interval_days,
            }

    def list_keys(self) -> list[dict]:
        with self._lock:
            return [{"key_id": k, "version": v["version"],
                     "status": v["status"], "created_at": v["created_at"]}
                    for k, v in self._keys.items()]

    def history(self, key_id: str) -> list[dict]:
        with self._lock:
            return list(self._history.get(key_id, deque()))


class ComplianceChecker:
    """合规检查器"""

    def __init__(self):
        self._checks: dict[str, dict] = {}
        self._lock = threading.Lock()

    def register_check(self, name: str, description: str = "",
                       severity: str = "medium") -> dict:
        with self._lock:
            self._checks[name] = {
                "description": description,
                "severity": severity,
                "last_run": None,
                "last_result": None,
            }
            return {"status": "ok"}

    def run_check(self, name: str, data: dict) -> dict:
        with self._lock:
            check = self._checks.get(name)
            if not check:
                return {"status": "error", "error": "检查项不存在"}
        # 简化合规检查逻辑
        issues = []
        if name == "data_retention":
            retention_days = data.get("retention_days", 0)
            if retention_days > 365:
                issues.append(f"数据保留期{retention_days}天超过365天上限")
        elif name == "encryption_at_rest":
            if not data.get("encrypted", False):
                issues.append("静态数据未加密")
        elif name == "access_control":
            if not data.get("mfa_enabled", False):
                issues.append("未启用MFA")
            if data.get("shared_accounts", 0) > 0:
                issues.append(f"存在{data['shared_accounts']}个共享账号")
        elif name == "audit_logging":
            if not data.get("audit_enabled", False):
                issues.append("未启用审计日志")
        elif name == "pii_handling":
            if data.get("pii_unencrypted", 0) > 0:
                issues.append(f"{data['pii_unencrypted']}个PII字段未加密")
        result = {
            "name": name,
            "passed": len(issues) == 0,
            "issues": issues,
            "severity": check["severity"],
            "timestamp": datetime.now().isoformat(),
        }
        with self._lock:
            self._checks[name]["last_run"] = result["timestamp"]
            self._checks[name]["last_result"] = result
        return result

    def list_checks(self) -> list[dict]:
        with self._lock:
            return [{"name": k, **v} for k, v in self._checks.items()]

    def compliance_summary(self) -> dict:
        with self._lock:
            checks = list(self._checks.values())
        total = len(checks)
        passed = sum(1 for c in checks if c.get("last_result", {}).get("passed"))
        return {
            "total_checks": total,
            "passed": passed,
            "failed": total - passed,
            "compliance_rate": round(passed / max(1, total), 4),
        }


_key_rotation = KeyRotationManager()
_compliance = ComplianceChecker()
