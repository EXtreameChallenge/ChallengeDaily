"""挑战日报可选企业仿真插件。

设计原则：
- 26 个仿真域（304 个端点）默认不注册，避免把“无 UI、无真实调用方”的
  企业演示端点混进正式运行时。
- 剪贴板核心 3 个端点留在 routes/platform_core_routes.py，始终可用。
- 只有显式设置 CHALLENGEDAILY_ENTERPRISE_PLUGIN=1 时才注册本插件。

启用方式：
    PowerShell: $env:CHALLENGEDAILY_ENTERPRISE_PLUGIN="1"
    cmd:        set CHALLENGEDAILY_ENTERPRISE_PLUGIN=1
"""
from __future__ import annotations

import importlib
import os

# 26 个仿真域（顺序与 routes/__init__.py 移除顺序一致）
PLUGIN_MODULES = (
    "analytics_routes",
    "ai_intel_routes",
    "devops_routes",
    "platform_routes",
    "delight_routes",
    "resilience_routes",
    "advanced_data_routes",
    "security_routes2",
    "smart_routes",
    "uiux_routes",
    "perf_routes",
    "integration_routes",
    "viz_routes",
    "observability_routes",
    "workflow_routes",
    "cross_platform_routes",
    "knowledge_graph_routes",
    "smart_search_routes",
    "collaboration_routes",
    "version_control_routes",
    "offline_routes",
    "realtime_routes",
    "migration_i18n_routes",
    "accessibility_routes",
    "ml_basic_routes",
    "nlp_routes",
)

# 静态清单：启用时实际注册数以此为准，测试会对照真实 bp 数
EXPECTED_ENDPOINT_COUNT = 301
EXPECTED_BLUEPRINT_COUNT = 26


def is_enabled() -> bool:
    return os.getenv("CHALLENGEDAILY_ENTERPRISE_PLUGIN", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


def load_blueprints() -> list:
    """导入并返回 26 个仿真蓝图；仅在显式启用时调用。"""
    blueprints = []
    for module_name in PLUGIN_MODULES:
        module = importlib.import_module(f"enterprise_plugin.{module_name}")
        bp = getattr(module, "bp", None)
        if bp is None:
            raise RuntimeError(f"enterprise plugin module has no bp: {module_name}")
        blueprints.append(bp)
    return blueprints


def register(app) -> dict:
    """按开关注册插件；返回本次注册状态，不修改全局配置。"""
    if not is_enabled():
        status = {
            "enabled": False,
            "registered": False,
            "blueprints": 0,
            "endpoints": 0,
            "manifest_blueprints": EXPECTED_BLUEPRINT_COUNT,
            "manifest_endpoints": EXPECTED_ENDPOINT_COUNT,
        }
        app.extensions["enterprise_plugin"] = status
        return status

    blueprints = load_blueprints()
    for bp in blueprints:
        app.register_blueprint(bp)
    status = {
        "enabled": True,
        "registered": True,
        "blueprints": len(blueprints),
        "endpoints": sum(len(bp.deferred_functions) for bp in blueprints),
        "manifest_blueprints": EXPECTED_BLUEPRINT_COUNT,
        "manifest_endpoints": EXPECTED_ENDPOINT_COUNT,
    }
    app.extensions["enterprise_plugin"] = status
    return status
