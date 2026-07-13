"""
v3.1.0 功能测试

覆盖：
- T1: 热力图年度范围 /api/stats/heatmap?range=year
- T7: activities ATTACH DATABASE 归档迁移
- T3: AI 拆解草案 /api/week-plan/auto-split（mock AI client）
"""
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import db


# ── T1: 热力图年度范围 ──

def test_heatmap_year_range(authed_client):
    """GET /api/stats/heatmap?range=year 返回正确的年度聚合数据"""
    # 插入测试数据：今天 + 半年前各一条
    today = date.today()
    half_year_ago = today - timedelta(days=180)
    ts_today = f"{today.isoformat()} 10:00:00"
    ts_old = f"{half_year_ago.isoformat()} 14:00:00"

    db.insert_activity(ts_today, "", "test.exe", "工作窗口", "开发", "测试摘要", interval_sec=3600)
    db.insert_activity(ts_old, "", "old.exe", "旧窗口", "开发", "旧摘要", interval_sec=7200)
    # 生活类不应计入 focus_min
    db.insert_activity(ts_today, "", "game.exe", "游戏", "生活", "游戏", interval_sec=3600)

    resp = authed_client.get(f"/api/stats/heatmap?range=year&date={today.isoformat()}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["range"] == "year"
    assert "data" in body
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 2

    # 验证每条数据结构
    for item in body["data"]:
        assert "date" in item
        assert "focus_min" in item
        assert "level" in item
        assert 0 <= item["level"] <= 4

    # 今天的记录：3600秒 = 60分钟，生活类不计入
    today_entry = next((d for d in body["data"] if d["date"] == today.isoformat()), None)
    assert today_entry is not None
    assert today_entry["focus_min"] == 60
    assert today_entry["level"] == 0  # 60分钟 < 120分钟阈值

    # 半年前的记录：7200秒 = 120分钟
    old_entry = next((d for d in body["data"] if d["date"] == half_year_ago.isoformat()), None)
    assert old_entry is not None
    assert old_entry["focus_min"] == 120
    assert old_entry["level"] == 1  # 120分钟 / 120 = 1


def test_heatmap_month_range(authed_client):
    """GET /api/stats/heatmap?range=month 返回月度数据"""
    today = date.today()
    ts = f"{today.isoformat()} 09:00:00"
    db.insert_activity(ts, "", "app.exe", "窗口", "开发", "摘要", interval_sec=3000)

    resp = authed_client.get(f"/api/stats/heatmap?range=month&date={today.isoformat()}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["range"] == "month"
    assert len(body["data"]) >= 1


def test_heatmap_week_range(authed_client):
    """GET /api/stats/heatmap?range=week 返回周度数据"""
    today = date.today()
    ts = f"{today.isoformat()} 11:00:00"
    db.insert_activity(ts, "", "app.exe", "窗口", "开发", "摘要", interval_sec=6000)

    resp = authed_client.get(f"/api/stats/heatmap?range=week&date={today.isoformat()}")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["range"] == "week"
    assert len(body["data"]) >= 1


# ── T7: 归档迁移 ──

def test_archive_migration(temp_db):
    """_do_archive 将超过保留天数的 activities 迁移到归档库"""
    from backup_scheduler import _do_archive, _ARCHIVE_RETENTION_DAYS

    # 插入一条过期数据和一条新数据
    cutoff_date = date.today() - timedelta(days=_ARCHIVE_RETENTION_DAYS + 10)
    old_ts = f"{cutoff_date.isoformat()} 10:00:00"
    new_ts = f"{date.today().isoformat()} 10:00:00"

    db.insert_activity(old_ts, "", "old.exe", "旧窗口", "开发", "旧摘要", interval_sec=60)
    db.insert_activity(new_ts, "", "new.exe", "新窗口", "开发", "新摘要", interval_sec=60)

    # 执行归档
    count = _do_archive(str(temp_db))
    assert count == 1, f"应归档 1 条记录，实际 {count}"

    # 验证主库只剩新数据
    with db.get_conn() as conn:
        rows = conn.execute("SELECT COUNT(*) as cnt FROM activities").fetchone()
        assert rows["cnt"] == 1, "主库应只剩 1 条新记录"
        remaining = conn.execute("SELECT app_name FROM activities").fetchone()
        assert remaining["app_name"] == "new.exe"

    # 验证归档库有旧数据
    with db.get_conn_with_archive() as conn:
        rows = conn.execute("SELECT COUNT(*) as cnt FROM archive.activities").fetchone()
        assert rows["cnt"] == 1, "归档库应有 1 条记录"
        archived = conn.execute("SELECT app_name, original_id FROM archive.activities").fetchone()
        assert archived["app_name"] == "old.exe"
        assert archived["original_id"] is not None, "归档库应保留 original_id"


def test_archive_no_data(temp_db):
    """无过期数据时归档返回 0"""
    from backup_scheduler import _do_archive

    # 只插入新数据
    new_ts = f"{date.today().isoformat()} 10:00:00"
    db.insert_activity(new_ts, "", "new.exe", "新窗口", "开发", "摘要", interval_sec=60)

    count = _do_archive(str(temp_db))
    assert count == 0, "无过期数据时应返回 0"

    # 主库数据不变
    with db.get_conn() as conn:
        rows = conn.execute("SELECT COUNT(*) as cnt FROM activities").fetchone()
        assert rows["cnt"] == 1


def test_archive_idempotent(temp_db):
    """归档操作可重复执行（幂等性）"""
    from backup_scheduler import _do_archive, _ARCHIVE_RETENTION_DAYS

    cutoff_date = date.today() - timedelta(days=_ARCHIVE_RETENTION_DAYS + 5)
    old_ts = f"{cutoff_date.isoformat()} 10:00:00"
    db.insert_activity(old_ts, "", "old.exe", "旧窗口", "开发", "旧摘要", interval_sec=60)

    # 第一次归档
    count1 = _do_archive(str(temp_db))
    assert count1 == 1

    # 第二次归档（无新数据）
    count2 = _do_archive(str(temp_db))
    assert count2 == 0


# ── T3: AI 拆解草案 ──

def test_auto_split_returns_draft(authed_client):
    """POST /api/week-plan/auto-split 返回 draft_tasks（mock AI client）"""
    # Mock AI client 返回 JSON 数组
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = (
        '[{"title":"需求分析","target_min":60,"category":"开发","day":1},'
        '{"title":"编码实现","target_min":90,"category":"开发","day":2},'
        '{"title":"测试验证","target_min":45,"category":"测试","day":3}]'
    )
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch('ai_client._get_client', return_value=mock_client):
        resp = authed_client.post('/api/week-plan/auto-split', json={
            'goal_title': '完成 v3.1 功能开发',
            'goal_description': '包含热力图、归档、AI拆解等功能',
            'week_start': '2026-07-13',
        })

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'draft'
    assert 'draft_tasks' in body
    assert isinstance(body['draft_tasks'], list)
    assert len(body['draft_tasks']) == 3

    # 验证任务结构
    task = body['draft_tasks'][0]
    assert 'title' in task
    assert 'target_min' in task
    assert 'category' in task
    assert 'day' in task


def test_auto_split_empty_title(authed_client):
    """POST /api/week-plan/auto-split 空标题返回 400"""
    resp = authed_client.post('/api/week-plan/auto-split', json={
        'goal_title': '',
        'goal_description': '描述',
        'week_start': '2026-07-13',
    })
    assert resp.status_code == 400
    body = resp.get_json()
    assert 'error' in body


def test_auto_split_ai_error(authed_client):
    """POST /api/week-plan/auto-split AI 异常返回 500"""
    with patch('ai_client._get_client', side_effect=Exception("AI 服务不可用")):
        resp = authed_client.post('/api/week-plan/auto-split', json={
            'goal_title': '测试目标',
            'goal_description': '描述',
            'week_start': '2026-07-13',
        })
    assert resp.status_code == 500
    body = resp.get_json()
    assert 'error' in body


# ── T5: SSE 事件流 ──

def test_sse_stream_requires_token(client):
    """GET /api/events/stream 无 token 返回 401"""
    resp = client.get('/api/events/stream')
    assert resp.status_code == 401


def test_sse_stream_with_token(client):
    """GET /api/events/stream 带正确 token（query param）返回 SSE 流"""
    # SSE 通过 query param ?token=xxx 鉴权（非 header）
    from routes.deps import LOCAL_TOKEN
    resp = client.get(f'/api/events/stream?token={LOCAL_TOKEN}', buffered=False)
    assert resp.status_code == 200
    assert resp.mimetype == 'text/event-stream'
