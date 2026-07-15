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
]
