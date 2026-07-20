# -*- coding: utf-8 -*-
"""测试番茄自习室局域网广播

覆盖：
- /api/study-room/broadcast: 并行扫描耗时（回归：旧顺序实现需 ~78s 导致前端超时"广播失败"）、
  并发保护、成功计数
- /api/study-room/heartbeat: 免 token 访问（跨设备心跳不可能持有本机 token）
"""
import time
import pytest
from unittest.mock import patch

import routes.study_room as sr


@pytest.fixture(autouse=True)
def _clean_discovered():
    """清空已发现成员表和广播状态，避免测试间污染"""
    sr._discovered.clear()
    with sr._broadcast_lock:
        sr._broadcasting = False
    yield
    sr._discovered.clear()
    with sr._broadcast_lock:
        sr._broadcasting = False


# ── /api/study-room/broadcast ──

def test_broadcast_parallel_scan_fast(authed_client):
    """并行扫描应在数秒内返回（旧顺序实现 254×0.3s≈78s，前端 10s 超时必失败）"""
    def _fake_urlopen(req, timeout=None):
        time.sleep(0.25)  # 模拟每个 IP 的连接超时
        raise OSError("connection refused")

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        t0 = time.time()
        resp = authed_client.post('/api/study-room/broadcast', json={})
        elapsed = time.time() - t0

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["broadcasted"] == 0
    # 64 并发 × 4 批 × 0.25s ≈ 1s；放宽到 8s 兜底 CI 抖动，
    # 同时远低于旧实现的 78s 和前端 20s 超时
    assert elapsed < 8, f"广播耗时 {elapsed:.1f}s，疑似退化为顺序扫描"


def test_broadcast_counts_successful_hosts(authed_client):
    """能连通的 IP 应计入 broadcasted"""
    def _fake_urlopen(req, timeout=None):
        # 只有 .10/.20/.30 三个 IP "在线"
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if any(url.startswith(f"http://192.168.0.{i}:") for i in (10, 20, 30)):
            class _Resp:
                def close(self):
                    pass
            return _Resp()
        raise OSError("connection refused")

    with patch("routes.study_room._get_local_ip", return_value="192.168.0.5"), \
         patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        resp = authed_client.post('/api/study-room/broadcast', json={})

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["broadcasted"] == 3
    assert data["subnet"] == "192.168.0.0/24"


def test_broadcast_concurrent_guard(authed_client):
    """扫描进行中时再次触发应直接返回 scanning，不重复扫描"""
    with sr._broadcast_lock:
        sr._broadcasting = True
    resp = authed_client.post('/api/study-room/broadcast', json={})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "scanning"


# ── /api/study-room/heartbeat ──

def test_heartbeat_without_token_allowed(client):
    """跨设备心跳免 token：其他设备无法持有本机 token，必须公开"""
    resp = client.post('/api/study-room/heartbeat', json={
        "id": "peer-1", "name": "室友的电脑", "status": "focusing",
        "task": "写论文", "today_min": 45, "today_count": 2,
    })
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_heartbeat_registers_member(authed_client):
    """心跳应把对方登记到已发现成员，/status 能看到"""
    authed_client.post('/api/study-room/heartbeat', json={
        "id": "peer-1", "name": "室友的电脑", "status": "focusing",
        "task": "写论文", "today_min": 45, "today_count": 2,
    })
    resp = authed_client.get('/api/study-room/status')
    assert resp.status_code == 200
    members = resp.get_json()["members"]
    peers = [m for m in members if m.get("name") == "室友的电脑"]
    assert len(peers) == 1
    assert peers[0]["today_min"] == 45


def test_other_study_room_apis_still_require_token(client):
    """除心跳外的自习室接口仍须鉴权（安全回归）"""
    resp = client.get('/api/study-room/status')
    assert resp.status_code == 401
    resp = client.post('/api/study-room/broadcast', json={})
    assert resp.status_code == 401
