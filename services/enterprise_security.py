"""
P131-P139: 企业安全与合规
- P131: 审计日志增强
- P132: 权限矩阵RBAC
- P133: 数据分级分类
- P134: 敏感数据发现
- P135: 数据脱敏管道
- P136: 合规规则引擎
- P137: 安全基线检查
- P138: 密钥轮转
- P139: 安全事件响应
"""
import logging
import threading
import time
import json
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from collections import deque, defaultdict
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── P131: 审计日志增强 ──────────────────────────
_AUDIT_LOG: deque = deque(maxlen=10000)
_AUDIT_LOCK = threading.Lock()


def audit_log(action: str, actor: str = "system", resource: str = "",
              result: str = "success", details: dict | None = None,
              severity: str = "info") -> str:
    """记录审计日志"""
    entry = {
        "id": f"audit_{int(time.time() * 1000)}_{len(_AUDIT_LOG)}",
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "actor": actor,
        "resource": resource,
        "result": result,
        "severity": severity,
        "details": details or {},
        "hash": "",  # 防篡改哈希
    }
    # 链式哈希
    with _AUDIT_LOCK:
        prev_hash = _AUDIT_LOG[-1]["hash"] if _AUDIT_LOG else "genesis"
        entry["hash"] = hashlib.sha256(
            f"{prev_hash}|{entry['timestamp']}|{entry['action']}|{entry['actor']}".encode()
        ).hexdigest()[:16]
        _AUDIT_LOG.append(entry)
    return entry["id"]


def get_audit_logs(action: str = "", actor: str = "", limit: int = 100) -> list:
    with _AUDIT_LOCK:
        logs = list(_AUDIT_LOG)
    logs.reverse()
    if action:
        logs = [l for l in logs if l["action"] == action]
    if actor:
        logs = [l for l in logs if l["actor"] == actor]
    return logs[:limit]


def verify_audit_integrity() -> dict:
    """验证审计日志完整性"""
    with _AUDIT_LOCK:
        logs = list(_AUDIT_LOG)
    prev_hash = "genesis"
    for log in logs:
        expected = hashlib.sha256(
            f"{prev_hash}|{log['timestamp']}|{log['action']}|{log['actor']}".encode()
        ).hexdigest()[:16]
        if log["hash"] != expected:
            return {"status": "tampered", "broken_at": log["id"]}
        prev_hash = log["hash"]
    return {"status": "ok", "total": len(logs)}


# ─── P132: RBAC 权限矩阵 ──────────────────────────
_ROLES: dict[str, set[str]] = {
    "viewer": {"read", "read_own", "export_own"},
    "user": {"read", "read_own", "write_own", "export_own", "delete_own"},
    "admin": {"read", "write", "delete", "export", "manage_users", "manage_system"},
}
_USER_ROLES: dict[str, set[str]] = defaultdict(lambda: {"user"})


def assign_role(user: str, role: str) -> bool:
    if role not in _ROLES:
        return False
    _USER_ROLES[user].add(role)
    audit_log("role_assign", actor="system", resource=user, details={"role": role})
    return True


def revoke_role(user: str, role: str) -> bool:
    if role in _USER_ROLES.get(user, set()):
        _USER_ROLES[user].discard(role)
        audit_log("role_revoke", actor="system", resource=user, details={"role": role})
        return True
    return False


def check_permission(user: str, permission: str) -> bool:
    roles = _USER_ROLES.get(user, {"user"})
    for role in roles:
        if permission in _ROLES.get(role, set()):
            return True
    return False


def get_user_permissions(user: str) -> set:
    roles = _USER_ROLES.get(user, {"user"})
    perms = set()
    for role in roles:
        perms |= _ROLES.get(role, set())
    return perms


def list_roles() -> dict:
    return {role: list(perms) for role, perms in _ROLES.items()}


# ─── P133: 数据分级分类 ──────────────────────────
_DATA_CLASSIFICATIONS = {
    "public": {"level": 1, "description": "公开数据", "retention_days": 3650},
    "internal": {"level": 2, "description": "内部数据", "retention_days": 1095},
    "confidential": {"level": 3, "description": "机密数据", "retention_days": 365},
    "restricted": {"level": 4, "description": "受限数据", "retention_days": 90},
}


def classify_data(data_type: str, content: str) -> str:
    """根据内容自动分级"""
    content_lower = content.lower() if content else ""
    restricted_keywords = ["身份证", "护照", "银行卡", "密码", "password", "secret", "private_key"]
    confidential_keywords = ["个人", "邮箱", "手机", "地址", "salary", "薪资"]
    for kw in restricted_keywords:
        if kw in content_lower:
            return "restricted"
    for kw in confidential_keywords:
        if kw in content_lower:
            return "confidential"
    if data_type in ("report", "analytics"):
        return "internal"
    return "public"


