"""P52+P57: 集中化常量 — 消除散落在各文件中的魔法数字

所有阈值、限制、配置常量集中管理，避免不一致和难以调优。
"""

# ── 专注与效率阈值 ──
DEEP_WORK_MIN_MINUTES = 25          # 深度工作最小分钟数
FOCUS_SESSION_MIN_MINUTES = 15      # 专注会话最小分钟数
FLOW_PROTECT_THRESHOLD_MIN = 25     # 心流保护阈值（分钟）
SMART_BREAK_FLOW_MIN = 25           # 心流后建议休息阈值
SMART_BREAK_WORK_MIN = 50           # 连续工作建议休息阈值
OVERWORK_THRESHOLD_MIN = 120        # 过劳保护阈值（2小时）
DISTRACTION_LIGHT_MIN = 15          # 轻度摸鱼提醒
DISTRACTION_HEAVY_MIN = 30          # 中度摸鱼干预

# ── 采集相关 ──
MAX_SCREENSHOT_SIZE_MB = 10         # 单张截图最大体积
SCREENSHOT_DEDUP_HASH_THRESHOLD = 0.95  # 截图去重相似度阈值
MAX_WINDOWS_PER_CAPTURE = 10        # 单次采集最多记录窗口数
CAPTURE_QUEUE_MAX_SIZE = 100        # 采集队列最大长度

# ── AI 调用限制 ──
AI_RATE_LIMIT_VISION_PER_MIN = 30   # 视觉 AI 每分钟最大调用
AI_RATE_LIMIT_TEXT_PER_MIN = 20     # 文本 AI 每分钟最大调用
AI_RATE_LIMIT_CHAT_PER_MIN = 10     # 聊天 AI 每分钟最大调用
AI_RETRY_MAX_ATTEMPTS = 3           # AI 调用最大重试次数
AI_RETRY_BASE_DELAY_SEC = 1.0       # AI 重试基础延迟
AI_RETRY_MAX_DELAY_SEC = 30.0       # AI 重试最大延迟
AI_TIMEOUT_SEC = 60                 # AI 调用超时
AI_VISION_TIMEOUT_SEC = 30          # AI 视觉调用超时

# ── 数据库 ──
DB_BUSY_TIMEOUT_MS = 5000           # SQLite busy 超时
DB_CACHE_SIZE_MB = 4                # SQLite cache 大小
DB_MMAP_SIZE_MB = 256               # SQLite mmap 大小
DB_MAX_RETRIES = 3                  # DB 操作最大重试
DB_RETRY_BASE_DELAY_SEC = 0.1       # DB 重试基础延迟

# ── 数据保留 ──
DEFAULT_RETENTION_DAYS = 90         # 默认数据保留天数
BACKUP_MAX_COUNT = 10               # 最大备份数
BACKUP_INTERVAL_HOURS = 6           # 备份间隔小时

# ── HTTP API ──
API_DEFAULT_TIMEOUT_SEC = 10        # API 默认超时
API_LONG_TIMEOUT_SEC = 60           # API 长超时（报告生成等）
API_MAX_BODY_SIZE_KB = 1024         # API 请求体最大大小
API_RATE_LIMIT_DEFAULT = 60         # 默认速率限制（每分钟）
API_RATE_LIMIT_WINDOW_SEC = 60      # 速率限制窗口

# ── 前端轮询 ──
POLL_INTERVAL_COACH_SEC = 30        # 行为教练轮询间隔
POLL_INTERVAL_PET_SEC = 10          # 宠物状态轮询间隔
POLL_INTERVAL_NOTIFICATION_SEC = 60 # 通知轮询间隔
POLL_INTERVAL_BACKEND_CHECK_SEC = 1 # 后端检查间隔

# ── 文本限制 ──
MAX_APP_NAME_LEN = 100              # 应用名最大长度
MAX_WINDOW_TITLE_LEN = 200          # 窗口标题最大长度
MAX_SUMMARY_LEN = 200               # 摘要最大长度
MAX_REPORT_LEN = 50000              # 日报最大长度
MAX_AI_DETAIL_LEN = 1000            # AI 详情最大长度
MAX_CHAT_HISTORY = 50               # 聊天历史最大条数

# ── 情绪公式权重（文档化）──
MOOD_WEIGHT_PRODUCTIVITY = 0.35     # 生产力权重
MOOD_WEIGHT_FOCUS = 0.25            # 专注度权重
MOOD_WEIGHT_RHYTHM = 0.20           # 节奏权重
MOOD_WEIGHT_VARIETY = 0.10          # 多样性权重
MOOD_WEIGHT_BREAK = 0.10            # 休息权重
# 总和 = 1.00

# ── Bloom 分类学权重（参考 docs/bloom_weights.md）──
BLOOM_WEIGHTS = {
    "remember": 0.10,
    "understand": 0.15,
    "apply": 0.20,
    "analyze": 0.20,
    "evaluate": 0.20,
    "create": 0.15,
}
