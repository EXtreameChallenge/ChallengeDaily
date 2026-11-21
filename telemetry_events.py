"""遥测埋点统一入口：任何调用点失败都不能影响主流程。"""
from __future__ import annotations


def track(event: str, data: dict | None = None) -> bool:
    try:
        from enterprise_features import telemetry
        return telemetry.track(event, data or {})
    except Exception:
        return False