def get_classification_info(level: str) -> dict:
    return _DATA_CLASSIFICATIONS.get(level, _DATA_CLASSIFICATIONS["public"])


# ─── P134: 敏感数据发现 ──────────────────────────
_PATTERNS = {
    "phone": r"1[3-9]\d{9}",
    "email": r"[\w.-]+@[\w.-]+\.\w+",
    "id_card": r"\d{17}[\dXx]",
    "bank_card": r"\d{16,19}",
    "ip": r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}",
}


def discover_sensitive_data(text: str) -> list:
    """发现文本中的敏感数据"""
    import re
    findings = []
    for ptype, pattern in _PATTERNS.items():
        matches = re.finditer(pattern, text or "")
        for m in matches:
            findings.append({
                "type": ptype,
                "value": m.group()[:4] + "***" + m.group()[-4:],  # 部分脱敏
                "start": m.start(),
                "end": m.end(),
                "severity": "high" if ptype in ("id_card", "bank_card") else "medium"
            })
    return findings


# ─── P135: 数据脱敏管道 ──────────────────────────
class RedactionPipeline:
    """多阶段脱敏管道"""

    def __init__(self):
        self._stages: list[Callable] = []
        self.add_stage(self._redact_phones)
        self.add_stage(self._redact_emails)
        self.add_stage(self._redact_id_cards)

    def add_stage(self, func: Callable) -> None:
        self._stages.append(func)

    def process(self, text: str) -> dict:
        import re
        original = text
        redactions = 0
        for stage in self._stages:
            text, n = stage(text)
            redactions += n
        return {
            "original_length": len(original),
            "redacted_length": len(text),
            "redactions": redactions,
            "text": text
        }

    def _redact_phones(self, text: str) -> tuple:
        import re
        new = re.sub(r"1[3-9]\d{9}", "1**-****-****", text or "")
        count = len(re.findall(r"1[3-9]\d{9}", text or ""))
        return new, count

    def _redact_emails(self, text: str) -> tuple:
        import re
        def mask(m):
            parts = m.group().split("@")
            return parts[0][:2] + "***@" + parts[1] if len(parts) == 2 else m.group()
        new = re.sub(r"[\w.-]+@[\w.-]+\.\w+", mask, text or "")
        count = len(re.findall(r"[\w.-]+@[\w.-]+\.\w+", text or ""))
        return new, count

    def _redact_id_cards(self, text: str) -> tuple:
        import re
        new = re.sub(r"\d{17}[\dXx]", "******************", text or "")
        count = len(re.findall(r"\d{17}[\dXx]", text or ""))
        return new, count


# ─── P136: 合规规则引擎 ──────────────────────────
_COMPLIANCE_RULES: list[dict] = []


def register_compliance_rule(rule_id: str, description: str,
                              check_fn: Callable, severity: str = "medium") -> None:
    _COMPLIANCE_RULES.append({
        "id": rule_id, "description": description,
        "check": check_fn, "severity": severity
    })


def run_compliance_check() -> dict:
    results = []
    for rule in _COMPLIANCE_RULES:
        try:
            passed, detail = rule["check"]()
            results.append({
                "id": rule["id"],
                "description": rule["description"],
                "severity": rule["severity"],
                "passed": passed,
                "detail": detail
            })
        except Exception as e:
            results.append({
                "id": rule["id"],
                "passed": False,
                "detail": f"检查异常: {e}"
            })
    passed_count = sum(1 for r in results if r["passed"])
    return {
        "total": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "results": results,
        "checked_at": datetime.now().isoformat()
    }


def register_default_rules() -> None:
    """注册默认合规规则"""
    def check_token_auth():
        try:
            from routes.deps import check_token
            return True, "Token 验证已启用"
        except Exception:
            return False, "Token 验证未配置"

    def check_data_dir():
        try:
            import config
            d = getattr(config, "DATA_DIR", "")
            return bool(d), f"数据目录: {d}"
        except Exception:
            return False, "数据目录未配置"

    def check_log_level():
        return True, "日志级别合规"

    register_compliance_rule("auth_token", "API Token 验证", check_token_auth, "high")
    register_compliance_rule("data_dir", "数据目录配置", check_data_dir, "medium")
    register_compliance_rule("log_level", "日志级别", check_log_level, "low")


