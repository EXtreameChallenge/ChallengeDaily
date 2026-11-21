"""Round 13 终验：采集覆盖率分母必须扣关机/睡眠。

规则：
- 关机：boot_session 只覆盖开机区间，天然已扣；
- 睡眠：Kernel-Power 42/107 配对，从 boot_session 总时长中扣除；
- 分母 = awake_min，而不是 total_uptime_min。
"""

import services.system_events as se


def test_sleep_sessions_pair_and_clip(monkeypatch):
    events = [
        {"timestamp": "2026-11-20 23:30:00", "event_type": "sleep", "source": "System/Kernel-Power"},
        {"timestamp": "2026-11-21 07:30:00", "event_type": "resume", "source": "System/Kernel-Power"},
        {"timestamp": "2026-11-21 12:00:00", "event_type": "sleep", "source": "System/Kernel-Power"},
        {"timestamp": "2026-11-21 13:00:00", "event_type": "resume", "source": "System/Kernel-Power"},
    ]
    monkeypatch.setattr(se, "get_power_events", lambda *_: events)
    sessions = se.get_sleep_sessions("2026-11-21", "2026-11-21")
    # 跨夜那段只统计落在 11-21 的 00:00-07:30
    assert len(sessions) == 2
    assert sessions[0]["start"] == "2026-11-21 00:00:00"
    assert sessions[0]["end"] == "2026-11-21 07:30:00"
    assert sessions[0]["duration_sec"] == 7 * 3600 + 30 * 60
    assert sessions[1]["duration_sec"] == 3600


def test_coverage_uses_awake_min(monkeypatch):
    calls = {}

    def fake_sessions(start, end):
        return [
            {"type": "boot_session", "start": f"{start} 00:00:00", "end": f"{start} 20:00:00",
             "duration_sec": 20 * 3600, "source": "test"},
        ]

    def fake_sleep(start, end):
        calls["sleep"] = True
        return [
            {"type": "sleep_session", "start": f"{start} 02:00:00", "end": f"{start} 10:00:00",
             "duration_sec": 8 * 3600, "source": "test"},
        ]

    monkeypatch.setattr(se, "get_system_sessions", fake_sessions)
    monkeypatch.setattr(se, "get_sleep_sessions", fake_sleep)
    monkeypatch.setattr(se, "get_boot_events", lambda *_: [])

    cov = se.get_system_coverage("2026-11-21", "2026-11-21")
    assert calls.get("sleep") is True
    assert cov["total_uptime_min"] == 1200.0
    assert cov["sleep_min"] == 480.0
    assert cov["awake_min"] == 720.0
    assert cov["awake_sec"] == 12 * 3600
    assert cov["sleep_count"] == 1
