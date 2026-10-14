# ChallengeDaily Agent 系统架构

> 本文档描述 ChallengeDaily 智能 Agent 系统的整体架构、核心模块、工具开发流程与安全模型。
> 前端面板见 `client/src/components/AgentPanel.tsx`。

---

## 1. 系统概览

### 1.1 总体数据流（文字架构图）

```
用户 (Electron 前端)
   │  ① 输入消息
   ▼
SSE 流式接口  /api/ai/chat/stream
   │
   ▼
chat.py (路由层)
   │  ② 构造上下文 / 记忆
   ▼
AgentEngine (agent_engine.py)
   │
   ├──► Agno 模式 (agno 框架封装)
   │      ├── 34 个工具 (agent_tools.py)
   │      ├── 多 Agent Team (Planner / Executor / Reviewer)
   │      └── 推理路由 (低/中/高三档)
   │
   └──► Classic 模式 (降级方案，纯 prompt + function calling)
          └── 与 Agno 共用同一套工具与护栏
   │
   ▼
AgentGuard (agent_guard.py) ── 三级风险分类 / 确认令牌 / 审计
   │
   ▼
Tools 执行后端
   ├── DB (agent_db.py / db.py)
   ├── Memory (context_manager.py / memory_engine.py)
   └── MCP (mcp_server.py)
   │
   ▼
SSE 事件回流: content / tool_call / tool_result / done / error
```

### 1.2 四期改造内容总览

| 期次 | 目标 | 核心交付 |
|------|------|----------|
| 一期 | 工具化对话 | 34 个工具、Agno 封装、流式输出、基础护栏 |
| 二期 | 安全与可观测 | 三级风险分类、确认令牌、审计日志、指标接口 |
| 三期 | 多 Agent 协作 | Planner/Executor/Reviewer 三角色、工作流编排、断点续跑 |
| 四期 | 自进化 | 技能库 (skill_library)、反思钩子、项目数据地图、代码推理沙箱 |

---

## 2. 核心模块

### 2.1 `agent_engine.py` — 核心引擎

Agent 系统的入口，封装 Agno 框架并提供统一接口。

**关键能力：**

- **Agno 封装**：基于 `agno.Agent` 创建实例，注入工具列表、system prompt、记忆。
- **自定义 LLM Client**：通过 `BaseLLM` 适配本地 GLM / DeepSeek 接口，统一流式回调。
- **流式输出**：逐 token 通过 SSE 推送 `content` 事件，首字目标 < 2s。
- **确认机制**：危险工具执行前生成 `confirmation_token`，前端二次确认后才放行。
- **记忆集成**：接入 `context_manager` 做短期上下文，`memory_engine` 做长期偏好。
- **上下文压缩**：超过窗口阈值时自动摘要历史，保留最近 N 轮 + 摘要。
- **推理路由**：按问题复杂度选择 `low / medium / high` 三档推理强度，控制成本。
- **离线降级**：Agno 不可用时自动回退 Classic 模式（纯 function calling）。
- **多 Agent Team**：`PlannerAgent` 拆解任务 → `ExecutorAgent` 执行工具 → `ReviewerAgent` 校验结果。

```python
# agent_engine.py 核心接口示意
class AgentEngine:
    def __init__(self, mode: str = "agno"):
        self.mode = mode          # "agno" | "classic"
        self.guard = AgentGuard()
        self.tools = AGENT_TOOLS

    async def chat(self, message: str, history: list) -> AsyncIterator[dict]:
        """流式主入口，yield SSE 事件 dict"""
        # 1. 路由推理强度
        level = route_reasoning(message)
        # 2. 调用 Agno 或 Classic
        async for event in self._run(message, history, level):
            # 3. 经过护栏过滤危险调用
            yield self.guard.intercept(event)
```

### 2.2 `agent_tools.py` — 工具系统

34 个工具按风险分三类，统一以 pydantic 模型声明参数 + `execute` 函数实现。

**工具清单（分类）：**

| 分类 | 工具示例 | 风险级别 |
|------|----------|----------|
| 查询类（只读） | `get_activities`、`get_todos`、`get_pomodoro_stats`、`get_daily_summary`、`get_work_trends`、`get_user_profile`、`get_report`、`search_notes` | readonly |
| 操作类（写库） | `create_todo`、`update_todo`、`start_pomodoro`、`stop_pomodoro`、`save_diary`、`create_habit`、`schedule_task` | operation |
| 危险类（外部副作用） | `delete_todo`、`clear_history`、`run_code`、`send_email`、`modify_settings` | dangerous |

