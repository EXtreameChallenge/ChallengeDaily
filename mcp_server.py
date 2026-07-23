"""
ChallengeDaily MCP Server — 让外部 Agent 读写桌面端数据库
================================================================
设计要点：
1. 零外部依赖：仅用 Python 标准库，避免给项目新增 pip 依赖
2. stdio JSON-RPC：原生兼容 Claude Desktop / Cursor / TRAE / Continue 等
3. HTTP 调本地 Flask：所有读写走 http://127.0.0.1:58888 + X-API-Token
   —— 完整复用现有 routes 的鉴权、校验、事务、ETag，不绕过任何安全层
4. token 自动读取：优先 userData/backend-data，回退项目 data 目录
5. 进程生命周期：可由 Electron 主进程拉起，也可独立 `python mcp_server.py` 跑

启动：
    python mcp_server.py                    # 默认 stdio 模式
    set MCP_LOG_LEVEL=DEBUG  python mcp_server.py   # 开 debug 日志

注意：故意不使用 `from __future__ import annotations`，
因为 inspect.signature 不会自动 eval 字符串注解，会导致类型推断失败。
"""
import json
import os
import sys
import time
import logging
import threading
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Any, Callable, Optional

# ──────────────────────────────────────────────────────────────
# 配置：与 Electron 后端共享同一个 backend-data 目录
# ──────────────────────────────────────────────────────────────

# 1. 环境变量优先（Electron 启动时会注入）
_DATA_DIR_ENV = os.environ.get("CHALLENGE_DAILY_DATA_DIR", "").strip()

# 2. 用户级 userData 目录（与 main.cjs _userDataPath 完全一致）
_APPDATA = os.environ.get("APPDATA", "")
_CANDIDATE_DATA_DIRS: list[Path] = []
if _DATA_DIR_ENV:
    _CANDIDATE_DATA_DIRS.append(Path(_DATA_DIR_ENV))
if _APPDATA:
    _CANDIDATE_DATA_DIRS.append(Path(_APPDATA) / "challenge-daily" / "backend-data")
# 3. 项目内 data 目录（开发模式兜底）
_CANDIDATE_DATA_DIRS.append(Path(__file__).resolve().parent / "data")


def _resolve_data_dir() -> Path:
    """找到第一个含 .api_token 的目录，否则返回最后一个候选"""
    for p in _CANDIDATE_DATA_DIRS:
        if (p / ".api_token").exists():
            return p
    return _CANDIDATE_DATA_DIRS[-1]


DATA_DIR = _resolve_data_dir()
TOKEN_PATH = DATA_DIR / ".api_token"
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "mcp_server.log"

BACKEND_URL = os.environ.get("CHALLENGE_DAILY_BACKEND_URL", "http://127.0.0.1:58888")
BACKEND_TIMEOUT = float(os.environ.get("CHALLENGE_DAILY_BACKEND_TIMEOUT", "15"))
# 后端启动等待：Flask 可能比 MCP 晚几秒起来，第一次请求重试窗口
BACKEND_READY_WAIT = float(os.environ.get("CHALLENGE_DAILY_BACKEND_READY_WAIT", "30"))

SERVER_NAME = "challenge-daily-mcp"
SERVER_VERSION = "1.0.0"

# ──────────────────────────────────────────────────────────────
# 日志：同时写文件和 stderr（stderr 不污染 stdio JSON-RPC 通道，
#      因为 stdout 才是 JSON-RPC 通道，stderr 是 MCP 协议允许的日志通道）
# ──────────────────────────────────────────────────────────────


def _setup_logging() -> logging.Logger:
    level = os.environ.get("MCP_LOG_LEVEL", "INFO").upper()
    logger = logging.getLogger("mcp")
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False

    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件 handler
    try:
        fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass

    # stderr handler（stdio MCP 协议中 stderr 是合法日志通道）
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


log = _setup_logging()
log.info("=" * 60)
log.info(f"MCP Server starting, DATA_DIR={DATA_DIR}")
log.info(f"BACKEND_URL={BACKEND_URL}, TOKEN_PATH={TOKEN_PATH}")


# ──────────────────────────────────────────────────────────────
# Token 读取（与 routes/deps.py 完全一致，支持 30 天轮换）
# ──────────────────────────────────────────────────────────────


