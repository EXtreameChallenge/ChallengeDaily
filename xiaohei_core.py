"""
ChallengeDaily — 小黑日报助手满血版核心模块
=============================================
基于逆向分析小黑日报助手 preload.cjs（63个IPC模块）后的真实迁移实现。

本模块实现小黑核心业务逻辑（非占位）：
  1. AI 工作记录（work_records）— 截图→AI分析→结构化工作记录，含人工修正
  2. 积分计费账本（points ledger）— 真实余额/扣费/充值/使用记录
  3. 徽章系统（badges）— 事件触发式解锁
  4. 排行榜（leaderboard）— 从真实专注/工作数据计算
  5. 模板市场（template_market）— 本地持久化 CRUD
  6. Token 使用统计（token_usage）— 从 AI 调用记录聚合
  7. 帧去重日志（frame_dedup_log）— 截图去重日志持久化
  8. 数据管理（data_management）— 备份/导出/导入/清理

全部通过 SQLite 持久化（复用项目 db 连接池），数据真实可查。
"""
import json
import logging
import sqlite3
import time
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

from contextlib import contextmanager

from db import get_conn

logger = logging.getLogger(__name__)
_auto_extract_thread = None


@contextmanager
def _conn():
    """B04 修复：db.get_conn 不自动 commit，统一在块结束时提交。
    此前所有写路径（工作记录/积分/徽章/模板/Token/备份/清库）均未提交，
    HTTP 返回 ok 但数据从未落库（假成功）。
    """
    with get_conn() as conn:
        yield conn
        conn.commit()

# ════════════════════════════════════════════════════════════════
# 1. AI 工作记录 — 小黑最核心功能
#    截图采集 → AI 分析 → 生成结构化工作记录（分类/总结/耗时）
#    支持人工修正，支持按日汇总，支持从截图 timeline 提取
# ════════════════════════════════════════════════════════════════

_WORK_RECORD_CATEGORIES = [
    "编码开发", "文档写作", "会议沟通", "学习研究", "设计创作",
    "数据整理", "测试调试", "项目管理", "其他",
]


def init_xiaohei_tables():
    """初始化小黑核心功能所需的全部数据库表（幂等）"""
    with _conn() as conn:
        conn.executescript("""
            -- 工作记录表
            CREATE TABLE IF NOT EXISTS work_records (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                date        TEXT NOT NULL,
                category    TEXT DEFAULT '其他',
                title       TEXT NOT NULL,
                content     TEXT DEFAULT '',
                app_name    TEXT DEFAULT '',
                source_screenshot TEXT DEFAULT '',
                duration_sec INTEGER DEFAULT 0,
                editable    INTEGER DEFAULT 1,
                created_at  TEXT DEFAULT (datetime('now','localtime')),
                updated_at  TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_wr_date ON work_records(date);
            CREATE INDEX IF NOT EXISTS idx_wr_cat ON work_records(category);

            -- 积分账本表
            CREATE TABLE IF NOT EXISTS points_ledger (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                type        TEXT NOT NULL,           -- 'credit' | 'debit'
                amount      INTEGER NOT NULL,
                item        TEXT NOT NULL,           -- 积分项目名
                detail      TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now','localtime'))
            );

            -- 徽章表
            CREATE TABLE IF NOT EXISTS badges (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                icon        TEXT DEFAULT '🏅',
                desc        TEXT DEFAULT '',
                condition   TEXT DEFAULT '',         -- 触发条件说明
                unlocked    INTEGER DEFAULT 0,
                progress    INTEGER DEFAULT 0,       -- 当前进度
                target      INTEGER DEFAULT 1,       -- 目标值
                unlocked_at TEXT
            );

            -- 模板市场表
            CREATE TABLE IF NOT EXISTS template_market (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                category    TEXT DEFAULT '通用',
                content     TEXT DEFAULT '',
                downloads   INTEGER DEFAULT 0,
                price       INTEGER DEFAULT 0,
                is_local    INTEGER DEFAULT 1,
                created_at  TEXT DEFAULT (datetime('now','localtime'))
            );

            -- Token 使用记录表
            CREATE TABLE IF NOT EXISTS token_usage (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                feature     TEXT NOT NULL,           -- 功能名（报告/词云/聊天...）
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                cost_points  INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_tu_date ON token_usage(date(created_at));

            -- 帧去重日志表
            CREATE TABLE IF NOT EXISTS frame_dedup_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT NOT NULL,
                event       TEXT NOT NULL,           -- 'saved' | 'skipped'
                similarity  REAL DEFAULT 0,
                detail      TEXT DEFAULT '',
                created_at  TEXT DEFAULT (datetime('now','localtime'))
            );

            -- 数据管理表（记录备份历史）
            CREATE TABLE IF NOT EXISTS backup_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                filename    TEXT NOT NULL,
                size_bytes  INTEGER DEFAULT 0,
                kind        TEXT DEFAULT 'manual',   -- manual | auto
                created_at  TEXT DEFAULT (datetime('now','localtime'))
            );
        """)