**动态工具加载机制：**

启动时遍历 `AGENT_TOOLS` 注册表，按 pydantic 模型的 JSON Schema 生成 Agno 工具描述；运行时可通过 `register_tool()` 热加载技能库中的新技能。

```python
# 工具定义范式
from pydantic import BaseModel, Field

class CreateTodoParams(BaseModel):
    title: str = Field(..., description="待办标题")
    priority: int = Field(1, ge=1, le=5)

async def execute_create_todo(params: CreateTodoParams) -> dict:
    from db import create_todo
    tid = create_todo(params.title, params.priority)
    return {"todo_id": tid, "title": params.title}

AGENT_TOOLS.append({
    "name": "create_todo",
    "params": CreateTodoParams,
    "execute": execute_create_todo,
    "risk": "operation",
})
```

### 2.3 `agent_guard.py` — 安全护栏

- **三级风险分类**：
  - `readonly`：只读查询，直接放行。
  - `operation`：写库操作，记录审计但不阻塞。
  - `dangerous`：删除/代码执行/外部调用，必须二次确认。
- **确认机制**：生成 `confirmation_token`（UUID），有效期 5 分钟，前端点击"确认执行"后携带 token 回调 `/api/ai/chat/execute` 才真正执行。
- **审计日志**：每次工具调用落库 `agent_audit_log`（工具名、风险、确认状态、耗时、入参摘要）。
- **Prompt Injection 防护**：系统 prompt 中隔离用户输入，检测"忽略以上指令"等模式并降级处理。

```python
class AgentGuard:
    DANGEROUS_TOOLS = {"delete_todo", "run_code", "modify_settings"}

    def intercept(self, event: dict) -> dict:
        if event.get("type") == "tool_call":
            name = event["name"]
            if name in self.DANGEROUS_TOOLS:
                token = self.issue_token(name, event["data"])
                event["need_confirm"] = True
                event["confirmation_token"] = token
        return event
```

### 2.4 `agent_db.py` — 数据持久化

三张核心表（SQLite）：

```sql
-- 已审核技能库
CREATE TABLE agent_skills (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT UNIQUE NOT NULL,
    description TEXT,
    risk_level  TEXT DEFAULT 'readonly',   -- readonly / operation / dangerous
    enabled     INTEGER DEFAULT 1,
    use_count   INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- 工作流任务状态（断点续跑）
CREATE TABLE agent_task_states (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_name TEXT NOT NULL,
    node_index    INTEGER NOT NULL,
    node_data     TEXT,                -- JSON 序列化的节点中间态
    status        TEXT DEFAULT 'running', -- running / done / failed
    started_at    TEXT,
    updated_at    TEXT
);

-- 审计日志
CREATE TABLE agent_audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name     TEXT NOT NULL,
    risk_level    TEXT,
    confirmed     INTEGER DEFAULT 0,
    duration_ms   INTEGER,
    params_digest TEXT,                  -- 入参摘要（脱敏）
    created_at    TEXT DEFAULT (datetime('now'))
);
```

### 2.5 `skill_library.py` — 自进化技能

- **技能卡片结构**：`name / description / trigger_pattern / tool_ref / use_count / feedback_score`。
- **反思钩子触发条件**：
  1. 同一类问题被连续提问 ≥ 3 次；
  2. 工具执行失败率 > 30%；
  3. 用户手动"将本次对话存为技能"。
- **技能匹配与注入**：用户消息进入时，按 `trigger_pattern` 做关键词/语义匹配，命中则把技能卡片注入 system prompt 顶部。

```python
class SkillLibrary:
    def match(self, user_message: str) -> list[dict]:
        """返回命中的技能卡片，注入到 prompt"""
        skills = db.query("SELECT * FROM agent_skills WHERE enabled=1")
        return [s for s in skills if self._hit(s, user_message)]
```

### 2.6 `code_agent.py` — 代码推理模式

- **适用场景**：用户要求"帮我跑一段脚本 / 分析数据 / 批处理文件"。
- **安全沙箱机制**：
  - **白名单**：仅允许 `pandas / numpy / os.path / json` 等安全模块；
  - **静态检查**：AST 遍历禁止 `subprocess / socket / open(..., 'w') / eval`；
  - **超时**：单段代码执行 5s 超时即 kill；
  - **目录隔离**：在临时目录执行，结果读回后端，不允许写用户目录。

