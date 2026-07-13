"""测试数据可信度计算"""
import pytest
from unittest.mock import patch, MagicMock

def test_credibility_empty_date():
    """无数据时可信度为 0"""
    from routes.health import _calculate_credibility_for_date
    with patch('db.get_conn') as mock:
        mock_conn = MagicMock()
        mock_conn.__enter__.return_value.execute.return_value.fetchone.return_value = (0, 0)
        mock.return_value = mock_conn
        result = _calculate_credibility_for_date("2026-01-01")
        assert result["score"] == 0

def test_credibility_high_coverage():
    """高覆盖率时可信度高"""
    from routes.health import _calculate_credibility_for_date
    with patch('db.get_conn') as mock:
        mock_conn = MagicMock()
        # 240 条记录，跨度 480 分钟（8 小时）
        mock_conn.__enter__.return_value.execute.return_value.fetchone.return_value = (240, 480)
        mock.return_value = mock_conn
        result = _calculate_credibility_for_date("2026-01-01")
        assert result["coverage"] == 100
        assert result["score"] > 50

def test_credibility_db_error():
    """DB 异常时返回零值不崩溃"""
    from routes.health import _calculate_credibility_for_date
    with patch('db.get_conn', side_effect=Exception("DB error")):
        result = _calculate_credibility_for_date("2026-01-01")
        assert result["score"] == 0
