"""ChallengeDaily Web Tracker — 接收 WebExtension 发来的网页活动

端点：
  POST /api/web-activity/           单条网页活动
  POST /api/web-activity/batch      批量网页活动
  GET  /api/web-activity/stats/today 今日网页活动统计

数据存入 web_activities 表（独立于 app_usage，避免与桌面端 chrome.exe 追踪重复计数）。
start_time 统一归一化为 "%Y-%m-%d %H:%M:%S" 本地时间格式，与现有系统一致。
"""
import os
import logging
from datetime import datetime, date
from flask import Blueprint, jsonify, request

from db import get_conn
from routes.deps import safe_error

logger = logging.getLogger(__name__)

bp = Blueprint('web_tracker', __name__, url_prefix='/api/web-activity')

# 可选 Token：仅当环境变量 CHALLENGE_WEB_TOKEN 设置时才校验（localhost 默认不校验）
_WEB_TOKEN = os.getenv("CHALLENGE_WEB_TOKEN", "").strip()

# 域名 → 分类 推断规则（与扩展端保持一致，作为后端兜底）
_DOMAIN_CATEGORY_RULES = [
    (("github.com", "gitlab.com", "gitee.com", "bitbucket.org"), "开发"),
    (("stackoverflow.com", "stackexchange.com", "leetcode.com", "coursera.org", "mooc"), "学习"),
    (("gmail.com", "outlook.com", "mail.google.com", "mail.qq.com", "feishu.cn"), "沟通"),
    (("notion.so", "notion.com", "docs.google.com", "yuque.com", "mubu.com"), "文档"),
    (("youtube.com", "bilibili.com", "netflix.com", "youku.com", "iqiyi.com"), "生活"),
]

_INITED = False


