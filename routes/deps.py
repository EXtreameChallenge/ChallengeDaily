import re
import secrets
import hmac
import threading
import logging

from config import BASE_DIR

logger = logging.getLogger(__name__)

collector = None
collector_lock = threading.Lock()
collector_paused = False
state_lock = threading.Lock()
shutdown_event = threading.Event()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 优先复用已有的 token 文件，避免重启后客户端缓存失效
_TOKEN_PATH = BASE_DIR / "data" / ".api_token"
if _TOKEN_PATH.exists():
    try:
        _existing = _TOKEN_PATH.read_text(encoding="utf-8").strip()
        if _existing:
            LOCAL_TOKEN = _existing
        else:
            LOCAL_TOKEN = secrets.token_hex(16)
    except Exception:
        LOCAL_TOKEN = secrets.token_hex(16)
else:
    LOCAL_TOKEN = secrets.token_hex(16)
TOKEN_PATH = _TOKEN_PATH


def save_token():
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(LOCAL_TOKEN, encoding="utf-8")
    try:
        import win32security
        import win32con
        import win32api
        username = win32api.GetUserNameEx(win32con.NameSamCompatible)
        sid, _, _ = win32security.LookupAccountName(None, username)
        sd = win32security.SECURITY_DESCRIPTOR()
        sd.SetSecurityDescriptorOwner(sid, False)
        dacl = win32security.ACL()
        dacl.AddAccessAllowedAce(win32security.ACL_REVISION, win32con.GENERIC_ALL, sid)
        sd.SetSecurityDescriptorDacl(True, dacl, False)
        win32security.SetFileSecurity(str(TOKEN_PATH), win32security.DACL_SECURITY_INFORMATION, sd)
    except ImportError:
        pass


def check_token(req) -> bool:
    token = req.headers.get("X-API-Token", "")
    return hmac.compare_digest(token, LOCAL_TOKEN)


def safe_error(e: Exception, fallback: str = "操作失败，请稍后重试") -> str:
    logger.error(f"Internal error: {e}", exc_info=True)
    return fallback


def validate_date(d: str):
    if not _DATE_RE.match(d):
        return None
    return d
