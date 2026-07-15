"""
P9-1：剪贴板监听器

后台线程监听 Windows 剪贴板变化，缓存最近 URL / 文本关键词，
供 AI 截图分析时作为辅助上下文，提升"学习"/"文档"分类精度。

设计要点：
- 使用 win32clipboard + 用户消息钩子（简化版：轮询模式，每 2 秒检查一次）
- 仅缓存 URL 和前 200 字符文本，自动去重
- 缓存 TTL 5 分钟，过期自动清理
- 线程安全：所有读写都加锁
- 失败安全：任何异常都不影响主采集流程
"""
import threading
import time
import logging
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)

# 缓存最近 10 条剪贴板记录，每条 TTL 5 分钟
_CLIP_TTL_SEC = 300
_CLIP_MAX_SIZE = 10
_POLL_INTERVAL_SEC = 2

_URL_PREFIXES = ("http://", "https://", "ftp://", "www.")


class ClipboardRecord:
    __slots__ = ("kind", "content", "ts")

    def __init__(self, kind: str, content: str, ts: float):
        self.kind = kind  # "url" | "text"
        self.content = content
        self.ts = ts


class ClipboardMonitor:
    """剪贴板监听单例（线程安全）"""

    def __init__(self):
        self._lock = threading.Lock()
        self._records: deque[ClipboardRecord] = deque(maxlen=_CLIP_MAX_SIZE)
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_content_hash: int = 0
        self._enabled = True  # 可通过配置关闭

    def start(self) -> None:
        """启动后台监听线程（幂等）"""
        if self._running:
            return
        try:
            import win32clipboard  # noqa: F401
        except ImportError:
            logger.info("pywin32 未安装，剪贴板监听跳过")
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name="clipboard-monitor", daemon=True)
        self._thread.start()
        logger.info("剪贴板监听已启动")

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None

    def set_enabled(self, enabled: bool) -> None:
        """运行时开关"""
        self._enabled = enabled

    def _run(self) -> None:
        """后台轮询线程"""
        while self._running:
            try:
                if self._enabled:
                    self._poll_once()
            except Exception as e:
                # 任何异常都不能让线程退出
                logger.debug(f"剪贴板轮询异常: {e}")
            time.sleep(_POLL_INTERVAL_SEC)

    def _poll_once(self) -> None:
        """读取一次剪贴板内容"""
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            try:
                # 优先读文本
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    text = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                    if text:
                        self._handle_text(text)
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass  # 剪贴板被占用等场景静默跳过

    def _handle_text(self, text: str) -> None:
        """处理剪贴板文本：判定 URL 或普通文本，去重后入队"""
        text = text.strip()
        if not text or len(text) > 2000:  # 过长内容忽略（可能是大段复制）
            return
        h = hash(text)
        if h == self._last_content_hash:
            return  # 与上次相同，跳过
        self._last_content_hash = h

        kind = "url" if text.lower().startswith(_URL_PREFIXES) else "text"
        # URL 只取前 200 字符，文本只取前 200 字符
        content = text[:200]
        now = time.time()
        with self._lock:
            # 去重：如果内容已存在则更新时间戳
            for r in self._records:
                if r.content == content:
                    r.ts = now
                    return
            self._records.append(ClipboardRecord(kind, content, now))

    def get_recent_context(self, max_items: int = 3) -> str:
        """获取近期剪贴板上下文，供 AI prompt 注入使用。

        返回形如：
          [剪贴板辅助上下文]
          - URL: https://example.com/docs (2 分钟前)
          - 文本: report.py 第 42 行 (5 分钟前)
        """
        now = time.time()
        lines: list[str] = []
        with self._lock:
            # 清理过期记录
            while self._records and (now - self._records[0].ts) > _CLIP_TTL_SEC:
                self._records.popleft()
            # 取最近 N 条
            recent = list(self._records)[-max_items:] if self._records else []
        if not recent:
            return ""
        for r in reversed(recent):  # 最新的在前
            age_min = int((now - r.ts) / 60)
            label = "URL" if r.kind == "url" else "文本"
            age_str = f"{age_min} 分钟前" if age_min > 0 else "刚刚"
            lines.append(f"- {label}: {r.content} ({age_str})")
        return "[剪贴板辅助上下文，可用于辅助判断用户当前活动]\n" + "\n".join(lines)

    def clear(self) -> None:
        """清空缓存（隐私保护：用户可手动清空）"""
        with self._lock:
            self._records.clear()


# 模块级单例
_monitor: ClipboardMonitor | None = None


def get_clipboard_monitor() -> ClipboardMonitor:
    """获取剪贴板监听单例"""
    global _monitor
    if _monitor is None:
        _monitor = ClipboardMonitor()
    return _monitor


def get_clipboard_context(max_items: int = 3) -> str:
    """便捷接口：获取近期剪贴板上下文文本（供 prompt 注入）"""
    if _monitor is None:
        return ""
    return _monitor.get_recent_context(max_items=max_items)
