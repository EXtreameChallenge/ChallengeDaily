"""
B18 小黑业务闭环回归：日报消费 work_records / 模板应用到日报 / 积分发放。
"""
import report
import xiaohei_core as xc


def test_b18_report_consumes_work_records(temp_db):
    xc.create_work_record({
        "date": "2026-11-20", "title": "写 B18 闭环", "category": "编码开发",
        "duration_sec": 1800, "app_name": "Code.exe",
    })
    section = report._work_records_section("2026-11-20")
    assert "工作记录（小黑）" in section
    assert "写 B18 闭环" in section
    assert "30 分钟" in section


def test_b18_report_section_empty(temp_db):
    assert report._work_records_section("2026-11-20") == ""


def test_b18_apply_template_to_report(temp_db, monkeypatch):
    tpls = xc.list_templates()
    assert tpls, "模板种子应已初始化"
    tid = tpls[0]["id"]
    captured = {}

    def fake_save(content, day):
        captured["content"] = content
        captured["day"] = day

    monkeypatch.setattr(report, "_save", fake_save)
    res = xc.apply_template_to_daily_report(tid, "2026-11-20")
    assert res["ok"] is True
    assert "应用模板" in captured["content"]
    assert captured["day"] == "2026-11-20"