### 2.7 `project_map.py` — 项目数据地图

- **地图内容**：项目内所有 API 路由、数据库表、可用工具的索引，供 Agent 自动发现"我能调什么"。
- **缓存机制**：内存缓存 24 小时，启动时构建一次；代码文件变更时增量更新。

### 2.8 `agent_workflows.py` — 工作流编排

- **内置工作流**：
  - `制定计划`：用户输入目标 → Planner 拆解为待办 → 写入 DB。
  - `每日复盘`：拉取当天活动/番茄/待办 → LLM 生成摘要 → 存入日记。
- **节点类型**：
  - `llm`：调用大模型生成文本；
  - `tool`：执行指定工具；
  - `human`：暂停等待用户确认。
- **断点续跑**：每个节点完成后把中间态写入 `agent_task_states`，崩溃后可从最近 checkpoint 恢复。

```python
WORKFLOWS = {
    "daily_review": [
        {"type": "tool", "tool": "get_activities"},
        {"type": "tool", "tool": "get_pomodoro_stats"},
        {"type": "llm", "prompt": "基于以下数据生成今日复盘: {input}"},
        {"type": "tool", "tool": "save_diary"},
    ],
}
```

---

## 3. 工具开发指南

### 3.1 添加新工具步骤

1. 在 `agent_tools.py` 定义 pydantic 参数模型：

   ```python
   class QueryWeatherParams(BaseModel):
       city: str = Field(..., description="城市名")
   ```

2. 实现 `execute` 异步函数：

   ```python
   async def execute_query_weather(params: QueryWeatherParams) -> dict:
       # 调用外部 API 或本地逻辑
       return {"city": params.city, "temp": 25}
   ```

3. 注册到 `AGENT_TOOLS` 列表：

   ```python
   AGENT_TOOLS.append({
       "name": "query_weather",
       "params": QueryWeatherParams,
       "execute": execute_query_weather,
       "risk": "readonly",
   })
   ```

4. 在 `agent_guard.py` 设置风险级别（一般在注册时声明即可）。

5. 若为写操作，在 `chat.py` 的 `execute_action` 中加入确认执行分支。

### 3.2 添加新 Agent

- 继承或配置 `AgentEngine`：

  ```python
  class ReviewerAgent(AgentEngine):
      SYSTEM_PROMPT = "你是审查员，检查上游输出是否有误..."
      TOOL_SUBSET = ["get_todos", "get_activities"]  # 仅放行只读工具
  ```

- 设置 system prompt 与工具子集（危险工具一律不放行）。

### 3.3 添加新工作流

- 在 `agent_workflows.py` 的 `WORKFLOWS` 字典中定义节点序列：

  ```python
  WORKFLOWS["weekly_review"] = [
      {"type": "tool", "tool": "get_work_trends"},
      {"type": "llm", "prompt": "生成本周趋势分析"},
  ]
  ```

- 前端通过 `/api/agent/tasks` 轮询即可看到进度。

---

## 4. 安全模型

### 4.1 工具三级分类详解

| 级别 | 示例 | 行为 |
|------|------|------|
| readonly | 查询类 | 直接执行，仅记审计 |
| operation | 写库 | 直接执行，记审计，前端显示操作回执 |
| dangerous | 删除/代码/外部调用 | 暂停 → 发 `confirmation_token` → 前端确认 → 执行 |

### 4.2 确认流程时序（文字描述）

```
Agent 调用 dangerous 工具
   │
   ▼
AgentGuard 拦截 → 生成 token（5 分钟有效）
   │
   ▼
SSE 推送: { type: "action", action: "...", confirm_message: "确认删除该待办？", confirmation_token }
   │
   ▼
前端渲染"确认执行 / 取消"按钮
   │
   ├── 用户点确认 → POST /api/ai/chat/execute { action, data, confirmation_token }
   │       │
   │       ▼
   │   chat.py 校验 token → 执行 → 写审计
   │
   └── 用户点取消 → 丢弃 token，不执行
```

### 4.3 代码执行安全边界

- AST 静态扫描 + 模块白名单 + 5s 超时 + 临时目录隔离；
- 禁止网络、禁止写用户目录、禁止 `eval/exec`；
- 结果仅把 stdout / 变量回传，不落地持久化。

### 4.4 数据隔离

