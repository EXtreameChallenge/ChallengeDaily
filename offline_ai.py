"""
P10-1：AI 离线优先模块

功能：
1. AI 请求失败时加入重试队列，网络恢复后自动补发
2. 离线状态下使用规则引擎生成简化版日报
3. 网络连通性检测（基于最近一次 AI 调用结果）

设计：
- 重试队列持久化到 SQLite（ai_retry_queue 表），避免进程崩溃丢失
- 后台线程每 60 秒检查一次：网络恢复 + 队列非空 → 重发
- 单条记录最多重试 5 次，超过则放弃
- 离线日报降级：基于 activities 表的简单聚合 + 模板填充
"""
import threading
import time
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# 网络状态：基于最近 AI 调用结果动态判断
_online_state = {"online": True, "last_check": 0.0, "consecutive_failures": 0}
_state_lock = threading.Lock()

# 重试队列后台线程
_queue_thread: Optional[threading.Thread] = None
_queue_stop = threading.Event()


def mark_ai_success():
    """记录一次成功的 AI 调用"""
    with _state_lock:
        _online_state["online"] = True
        _online_state["consecutive_failures"] = 0
        _online_state["last_check"] = time.time()


def mark_ai_failure():
    """记录一次失败的 AI 调用（网络/超时/5xx）"""
    with _state_lock:
        _online_state["consecutive_failures"] += 1
        # 连续 3 次失败才判定为离线
        if _online_state["consecutive_failures"] >= 3:
            _online_state["online"] = False
        _online_state["last_check"] = time.time()


def is_online() -> bool:
    """当前是否在线（基于最近 AI 调用结果）"""
    with _state_lock:
        return _online_state["online"]


def enqueue_retry(payload: dict, kind: str = "screenshot"):
    """将失败的 AI 请求加入重试队列

    Args:
        payload: 原始请求参数（image_path/task/date 等）
        kind: 请求类型（screenshot/report/chat）
    """
    try:
        import db
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO ai_retry_queue (kind, payload, attempts, last_attempt, created_at, status) "
                "VALUES (?, ?, 0, NULL, ?, 'pending')",
                (kind, json.dumps(payload, ensure_ascii=False),
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            )
            conn.commit()
        logger.info(f"AI 请求已加入重试队列: kind={kind}")
    except Exception as e:
        logger.warning(f"入队失败（不影响主流程）: {e}")


def get_queue_size() -> int:
    """获取待重试队列长度"""
    try:
        import db
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM ai_retry_queue WHERE status='pending' AND attempts < 5"
            ).fetchone()
            return row["cnt"] if row else 0
    except Exception:
        return 0


def _drain_queue_once():
    """尝试排空一次重试队列（在线时）"""
    if not is_online():
        return
    try:
        import db
        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT id, kind, payload, attempts FROM ai_retry_queue "
                "WHERE status='pending' AND attempts < 5 "
                "ORDER BY created_at ASC LIMIT 10"
            ).fetchall()
        if not rows:
            return
        logger.info(f"重试队列处理 {len(rows)} 条")
        for r in rows:
            success = _retry_one(r["kind"], r["payload"])
            with db.get_conn() as conn:
                if success:
                    conn.execute(
                        "UPDATE ai_retry_queue SET status='done', last_attempt=? WHERE id=?",
                        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), r["id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE ai_retry_queue SET attempts=attempts+1, last_attempt=? WHERE id=?",
                        (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), r["id"]),
                    )
                conn.commit()
    except Exception as e:
        logger.warning(f"重试队列处理异常: {e}")


def _retry_one(kind: str, payload_json: str) -> bool:
    """重试单条 AI 请求"""
    try:
        payload = json.loads(payload_json)
        if kind == "screenshot":
            from ai_client import analyze_screenshot
            analyze_screenshot(
                payload.get("image_path", ""),
                payload.get("app_name", ""),
                payload.get("window_title", ""),
            )
            return True
        # 其他 kind 暂不重试（report/chat 通常是即时的，过期重试意义不大）
        return True
    except Exception as e:
        logger.debug(f"重试失败: {kind} - {e}")
        mark_ai_failure()
        return False


def _queue_loop():
    """后台重试线程主循环"""
    while not _queue_stop.is_set():
        try:
            _drain_queue_once()
        except Exception as e:
            logger.debug(f"重试循环异常: {e}")
        _queue_stop.wait(timeout=60)  # 每 60 秒检查一次


def start_retry_queue():
    """启动重试队列后台线程"""
    global _queue_thread
    if _queue_thread and _queue_thread.is_alive():
        return
    _queue_stop.clear()
    _queue_thread = threading.Thread(target=_queue_loop, name="ai-retry-queue", daemon=True)
    _queue_thread.start()
    logger.info("AI 重试队列已启动")


def stop_retry_queue():
    """停止重试队列"""
    _queue_stop.set()
    if _queue_thread:
        _queue_thread.join(timeout=2)


def generate_offline_daily_report(target_date: Optional[str] = None) -> str:
    """离线状态下的规则引擎降级日报

    基于 activities 表的简单聚合，不调用 AI。
    """
    try:
        import db
        if not target_date:
            target_date = date.today().isoformat()

        with db.get_conn() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) AS cnt, COALESCE(SUM(interval_sec), 0) AS sec, "
                "       GROUP_CONCAT(DISTINCT app_name) AS apps "
                "FROM activities WHERE date(timestamp) = ? "
                "GROUP BY category ORDER BY sec DESC",
                (target_date,),
            ).fetchall()

        if not rows:
            return f"# {target_date} 日报（离线模式）\n\n今日暂无采集数据。"

        total_sec = sum(r["sec"] for r in rows)
        total_min = total_sec // 60
        total_hour = total_min // 60

        lines = [
            f"# {target_date} 日报（离线模式 · 规则引擎生成）",
            "",
            f"今日总专注：**{total_hour} 小时 {total_min % 60} 分钟**",
            "",
            "## 分类分布",
            "",
        ]
        for r in rows:
            cat = r["category"] or "其他"
            sec = r["sec"] or 0
            min_v = sec // 60
            pct = (sec / total_sec * 100) if total_sec else 0
            lines.append(f"- **{cat}**：{min_v} 分钟（{pct:.1f}%），{r['cnt']} 次采集")
        lines.append("")
        lines.append("## 主要应用")
        lines.append("")
        all_apps = set()
        for r in rows:
            if r["apps"]:
                for a in r["apps"].split(","):
                    if a.strip():
                        all_apps.add(a.strip())
        lines.append("、".join(list(all_apps)[:10]))
        lines.append("")
        lines.append("---")
        lines.append("*当前处于离线模式，AI 增强分析暂不可用。网络恢复后将自动补发 AI 请求。*")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"离线日报生成失败: {e}", exc_info=True)
        return f"# 日报生成失败（离线模式）\n\n错误：{e}"
