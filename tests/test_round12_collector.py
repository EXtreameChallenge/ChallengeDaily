"""B32: collector 模块单测（不启动真实采集循环）。"""
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import collector as co
import config


@pytest.fixture
def clean_icon_cache(monkeypatch):
    monkeypatch.setattr(co, "_icon_extract_recent", {})


def test_should_extract_icon_cooldown_and_cleanup(monkeypatch, clean_icon_cache):
    calls = []
    monkeypatch.setattr(co, "_ICON_EXTRACT_COOLDOWN_SEC", 60)
    monkeypatch.setattr(co, "_ICON_CACHE_MAX_SIZE", 3)
    monkeypatch.setattr(co.time, "time", lambda: 1000.0)
    assert co._should_extract_icon("Code.exe") is True
    assert co._should_extract_icon("Code.exe") is False
    assert co._should_extract_icon("chrome.exe") is True
    assert co._should_extract_icon("word.exe") is True
    # 超过上限后触发清理；把旧条目设为过期
    co._icon_extract_recent["old.exe"] = 1.0
    co._should_extract_icon("new.exe")
    assert "old.exe" not in co._icon_extract_recent


def test_get_process_rss_mb(monkeypatch):
    class Proc:
        def memory_info(self):
            class M:
                rss = 123 * 1024 * 1024
            return M()

    import psutil
    monkeypatch.setattr(psutil, "Process", lambda: Proc())
    assert round(co._get_process_rss_mb()) == 123


def test_aggressive_cleanup(monkeypatch):
    calls = []
    monkeypatch.setattr(co.gc, "collect", lambda: calls.append(1))
    co._aggressive_cleanup()
    assert len(calls) == 2


def test_maybe_mem_check_levels(monkeypatch):
    monkeypatch.setattr(co, "_MEM_CHECK_INTERVAL_SEC", 0)
    monkeypatch.setattr(co, "_last_mem_check", 0)
    monkeypatch.setattr(co, "_MEM_WARN_MB", 100)
    monkeypatch.setattr(co, "_MEM_CRITICAL_MB", 200)
    monkeypatch.setattr(co, "_get_process_rss_mb", lambda: 0)
    co._maybe_mem_check()

    monkeypatch.setattr(co, "_get_process_rss_mb", lambda: 150)
    gc_calls = []
    monkeypatch.setattr(co.gc, "collect", lambda: gc_calls.append(1))
    co._maybe_mem_check()
    assert gc_calls

    class C:
        _recent_context_cache = {}
        _recent_categories = ["a", "b", "c", "d"]

    monkeypatch.setattr(co, "_get_process_rss_mb", lambda: 250)
    aggressive = []
    monkeypatch.setattr(co, "_aggressive_cleanup", lambda: aggressive.append(1))
    co._maybe_mem_check(C())
    assert aggressive


def test_maybe_gc(monkeypatch):
    monkeypatch.setattr(co, "_last_gc_time", 0)
    monkeypatch.setattr(co.gc, "collect", lambda: 3)
    co._maybe_gc()


def test_smooth_category_cases(monkeypatch):
    assert co._smooth_category("不存在", "Code.exe", "x", False) == "不存在"
    monkeypatch.setattr(co, "get_recent_activities", lambda n: [])
    assert co._smooth_category("其他", "Code.exe", "x", False) == "其他"

    recent = [{
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "category": "开发", "app_name": "Code.exe", "window_title": "main.py",
        "summary": "写代码",
    }]
    monkeypatch.setattr(co, "get_recent_activities", lambda n: recent)
    assert co._smooth_category("其他", "Code.exe", "main.py", True) == "开发"
    assert co._smooth_category("其他", "Code.exe", "main.py", False) == "开发"
    assert co._smooth_category("其他", "Word.exe", "other.docx", False) == "其他"

    recent_bad = [{
        "timestamp": "bad", "category": "开发", "app_name": "Other",
        "window_title": "a - b", "summary": "截图文件缺失，降级",
    }]
    monkeypatch.setattr(co, "get_recent_activities", lambda n: recent_bad)
    assert co._smooth_category("其他", "Other", "a - b", False) == "其他"


def test_smooth_category_b32_other_is_never_reference(monkeypatch):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    recent = [
        {"timestamp": now, "category": "其他", "app_name": "Code.exe",
         "window_title": "main.py", "summary": "认不出"},
        {"timestamp": now, "category": "开发", "app_name": "Code.exe",
         "window_title": "main.py", "summary": "写代码"},
    ]
    monkeypatch.setattr(co, "get_recent_activities", lambda n: recent)
    assert co._smooth_category("其他", "Code.exe", "main.py", False, ai_category="") == "开发"
    # AI 明确返回“其他”时，诚实保留，不伪装成开发
    assert co._smooth_category("其他", "Code.exe", "main.py", False, ai_category="其他") == "其他"
    # 重复帧没有新的 AI 判断，允许继承上下文
    assert co._smooth_category("其他", "Code.exe", "main.py", True, ai_category="其他") == "开发"


