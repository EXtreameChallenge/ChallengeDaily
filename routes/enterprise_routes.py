"""
ChallengeDaily — 企业级功能路由
批量暴露: 账号/积分/模板市场/发布器/微信/浏览器自动化/MCP/小程序/学生认证/效率节/问卷/遥测
"""
from flask import Blueprint, jsonify, request
from enterprise_features import (
    auth_manager, points_manager, template_market, publisher,
    wechat, browser_auto, mcp_manager, mini_sync,
    student_verification, efficiency_festival, survey_system, telemetry,
)

enterprise_bp = Blueprint('enterprise', __name__, url_prefix='/api/enterprise')


def _not_implemented(module: str, operation: str, detail: str = ""):
    """企业演示模块统一响应：不回假成功，明确标注未接线。"""
    return jsonify({
        "status": "not_implemented",
        "implemented": False,
        "module": module,
        "operation": operation,
        "message": detail or f"{module} 为演示模块，当前未接入真实服务",
    }), 501


def _demo_state(module: str, **extra):
    """只读状态也写明未实现，避免 UI 把空状态当成真实空数据。"""
    payload = {
        "status": "not_implemented",
        "implemented": False,
        "demo": True,
        "module": module,
        "message": f"{module} 为演示模块，当前未接入真实服务",
    }
    payload.update(extra)
    return jsonify(payload)


# ── 可选企业仿真插件状态 ──
@enterprise_bp.route('/plugin/status', methods=['GET'])
def enterprise_plugin_status():
    from enterprise_plugin import is_enabled, EXPECTED_BLUEPRINT_COUNT, EXPECTED_ENDPOINT_COUNT
    from flask import current_app
    status = current_app.extensions.get("enterprise_plugin", {})
    return jsonify({
        "configured": is_enabled(),
        "registered": status.get("registered", False),
        "blueprints": status.get("blueprints", 0),
        "endpoints": status.get("endpoints", 0),
        "manifest_blueprints": EXPECTED_BLUEPRINT_COUNT,
        "manifest_endpoints": EXPECTED_ENDPOINT_COUNT,
        "toggle": "CHALLENGEDAILY_ENTERPRISE_PLUGIN=1",
    })


# ── 账号体系 ──
@enterprise_bp.route('/auth/session', methods=['GET'])
def get_session():
    return jsonify(auth_manager.get_session())

@enterprise_bp.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    return jsonify(auth_manager.login(data.get('email', ''), data.get('password', '')))

@enterprise_bp.route('/auth/logout', methods=['POST'])
def logout():
    return jsonify(auth_manager.logout())


# ── 积分计费 ──
@enterprise_bp.route('/points/balance', methods=['GET'])
def get_balance():
    return jsonify(points_manager.get_balance())

@enterprise_bp.route('/points/consume', methods=['POST'])
def consume_points():
    data = request.get_json(silent=True) or {}
    return jsonify(points_manager.consume(data.get('amount', 0), data.get('reason', '')))

@enterprise_bp.route('/points/records', methods=['GET'])
def point_records():
    return jsonify(points_manager.get_usage_records())


# ── 模板市场 ──
@enterprise_bp.route('/templates/list', methods=['GET'])
def list_templates():
    return jsonify(template_market.list())

@enterprise_bp.route('/templates/publish', methods=['POST'])
def publish_template():
    data = request.get_json(silent=True) or {}
    return jsonify(template_market.publish(data.get('name', ''), data.get('content', ''), data.get('price', 0)))


# ── 视频发布器（演示/规划中） ──
@enterprise_bp.route('/publisher/accounts', methods=['GET'])
def list_publisher_accounts():
    return _demo_state('publisher', accounts=[])

@enterprise_bp.route('/publisher/bind', methods=['POST'])
def bind_publisher_account():
    return _not_implemented('publisher', 'bind_account', '视频平台账号绑定尚未接入，当前不会写入任何账号')

@enterprise_bp.route('/publisher/task', methods=['POST'])
def create_publish_task():
    return _not_implemented('publisher', 'create_task', '视频发布任务尚未接入，当前不会创建任务')


# ── 微信集成（演示/规划中） ──
@enterprise_bp.route('/wechat/state', methods=['GET'])
def wechat_state():
    return _demo_state('wechat', connected=False, qrcode=None)

@enterprise_bp.route('/wechat/begin', methods=['POST'])
def wechat_begin():
    return _not_implemented('wechat', 'begin_bind', '微信绑定尚未接入，当前不会拉起登录或写绑定状态')

@enterprise_bp.route('/wechat/unbind', methods=['POST'])
def wechat_unbind():
    return _not_implemented('wechat', 'unbind', '微信解绑尚未接入')


# ── 浏览器自动化（演示/规划中） ──
@enterprise_bp.route('/browser/deepseek', methods=['POST'])
def open_deepseek():
    return _not_implemented('browser', 'open_deepseek', '浏览器自动化尚未接入，当前不会启动浏览器')

@enterprise_bp.route('/browser/chatgpt', methods=['POST'])
def open_chatgpt():
    return _not_implemented('browser', 'open_chatgpt', '浏览器自动化尚未接入，当前不会启动浏览器')


# ── MCP 服务器管理（本页为演示；真开关在设置 → 集成） ──
@enterprise_bp.route('/mcp/list', methods=['GET'])
def list_mcp():
    return _demo_state('mcp', servers=[])