- 所有 Agent 数据存在用户本地 SQLite，不上传云端；
- API Token 通过 Electron 桥注入，前端不硬编码；
- 审计日志中的入参做摘要脱敏（仅保留前 80 字符）。

---

## 5. 配置说明

### 5.1 `config.py` 中 AGENT_* 配置项

```python
# config.py
AGENT_MODE = "agno"            # "agno" | "classic"（feature flag 切换）
AGENT_DEFAULT_REASONING = "medium"
AGENT_CONFIRM_TTL_SECONDS = 300       # 确认令牌有效期
AGENT_CODE_TIMEOUT_SECONDS = 5
AGENT_MAP_CACHE_HOURS = 24
AGENT_ENABLE_MULTI_AGENT = True        # 多 Agent Team 开关
```

### 5.2 `.env` 环境变量

```bash
AGENT_MODE=agno
AGENT_LLM_BASE_URL=http://127.0.0.1:58888
AGENT_LLM_API_KEY=your-key
AGENT_LLM_MODEL=glm-4.5-flash
```

### 5.3 feature flag

通过 `feature_flags.py` 运行时切换 `agno / classic`，无需重启：

```python
from feature_flags import set_flag
set_flag("agent_mode", "classic")
```

---

## 6. 可观测性

### 6.1 `/api/agent/metrics` 指标

| 指标 | 含义 |
|------|------|
| `total_calls` | 累计工具调用次数 |
| `avg_response_ms` | 工具平均响应耗时 |
| `token_usage` | 累计 token 消耗 |
| `success_rate` | 工具成功率（成功/总调用） |

### 6.2 审计日志查询

`GET /api/agent/audit?limit=20` 返回最近 N 条审计记录，字段：`tool_name / risk_level / confirmed / duration_ms / created_at`。

### 6.3 性能目标

| 环节 | 目标 |
|------|------|
| 首字延迟 (TTFT) | < 2s |
| 单次工具调用 | < 500ms |
| 记忆检索 | < 200ms |
| 工作流断点恢复 | < 1s |

---

## 7. 前端集成

### 7.1 AgentPanel 组件

位置：`client/src/components/AgentPanel.tsx`，默认导出 `AgentPanel`。

功能模块：

1. **Agent 状态**：引擎类型 / 当前角色 / 推理强度；
2. **工具调用**：实时列表，监听 SSE `tool_call` / `tool_result`；
3. **协作流程**：Planner → Executor → Reviewer 三节点状态；
4. **工作流进度**：进度条 + 当前节点，数据来自 `/api/agent/tasks`；
5. **技能库**：搜索 / 详情展开 / 启用禁用，数据来自 `/api/agent/skills`；
6. **审计日志**：最近 10 条，数据来自 `/api/agent/audit`；
7. **指标概览**：总调用 / 平均响应 / Token / 成功率。

### 7.2 SSE 事件格式说明

AgentPanel 连接全局事件流 `/api/events/stream?token=...`，过滤以下事件：

```json
// 工具调用开始
{ "type": "tool_call", "data": { "id": "call_1", "name": "get_todos", "params": {} } }

// 工具调用结束
{ "type": "tool_result", "data": { "id": "call_1", "result": "[...]", "error": false } }

// 角色切换
{ "type": "agent_role", "data": { "role": "executor" } }

// 多 Agent 节点更新
{ "type": "team_update", "data": { "nodes": [
    {"key": "planner", "status": "done"},
    {"key": "executor", "status": "running"}
] } }

// 工作流进度
{ "type": "workflow_update", "data": { "name": "daily_review", "node_index": 1, "total_nodes": 4, "current_node": "llm" } }
```

### 7.3 零修改原则

- AgentPanel 是**新增独立组件**，不修改 `AIChat.tsx`；
- 可在任意页面 `<AgentPanel />` 引入，或通过 `visible` prop 控制显隐；
- REST 接口未就绪时组件自动降级为"暂无数据"占位，不影响主聊天流程。

---

## 附录：API 路由速查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/agent/status` | 当前 Agent 状态（引擎/角色/推理强度） |
| GET | `/api/agent/tasks` | 工作流任务与进度 |
| GET | `/api/agent/skills` | 技能库列表 |
| POST | `/api/agent/skills/:id/toggle` | 启用/禁用技能 |
| GET | `/api/agent/audit` | 审计日志 |
| GET | `/api/agent/metrics` | 指标概览 |
| GET | `/api/events/stream` | SSE 全局事件流（AgentPanel 订阅） |
