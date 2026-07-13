"""
ChallengeDaily Windows 版 — 核心循环
截图 → AI 分析 → 分类 → 存储
企业级稳定性：线程限流、内存监控、异常隔离
"""
import logging
import threading
import gc
import time
from datetime import datetime

from config import RETENTION_DAYS, is_app_excluded, load_settings
import config
import json
from app_tracker import get_foreground_app, get_display_name, get_idle_seconds, get_visible_windows
from screenshot import take_screenshot, get_active_monitor_index
from ai_client import analyze_screenshot
from classifier import classify
from db import insert_activity, upsert_app_usage_multi, cleanup_old_data, get_recent_activities
from screenshot import cleanup_screenshots, get_screenshots_size_mb
from config import CATEGORIES

logger = logging.getLogger(__name__)

# 同应用持续运行时，每隔多少秒强制落盘一次 app_usage
_FLUSH_APP_USAGE_SEC = 300  # 5分钟

# 闲置检测：超过此时间无键盘/鼠标活动则暂停记录
_IDLE_THRESHOLD_SEC = 180  # 3分钟无操作判定为闲置

# 图标提取线程限流：避免每分钟都启动新线程提取同一应用的图标
_icon_extract_lock = threading.Lock()
_icon_extract_recent: dict[str, float] = {}  # app_name -> last_extract_time
_ICON_EXTRACT_COOLDOWN_SEC = 600  # 同一应用10分钟内不重复提取图标
_ICON_CACHE_MAX_SIZE = 100  # 限制图标提取缓存大小，避免内存无限增长


def _should_extract_icon(app_name: str) -> bool:
    """检查是否应该提取图标（限流：同一应用10分钟内只提取一次）"""
    now = time.time()
    with _icon_extract_lock:
        # 定期清理过期条目，防止字典无限增长
        if len(_icon_extract_recent) > _ICON_CACHE_MAX_SIZE:
            cutoff = now - _ICON_EXTRACT_COOLDOWN_SEC
            expired = [k for k, v in _icon_extract_recent.items() if v < cutoff]
            for k in expired:
                del _icon_extract_recent[k]
        last = _icon_extract_recent.get(app_name.lower(), 0)
        if (now - last) < _ICON_EXTRACT_COOLDOWN_SEC:
            return False
        _icon_extract_recent[app_name.lower()] = now
        return True


# 内存监控：每隔一段时间强制 GC，避免长期运行内存增长
# 优化：从 10 分钟调整为 30 分钟，gc.collect() 本身有 CPU 开销
_last_gc_time = 0
_GC_INTERVAL_SEC = 1800  # 30分钟执行一次 GC


def _maybe_gc():
    """定时执行垃圾回收，控制内存增长"""
    global _last_gc_time
    now = time.time()
    if (now - _last_gc_time) > _GC_INTERVAL_SEC:
        gc.collect()
        _last_gc_time = now
        logger.debug("执行垃圾回收，控制内存")


def _smooth_category(current_category: str, app_name: str, window_title: str,
                     is_duplicate: bool) -> str:
    """
    分类稳定性平滑：避免同一工作场景下 category 在"开发"和"其他"之间乱跳。
    规则：
      1. 当前是"其他"且最近非生活记录与当前为同一应用/相似窗口，沿用最近分类。
      2. 画面重复且应用未变，沿用最近一条记录的分类。
    """
    if current_category not in CATEGORIES:
        return current_category

    recent = get_recent_activities(3)
    if not recent:
        return current_category

    # 找到最近一条非生活/非空闲记录
    last_work = None
    for r in recent:
        cat = r.get("category", "")
        if cat and cat not in ("生活", ""):
            last_work = r
            break
    if not last_work:
        return current_category

    last_ts = last_work.get("timestamp", "")
    last_cat = last_work.get("category", "")
    last_app = last_work.get("app_name", "")
    last_title = last_work.get("window_title", "")

    # 计算时间差（秒）
    try:
        from datetime import datetime
        last_dt = datetime.strptime(last_ts, "%Y-%m-%d %H:%M:%S")
        now_dt = datetime.now()
        delta_sec = (now_dt - last_dt).total_seconds()
    except Exception:
        delta_sec = 9999

    # 同一应用或窗口标题高度相似
    same_app = bool(app_name and last_app and app_name.lower() == last_app.lower())
    similar_title = bool(window_title and last_title and
                         (window_title == last_title or
                          window_title.split(" - ")[-1] == last_title.split(" - ")[-1]))

    # 画面重复：直接沿用上一分类
    if is_duplicate and same_app:
        return last_cat

    # 当前被归为"其他"，但最近是工作分类且时间/应用/窗口连续，沿用工作分类
    if current_category == "其他" and last_cat != "其他" and delta_sec <= 300:
        if same_app or similar_title:
            logger.debug(f"分类平滑: {current_category} -> {last_cat} (同一工作场景)")
            return last_cat

    return current_category