def _ensure_table():
    """首次调用时建表（幂等）。使用模块级标志避免每次请求都执行 DDL。"""
    global _INITED
    if _INITED:
        return
    try:
        with get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS web_activities (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    url          TEXT,
                    domain       TEXT NOT NULL,
                    title        TEXT,
                    category     TEXT,
                    start_time   TEXT NOT NULL,
                    end_time     TEXT,
                    duration_sec INTEGER DEFAULT 0,
                    tab_id       INTEGER,
                    source       TEXT DEFAULT 'webextension',
                    created_at   TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_web_activities_start ON web_activities(start_time);
                CREATE INDEX IF NOT EXISTS idx_web_activities_domain ON web_activities(domain);
                CREATE INDEX IF NOT EXISTS idx_web_activities_category ON web_activities(category);
            """)
            conn.commit()
        _INITED = True
    except Exception as e:
        logger.error(f"web_activities 建表失败: {e}")
        raise


def _parse_start_time(raw) -> str:
    """将扩展发来的 start_time（ISO 8601 如 2026-07-28T10:00:00）归一化为 YYYY-MM-DD HH:MM:SS"""
    if not raw:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(max(0, raw)).strftime("%Y-%m-%d %H:%M:%S")
    s = str(raw).strip()
    # 兼容带 Z / 带时区的情况
    try:
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    # 兼容已有的本地格式
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _infer_category(domain: str, url: str = "") -> str:
    d = (domain or "").lower()
    u = (url or "").lower()
    for keys, cat in _DOMAIN_CATEGORY_RULES:
        for k in keys:
            if k in d or k in u:
                return cat
    return "其他"


def _check_token():
    """校验可选 Token。未配置则放行。"""
    if not _WEB_TOKEN:
        return True
    auth = request.headers.get("Authorization", "")
    token = auth.replace("Bearer", "", 1).strip() if auth else ""
    if not token:
        token = request.headers.get("X-Api-Token", "").strip()
    return token == _WEB_TOKEN


def _insert_activity(conn, data: dict):
    """插入一条网页活动记录（已做字段校验与归一化）。返回新 id。"""
    domain = str(data.get("domain", "")).strip()
    if not domain:
        raise ValueError("domain 必填")

    url = str(data.get("url", "")).strip()
    title = str(data.get("title", "")).strip()
    category = str(data.get("category", "")).strip()
    if not category:
        category = _infer_category(domain, url)

    start_time = _parse_start_time(data.get("start_time"))
    try:
        duration_sec = int(data.get("duration_sec", 0))
    except (TypeError, ValueError):
        duration_sec = 0
    # 单条记录时长上限 1 天，避免异常值污染统计
    duration_sec = max(0, min(86400, duration_sec))

    end_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
    from datetime import timedelta
    end_time = (end_dt + timedelta(seconds=duration_sec)).strftime("%Y-%m-%d %H:%M:%S")

    try:
        tab_id = int(data.get("tab_id", 0))
    except (TypeError, ValueError):
        tab_id = 0

    cursor = conn.execute(
        "INSERT INTO web_activities (url, domain, title, category, start_time, end_time, duration_sec, tab_id, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (url, domain, title, category, start_time, end_time, duration_sec, tab_id, "webextension"),
    )
    return cursor.lastrowid


@bp.route('/', methods=['POST'])
def receive_web_activity():
    """接收 WebExtension 发来的单条网页活动

    Body: {url, domain, title, start_time, duration_sec, tab_id, category?}
    """
    if not _check_token():
        return jsonify({"error": "无效的 API Token"}), 401
    _ensure_table()
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "请求体需为 JSON 对象"}), 400
    try:
        with get_conn() as conn:
            new_id = _insert_activity(conn, data)
            conn.commit()
        return jsonify({"status": "ok", "id": new_id}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.exception("receive_web_activity 失败")
        return jsonify({"error": safe_error(e, "保存失败")}), 500


@bp.route('/batch', methods=['POST'])
def receive_batch():
    """批量接收网页活动

    Body: {activities: [{url, domain, title, start_time, duration_sec, tab_id, category?}, ...]}
    """
    if not _check_token():
        return jsonify({"error": "无效的 API Token"}), 401
    _ensure_table()
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "请求体需为 JSON 对象"}), 400
    activities = data.get("activities")
    if not isinstance(activities, list) or not activities:
        return jsonify({"error": "activities 需为非空数组"}), 400

    inserted = 0
    errors = []
    with get_conn() as conn:
        for idx, item in enumerate(activities):
            if not isinstance(item, dict):
                errors.append({"index": idx, "error": "非对象"})
                continue
            try:
                _insert_activity(conn, item)
                inserted += 1
            except Exception as e:
                errors.append({"index": idx, "error": str(e)})
        conn.commit()
    return jsonify({"status": "ok", "count": inserted, "errors": errors[:20]}), 201


@bp.route('/stats/today', methods=['GET'])
def today_stats():
    """今日网页活动统计：总时长、域名 Top 5、分类汇总"""
    _ensure_table()
    today = date.today().isoformat()
    start = f"{today} 00:00:00"
    end = f"{today} 23:59:59"
    try:
        with get_conn() as conn:
            # 总时长
            total_row = conn.execute(
                "SELECT COALESCE(SUM(duration_sec), 0) AS total FROM web_activities "
                "WHERE start_time >= ? AND start_time <= ?",
                (start, end),
            ).fetchone()
            total_sec = int(dict(total_row)["total"]) if total_row else 0

            # 域名 Top 5
            domain_rows = conn.execute(
                "SELECT domain, SUM(duration_sec) AS sec, COUNT(*) AS cnt "
                "FROM web_activities WHERE start_time >= ? AND start_time <= ? "
                "GROUP BY domain ORDER BY sec DESC LIMIT 5",
                (start, end),
            ).fetchall()
            top_domains = [
                {"domain": dict(r)["domain"],
                 "duration_sec": int(dict(r)["sec"] or 0),
                 "duration_min": round((dict(r)["sec"] or 0) / 60, 1),
                 "count": int(dict(r)["cnt"])}
                for r in domain_rows
            ]

            # 分类汇总
            cat_rows = conn.execute(
                "SELECT category, SUM(duration_sec) AS sec "
                "FROM web_activities WHERE start_time >= ? AND start_time <= ? "
                "GROUP BY category ORDER BY sec DESC",
                (start, end),
            ).fetchall()
            categories = [
                {"category": dict(r)["category"],
                 "duration_sec": int(dict(r)["sec"] or 0),
                 "duration_min": round((dict(r)["sec"] or 0) / 60, 1)}
                for r in cat_rows
            ]

            # 记录条数
            cnt_row = conn.execute(
                "SELECT COUNT(*) AS c FROM web_activities "
                "WHERE start_time >= ? AND start_time <= ?",
                (start, end),
            ).fetchone()
            record_count = int(dict(cnt_row)["c"]) if cnt_row else 0

        return jsonify({
            "date": today,
            "total_sec": total_sec,
            "total_min": round(total_sec / 60, 1),
            "record_count": record_count,
            "top_domains": top_domains,
            "categories": categories,
        })
    except Exception as e:
        logger.exception("today_stats 失败")
        return jsonify({"error": safe_error(e, "统计失败")}), 500
