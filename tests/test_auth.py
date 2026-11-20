"""
鉴权中间件测试

覆盖：
- 公开路径不需 token
- 受保护路径无 token → 401
- 受保护路径带正确 token → 200
- 错误 token → 401
- 速率限制：localhost 豁免（既有设计，防前端 429 雪崩）；外部 IP 300 次/60s 后 → 429
- 鉴权失败锁定：localhost 豁免；外部 IP 5 次失败后第 6 次 → 429
"""
import server


# ── 公开路径 ──

def test_public_paths_no_token(client):
    """/api/health 不需 token"""
    resp = client.get("/api/health?quick=1")
    assert resp.status_code == 200


# ── 受保护路径 ──

def test_protected_path_no_token_returns_401(client):
    """/api/activities 无 token 返回 401"""
    resp = client.get("/api/activities")
    assert resp.status_code == 401


def test_protected_path_with_token_returns_200(authed_client):
    """带正确 token 返回 200"""
    resp = authed_client.get("/api/activities")
    assert resp.status_code == 200


def test_invalid_token_returns_401(client):
    """错误 token 返回 401"""
    resp = client.get("/api/activities", headers={"X-API-Token": "wrong-token-xxx"})
    assert resp.status_code == 401


# ── 速率限制 ──

_REMOTE = {"REMOTE_ADDR": "203.0.113.9"}   # TEST-NET-3 模拟外部 IP


def test_rate_limiting_localhost_exempt(client):
    """localhost 豁免限流（既有设计）：连续 61 次仍全部 200"""
    for i in range(61):
        resp = client.get("/api/health?quick=1")
        assert resp.status_code == 200, f"第 {i + 1} 次请求应通过，实际 {resp.status_code}"


def test_rate_limiting_remote_ip_429(client):
    """外部 IP：60s 窗口内 300 次后返回 429"""
    for i in range(server._RATE_LIMIT_MAX):
        resp = client.get("/api/health?quick=1", environ_overrides=_REMOTE)
        assert resp.status_code == 200, f"第 {i + 1} 次请求应通过，实际 {resp.status_code}"
    resp = client.get("/api/health?quick=1", environ_overrides=_REMOTE)
    assert resp.status_code == 429


# ── 鉴权失败锁定 ──

def test_auth_fail_lockout_remote_ip(client):
    """外部 IP：5 次错误 token 后第 6 次 429（localhost 豁免为既有设计）"""
    for i in range(server._AUTH_FAIL_LIMIT):
        resp = client.get("/api/activities", headers={"X-API-Token": "bad-token"},
                          environ_overrides=_REMOTE)
        assert resp.status_code == 401, f"第 {i + 1} 次失败应返回 401，实际 {resp.status_code}"
    resp = client.get("/api/activities", headers={"X-API-Token": "bad-token"},
                      environ_overrides=_REMOTE)
    assert resp.status_code == 429
