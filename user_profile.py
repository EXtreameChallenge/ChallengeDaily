"""P0-2：我的资料（用户画像）模块

单用户模式：id 固定为 1，存储称呼、角色、公司、当前项目、工作职责、
行业、工作年限、个人目标、AI 报告偏好风格等基础画像，用于注入 AI prompt。
"""
import logging
from datetime import datetime

from db import get_conn

logger = logging.getLogger(__name__)

# 单用户固定 id
_PROFILE_ID = 1

# 全量字段（与建表字段一一对应）
_PROFILE_FIELDS = (
    "nickname", "role", "company", "current_project",
    "responsibilities", "industry", "work_years",
    "goals", "report_style",
)

# 空画像（不存在时返回）
_EMPTY_PROFILE = {
    "id": _PROFILE_ID,
    "nickname": "",
    "role": "",
    "company": "",
    "current_project": "",
    "responsibilities": "",
    "industry": "",
    "work_years": None,
    "goals": "",
    "report_style": "",
    "created_at": "",
    "updated_at": "",
}


# 我的资料所需列及其类型（用于 CREATE / ALTER 补列）
_PROFILE_COLUMNS = {
    "nickname": "TEXT",
    "role": "TEXT",
    "company": "TEXT",
    "current_project": "TEXT",
    "responsibilities": "TEXT",
    "industry": "TEXT",
    "work_years": "INTEGER",
    "goals": "TEXT",
    "report_style": "TEXT",
    "created_at": "TEXT",
    "updated_at": "TEXT",
}


def init_table() -> None:
    """建表并确保「我的资料」列存在（幂等）。

    项目中 user_profile 表可能已由 db_migrations（AI 深度画像）创建，
    此处用 CREATE TABLE IF NOT EXISTS 兜底全新库，再用 ALTER TABLE ADD COLUMN
    把缺失的「我的资料」列补进去，两套画像共用同一行（id=1），互不干扰。
    """
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                nickname TEXT,
                role TEXT,
                company TEXT,
                current_project TEXT,
                responsibilities TEXT,
                industry TEXT,
                work_years INTEGER,
                goals TEXT,
                report_style TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        # 补列：既有表可能缺少「我的资料」相关列
        existing = {row[1] for row in conn.execute("PRAGMA table_info(user_profile)").fetchall()}
        for col, col_type in _PROFILE_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE user_profile ADD COLUMN {col} {col_type}")
        conn.commit()
    logger.debug("user_profile 表已初始化（我的资料列已就绪）")


def _row_to_dict(row) -> dict:
    """sqlite3.Row -> dict，缺字段回退空值"""
    if row is None:
        return dict(_EMPTY_PROFILE)
    result = dict(_EMPTY_PROFILE)
    result.update({k: row[k] for k in row.keys()})
    result["id"] = _PROFILE_ID
    return result


def get_profile() -> dict:
    """获取用户画像；不存在时返回空字段 dict"""
    try:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM user_profile WHERE id=?", (_PROFILE_ID,)
            ).fetchone()
        return _row_to_dict(row)
    except Exception as e:
        # 表尚未创建等场景，静默回退空画像，避免影响主流程
        logger.warning(f"读取 user_profile 失败，返回空画像: {e}")
        return dict(_EMPTY_PROFILE)


def save_profile(data: dict) -> dict:
    """保存用户画像（UPSERT，单用户 id=1），返回最新画像 dict"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 仅接受白名单字段，work_years 做整数归一化
    values = {}
    for field in _PROFILE_FIELDS:
        if field in data and data[field] is not None:
            values[field] = data[field]
    if "work_years" in values:
        try:
            values["work_years"] = int(values["work_years"])
        except (TypeError, ValueError):
            values["work_years"] = None

    with get_conn() as conn:
        # 首次写入时带上 created_at
        existing = conn.execute(
            "SELECT created_at FROM user_profile WHERE id=?", (_PROFILE_ID,)
        ).fetchone()
        created_at = existing["created_at"] if existing else now

        set_clauses = ", ".join([f"{f}=?" for f in values.keys()])
        if set_clauses:
            params = list(values.values()) + [now]
            conn.execute(
                f"""
                UPDATE user_profile
                SET {set_clauses}, updated_at=?
                WHERE id=?
                """,
                params + [_PROFILE_ID],
            )
        # 无论是否有字段更新，都确保记录存在（INSERT OR IGNORE）
        conn.execute(
            """
            INSERT OR IGNORE INTO user_profile
                (id, nickname, role, company, current_project, responsibilities,
                 industry, work_years, goals, report_style, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _PROFILE_ID,
                values.get("nickname", ""),
                values.get("role", ""),
                values.get("company", ""),
                values.get("current_project", ""),
                values.get("responsibilities", ""),
                values.get("industry", ""),
                values.get("work_years"),
                values.get("goals", ""),
                values.get("report_style", ""),
                created_at,
                now,
            ),
        )
        conn.commit()
    logger.info("用户画像已保存")
    return get_profile()


def get_profile_context() -> str:
    """返回格式化的用户画像文本，用于注入 AI prompt。

    形如："用户称呼：XXX，角色：XXX，行业：XXX..."，仅拼写出有值的字段。
    """
    p = get_profile()
    parts = []
    label_map = [
        ("nickname", "用户称呼"),
        ("role", "角色/职位"),
        ("company", "公司/团队"),
        ("current_project", "当前项目"),
        ("responsibilities", "工作职责"),
        ("industry", "行业"),
        ("work_years", "工作年限"),
        ("goals", "个人目标"),
        ("report_style", "AI报告偏好风格"),
    ]
    for field, label in label_map:
        val = p.get(field)
        if val is None or str(val).strip() == "":
            continue
        if field == "work_years":
            parts.append(f"{label}：{val}年")
        else:
            parts.append(f"{label}：{val}")
    return "，".join(parts)
