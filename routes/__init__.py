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
from routes.analytics_routes import bp as analytics_bp
from routes.ai_intel_routes import bp as ai_intel_bp
from routes.devops_routes import bp as devops_bp
from routes.platform_routes import bp as platform_bp
from routes.delight_routes import bp as delight_bp
from routes.resilience_routes import bp as resilience_bp
from routes.advanced_data_routes import bp as advanced_data_bp
from routes.security_routes2 import bp as security_bp2
from routes.smart_routes import bp as smart_bp
from routes.uiux_routes import bp as uiux_bp
from routes.perf_routes import bp as perf_bp
from routes.integration_routes import bp as integration_bp
from routes.viz_routes import bp as viz_bp
from routes.observability_routes import bp as observability_bp
from routes.workflow_routes import bp as workflow_bp
from routes.cross_platform_routes import bp as cross_platform_bp
from routes.knowledge_graph_routes import bp as knowledge_graph_bp
from routes.smart_search_routes import bp as smart_search_bp
from routes.collaboration_routes import bp as collaboration_bp
from routes.version_control_routes import bp as version_control_bp
from routes.offline_routes import bp as offline_bp
from routes.realtime_routes import bp as realtime_bp
from routes.migration_i18n_routes import bp as migration_i18n_bp
from routes.accessibility_routes import bp as accessibility_bp
from routes.ml_basic_routes import bp as ml_basic_bp
from routes.nlp_routes import bp as nlp_bp
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
    analytics_bp,
    ai_intel_bp,
    devops_bp,
    platform_bp,
    delight_bp,
    resilience_bp,
    advanced_data_bp,
    security_bp2,
    smart_bp,
    uiux_bp,
    perf_bp,
    integration_bp,
    viz_bp,
    observability_bp,
    workflow_bp,
    cross_platform_bp,
    knowledge_graph_bp,
    smart_search_bp,
    collaboration_bp,
    version_control_bp,
    offline_bp,
    realtime_bp,
    migration_i18n_bp,
    accessibility_bp,
    ml_basic_bp,
    nlp_bp,
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
]