def _read_token() -> str:
    """读取本地 API token，与后端 routes/deps.py 共用同一文件"""
    try:
        if TOKEN_PATH.exists():
            t = TOKEN_PATH.read_text(encoding="utf-8").strip()
            if t:
                return t
    except Exception as e:
        log.warning(f"读取 token 失败: {e}")
    return ""


_TOKEN_CACHE: dict[str, Any] = {"value": "", "ts": 0.0}
_TOKEN_TTL = 5.0  # 5 秒缓存，避免每次工具调用都读磁盘


def get_token() -> str:
    now = time.time()
    if _TOKEN_CACHE["value"] and (now - _TOKEN_CACHE["ts"]) < _TOKEN_TTL:
        return _TOKEN_CACHE["value"]
    t = _read_token()
    _TOKEN_CACHE["value"] = t
    _TOKEN_CACHE["ts"] = now
    return t


# ──────────────────────────────────────────────────────────────
# HTTP 客户端：调用本地 Flask 后端
# ──────────────────────────────────────────────────────────────


class BackendError(Exception):
    def __init__(self, message: str, status: int = 0, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _backend_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    retry_on_not_ready: bool = True,
) -> Any:
    """调用本地 Flask 后端，返回解析后的 JSON。

    自动注入 X-API-Token，处理 401（token 失效）、503（Flask 未就绪）等。
    """
    url = BACKEND_URL.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )

    headers = {"Accept": "application/json", "X-API-Token": get_token()}
    body_bytes: bytes | None = None
    if json_body is not None:
        body_bytes = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    deadline = time.time() + BACKEND_READY_WAIT if retry_on_not_ready else time.time() + BACKEND_TIMEOUT
    last_err: Exception | None = None

    while True:
        try:
            req = urllib.request.Request(url, data=body_bytes, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=BACKEND_TIMEOUT) as resp:
                raw = resp.read()
                if not raw:
                    return None
                ct = resp.headers.get("Content-Type", "")
                if "application/json" in ct:
                    return json.loads(raw.decode("utf-8"))
                return raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
            try:
                parsed = json.loads(raw) if raw else None
            except Exception:
                parsed = raw

            # 401：token 可能刚轮换，强制重读后重试一次
            if e.code == 401:
                log.warning("401, 强制刷新 token 重试")
                _TOKEN_CACHE["value"] = ""
                _TOKEN_CACHE["ts"] = 0.0
                if get_token():
                    continue

            # 503：Flask 正在启动
            if e.code == 503 and retry_on_not_ready and time.time() < deadline:
                log.info("Backend 503, waiting 0.5s ...")
                time.sleep(0.5)
                continue

            raise BackendError(f"Backend {e.code} on {method} {path}", status=e.code, body=parsed)
        except urllib.error.URLError as e:
            # 连不上后端：可能是 Flask 还没起来
            last_err = e
            if retry_on_not_ready and time.time() < deadline:
                log.info(f"Backend not reachable ({e}), retry in 0.5s ...")
                time.sleep(0.5)
                continue
            raise BackendError(f"Backend not reachable: {e}")
        except Exception as e:
            last_err = e
            raise BackendError(f"Backend request failed: {e}")

    if last_err:
        raise BackendError(f"Backend unreachable after {BACKEND_READY_WAIT}s: {last_err}")


# ──────────────────────────────────────────────────────────────
# 工具实现：每个工具对应一个 Flask route
# ──────────────────────────────────────────────────────────────


def _ok(text: str | dict | list) -> list[dict]:
    """构造 MCP tools/call 成功响应（content 数组）"""
    if isinstance(text, (dict, list)):
        text = json.dumps(text, ensure_ascii=False, indent=2)
    return [{"type": "text", "text": str(text)}]


def _err(text: str) -> list[dict]:
    return [{"type": "text", "text": f"ERROR: {text}", "isError": True}]


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


