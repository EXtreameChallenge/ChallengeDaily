"""截屏内容脱敏"""
import logging
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

# 需要脱敏的应用窗口标题关键词
_SENSITIVE_WINDOW_KEYWORDS = [
    '密码', 'password', '登录', 'login', '银行', 'bank', '支付', 'payment',
    '微信', 'wechat', 'qq', '支付宝', 'alipay', 'wallet',
]

# 隐私应用名单（用户可在 Settings 配置，存 settings 表）
_PRIVACY_APPS_CACHE = None


def is_sensitive_window(window_title: str, app_name: str) -> bool:
    """判断窗口是否敏感（需要跳过采集）"""
    if not window_title:
        return False
    title_lower = window_title.lower()
    app_lower = app_name.lower() if app_name else ""
    for kw in _SENSITIVE_WINDOW_KEYWORDS:
        if kw in title_lower or kw in app_lower:
            return True
    return False


def blur_sensitive_region(image, region=None):
    """模糊图片指定区域（region = (x, y, w, h)）"""
    if region is None:
        return image
    x, y, w, h = region
    cropped = image.crop((x, y, x + w, y + h))
    blurred = cropped.filter(ImageFilter.GaussianBlur(radius=15))
    image.paste(blurred, (x, y))
    return image


def get_privacy_apps() -> list:
    """从 settings 表读取用户配置的隐私应用名单"""
    global _PRIVACY_APPS_CACHE
    if _PRIVACY_APPS_CACHE is not None:
        return _PRIVACY_APPS_CACHE
    try:
        import db
        with db.get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key='privacy_apps'").fetchone()
            if row:
                import json
                _PRIVACY_APPS_CACHE = json.loads(row[0])
            else:
                _PRIVACY_APPS_CACHE = []
    except Exception:
        _PRIVACY_APPS_CACHE = []
    return _PRIVACY_APPS_CACHE


def should_skip_capture(window_title: str, app_name: str) -> bool:
    """判断是否应跳过本次采集"""
    if is_sensitive_window(window_title, app_name):
        return True
    privacy_apps = get_privacy_apps()
    if app_name and app_name.lower() in [a.lower() for a in privacy_apps]:
        return True
    return False
