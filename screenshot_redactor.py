"""截屏内容脱敏"""
import base64
import io
import logging
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

# 需要脱敏的应用窗口标题关键词
_SENSITIVE_WINDOW_KEYWORDS = [
    '密码', 'password', '登录', 'login', '银行', 'bank', '支付', 'payment',
    '微信', 'wechat', '支付宝', 'alipay', 'wallet', '钱包',
    # P33: 扩展敏感关键词
    '验证码', 'verification', 'otp', 'token', 'secret',
    '私人', 'private', '机密', 'confidential',
    '病历', 'medical', '健康记录',
    '社保', 'passport', '护照', '身份证',
]

# B03 收口：QQ 只记录使用时长（归"沟通"），但截图不上传、不做内容分析
_NO_UPLOAD_WINDOW_KEYWORDS = ['qq']

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


def is_no_upload_window(window_title: str, app_name: str) -> bool:
    """可记录但禁止上传截图的窗口（如 QQ：只统计时长与分类）。"""
    title_lower = (window_title or "").lower()
    app_lower = (app_name or "").lower()
    return any(kw in title_lower or kw in app_lower for kw in _NO_UPLOAD_WINDOW_KEYWORDS)


def blur_sensitive_region(image, region=None):
    """模糊图片指定区域（region = (x, y, w, h)）"""
    if region is None:
        return image
    x, y, w, h = region
    cropped = image.crop((x, y, x + w, y + h))
    blurred = cropped.filter(ImageFilter.GaussianBlur(radius=15))
    image.paste(blurred, (x, y))
    return image


def redact_base64_image(b64_image: str, radius: int = 15) -> str:
    """整图高斯模糊后返回新的 base64（内存中处理，不落临时文件）。

    用于 privacy_redact 开关开启时的敏感窗口：宁可牺牲分析精度，也不让
    原始像素离开本机。
    """
    raw = base64.b64decode(b64_image)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    blurred = img.filter(ImageFilter.GaussianBlur(radius=radius))
    buf = io.BytesIO()
    blurred.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


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