def _week_start(d: str | None = None) -> str:
    from datetime import date, timedelta
    today = date.fromisoformat(d) if d else date.today()
    return (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")


# ── 待办 ──────────────────────────────────────────────────────


def tool_list_todos(status: str = "all") -> list[dict]:
    """列出待办清单

    Args:
        status: all / pending / completed
    """
    data = _backend_request("GET", "/api/todos", params={"status": status})
    return _ok(data)


def tool_create_todo(
    title: str,
    category: str = "开发",
    target_min: int = 25,
    priority: int = 2,
    task_level: str = "day",
    due_date: str | None = None,
    assigned_date: str | None = None,
    week_start: str | None = None,
    month_key: str | None = None,
    parent_id: int | None = None,
    estimated_pomodoros: int = 1,
    pomodoro_size: str = "big",
    goal_id: int | None = None,
    mode: str = "timer",
    repeat_type: str = "none",
    repeat_days: str = "",
) -> list[dict]:
    """创建一条待办

    Args:
        title: 待办标题（必填）
        category: 分类，可选：开发/测试/运维/数据分析/产品/设计/管理/文档/会议/沟通/学习/生活
        target_min: 目标分钟数 5-480
        priority: 优先级 1-5
        task_level: 层级 month/week/day
        due_date: 截止日期 YYYY-MM-DD
        assigned_date: 分配到某天 YYYY-MM-DD
        week_start: 所属周 YYYY-MM-DD（周一）
        month_key: 所属月 YYYY-MM
        parent_id: 父任务 id
        estimated_pomodoros: 预计番茄数
        pomodoro_size: big/small
        goal_id: 关联目标 id
        mode: timer/manual
        repeat_type: none/daily/weekly/monthly
        repeat_days: 重复日（如 "1,3,5"）
    """
    body = {
        "title": title,
        "category": category,
        "target_min": target_min,
        "priority": priority,
        "task_level": task_level,
        "due_date": due_date,
        "assigned_date": assigned_date,
        "week_start": week_start,
        "month_key": month_key,
        "parent_id": parent_id,
        "estimated_pomodoros": estimated_pomodoros,
        "pomodoro_size": pomodoro_size,
        "goal_id": goal_id,
        "mode": mode,
        "repeat_type": repeat_type,
        "repeat_days": repeat_days,
    }
    data = _backend_request("POST", "/api/todos", json_body=body)
    return _ok(data)


def tool_complete_todo(todo_id: int, completed_at: str | None = None) -> list[dict]:
    """把指定待办标记为完成

    Args:
        todo_id: 待办 id
        completed_at: 完成时间（不传则用当前时间）
    """
    from datetime import datetime
    body = {"status": "completed", "completed_at": completed_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    data = _backend_request("PUT", f"/api/todos/{todo_id}", json_body=body)
    return _ok(data)


# ── 活动 ──────────────────────────────────────────────────────


def tool_list_activities(target_date: str | None = None, page: int = 1, per_page: int = 200) -> list[dict]:
    """列出某天的活动记录（应用切换、分类、AI 摘要）

    Args:
        target_date: 日期 YYYY-MM-DD，默认今天
        page: 页码
        per_page: 每页 1-500
    """
    data = _backend_request("GET", "/api/activities", params={
        "date": target_date or _today(),
        "page": page,
        "per_page": per_page,
    })
    return _ok(data)


def tool_get_activity_stats(target_date: str | None = None) -> list[dict]:
    """获取某天活动分类统计（每类时长占比、专注度等）

    Args:
        target_date: 日期 YYYY-MM-DD
    """
    # 后端实际路由为 /api/stats/date/<date>，今天的为 /api/stats/today
    d = target_date or _today()
    path = "/api/stats/today" if d == _today() else f"/api/stats/date/{d}"
    data = _backend_request("GET", path)
    return _ok(data)


# ── 日记 ──────────────────────────────────────────────────────


def tool_get_diary(diary_date: str | None = None) -> list[dict]:
    """获取某天日记

    Args:
        diary_date: 日期 YYYY-MM-DD
    """
    data = _backend_request("GET", f"/api/diaries/{diary_date or _today()}")
    return _ok(data)


def tool_save_diary(
    content: str,
    diary_date: str | None = None,
    mood: str = "",
    weather: str = "",
    tags: str = "",
    highlights: str = "",
    gratitude: str = "",
) -> list[dict]:
    """保存或更新日记（一日一页，覆盖当天）

    Args:
        content: 日记正文
        diary_date: 日期 YYYY-MM-DD，默认今天
        mood: 心情
        weather: 天气
        tags: 标签（逗号分隔）
        highlights: 当日亮点
        gratitude: 感恩
    """
    body = {
        "diary_date": diary_date or _today(),
        "content": content,
        "mood": mood,
        "weather": weather,
        "tags": tags,
        "highlights": highlights,
        "gratitude": gratitude,
    }
    data = _backend_request("POST", "/api/diaries", json_body=body)
    return _ok(data)


def tool_list_diaries(limit: int = 30) -> list[dict]:
    """列出最近 N 天日记

    Args:
        limit: 1-200，默认 30
    """
    data = _backend_request("GET", "/api/diaries/list", params={"limit": limit})
    return _ok(data)


# ── 习惯 ──────────────────────────────────────────────────────


def tool_list_habits() -> list[dict]:
    """列出所有习惯 + 最近 30 天打卡日志"""
    data = _backend_request("GET", "/api/habits")
    return _ok(data)


def tool_check_habit(habit_id: int, target_date: str | None = None) -> list[dict]:
    """给指定习惯打卡

    Args:
        habit_id: 习惯 id
        target_date: 打卡日期 YYYY-MM-DD，默认今天
    """
    body = {"log_date": target_date or _today(), "count": 1}
    data = _backend_request("POST", f"/api/habits/{habit_id}/log", json_body=body)
    return _ok(data)


# ── 周计划 ──────────────────────────────────────────────────────


def tool_get_week_plan(week_start: str | None = None) -> list[dict]:
    """获取周计划（含周一到周日每日任务）

    Args:
        week_start: 周一日期 YYYY-MM-DD，默认本周
    """
    data = _backend_request("GET", f"/api/week-plan/week/{week_start or _week_start()}")
    return _ok(data)


def tool_get_unassigned_todos() -> list[dict]:
    """获取待分配区所有任务"""
    data = _backend_request("GET", "/api/week-plan/unassigned")
    return _ok(data)


# ── 报告 ──────────────────────────────────────────────────────


def tool_get_daily_report(target_date: str | None = None, template: str = "standard") -> list[dict]:
    """生成/获取某天日报

    Args:
        target_date: 日期 YYYY-MM-DD
        template: standard/simple/technical/okr/ai/deep
    """
    data = _backend_request("GET", "/api/report/daily", params={
        "date": target_date or _today(),
        "template": template,
    })
    return _ok(data)


def tool_get_ai_insight(force: bool = False) -> list[dict]:
    """获取今日 AI 晨报洞察（活泼可爱温馨风格）

    Args:
        force: 是否强制重新生成（默认仅在 7-11 点且未推送时生成）
    """
    data = _backend_request("GET", "/api/insight/morning", params={"force": "1" if force else "0"})
    return _ok(data)


# ── 目标 ──────────────────────────────────────────────────────


def tool_list_goals(status: str | None = None, timeframe: str | None = None) -> list[dict]:
    """列出长期目标

    Args:
        status: active/completed/archived
        timeframe: yearly/quarterly/monthly
    """
    data = _backend_request("GET", "/api/goals", params={"status": status, "timeframe": timeframe})
    return _ok(data)


# ── 番茄钟 ──────────────────────────────────────────────────────


def tool_list_pomodoro_sessions(target_date: str | None = None) -> list[dict]:
    """列出某天番茄钟会话

    Args:
        target_date: 日期 YYYY-MM-DD
    """
    data = _backend_request("GET", "/api/pomodoro/sessions", params={
        "date": target_date or _today(),
    })
    return _ok(data)


# ── 数据库只读查询（白名单 + 严格只读） ──────────────────────────────

# 仅允许 SELECT，且表名白名单
_ALLOWED_TABLES = {
    "activities", "todos", "diaries", "habits", "habit_logs",
    "pomodoro_sessions", "goals", "week_plan_meta", "month_tasks",
    "settings", "app_records", "app_tags", "countdowns",
    "daily_cards", "achievements", "growth_records",
}

_QUERY_BLOCKLIST_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create",
    "replace", "attach", "detach", "pragma", "vacuum",
    "transaction", "begin", "commit", "rollback",
)


def tool_query_database(sql: str, limit: int = 100) -> list[dict]:
    """执行只读 SQL 查询（白名单表 + 仅 SELECT）

    直接读 SQLite（WAL 模式支持多进程并发读），不依赖 Flask 后端进程是否启动。
    适合外部 agent 做历史数据聚合分析。

    Args:
        sql: SQL 语句（仅 SELECT，仅允许查询白名单表）
        limit: 返回行数上限 1-500
    """
    if not sql or not sql.strip():
        return _err("SQL 不能为空")
    normalized = sql.strip().lower()
    if not normalized.startswith("select"):
        return _err("仅允许 SELECT 语句")
    for kw in _QUERY_BLOCKLIST_KEYWORDS:
        if kw in normalized:
            return _err(f"SQL 含禁止关键字: {kw}")

    # 检查 from 后的表名
    import re
    # 提取所有 from/ join 后的表名
    table_tokens = re.findall(r"\b(?:from|join)\s+(\w+)", normalized)
    for t in table_tokens:
        if t not in _ALLOWED_TABLES:
            return _err(f"表 {t} 不在白名单内，仅允许: {sorted(_ALLOWED_TABLES)}")

    if limit < 1 or limit > 500:
        limit = max(1, min(500, limit))

    # 加 LIMIT 兜底（如果原 SQL 没有）
    if "limit" not in normalized:
        sql = f"{sql.rstrip(';')} LIMIT {limit}"

    # 直接读 SQLite（WAL 模式支持多进程读，不影响后端写入）
    db_path = DATA_DIR / "xiaohei.db"
    if not db_path.exists():
        return _err(f"数据库文件不存在: {db_path}")

    import sqlite3
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql).fetchall()
            result = [dict(r) for r in rows]
            return _ok({
                "rows": result,
                "count": len(result),
                "truncated": len(result) >= limit,
            })
    except sqlite3.Error as e:
        return _err(f"SQL 执行失败: {e}")
    except Exception as e:
        return _err(f"查询异常: {e}")


