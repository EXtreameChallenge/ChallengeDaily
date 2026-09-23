"""P0-3：报告模板系统

支持用户自定义 Markdown 报告模板，通过 {{placeholder}} 占位符注入当日数据。
内置 3 个默认模板：标准日报 / 简洁日报 / 周报模板。
"""
import logging
from datetime import datetime

from db import get_conn

logger = logging.getLogger(__name__)

# 支持的占位符白名单（render_template 只替换这些 key，避免误替换文本）
SUPPORTED_PLACEHOLDERS = (
    "date",
    "activities",
    "todos_completed",
    "todos_pending",
    "pomodoro_count",
    "focus_minutes",
    "apps_top5",
    "user_name",
    "user_role",
)


# ── 内置默认模板种子数据 ─────────────────────────────────────

_SEED_TEMPLATES = [
    {
        "name": "标准日报",
        "description": "包含日期、活动摘要、待办完成情况、番茄统计、Top5 应用",
        "is_default": 1,
        "content_md": (
            "# {{date}} 工作日报\n\n"
            "## 今日活动\n\n"
            "{{activities}}\n\n"
            "## 待办完成情况\n\n"
            "### 已完成\n\n"
            "{{todos_completed}}\n\n"
            "### 进行中 / 待办\n\n"
            "{{todos_pending}}\n\n"
            "## 专注统计\n\n"
            "- 完成番茄钟：{{pomodoro_count}} 个\n"
            "- 专注总时长：{{focus_minutes}} 分钟\n\n"
            "## Top5 应用使用\n\n"
            "{{apps_top5}}\n"
        ),
    },
    {
        "name": "简洁日报",
        "description": "只包含日期、一句话总结与关键数字",
        "is_default": 0,
        "content_md": (
            "# {{date}}\n\n"
            "> 一句话总结：{{activities}}\n\n"
            "- 已完成待办：{{todos_completed}}\n"
            "- 待办：{{todos_pending}}\n"
            "- 番茄钟：{{pomodoro_count}} 个 / 专注 {{focus_minutes}} 分钟\n"
        ),
    },
    {
        "name": "周报模板",
        "description": "包含周日期范围、每日概览、分类汇总",
        "is_default": 0,
        "content_md": (
            "# 周报（{{date}}）\n\n"
            "## 每日概览\n\n"
            "{{activities}}\n\n"
            "## 待办汇总\n\n"
            "- 已完成：{{todos_completed}}\n"
            "- 待处理：{{todos_pending}}\n\n"
            "## 专注汇总\n\n"
            "- 番茄钟：{{pomodoro_count}} 个\n"
            "- 专注时长：{{focus_minutes}} 分钟\n\n"
            "## Top5 应用\n\n"
            "{{apps_top5}}\n"
        ),
    },
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row) -> dict:
    d = dict(row)
    # is_default 在 SQLite 中是 INTEGER(0/1)，统一成 bool 语义返回
    d["is_default"] = bool(d.get("is_default", 0))
    return d


# ── 建表与种子数据 ───────────────────────────────────────────

def init_table() -> None:
    """建表（幂等）；若表为空则插入 3 个内置默认模板。"""
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_templates (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL,
                description  TEXT,
                content_md   TEXT NOT NULL,
                is_default   INTEGER DEFAULT 0,
                created_at   TEXT,
                updated_at   TEXT
            )
            """
        )
        row = conn.execute("SELECT COUNT(*) AS c FROM report_templates").fetchone()
        count = row["c"] if row else 0
        if count == 0:
            now = _now()
            for tpl in _SEED_TEMPLATES:
                conn.execute(
                    "INSERT INTO report_templates "
                    "(name, description, content_md, is_default, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        tpl["name"],
                        tpl["description"],
                        tpl["content_md"],
                        tpl["is_default"],
                        now,
                        now,
                    ),
                )
        conn.commit()
    logger.debug("report_templates 表已初始化")


# ── 查询 ────────────────────────────────────────────────────

def get_templates() -> list[dict]:
    """列出所有模板，默认模板排在最前，按 id 升序。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM report_templates ORDER BY is_default DESC, id ASC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_template(template_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM report_templates WHERE id=?", (template_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None


def get_default_template() -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM report_templates WHERE is_default=1 ORDER BY id ASC LIMIT 1"
        ).fetchone()
        return _row_to_dict(row) if row else None


# ── 写入 ────────────────────────────────────────────────────

def create_template(name: str, description: str, content_md: str,
                    is_default: bool = False) -> int:
    now = _now()
    with get_conn() as conn:
        if is_default:
            conn.execute("UPDATE report_templates SET is_default=0")
        cur = conn.execute(
            "INSERT INTO report_templates "
            "(name, description, content_md, is_default, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, description or "", content_md, 1 if is_default else 0, now, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_template(template_id: int, name: str, description: str,
                    content_md: str, is_default: bool) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM report_templates WHERE id=?", (template_id,)
        ).fetchone()
        if not row:
            return False
        if is_default:
            conn.execute("UPDATE report_templates SET is_default=0")
        conn.execute(
            "UPDATE report_templates SET name=?, description=?, content_md=?, "
            "is_default=?, updated_at=? WHERE id=?",
            (name, description or "", content_md, 1 if is_default else 0,
             _now(), template_id),
        )
        conn.commit()
        return True


def delete_template(template_id: int) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT is_default FROM report_templates WHERE id=?", (template_id,)
        ).fetchone()
        if not row:
            return False
        conn.execute("DELETE FROM report_templates WHERE id=?", (template_id,))
        conn.commit()
        return True


def set_default(template_id: int) -> bool:
    """将其他模板设为非默认，本条设为默认。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM report_templates WHERE id=?", (template_id,)
        ).fetchone()
        if not row:
            return False
        conn.execute("UPDATE report_templates SET is_default=0")
        conn.execute(
            "UPDATE report_templates SET is_default=1, updated_at=? WHERE id=?",
            (_now(), template_id),
        )
        conn.commit()
        return True


# ── 渲染 ────────────────────────────────────────────────────

def render_template(content_md: str, context: dict) -> str:
    """用 context 中的值替换模板中的 {{placeholder}} 占位符。

    只替换 SUPPORTED_PLACEHOLDERS 中的 key；context 中缺失的值替换为空串。
    未识别的占位符原样保留。
    """
    result = content_md or ""
    for key in SUPPORTED_PLACEHOLDERS:
        value = context.get(key, "")
        if value is None:
            value = ""
        result = result.replace("{{" + key + "}}", str(value))
    return result
