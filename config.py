"""
ChallengeDaily Windows 版 — 配置管理
支持 .env 文件和环境变量两种配置方式，优先级：环境变量 > .env 文件 > 空默认值
"""
import json
import os
import logging
import threading
import time
from pathlib import Path
from file_utils import atomic_write_text, backup_file

# ── 加载 .env 文件 ──
# 加载 .env 文件，但空值不会写入 os.environ，避免覆盖 vault 或环境变量中已保存的敏感信息
_ENV_FILE = Path(__file__).resolve().parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # 空值不设置：防止 .env 里的 AI_API_KEY= 覆盖已保存的 key
                if key and value and key not in os.environ:
                    os.environ[key] = value

# ── 基础路径 ──
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
REPORT_DIR = DATA_DIR / "reports"
DB_PATH = DATA_DIR / "xiaohei.db"
SETTINGS_PATH = DATA_DIR / "settings.json"

# 确保目录存在
for d in [DATA_DIR, SCREENSHOT_DIR, REPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── 截图间隔（秒）──
SCREENSHOT_INTERVAL_SEC = int(os.getenv("SCREENSHOT_INTERVAL_SEC", "60"))

# ── 截图压缩质量（1-100）──
SCREENSHOT_QUALITY = int(os.getenv("SCREENSHOT_QUALITY", "70"))

# ── 截图最大宽度像素（超过则等比缩放）──
SCREENSHOT_MAX_WIDTH = int(os.getenv("SCREENSHOT_MAX_WIDTH", "1920"))

# ── HTTP API 端口 ──
HTTP_PORT = int(os.getenv("PORT", os.getenv("HTTP_PORT", "58888")))

# ── AI 模型配置（兼容 OpenAI 接口协议）──
# 支持双模型：识图模型（Vision）+ 文本分析模型（Text）
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")

# 向后兼容：旧的 AI_MODEL 同时作为 vision/text 的兜底
_legacy_model = os.getenv("AI_MODEL", "")
AI_VISION_MODEL = os.getenv("AI_VISION_MODEL", _legacy_model or "glm-4v-flash")
AI_TEXT_MODEL = os.getenv("AI_TEXT_MODEL", _legacy_model or "glm-4-flash")

# API Key 优先级：环境变量（非空）> 加密 vault > 默认值
_raw_api_key = os.getenv("AI_API_KEY", "").strip()
if not _raw_api_key:
    try:
        from crypto import load_secret
        _raw_api_key = load_secret("ai_api_key", "")
    except Exception:
        pass
AI_API_KEY = _raw_api_key

# ── 数据保留天数 ──
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "7"))

# ── 工作分类 ──
CATEGORIES = [
    "开发", "会议", "沟通", "文档", "测试",
    "设计", "运维", "数据分析", "学习", "管理", "产品", "生活",
]

# ── 隐私关键词（截图分析时脱敏）──
PRIVACY_KEYWORDS = os.getenv("PRIVACY_KEYWORDS", "").split(",") if os.getenv("PRIVACY_KEYWORDS") else []

# ── 持久化设置（JSON 文件）──
_DEFAULT_SETTINGS = {
    "exclude_apps": ["1password", "bitwarden", "keepass"],
    "screenshot_interval_sec": 60,
    "work_start_hour": 9,
    "work_end_hour": 18,
    "custom_report_instructions": "",
    "ai_enabled": False,
    "ai_base_url": "https://open.bigmodel.cn/api/paas/v4",
    "ai_vision_model": "glm-4v-flash",
    "ai_text_model": "glm-4-flash",
    "pomodoro_work_min": 25,
    "pomodoro_break_min": 5,
    "pomodoro_long_break_min": 15,
    "pomodoro_auto_start_break": True,
    "pomodoro_sound_enabled": True,
    "pomodoro_default_category": "开发",
    "diary_auto_link_workdata": True,
    "white_noise_default": "none",
    "focus_blocking_mode": False,
}

# ── settings 缓存（避免每次 API 请求都读磁盘）──
_settings_cache = None
_settings_cache_time = 0
_SETTINGS_CACHE_TTL = 10  # 10 秒缓存
_settings_lock = threading.Lock()  # 保护缓存读写（多线程安全）

def load_settings() -> dict:
    """从 settings.json 读取设置，不存在则返回默认值（带缓存，线程安全）"""
    global _settings_cache, _settings_cache_time
    with _settings_lock:
        now = time.time()
        if _settings_cache is not None and (now - _settings_cache_time) < _SETTINGS_CACHE_TTL:
            return _settings_cache.copy()
        if SETTINGS_PATH.exists():
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # 合并默认值（确保新字段有默认值）
                result = dict(_DEFAULT_SETTINGS)
                result.update(saved)
                _settings_cache = result
                _settings_cache_time = now
                return result
            except Exception as e:
                logging.getLogger(__name__).warning(f"Failed to load settings: {e}, using defaults")
        result = dict(_DEFAULT_SETTINGS)
        _settings_cache = result
        _settings_cache_time = now
        return result

def save_settings(settings: dict) -> None:
    """保存设置到 settings.json（原子写入，线程安全）"""
    global _settings_cache, _settings_cache_time
    with _settings_lock:
        # 合并默认值
        result = dict(_DEFAULT_SETTINGS)
        result.update(settings)
        content = json.dumps(result, ensure_ascii=False, indent=2)
        if SETTINGS_PATH.exists():
            backup_file(SETTINGS_PATH)
        atomic_write_text(SETTINGS_PATH, content)
        # 更新缓存
        _settings_cache = result
        _settings_cache_time = time.time()

def get_exclude_apps() -> list[str]:
    """获取排除应用列表"""
    return load_settings().get("exclude_apps", _DEFAULT_SETTINGS["exclude_apps"])

def is_app_excluded(app_name: str) -> bool:
    """检查应用是否在排除列表中（不区分大小写的子串匹配）"""
    exclude_list = get_exclude_apps()
    app_lower = app_name.lower()
    return any(excluded.lower() in app_lower for excluded in exclude_list)
