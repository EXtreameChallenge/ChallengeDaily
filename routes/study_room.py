"""番茄自习室 — 局域网 mDNS 发现 + 实时状态广播 + 排行榜

对标番茄TODO自习室，但无需服务器，同局域网自动发现。
使用 HTTP 轮询实现状态同步（避免 WebSocket 复杂度）。
"""
import logging
import json
import time
import socket
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify
import db

logger = logging.getLogger(__name__)

bp = Blueprint('study_room', __name__, url_prefix='/api/study-room')

_member_id = f"{socket.gethostname()}-{int(time.time())}"
_local_member = {
    "id": _member_id,
    "name": socket.gethostname(),
    "status": "idle",  # idle / focusing / break / away
    "task": "",
    "started_at": None,
    "today_min": 0,
    "today_count": 0,
    "last_heartbeat": time.time(),
}
_local_lock = threading.Lock()

_discovered: dict = {}
_DISCOVERY_TIMEOUT = 60


def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


@bp.route('/status', methods=['GET'])
def get_status():
    """获取自习室状态：本机 + 已发现成员"""
    now = time.time()
    with _local_lock:
        expired = [ip for ip, m in _discovered.items() if now - m.get("last_heartbeat", 0) > _DISCOVERY_TIMEOUT]
        for ip in expired:
            del _discovered[ip]
        members = list(_discovered.values())
        local = {**_local_member, "is_self": True, "ip": _get_local_ip()}

    try:
        today_stats = db.get_pomodoro_today_count()
        local["today_count"] = today_stats.get("count", 0)
        local["today_min"] = today_stats.get("total_min", 0)
    except:
        pass

    all_members = [local] + members
    leaderboard = sorted(all_members, key=lambda m: m.get("today_min", 0), reverse=True)

    return jsonify({
        "members": all_members,
        "leaderboard": leaderboard,
        "online_count": len(all_members),
        "focusing_count": sum(1 for m in all_members if m.get("status") == "focusing"),
    })


@bp.route('/heartbeat', methods=['POST'])
def heartbeat():
    """接收其他成员的心跳广播（局域网内其他设备调用）"""
    data = request.get_json(force=True, silent=True) or {}
    ip = request.remote_addr
    with _local_lock:
        _discovered[ip] = {
            **data,
            "ip": ip,
            "is_self": False,
            "last_heartbeat": time.time(),
        }
    return jsonify({"status": "ok"})


@bp.route('/update', methods=['POST'])
def update_status():
    """更新本机状态（番茄开始/结束/休息时调用）"""
    data = request.get_json(force=True, silent=True) or {}
    with _local_lock:
        _local_member["status"] = data.get("status", "idle")
        _local_member["task"] = data.get("task", "")
        _local_member["started_at"] = data.get("started_at")
        _local_member["last_heartbeat"] = time.time()
    return jsonify({"status": "ok"})


@bp.route('/broadcast', methods=['POST'])
def broadcast_to_lan():
    """向局域网广播本机状态"""
    local_ip = _get_local_ip()
    parts = local_ip.split(".")
    if len(parts) != 4:
        return jsonify({"error": "无法解析局域网网段"})
    base = ".".join(parts[:3])
    my_port = request.host.split(":")[-1] if ":" in request.host else "5000"

    with _local_lock:
        payload = {**_local_member, "ip": local_ip}

    sent = 0
    for i in range(1, 255):
        target_ip = f"{base}.{i}"
        if target_ip == local_ip:
            continue
        try:
            import urllib.request
            url = f"http://{target_ip}:{my_port}/api/study-room/heartbeat"
            req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=0.3)
            sent += 1
        except:
            pass

    return jsonify({"status": "ok", "broadcasted": sent, "subnet": f"{base}.0/24"})


@bp.route('/leaderboard', methods=['GET'])
def get_leaderboard():
    """获取排行榜（按今日专注分钟降序）"""
    now = time.time()
    with _local_lock:
        expired = [ip for ip, m in _discovered.items() if now - m.get("last_heartbeat", 0) > _DISCOVERY_TIMEOUT]
        for ip in expired:
            del _discovered[ip]
        members = list(_discovered.values())

    local = {**_local_member, "is_self": True, "ip": _get_local_ip()}
    try:
        today_stats = db.get_pomodoro_today_count()
        local["today_count"] = today_stats.get("count", 0)
        local["today_min"] = today_stats.get("total_min", 0)
    except:
        pass

    all_members = [local] + members
    leaderboard = sorted(all_members, key=lambda m: m.get("today_min", 0), reverse=True)

    return jsonify({
        "leaderboard": leaderboard,
        "my_rank": next((i + 1 for i, m in enumerate(leaderboard) if m.get("is_self")), len(leaderboard)),
    })
