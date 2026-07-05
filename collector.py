"""
ChallengeDaily Windows 版 — 核心循环
截图 → AI 分析 → 分类 → 存储
"""
import logging
import threading
from datetime import datetime

from config import RETENTION_DAYS, is_app_excluded, load_settings
import config
from app_tracker import get_foreground_app, get_display_name, get_idle_seconds
from screenshot import take_screenshot, get_active_monitor_index
from ai_client import analyze_screenshot
from classifier import classify
from db import insert_activity, upsert_app_usage, cleanup_old_data, get_recent_activities
from screenshot import cleanup_screenshots, get_screenshots_size_mb

logger = logging.getLogger(__name__)

# 同应用持续运行时，每隔多少秒强制落盘一次 app_usage
_FLUSH_APP_USAGE_SEC = 300  # 5分钟

# 闲置检测：超过此时间无键盘/鼠标活动则暂停记录
_IDLE_THRESHOLD_SEC = 180  # 3分钟无操作判定为闲置


class Collector:
    """核心采集器：定时截图 + 分析 + 存储"""

    def __init__(self):
        self._last_app_key = None    # "app_name|window_title"
        self._last_app_data = None   # {"app_name": ..., "window_title": ...}
        self._segment_start = None   # 当前分段的起始时间
        self._last_flush_time = None # 上次强制落盘 app_usage 的时间
        self._running = False
        self._capture_lock = threading.Lock()  # 防止定时和手动并发

    def capture_once(self) -> dict | None:
        """执行一次截图→分析→存储的完整流程（线程安全）"""
        if not self._capture_lock.acquire(blocking=False):
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
                # 结算上一段 app_usage（成功后再重置状态，避免数据丢失）
                if self._last_app_data is not None and self._segment_start is not None:
                    try:
                        upsert_app_usage(
                            app_name=self._last_app_data["app_name"],
                            window_title=self._last_app_data["window_title"],
                            start_time=self._segment_start,
                            end_time=timestamp,
                        )
                    except Exception as e:
                        logger.error(f"闲置时保存 app_usage 失败: {e}")
                    self._last_app_key = None
                    self._last_app_data = None
                    self._segment_start = None
                return None
        except Exception:
            pass  # 闲置检测失败时不阻断采集

        # 1. 截图（获取前台窗口所在显示器）
        try:
            mon_idx = get_active_monitor_index()
            filename, filepath, is_duplicate = take_screenshot(monitor_index=mon_idx)
            logger.info(f"截图完成: {filename}{' (画面重复)' if is_duplicate else ''}")
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return None

        # 2. 获取前台应用
        try:
            fg = get_foreground_app()
            app_name = fg["app_name"]
            window_title = fg["window_title"]
            exe_path = fg.get("exe_path", "")
            display_name = get_display_name(app_name)
            # 异步提取图标（不阻塞采集）
            try:
                from icon_extractor import get_app_icon_path
                threading.Thread(
                    target=get_app_icon_path,
                    args=(app_name, exe_path),
                    daemon=True,
                ).start()
            except Exception:
                pass
        except Exception as e:
            logger.error(f"获取前台应用失败: {e}")
            app_name = "Unknown"
            window_title = ""
            exe_path = ""
            display_name = "Unknown"

        # 2.5 检查是否在排除列表中 — 跳过截图和分析，节省AI额度
        if is_app_excluded(app_name) or is_app_excluded(window_title):
            logger.info(f"应用在排除列表中，跳过: {display_name} / {window_title}")
            # 结算上一段 app_usage（成功后再重置状态，避免数据丢失）
            if self._last_app_data is not None and self._segment_start is not None:
                try:
                    upsert_app_usage(
                        app_name=self._last_app_data["app_name"],
                        window_title=self._last_app_data["window_title"],
                        start_time=self._segment_start,
                        end_time=timestamp,
                    )
                except Exception as e:
                    logger.error(f"排除应用时保存 app_usage 失败: {e}")
                self._last_app_key = None
                self._last_app_data = None
                self._segment_start = None
            return None

        # 3. 记录应用使用时长
        current_app_key = f"{app_name}|{window_title}"
        should_flush = False

        if current_app_key != self._last_app_key:
            # 应用切换了，先写入上一段
            if self._last_app_data is not None and self._segment_start is not None:
                upsert_app_usage(
                    app_name=self._last_app_data["app_name"],
                    window_title=self._last_app_data["window_title"],
                    start_time=self._segment_start,
                    end_time=timestamp,
                )
            # 开始新段
            self._last_app_key = current_app_key
            self._last_app_data = {"app_name": app_name, "window_title": window_title}
            self._segment_start = timestamp
            self._last_flush_time = now
        else:
            # 同应用持续运行，定期强制落盘
            if self._last_flush_time and (now - self._last_flush_time).total_seconds() >= _FLUSH_APP_USAGE_SEC:
                should_flush = True

        if should_flush and self._last_app_data is not None and self._segment_start is not None:
            upsert_app_usage(
                app_name=self._last_app_data["app_name"],
                window_title=self._last_app_data["window_title"],
                start_time=self._segment_start,
                end_time=timestamp,
            )
            self._segment_start = timestamp  # 开始新的分段
            self._last_flush_time = now

        # 4. AI 分析 — 画面重复或用户关闭 AI 时跳过，节省额度
        ai_enabled = bool(load_settings().get("ai_enabled", False))
        category = ""
        summary = ""
        ai_detail = ""

        if is_duplicate or not ai_enabled:
            if is_duplicate:
                logger.info("画面与上次相同，跳过AI分析，复用上次分类")
            if not ai_enabled:
                logger.info("AI 分析已关闭，使用规则分类")
            # 使用基于应用名的规则分类
            category = classify(app_name, "", window_title)
            summary = f"{display_name} - {window_title[:20]}" if window_title else display_name
        else:
            # 4.5 获取近期活动上下文，供 AI 综合分析
            recent_context = ""
            try:
                recent = get_recent_activities(5)
                if recent:
                    ctx_lines = []
                    for r in recent:
                        ts = r["timestamp"][11:] if len(r["timestamp"]) > 11 else r["timestamp"]  # 只取时分秒
                        app = r.get("app_name", "")
                        cat = r.get("category", "")
                        summ = r.get("ai_summary", "")
                        ctx_lines.append(f"- {ts} [{cat}] {app}: {summ}")
                    recent_context = "\n".join(ctx_lines)
            except Exception as e:
                logger.debug(f"获取近期活动上下文失败（不影响采集）: {e}")

            try:
                ai_result = analyze_screenshot(filepath, display_name, window_title, recent_context)
            except Exception as e:
                logger.error(f"AI 分析失败: {e}")
                ai_result = {"category": "", "summary": "", "detail": ""}

            # 5. 分类
            category = classify(app_name, ai_result.get("category", ""), window_title)
            summary = ai_result.get("summary", "")
            ai_detail = ai_result.get("detail", "")

        # 6. 存储
        insert_activity(
            timestamp=timestamp,
            screenshot=filename,
            app_name=app_name,
            window_title=window_title,
            category=category,
            summary=summary or f"{display_name} - {window_title[:20]}",
            interval_sec=config.SCREENSHOT_INTERVAL_SEC,
            ai_detail=ai_detail if not is_duplicate else "",
        )

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
            last_data = self._last_app_data
            seg_start = self._segment_start
            self._last_app_key = None
            self._last_app_data = None
            self._segment_start = None
        # 把最后一段 app_usage 写入（异常保护，不在锁内做 IO）
        if last_data is not None and seg_start is not None:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                upsert_app_usage(
                    app_name=last_data["app_name"],
                    window_title=last_data["window_title"],
                    start_time=seg_start,
                    end_time=now,
                )
            except Exception as e:
                logger.error(f"保存最后 app_usage 失败: {e}")
        logger.info("采集器已停止")
