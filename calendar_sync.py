"""
P18-1: 外部日历集成（ICS 订阅 + 会议检测）
- 支持订阅 Google Calendar / Outlook 公开 ICS URL
- 本地缓存 + 定时刷新（默认 30 分钟）
- 提供今日会议查询、当前是否在会议中、与采集数据联动（会议时段不判定为摸鱼）
- 纯标准库实现 icalendar 解析（避免外部依赖）
"""
import logging
import threading
import time
import urllib.request
import urllib.parse
from datetime import datetime, date, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

from config import DATA_DIR

logger = logging.getLogger(__name__)

# ── 配置 ──
_SUBSCRIPTIONS_PATH = DATA_DIR / "calendar_subscriptions.json"
_CACHE_DIR = DATA_DIR / "calendar_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_REFRESH_INTERVAL_SEC = 30 * 60   # 30 分钟刷新一次
_REQUEST_TIMEOUT_SEC = 15
_MAX_EVENTS_PER_CALENDAR = 200    # 单日历最多缓存事件数

_lock = threading.Lock()
_subscriptions: list[dict] = []   # [{id, name, url, enabled, color, last_sync, last_error}]
_cache: dict[str, list[dict]] = {}  # subscription_id -> [event dict]
_last_full_refresh = 0.0


# ── ICS 解析（纯标准库） ──

def _parse_ics_datetime(value: str, tz_default: Optional[timezone] = None) -> Optional[datetime]:
    """解析 ICS 时间字符串：支持 UTC（Z）、带时区、本地时间（floating）"""
    if not value:
        return None
    value = value.strip()
    try:
        # UTC 时间：20260716T120000Z
        if value.endswith("Z"):
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
            return dt.replace(tzinfo=timezone.utc)
        # 带时区：20260716T120000TZID（这里简化处理，只截取前 15 位）
        if "T" in value and len(value) >= 15:
            dt = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
            return dt.replace(tzinfo=tz_default) if tz_default else dt
        # 全天日期：20260716
        if len(value) == 8:
            dt = datetime.strptime(value, "%Y%m%d")
            return dt
    except Exception:
        return None
    return None


def _unfold_ics(text: str) -> list[str]:
    """ICS 行折叠展开：以空格开头的行是上一行的续行"""
    lines = []
    for line in text.splitlines():
        if line.startswith(" ") or line.startswith("\t"):
            if lines:
                lines[-1] += line[1:]
        else:
            lines.append(line)
    return lines


def _parse_ics(text: str, calendar_id: str) -> list[dict]:
    """解析 ICS 文本，提取未来 30 天内的事件"""
    events: list[dict] = []
    current: Optional[dict] = None
    now = datetime.now().astimezone()

    for line in _unfold_ics(text):
        line = line.strip()
        if not line:
            continue

        # 处理属性参数：DTSTART;TZID=Asia/Shanghai:20260716T120000
        if ":" in line:
            prop_part, value = line.split(":", 1)
        else:
            prop_part, value = line, ""

        prop_tokens = prop_part.split(";")
        prop_name = prop_tokens[0].upper()
        params = {}
        for tok in prop_tokens[1:]:
            if "=" in tok:
                k, v = tok.split("=", 1)
                params[k.upper()] = v

        if prop_name == "BEGIN" and value == "VEVENT":
            current = {"calendar_id": calendar_id}
        elif prop_name == "END" and value == "VEVENT" and current is not None:
            # 校验事件完整性
            if current.get("start") and current.get("summary"):
                events.append(current)
            current = None
        elif current is not None:
            if prop_name == "SUMMARY":
                current["summary"] = value
            elif prop_name == "LOCATION":
                current["location"] = value
            elif prop_name == "DESCRIPTION":
                current["description"] = value
            elif prop_name == "DTSTART":
                dt = _parse_ics_datetime(value)
                if dt:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc).astimezone()
                    else:
                        dt = dt.astimezone()
                    current["start"] = dt.isoformat()
                    current["start_timestamp"] = dt.timestamp()
            elif prop_name == "DTEND":
                dt = _parse_ics_datetime(value)
                if dt:
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc).astimezone()
                    else:
                        dt = dt.astimezone()
                    current["end"] = dt.isoformat()
                    current["end_timestamp"] = dt.timestamp()
            elif prop_name == "RRULE":
                current["rrule"] = value

    # 过滤：仅保留未来 30 天内的事件
    cutoff = now - timedelta(days=1)
    future_limit = now + timedelta(days=30)
    result = []
    for ev in events:
        try:
            start_ts = ev.get("start_timestamp", 0)
            ev_dt = datetime.fromtimestamp(start_ts)
            if cutoff <= ev_dt <= future_limit:
                result.append(ev)
        except Exception:
            continue
    result.sort(key=lambda e: e.get("start_timestamp", 0))
    return result[:_MAX_EVENTS_PER_CALENDAR]


