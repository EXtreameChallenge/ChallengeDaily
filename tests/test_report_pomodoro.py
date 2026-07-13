"""测试番茄数据注入日报"""
import pytest
from unittest.mock import patch, MagicMock

def test_pomodoro_summary_empty_date():
    """无番茄数据时返回零值"""
    from routes.reports import _get_pomodoro_summary_for_date
    with patch('db.get_conn') as mock:
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value.execute.return_value.fetchone.return_value = (0, 0, 0, 0)
        mock.return_value = mock_conn
        result = _get_pomodoro_summary_for_date("2026-01-01")
        assert result["total"] == 0
        assert result["completed"] == 0

def test_pomodoro_summary_with_data():
    """有番茄数据时正确汇总"""
    from routes.reports import _get_pomodoro_summary_for_date
    with patch('db.get_conn') as mock:
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value.execute.return_value.fetchone.return_value = (8, 6, 200, 3)
        mock.return_value = mock_conn
        result = _get_pomodoro_summary_for_date("2026-01-01")
        assert result["total"] == 8
        assert result["completed"] == 6
        assert result["total_min"] == 200
        assert result["distractions"] == 3

def test_pomodoro_summary_db_error():
    """DB 异常时返回零值不崩溃"""
    from routes.reports import _get_pomodoro_summary_for_date
    with patch('db.get_conn', side_effect=Exception("DB error")):
        result = _get_pomodoro_summary_for_date("2026-01-01")
        assert result["total"] == 0