# ── 工作记录核心逻辑 ──────────────────────────────────────────

def list_work_records(day: Optional[str] = None, category: Optional[str] = None,
                      limit: int = 100, offset: int = 0) -> list:
    """查询工作记录。day='YYYY-MM-DD' 精确到天；category 按分类过滤。"""
    init_xiaohei_tables()
    where, args = [], []
    if day:
        where.append("date = ?")
        args.append(day)
    if category and category != "全部":
        where.append("category = ?")
        args.append(category)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with _conn() as conn:
        rows = conn.execute(
            f"""SELECT * FROM work_records {where_sql}
                ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (*args, limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]


def create_work_record(data: dict) -> dict:
    """新建工作记录（可来自AI生成或人工录入）"""
    init_xiaohei_tables()
    day = data.get("date") or date.today().isoformat()
    category = data.get("category") or "其他"
    if category not in _WORK_RECORD_CATEGORIES:
        category = "其他"
    title = (data.get("title") or "").strip()[:200]
    if not title:
        title = f"工作记录 {datetime.now().strftime('%H:%M')}"
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO work_records
               (date, category, title, content, app_name, source_screenshot, duration_sec)
               VALUES (?,?,?,?,?,?,?)""",
            (day, category, title, data.get("content", ""),
             data.get("app_name", ""), data.get("source_screenshot", ""),
             int(data.get("duration_sec", 0)))
        )
        rid = cur.lastrowid
    logger.info(f"工作记录已创建: #{rid} {title}")
    return {"ok": True, "id": rid}


def update_work_record(rid: int, data: dict) -> dict:
    """更新工作记录（人工修正AI结果）"""
    init_xiaohei_tables()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM work_records WHERE id=?", (rid,)).fetchone()
        if not row:
            return {"ok": False, "error": "记录不存在"}
        fields = ["title", "content", "category", "app_name", "duration_sec"]
        sets, args = [], []
        for f in fields:
            if f in data:
                sets.append(f"{f} = ?")
                args.append(data[f])
        if sets:
            sets.append("updated_at = datetime('now','localtime')")
            conn.execute(f"UPDATE work_records SET {', '.join(sets)} WHERE id=?",
                         (*args, rid))
    return {"ok": True, "id": rid}


def delete_work_record(rid: int) -> dict:
    init_xiaohei_tables()
    with _conn() as conn:
        conn.execute("DELETE FROM work_records WHERE id=?", (rid,))
    return {"ok": True}


def get_work_records_daily_summary(day: Optional[str] = None) -> dict:
    """按日汇总：总记录数、总时长、分类分布、时间线摘要"""
    init_xiaohei_tables()
    day = day or date.today().isoformat()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM work_records WHERE date=? ORDER BY created_at", (day,)
        ).fetchall()
    total_dur = sum(r["duration_sec"] for r in rows)
    cat_map = {}
    for r in rows:
        cat_map[r["category"]] = cat_map.get(r["category"], 0) + 1
    return {
        "date": day,
        "count": len(rows),
        "total_seconds": total_dur,
        "total_minutes": round(total_dur / 60, 1),
        "categories": [{"name": k, "count": v} for k, v in sorted(cat_map.items(), key=lambda x: -x[1])],
        "records": [dict(r) for r in rows][:50],
    }


