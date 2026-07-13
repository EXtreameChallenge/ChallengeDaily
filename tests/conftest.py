"""
ChallengeDaily 测试公共 fixtures

注意：必须在导入任何项目模块之前设置 CHALLENGE_DAILY_DATA_DIR，
使 config.DATA_DIR / DB_PATH 指向临时目录，避免污染真实数据。
"""
import os
import tempfile

# ── 在导入项目模块前设置临时数据目录 ──
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="xiaohei_test_")
os.environ["CHALLENGE_DAILY_DATA_DIR"] = _TMP_DATA_DIR

import pytest

# 现在安全地导入项目模块（config 会读取上面的环境变量）
import config  # noqa: E402
import db  # noqa: E402
import server  # noqa: E402
import routes.deps as deps  # noqa: E402
from server import _rate_limit_store, _auth_fail_store  # noqa: E402


# ── Flask app fixture ──

@pytest.fixture
def app():
    """用临时数据库创建测试 Flask app（不依赖外部服务）"""
    db.init_db()
    yield server.app


@pytest.fixture
def client(app):
    """返回 app.test_client()"""
    return app.test_client()


@pytest.fixture
def authed_client(client):
    """带正确 X-API-Token header 的 client"""
    token = deps.LOCAL_TOKEN
    client.environ_base["HTTP_X_API_TOKEN"] = token
    return client


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """临时数据库文件：monkey-patch db.DB_PATH 到 tmp_path 下的独立文件"""
    db_path = tmp_path / "test_xiaohei.db"
    monkeypatch.setattr(db, "DB_PATH", db_path)
    # 重置线程局部连接，使下次 _get_thread_conn 使用新路径
    _reset_thread_conn()
    db._wal_initialized = False
    db.init_db()
    yield db_path
    _reset_thread_conn()
    db._wal_initialized = False


def _reset_thread_conn():
    """关闭并清除当前线程的数据库连接"""
    conn = getattr(db._local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        db._local.conn = None


# ── autouse: 每个测试前后清空速率限制 / 鉴权失败计数器 ──

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    _rate_limit_store.clear()
    _auth_fail_store.clear()
    yield
    _rate_limit_store.clear()
    _auth_fail_store.clear()