class Collector:
    """核心采集器：定时截图 + 分析 + 存储"""

    def __init__(self):
        # 多窗口分摊状态：上一采集周期内可见的窗口列表（带 area_ratio），用于结算 duration
        self._last_visible_windows: list[dict] = []
        self._last_fg_signature: str | None = None   # "app_name|window_title" 用于切换检测
        self._segment_start: str | None = None       # 当前分段的起始时间
        self._last_flush_time = None                  # 上次强制落盘 app_usage 的时间
        self._running = False
        self._capture_lock = threading.Lock()  # 防止定时和手动并发
        # AI 分析缓存：重复画面时复用，但每隔一段时间强制重新分析以结合新上下文
        self._last_ai_analysis_time = None
        self._last_ai_detail = ""
        self._last_ai_summary = ""
        self._last_ai_category = ""
        self._AI_REANALYZE_INTERVAL_SEC = 180  # 3分钟
        # 近期活动上下文缓存：避免每次采集都查 DB
        self._recent_context_cache = None
        self._recent_context_cache_time = 0
        self._RECENT_CONTEXT_CACHE_TTL = 120  # 2分钟缓存
        # 上一次非闲置采集的时间戳（字符串 "YYYY-MM-DD HH:MM:SS"），
        # 闲置时段 flush 时用它作为 end_time，避免把闲置时长算入应用使用时长
        self._last_active_time: str | None = None

    def _flush_segment(self, end_time: str):
        """结算当前时间段：按 area_ratio 把 duration 分摊给所有可见窗口后写入 app_usage。

        - 用 self._last_visible_windows 作为分摊依据
        - 结算后清空状态，下一段由下次采集重新填充
        - 在锁内被调用，但 IO 异常不应影响主流程
        """
        if not self._last_visible_windows or self._segment_start is None:
            self._last_visible_windows = []
            self._last_fg_signature = None
            self._segment_start = None
            return
        try:
            upsert_app_usage_multi(self._last_visible_windows, self._segment_start, end_time)
        except Exception as e:
            logger.warning(f"upsert_app_usage_multi 失败: {e}")
        self._last_visible_windows = []
        self._last_fg_signature = None
        self._segment_start = None

    def capture_once(self) -> dict | None:
        """执行一次截图→分析→存储的完整流程（线程安全）"""
        if not self._capture_lock.acquire(blocking=False):
            # 采集被并发拒绝时记录到日志，便于排查是否存在手动+定时并发冲突
            logger.warning("capture_once 并发调用被拒绝")
            return None
        try:
            return self._capture_once_inner()
        finally:
            self._capture_lock.release()

    def _capture_once_inner(self) -> dict | None:
        """capture_once 的实际实现"""
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        # 0. 闲置检测 — 超过阈值则跳过本次采集
        try:
            idle_sec = get_idle_seconds()
            if idle_sec >= _IDLE_THRESHOLD_SEC:
                logger.debug(f"用户已闲置 {idle_sec}s，跳过本次采集")
                # 闲置时 flush 的 end_time 应为上一次活动时间，而非当前时间，
                # 避免把闲置时长算入应用使用时长
                self._flush_segment(self._last_active_time or timestamp)
                return None
        except Exception:
            pass  # 闲置检测失败时不阻断采集

        # 非闲置时记录本次活动时间，供闲置时段 flush 用作 end_time
        self._last_active_time = timestamp

        # 1. 截图（获取前台窗口所在显示器）
        try:
            mon_idx = get_active_monitor_index()
            filename, filepath, is_duplicate = take_screenshot(monitor_index=mon_idx)
            logger.info(f"截图完成: {filename}{' (画面重复)' if is_duplicate else ''}")
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

        # 2. 获取前台应用 + 所有可见窗口
        visible_windows = []
        try:
            fg = get_foreground_app()
            app_name = fg["app_name"]
            window_title = fg["window_title"]
            exe_path = fg.get("exe_path", "")
            display_name = get_display_name(app_name)
            # 异步提取图标（不阻塞采集），限流：同一应用10分钟内只提取一次
            if _should_extract_icon(app_name):
                try:
                    from icon_extractor import get_app_icon_path
                    threading.Thread(
                        target=get_app_icon_path,
                        args=(app_name, exe_path),
                        daemon=True,
                    ).start()
                except Exception:
                    pass
            # 枚举所有可见窗口（供 AI 多窗口分析）
            try:
                visible_windows = get_visible_windows()
            except Exception as e:
                logger.warning(f"获取可见窗口列表失败: {e}")
        except Exception as e:
            logger.error(f"获取前台应用失败: {e}")
            app_name = "Unknown"
            window_title = ""
            exe_path = ""
            display_name = "Unknown"

        # 2.5 检查是否在排除列表中 — 跳过截图和分析，节省AI额度
        if is_app_excluded(app_name) or is_app_excluded(window_title):
            logger.info(f"应用在排除列表中，跳过: {display_name} / {window_title}")
            # 结算上一段（按多窗口面积分摊）
            self._flush_segment(timestamp)
            return None

        # 3. 记录应用使用时长 — 多窗口分摊写入
        #    切换检测基于"前台签名"变化（避免过度细分），但写入时把 duration 分摊给所有可见窗口
        current_fg_signature = f"{app_name}|{window_title}"
        # 构建本次采集的可见窗口列表（≥15%面积），用于下一时段分摊
        new_visible_windows: list[dict] = []
        if visible_windows:
            for w in visible_windows:
                area_ratio = w.get("area_ratio", 0)
                if area_ratio >= 0.15:
                    new_visible_windows.append({
                        "app_name": w.get("app_name", app_name),
                        "window_title": w.get("window_title", "") or "",
                        "area_ratio": area_ratio,
                    })
        # 过滤后为空则回退到前台窗口（占满 100%）
        if not new_visible_windows:
            new_visible_windows = [{
                "app_name": app_name,
                "window_title": window_title,
                "area_ratio": 1.0,
            }]

        should_flush = False
        if current_fg_signature != self._last_fg_signature:
            # 前台应用切换了，先结算上一段（用旧窗口列表分摊）
            self._flush_segment(timestamp)
            # 开始新段
            self._last_visible_windows = new_visible_windows
            self._last_fg_signature = current_fg_signature
            self._segment_start = timestamp
            self._last_flush_time = now
        else:
            # 前台未切换，但持续运行时定期强制落盘（用最新窗口列表分摊）
            if self._last_flush_time and (now - self._last_flush_time).total_seconds() >= _FLUSH_APP_USAGE_SEC:
                should_flush = True
            # 持续更新窗口列表，反映分屏布局变化（不重置段起点）
            self._last_visible_windows = new_visible_windows

        if should_flush and self._last_visible_windows and self._segment_start is not None:
            self._flush_segment(timestamp)
            # 开始新段（仍用最新窗口列表）
            self._last_visible_windows = new_visible_windows
            self._last_fg_signature = current_fg_signature
            self._segment_start = timestamp
            self._last_flush_time = now

        # 4. AI 分析 — 分析所有可见的并行大窗口（而不仅是前台窗口）
        # 过滤掉面积过小（<15%）的悬浮/背景窗口，但保留所有并行的主要工作窗口
        analysis_windows = [w for w in visible_windows if w.get("area_ratio", 0) >= 0.15]
        # 如果过滤后为空，回退到前台窗口或 Z-Order 最高的窗口
        if not analysis_windows:
            analysis_windows = [w for w in visible_windows if w.get("is_foreground")]
        if not analysis_windows and visible_windows:
            analysis_windows = [visible_windows[0]]

        ai_enabled = bool(load_settings().get("ai_enabled", False))
        category = ""
        summary = ""
        ai_detail = ""
        windows_data = analysis_windows

        # 是否需要完整 AI 分析：画面变化、AI 首次分析、或超过复用间隔
        now_ts = time.time()
        should_analyze = (
            ai_enabled
            and (not is_duplicate
                 or self._last_ai_analysis_time is None
                 or (now_ts - self._last_ai_analysis_time) >= self._AI_REANALYZE_INTERVAL_SEC)
        )

        if not ai_enabled:
            logger.info("AI 分析已关闭，使用规则分类")
            category = classify(app_name, "", window_title)
            summary = f"{display_name} - {window_title[:20]}" if window_title else display_name
        elif should_analyze:
            if is_duplicate:
                logger.info("画面相同但超过复用间隔，重新结合上下文分析")
            # 4.5 获取近期活动上下文，供 AI 综合分析（带缓存）
            recent_context = ""
            try:
                now_ctx = time.time()
                if (self._recent_context_cache is not None and
                    (now_ctx - self._recent_context_cache_time) < self._RECENT_CONTEXT_CACHE_TTL):
                    recent_context = self._recent_context_cache
                else:
                    recent = get_recent_activities(8)
                    if recent:
                        ctx_lines = []
                        for r in recent:
                            ts = r["timestamp"][11:16] if len(r["timestamp"]) > 11 else r["timestamp"]  # 只取时分
                            app = r.get("app_name", "")
                            cat = r.get("category", "")
                            summ = r.get("ai_summary", "")
                            detail = r.get("ai_detail", "")
                            # 解析 windows_json，显示窗口变化
                            try:
                                wins = json.loads(r.get("windows_json", "[]") or "[]")
                                win_names = ", ".join([
                                    f"{w.get('app_name', '').replace('.exe', '')}{'[前台]' if w.get('is_foreground') else ''}"
                                    for w in wins[:3]
                                ]) if wins else app
                            except Exception:
                                win_names = app
                            ctx_lines.append(f"- {ts} [{cat}] {win_names}: {summ}")
                            if detail:
                                ctx_lines.append(f"  详情：{detail[:80]}{'...' if len(detail) > 80 else ''}")
                        recent_context = "\n".join(ctx_lines)
                    # 缓存上下文
                    self._recent_context_cache = recent_context
                    self._recent_context_cache_time = now_ctx
            except Exception as e:
                logger.debug(f"获取近期活动上下文失败（不影响采集）: {e}")

            try:
                ai_result = analyze_screenshot(filepath, display_name, window_title, recent_context, analysis_windows)
            except Exception as e:
                logger.error(f"AI 分析失败: {e}")
                ai_result = {"category": "", "summary": "", "detail": "", "windows": []}

            # 5. 分类
            category = classify(app_name, ai_result.get("category", ""), window_title)
            summary = ai_result.get("summary", "")
            ai_detail = ai_result.get("detail", "")
            # 合并 AI 返回的 description 与原始窗口数据：保留原始 app_name/window_title，防止 AI 改名导致图标错误
            ai_windows = ai_result.get("windows", []) if isinstance(ai_result.get("windows"), list) else []
            windows_data = []
            for idx, orig in enumerate(analysis_windows):
                ai_desc = ""
                if idx < len(ai_windows):
                    ai_desc = ai_windows[idx].get("description", "")
                windows_data.append({
                    "app_name": orig.get("app_name", ""),
                    "window_title": orig.get("window_title", ""),
                    "is_foreground": orig.get("is_foreground", False),
                    "description": ai_desc,
                    "area_ratio": orig.get("area_ratio", 0),
                })

            # 缓存本次分析结果
            self._last_ai_analysis_time = now_ts
            self._last_ai_detail = ai_detail
            self._last_ai_summary = summary
            self._last_ai_category = category
        else:
            logger.info("画面与上次相同，复用AI分析缓存")
            category = self._last_ai_category or classify(app_name, "", window_title)
            summary = self._last_ai_summary or f"{display_name} - {window_title[:20]}"
            ai_detail = self._last_ai_detail

        # 5.5 分类稳定性平滑：同一工作场景下避免"开发"与"其他"乱跳
        try:
            category = _smooth_category(
                current_category=category,
                app_name=app_name,
                window_title=window_title,
                is_duplicate=is_duplicate,
            )
        except Exception as e:
            logger.debug(f"分类平滑失败（不影响采集）: {e}")

        # 6. 存储
        try:
            insert_activity(
                timestamp=timestamp,
                screenshot=filename,
                app_name=app_name,
                window_title=window_title,
                category=category,
                summary=summary or f"{display_name} - {window_title[:20]}",
                interval_sec=config.SCREENSHOT_INTERVAL_SEC,
                ai_detail=ai_detail,
                windows_json=json.dumps(windows_data, ensure_ascii=False) if windows_data else "[]",
            )
        except Exception as e:
            logger.error(f"insert_activity 失败: {e}", exc_info=True)

        logger.info(f"[{category}] {summary} ({display_name})")

        # 7. AI分析完成后自动删除截图文件（隐私保护）
        try:
            from pathlib import Path
            fp = Path(filepath)
            if fp.exists():
                fp.unlink()
                logger.debug(f"已删除截图: {filename}")
        except Exception as e:
            logger.warning(f"删除截图失败: {e}")

        # 8. 定时垃圾回收，控制长期运行的内存增长
        try:
            _maybe_gc()
        except Exception:
            pass

        return {
            "timestamp": timestamp,
            "category": category,
            "summary": summary,
            "app_name": display_name,
            "window_title": window_title,
        }

    def on_start(self):
        """启动前初始化（清理过期数据等）"""
        self._running = True
        logger.info(f"ChallengeDaily采集器启动，截图间隔 {config.SCREENSHOT_INTERVAL_SEC}s")

        # 启动时清理过期数据
        try:
            cleanup_old_data(RETENTION_DAYS)
            cleanup_screenshots(RETENTION_DAYS)
            ss_size = get_screenshots_size_mb()
            logger.info(f"已清理 {RETENTION_DAYS} 天前的数据，截图占用 {ss_size}MB")
        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")

    def run(self):
        """持续运行主循环（阻塞）。注意：main.py 未使用此方法，而是直接调用 capture_once + Event.wait。"""
        self.on_start()
        stop = threading.Event()

        while self._running and not stop.is_set():
            try:
                self.capture_once()
            except Exception as e:
                logger.error(f"采集循环异常: {e}")

            # 可被 stop.set() 打断
            stop.wait(timeout=config.SCREENSHOT_INTERVAL_SEC)

    def stop(self):
        self._running = False
        # 持锁读取和清空追踪状态，避免与 capture_once 并发导致数据损坏
        with self._capture_lock:
            last_windows = self._last_visible_windows
            seg_start = self._segment_start
            self._last_visible_windows = []
            self._last_fg_signature = None
            self._segment_start = None
        # 把最后一段 app_usage 写入（多窗口分摊，异常保护，不在锁内做 IO）
        if last_windows and seg_start is not None:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                upsert_app_usage_multi(last_windows, seg_start, now)
            except Exception as e:
                logger.error(f"保存最后 app_usage 失败: {e}")
        logger.info("采集器已停止")