# ── 订阅管理 ──

def _load_subscriptions() -> None:
    """从磁盘加载订阅列表"""
    global _subscriptions
    import json
    try:
        if _SUBSCRIPTIONS_PATH.exists():
            with open(_SUBSCRIPTIONS_PATH, "r", encoding="utf-8") as f:
                _subscriptions = json.load(f)
    except Exception as e:
        logger.warning(f"加载日历订阅失败: {e}")
        _subscriptions = []


def _save_subscriptions() -> None:
    """保存订阅列表到磁盘"""
    import json
    try:
        _SUBSCRIPTIONS_PATH.write_text(
            json.dumps(_subscriptions, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"保存日历订阅失败: {e}")


def list_subscriptions() -> list[dict]:
    """列出所有日历订阅"""
    with _lock:
        return list(_subscriptions)


def add_subscription(name: str, url: str, color: str = "#4A90E2", enabled: bool = True) -> dict:
    """添加一个新的 ICS 订阅"""
    import uuid as uuid_mod
    sub = {
        "id": uuid_mod.uuid4().hex[:12],
        "name": name[:60],
        "url": url[:500],
        "color": color,
        "enabled": enabled,
        "last_sync": None,
        "last_error": None,
    }
    with _lock:
        _subscriptions.append(sub)
        _save_subscriptions()
    # 立即尝试刷新一次
    refresh_subscription(sub["id"])
    return sub


def update_subscription(sub_id: str, **kwargs) -> Optional[dict]:
    """更新订阅属性"""
    with _lock:
        for sub in _subscriptions:
            if sub["id"] == sub_id:
                for k in ("name", "url", "color", "enabled"):
                    if k in kwargs:
                        sub[k] = kwargs[k]
                _save_subscriptions()
                return dict(sub)
    return None


def remove_subscription(sub_id: str) -> bool:
    """删除订阅"""
    with _lock:
        before = len(_subscriptions)
        _subscriptions[:] = [s for s in _subscriptions if s["id"] != sub_id]
        if len(_subscriptions) < before:
            _save_subscriptions()
            _cache.pop(sub_id, None)
            return True
    return False


def refresh_subscription(sub_id: str) -> bool:
    """刷新单个订阅：下载 ICS 并解析"""
    sub = None
    with _lock:
        for s in _subscriptions:
            if s["id"] == sub_id:
                sub = dict(s)
                break
    if not sub or not sub.get("enabled"):
        return False

    url = sub.get("url", "")
    if not url:
        return False

    try:
        # SSRF 防护：仅允许 http/https 协议，禁止 file/ftp 等
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"不支持的协议: {parsed.scheme}")
        # 禁止 localhost / 内网地址（避免 SSRF）
        host = parsed.hostname or ""
        if host.lower() in ("localhost", "127.0.0.1", "::1") or host.startswith("192.168.") or host.startswith("10."):
            raise ValueError(f"禁止访问内网地址: {host}")

        req = urllib.request.Request(url, headers={"User-Agent": "ChallengeDaily/3.2"})
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_SEC) as resp:
            # 限制最大下载 5MB，避免恶意超大文件
            content = resp.read(5 * 1024 * 1024)
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                text = content.decode("latin-1", errors="replace")

        events = _parse_ics(text, sub_id)

        with _lock:
            _cache[sub_id] = events
            for s in _subscriptions:
                if s["id"] == sub_id:
                    s["last_sync"] = datetime.now().isoformat()
                    s["last_error"] = None
                    break
            _save_subscriptions()

        # 写入缓存文件（便于跨进程查看）
        cache_path = _CACHE_DIR / f"{sub_id}.json"
        try:
            import json
            cache_path.write_text(
                json.dumps(events, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass

        logger.info(f"日历订阅刷新成功: {sub.get('name')} ({len(events)} 个事件)")
        return True

    except Exception as e:
        err_msg = str(e)[:200]
        logger.warning(f"日历订阅刷新失败 [{sub.get('name')}]: {err_msg}")
        with _lock:
            for s in _subscriptions:
                if s["id"] == sub_id:
                    s["last_error"] = err_msg
                    s["last_sync"] = datetime.now().isoformat()
                    break
            _save_subscriptions()
        return False


def refresh_all(force: bool = False) -> dict:
    """刷新所有订阅（带节流）"""
    global _last_full_refresh
    now = time.time()
    if not force and (now - _last_full_refresh) < _REFRESH_INTERVAL_SEC:
        return {"skipped": True, "reason": "throttled"}

    with _lock:
        subs_snapshot = [dict(s) for s in _subscriptions if s.get("enabled", True)]

    success, failed = 0, 0
    for sub in subs_snapshot:
        if refresh_subscription(sub["id"]):
            success += 1
        else:
            failed += 1
    _last_full_refresh = now
    return {"refreshed": success, "failed": failed, "total": len(subs_snapshot)}


# ── 查询接口 ──

def get_today_events() -> list[dict]:
    """获取今日所有会议事件"""
    today = date.today()
    today_str = today.isoformat()
    result = []
    with _lock:
        for sub_id, events in _cache.items():
            sub_meta = next((s for s in _subscriptions if s["id"] == sub_id), {})
            for ev in events:
                try:
                    start_str = ev.get("start", "")
                    if today_str in start_str:
                        result.append({
                            **ev,
                            "calendar_name": sub_meta.get("name", ""),
                            "calendar_color": sub_meta.get("color", "#4A90E2"),
                        })
                except Exception:
                    continue
    result.sort(key=lambda e: e.get("start_timestamp", 0))
    return result


def get_upcoming_events(hours: int = 24) -> list[dict]:
    """获取未来 N 小时内的事件"""
    now = datetime.now().timestamp()
    future = now + hours * 3600
    result = []
    with _lock:
        for sub_id, events in _cache.items():
            sub_meta = next((s for s in _subscriptions if s["id"] == sub_id), {})
            for ev in events:
                start_ts = ev.get("start_timestamp", 0)
                if now <= start_ts <= future:
                    result.append({
                        **ev,
                        "calendar_name": sub_meta.get("name", ""),
                        "calendar_color": sub_meta.get("color", "#4A90E2"),
                    })
    result.sort(key=lambda e: e.get("start_timestamp", 0))
    return result


def is_in_meeting_now() -> bool:
    """检测当前是否处于会议时段"""
    now = datetime.now().timestamp()
    with _lock:
        for events in _cache.values():
            for ev in events:
                start_ts = ev.get("start_timestamp", 0)
                end_ts = ev.get("end_timestamp", start_ts)
                if start_ts <= now <= end_ts:
                    return True
    return False


def get_current_meeting() -> Optional[dict]:
    """获取当前正在进行的会议（若有）"""
    now = datetime.now().timestamp()
    with _lock:
        for sub_id, events in _cache.items():
            sub_meta = next((s for s in _subscriptions if s["id"] == sub_id), {})
            for ev in events:
                start_ts = ev.get("start_timestamp", 0)
                end_ts = ev.get("end_timestamp", start_ts)
                if start_ts <= now <= end_ts:
                    return {
                        **ev,
                        "calendar_name": sub_meta.get("name", ""),
                        "calendar_color": sub_meta.get("color", "#4A90E2"),
                    }
    return None


# ── 后台刷新线程 ──

_bg_thread: Optional[threading.Thread] = None
_bg_stop = threading.Event()


def _bg_refresh_loop():
    """后台定时刷新所有订阅"""
    while not _bg_stop.is_set():
        try:
            refresh_all(force=False)
        except Exception as e:
            logger.warning(f"日历后台刷新异常: {e}")
        # 每 10 分钟醒来检查一次（实际刷新间隔由 _REFRESH_INTERVAL_SEC 控制）
        _bg_stop.wait(600)


def start_background_refresh() -> None:
    """启动后台刷新线程（进程级单例）"""
    global _bg_thread
    if _bg_thread is not None and _bg_thread.is_alive():
        return
    _bg_stop.clear()
    _bg_thread = threading.Thread(target=_bg_refresh_loop, daemon=True, name="calendar-refresh")
    _bg_thread.start()
    logger.info("日历后台刷新线程已启动")


def stop_background_refresh() -> None:
    """停止后台刷新线程"""
    _bg_stop.set()
    if _bg_thread:
        _bg_thread.join(timeout=2)


# ── 初始化 ──

_load_subscriptions()
