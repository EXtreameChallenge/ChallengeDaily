# ChallengeDaily MCP 联调文档

> 适用版本：v3.9.11 起。MCP 服务默认**关闭**，必须在桌面端「设置 → 集成」打开 `mcp_enabled` 后才允许启动。

## 1. 它是什么

`mcp_server.py` 是一个 **stdio JSON-RPC** MCP 服务，不是 HTTP 端口。外部客户端（Claude Desktop、Cursor、TRAE、Continue 等）通过标准输入/输出与它通信，它再以本地 HTTP 调 `http://127.0.0.1:59300` 的 ChallengeDaily 后端，复用现有鉴权、校验和数据库事务。

## 2. 开关语义

| 位置 | 值 | 行为 |
|---|---|---|
| 设置 → 集成 → MCP stdio 服务 | 开 | `settings.json` 写入 `"mcp_enabled": true`，客户端可启动服务 |
| 设置 → 集成 → MCP stdio 服务 | 关（默认） | `"mcp_enabled": false`，`python mcp_server.py` 直接退出并提示关闭原因 |

开关只控制**外部客户端接入**，不会影响桌面端 Agent 的正常使用。

## 3. 客户端配置

把下面配置合并进客户端自己的 MCP 配置文件（路径以客户端文档为准）：

```json
{
  "mcpServers": {
    "challenge-daily": {
      "command": "C:\\Users\\<you>\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
      "args": ["D:\\Project\\OpenSourcePlan\\ChallengeDaily20260703\\ChallengeDaily\\mcp_server.py"],
      "env": {
        "CHALLENGE_DAILY_DATA_DIR": "C:\\Users\\<you>\\AppData\\Roaming\\challenge-daily\\backend-data"
      }
    }
  }
}
```

注意：

- `command` 建议写 Python 绝对路径，避免客户端 PATH 找不到解释器。
- `args` 写 `mcp_server.py` 绝对路径；如果工作目录就是仓库根目录，也可以写相对路径。
- `CHALLENGE_DAILY_DATA_DIR` 应指向**含 `.api_token` 的 backend-data 目录**；不填时脚本会按 `APPDATA` 和仓库 `data/` 自动探测。
- 改完开关或路径后需重启外部客户端。

## 4. 冒烟测试

在仓库根目录执行：

```powershell
# 1) 确认开关已开
python -c "import json,pathlib,os; p=pathlib.Path(os.getenv('APPDATA'))/'challenge-daily'/'backend-data'/'settings.json'; print(json.loads(p.read_text(encoding='utf-8')).get('mcp_enabled'))"

# 2) 进程级冒烟：initialize + tools/list + 退出
python tests/test_round9_mcp_smoke.py
```

测试会启动真实 `mcp_server.py` 子进程，发送 `initialize` / `tools/list`，断言返回协议版本和工具列表；随后关闭开关再启动一次，断言进程以非 0 退出并打印关闭提示。

## 5. 工具面

工具列表由 `mcp_server.py` 的 `_TOOL_REGISTRY` 决定，全部走本地后端 API，不直接读数据库。常用工具包括活动查询、统计、待办、日报、设置读取等；具体 schema 可通过 `tools/list` 获取。

## 6. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 客户端显示 MCP 启动失败 | 开关关闭 / Python 路径错误 / 数据目录不含 `.api_token` | 先手动 `python mcp_server.py` 看 stderr |
| `Backend error (401)` | 未读取到 `.api_token` 或后端未启动 | 确认后端 `59300` 健康，检查 `CHALLENGE_DAILY_DATA_DIR` |
| `Backend error (timeout)` | 后端忙或 AI 请求超时 | 重试，或把 `CHALLENGE_DAILY_BACKEND_TIMEOUT` 调大 |
| 工具列表为空 | 客户端未完成 `initialize` | 按 MCP 协议先发 `initialize` 再 `tools/list` |
