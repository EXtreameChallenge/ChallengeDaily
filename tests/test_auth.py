"""
鉴权中间件测试

覆盖：
- 公开路径不需 token
- 受保护路径无 token → 401
- 受保护路径带正确 token → 200
- 错误 token → 401
- 速率限制：60 次/60s 内通过，第 61 次 → 429
- 鉴权失败锁定：5 次失败后第 6 次 → 429
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

def test_rate_limiting(client):
    """60 次内通过，第 61 次 429"""
    # /api/health 是公开路径，不受鉴权影响，但速率限制对所有请求生效
    for i in range(60):
        resp = client.get("/api/health?quick=1")
        assert resp.status_code == 200, f"第 {i + 1} 次请求应通过，实际 {resp.status_code}"
    # 第 61 次应被限流
    resp = client.get("/api/health?quick=1")
    assert resp.status_code == 429


# ── 鉴权失败锁定 ──

def test_auth_fail_lockout(client):
    """5 次失败后第 6 次返回 429（锁定）"""
    # 前 5 次错误 token → 401，每次记录一次鉴权失败
    for i in range(5):
        resp = client.get("/api/activities", headers={"X-API-Token": "bad-token"})
        assert resp.status_code == 401, f"第 {i + 1} 次失败应返回 401，实际 {resp.status_code}"
    # 第 6 次：鉴权失败计数达上限 → 429
    resp = client.get("/api/activities", headers={"X-API-Token": "bad-token"})
    assert resp.status_code == 429
