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
# 支持通过环境变量覆盖数据目录，Electron 打包后会把数据固定到 userData/backend-data
_data_dir_override = os.getenv("CHALLENGE_DAILY_DATA_DIR", "")
if _data_dir_override:
    DATA_DIR = Path(_data_dir_override)
else:
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

# ── P8-3：自适应采样 ──
# 启用后采集器会根据近期分类变化频率动态调整下次采样间隔：
#   - 分类频繁切换 → 缩短到下限（捕捉细节）
#   - 分类长时间稳定 → 拉长到上限（节省资源）
# 仅在工作时间生效，非工作时间仍维持 5 分钟一次
ADAPTIVE_SAMPLING_ENABLED = os.getenv("ADAPTIVE_SAMPLING_ENABLED", "1") == "1"
ADAPTIVE_SAMPLING_MIN_SEC = int(os.getenv("ADAPTIVE_SAMPLING_MIN_SEC", "30"))   # 下限
ADAPTIVE_SAMPLING_MAX_SEC = int(os.getenv("ADAPTIVE_SAMPLING_MAX_SEC", "120"))  # 上限
ADAPTIVE_SAMPLING_WINDOW = int(os.getenv("ADAPTIVE_SAMPLING_WINDOW", "6"))      # 观察窗口大小（最近N次采样）

# ── 截图压缩质量（1-100）──
SCREENSHOT_QUALITY = int(os.getenv("SCREENSHOT_QUALITY", "70"))

# ── 截图最大宽度像素（超过则等比缩放）──
SCREENSHOT_MAX_WIDTH = int(os.getenv("SCREENSHOT_MAX_WIDTH", "1920"))

# ── HTTP API 端口 ──
HTTP_PORT = int(os.getenv("PORT", os.getenv("HTTP_PORT", "58888")))

# ── HTTP 绑定地址 ──
# 默认 0.0.0.0：自习室"扫描局域网"需要让同网段设备能访问本机 /api/study-room/heartbeat。
# 其余所有接口仍有 token 鉴权 + rate limit 保护；设 HTTP_HOST=127.0.0.1 可回退为仅本机访问。
HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")

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

# ── P20-3: AI 调用参数集中化 ──────────────────────────────────
# 设计依据：原先 14+ 处 AI 调用各自硬编码 max_tokens/temperature，调优困难。
# 统一到 AI_PARAMS 后可一键调整成本/质量权衡，并为后续 A/B 测试打基础。
# 取值参考：
#   - vision_classify: 低温度 0.2 保证分类稳定，500 tokens 足够 JSON 响应
#   - text_report: 中温度 0.78 让日报有温度，6000 tokens 覆盖全天叙事
#   - chat: 中温度 0.7 平衡创意与可控，2000 tokens 单轮对话
#   - insight: 中高温度 0.7 让洞察有变化，400 tokens 简短有力
#   - weekly_report: 中温度 0.5 保持周报严谨，1500 tokens 覆盖周叙事
#   - json_extract: 低温度 0.4 保证 JSON 结构稳定，1500 tokens
AI_PARAMS = {
    "vision_classify": {"max_tokens": 500, "temperature": 0.2},
    "vision_classify_lite": {"max_tokens": 220, "temperature": 0.3},  # 概要分类，更省 token
    "context_extract": {"max_tokens": 600, "temperature": 0.2},         # 上下文抽取，需稳定
    "text_report": {"max_tokens": 6000, "temperature": 0.78},           # 日报生成，叙事性
    "weekly_report": {"max_tokens": 1500, "temperature": 0.5},          # 周报，简洁
    "report_summary": {"max_tokens": 500, "temperature": 0.4},          # 报告精简
    "chat": {"max_tokens": 2000, "temperature": 0.7},                   # 对话
    "chat_json": {"max_tokens": 1500, "temperature": 0.85},             # 对话式 JSON
    "insight": {"max_tokens": 400, "temperature": 0.7},                 # 洞察推送
    "agent": {"max_tokens": 800, "temperature": 0.7},                   # Agent 决策
    "agent_lite": {"max_tokens": 10, "temperature": 1.0},               # Agent 极简决策
    "week_plan": {"max_tokens": 1000, "temperature": 0.7},              # 周计划
    "local_vision": {"max_tokens": 500, "temperature": 0.3},            # 本地 Ollama 视觉
    "local_text": {"max_tokens": 1500, "temperature": 0.6},             # 本地 Ollama 文本
}


def get_ai_params(preset: str) -> dict:
    """
    获取指定 preset 的 AI 调用参数（max_tokens + temperature）。
    preset 必须是 AI_PARAMS 中的键。
    返回的 dict 是副本，调用方可安全修改。
    """
    preset_params = AI_PARAMS.get(preset)
    if preset_params is None:
        # 未知 preset 回退到最通用的 chat 参数，并记录警告
        logging.getLogger(__name__).warning(f"未知 AI 参数 preset: {preset}，回退到 chat")
        preset_params = AI_PARAMS["chat"]
    return dict(preset_params)

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
    "birthday": "",
    "life_expectancy": 80,
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
