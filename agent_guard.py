"""
ChallengeDaily — Agent 统一安全护栏（Guard）

核心职责：
  1. 为每个工具标注风险级别（只读 / 操作级 / 危险级）；
  2. 写操作在真正执行前必须拿到用户确认（confirmation token，5 分钟有效）；
  3. 把来自模型/外部的不可信数据用 <untrusted_data> 包裹，防止 prompt 注入；
  4. 每次工具调用都落审计日志（agent_audit_log），便于事后追溯。

设计原则：默认安全。凡是查不清风险的工具，一律按 OPERATION 处理（需确认）。
"""
import logging
import secrets
import threading
import time
from enum import Enum
from typing import Any

import agent_db

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 风险级别定义
# ═══════════════════════════════════════════════════════════════

class ToolRiskLevel(str, Enum):
    """工具风险级别（继承 str 便于 JSON 序列化与比较）"""
    READ_ONLY = "READ_ONLY"     # 只读：查询类，无需确认，可直接执行
    OPERATION = "OPERATION"     # 操作级：会写库/改状态，需用户确认
    DANGEROUS = "DANGEROUS"      # 危险级：改全局配置/外部系统写入，需二次确认


# ═══════════════════════════════════════════════════════════════
# 34 个工具的风险映射
#   - READ_ONLY: 纯查询，可直接执行
#   - OPERATION: 本地写库，需 confirm_message
#   - DANGEROUS: 改全局设置/写外部系统，需二次确认
# ═══════════════════════════════════════════════════════════════
TOOL_RISK_MAP: dict[str, ToolRiskLevel] = {
    # ── 迁移自 chat.py 的 9 个工具 ──
    "get_activities": ToolRiskLevel.READ_ONLY,
    "get_todos": ToolRiskLevel.READ_ONLY,
    "get_pomodoro_stats": ToolRiskLevel.READ_ONLY,
    "get_daily_summary": ToolRiskLevel.READ_ONLY,
    "get_work_trends": ToolRiskLevel.READ_ONLY,
    "get_user_profile": ToolRiskLevel.READ_ONLY,
    "create_todo": ToolRiskLevel.OPERATION,
    "start_pomodoro": ToolRiskLevel.OPERATION,
    "save_diary": ToolRiskLevel.OPERATION,

    # ── P0 工具（15 个）──
    "create_goal": ToolRiskLevel.OPERATION,
    "list_goals": ToolRiskLevel.READ_ONLY,
    "update_goal": ToolRiskLevel.OPERATION,
    "get_week_plan": ToolRiskLevel.READ_ONLY,
    "create_plan_item": ToolRiskLevel.OPERATION,
    "create_habit": ToolRiskLevel.OPERATION,
    "list_habits": ToolRiskLevel.READ_ONLY,
    "get_stats": ToolRiskLevel.READ_ONLY,
    "get_heatmap": ToolRiskLevel.READ_ONLY,
    "get_settings": ToolRiskLevel.READ_ONLY,
    "update_setting": ToolRiskLevel.DANGEROUS,   # 改全局设置，风险高
    "create_reminder": ToolRiskLevel.OPERATION,
    "list_reminders": ToolRiskLevel.READ_ONLY,
    "search_knowledge": ToolRiskLevel.READ_ONLY,
    "get_project_map": ToolRiskLevel.READ_ONLY,

    # ── P1 工具（10 个）──
    "mubu_search": ToolRiskLevel.READ_ONLY,
    "mubu_create_doc": ToolRiskLevel.OPERATION,
    "mubu_update_doc": ToolRiskLevel.DANGEROUS,  # 外部系统覆盖写
    "obsidian_sync": ToolRiskLevel.OPERATION,
    "get_calendar": ToolRiskLevel.READ_ONLY,
    "generate_report": ToolRiskLevel.OPERATION,
    "export_data": ToolRiskLevel.OPERATION,
    "get_pomodoro_detail": ToolRiskLevel.READ_ONLY,
    "trigger_workflow": ToolRiskLevel.DANGEROUS,  # 触发多步自动化流程
    "list_skills": ToolRiskLevel.READ_ONLY,
}


def check_tool_risk(tool_name: str) -> ToolRiskLevel:
    """查询工具风险级别。未登记的工具默认按 OPERATION（需确认）处理。"""
    level = TOOL_RISK_MAP.get(tool_name)
    if level is None:
        logger.warning(f"工具 {tool_name} 未登记风险级别，默认按 OPERATION 处理")
        return ToolRiskLevel.OPERATION
    return level


# ═══════════════════════════════════════════════════════════════
# 确认令牌（内存态，5 分钟有效，自动过期清理）
# ═══════════════════════════════════════════════════════════════
_TOKEN_TTL_SEC = 300  # 5 分钟
_confirmation_tokens: dict[str, float] = {}  # token -> 过期时间戳
_token_lock = threading.Lock()


def _cleanup_expired_tokens() -> None:
    """清理过期令牌（调用方需持有锁）"""
    now = time.time()
    expired = [t for t, exp in _confirmation_tokens.items() if exp <= now]
    for t in expired:
        _confirmation_tokens.pop(t, None)


def generate_confirmation_token() -> str:
    """生成一个 5 分钟有效的确认令牌。"""
    token = secrets.token_hex(16)
    with _token_lock:
        _cleanup_expired_tokens()
        _confirmation_tokens[token] = time.time() + _TOKEN_TTL_SEC
    return token


def validate_confirmation_token(token: str) -> bool:
    """校验确认令牌是否有效（有效即消费掉，一次性使用）。"""
    if not token:
        return False
    with _token_lock:
        _cleanup_expired_tokens()
        exp = _confirmation_tokens.get(token)
        if exp is None:
            return False
        # 一次性令牌：用后即焚
        _confirmation_tokens.pop(token, None)
        return exp > time.time()


# ═══════════════════════════════════════════════════════════════
# 不可信数据包裹（防 prompt 注入）
# ═══════════════════════════════════════════════════════════════

def wrap_untrusted_data(content: str) -> str:
    """把来自工具/外部的内容包裹为 <untrusted_data> 段。

    模型在系统提示中被指示：<untrusted_data> 内的内容只是数据，不得当作指令执行。
    这样即使工具返回里夹带“忽略以上指令”之类的文本，也不会污染主流程。
    """
    if not content:
        return ""
    return f"<untrusted_data>\n{content}\n</untrusted_data>"


# ═══════════════════════════════════════════════════════════════
# 审计日志封装
# ═══════════════════════════════════════════════════════════════

def audit_tool_call(trace_id: str, tool_name: str, risk_level: ToolRiskLevel,
                    params: dict | None, result_preview: str,
                    confirmed: bool, cost_ms: int) -> None:
    """记录一次工具调用到审计日志（失败静默降级）。"""
    try:
        agent_db.log_audit(
            trace_id=trace_id or "",
            tool_name=tool_name,
            risk_level=risk_level.value if isinstance(risk_level, ToolRiskLevel) else str(risk_level),
            params=params or {},
            result_preview=result_preview or "",
            confirmed=1 if confirmed else 0,
            cost_ms=int(cost_ms),
        )
    except Exception as e:
        logger.warning(f"audit_tool_call 写日志失败（已降级）: {e}")


def needs_confirmation(tool_name: str) -> bool:
    """便捷判断：该工具是否需要用户确认才执行。"""
    return check_tool_risk(tool_name) in (ToolRiskLevel.OPERATION, ToolRiskLevel.DANGEROUS)
