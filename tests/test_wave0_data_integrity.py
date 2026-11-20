"""
Wave0 数据可信三连回归测试（B01 污染 / B05 时长口径 / B20 幂等去重）

证据基准：《ChallengeDaily-项目深度摸底报告.md》3.2 / 3.5 章。
所有 DB 测试使用 conftest.temp_db 隔离临时库，不触碰真实数据。
"""
from datetime import datetime, timedelta

import config
import db
import ai_client
import collector
from classifier import classify


# ── B01: 降级分支禁止强制"生活"，交还规则分类 ──

def test_b01_missing_file_returns_empty_category(tmp_path, monkeypatch):
    """截图文件缺失时返回空分类（而非"生活"），classifier 规则兜底微信→沟通。"""
    monkeypatch.setattr(config, "AI_API_KEY", "test-key")
    monkeypatch.setattr(ai_client, "_cb_check", lambda: True)
    monkeypatch.setattr(ai_client, "_rate_limit_check", lambda model_type="text": True)

    missing = str(tmp_path / "definitely_missing.jpg")
    result = ai_client.analyze_screenshot(missing, "Weixin.exe", "微信")

    assert result["category"] == "", "文件缺失必须返回空分类，禁止 fallback 生活"
    assert "截图文件缺失" not in result["summary"], "摘要不得再写入污染文案"
    # 空分类交还规则后，微信应归"沟通"
    assert classify("Weixin.exe", result["category"], "微信") == "沟通"


def test_b01_no_key_returns_empty_category(monkeypatch):
    """未配置 AI Key 的降级同样不得强制"生活"。"""
    monkeypatch.setattr(config, "AI_API_KEY", "")
    result = ai_client.analyze_screenshot("whatever.jpg", "Code.exe", "main.py")
    assert result["category"] == ""
    assert classify("Code.exe", result["category"], "main.py") == "开发"


def test_b01_smoother_skips_polluted_reference(temp_db):
    """平滑器不得把"截图文件缺失"污染记录当作参照。"""
    # 旧的正确记录 + 两条更新的污染记录
    db.insert_activity("2026-11-20 10:00:00", "a.jpg", "Weixin.exe", "微信",
                       "沟通", "微信 - 聊天")
    db.insert_activity("2026-11-20 10:01:00", "b.jpg", "Weixin.exe", "微信",
                       "生活", "截图文件缺失")
    db.insert_activity("2026-11-20 10:02:00", "c.jpg", "Weixin.exe", "微信",
                       "生活", "截图文件缺失")

    smoothed = collector._smooth_category(
        current_category="生活", app_name="Weixin.exe",
        window_title="微信", is_duplicate=True,
    )
    assert smoothed == "沟通", "应跳过污染参照，沿用最近的正确工作分类"


def test_b01_resolve_analysis_path_cache_or_skip(tmp_path, monkeypatch):
    """重复帧重分析：有缓存帧→临时文件；无缓存帧→跳过（绝不读已删文件）。"""
    monkeypatch.setattr(config, "SCREENSHOT_DIR", tmp_path)
    c = collector.Collector()

    # 无缓存帧：跳过重分析
    path, tmp, should = c._resolve_analysis_path("deleted.jpg", True, True)
    assert path is None and tmp is None and should is False

    # 有缓存帧：写入临时文件，内容一致
    c._last_frame_bytes = b"fake-jpeg-bytes"
    path, tmp, should = c._resolve_analysis_path("deleted.jpg", True, True)
    assert should is True and path == tmp and tmp is not None
    with open(tmp, "rb") as f:
        assert f.read() == b"fake-jpeg-bytes"
    import os
    os.unlink(tmp)

    # 非重复帧：原路径直通
    path, tmp, should = c._resolve_analysis_path("real.jpg", False, True)
    assert path == "real.jpg" and tmp is None and should is True


# ── B05: interval_sec 记实际经过秒数 ──

def test_b05_interval_actual_elapsed_clamped():
    c = collector.Collector()
    now = datetime(2026, 11, 20, 12, 0, 0)

    # 首次无参照 → 配置默认
    assert c._compute_interval_sec(now) == config.SCREENSHOT_INTERVAL_SEC

    # 实际经过 90s → 90（不再恒 60）
    c._last_insert_dt = now - timedelta(seconds=90)
    assert c._compute_interval_sec(now) == 90

    # Wave2-B42 取代旧 clamp：5s 连采 → 记真实 5s（相邻采样由 merge 合并进上一行）
    c._last_insert_dt = now - timedelta(seconds=5)
    assert c._compute_interval_sec(now) == 5

    # 闲置恢复 999s → clamp 上限 300
    c._last_insert_dt = now - timedelta(seconds=999)
    assert c._compute_interval_sec(now) == 300


# ── B20: 同秒重复入库幂等 ──

def test_b20_insert_idempotent(temp_db):
    args = dict(timestamp="2026-11-20 08:48:10", screenshot="x.jpg",
                app_name="Weixin.exe", window_title="微信",
                category="沟通", summary="微信 - 聊天")
    first = db.insert_activity(**args)
    second = db.insert_activity(**args)
    assert first is True
    assert second is False, "同 (timestamp, app, title) 第二条必须被幂等忽略"

    with db.get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    assert n == 1

    # 同秒不同标题是合法的不同活动
    third = db.insert_activity(**{**args, "window_title": "微信 - 另一个窗口"})
    assert third is True
    with db.get_conn() as conn:
        n = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    assert n == 2


def test_b20_migration_creates_unique_index(temp_db):
    """V38 迁移必须建立唯一表达式索引（NULL 与 '' 等价）。"""
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='uq_activities_ts_app_title'"
        ).fetchone()
        ver = conn.execute("SELECT value FROM schema_version WHERE key='version'").fetchone()
    assert row is not None
    assert int(ver["value"]) >= 38