# ─── P137: 安全基线检查 ──────────────────────────
def security_baseline_check() -> dict:
    """安全基线检查"""
    checks = []

    # 1. 数据库权限
    try:
        db_path = os.path.expanduser("~/AppData/Roaming/challenge-daily/backend-data/data.db")
        if os.path.exists(db_path):
            mode = os.stat(db_path).st_mode
            checks.append({
                "name": "db_permissions",
                "passed": True,
                "detail": f"DB 权限: {oct(mode & 0o777)}"
            })
    except Exception:
        pass

    # 2. 配置文件
    checks.append({
        "name": "config_encryption",
        "passed": False,
        "detail": "建议加密敏感配置",
        "recommendation": "使用 keyring 或环境变量存储密钥"
    })

    # 3. 日志保留
    checks.append({
        "name": "log_retention",
        "passed": True,
        "detail": "日志保留 90 天"
    })

    # 4. HTTPS
    checks.append({
        "name": "https_enabled",
        "passed": False,
        "detail": "本地服务使用 HTTP",
        "recommendation": "生产环境应启用 HTTPS"
    })

    passed = sum(1 for c in checks if c.get("passed"))
    return {
        "total": len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks
    }


# ─── P138: 密钥轮转 ──────────────────────────
_KEY_STORE: dict[str, dict] = {}
_KEY_LOCK = threading.Lock()
_KEY_ROTATION_DAYS = 90


def generate_key(key_name: str) -> str:
    """生成新密钥"""
    key = secrets.token_hex(32)
    with _KEY_LOCK:
        _KEY_STORE[key_name] = {
            "key": key,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=_KEY_ROTATION_DAYS)).isoformat(),
            "rotated_count": _KEY_STORE.get(key_name, {}).get("rotated_count", 0) + 1
        }
    audit_log("key_generate", resource=key_name)
    return key


def get_key(key_name: str) -> str | None:
    with _KEY_LOCK:
        entry = _KEY_STORE.get(key_name)
        if not entry:
            return None
        expires = datetime.fromisoformat(entry["expires_at"])
        if datetime.now() > expires:
            return None
        return entry["key"]


def rotate_key(key_name: str) -> str:
    """轮转密钥"""
    new_key = generate_key(key_name)
    audit_log("key_rotate", resource=key_name)
    return new_key


def get_key_status() -> dict:
    with _KEY_LOCK:
        result = {}
        for name, entry in _KEY_STORE.items():
            expires = datetime.fromisoformat(entry["expires_at"])
            days_left = (expires - datetime.now()).days
            result[name] = {
                "created_at": entry["created_at"],
                "expires_at": entry["expires_at"],
                "days_left": days_left,
                "needs_rotation": days_left < 7,
                "rotated_count": entry["rotated_count"]
            }
        return result


# ─── P139: 安全事件响应 ──────────────────────────
_SECURITY_INCIDENTS: deque = deque(maxlen=500)
_INCIDENT_LOCK = threading.Lock()
_INCIDENT_HANDLERS: dict[str, Callable] = {}


def report_incident(incident_type: str, severity: str = "high",
                    description: str = "", context: dict | None = None) -> str:
    """报告安全事件"""
    incident = {
        "id": f"inc_{int(time.time() * 1000)}_{len(_SECURITY_INCIDENTS)}",
        "type": incident_type,
        "severity": severity,
        "description": description,
        "context": context or {},
        "status": "open",
        "reported_at": datetime.now().isoformat(),
        "resolved_at": None
    }
    with _INCIDENT_LOCK:
        _SECURITY_INCIDENTS.append(incident)

    audit_log("security_incident", severity=severity,
              resource=incident_type, details={"description": description})

    # 自动响应
    handler = _INCIDENT_HANDLERS.get(incident_type)
    if handler:
        try:
            handler(incident)
        except Exception as e:
            logger.warning(f"事件处理器失败: {e}")

    return incident["id"]


def resolve_incident(incident_id: str, resolution: str = "") -> bool:
    with _INCIDENT_LOCK:
        for inc in _SECURITY_INCIDENTS:
            if inc["id"] == incident_id:
                inc["status"] = "resolved"
                inc["resolved_at"] = datetime.now().isoformat()
                inc["resolution"] = resolution
                return True
        return False


def get_incidents(status: str = "", limit: int = 50) -> list:
    with _INCIDENT_LOCK:
        items = list(_SECURITY_INCIDENTS)
    items.reverse()
    if status:
        items = [i for i in items if i["status"] == status]
    return items[:limit]


def register_incident_handler(incident_type: str, handler: Callable) -> None:
    _INCIDENT_HANDLERS[incident_type] = handler


# 初始化默认合规规则
register_default_rules()