# ── 系统 ──────────────────────────────────────────────────────


def tool_health_check() -> list[dict]:
    """检查后端 + 数据库 + token 是否正常"""
    try:
        data = _backend_request("GET", "/api/health", retry_on_not_ready=True)
        return _ok({
            "backend": "ok",
            "backend_url": BACKEND_URL,
            "data_dir": str(DATA_DIR),
            "token_loaded": bool(get_token()),
            "health": data,
        })
    except BackendError as e:
        return _ok({
            "backend": "error",
            "backend_url": BACKEND_URL,
            "data_dir": str(DATA_DIR),
            "token_loaded": bool(get_token()),
            "error": str(e),
            "body": e.body,
        })


# ── 幕布文档 ────────────────────────────────────


def tool_search_mubu_docs(query: str, limit: int = 20) -> list[dict]:
    """搜索已同步的幕布文档（关键词匹配标题和正文，返回命中片段）

    Args:
        query: 搜索关键词
        limit: 返回条数上限 1-100
    """
    if not query or not query.strip():
        return _err("query 不能为空")
    data = _backend_request("GET", "/api/mubu/search", params={"q": query, "limit": limit})
    return _ok(data)


def tool_list_mubu_docs(limit: int = 50) -> list[dict]:
    """列出已同步的幕布文档（不含正文，节省带宽）

    Args:
        limit: 返回条数上限 1-500
    """
    data = _backend_request("GET", "/api/mubu/docs", params={"limit": limit})
    return _ok(data)


