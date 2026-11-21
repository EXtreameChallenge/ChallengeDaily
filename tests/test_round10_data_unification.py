"""轮10 B24/B25/B37 端到端回归：隔离数据目录，真实迁移/删除/恢复。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def round10_e2e(tmp_path_factory):
    base = tmp_path_factory.mktemp("round10-e2e")
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_round10_e2e.py"),
            "--data-dir", str(base / "data"),
            "--home-dir", str(base / "home"),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    return json.loads(proc.stdout)


def test_b24_home_json_migrates_to_single_sqlite(round10_e2e):
    before = round10_e2e["migration_before"]
    after = round10_e2e["migration_after"]
    assert before["points_ledger"] == 0
    assert before["template_market"] == 0
    assert after["points_ledger"] == 2
    assert after["template_market"] >= 1
    assert after["enterprise_kv"] >= 1
    assert round10_e2e["points_balance"] == 120


def test_b25_template_counts_and_price_are_real(round10_e2e):
    assert round10_e2e["legacy_template_downloads_after_use"] == 1
    assert round10_e2e["published_template_price"] == 7


def test_b37_delete_scan_and_restore_three_roots(round10_e2e):
    assert round10_e2e["export_tables"] >= 40
    assert round10_e2e["export_directories"] >= 1
    assert round10_e2e["export_files"] >= 2
    assert round10_e2e["delete_rows"] > 0
    assert round10_e2e["scan_clean"] is True
    assert round10_e2e["restored_activities"] == 1
    assert round10_e2e["restored_legacy_template_downloads"] == 1
    assert round10_e2e["restored_salt"] is True
    assert round10_e2e["restored_screenshot"] is True
    assert round10_e2e["logs_removed_and_restored"] is True
