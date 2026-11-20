"""
Wave2 批次3 回归测试（B06/B07/B08/B12/B13/B14/B42）

覆盖：相邻采样合并、interval 下限、键盘可用性/持久化、转写 unsupported、
机械音效真实可用性、PDF 输出路径白名单。
"""
from datetime import datetime, timedelta

import config
import db
import collector
import audio_recorder


# ── B42：相邻采样合并 & interval 不再 clamp 到 30 ──

def test_b42_merge_activity_interval(temp_db):
    db.insert_activity("2026-11-20 10:00:00", "a.jpg", "Code.exe", "main.py",
                       "开发", "写代码", interval_sec=10)
    assert db.merge_activity_interval(8) is True
    rows = db.get_activities("2026-11-20", "2026-11-20")
    assert rows[0]["interval_sec"] == 18, "相邻采样应累加到上一行"


def test_b42_merge_caps_at_max(temp_db):
    db.insert_activity("2026-11-20 10:00:00", "a.jpg", "Code.exe", "main.py",
                       "开发", "写代码", interval_sec=295)
    db.merge_activity_interval(20, max_interval_sec=300)
    rows = db.get_activities("2026-11-20", "2026-11-20")
    assert rows[0]["interval_sec"] == 300


def test_b42_interval_lower_bound_is_one():
    c = object.__new__(collector.Collector)
    c._last_insert_dt = datetime(2026, 11, 20, 10, 0, 0)
    now = c._last_insert_dt + timedelta(seconds=10)
    assert c._compute_interval_sec(now) == 10, "10s 真实间隔不得被抬到 30"


def test_b42_should_merge_only_same_signature():
    c = object.__new__(collector.Collector)
    c._last_insert_dt = datetime(2026, 11, 20, 10, 0, 0)
    c._last_insert_sig = ("Code.exe", "main.py")
    assert c._should_merge_adjacent(datetime(2026, 11, 20, 10, 0, 10),
                                    "Code.exe", "main.py") is True
    assert c._should_merge_adjacent(datetime(2026, 11, 20, 10, 0, 10),
                                    "Code.exe", "other.py") is False
    assert c._should_merge_adjacent(datetime(2026, 11, 20, 10, 1, 0),
                                    "Code.exe", "main.py") is False


# ── B06：键盘监听不假成功 + 持久化表 ──

def test_b06_start_listening_returns_real_result(monkeypatch):
    import keyboard_tracker as kt

    monkeypatch.setattr(kt, "check_availability",
                        lambda: {"ok": False, "reason": "keyboard 库不可用: mock"})
    result = kt.start_listening()
    assert result["ok"] is False
    assert "keyboard" in result["error"]


def test_b06_flush_stats_persists(temp_db, monkeypatch):
    import keyboard_tracker as kt
    from db import get_conn

    monkeypatch.setattr(kt, "_today", lambda: "2026-11-20")
    kt._key_stats.clear()
    kt._persisted.clear()
    kt._key_stats["A"] = 5
    assert kt.flush_stats() == 1

    with get_conn() as conn:
        row = conn.execute(
            "SELECT count FROM keyboard_stats_daily WHERE stat_date='2026-11-20' AND key_name='A'"
        ).fetchone()
    assert row and row[0] == 5


# ── B08：转写不返回占位文本 ──

def test_b08_transcribe_without_key_is_unsupported(tmp_path, monkeypatch):
    f = tmp_path / "a.wav"
    f.write_bytes(b"RIFF----")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = audio_recorder.transcribe_audio(str(f))
    assert result["ok"] is False
    assert result.get("unsupported") is True
    assert "占位" not in result.get("error", "")
    assert "text" not in result


def test_b08_transcribe_missing_file():
    result = audio_recorder.transcribe_audio("definitely_missing.wav")
    assert result["ok"] is False
    assert "不存在" in result["error"]


# ── B07：录音未启动时 stop 如实失败 ──

def test_b07_stop_without_recording():
    result = audio_recorder.stop_recording()
    assert result["ok"] is False


# ── B12：机械音效可用性如实返回 ──

def test_b12_sound_status_shape():
    import mechanical_sound as ms
    status = ms.get_status()
    assert "available" in status and "enabled" in status
    result = ms.set_enabled(True)
    assert isinstance(result, dict) and "ok" in result
    ms.set_enabled(False)


# ── B13/B14：输出路径白名单 ──

def test_b13_pdf_output_path_blocks_outside_data_dir(tmp_path, monkeypatch):
    import routes.tools_routes as tr
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    outside = str(tmp_path / "elsewhere" / "x.pdf")
    try:
        tr._pdf_output_path(outside)
    except ValueError:
        pass
    else:
        raise AssertionError("应用数据目录外的 PDF 输出必须被拒绝")
    inside = str(tmp_path / "data" / "ok.pdf")
    assert tr._pdf_output_path(inside).endswith("ok.pdf")
