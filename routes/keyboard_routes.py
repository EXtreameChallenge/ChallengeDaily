"""
ChallengeDaily — 键盘热力图 & 机械音效 API 路由
Wave2-B06/B12：不再假报 ok，监听不可用/音效不可用时如实返回原因。
"""
from flask import Blueprint, jsonify, request

keyboard_bp = Blueprint('keyboard', __name__, url_prefix='/api/keyboard')


@keyboard_bp.route('/stats', methods=['GET'])
def get_keyboard_stats():
    """获取按键统计（含监听/依赖可用性）"""
    from keyboard_tracker import get_stats, get_hotkeys, is_listening, check_availability
    return jsonify({
        "stats": get_stats(),
        "hotkeys": get_hotkeys(20),
        "listening": is_listening(),
        "available": check_availability(),
    })


@keyboard_bp.route('/start', methods=['POST'])
def start_keyboard_listening():
    """启动按键监听（依赖缺失时 ok:false + 原因）"""
    from keyboard_tracker import start_listening
    result = start_listening()
    return jsonify(result)


@keyboard_bp.route('/stop', methods=['POST'])
def stop_keyboard_listening():
    """停止按键监听"""
    from keyboard_tracker import stop_listening
    result = stop_listening()
    return jsonify(result)


@keyboard_bp.route('/reset', methods=['POST'])
def reset_keyboard_stats():
    """重置统计（内存 + 今日持久化行）"""
    from keyboard_tracker import reset_stats
    result = reset_stats()
    return jsonify(result)


@keyboard_bp.route('/sound/status', methods=['GET'])
def get_sound_status():
    """获取音效状态（含真实可用性）"""
    from mechanical_sound import get_status
    return jsonify(get_status())


@keyboard_bp.route('/sound/toggle', methods=['POST'])
def toggle_sound():
    """开关机械音效（不可用时拒绝并说明原因）"""
    from mechanical_sound import set_enabled, is_enabled
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled', not is_enabled())
    result = set_enabled(bool(enabled))
    return jsonify(result)