def tool_get_mubu_doc(doc_id: str) -> list[dict]:
    """获取单篇幕布文档完整内容

    Args:
        doc_id: 文档 id
    """
    data = _backend_request("GET", f"/api/mubu/docs/{doc_id}")
    return _ok(data)


def tool_get_mubu_context(days: int = 7, limit: int = 20) -> list[dict]:
    """获取最近编辑的幕布文档作为 AI 上下文（用于日报生成、深度分析）

    Args:
        days: 最近 N 天 1-90
        limit: 最多返回 N 篇 1-50
    """
    data = _backend_request("GET", "/api/mubu/context", params={"days": days, "limit": limit})
    return _ok(data)


def tool_get_mubu_sync_status() -> list[dict]:
    """获取幕布文档同步状态（文档数、最后同步时间、cookie 是否有效）"""
    data = _backend_request("GET", "/api/mubu/status")
    return _ok(data)


# ──────────────────────────────────────────────────────────────
# 工具注册表
# ──────────────────────────────────────────────────────────────

# JSON Schema 类型 → Python 类型
_PY_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _coerce(value: Any, schema: dict) -> Any:
    """根据 schema 自动转换参数类型（MCP 客户端可能传字符串）"""
    if value is None:
        return None
    t = schema.get("type")
    if t == "integer":
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if t == "number":
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if t == "boolean":
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)
    return value