@enterprise_bp.route('/mcp/add', methods=['POST'])
def add_mcp():
    return _not_implemented('mcp', 'add', '企业页 MCP 管理为演示模块；请使用设置 → 集成中的 MCP 开关')


# ── 小程序同步（演示/规划中） ──
@enterprise_bp.route('/miniprogram/status', methods=['GET'])
def miniprogram_status():
    return _demo_state('miniprogram', connected=False, last_sync=None)

@enterprise_bp.route('/miniprogram/sync', methods=['POST'])
def miniprogram_sync():
    return _not_implemented('miniprogram', 'sync_now', '小程序同步尚未接入，当前不会上传或下载数据')


# ── 学生认证（演示/规划中） ──
@enterprise_bp.route('/student/status', methods=['GET'])
def student_status():
    return _demo_state('student', verified=False)

@enterprise_bp.route('/student/submit', methods=['POST'])
def student_submit():
    return _not_implemented('student', 'submit', '学生认证尚未接入，当前不会提交或自动通过')


# ── 效率节活动（演示/规划中） ──
@enterprise_bp.route('/festival/info', methods=['GET'])
def festival_info():
    return _demo_state('festival', active=False, events=[])


# ── 问卷调查（演示/规划中） ──
@enterprise_bp.route('/survey/active', methods=['GET'])
def active_surveys():
    return _demo_state('survey', surveys=[])

@enterprise_bp.route('/survey/submit', methods=['POST'])
def submit_survey():
    return _not_implemented('survey', 'submit', '问卷系统尚未接入，当前不会记录答案')


# ── 遥测系统（本地诊断，默认关闭，不上传） ──
@enterprise_bp.route('/telemetry/status', methods=['GET'])
def telemetry_status():
    return jsonify({
        "enabled": telemetry.is_enabled(),
        "storage": "local_jsonl",
        "upload": False,
        "events": len(telemetry.get_events(limit=1000)),
    })


@enterprise_bp.route('/telemetry/track', methods=['POST'])
def track_event():
    data = request.get_json(silent=True) or {}
    ok = telemetry.track(data.get('event', ''), data.get('data', {}))
    return jsonify({"ok": ok, "enabled": telemetry.is_enabled()})


@enterprise_bp.route('/telemetry/events', methods=['GET'])
def list_telemetry_events():
    limit = min(max(int(request.args.get('limit', 100)), 1), 1000)
    return jsonify({
        "enabled": telemetry.is_enabled(),
        "events": telemetry.get_events(limit=limit),
    })


@enterprise_bp.route('/telemetry/clear', methods=['POST'])
def clear_telemetry_events():
    return jsonify({"ok": True, "cleared": telemetry.clear()})


# ── 应用锁（含恢复词） ──
@enterprise_bp.route('/app-lock/status', methods=['GET'])
def app_lock_status():
    from app_lock import get_status
    return jsonify(get_status())

@enterprise_bp.route('/app-lock/setup', methods=['POST'])
def app_lock_setup():
    from app_lock import setup_lock
    data = request.get_json(silent=True) or {}
    return jsonify(setup_lock(data.get('password', ''), data.get('recoveryWord', '')))

@enterprise_bp.route('/app-lock/verify', methods=['POST'])
def app_lock_verify():
    from app_lock import verify_password
    data = request.get_json(silent=True) or {}
    return jsonify({"ok": verify_password(data.get('password', ''))})

@enterprise_bp.route('/app-lock/recovery', methods=['POST'])
def app_lock_recovery():
    from app_lock import verify_recovery
    data = request.get_json(silent=True) or {}
    return jsonify(verify_recovery(data.get('recoveryWord', '')))

@enterprise_bp.route('/app-lock/reset', methods=['POST'])
def app_lock_reset():
    from app_lock import reset_password
    data = request.get_json(silent=True) or {}
    return jsonify(reset_password(data.get('newPassword', '')))

@enterprise_bp.route('/app-lock/disable', methods=['POST'])
def app_lock_disable():
    from app_lock import disable_lock
    return jsonify(disable_lock())


# ── 朋友协作 ──
@enterprise_bp.route('/friends/list', methods=['GET'])
def list_friends():
    from friends import list_friends
    return jsonify(list_friends())

@enterprise_bp.route('/friends/add', methods=['POST'])
def add_friend():
    from friends import add_friend
    data = request.get_json(silent=True) or {}
    return jsonify(add_friend(data.get('name', ''), data.get('email', '')))

@enterprise_bp.route('/friends/invitations', methods=['GET'])
def list_invitations():
    from friends import list_invitations
    return jsonify(list_invitations())

@enterprise_bp.route('/friends/invite', methods=['POST'])
def send_invite():
    from friends import send_invitation
    data = request.get_json(silent=True) or {}
    return jsonify(send_invitation(data.get('friendId', ''), data.get('todoId', ''), data.get('message', '')))

@enterprise_bp.route('/friends/accept', methods=['POST'])
def accept_invite():
    from friends import accept_invitation
    data = request.get_json(silent=True) or {}
    return jsonify(accept_invitation(data.get('inviteId', '')))

@enterprise_bp.route('/friends/shared-todos', methods=['GET'])
def shared_todos():
    from friends import list_shared_todos
    return jsonify(list_shared_todos())