def test_adaptive_sampling(monkeypatch):
    c = co.Collector()
    monkeypatch.setattr(config, "ADAPTIVE_SAMPLING_ENABLED", False)
    c._record_category_for_adaptive("开发")
    assert c.get_adaptive_interval() is None

    monkeypatch.setattr(config, "ADAPTIVE_SAMPLING_ENABLED", True)
    monkeypatch.setattr(config, "ADAPTIVE_SAMPLING_WINDOW", 3)
    monkeypatch.setattr(config, "SCREENSHOT_INTERVAL_SEC", 60)
    c._record_category_for_adaptive("开发")
    assert c.get_adaptive_interval() == 60
    c._recent_categories = ["开发", "沟通", "开发"]
    assert c.get_adaptive_interval() is not None
    c._adaptive_next_interval = 99
    assert c.get_adaptive_interval() == 99
    c._reset_adaptive_interval()
    assert c._adaptive_next_interval is None
    c._recent_categories = ["开发", "开发", "开发"]
    assert c.get_adaptive_interval() is not None
    c._recent_categories = ["开发", "沟通", "学习"]
    assert c.get_adaptive_interval() is not None


def test_interval_and_merge(monkeypatch):
    c = co.Collector()
    monkeypatch.setattr(config, "SCREENSHOT_INTERVAL_SEC", 60)
    assert c._compute_interval_sec(datetime.now()) == 60
    c._last_insert_dt = datetime.now() - timedelta(seconds=10)
    assert 9 <= c._compute_interval_sec(datetime.now()) <= 11
    c._last_insert_dt = datetime.now() - timedelta(seconds=999)
    assert c._compute_interval_sec(datetime.now()) == 300

    c._last_insert_dt = None
    assert c._should_merge_adjacent(datetime.now(), "Code.exe", "main.py") is False
    c._last_insert_dt = datetime.now() - timedelta(seconds=10)
    c._last_insert_sig = ("Code.exe", "main.py")
    assert c._should_merge_adjacent(datetime.now(), "Code.exe", "main.py") is True
    assert c._should_merge_adjacent(datetime.now(), "Word.exe", "a.docx") is False
    c._last_insert_dt = datetime.now() - timedelta(seconds=60)
    assert c._should_merge_adjacent(datetime.now(), "Code.exe", "main.py") is False


def test_resolve_analysis_path(tmp_path, monkeypatch):
    c = co.Collector()
    assert c._resolve_analysis_path("x.jpg", True, False) == ("x.jpg", None, False)
    assert c._resolve_analysis_path("x.jpg", True, True) == (None, None, False)
    c._last_frame_bytes = b"abc"
    monkeypatch.setattr(config, "SCREENSHOT_DIR", tmp_path)
    path, tmp, should = c._resolve_analysis_path("x.jpg", True, True)
    assert tmp == path and Path(path).exists()
    assert should is True
    Path(path).unlink()


def test_flush_segment(monkeypatch):
    c = co.Collector()
    calls = []
    monkeypatch.setattr(co, "upsert_app_usage_multi", lambda *a: calls.append(a))
    c._last_visible_windows = []
    c._flush_segment("2026-01-01 00:00:00")
    assert calls == []
    c._last_visible_windows = [{"app_name": "Code.exe"}]
    c._segment_start = "2026-01-01 00:00:00"
    c._flush_segment("2026-01-01 00:01:00")
    assert calls
    assert c._last_visible_windows == []


