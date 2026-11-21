"""减脂加固波第一批：死代码接线新增 API 的回归测试。

覆盖 6 个此前前端已调用但后端缺失的端点：
- /api/stats/focus-score/calendar
- /api/stats/wordcloud
- /api/week-plan/sprint/<week_start>
- /api/week-plan/sprint-goal/<week_start>
- /api/agent/status
- /api/agent/skills/<id>/toggle
"""
from datetime import date, timedelta

import agent_db
import db
import xiaohei_core as xc


def _current_week_start() -> str:
    today = date.today()
    return (today - timedelta(days=today.weekday())).strftime('%Y-%m-%d')


def test_focus_score_calendar_uses_real_sessions(authed_client):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM pomodoro_sessions")
        conn.execute(
            "INSERT INTO pomodoro_sessions (start_time, end_time, duration_min, task, category, status, interrupted_count) "
            "VALUES (?, ?, 25, '专注测试', '开发', 'completed', 0)",
            (f"{date.today().isoformat()} 09:00:00", f"{date.today().isoformat()} 09:25:00"),
        )
        conn.execute(
            "INSERT INTO pomodoro_sessions (start_time, end_time, duration_min, task, category, status, interrupted_count) "
            "VALUES (?, ?, 25, '中断测试', '开发', 'completed', 2)",
            (f"{date.today().isoformat()} 10:00:00", f"{date.today().isoformat()} 10:25:00"),
        )

    resp = authed_client.get('/api/stats/focus-score/calendar?months=3')
    assert resp.status_code == 200
    payload = resp.get_json()
    today = date.today().isoformat()
    day = next(d for d in payload['days'] if d['date'] == today)
    # (100 + 80) / 2 = 90 -> S
    assert day['score'] == 90
    assert day['grade'] == 'S'
    assert any(m['month'] == today[:7] and m['days_count'] >= 1 for m in payload['month_stats'])


def test_wordcloud_extracts_from_work_records(authed_client):
    xc.create_work_record({
        "date": date.today().isoformat(),
        "title": "重构 数据看板 词云",
        "category": "编码开发",
        "duration_sec": 900,
        "app_name": "Code.exe",
    })
    resp = authed_client.get('/api/stats/wordcloud')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['words'], "应至少抽出一个关键词"
    assert payload['source'] == 'work_records'


def test_sprint_aggregation_and_goal(authed_client):
    week_start = _current_week_start()
    with db.get_conn() as conn:
        conn.execute("DELETE FROM todos WHERE week_start=?", (week_start,))
        conn.execute(
            "INSERT INTO todos (title, category, task_level, week_start, status, target_min, progress_min, completed_at) "
            "VALUES ('Sprint 完成项', '开发', 'week', ?, 'completed', 25, 25, ?)",
            (week_start, f"{week_start} 10:00:00"),
        )
        conn.execute(
            "INSERT INTO todos (title, category, task_level, week_start, status, target_min, progress_min) "
            "VALUES ('Sprint 未完成项', '开发', 'week', ?, 'pending', 25, 0)",
            (week_start,),
        )

    resp = authed_client.get(f'/api/week-plan/sprint/{week_start}')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['total_tasks'] == 2
    assert payload['completed_tasks'] == 1
    assert payload['completion_rate'] == 50.0
    assert len(payload['burndown']) == 7
    assert len(payload['daily_completion']) == 7

    save = authed_client.post(
        f'/api/week-plan/sprint-goal/{week_start}',
        json={'goal_text': '冲刺目标：完成接线'},
    )
    assert save.status_code == 200
    load = authed_client.get(f'/api/week-plan/sprint-goal/{week_start}')
    assert load.status_code == 200
    assert load.get_json()['goal_text'] == '冲刺目标：完成接线'


def test_agent_status_and_skill_toggle(authed_client):
    status = authed_client.get('/api/agent/status')
    assert status.status_code == 200
    payload = status.get_json()
    assert payload['engine'] in ('agno', 'classic')
    assert payload['role'] == 'single'
    assert payload['reasoning_level'] in ('low', 'medium', 'high')
    assert payload['team_active'] is False

    skill_id = agent_db.save_skill(name='接线测试技能', description='test', status='pending')
    first = authed_client.post(f'/api/agent/skills/{skill_id}/toggle')
    assert first.status_code == 200
    assert first.get_json()['enabled'] is True

    second = authed_client.post(f'/api/agent/skills/{skill_id}/toggle')
    assert second.status_code == 200
    assert second.get_json()['enabled'] is False

    missing = authed_client.post('/api/agent/skills/not-exist/toggle')
    assert missing.status_code == 404


def test_rule_create_and_delete_support_workflow_editor(authed_client):
    """WorkflowEditor 还缺 create/delete 两个动作，本次一并补齐。"""
    created = authed_client.post('/api/rules/create', json={
        'name': '接线测试规则',
        'description': 'test',
        'trigger_type': 'pomodoro_complete',
        'trigger_params': {},
        'action_type': 'notify',
        'action_params': {'message': 'done'},
    })
    assert created.status_code == 200
    rule_id = created.get_json()['id']

    listed = authed_client.get('/api/rules/list').get_json()['rules']
    assert any(r['id'] == rule_id for r in listed)

    deleted = authed_client.delete(f'/api/rules/{rule_id}')
    assert deleted.status_code == 200
    listed_after = authed_client.get('/api/rules/list').get_json()['rules']
    assert not any(r['id'] == rule_id for r in listed_after)

    invalid = authed_client.post('/api/rules/create', json={
        'name': '非法触发器', 'trigger_type': 'not-a-trigger',
    })
    assert invalid.status_code == 400

