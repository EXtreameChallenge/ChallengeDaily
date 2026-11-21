from routes.health import bp as health_bp
from routes.activities import bp as activities_bp
from routes.stats import bp as stats_bp
from routes.reports import bp as reports_bp
from routes.settings_routes import bp as settings_bp
from routes.webhooks import bp as webhooks_bp
from routes.auto_report import bp as auto_report_bp
from routes.backup import bp as backup_bp
from routes.notifications import bp as notifications_bp
from routes.exports import bp as exports_bp
from routes.agent import bp as agent_bp
from routes.app_rules import bp as app_rules_bp
from routes.profile import bp as profile_bp
from routes.deep_insight import bp as deep_insight_bp
from routes.pomodoro import bp as pomodoro_bp
from routes.todos import bp as todos_bp
from routes.diaries import bp as diaries_bp
from routes.achievements import bp as achievements_bp
from routes.countdowns import bp as countdowns_bp
from routes.chat import bp as chat_bp
from routes.habits import bp as habits_bp
from routes.week_plan import bp as week_plan_bp
from routes.auth_routes import auth_bp
from routes.privacy_routes import privacy_bp
from routes.report_channels import bp as report_channels_bp
from routes.study_room import bp as study_room_bp
from routes.rules_engine import bp as rules_engine_bp
from routes.goals import bp as goals_bp
from routes.data_import import bp as data_import_bp
from routes.coach import bp as coach_bp
from routes.insight import bp as insight_bp
from routes.imports import bp as imports_bp
from routes.preferences import bp as preferences_bp
from routes.audit import bp as audit_bp
from routes.calendar_routes import bp as calendar_bp
from routes.git_routes import bp as git_integration_bp
from routes.benchmark_routes import bp as benchmark_bp
from routes.local_model_routes import bp as local_model_bp
from routes.platform_core_routes import bp as platform_core_bp
from routes.cv_routes import bp as cv_bp
from routes.rec_ab_routes import bp as rec_ab_bp
from routes.flags_adv_routes import bp as flags_adv_bp
from routes.chaos_cap_routes import bp as chaos_cap_bp
from routes.cost_compliance_routes import bp as cost_compliance_bp
from routes.privacy_dq_routes import bp as privacy_dq_bp
from routes.mlops_routes import bp as mlops_bp
from routes.infra_edge_routes import bp as infra_edge_bp
from routes.network_dr_routes import bp as network_dr_bp
from routes.flow_control_routes import bp as flow_control_bp
from routes.db_advanced_routes import bp as db_advanced_bp
from routes.cache_advanced_routes import bp as cache_advanced_bp
from routes.mq_stream_routes import bp as mq_stream_bp
from routes.security_advanced_routes import bp as security_advanced_bp
from routes.perf_apm_routes import bp as perf_apm_bp
from routes.deployment_routes import bp as deployment_bp
from routes.quality_docs_routes import bp as quality_docs_bp
from routes.daily_card import bp as daily_card_bp
from routes.growth import bp as growth_bp
from routes.ritual import bp as ritual_bp
from routes.scheduler import bp as scheduler_bp
from routes.mubu_routes import bp as mubu_bp
from routes.mubu_routes import memory_bp
from routes.obsidian_routes import bp as obsidian_bp
from routes.reclassify_routes import bp as reclassify_bp
from routes.web_tracker import bp as web_tracker_bp
from routes.aw_compat import bp as aw_compat_bp
from routes.wakatime_compat import bp as wakatime_compat_bp
from routes.leaderboard import bp as leaderboard_bp
from routes.ai_today_summary import bp as ai_today_summary_bp
from routes.user_profile_routes import bp as user_profile_bp
from routes.todo_extraction import bp as todo_extraction_bp
from routes.report_templates import bp as report_templates_bp
from routes.agent_routes import bp as agent_routes_bp
from routes.keyboard_routes import keyboard_bp
from routes.tools_routes import tools_bp
from routes.enterprise_routes import enterprise_bp
from routes.xiaohei_routes import bp as xiaohei_bp

ALL_BLUEPRINTS = [
    health_bp,
    activities_bp,
    stats_bp,
    reports_bp,
    settings_bp,
    webhooks_bp,
    auto_report_bp,
    backup_bp,
    notifications_bp,
    exports_bp,
    agent_bp,
    app_rules_bp,
    profile_bp,
    deep_insight_bp,
    pomodoro_bp,
    todos_bp,
    diaries_bp,
    achievements_bp,
    countdowns_bp,
    chat_bp,
    habits_bp,
    week_plan_bp,
    auth_bp,
    privacy_bp,
    report_channels_bp,
    study_room_bp,
    rules_engine_bp,
    goals_bp,
    data_import_bp,
    coach_bp,
    insight_bp,
    imports_bp,
    preferences_bp,
    audit_bp,
    calendar_bp,
    git_integration_bp,
    benchmark_bp,
    local_model_bp,
    platform_core_bp,
    cv_bp,
    rec_ab_bp,
    flags_adv_bp,
    chaos_cap_bp,
    cost_compliance_bp,
    privacy_dq_bp,
    mlops_bp,
    infra_edge_bp,
    network_dr_bp,
    flow_control_bp,
    db_advanced_bp,
    cache_advanced_bp,
    mq_stream_bp,
    security_advanced_bp,
    perf_apm_bp,
    deployment_bp,
    quality_docs_bp,
    daily_card_bp,
    growth_bp,
    ritual_bp,
    scheduler_bp,
    mubu_bp,
    memory_bp,
    obsidian_bp,
    reclassify_bp,
    web_tracker_bp,
    aw_compat_bp,
    wakatime_compat_bp,
    leaderboard_bp,
    ai_today_summary_bp,
    user_profile_bp,
    todo_extraction_bp,
    report_templates_bp,
    agent_routes_bp,
    keyboard_bp,
    tools_bp,
    enterprise_bp,
    xiaohei_bp,
]
