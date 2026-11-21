"""B27 MCP 开关冒烟测试：真实启动 mcp_server.py 子进程。

覆盖：
1. mcp_enabled=true 时 initialize/tools/list 正常返回；
2. mcp_enabled=false 时进程拒绝启动（退出码 2）。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "mcp_server.py"


def _run(settings: dict | None, stdin_text: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        (data_dir / ".api_token").write_text("smoke-token", encoding="utf-8")
        if settings is not None:
            (data_dir / "settings.json").write_text(
                json.dumps(settings, ensure_ascii=False), encoding="utf-8"
            )
        env = os.environ.copy()
        env["CHALLENGE_DAILY_DATA_DIR"] = str(data_dir)
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, str(SERVER)],
            input=stdin_text,
            text=True,
            capture_output=True,
            cwd=str(REPO),
            env=env,
            timeout=20,
        )


def test_mcp_enabled_initialize_and_tools_list():
    requests = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "smoke", "version": "0"}}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
    ]) + "\n"
    proc = _run({"mcp_enabled": True}, requests)
    assert proc.returncode == 0, proc.stderr
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip().startswith("{")]
    by_id = {item.get("id"): item for item in lines}
    assert by_id[1]["result"]["protocolVersion"] == "2024-11-05"
    assert isinstance(by_id[2]["result"]["tools"], list)


def test_mcp_disabled_refuses_to_start():
    proc = _run({"mcp_enabled": False}, "")
    assert proc.returncode == 2
    assert "mcp_enabled=false" in proc.stderr or "MCP 服务已在设置中关闭" in proc.stderr


def test_mcp_missing_settings_defaults_to_disabled():
    proc = _run(None, "")
    assert proc.returncode == 2
