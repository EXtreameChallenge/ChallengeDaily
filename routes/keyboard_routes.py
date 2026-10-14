"""
ChallengeDaily — 键盘热力图 & 机械音效 API 路由
"""
from flask import Blueprint, jsonify, request

keyboard_bp = Blueprint('keyboard', __name__, url_prefix='/api/keyboard')


@keyboard_bp.route('/stats', methods=['GET'])
def get_keyboard_stats():
    """获取按键统计"""
    from keyboard_tracker import get_stats, get_hotkeys
    return jsonify({
        "stats": get_stats(),
        "hotkeys": get_hotkeys(20),
    })


@keyboard_bp.route('/start', methods=['POST'])
def start_keyboard_listening():
    """启动按键监听"""
    from keyboard_tracker import start_listening
    start_listening()
    return jsonify({"ok": True, "message": "键盘监听已启动"})


@keyboard_bp.route('/stop', methods=['POST'])
def stop_keyboard_listening():
    """停止按键监听"""
    from keyboard_tracker import stop_listening
    stop_listening()
    return jsonify({"ok": True, "message": "键盘监听已停止"})


@keyboard_bp.route('/reset', methods=['POST'])
def reset_keyboard_stats():
    """重置统计"""
    from keyboard_tracker import reset_stats
    reset_stats()
    return jsonify({"ok": True})


@keyboard_bp.route('/sound/status', methods=['GET'])
def get_sound_status():
    """获取音效状态"""
    from mechanical_sound import get_status
    return jsonify(get_status())


@keyboard_bp.route('/sound/toggle', methods=['POST'])
def toggle_sound():
    """开关机械音效"""
    from mechanical_sound import set_enabled, is_enabled
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled', not is_enabled())
    set_enabled(enabled)
    return jsonify({"ok": True, "enabled": enabled})
