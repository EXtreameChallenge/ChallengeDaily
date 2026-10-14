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


# ── 视频发布器 ──
@enterprise_bp.route('/publisher/accounts', methods=['GET'])
def list_publisher_accounts():
    return jsonify(publisher.list_accounts())

@enterprise_bp.route('/publisher/bind', methods=['POST'])
def bind_publisher_account():
    data = request.get_json(silent=True) or {}
    return jsonify(publisher.bind_account(data.get('platform', ''), data.get('account', '')))

@enterprise_bp.route('/publisher/task', methods=['POST'])
def create_publish_task():
    data = request.get_json(silent=True) or {}
    return jsonify(publisher.create_task(data.get('videoPath', ''), data.get('platforms', [])))


# ── 微信集成 ──
@enterprise_bp.route('/wechat/state', methods=['GET'])
def wechat_state():
    return jsonify(wechat.get_state())

@enterprise_bp.route('/wechat/begin', methods=['POST'])
def wechat_begin():
    return jsonify(wechat.begin_bind())

@enterprise_bp.route('/wechat/unbind', methods=['POST'])
def wechat_unbind():
    return jsonify(wechat.unbind())


# ── 浏览器自动化 ──
@enterprise_bp.route('/browser/deepseek', methods=['POST'])
def open_deepseek():
    data = request.get_json(silent=True) or {}
    return jsonify(browser_auto.open_deepseek(data.get('prompt', '')))

@enterprise_bp.route('/browser/chatgpt', methods=['POST'])
def open_chatgpt():
    data = request.get_json(silent=True) or {}
    return jsonify(browser_auto.open_chatgpt(data.get('prompt', '')))


# ── MCP 服务器管理 ──
@enterprise_bp.route('/mcp/list', methods=['GET'])
def list_mcp():
    return jsonify(mcp_manager.list())

@enterprise_bp.route('/mcp/add', methods=['POST'])
def add_mcp():
    data = request.get_json(silent=True) or {}
    return jsonify(mcp_manager.add(data.get('name', ''), data.get('command', ''), data.get('args', [])))


# ── 小程序同步 ──
@enterprise_bp.route('/miniprogram/status', methods=['GET'])
def miniprogram_status():
    return jsonify(mini_sync.get_status())

@enterprise_bp.route('/miniprogram/sync', methods=['POST'])
def miniprogram_sync():
    return jsonify(mini_sync.sync_now())


# ── 学生认证 ──
@enterprise_bp.route('/student/status', methods=['GET'])
def student_status():
    return jsonify(student_verification.get_status())

@enterprise_bp.route('/student/submit', methods=['POST'])
def student_submit():
    data = request.get_json(silent=True) or {}
    return jsonify(student_verification.submit(data.get('email', '')))


# ── 效率节 ──
@enterprise_bp.route('/festival/info', methods=['GET'])
def festival_info():
    return jsonify(efficiency_festival.get_info())


# ── 问卷调查 ──
@enterprise_bp.route('/survey/active', methods=['GET'])
def active_surveys():
    return jsonify(survey_system.get_active())

@enterprise_bp.route('/survey/submit', methods=['POST'])
def submit_survey():
    data = request.get_json(silent=True) or {}
    return jsonify(survey_system.submit(data.get('id', ''), data.get('answers', {})))


# ── 遥测系统 ──
@enterprise_bp.route('/telemetry/track', methods=['POST'])
def track_event():
    data = request.get_json(silent=True) or {}
    telemetry.track(data.get('event', ''), data.get('data', {}))
    return jsonify({"ok": True})

@enterprise_bp.route('/telemetry/events', methods=['GET'])
def list_telemetry_events():
    return jsonify(telemetry.get_events())


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