def _resolve_type(annotation: Any) -> str:
    """从 Python 类型注解推导 JSON Schema 类型，正确处理 Optional/Union"""
    import types
    import typing

    ann = annotation
    # 处理 Optional[X] / Union[X, None] / X | None
    origin = typing.get_origin(ann)
    if origin is typing.Union or (hasattr(types, "UnionType") and isinstance(ann, types.UnionType)):
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        if len(args) == 1:
            ann = args[0]
        else:
            return "string"  # 复合 Union，退化为 string

    if ann is int:
        return "integer"
    if ann is float:
        return "number"
    if ann is bool:
        return "boolean"
    if ann is dict:
        return "object"
    if ann is list:
        return "array"
    return "string"


def _build_tool_schemas() -> list[dict]:
    """从函数签名 + docstring 自动生成 MCP 工具 schema"""
    import inspect
    tools = []
    for name, fn in _TOOL_REGISTRY.items():
        sig = inspect.signature(fn)
        props = {}
        required = []
        for pname, param in sig.parameters.items():
            ptype = _resolve_type(param.annotation)

            prop = {"type": ptype}
            if param.default is inspect.Parameter.empty:
                required.append(pname)
            else:
                prop["default"] = param.default
            props[pname] = prop

        # 从 docstring 提取参数描述
        desc_lines = []
        if fn.__doc__:
            doc = inspect.getdoc(fn) or ""
            desc_lines.append(doc.split("Args:")[0].strip())
            # 提取 Args 部分
            if "Args:" in doc:
                args_section = doc.split("Args:", 1)[1].split("Returns:", 1)[0]
                for line in args_section.strip().splitlines():
                    line = line.strip()
                    if ":" in line and line:
                        arg_name, _, arg_desc = line.partition(":")
                        arg_name = arg_name.strip()
                        if arg_name in props:
                            props[arg_name]["description"] = arg_desc.strip()

        tools.append({
            "name": name,
            "description": desc_lines[0] if desc_lines else fn.__name__,
            "inputSchema": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        })
    return tools


# 工具注册表：name → callable
_TOOL_REGISTRY: dict[str, Callable[..., list[dict]]] = {
    "list_todos": tool_list_todos,
    "create_todo": tool_create_todo,
    "complete_todo": tool_complete_todo,
    "list_activities": tool_list_activities,
    "get_activity_stats": tool_get_activity_stats,
    "get_diary": tool_get_diary,
    "save_diary": tool_save_diary,
    "list_diaries": tool_list_diaries,
    "list_habits": tool_list_habits,
    "check_habit": tool_check_habit,
    "get_week_plan": tool_get_week_plan,
    "get_unassigned_todos": tool_get_unassigned_todos,
    "get_daily_report": tool_get_daily_report,
    "get_ai_insight": tool_get_ai_insight,
    "list_goals": tool_list_goals,
    "list_pomodoro_sessions": tool_list_pomodoro_sessions,
    "query_database": tool_query_database,
    "health_check": tool_health_check,
    "search_mubu_docs": tool_search_mubu_docs,
    "list_mubu_docs": tool_list_mubu_docs,
    "get_mubu_doc": tool_get_mubu_doc,
    "get_mubu_context": tool_get_mubu_context,
    "get_mubu_sync_status": tool_get_mubu_sync_status,
}

_TOOL_SCHEMAS = _build_tool_schemas()


# ──────────────────────────────────────────────────────────────
# MCP 协议：stdio JSON-RPC
# ──────────────────────────────────────────────────────────────

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": SERVER_NAME, "version": SERVER_VERSION}
CAPABILITIES = {"tools": {}}