def extract_work_records_from_activities(day: Optional[str] = None) -> dict:
    """从截图的 activities 表提取/生成工作记录（小黑核心：截图→记录）"""
    init_xiaohei_tables()
    day = day or date.today().isoformat()
    with _conn() as conn:
        acts = conn.execute(
            """SELECT * FROM activities WHERE date(timestamp)=? AND summary IS NOT NULL
               ORDER BY timestamp""", (day,)
        ).fetchall()
    if not acts:
        return {"ok": True, "extracted": 0, "message": f"{day} 没有可提取的截图记录"}

    # 聚合相似应用为一条工作记录
    from collections import defaultdict
    app_groups = defaultdict(list)
    for a in acts:
        key = a["app_name"] or "未知应用"
        app_groups[key].append(dict(a))

    created = 0
    for app_name, items in app_groups.items():
        # 若当天该应用已有工作记录则跳过（幂等）
        with _conn() as conn:
            existing = conn.execute(
                "SELECT COUNT(*) c FROM work_records WHERE date=? AND app_name=?",
                (day, app_name)).fetchone()["c"]
        if existing:
            continue
        titles = [i.get("summary") or "" for i in items if i.get("summary")]
        content = "；".join(titles[:5])[:800]
        duration = sum(i.get("interval_sec") or 60 for i in items)
        category = _classify_app(app_name)
        title = app_name if len(app_name) < 30 else app_name[:27] + "..."
        with _conn() as conn:
            conn.execute(
                """INSERT INTO work_records
                   (date, category, title, content, app_name, source_screenshot, duration_sec)
                   VALUES (?,?,?,?,?,?,?)""",
                (day, category, title, content, app_name, items[0].get("screenshot") or "", duration))
        created += 1
    return {"ok": True, "extracted": created, "total_activities": len(acts)}


def _classify_app(app_name: str) -> str:
    """根据应用名粗分类"""
    name = app_name.lower()
    rules = [
        ("code", "编码开发"), ("visual", "编码开发"), ("idea", "编码开发"),
        ("pycharm", "编码开发"), ("vscode", "编码开发"), ("goland", "编码开发"),
        ("chrome", "学习研究"), ("edge", "学习研究"), ("browser", "学习研究"),
        ("word", "文档写作"), ("wps", "文档写作"), ("typora", "文档写作"),
        ("obsidian", "文档写作"), ("notion", "文档写作"),
        ("wechat", "会议沟通"), ("dingtalk", "会议沟通"), ("feishu", "会议沟通"),
        ("teams", "会议沟通"), ("zoom", "会议沟通"), ("qq", "会议沟通"),
        ("photoshop", "设计创作"), ("figma", "设计创作"), ("剪映", "设计创作"),
        ("excel", "数据整理"), ("numbers", "数据整理"),
    ]
    for kw, cat in rules:
        if kw in name:
            return cat
    return "其他"


# ── 积分计费账本 ────────────────────────────────────────────
_INITIAL_POINTS = 1000
_INITIAL_CREDITS = 500

# 各功能定价（积分/次）
_FEATURE_PRICING = {
    "ai_report": 50,        # AI报告生成
    "word_cloud": 20,       # 词云
    "pdf_compress": 30,     # PDF压缩
    "ai_chat": 10,          # AI聊天（每次）
    "audio_transcribe": 40, # 音频转写
    "template": 15,         # 模板使用
}


def get_points_balance() -> dict:
    """获取积分余额 + 额度余额"""
    init_xiaohei_tables()
    with _conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN type='credit' THEN amount ELSE -amount END), 0) bal FROM points_ledger"
        ).fetchone()
    balance = row["bal"]
    if not conn_exec_any("points_ledger"):
        balance = _INITIAL_POINTS
    return {"balance": balance, "credits": _INITIAL_CREDITS}


def conn_exec_any(table: str) -> bool:
    with _conn() as conn:
        r = conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()
        return r["c"] > 0


