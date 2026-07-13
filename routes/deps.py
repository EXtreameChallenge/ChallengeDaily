import re
import secrets
import hmac
import threading
import logging
import time

from config import DATA_DIR

logger = logging.getLogger(__name__)

collector = None
collector_lock = threading.Lock()
collector_paused = False
state_lock = threading.Lock()
shutdown_event = threading.Event()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 优先复用已有的 token 文件，避免重启后客户端缓存失效
_TOKEN_PATH = DATA_DIR / ".api_token"
# P0-03: token 30 天过期 + 自动轮换，避免泄露后永不过期
_TOKEN_MAX_AGE_SEC = 30 * 24 * 3600  # 30 天
_TOKEN_CREATED_AT = time.time()  # 默认视为刚创建（向后兼容旧 token 文件）
if _TOKEN_PATH.exists():
    try:
        _existing = _TOKEN_PATH.read_text(encoding="utf-8").strip()
        if _existing:
            # 基于文件 mtime 检查过期，超 30 天则生成新 token 触发轮换
            _TOKEN_CREATED_AT = _TOKEN_PATH.stat().st_mtime
            if time.time() - _TOKEN_CREATED_AT > _TOKEN_MAX_AGE_SEC:
                LOCAL_TOKEN = secrets.token_hex(16)
            else:
                LOCAL_TOKEN = _existing
        else:
            LOCAL_TOKEN = secrets.token_hex(16)
    except Exception:
        LOCAL_TOKEN = secrets.token_hex(16)
else:
    LOCAL_TOKEN = secrets.token_hex(16)
TOKEN_PATH = _TOKEN_PATH

# 关键修复：在模块加载时立即持久化 token，避免 Electron 前端在服务端启动完成前
# 读取到空 token 导致 401。后续 start_server() 会再次调用 save_token() 作为兜底。
save_token = None  # type: ignore


def _save_token_impl():
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


_save_token_impl()


def save_token():
    """持久化当前 token（供 server.py 在启动时调用）"""
    _save_token_impl()


def check_token(req) -> bool:
    # P0-03: 过期检查，超 30 天返回 False 触发 401（下次重启时自动轮换）
    try:
        if time.time() - _TOKEN_CREATED_AT > _TOKEN_MAX_AGE_SEC:
            return False
    except Exception:
        pass
    token = req.headers.get("X-API-Token", "")
    return hmac.compare_digest(token, LOCAL_TOKEN)


def safe_error(e: Exception, fallback: str = "操作失败，请稍后重试") -> str:
    logger.error(f"Internal error: {e}", exc_info=True)
    return fallback


def validate_date(d: str):
    if not _DATE_RE.match(d):
        return None
    return d


# P0-06: 日志脱敏过滤器，避免日志记录 X-API-Token、Authorization 等敏感信息
class SensitiveDataFilter(logging.Filter):
    """过滤日志中的敏感信息"""
    _SENSITIVE_HEADERS = ['x-api-token', 'authorization', 'x-auth-token', 'cookie']
    _SENSITIVE_KEYS = ['api_key', 'apikey', 'token', 'password', 'secret']

    def filter(self, record):
        try:
            msg = str(record.getMessage())
            for h in self._SENSITIVE_HEADERS:
                msg = msg.replace(h, f'{h}=***REDACTED***')
            for k in self._SENSITIVE_KEYS:
                msg = msg.replace(f'"{k}"', f'"{k}":"***REDACTED***"')
            record.msg = msg
            record.args = ()
        except Exception:
            pass
        return True


def install_log_redaction():
    """安装日志脱敏过滤器到 root logger"""
    root = logging.getLogger()
    if not any(isinstance(f, SensitiveDataFilter) for f in root.filters):
        root.addFilter(SensitiveDataFilter())