# 读锁：stdin 是阻塞读取，写锁保护 stdout
_stdout_lock = threading.Lock()


def _send(msg: dict) -> None:
    """向 stdout 写一条 JSON-RPC 消息"""
    data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
    with _stdout_lock:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


def _send_result(req_id: Any, result: Any) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _send_error(req_id: Any, code: int, message: str, data: Any = None) -> None:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    _send({"jsonrpc": "2.0", "id": req_id, "error": err})


def _handle_initialize(req_id: Any, params: dict) -> None:
    _send_result(req_id, {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": CAPABILITIES,
        "serverInfo": SERVER_INFO,
    })


def _handle_tools_list(req_id: Any, params: dict) -> None:
    _send_result(req_id, {"tools": _TOOL_SCHEMAS})


def _handle_tools_call(req_id: Any, params: dict) -> None:
    name = params.get("name")
    args = params.get("arguments") or {}

    fn = _TOOL_REGISTRY.get(name)
    if fn is None:
        _send_error(req_id, -32601, f"Unknown tool: {name}")
        return

    # 类型转换
    import inspect
    sig = inspect.signature(fn)
    coerced = {}
    for pname, param in sig.parameters.items():
        if pname in args:
            schema = _find_tool_schema(name, pname)
            coerced[pname] = _coerce(args[pname], schema) if schema else args[pname]
        elif param.default is inspect.Parameter.empty:
            _send_error(req_id, -32602, f"Missing required argument: {pname}")
            return

    try:
        content = fn(**coerced)
        _send_result(req_id, {"content": content})
    except BackendError as e:
        log.warning(f"tool {name} backend error: {e}")
        _send_result(req_id, {
            "content": _err(f"Backend error ({e.status}): {e}\nBody: {json.dumps(e.body, ensure_ascii=False) if e.body else 'n/a'}"),
            "isError": True,
        })
    except Exception as e:
        log.exception(f"tool {name} failed")
        _send_result(req_id, {
            "content": _err(f"Tool execution failed: {e}"),
            "isError": True,
        })


def _find_tool_schema(tool_name: str, arg_name: str) -> dict | None:
    for t in _TOOL_SCHEMAS:
        if t["name"] == tool_name:
            return t["inputSchema"]["properties"].get(arg_name)
    return None


# 方法路由
_METHODS: dict[str, Callable[[Any, dict], None]] = {
    "initialize": _handle_initialize,
    "notifications/initialized": lambda *_: None,  # 通知无响应
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
    "ping": lambda req_id, _: _send_result(req_id, {}),
    "shutdown": lambda req_id, _: _send_result(req_id, {}),
}


def _process_line(line: str) -> None:
    """处理一行 JSON-RPC 消息"""
    if not line.strip():
        return
    try:
        msg = json.loads(line)
    except json.JSONDecodeError as e:
        log.warning(f"invalid JSON: {e}")
        _send_error(None, -32700, "Parse error", str(e))
        return

    req_id = msg.get("id")
    method = msg.get("method")

    if not method:
        _send_error(req_id, -32600, "Invalid Request: missing method")
        return

    handler = _METHODS.get(method)
    if handler is None:
        # 通知类方法（无 id）静默忽略；请求类方法返回 method not found
        if req_id is None:
            log.debug(f"ignoring unknown notification: {method}")
            return
        _send_error(req_id, -32601, f"Method not found: {method}")
        return

    try:
        handler(req_id, msg.get("params") or {})
    except Exception as e:
        log.exception(f"handler {method} crashed")
        _send_error(req_id, -32603, f"Internal error: {e}")


def main() -> None:
    log.info(f"Loaded {len(_TOOL_REGISTRY)} tools: {sorted(_TOOL_REGISTRY.keys())}")
    log.info("Listening on stdin (stdio JSON-RPC), protocol version %s", PROTOCOL_VERSION)

    # stdin 行缓冲读取
    for raw_line in sys.stdin:
        try:
            _process_line(raw_line.strip())
        except KeyboardInterrupt:
            log.info("KeyboardInterrupt, exiting")
            break
        except Exception as e:
            log.exception(f"unexpected error processing line: {e}")

    log.info("stdin closed, MCP Server exiting")


if __name__ == "__main__":
    main()
