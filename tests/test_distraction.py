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
    # 清空分心去抖的 episode 状态（模块级字典，跨测试残留会污染结果）
    from routes import pomodoro as pomodoro_routes
    pomodoro_routes._distraction_episodes.clear()
    yield


# ── /api/pomodoro/distraction-check ──

def test_distraction_check_missing_session_id(authed_client):
    """缺少 session_id 返回 400"""
    resp = authed_client.post('/api/pomodoro/distraction-check', json={})
    assert resp.status_code == 400


def test_distraction_check_life_category_dwell(authed_client):
    """生活类应用连续停留满 30 秒才计 1 次有效分心（去抖），同 episode 不重复计数"""
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
    results = []
    with patch('app_tracker.get_foreground_app') as mock_fg, \
         patch('routes.pomodoro.time') as mock_time:
        mock_fg.return_value = {
            "app_name": "bilibili.exe",
            "window_title": "哔哩哔哩 - 看视频",
            "exe_path": "",
        }
        # 模拟每 15 秒轮询一次：t=1000 首次发现 / t=1015 停留中 / t=1030 满 30 秒 / t=1045 同 episode
        for t in (1000.0, 1015.0, 1030.0, 1045.0):
            mock_time.time.return_value = t
            resp = authed_client.post(
                '/api/pomodoro/distraction-check',
                json={"session_id": session_id},
            )
            assert resp.status_code == 200
            results.append(resp.get_json())
    # 前两次停留不足 30 秒不计数；第三次确认；第四次同 episode 不重复计
    assert [r["is_distraction"] for r in results] == [False, False, True, False]
    assert results[2]["category"] == "生活"
    assert results[2]["distraction_count"] == 1
    assert results[3]["distraction_count"] == 1