def _patch_capture(monkeypatch, tmp_path, ai=False, duplicate=False):
    shot = tmp_path / "shot.jpg"
    shot.write_bytes(b"\xff\xd8x")
    import app_tracker
    fg = {
        "app_name": "Code.exe", "window_title": "main.py - VS Code", "exe_path": "/code.exe"}
    monkeypatch.setattr(app_tracker, "get_foreground_app", lambda: fg)
    monkeypatch.setattr(co, "get_foreground_app", lambda: fg)
    monkeypatch.setattr(co, "get_idle_seconds", lambda: 0)
    monkeypatch.setattr(co, "get_active_monitor_index", lambda: 0)
    monkeypatch.setattr(co, "take_screenshot", lambda **k: ("shot.jpg", str(shot), duplicate))
    monkeypatch.setattr(co, "get_display_name", lambda x: "VS Code")
    monkeypatch.setattr(co, "get_visible_windows", lambda: [{
        "app_name": "Code.exe", "window_title": "main.py - VS Code",
        "area_ratio": 1.0, "is_foreground": True}])
    monkeypatch.setattr(co, "is_app_excluded", lambda x: False)
    monkeypatch.setattr(config, "is_privacy_skip_enabled", lambda: False)
    monkeypatch.setattr(co, "should_skip_capture", lambda *a: False)
    monkeypatch.setattr(co, "_should_extract_icon", lambda x: False)
    monkeypatch.setattr(co, "_smooth_category", lambda **k: k["current_category"])
    monkeypatch.setattr(co, "_maybe_gc", lambda: None)
    monkeypatch.setattr(co, "_maybe_mem_check", lambda *a: None)
    monkeypatch.setattr(co, "load_settings", lambda: {"ai_enabled": ai})
    monkeypatch.setattr(co, "classify", lambda app, ai_cat, title: ai_cat or "开发")
    monkeypatch.setattr(co, "insert_activity", lambda **k: True)
    monkeypatch.setattr(co, "merge_activity_interval", lambda *a, **k: None)
    monkeypatch.setattr(co, "get_recent_activities", lambda n: [])
    return shot


def test_capture_once_ai_off(tmp_path, monkeypatch):
    shot = _patch_capture(monkeypatch, tmp_path, ai=False)
    c = co.Collector()
    result = c.capture_once()
    assert result is not None
    assert result["category"] == "开发"
    assert not shot.exists()  # 分析完成后即删
    assert c._last_insert_dt is not None


def test_capture_once_ai_on(tmp_path, monkeypatch):
    shot = _patch_capture(monkeypatch, tmp_path, ai=True)
    monkeypatch.setattr(co, "analyze_screenshot", lambda *a: {
        "category": "开发", "summary": "AI 总结", "detail": "细节",
        "windows": [{"description": "编辑器"}]})
    c = co.Collector()
    result = c.capture_once()
    assert result["summary"] == "AI 总结"
    assert c._last_ai_detail == "细节"


def test_capture_once_ai_error_falls_back(tmp_path, monkeypatch):
    shot = _patch_capture(monkeypatch, tmp_path, ai=True)
    monkeypatch.setattr(co, "analyze_screenshot", lambda *a: (_ for _ in ()).throw(RuntimeError("ai down")))
    c = co.Collector()
    result = c.capture_once()
    assert result["category"] == "开发"


def test_capture_once_idle_excluded_privacy(tmp_path, monkeypatch):
    c = co.Collector()
    called = []
    monkeypatch.setattr(co, "get_idle_seconds", lambda: 999)
    monkeypatch.setattr(c, "_flush_segment", lambda t: called.append(t))
    assert c.capture_once() is None
    assert called

    monkeypatch.setattr(co, "get_idle_seconds", lambda: 0)
    _patch_capture(monkeypatch, tmp_path)
    monkeypatch.setattr(co, "is_app_excluded", lambda x: True)
    assert c.capture_once() is None

    monkeypatch.setattr(co, "is_app_excluded", lambda x: False)
    monkeypatch.setattr(config, "is_privacy_skip_enabled", lambda: True)
    monkeypatch.setattr(co, "should_skip_capture", lambda *a: True)
    assert c.capture_once() is None


def test_capture_once_screenshot_failure_and_lock(tmp_path, monkeypatch):
    c = co.Collector()
    monkeypatch.setattr(co, "get_idle_seconds", lambda: 0)
    monkeypatch.setattr(co, "get_active_monitor_index", lambda: 0)
    monkeypatch.setattr(co, "take_screenshot", lambda **k: (_ for _ in ()).throw(RuntimeError("grab fail")))
    assert c.capture_once() is None

    c._capture_lock.acquire()
    try:
        assert c.capture_once() is None
    finally:
        c._capture_lock.release()


def test_capture_once_merge_adjacent(tmp_path, monkeypatch):
    _patch_capture(monkeypatch, tmp_path)
    c = co.Collector()
    c._last_insert_dt = datetime.now() - timedelta(seconds=10)
    c._last_insert_sig = ("Code.exe", "main.py - VS Code")
    monkeypatch.setattr(co, "merge_activity_interval", lambda *a, **k: 1)
    assert c.capture_once() is None


def test_on_start_and_stop(tmp_path, monkeypatch):
    c = co.Collector()
    clean = []
    monkeypatch.setattr(co, "cleanup_old_data", lambda d: clean.append(d))
    monkeypatch.setattr(co, "cleanup_screenshots", lambda d: clean.append(d))
    monkeypatch.setattr(co, "get_screenshots_size_mb", lambda: 1.0)
    monkeypatch.setattr(co, "upsert_app_usage_multi", lambda *a: None)
    c.on_start()
    assert c._running is True
    c.stop()
    assert c._running is False