def points_grant(amount: int, item: str, detail: str = "") -> dict:
    """发放积分"""
    init_xiaohei_tables()
    with _conn() as conn:
        conn.execute("INSERT INTO points_ledger (type, amount, item, detail) VALUES ('credit',?,?,?)",
                     (amount, item, detail))
    return {"ok": True, "amount": amount, "item": item}


def points_consume(item: str, detail: str = "", auto_pricing: bool = True) -> dict:
    """扣费。返回余额，余额不足返回 error。"""
    init_xiaohei_tables()
    price = _FEATURE_PRICING.get(item, 10)
    with _conn() as conn:
        bal_row = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN type='credit' THEN amount ELSE -amount END), 0) bal FROM points_ledger"
        ).fetchone()
        balance = bal_row["bal"]
        if balance < price:
            return {"ok": False, "error": "积分不足", "balance": balance, "need": price}
        conn.execute("INSERT INTO points_ledger (type, amount, item, detail) VALUES ('debit',?,?,?)",
                     (price, item, detail))
        new_bal = balance - price
    return {"ok": True, "consumed": price, "balance": new_bal}


def get_points_usage_records(page: int = 1, page_size: int = 20) -> dict:
    init_xiaohei_tables()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM points_ledger ORDER BY id DESC LIMIT ? OFFSET ?",
            (page_size, (page - 1) * page_size)).fetchall()
        total = conn.execute("SELECT COUNT(*) c FROM points_ledger").fetchone()["c"]
    return {"records": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


# ── 徽章系统（事件触发） ─────────────────────────────────────
_BADGE_DEFS = [
    {"id": "early_bird", "name": "早起鸟", "icon": "🌅", "desc": "连续7天 7点前开始专注", "condition": "早起达标天数", "target": 7},
    {"id": "focus_master", "name": "专注大师", "icon": "🎯", "desc": "累计专注 100 小时", "condition": "累计专注小时", "target": 100},
    {"id": "night_owl", "name": "夜猫子", "icon": "🦉", "desc": "深夜(23点后)工作 10 次", "condition": "深夜工作次数", "target": 10},
    {"id": "efficiency_king", "name": "效率狂人", "icon": "⚡", "desc": "单日完成 20 项待办", "condition": "单日完成待办", "target": 20},
    {"id": "streak_warrior", "name": "连击勇士", "icon": "🔥", "desc": "连续打卡 30 天", "condition": "连续打卡天数", "target": 30},
    {"id": "first_report", "name": "初出茅庐", "icon": "📄", "desc": "生成第一份日报", "condition": "日报生成数", "target": 1},
]


def init_badges():
    init_xiaohei_tables()
    with _conn() as conn:
        for b in _BADGE_DEFS:
            conn.execute(
                """INSERT OR IGNORE INTO badges (id, name, icon, desc, condition, target)
                   VALUES (?,?,?,?,?,?)""",
                (b["id"], b["name"], b["icon"], b["desc"], b["condition"], b["target"]))


def get_badges() -> list:
    init_badges()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM badges ORDER BY unlocked DESC, target").fetchall()
        return [dict(r) for r in rows]


def badge_track_progress(badge_id: str, add: int = 1, check: bool = True) -> dict:
    """推进徽章进度，达到目标自动解锁"""
    init_badges()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM badges WHERE id=?", (badge_id,)).fetchone()
        if not row:
            return {"ok": False}
        if row["unlocked"]:
            return {"ok": True, "unlocked": True}
        new_prog = min(row["progress"] + add, row["target"])
        unlocked = 1 if new_prog >= row["target"] else 0
        conn.execute(
            "UPDATE badges SET progress=?, unlocked=?, unlocked_at=CASE WHEN ?=1 THEN datetime('now','localtime') ELSE unlocked_at END WHERE id=?",
            (new_prog, unlocked, unlocked, badge_id))
    return {"ok": True, "unlocked": bool(unlocked), "progress": new_prog, "target": row["target"]}


# ── 排行榜（真实数据） ───────────────────────────────────────
def get_leaderboard_daily(day: Optional[str] = None) -> list:
    """从真实专注数据计算日榜（基于 activities 累计时长）"""
    init_xiaohei_tables()
    day = day or date.today().isoformat()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT COALESCE(app_name,'未知') app, SUM(interval_sec) total_sec
               FROM activities WHERE date(timestamp)=? GROUP BY app_name
               ORDER BY total_sec DESC LIMIT 10""", (day,)).fetchall()
    # 与积分/报告维度结合，形成“本人”条目
    result = []
    for i, r in enumerate(rows, 1):
        result.append({
            "rank": i,
            "name": r["app"],
            "hours": round(r["total_sec"] / 3600, 1),
            "me": False,
        })
    # 补一个本人条目（基于全部活动时长）
    with _conn() as conn:
        my_total = conn.execute(
            "SELECT COALESCE(SUM(interval_sec),0) s FROM activities WHERE date(timestamp)=?",
            (day,)).fetchone()["s"]
    if my_total:
        result.append({"rank": len(result) + 1, "name": "我", "hours": round(my_total / 3600, 1), "me": True})
    return result


# ── 模板市场（本地持久化） ───────────────────────────────────
def init_template_market_seed():
    """首次运行写入种子模板"""
    init_xiaohei_tables()
    with _conn() as conn:
        c = conn.execute("SELECT COUNT(*) c FROM template_market").fetchone()["c"]
        if c > 0:
            return
        seeds = [
            {"name": "标准日报模板", "category": "日报", "content": "今日完成 / 进行中 / 明日计划 / 问题与风险"},
            {"name": "深度周报模板", "category": "周报", "content": "本周成果 / 数据指标 / 团队协作 / 下周规划"},
            {"name": "项目复盘模板", "category": "复盘", "content": "目标回顾 / 结果对比 / 原因分析 / 经验沉淀 / 行动计划"},
            {"name": "月报模板", "category": "月报", "content": "月度概览 / 关键项目 / 数据看板 / 下月目标"},
            {"name": "面试总结模板", "category": "职场", "content": "岗位要求 / 面试问题 / 答得好的 / 待改进 / 后续行动"},
        ]
        for s in seeds:
            conn.execute(
                "INSERT INTO template_market (name, category, content, downloads) VALUES (?,?,?,?)",
                (s["name"], s["category"], s["content"], 0))


def list_templates(category: Optional[str] = None) -> list:
    init_template_market_seed()
    init_xiaohei_tables()
    if category and category != "全部":
        with _conn() as conn:
            rows = conn.execute(
                "SELECT * FROM template_market WHERE category=? ORDER BY downloads DESC", (category,)).fetchall()
    else:
        with _conn() as conn:
            rows = conn.execute("SELECT * FROM template_market ORDER BY downloads DESC").fetchall()
    return [dict(r) for r in rows]


def create_template(data: dict) -> dict:
    init_xiaohei_tables()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO template_market (name, category, content) VALUES (?,?,?)",
            (data.get("name", "未命名模板"), data.get("category", "通用"), data.get("content", "")))
        tid = cur.lastrowid
    return {"ok": True, "id": tid}


def use_template(tid: int) -> dict:
    """使用模板：下载数+1，返回模板内容"""
    init_xiaohei_tables()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM template_market WHERE id=?", (tid,)).fetchone()
        if not row:
            return {"ok": False, "error": "模板不存在"}
        conn.execute("UPDATE template_market SET downloads=downloads+1 WHERE id=?", (tid,))
    return {"ok": True, "template": dict(row), "downloads": row["downloads"] + 1}


def delete_template(tid: int) -> dict:
    init_xiaohei_tables()
    with _conn() as conn:
        conn.execute("DELETE FROM template_market WHERE id=?", (tid,))
    return {"ok": True}


# ── Token 使用统计 ──────────────────────────────────────────
def record_token_usage(feature: str, prompt_tokens: int, completion_tokens: int,
                       cost_points: int = 0) -> dict:
    init_xiaohei_tables()
    total = prompt_tokens + completion_tokens
    with _conn() as conn:
        conn.execute(
            "INSERT INTO token_usage (feature, prompt_tokens, completion_tokens, total_tokens, cost_points) VALUES (?,?,?,?,?)",
            (feature, prompt_tokens, completion_tokens, total, cost_points))
    return {"ok": True, "total": total}


def get_token_usage_summary() -> dict:
    init_xiaohei_tables()
    with _conn() as conn:
        total = conn.execute("SELECT COALESCE(SUM(total_tokens),0) s FROM token_usage").fetchone()["s"]
        today = conn.execute(
            "SELECT COALESCE(SUM(total_tokens),0) s FROM token_usage WHERE date(created_at)=date('now','localtime')"
        ).fetchone()["s"]
        cost = conn.execute("SELECT COALESCE(SUM(cost_points),0) s FROM token_usage").fetchone()["s"]
        rows = conn.execute(
            "SELECT feature, COUNT(*) cnt, SUM(total_tokens) tokens FROM token_usage GROUP BY feature ORDER BY tokens DESC LIMIT 10"
        ).fetchall()
    return {"total_tokens": total, "today_tokens": today, "total_cost_points": cost,
            "by_feature": [dict(r) for r in rows]}


def list_token_usage(limit: int = 50) -> list:
    init_xiaohei_tables()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM token_usage ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


# ── 帧去重日志 ──────────────────────────────────────────────
def log_frame_dedup(event: str, similarity: float = 0, detail: str = "") -> None:
    """记录帧去重事件（由 screenshot.py 调用）"""
    init_xiaohei_tables()
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO frame_dedup_log (ts, event, similarity, detail) VALUES (datetime('now','localtime'),?,?,?)",
                (event, similarity, detail[:500]))
    except Exception as e:
        logger.warning(f"帧去重日志写入失败: {e}")


def list_frame_dedup_log(limit: int = 100) -> list:
    init_xiaohei_tables()
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM frame_dedup_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        rows.reverse()
    return [dict(r) for r in rows]


def clear_frame_dedup_log() -> dict:
    init_xiaohei_tables()
    with _conn() as conn:
        conn.execute("DELETE FROM frame_dedup_log")
    return {"ok": True}


# ── 数据管理：备份 / 导出 / 导入 / 清理 ─────────────────────
def export_backup(target_dir: Optional[str] = None) -> dict:
    """导出全量数据备份（JSON）"""
    from config import DATA_DIR
    out_dir = Path(target_dir) if target_dir else DATA_DIR / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"challengedaily_backup_{ts}.json"
    fpath = out_dir / fname

    tables = ["work_records", "points_ledger", "badges", "template_market",
              "token_usage", "frame_dedup_log", "activities", "app_usage", "reports"]
    payload = {"exported_at": datetime.now().isoformat(), "version": 1, "tables": {}}
    with _conn() as conn:
        for t in tables:
            try:
                rows = conn.execute(f"SELECT * FROM {t}").fetchall()
                payload["tables"][t] = [dict(r) for r in rows]
            except Exception:
                payload["tables"][t] = []

    fpath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    size = fpath.stat().st_size
    with _conn() as conn:
        conn.execute("INSERT INTO backup_history (filename, size_bytes, kind) VALUES (?,?,?)",
                     (fname, size, "manual"))
    return {"ok": True, "file": str(fpath), "size_bytes": size}


def preview_import_backup(src_path: Optional[str] = None) -> dict:
    """预览备份内容（不实际导入）"""
    from config import DATA_DIR
    if src_path and Path(src_path).exists():
        fpath = Path(src_path)
    else:
        backups = list((DATA_DIR / "backups").glob("challengedaily_backup_*.json"))
        if not backups:
            return {"ok": False, "error": "没有可导入的备份文件"}
        fpath = sorted(backups, key=lambda p: p.stat().st_mtime)[-1]
    try:
        payload = json.loads(fpath.read_text(encoding="utf-8"))
        stats = {k: len(v) for k, v in payload.get("tables", {}).items()}
        return {"ok": True, "file": str(fpath), "stats": stats,
                "exported_at": payload.get("exported_at", "")}
    except Exception as e:
        return {"ok": False, "error": f"备份文件解析失败: {e}"}


def import_backup(src_path: Optional[str] = None) -> dict:
    """导入备份（合并：INSERT OR IGNORE）"""
    from config import DATA_DIR
    if src_path and Path(src_path).exists():
        fpath = Path(src_path)
    else:
        backups = list((DATA_DIR / "backups").glob("challengedaily_backup_*.json"))
        if not backups:
            return {"ok": False, "error": "没有可导入的备份文件"}
        fpath = sorted(backups, key=lambda p: p.stat().st_mtime)[-1]
    try:
        payload = json.loads(fpath.read_text(encoding="utf-8"))
    except Exception as e:
        return {"ok": False, "error": f"备份文件解析失败: {e}"}

    imported = 0
    with _conn() as conn:
        for table, rows in payload.get("tables", {}).items():
            if not rows:
                continue
            cols = [k for k in rows[0].keys() if k != "id"]
            try:
                for r in rows:
                    conn.execute(
                        f"INSERT OR IGNORE INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                        [r.get(c) for c in cols])
                    imported += 1
            except Exception as e:
                logger.warning(f"导入 {table} 失败: {e}")
    return {"ok": True, "imported": imported}


def clear_all_data() -> dict:
    """清空全部业务数据（保留 schema）"""
    tables = ["work_records", "points_ledger", "badges", "template_market",
              "token_usage", "frame_dedup_log", "activities", "app_usage", "reports"]
    with _conn() as conn:
        for t in tables:
            try:
                conn.execute(f"DELETE FROM {t}")
            except Exception:
                pass
    return {"ok": True, "cleared": tables}


def get_storage_stats() -> dict:
    """本地数据统计：各表行数 + 截图目录大小"""
    from config import DATA_DIR, SCREENSHOT_DIR
    stats = {}
    with _conn() as conn:
        for t in ["work_records", "points_ledger", "badges", "template_market",
                  "token_usage", "frame_dedup_log", "activities", "app_usage", "reports"]:
            try:
                stats[t] = conn.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            except Exception:
                stats[t] = 0
    # 截图目录大小
    shot_bytes = 0
    if SCREENSHOT_DIR.exists():
        for f in SCREENSHOT_DIR.iterdir():
            if f.is_file():
                shot_bytes += f.stat().st_size
    stats["screenshot_dir_size_mb"] = round(shot_bytes / 1024 / 1024, 1)
    return stats


def apply_template_to_daily_report(tid: int, day: Optional[str] = None) -> dict:
    """B18：模板「应用到日报」— 生成/更新当日日报并追加模板正文。"""
    day = day or date.today().isoformat()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM template_market WHERE id=?", (tid,)).fetchone()
        if not row:
            return {"ok": False, "error": "模板不存在"}
        conn.execute("UPDATE template_market SET downloads=downloads+1 WHERE id=?", (tid,))
    try:
        import report
        content = report.generate_daily_report(day)
        section = f"\n\n## 应用模板：{row['name']}\n\n{row['content']}"
        final = content + section
        report._save(final, day)
        return {"ok": True, "day": day, "template": row["name"], "chars": len(final)}
    except Exception as e:
        logger.error(f"模板应用到日报失败: {e}")
        return {"ok": False, "error": str(e)}


def start_daily_auto_extract(hour: int = 23) -> None:
    """B18：每日定时自动抽取工作记录（daemon 线程，按本地日期去重）。"""
    global _auto_extract_thread
    if _auto_extract_thread is not None and _auto_extract_thread.is_alive():
        return
    import threading
    import time
    state = {"day": None}

    def _loop():
        while True:
            try:
                now = datetime.now()
                today = now.date().isoformat()
                if now.hour >= hour and state["day"] != today:
                    result = extract_work_records_from_activities(today)
                    state["day"] = today
                    logger.info(f"每日自动抽取工作记录完成: {result}")
            except Exception as e:
                logger.warning(f"每日自动抽取失败: {e}")
            time.sleep(60)

    _auto_extract_thread = threading.Thread(target=_loop, daemon=True, name="xh-auto-extract")
    _auto_extract_thread.start()


# ════════════════════════════════════════════════════════════
# 初始化（模块导入时建表）
# ════════════════════════════════════════════════════════════
try:
    init_xiaohei_tables()
    init_badges()
    init_template_market_seed()
except Exception as e:
    logger.warning(f"小黑核心表初始化失败（可能数据库未就绪）: {e}")