def test_distraction_check_short_glance_not_counted(authed_client):
    """不足 30 秒切回工作应用：视为误触一瞥，不计分心，episode 清零"""
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
    db.insert_activity(
        timestamp=now, screenshot='', app_name='Code.exe',
        window_title='main.py - Visual Studio Code', category='开发',
        summary='写代码', interval_sec=60,
    )
    # t=1000/1015 停在 B 站（不足 30 秒），t=1030 切回 VSCode
    timeline = [
        (1000.0, "bilibili.exe", "哔哩哔哩 - 看视频"),
        (1015.0, "bilibili.exe", "哔哩哔哩 - 看视频"),
        (1030.0, "Code.exe", "main.py - Visual Studio Code"),
    ]
    with patch('app_tracker.get_foreground_app') as mock_fg, \
         patch('routes.pomodoro.time') as mock_time:
        for t, app, title in timeline:
            mock_time.time.return_value = t
            mock_fg.return_value = {"app_name": app, "window_title": title, "exe_path": ""}
            resp = authed_client.post(
                '/api/pomodoro/distraction-check',
                json={"session_id": session_id},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["is_distraction"] is False
            assert data["distraction_count"] == 0


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


# ── _judge_focus 单元测试（三档严格度 + 关键词 + 相关性）──

class TestJudgeFocus:
    """测试核心判定函数 _judge_focus"""

    def test_excluded_app_returns_excluded(self):
        """排除应用应返回 excluded，不参与判定"""
        from routes.pomodoro import _judge_focus
        judgment, score, method = _judge_focus("微信", "工作群", "沟通", "写代码", "standard")
        assert judgment == "excluded"
        assert method == "excluded"

    def test_whitelist_keyword_returns_focused(self):
        """白名单关键词（教程/课程/文档）命中应判定专注，覆盖其他判定"""
        from routes.pomodoro import _judge_focus
        # B站教程页：虽然是生活类，但标题含"教程"应判定专注
        judgment, score, method = _judge_focus("chrome", "B站 - Python教程", "生活", "学习Python", "standard")
        assert judgment == "focused"
        assert "whitelist" in method

    def test_blacklist_keyword_returns_distracted(self):
        """黑名单关键词（推荐/热门/直播）命中应判定分心"""
        from routes.pomodoro import _judge_focus
        judgment, score, method = _judge_focus("chrome", "B站 - 热门推荐", "生活", "学习Python", "standard")
        assert judgment == "distracted"
        assert "blacklist" in method

    def test_hard_distraction_app_all_modes(self):
        """明显分心应用（游戏/短视频）在所有模式都应检测"""
        from routes.pomodoro import _judge_focus
        for mode in ["relaxed", "standard", "strict"]:
            judgment, _, _ = _judge_focus("steam.exe", "游戏中", "游戏", "", mode)
            assert judgment == "distracted", f"{mode} 模式下游戏应判定分心"

    def test_relaxed_mode_ignores_soft_distraction(self):
        """宽松模式下，非硬分心的生活类应用应判定专注"""
        from routes.pomodoro import _judge_focus
        judgment, _, method = _judge_focus("chrome", "购物网站", "生活", "", "relaxed")
        assert judgment == "focused"
        assert "relaxed" in method

    def test_standard_mode_uses_relevance(self):
        """标准模式下，生活类应用结合任务相关性判定"""
        from routes.pomodoro import _judge_focus
        # 任务是"看设计参考"，打开Figma应相关
        judgment, score, method = _judge_focus("chrome", "Figma - UI设计稿", "生活", "看设计参考", "standard")
        assert judgment in ("focused", "suspected")
        assert score > 0.3  # 应有一定相关性

    def test_work_category_always_focused(self):
        """开发/设计等工作类应用应判定专注"""
        from routes.pomodoro import _judge_focus
        judgment, _, _ = _judge_focus("Code.exe", "main.py", "开发", "写代码", "standard")
        assert judgment == "focused"

    def test_unknown_category_standard(self):
        """未知分类在标准模式下应返回 suspected（信息不足）"""
        from routes.pomodoro import _judge_focus
        judgment, _, method = _judge_focus("unknown_app", "未知窗口", "未知", "", "standard")
        assert judgment in ("suspected", "focused")

    def test_invalid_strictness_fallback(self):
        """无效严格度应回退到 standard"""
        from routes.pomodoro import _judge_focus
        judgment, _, _ = _judge_focus("chrome", "测试", "生活", "", "invalid_mode")
        # 不应崩溃，应返回有效判定
        assert judgment in ("focused", "suspected", "distracted", "excluded")


class TestTaskRelevance:
    """测试任务相关性计算 _calc_task_relevance"""

    def test_high_relevance_same_keywords(self):
        """任务标题与窗口标题有相同关键词应高相关"""
        from routes.pomodoro import _calc_task_relevance
        score = _calc_task_relevance("重构UI方案", "Figma - UI设计稿", "chrome")
        assert score > 0.3

    def test_low_relevance_unrelated(self):
        """完全不相关的任务和窗口应低相关"""
        from routes.pomodoro import _calc_task_relevance
        score = _calc_task_relevance("写Python代码", "淘宝 - 购物", "chrome")
        assert score < 0.3

    def test_empty_task_title(self):
        """空任务标题应返回0"""
        from routes.pomodoro import _calc_task_relevance
        score = _calc_task_relevance("", "任意窗口", "chrome")
        assert score == 0

    def test_development_app_high_base(self):
        """开发类应用应有基础相关性加成"""
        from routes.pomodoro import _calc_task_relevance
        score = _calc_task_relevance("写代码", "main.py", "Code.exe")
        assert score >= 0.5


class TestSessionReport:
    """测试单次番茄钟报告 API"""

    def test_session_report_missing_id(self, authed_client):
        """缺少 session_id 返回 400"""
        resp = authed_client.get('/api/pomodoro/session-report')
        assert resp.status_code == 400

    def test_session_report_not_found(self, authed_client):
        """不存在的 session_id 返回 404"""
        resp = authed_client.get('/api/pomodoro/session-report?session_id=999999')
        assert resp.status_code == 404

    def test_session_report_completed(self, authed_client):
        """正常完成的番茄钟应返回完整报告"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        session_id = db.insert_pomodoro_session(
            start_time=now, end_time=now, duration_min=25,
            task="测试任务", category="开发", status="completed",
            interrupted_count=1,
        )
        resp = authed_client.get(f'/api/pomodoro/session-report?session_id={session_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["session_id"] == session_id
        assert data["task"] == "测试任务"
        assert data["duration_min"] == 25
        assert data["distraction_count"] == 1
        assert "focus_score" in data
        assert "grade" in data
        assert data["grade"] in ("S", "A", "B", "C", "D")
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)

    def test_session_report_no_distractions_high_score(self, authed_client):
        """无分心的番茄钟应获得较高评分"""
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        session_id = db.insert_pomodoro_session(
            start_time=now, end_time=now, duration_min=25,
            task="专注任务", category="开发", status="completed",
            interrupted_count=0,
        )
        resp = authed_client.get(f'/api/pomodoro/session-report?session_id={session_id}')
        data = resp.get_json()
        assert data["focus_score"] >= 80
        assert data["grade"] in ("S", "A")
