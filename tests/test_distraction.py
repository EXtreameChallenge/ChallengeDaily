"""测试分心检测和 AI 教练

覆盖：
- /api/pomodoro/distraction-check: 生活类触发分心、工作类不触发、缺 session_id、未知应用、API 异常
- /api/stats/distraction-heatmap: 空数据、有数据、DB 异常
"""
import pytest
from unittest.mock import patch
from datetime import datetime

import db


@pytest.fixture(autouse=True)
def _clean_tables(app):
    """每个测试前清空 activities 和 pomodoro_sessions 表，避免数据污染"""
    db._flush_pending_commits()
    with db.get_conn() as conn:
        conn.execute("DELETE FROM activities")
        conn.execute("DELETE FROM pomodoro_sessions")
        conn.commit()
    yield


# ── /api/pomodoro/distraction-check ──

def test_distraction_check_missing_session_id(authed_client):
    """缺少 session_id 返回 400"""
    resp = authed_client.post('/api/pomodoro/distraction-check', json={})
    assert resp.status_code == 400


def test_distraction_check_life_category(authed_client):
    """生活类应用触发分心，interrupted_count 累加为 1"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    session_id = db.insert_pomodoro_session(
        start_time=now, end_time=None, duration_min=25,
        task='测试', category='开发', status='running',
        interrupted_count=0, source='manual',
    )
    db.insert_activity(
        timestamp=now, screenshot='', app_name='bilibili.exe',
        window_title='哔哩哔哩 - 看视频', category='生活',
        summary='看视频', interval_sec=60,
    )
    with patch('app_tracker.get_foreground_app') as mock_fg:
        mock_fg.return_value = {
            "app_name": "bilibili.exe",
            "window_title": "哔哩哔哩 - 看视频",
            "exe_path": "",
        }
        resp = authed_client.post(
            '/api/pomodoro/distraction-check',
            json={"session_id": session_id},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["is_distraction"] is True
    assert data["category"] == "生活"
    assert data["distraction_count"] == 1


def test_distraction_check_work_category(authed_client):
    """工作类应用不触发分心，interrupted_count 保持 0"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    session_id = db.insert_pomodoro_session(
        start_time=now, end_time=None, duration_min=25,
        task='开发', category='开发', status='running',
        interrupted_count=0, source='manual',
    )
    db.insert_activity(
        timestamp=now, screenshot='', app_name='Code.exe',
        window_title='main.py - Visual Studio Code', category='开发',
        summary='写代码', interval_sec=60,
    )
    with patch('app_tracker.get_foreground_app') as mock_fg:
        mock_fg.return_value = {
            "app_name": "Code.exe",
            "window_title": "main.py - Visual Studio Code",
            "exe_path": "",
        }
        resp = authed_client.post(
            '/api/pomodoro/distraction-check',
            json={"session_id": session_id},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["is_distraction"] is False
    assert data["category"] == "开发"
    assert data["distraction_count"] == 0


def test_distraction_check_unknown_app(authed_client):
    """无匹配活动记录时 category='未知'，不触发分心"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    session_id = db.insert_pomodoro_session(
        start_time=now, end_time=None, duration_min=25,
        task='测试', category='开发', status='running',
        interrupted_count=0, source='manual',
    )
    with patch('app_tracker.get_foreground_app') as mock_fg:
        mock_fg.return_value = {
            "app_name": "unknown_app.exe",
            "window_title": "Unknown Window",
            "exe_path": "",
        }
        resp = authed_client.post(
            '/api/pomodoro/distraction-check',
            json={"session_id": session_id},
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["is_distraction"] is False
    assert data["category"] == "未知"


def test_distraction_check_foreground_error(authed_client):
    """get_foreground_app 抛异常时返回 500"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    session_id = db.insert_pomodoro_session(
        start_time=now, end_time=None, duration_min=25,
        task='测试', category='开发', status='running',
        interrupted_count=0, source='manual',
    )
    with patch('app_tracker.get_foreground_app', side_effect=Exception("WinAPI error")):
        resp = authed_client.post(
            '/api/pomodoro/distraction-check',
            json={"session_id": session_id},
        )
    assert resp.status_code == 500


# ── /api/stats/distraction-heatmap ──

def test_distraction_heatmap_empty(authed_client):
    """无分心数据时返回空数组"""
    resp = authed_client.get('/api/stats/distraction-heatmap?days=7')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["heatmap"] == []
    assert data["days"] == 7


def test_distraction_heatmap_with_data(authed_client):
    """有生活类活动时返回热点图数据，工作类不计入"""
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # 插入 3 条生活类记录
    for _ in range(3):
        db.insert_activity(
            timestamp=ts, screenshot='',
            app_name='bilibili.exe', window_title='视频',
            category='生活', summary='看视频', interval_sec=60,
        )
    # 插入 1 条工作类记录（不应出现在热点图）
    db.insert_activity(
        timestamp=ts, screenshot='',
        app_name='Code.exe', window_title='main.py',
        category='开发', summary='写代码', interval_sec=60,
    )
    resp = authed_client.get('/api/stats/distraction-heatmap?days=7')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["heatmap"]) >= 1
    # 生活类计数总和应为 3
    total_count = sum(item["count"] for item in data["heatmap"])
    assert total_count == 3


def test_distraction_heatmap_db_error(authed_client):
    """DB 异常时返回 500"""
    with patch('routes.stats.get_conn', side_effect=Exception("DB error")):
        resp = authed_client.get('/api/stats/distraction-heatmap?days=7')
    assert resp.status_code == 500
