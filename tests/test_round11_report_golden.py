"""轮11 B33：六种日报模板金样测试。

同一份输入快照 → 当前模板输出存 golden；拆分后逐字节比对。
设置 UPDATE_GOLDEN=1 可重新生成基线（仅限有意改变输出时）。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import report

DATE = "2026-11-20"
GOLDEN_DIR = Path(__file__).parent / "golden" / "round11_reports"

ACTIVITIES = [
    {"timestamp": "2026-11-20 08:58:00", "category": "开发", "app_name": "code", "window_title": "report.py - ChallengeDaily", "summary": "拆分日报生成模块", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 09:00:00", "category": "开发", "app_name": "code", "window_title": "report.py - ChallengeDaily", "summary": "编写模板分层代码", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 09:02:00", "category": "开发", "app_name": "code", "window_title": "report.py - ChallengeDaily", "summary": "调试模板输出", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 09:04:00", "category": "开发", "app_name": "terminal", "window_title": "PowerShell", "summary": "运行单元测试", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 09:06:00", "category": "开发", "app_name": "terminal", "window_title": "PowerShell", "summary": "运行单元测试", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 10:00:00", "category": "会议", "app_name": "feishu", "window_title": "周会", "summary": "同步排期与风险", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 10:02:00", "category": "会议", "app_name": "feishu", "window_title": "周会", "summary": "确认交付边界", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 10:04:00", "category": "会议", "app_name": "feishu", "window_title": "周会", "summary": "确认交付边界", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 11:00:00", "category": "文档", "app_name": "typora", "window_title": "轮11方案.md", "summary": "整理拆分方案", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 11:02:00", "category": "文档", "app_name": "typora", "window_title": "轮11方案.md", "summary": "补充验收口径", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 11:04:00", "category": "文档", "app_name": "typora", "window_title": "轮11方案.md", "summary": "补充验收口径", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 13:30:00", "category": "测试", "app_name": "pytest", "window_title": "pytest", "summary": "跑全量回归", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 13:32:00", "category": "测试", "app_name": "pytest", "window_title": "pytest", "summary": "跑全量回归", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 14:00:00", "category": "开发", "app_name": "code", "window_title": "Settings.tsx - ChallengeDaily", "summary": "拆分设置页组件", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 14:02:00", "category": "开发", "app_name": "code", "window_title": "Settings.tsx - ChallengeDaily", "summary": "检查 props 边界", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 14:04:00", "category": "开发", "app_name": "code", "window_title": "Settings.tsx - ChallengeDaily", "summary": "检查 props 边界", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 15:00:00", "category": "学习", "app_name": "browser", "window_title": "sqlite-vec 文档", "summary": "阅读向量检索文档", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 15:02:00", "category": "学习", "app_name": "browser", "window_title": "sqlite-vec 文档", "summary": "记录迁移要点", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 16:00:00", "category": "生活", "app_name": "wechat", "window_title": "微信", "summary": "午间休息", "ai_detail": "", "windows_json": "[]"},
    {"timestamp": "2026-11-20 16:02:00", "category": "生活", "app_name": "wechat", "window_title": "微信", "summary": "午间休息", "ai_detail": "", "windows_json": "[]"},
]

SUMMARY = {
    "total": len(ACTIVITIES),
    "first_ts": ACTIVITIES[0]["timestamp"],
    "last_ts": ACTIVITIES[-1]["timestamp"],
    "categories": {"开发": 8, "会议": 3, "文档": 3, "测试": 2, "学习": 2, "生活": 2},
}
APP_USAGE = [
    {"app_name": "code", "duration_min": 120},
    {"app_name": "terminal", "duration_min": 40},
    {"app_name": "feishu", "duration_min": 35},
    {"app_name": "typora", "duration_min": 25},
    {"app_name": "pytest", "duration_min": 20},
]


@pytest.fixture()
def offline_ai(monkeypatch):
    # 固定模板依赖的两个全局输入，避免前序测试污染导致金样漂移。
    monkeypatch.setattr(report.config, "AI_API_KEY", "")
    monkeypatch.setattr(report.config, "SCREENSHOT_INTERVAL_SEC", 60)


def test_six_templates_match_golden(offline_ai):
    assert set(report._TEMPLATE_MAP) == {"standard", "simple", "technical", "okr", "ai", "deep"}
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for name, func in report._TEMPLATE_MAP.items():
        content = func(DATE, ACTIVITIES, SUMMARY, APP_USAGE)
        golden = GOLDEN_DIR / f"{name}.md"
        if os.environ.get("UPDATE_GOLDEN") == "1":
            golden.write_text(content, encoding="utf-8")
        assert golden.exists(), f"缺少金样: {golden}"
        assert content == golden.read_text(encoding="utf-8"), f"{name} 输出与金样不一致"
